import json
import uuid
import time
import logging
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Workspace, ResearchAgentProcess
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
from ..workspaces import _check_workspace_access

logger = logging.getLogger(__name__)


def start_research_agent_logic(
    user,
    workspace_id: str,
    name: str = None,
    limit: int = 50,
    date_range_days: int = None,
    query_prefix: str = None,
    skip_abstract_screening: bool = None,
    notification_email: str = None,
    reprocess_existing: bool = False
) -> str:
    """
    Start a new autonomous ResearchAgentProcess to execute an end-to-end ingestion and intelligence cycle.
    Supports parallel runs, dynamic query modifiers, date windowing, and notification settings.
    Set reprocess_existing=True to re-evaluate and screen existing workspace papers even if no new papers were found.
    """
    workspace, membership, error = _check_workspace_access(user, workspace_id, required_roles=['admin', 'manager', 'researcher'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    agent_name = name or f"Autonomous Research Agent - {timezone.now().strftime('%Y-%m-%d %H:%M')}"

    config_override = {
        "limit": limit,
        "date_range_days": date_range_days,
        "query_prefix": query_prefix,
        "skip_abstract_screening": skip_abstract_screening if skip_abstract_screening is not None else workspace.skip_abstract_screening,
        "notification_email": notification_email or workspace.notification_email,
        "reprocess_existing": bool(reprocess_existing)
    }

    agent_process = ResearchAgentProcess.objects.create(
        workspace=workspace,
        name=agent_name,
        status='running',
        current_step='initialized',
        triggered_by=user if getattr(user, 'is_authenticated', False) or getattr(user, 'id', None) else None,
        configuration_override=config_override,
        step_history=[{
            "step": "initialized",
            "event": "created",
            "timestamp": timezone.now().isoformat()
        }]
    )

    # Trigger first tick to launch Step 1 (Search & Ingestion)
    tick_res = tick_agent_process(str(agent_process.id))
    agent_process.refresh_from_db()

    return json.dumps({
        "status": "success",
        "message": f"Autonomous Research Agent '{agent_name}' started successfully for workspace '{workspace.name}'.",
        "process_id": str(agent_process.id),
        "workspace_id": str(workspace.id),
        "pipeline_run_id": str(agent_process.pipeline_run.id) if agent_process.pipeline_run else None,
        "triggered_by": {
            "id": str(agent_process.triggered_by.id) if agent_process.triggered_by else None,
            "username": agent_process.triggered_by.username if agent_process.triggered_by else "system",
            "email": agent_process.triggered_by.email if agent_process.triggered_by else None
        },
        "agent_status": agent_process.status,
        "current_step": agent_process.current_step,
        "ocr_provider": workspace.ocr_provider or "None (Skipped)",
        "configuration_override": agent_process.configuration_override,
        "tick_result": tick_res
    }, indent=2, cls=DjangoJSONEncoder)


def list_research_agents_logic(user, workspace_id: str = None, limit: int = 20) -> str:
    """
    List active or recent ResearchAgentProcesses for a workspace or across accessible workspaces.
    """
    if workspace_id:
        workspace, membership, error = _check_workspace_access(user, workspace_id)
        if error:
            return error
        processes = ResearchAgentProcess.objects.filter(workspace=workspace).select_related('workspace', 'pipeline_run', 'triggered_by').order_by('-started_at')[:limit]
    else:
        # Accessible workspaces
        from research_intelligence.models import WorkspaceMember
        if getattr(user, 'is_superuser', False):
            processes = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run', 'triggered_by').order_by('-started_at')[:limit]
        else:
            memberships = WorkspaceMember.objects.filter(user=user)
            ws_ids = [m.workspace_id for m in memberships]
            processes = ResearchAgentProcess.objects.filter(workspace_id__in=ws_ids).select_related('workspace', 'pipeline_run', 'triggered_by').order_by('-started_at')[:limit]

    results = []
    for p in processes:
        results.append({
            "process_id": str(p.id),
            "workspace_id": str(p.workspace.id),
            "workspace_name": p.workspace.name,
            "pipeline_run_id": str(p.pipeline_run.id) if p.pipeline_run else None,
            "name": p.name,
            "status": p.status,
            "current_step": p.current_step,
            "duration_seconds": p.duration_seconds,
            "execution_time": p.execution_time_display,
            "triggered_by": {
                "id": str(p.triggered_by.id) if p.triggered_by else None,
                "username": p.triggered_by.username if p.triggered_by else "system",
                "email": p.triggered_by.email if p.triggered_by else None
            },
            "configuration_override": p.configuration_override,
            "started_at": p.started_at.isoformat(),
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "step_count": len(p.step_history or [])
        })

    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)


def _render_progress_bar(percent: int, length: int = 15) -> str:
    """Generate a visual ASCII/Unicode progress bar."""
    pct = max(0, min(100, int(percent)))
    filled = int(round((pct / 100.0) * length))
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}] {pct}%"


