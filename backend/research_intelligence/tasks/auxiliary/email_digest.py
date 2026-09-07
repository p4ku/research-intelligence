import logging
from typing import Optional, List, Dict, Any
from django.db import close_old_connections
from django.utils import timezone
from celery import shared_task
from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    Extraction,
    Subscriber,
)
from research_intelligence.utils.mailer import send_mailgun_message

from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def build_pipeline_run_digest_payload(
    pipeline_run: Optional[PipelineRun] = None,
    agent_process: Optional[Any] = None,
    workspace: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Gathers metrics, papers, extractions, and definitions for an executed PipelineRun/ResearchAgentProcess
    and generates both state-of-the-art responsive HTML and clean plaintext email content
    using Django's template engine (emails/pipeline_digest.html and emails/pipeline_digest.txt).
    """
    workspace = workspace or (pipeline_run.workspace if pipeline_run else (agent_process.workspace if agent_process else None))
    ws_name = workspace.name if workspace else "Research Workspace"
    run_date_str = (
        pipeline_run.started_at.strftime("%B %d, %Y %H:%M UTC")
        if (pipeline_run and pipeline_run.started_at)
        else timezone.now().strftime("%B %d, %Y %H:%M UTC")
    )
    duration_str = pipeline_run.execution_time_display if pipeline_run else "N/A"

    # 1. Fetch papers and extractions
    if pipeline_run:
        papers_qs = pipeline_run.get_papers().prefetch_related(
            'extractions', 'extractions__extraction_definition'
        ).order_by('-created_at')
    elif workspace:
        papers_qs = Paper.objects.filter(workspace=workspace).prefetch_related(
            'extractions', 'extractions__extraction_definition'
        ).order_by('-created_at')
    else:
        papers_qs = Paper.objects.none()

    # Determine truly accepted papers based on the terminal screening stage:
    if pipeline_run:
        if pipeline_run.get_papers(screening_status=['full_text_passed', 'accepted']).exists():
            accepted_papers = list(pipeline_run.get_papers(screening_status=['full_text_passed', 'accepted']).prefetch_related('extractions', 'extractions__extraction_definition'))
        elif pipeline_run.get_papers(screening_status='abstract_passed').exists():
            accepted_papers = list(pipeline_run.get_papers(screening_status='abstract_passed').prefetch_related('extractions', 'extractions__extraction_definition'))
        else:
            accepted_papers = list(pipeline_run.get_papers(exclude_status=['rejected', 'withdrawn', 'pending']).prefetch_related('extractions', 'extractions__extraction_definition'))
    elif workspace:
        ws_accepted = Paper.objects.filter(
            workspace=workspace,
            metrics__screening_status__in=['full_text_passed', 'accepted']
        ).distinct().prefetch_related('extractions', 'extractions__extraction_definition')
        if ws_accepted.exists():
            accepted_papers = list(ws_accepted)
        else:
            ws_abs_accepted = Paper.objects.filter(
                workspace=workspace,
                metrics__screening_status='abstract_passed'
            ).distinct().prefetch_related('extractions', 'extractions__extraction_definition')
            if ws_abs_accepted.exists():
                accepted_papers = list(ws_abs_accepted)
            else:
                accepted_papers = list(Paper.objects.filter(workspace=workspace).exclude(
                    metrics__screening_status__in=['rejected', 'withdrawn', 'pending']
                ).distinct().prefetch_related('extractions', 'extractions__extraction_definition'))
    else:
        accepted_papers = []

    from research_intelligence.models import PaperMetric
    if pipeline_run and accepted_papers:
        metrics_by_paper = {
            pm.paper_id: pm for pm in PaperMetric.objects.filter(paper__in=accepted_papers, pipeline_run=pipeline_run)
        }
    elif accepted_papers:
        metrics_by_paper = {}
        for pm in PaperMetric.objects.filter(paper__in=accepted_papers).order_by('-created_at'):
            if pm.paper_id not in metrics_by_paper:
                metrics_by_paper[pm.paper_id] = pm
    else:
        metrics_by_paper = {}

    # Sort accepted papers: scored papers with highest signal_score first, then unscored by creation date
    accepted_papers.sort(
        key=lambda p: (
            metrics_by_paper.get(p.id).signal_score is not None if metrics_by_paper.get(p.id) else False,
            metrics_by_paper.get(p.id).signal_score if (metrics_by_paper.get(p.id) and metrics_by_paper.get(p.id).signal_score is not None) else -1.0,
            p.created_at
        ),
        reverse=True
    )

    total_papers = papers_qs.count()
    if total_papers == 0 and pipeline_run and pipeline_run.total_papers_fetched:
        total_papers = pipeline_run.total_papers_fetched
    rejected_count = max(0, total_papers - len(accepted_papers))

    # Calculate signal score summary
    scored_metrics = [
        metrics_by_paper[p.id].signal_score
        for p in accepted_papers
        if p.id in metrics_by_paper and metrics_by_paper[p.id].signal_score is not None
    ]
    avg_signal_score = (sum(scored_metrics) / len(scored_metrics)) if scored_metrics else None
    top_signal_score = max(scored_metrics, default=None)

    # 2. Gather extractions across accepted papers
    all_extractions = []
    for p in accepted_papers:
        all_extractions.extend(list(p.extractions.all()))
    total_extractions = len(all_extractions)
    if total_extractions == 0 and pipeline_run:
        total_extractions = Extraction.objects.filter(paper__in=pipeline_run.get_papers()).count()

    cost_val = float(pipeline_run.usd_cost or 0.0) if pipeline_run else 0.0
    tokens_val = int(pipeline_run.tokens_consumed or 0) if pipeline_run else 0

    # 3. Fetch active extraction definitions for the matrix columns
    active_definitions = list(workspace.extraction_definitions.filter(is_active=True).order_by('created_at')) if workspace else []
    if not active_definitions and all_extractions:
        seen_def_ids = set()
        for ext in all_extractions:
            if ext.extraction_definition and ext.extraction_definition.id not in seen_def_ids:
                seen_def_ids.add(ext.extraction_definition.id)
                active_definitions.append(ext.extraction_definition)

    definition_names = [d.name for d in active_definitions]

    # 4. Build papers scorecard & matrix items
    papers_data = []
    has_gated = False

    for idx, p in enumerate(accepted_papers, 1):
        paper_exts = list(p.extractions.all())
        exts_list = []
        metrics_by_def_id = {}
        metrics_by_name = {}
        metrics_by_norm_name = {}

        for ext in paper_exts:
            def_obj = ext.extraction_definition
            def_name = def_obj.name if def_obj else (ext.category or "Parameter")
            metric_val = ext.exit_metric
            if not metric_val or metric_val == "-":
                if ext.fields_data and isinstance(ext.fields_data, dict):
                    data = ext.fields_data.get("fields", ext.fields_data)
                    if isinstance(data, dict):
                        for k, v in data.items():
                            if isinstance(v, dict) and "value" in v:
                                metric_val = str(v["value"])
                                break
                            elif v is not None and not str(v).startswith("http") and len(str(v)) < 100:
                                metric_val = str(v)
                                break
            metric_val = metric_val or "-"

            if def_obj:
                metrics_by_def_id[str(def_obj.id)] = metric_val
            metrics_by_name[def_name] = metric_val
            metrics_by_norm_name[def_name.lower().replace(" ", "_")] = metric_val
            if ext.category:
                metrics_by_norm_name[ext.category.lower().replace(" ", "_")] = metric_val

            exts_list.append({
                "name": def_name,
                "value": metric_val,
                "confidence": ext.confidence_score,
                "confidence_percent": int(ext.confidence_score * 100) if ext.confidence_score is not None else None,
                "status": ext.validation_status or "pass",
            })

        matrix_entries = []
        for def_obj in active_definitions:
            norm_key = def_obj.name.lower().replace(" ", "_")
            val = (
                metrics_by_def_id.get(str(def_obj.id))
                or metrics_by_name.get(def_obj.name)
                or metrics_by_norm_name.get(norm_key)
            )
            if not val or val == "-":
                for k, v in metrics_by_norm_name.items():
                    if k in norm_key or norm_key in k:
                        val = v
                        break
            matrix_entries.append({"name": def_obj.name, "value": val or "-"})

        pdf_link = (
            f"https://arxiv.org/pdf/{p.arxiv_id}.pdf"
            if p.arxiv_id
            else (f"https://doi.org/{p.doi}" if p.doi else p.original_pdf_path)
        )

        pm = metrics_by_paper.get(p.id)
        pm_status = (pm.screening_status if pm else 'pending').replace('_', ' ')
        abs_reason = (pm.abstract_screening_reasoning if pm else '') or ''
        ft_reason = (pm.full_text_screening_reasoning if pm else '') or ''
        pm_score = pm.signal_score if pm else None

        is_gated_paper = False
        if pm_score == 0.0 and len(scored_metrics) > 0 and (top_signal_score or 0.0) > 0.0:
            is_gated_paper = True
            has_gated = True

        if pm_score is not None:
            score_formatted = f"{pm_score:.2f}"
            if is_gated_paper:
                score_formatted += "*"
        else:
            score_formatted = "-"

        papers_data.append({
            "index": idx,
            "title": p.title,
            "authors": p.authors or "Unknown Authors",
            "doi": p.doi,
            "arxiv_id": p.arxiv_id,
            "source_url": p.source_url or (f"https://doi.org/{p.doi}" if p.doi else None),
            "pdf_link": pdf_link,
            "abstract": p.abstract or "",
            "screening_status": pm_status,
            "abstract_screening_reasoning": abs_reason,
            "full_text_screening_reasoning": ft_reason,
            "signal_score": round(pm_score, 2) if pm_score is not None else None,
            "signal_score_formatted": score_formatted,
            "is_gated": is_gated_paper,
            "matrix_entries": matrix_entries,
            "extractions": exts_list,
        })

    agent_title = agent_process.name if agent_process else f"Pipeline Run {pipeline_run.id if pipeline_run else 'Manual'}"
    status_val = (agent_process.status if agent_process else (pipeline_run.status if pipeline_run else 'completed')).upper()
    error_msg = (agent_process.error_message if agent_process else None)

    # 5. Context for Django Template Rendering
    context = {
        "workspace": workspace,
        "workspace_name": ws_name,
        "agent_process": agent_process,
        "agent_title": agent_title,
        "status": status_val,
        "error_message": error_msg,
        "pipeline_run": pipeline_run,
        "run_date_str": run_date_str,
        "duration_str": duration_str,
        "total_papers": total_papers,
        "accepted_count": len(accepted_papers),
        "rejected_count": rejected_count,
        "total_extractions": total_extractions,
        "avg_signal_score": f"{avg_signal_score:.2f}" if avg_signal_score is not None else None,
        "top_signal_score": f"{top_signal_score:.2f}" if top_signal_score is not None else None,
        "cost_usd": cost_val,
        "tokens_consumed": f"{tokens_val:,}",
        "definition_names": definition_names,
        "has_definitions": bool(definition_names),
        "papers_data": papers_data,
        "has_gated": has_gated,
    }

    # 6. Render via Django Template Loader
    html_content = render_to_string("emails/pipeline_digest.html", context)
    text_content = render_to_string("emails/pipeline_digest.txt", context)

    if agent_process:
        subject = f"[{status_val}] Research Intelligence Pipeline: {agent_title} ({ws_name})"
    else:
        subject = f"[Research Digest] {ws_name} - Review Complete ({len(accepted_papers)} accepted papers)"

    return {
        "subject": subject,
        "context": context,
        "html_content": html_content,
        "text_content": text_content,
        "stats": {
            "workspace_id": str(workspace.id) if workspace else None,
            "workspace_name": ws_name,
            "pipeline_run_id": str(pipeline_run.id) if pipeline_run else None,
            "total_papers": total_papers,
            "accepted_papers": len(accepted_papers),
            "rejected_papers": rejected_count,
            "total_extractions": total_extractions,
            "cost_usd": cost_val,
            "tokens_consumed": tokens_val,
        }
    }


def dispatch_pipeline_subscriber_digest(
    workspace_id: str,
    pipeline_run_id: str,
    recipient_override: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Main dispatch engine: Validates pipeline completion, gathers subscriber list,
    builds the rich executive email using Django templates, and delivers messages via Mailgun.
    """
    close_old_connections()

    # 1. Resolve Workspace
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except (Workspace.DoesNotExist, ValueError):
        return {
            "status": "error",
            "error": f"Workspace '{workspace_id}' does not exist."
        }

    # 2. Resolve PipelineRun and validate completion
    try:
        pipeline_run = PipelineRun.objects.select_related('workspace').get(pk=pipeline_run_id, workspace=workspace)
    except (PipelineRun.DoesNotExist, ValueError):
        return {
            "status": "error",
            "error": f"PipelineRun '{pipeline_run_id}' does not exist in workspace '{workspace.name}'."
        }

    if pipeline_run.status != 'completed':
        # Check if pipeline run is still active or failed
        return {
            "status": "error",
            "error": (
                f"Cannot send digest: PipelineRun status is '{pipeline_run.status}'. "
                f"Digest emails can only be sent for 'completed' runs with verified parameters."
            )
        }

    # 3. Resolve Recipients
    recipients = []
    if recipient_override and isinstance(recipient_override, list):
        recipients = [e.strip() for e in recipient_override if e and "@" in e]
    else:
        subscribers = workspace.subscribers.filter(is_active=True)
        recipients = [s.email for s in subscribers if s.email]

    if not recipients:
        return {
            "status": "no_subscribers",
            "message": f"No active subscribers found for workspace '{workspace.name}', and no recipient override provided.",
            "workspace_id": str(workspace.id),
            "pipeline_run_id": str(pipeline_run.id),
            "sent_count": 0,
            "failed_count": 0,
            "recipients": []
        }

    # 4. Generate Digest Payload & Context
    digest_payload = build_pipeline_run_digest_payload(pipeline_run)
    subject = digest_payload["subject"]
    context = digest_payload["context"]

    # 5. Dispatch to each recipient via Mailgun (using template_name)
    sent_count = 0
    failed_count = 0
    delivery_results = []

    for email in recipients:
        success, resp_or_err = send_mailgun_message(
            to_email=email,
            subject=subject,
            template_name="emails/pipeline_digest",
            context=context,
        )
        if success:
            sent_count += 1
            delivery_results.append({"email": email, "status": "sent", "response": resp_or_err})
            logger.info(f"📧 [DIGEST EMAIL SENT] Workspace '{workspace.name}' -> {email}")
        else:
            failed_count += 1
            delivery_results.append({"email": email, "status": "failed", "error": str(resp_or_err)})
            logger.error(f"❌ [DIGEST EMAIL FAILED] Workspace '{workspace.name}' -> {email}: {resp_or_err}")

    return {
        "status": "success" if sent_count > 0 else "failed",
        "workspace_id": str(workspace.id),
        "workspace_name": workspace.name,
        "pipeline_run_id": str(pipeline_run.id),
        "total_recipients": len(recipients),
        "sent_count": sent_count,
        "failed_count": failed_count,
        "stats": digest_payload["stats"],
        "deliveries": delivery_results,
    }


@shared_task(name="tasks.auxiliary.send_pipeline_subscriber_digest_task", bind=True)
def send_pipeline_subscriber_digest_task(
    self,
    workspace_id: str,
    pipeline_run_id: str,
    recipient_override: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Celery background worker task for dispatching subscriber digest emails asynchronously.
    """
    logger.info(f"🚀 [TASK START] send_pipeline_subscriber_digest_task ws={workspace_id} run={pipeline_run_id}")
    res = dispatch_pipeline_subscriber_digest(workspace_id, pipeline_run_id, recipient_override)
    logger.info(f"🏁 [TASK FINISHED] send_pipeline_subscriber_digest_task ws={workspace_id} run={pipeline_run_id} status={res.get('status')}")
    return res
