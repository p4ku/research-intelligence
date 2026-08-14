import json
import uuid
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Workspace, ResearchAgentProcess
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
from .workspaces import _check_workspace_access


def start_research_agent_logic(
    user,
    workspace_id: str,
    name: str = None,
    limit: int = 50,
    date_range_days: int = None,
    query_prefix: str = None,
    skip_abstract_screening: bool = None,
    notification_email: str = None
) -> str:
    """
    Start a new autonomous ResearchAgentProcess to execute an end-to-end ingestion and intelligence cycle.
    Supports parallel runs, dynamic query modifiers, date windowing, and notification settings.
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
        "notification_email": notification_email or workspace.notification_email
    }

    agent_process = ResearchAgentProcess.objects.create(
        workspace=workspace,
        name=agent_name,
        status='running',
        current_step='initialized',
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
        processes = ResearchAgentProcess.objects.filter(workspace=workspace).select_related('workspace', 'pipeline_run').order_by('-started_at')[:limit]
    else:
        # Accessible workspaces
        from research_intelligence.models import WorkspaceMember
        if getattr(user, 'is_superuser', False):
            processes = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').order_by('-started_at')[:limit]
        else:
            memberships = WorkspaceMember.objects.filter(user=user)
            ws_ids = [m.workspace_id for m in memberships]
            processes = ResearchAgentProcess.objects.filter(workspace_id__in=ws_ids).select_related('workspace', 'pipeline_run').order_by('-started_at')[:limit]

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
            "configuration_override": p.configuration_override,
            "started_at": p.started_at.isoformat(),
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "step_count": len(p.step_history or [])
        })

    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)


def get_research_agent_status_logic(user, process_id: str) -> str:
    """
    Retrieve full execution status, step history, and metrics for a ResearchAgentProcess by UUID.
    Triggers a status evaluation tick if running to update state transitions.
    """
    try:
        p_uuid = uuid.UUID(process_id)
        process = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').get(id=p_uuid)
    except (ValueError, ResearchAgentProcess.DoesNotExist):
        return f"Error: ResearchAgentProcess '{process_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id))
    if error:
        return error

    # Run a tick if process is running to evaluate step completion
    if process.status == 'running':
        tick_agent_process(str(process.id))
        process.refresh_from_db()

    # Gather component runs summary and metrics if pipeline_run exists
    component_runs_summary = []
    paper_metrics = {}
    storage_metrics = {}
    if process.pipeline_run:
        from research_intelligence.models import Paper, Extraction, PaperMetric
        from .pipeline_runs import _get_run_storage_stats

        for cr in process.pipeline_run.component_runs.all():
            component_runs_summary.append({
                "component_run_id": str(cr.id),
                "step_type": cr.step_type,
                "component_name": cr.component_name,
                "status": cr.status,
                "metrics": cr.metrics,
                "started_at": cr.started_at.isoformat(),
                "completed_at": cr.completed_at.isoformat() if cr.completed_at else None
            })

        papers_qs = Paper.objects.filter(pipeline_run=process.pipeline_run)
        paper_metrics = {
            "total_papers_fetched": process.pipeline_run.total_papers_fetched or papers_qs.count(),
            "downloaded_documents_count": papers_qs.filter(original_pdf_path__isnull=False).exclude(original_pdf_path='').count(),
            "ocr_converted_documents_count": papers_qs.filter(converted_md_path__isnull=False).exclude(converted_md_path='').count(),
            "screened_documents_count": PaperMetric.objects.filter(paper__pipeline_run=process.pipeline_run).count(),
            "extractions_count": Extraction.objects.filter(paper__pipeline_run=process.pipeline_run).count(),
            "tokens_in": process.pipeline_run.tokens_in,
            "tokens_out": process.pipeline_run.tokens_out,
            "tokens_consumed": process.pipeline_run.tokens_consumed,
            "usd_cost": float(process.pipeline_run.usd_cost)
        }
        run_storage_dir = f"workspaces/{process.workspace.id}/runs/{process.pipeline_run.id}"
        storage_metrics = _get_run_storage_stats(run_storage_dir)

    details = {
        "process_id": str(process.id),
        "workspace_id": str(process.workspace.id),
        "workspace_name": process.workspace.name,
        "pipeline_run_id": str(process.pipeline_run.id) if process.pipeline_run else None,
        "name": process.name,
        "status": process.status,
        "current_step": process.current_step,
        "ocr_provider": process.workspace.ocr_provider or "None (Skipped)",
        "configuration_override": process.configuration_override,
        "paper_metrics": paper_metrics,
        "storage": storage_metrics,
        "step_history": process.step_history,
        "component_runs": component_runs_summary,
        "error_message": process.error_message,
        "started_at": process.started_at.isoformat(),
        "completed_at": process.completed_at.isoformat() if process.completed_at else None
    }
    return json.dumps(details, indent=2, cls=DjangoJSONEncoder)


def pause_research_agent_logic(user, process_id: str) -> str:
    """
    Pause a running ResearchAgentProcess (requires Admin or Manager role).
    """
    try:
        p_uuid = uuid.UUID(process_id)
        process = ResearchAgentProcess.objects.select_related('workspace').get(id=p_uuid)
    except (ValueError, ResearchAgentProcess.DoesNotExist):
        return f"Error: ResearchAgentProcess '{process_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    if process.status != 'running':
        return f"Error: Agent process is in status '{process.status}' and cannot be paused."

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
        return f"Error: ResearchAgentProcess '{process_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    if process.status != 'paused':
        return f"Error: Agent process is in status '{process.status}' and cannot be resumed."

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
        return f"Error: ResearchAgentProcess '{process_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    # Abort attached pipeline run jobs if running
    if process.pipeline_run:
        from .pipeline_runs import abort_job_logic
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
        return f"Error: ResearchAgentProcess '{process_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    process_name = process.name
    pr_id = str(process.pipeline_run.id) if process.pipeline_run else None

    # Delete PipelineRun if present
    if process.pipeline_run:
        from .pipeline_runs import delete_pipeline_run_logic
        delete_pipeline_run_logic(user, pr_id)

    process.delete()

    return json.dumps({
        "status": "success",
        "message": f"ResearchAgentProcess '{process_name}' (ID: {process_id}) and attached PipelineRun data were successfully deleted.",
        "process_id": process_id,
        "deleted_pipeline_run_id": pr_id
    }, indent=2)