def _build_stages_breakdown_and_markdown(process, paper_metrics, matrix_preview, component_runs_summary):
    """
    Builds a structured breakdown of the 7 SLR pipeline stages along with a beautifully
    formatted GitHub-flavored markdown summary card ready for direct presentation to users.
    """
    canonical_stages = [
        ("search", "1. Search & Ingestion", "🔍"),
        ("download", "2. Parallel PDF Download", "📥"),
        ("ocr", "3. Layout OCR Parsing", "📄"),
        ("screening", "4. Dual-Stage Screening", "🎯"),
        ("extraction", "5. Dynamic Parameter Extraction", "📊"),
        ("signal_score", "6. Signal Score Ranking", "🧮"),
        ("reporting", "7. Executive Reporting", "📑"),
    ]

    step_order = ["initialized", "search", "download", "ocr", "screening", "extraction", "signal_score", "reporting", "completed"]
    step_weights = {
        "initialized": 5,
        "search": 15,
        "download": 30,
        "ocr": 45,
        "screening": 65,
        "extraction": 85,
        "signal_score": 92,
        "reporting": 98,
        "completed": 100,
        "failed": 100,
        "aborted": 100,
    }

    if process.status == "completed":
        progress_percent = 100
    elif process.status in ["failed", "aborted"]:
        progress_percent = step_weights.get(process.stopped_at_step or process.current_step, 50)
    else:
        progress_percent = step_weights.get(process.current_step, 10)

    progress_bar = _render_progress_bar(progress_percent)

    status_icons = {
        "running": "⏳ RUNNING",
        "completed": "✅ COMPLETED",
        "paused": "⏸️ PAUSED",
        "failed": "❌ FAILED",
        "aborted": "🛑 ABORTED",
        "pending": "🕒 PENDING",
    }
    status_display = status_icons.get(process.status, process.status.upper())

    stage_results = process.stage_results or {}
    stopped_at = process.stopped_at_step
    is_terminal = process.status in ["completed", "failed", "aborted"]

    try:
        current_step_idx = step_order.index(process.current_step)
    except ValueError:
        current_step_idx = 1

    stages_breakdown = []
    for slug, label, icon in canonical_stages:
        stage_idx = step_order.index(slug)
        res_info = stage_results.get(slug, {})
        raw_status = res_info.get("status")

        duration_str = res_info.get("execution_time") or ""

        # Determine status and summary
        if raw_status == "completed":
            s_status = "completed"
            s_badge = f"✅ Done ({duration_str})" if duration_str else "✅ Done"
            s_summary = res_info.get("message") or "Stage completed successfully"
        elif raw_status == "skipped":
            s_status = "skipped"
            s_badge = "⏭️ Skipped"
            s_summary = res_info.get("message") or "Skipped by configuration"
        elif raw_status == "failed":
            s_status = "failed"
            s_badge = "❌ Failed"
            s_summary = res_info.get("message") or "Execution error in stage"
        else:
            # Infer from active agent state
            if slug == "ocr" and not getattr(process.workspace, "ocr_provider", None):
                s_status = "skipped"
                s_badge = "⏭️ Skipped"
                s_summary = "Direct multimodal PDF analysis with Gemini 3.7 Flash"
            elif process.status == "running" and process.current_step == slug:
                s_status = "in_progress"
                s_badge = "⏳ In Progress"
                s_summary = "Actively executing stage in background..."
            elif process.status == "completed":
                s_status = "completed"
                s_badge = "✅ Done"
                s_summary = "Stage completed"
            elif is_terminal and stopped_at and step_order.index(stopped_at) < stage_idx:
                s_status = "halted"
                s_badge = "⏹️ Not Reached"
                s_summary = f"Pipeline halted at stage {stopped_at} ({process.stop_reason or 'preceding condition'})"
            elif is_terminal and (stopped_at == slug or process.current_step == slug):
                s_status = "failed" if process.status == "failed" else "aborted"
                s_badge = "❌ Failed" if process.status == "failed" else "🛑 Aborted"
                s_summary = process.error_message or process.stop_reason or "Halted"
            elif current_step_idx > stage_idx:
                s_status = "completed"
                s_badge = "✅ Done"
                s_summary = "Stage completed"
            elif current_step_idx == stage_idx:
                s_status = "in_progress" if process.status == "running" else "pending"
                s_badge = "⏳ In Progress" if process.status == "running" else "⏸️ Pending"
                s_summary = "Current active step"
            else:
                s_status = "pending"
                s_badge = "⏸️ Pending"
                s_summary = "Waiting for preceding stage"

        # Enrich summary with live metrics if available
        if slug == "search" and paper_metrics.get("total_papers_fetched", 0) > 0:
            if s_status in ["completed", "in_progress"]:
                s_summary = f"{paper_metrics['total_papers_fetched']} papers ingested"
        elif slug == "download" and paper_metrics.get("downloaded_documents_count", 0) > 0:
            if s_status in ["completed", "in_progress"]:
                s_summary = f"{paper_metrics['downloaded_documents_count']} PDFs downloaded"
        elif slug == "screening" and paper_metrics.get("abstract_screening"):
            abs_s = paper_metrics["abstract_screening"]
            ft_s = paper_metrics.get("full_text_screening")
            parts = [f"Abstract: {abs_s['passed']} passed, {abs_s['rejected']} rejected"]
            if ft_s and ft_s.get("screened", 0) > 0:
                parts.append(f"Full-Text: {ft_s['passed']} passed, {ft_s['rejected']} rejected")
            s_summary = " • ".join(parts)
        elif slug == "extraction" and paper_metrics.get("extractions_count", 0) > 0:
            s_summary = f"{paper_metrics['extractions_count']} parameters extracted from accepted papers"
        elif slug == "signal_score" and paper_metrics.get("total_papers_passed_screening", 0) > 0:
            if s_status == "completed":
                s_summary = f"Composite signal scores computed for {paper_metrics['total_papers_passed_screening']} accepted papers"

        stages_breakdown.append({
            "stage_key": slug,
            "stage_name": label,
            "icon": icon,
            "status": s_status,
            "badge": s_badge,
            "duration": duration_str,
            "summary": s_summary
        })

    # Contextual next-action recommendation
    current_label = dict(ResearchAgentProcess.STEP_CHOICES).get(process.current_step, process.current_step)
    if process.status == "running":
        recommendation = f"Pipeline is actively executing '{current_label}' (running for {process.execution_time_display}). Check status again in a few seconds using check_run_status(process_id='{process.id}')."
    elif process.status == "completed":
        recommendation = f"Review completed successfully! Call get_paper_extractions_matrix(process_id='{process.id}') to inspect extracted parameter scorecards, or review top ranked papers."
    elif process.status == "paused":
        recommendation = f"Agent process is currently paused at step '{current_label}'. Call resume_research_agent(process_id='{process.id}') to continue execution."
    elif process.status == "failed":
        recommendation = f"Pipeline execution failed at step '{current_label}'. Error: {process.error_message or process.stop_reason or 'Check step history logs.'}"
    elif process.status == "aborted":
        recommendation = "Pipeline execution was aborted by user."
    else:
        recommendation = f"Agent status is {process.status}."

    # Build Markdown table of stages
    table_lines = [
        "| Step | Stage Name | Status | Summary / Outcome |",
        "| :--- | :--- | :--- | :--- |"
    ]
    for idx, st in enumerate(stages_breakdown, start=1):
        table_lines.append(f"| {idx} | {st['icon']} {st['stage_name']} | {st['badge']} | {st['summary']} |")
    stages_table_md = "\n".join(table_lines)

    # Build Top Papers Preview table if available
    top_papers_md = ""
    if matrix_preview:
        p_lines = [
            "\n### 🏆 Top Accepted Papers & Key Parameters Preview",
            "| # | Paper Title | Screening | Signal Score | Extracted Highlights |",
            "| :- | :--- | :--- | :--- | :--- |"
        ]
        for p_idx, p in enumerate(matrix_preview[:5], start=1):
            title = (p["title"][:60] + "...") if len(p.get("title", "")) > 60 else p.get("title", "Untitled")
            score = str(p.get("signal_score")) if p.get("signal_score") is not None else "-"
            metrics_str = ", ".join([f"{k}: {v}" for k, v in list(p.get("metrics", {}).items())[:3]]) or "Extracted"
            p_lines.append(f"| {p_idx} | **{title}** | `{p.get('screening_status')}` | **`{score}`** | {metrics_str} |")
        top_papers_md = "\n".join(p_lines)

    # Full visual markdown card
    summary_markdown = f"""## 🔬 SLR Pipeline Status — {process.name}
**Status**: {status_display} `{progress_bar}` | **Elapsed**: {process.execution_time_display} | **Workspace**: {process.workspace.name}

### 📋 Stage Execution Timeline
{stages_table_md}

### 📊 Paper Pipeline Metrics
- **Papers Ingested**: {paper_metrics.get('total_papers_fetched', 0)}
- **PDFs Downloaded**: {paper_metrics.get('downloaded_documents_count', 0)}
- **Passed Screening**: {paper_metrics.get('total_papers_passed_screening', 0)}
- **Parameters Extracted**: {paper_metrics.get('extractions_count', 0)}
- **AI Tokens Consumed**: {paper_metrics.get('tokens_consumed', 0):,} (${paper_metrics.get('usd_cost', 0):.4f} USD)
{top_papers_md}

💡 **Next Action**: {recommendation}
"""

    return stages_breakdown, progress_percent, progress_bar, recommendation, summary_markdown


