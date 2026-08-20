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
from research_intelligence.utils.mailer import send_mailgun_message

logger = logging.getLogger(__name__)


def build_pipeline_run_digest_payload(pipeline_run: PipelineRun) -> Dict[str, Any]:
    """
    Gathers metrics, papers, extractions, and definitions for an executed PipelineRun
    and generates both state-of-the-art responsive HTML and clean plaintext email content
    using Django's template engine (emails/pipeline_digest.html and emails/pipeline_digest.txt).
    """
    workspace = pipeline_run.workspace
    ws_name = workspace.name if workspace else "Research Workspace"
    run_date_str = (
        pipeline_run.started_at.strftime("%B %d, %Y %H:%M UTC")
        if pipeline_run.started_at
        else timezone.now().strftime("%B %d, %Y")
    )
    duration_str = pipeline_run.execution_time_display

    # 1. Fetch papers and extractions
    papers_qs = Paper.objects.filter(pipeline_run=pipeline_run).prefetch_related(
        'extractions', 'extractions__extraction_definition'
    ).order_by('-created_at')

    total_papers = papers_qs.count()
    accepted_papers = [
        p for p in papers_qs
        if p.screening_status in ['accepted', 'full_text_passed', 'abstract_passed']
    ]
    rejected_count = total_papers - len(accepted_papers)

    # 2. Gather extractions
    extractions_qs = Extraction.objects.filter(paper__pipeline_run=pipeline_run).select_related(
        'paper', 'extraction_definition'
    )
    total_extractions = extractions_qs.count()

    cost_val = float(pipeline_run.usd_cost or 0.0)
    tokens_val = int(pipeline_run.tokens_consumed or 0)

    # 3. Build papers scorecard items
    papers_data = []
    for p in accepted_papers[:15]:  # top 15 in email digest for optimal reading length
        paper_exts = list(p.extractions.all())
        exts_list = []
        for ext in paper_exts:
            def_name = (
                ext.extraction_definition.name
                if ext.extraction_definition
                else (ext.category or "Parameter")
            )
            metric_val = ext.exit_metric or ext.get_exit_metric() or "Extracted"
            exts_list.append({
                "name": def_name,
                "value": metric_val,
                "confidence": ext.confidence_score,
                "confidence_percent": int(ext.confidence_score * 100) if ext.confidence_score else None,
                "status": ext.validation_status or "pass",
            })

        pdf_link = (
            f"https://arxiv.org/pdf/{p.arxiv_id}.pdf"
            if p.arxiv_id
            else (f"https://doi.org/{p.doi}" if p.doi else None)
        )

        papers_data.append({
            "title": p.title,
            "authors": p.authors or "Unknown Authors",
            "doi": p.doi,
            "arxiv_id": p.arxiv_id,
            "pdf_link": pdf_link,
            "screening_status": p.screening_status.replace('_', ' '),
            "screening_reason": p.screening_reasoning or "",
            "extractions": exts_list,
        })

    # 4. Context for Django Template Rendering
    context = {
        "workspace": workspace,
        "workspace_name": ws_name,
        "pipeline_run": pipeline_run,
        "run_date_str": run_date_str,
        "duration_str": duration_str,
        "total_papers": total_papers,
        "accepted_count": len(accepted_papers),
        "rejected_count": rejected_count,
        "total_extractions": total_extractions,
        "cost_usd": cost_val,
        "tokens_consumed": f"{tokens_val:,}",
        "papers_data": papers_data,
    }

    # 5. Render via Django Template Loader
    html_content = render_to_string("emails/pipeline_digest.html", context)
    text_content = render_to_string("emails/pipeline_digest.txt", context)

    subject = f"[Research Digest] {ws_name} - Review Complete ({len(accepted_papers)} accepted papers)"

    return {
        "subject": subject,
        "context": context,
        "html_content": html_content,
        "text_content": text_content,
        "stats": {
            "workspace_id": str(workspace.id) if workspace else None,
            "workspace_name": ws_name,
            "pipeline_run_id": str(pipeline_run.id),
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