def check_run_status_logic(
    user,
    process_id: str = None,
    pipeline_run_id: str = None,
    run_id: str = None
) -> str:
    """
    [STATE-OF-THE-ART PIPELINE & AGENT STATUS INSPECTOR]
    Non-blocking inspection of an autonomous ResearchAgentProcess or PipelineRun.
    Drives a state evaluation tick if running, and returns the current stage, execution time,
    what has completed vs in-progress vs pending, paper metrics, token usage, and a formatted
    visual Markdown progress card.
    """
    target_id = (process_id or pipeline_run_id or run_id or "").strip()
    if not target_id:
        return json.dumps({
            "status": "error",
            "error": "Either process_id or pipeline_run_id must be provided to check_run_status."
        }, indent=2)

    try:
        target_uuid = uuid.UUID(target_id)
    except ValueError:
        return json.dumps({
            "status": "error",
            "error": f"Invalid UUID format: '{target_id}'"
        }, indent=2)

    # 1. Try finding ResearchAgentProcess first
    process = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run', 'triggered_by').filter(id=target_uuid).first()

    # 2. If not found by process ID, search if target_uuid is a PipelineRun
    if not process:
        from research_intelligence.models import PipelineRun
        pipeline_run = PipelineRun.objects.select_related('workspace', 'triggered_by').filter(id=target_uuid).first()
        if pipeline_run:
            # Check if there is an associated ResearchAgentProcess
            process = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run', 'triggered_by').filter(pipeline_run=pipeline_run).order_by('-started_at').first()
            if not process:
                # Build status directly from PipelineRun
                from mcp_server.tools.pipeline_runs.status import get_pipeline_run_status_logic
                return get_pipeline_run_status_logic(user, str(pipeline_run.id))

    if not process:
        return json.dumps({
            "status": "error",
            "error": f"No ResearchAgentProcess or PipelineRun found matching ID '{target_id}'."
        }, indent=2)

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id))
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    # Run a tick if process is actively running to advance DAG state machine
    if process.status == 'running':
        tick_agent_process(str(process.id))
        process.refresh_from_db()

    # Gather component runs summary and metrics if pipeline_run exists
    component_runs_summary = []
    paper_metrics = {}
    storage_metrics = {}
    matrix_preview = []

    if process.pipeline_run:
        from research_intelligence.models import Paper, Extraction, PaperMetric
        from mcp_server.tools.pipeline_runs.status import _get_run_storage_stats
        from django.db.models import F, Count, Q

        comp_runs_list = list(process.pipeline_run.component_runs.all())
        for cr in comp_runs_list:
            component_runs_summary.append({
                "component_run_id": str(cr.id),
                "step_type": cr.step_type,
                "component_name": cr.component_name,
                "status": cr.status,
                "metrics": cr.metrics,
                "duration_seconds": cr.duration_seconds,
                "execution_time": cr.execution_time_display,
                "started_at": cr.started_at.isoformat(),
                "completed_at": cr.completed_at.isoformat() if cr.completed_at else None
            })

        papers_qs = Paper.objects.filter(pipeline_run=process.pipeline_run)
        paper_stats = papers_qs.aggregate(
            total_fetched=Count('id'),
            downloaded_count=Count('id', filter=Q(original_pdf_path__isnull=False) & ~Q(original_pdf_path='')),
            ocr_count=Count('id', filter=Q(converted_md_path__isnull=False) & ~Q(converted_md_path='')),
            abstract_passed=Count('id', filter=Q(screening_status__in=['abstract_passed', 'full_text_passed'])),
            abstract_screened=Count('id', filter=Q(screening_status__in=['abstract_passed', 'full_text_passed', 'rejected'])),
            full_text_passed=Count('id', filter=Q(screening_status='full_text_passed')),
            rejected_count=Count('id', filter=Q(screening_status='rejected')),
        )

        abstract_run = next((cr for cr in comp_runs_list if cr.step_type == 'screening' and 'abstract' in (cr.component_name or '').lower()), None)
        full_text_run = next((cr for cr in comp_runs_list if cr.step_type == 'screening' and 'full_text' in (cr.component_name or '').lower()), None)

        abstract_metrics = abstract_run.metrics if (abstract_run and abstract_run.metrics) else {}
        full_text_metrics = full_text_run.metrics if (full_text_run and full_text_run.metrics) else {}

        abstract_screened = abstract_metrics.get("total_screened", paper_stats['abstract_screened']) if abstract_run else 0
        abstract_passed = abstract_metrics.get("passed", paper_stats['abstract_passed']) if abstract_run else 0
        abstract_rejected = abstract_metrics.get("rejected", max(0, abstract_screened - abstract_passed)) if abstract_run else 0

        full_text_screened = full_text_metrics.get("total_screened", paper_stats['full_text_passed'] + full_text_metrics.get("rejected", 0)) if full_text_run else 0
        full_text_passed = full_text_metrics.get("passed", paper_stats['full_text_passed']) if full_text_run else 0
        full_text_rejected = full_text_metrics.get("rejected", max(0, full_text_screened - full_text_passed)) if full_text_run else 0

        total_screened_papers = abstract_screened or full_text_screened or PaperMetric.objects.filter(Q(pipeline_run=process.pipeline_run) | Q(paper__pipeline_run=process.pipeline_run)).distinct().count()

        paper_metrics = {
            "total_papers_fetched": process.pipeline_run.total_papers_fetched or paper_stats['total_fetched'],
            "downloaded_documents_count": paper_stats['downloaded_count'],
            "ocr_converted_documents_count": paper_stats['ocr_count'],
            "screened_documents_count": total_screened_papers,
            "abstract_screening": {
                "screened": abstract_screened,
                "passed": abstract_passed,
                "rejected": abstract_rejected
            } if abstract_run else None,
            "full_text_screening": {
                "screened": full_text_screened,
                "passed": full_text_passed,
                "rejected": full_text_rejected
            } if full_text_run else None,
            "total_papers_passed_screening": process.pipeline_run.total_papers_passed_screening or full_text_passed or abstract_passed,
            "extractions_count": Extraction.objects.filter(paper__pipeline_run=process.pipeline_run).count(),
            "tokens_in": process.pipeline_run.tokens_in,
            "tokens_out": process.pipeline_run.tokens_out,
            "tokens_consumed": process.pipeline_run.tokens_consumed,
            "usd_cost": float(process.pipeline_run.usd_cost)
        }
        run_storage_dir = f"workspaces/{process.workspace.id}/runs/{process.pipeline_run.id}"
        storage_metrics = _get_run_storage_stats(run_storage_dir)

        # Build extractions matrix preview for accepted papers
        accepted_papers = papers_qs.filter(screening_status__in=['full_text_passed', 'abstract_passed', 'accepted']).order_by(F('signal_score').desc(nulls_last=True), '-created_at').prefetch_related('extractions', 'extractions__extraction_definition')
        for ap in accepted_papers[:30]:
            ext_map = {}
            for ext in ap.extractions.all():
                dname = ext.extraction_definition.name if ext.extraction_definition else ext.category
                if dname:
                    ext_map[dname] = ext.exit_metric or ext.get_exit_metric()
            matrix_preview.append({
                "paper_id": str(ap.id),
                "title": ap.title,
                "screening_status": ap.screening_status,
                "signal_score": ap.signal_score,
                "metrics": ext_map
            })

    # Generate timeline breakdown, progress bar, and visual summary card
    stages_breakdown, progress_percent, progress_bar, recommendation, summary_markdown = _build_stages_breakdown_and_markdown(
        process=process,
        paper_metrics=paper_metrics,
        matrix_preview=matrix_preview,
        component_runs_summary=component_runs_summary
    )

    current_step_display = dict(ResearchAgentProcess.STEP_CHOICES).get(process.current_step, process.current_step)
    is_finished = process.status in ['completed', 'failed', 'aborted']

    response_data = {
        "status": process.status,
        "is_finished": is_finished,
        "agent_status": process.status,
        "current_step": process.current_step,
        "current_step_display": current_step_display,
        "progress_percent": progress_percent,
        "progress_bar": progress_bar,
        "duration_seconds": process.duration_seconds,
        "execution_time": process.execution_time_display,
        "process_id": str(process.id),
        "workspace_id": str(process.workspace.id),
        "workspace_name": process.workspace.name,
        "pipeline_run_id": str(process.pipeline_run.id) if process.pipeline_run else None,
        "name": process.name,
        "ocr_provider": process.workspace.ocr_provider or "None (Skipped)",
        "summary_markdown": summary_markdown,
        "stages_breakdown": stages_breakdown,
        "next_action_recommendation": recommendation,
        "paper_metrics": paper_metrics,
        "extractions_matrix_preview": matrix_preview,
        "storage": storage_metrics,
        "step_history": process.step_history,
        "component_runs": component_runs_summary,
        "stopped_at_step": process.stopped_at_step,
        "stop_reason": process.stop_reason,
        "stage_results": process.stage_results,
        "error_message": process.error_message,
        "triggered_by": {
            "id": str(process.triggered_by.id) if process.triggered_by else None,
            "username": process.triggered_by.username if process.triggered_by else "system",
            "email": process.triggered_by.email if process.triggered_by else None
        },
        "started_at": process.started_at.isoformat(),
        "completed_at": process.completed_at.isoformat() if process.completed_at else None
    }

    return json.dumps(response_data, indent=2, cls=DjangoJSONEncoder)


def get_research_agent_status_logic(user, process_id: str) -> str:
    """
    Retrieve full execution status, step history, and metrics for a ResearchAgentProcess by UUID.
    Triggers a status evaluation tick if running and returns the enriched state-of-the-art status payload.
    """
    return check_run_status_logic(user, process_id=process_id)


def pause_research_agent_logic(user, process_id: str) -> str:
    """
    Pause a running ResearchAgentProcess (requires Admin or Manager role).
    """
    try:
        p_uuid = uuid.UUID(process_id)
        process = ResearchAgentProcess.objects.select_related('workspace').get(id=p_uuid)
    except (ValueError, ResearchAgentProcess.DoesNotExist):
        return json.dumps({"status": "error", "error": f"ResearchAgentProcess '{process_id}' not found."}, indent=2)

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    if process.status != 'running':
        return json.dumps({"status": "error", "error": f"Agent process is in status '{process.status}' and cannot be paused."}, indent=2)

    process.status = 'paused'
    history = process.step_history or []
    history.append({
        "step": process.current_step,
        "event": "paused",
        "timestamp": timezone.now().isoformat()
    })
    process.step_history = history
    process.save(update_fields=['status', 'step_history', 'updated_at'])

    return json.dumps({
        "status": "success",
        "message": f"ResearchAgentProcess '{process.name}' was successfully paused.",
        "process_id": str(process.id),
        "agent_status": process.status,
        "current_step": process.current_step
    }, indent=2)


def resume_research_agent_logic(user, process_id: str) -> str:
    """
    Resume a paused ResearchAgentProcess and trigger the state engine to continue execution.
    """
    try:
        p_uuid = uuid.UUID(process_id)
        process = ResearchAgentProcess.objects.select_related('workspace').get(id=p_uuid)
    except (ValueError, ResearchAgentProcess.DoesNotExist):
        return json.dumps({"status": "error", "error": f"ResearchAgentProcess '{process_id}' not found."}, indent=2)

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    if process.status != 'paused':
        return json.dumps({"status": "error", "error": f"Agent process is in status '{process.status}' and cannot be resumed."}, indent=2)

    process.status = 'running'
    history = process.step_history or []
    history.append({
        "step": process.current_step,
        "event": "resumed",
        "timestamp": timezone.now().isoformat()
    })
    process.step_history = history
    process.save(update_fields=['status', 'step_history', 'updated_at'])

    # Evaluate tick to continue
    tick_res = tick_agent_process(str(process.id))
    process.refresh_from_db()

    return json.dumps({
        "status": "success",
        "message": f"ResearchAgentProcess '{process.name}' was successfully resumed.",
        "process_id": str(process.id),
        "agent_status": process.status,
        "current_step": process.current_step,
        "tick_result": tick_res
    }, indent=2)


def abort_research_agent_logic(user, process_id: str) -> str:
    """
    Abort a running or paused ResearchAgentProcess and stop any active Celery component jobs.
    """
    try:
        p_uuid = uuid.UUID(process_id)
        process = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').get(id=p_uuid)
    except (ValueError, ResearchAgentProcess.DoesNotExist):
        return json.dumps({"status": "error", "error": f"ResearchAgentProcess '{process_id}' not found."}, indent=2)

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    # Abort attached pipeline run jobs if running
    if process.pipeline_run:
        from mcp_server.tools.pipeline_runs import abort_job_logic
        abort_job_logic(user, pipeline_run_id=str(process.pipeline_run.id))

    process.status = 'aborted'
    process.completed_at = timezone.now()
    history = process.step_history or []
    history.append({
        "step": process.current_step,
        "event": "aborted",
        "timestamp": timezone.now().isoformat()
    })
    process.step_history = history
    process.save(update_fields=['status', 'completed_at', 'step_history', 'updated_at'])

    return json.dumps({
        "status": "success",
        "message": f"ResearchAgentProcess '{process.name}' was successfully aborted.",
        "process_id": str(process.id),
        "agent_status": process.status,
        "current_step": process.current_step
    }, indent=2)


def delete_research_agent_logic(user, process_id: str) -> str:
    """
    Delete a ResearchAgentProcess record and optionally cleanup associated PipelineRun data.
    """
    try:
        p_uuid = uuid.UUID(process_id)
        process = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').get(id=p_uuid)
    except (ValueError, ResearchAgentProcess.DoesNotExist):
        return json.dumps({"status": "error", "error": f"ResearchAgentProcess '{process_id}' not found."}, indent=2)

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    process_name = process.name
    pr_id = str(process.pipeline_run.id) if process.pipeline_run else None

    # Delete PipelineRun if present
    if process.pipeline_run:
        from mcp_server.tools.pipeline_runs import delete_pipeline_run_logic
        delete_pipeline_run_logic(user, pr_id)

    process.delete()

    return json.dumps({
        "status": "success",
        "message": f"ResearchAgentProcess '{process_name}' (ID: {process_id}) and attached PipelineRun data were successfully deleted.",
        "process_id": process_id,
        "deleted_pipeline_run_id": pr_id
    }, indent=2)


def get_workflow_dag_schema_logic(user, workspace_id: str = None) -> str:
    """
    Returns the complete SLR Workflow DAG schema, execution topology,
    dependencies, input contracts, and output contracts for each node.
    """
    workspace = None
    if workspace_id:
        workspace, membership, error = _check_workspace_access(user, workspace_id, required_roles=['admin', 'manager', 'researcher'])
        if error:
            return json.dumps({"status": "error", "error": error}, indent=2)

    from research_intelligence.tasks.orchestrator.dag import build_default_slr_dag
    dag = build_default_slr_dag(workspace=workspace)
    nodes_desc = dag.describe_pipeline()

    return json.dumps({
        "status": "success",
        "dag_name": dag.name,
        "workspace_id": str(workspace.id) if workspace else None,
        "total_nodes": len(nodes_desc),
        "execution_topology": [node["name"] for node in nodes_desc],
        "nodes": nodes_desc,
    }, indent=2, cls=DjangoJSONEncoder)


