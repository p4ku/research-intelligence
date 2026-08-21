import json
import uuid
import time
import logging
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Workspace, ResearchAgentProcess
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
from .workspaces import _check_workspace_access

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

        comp_runs = process.pipeline_run.component_runs.all()
        for cr in comp_runs:
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
        abstract_run = comp_runs.filter(step_type='screening', component_name__icontains='abstract').first()
        full_text_run = comp_runs.filter(step_type='screening', component_name__icontains='full_text').first()

        abstract_metrics = abstract_run.metrics if (abstract_run and abstract_run.metrics) else {}
        full_text_metrics = full_text_run.metrics if (full_text_run and full_text_run.metrics) else {}

        abstract_screened = abstract_metrics.get("total_screened", papers_qs.filter(screening_status__in=['abstract_passed', 'full_text_passed', 'rejected']).count()) if abstract_run else 0
        abstract_passed = abstract_metrics.get("passed", papers_qs.filter(screening_status__in=['abstract_passed', 'full_text_passed']).count()) if abstract_run else 0
        abstract_rejected = abstract_metrics.get("rejected", max(0, abstract_screened - abstract_passed)) if abstract_run else 0

        full_text_screened = full_text_metrics.get("total_screened", papers_qs.filter(screening_status='full_text_passed').count() + full_text_metrics.get("rejected", 0)) if full_text_run else 0
        full_text_passed = full_text_metrics.get("passed", papers_qs.filter(screening_status='full_text_passed').count()) if full_text_run else 0
        full_text_rejected = full_text_metrics.get("rejected", max(0, full_text_screened - full_text_passed)) if full_text_run else 0

        total_screened_papers = abstract_screened or full_text_screened or PaperMetric.objects.filter(paper__pipeline_run=process.pipeline_run).count()

        paper_metrics = {
            "total_papers_fetched": process.pipeline_run.total_papers_fetched or papers_qs.count(),
            "downloaded_documents_count": papers_qs.filter(original_pdf_path__isnull=False).exclude(original_pdf_path='').count(),
            "ocr_converted_documents_count": papers_qs.filter(converted_md_path__isnull=False).exclude(converted_md_path='').count(),
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
        matrix_preview = []
        accepted_papers = papers_qs.filter(screening_status__in=['full_text_passed', 'abstract_passed']).prefetch_related('extractions', 'extractions__extraction_definition')
        for ap in accepted_papers[:30]:
            ext_map = {}
            for ext in ap.extractions.all():
                dname = ext.extraction_definition.name if ext.extraction_definition else ext.category
                if dname:
                    ext_map[dname] = ext.exit_metric or ext.get_exit_metric()
            if ext_map:
                matrix_preview.append({
                    "paper_id": str(ap.id),
                    "title": ap.title,
                    "screening_status": ap.screening_status,
                    "metrics": ext_map
                })

    details = {
        "process_id": str(process.id),
        "workspace_id": str(process.workspace.id),
        "workspace_name": process.workspace.name,
        "pipeline_run_id": str(process.pipeline_run.id) if process.pipeline_run else None,
        "name": process.name,
        "status": process.status,
        "current_step": process.current_step,
        "duration_seconds": process.duration_seconds,
        "execution_time": process.execution_time_display,
        "triggered_by": {
            "id": str(process.triggered_by.id) if process.triggered_by else None,
            "username": process.triggered_by.username if process.triggered_by else "system",
            "email": process.triggered_by.email if process.triggered_by else None
        },
        "ocr_provider": process.workspace.ocr_provider or "None (Skipped)",
        "configuration_override": process.configuration_override,
        "paper_metrics": paper_metrics,
        "extractions_matrix_preview": matrix_preview if process.pipeline_run else [],
        "storage": storage_metrics,
        "step_history": process.step_history,
        "component_runs": component_runs_summary,
        "stopped_at_step": process.stopped_at_step,
        "stop_reason": process.stop_reason,
        "stage_results": process.stage_results,
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
        return json.dumps({"status": "error", "error": f"ResearchAgentProcess '{process_id}' not found."}, indent=2)

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

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


def wait_for_research_agent_logic(
    user,
    process_id: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 3
) -> str:
    """
    Block and wait synchronously for a ResearchAgentProcess to finish executing (reach 'completed', 'failed', or 'aborted').
    Periodically ticks the state engine to drive background steps forward.
    If timeout_seconds is reached before completion, returns current progress status.
    """
    import time
    from django.db import close_old_connections

    try:
        p_uuid = uuid.UUID(process_id)
        process = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').get(id=p_uuid)
    except (ValueError, ResearchAgentProcess.DoesNotExist):
        return json.dumps({"status": "error", "error": f"ResearchAgentProcess '{process_id}' not found."}, indent=2)

    workspace, membership, error = _check_workspace_access(user, str(process.workspace.id))
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    t0 = time.time()
    max_timeout = max(5, min(int(timeout_seconds), 600))
    interval = max(1, min(int(poll_interval_seconds), 30))

    while True:
        close_old_connections()
        process.refresh_from_db()

        # If already in a terminal state, return full status
        if process.status in ['completed', 'failed', 'aborted']:
            break

        # Drive the state engine forward
        if process.status == 'running':
            tick_agent_process(str(process.id))
            process.refresh_from_db()
            if process.status in ['completed', 'failed', 'aborted']:
                break

        elapsed = time.time() - t0
        if elapsed >= max_timeout:
            # Return current progress with timeout notice
            status_json_str = get_research_agent_status_logic(user, process_id)
            try:
                status_dict = json.loads(status_json_str)
            except Exception:
                status_dict = {"raw_status": status_json_str}

            step_label = dict(ResearchAgentProcess.STEP_CHOICES).get(process.current_step, process.current_step)
            return json.dumps({
                "status": "timeout",
                "message": f"Timeout of {max_timeout}s elapsed. Research agent '{process.name}' is currently at '{step_label}' (running for {process.execution_time_display}). Call wait_for_research_agent again to continue waiting or check status using get_research_agent_status.",
                "agent_status": process.status,
                "current_step": process.current_step,
                "current_step_display": step_label,
                "stopped_at_step": process.stopped_at_step,
                "stop_reason": process.stop_reason,
                "stage_results": process.stage_results,
                "total_duration_seconds": process.duration_seconds,
                "total_duration_display": process.execution_time_display,
                "wait_elapsed_seconds": round(elapsed, 1),
                "details": status_dict
            }, indent=2, cls=DjangoJSONEncoder)

        time.sleep(interval)

    # Return full final status report
    final_status_json_str = get_research_agent_status_logic(user, process_id)
    try:
        final_status_dict = json.loads(final_status_json_str)
    except Exception:
        final_status_dict = {"raw_status": final_status_json_str}

    final_step_label = dict(ResearchAgentProcess.STEP_CHOICES).get(process.current_step, process.current_step)
    return json.dumps({
        "status": "finished",
        "message": f"Research agent '{process.name}' finished with status: {process.status.upper()} in {process.execution_time_display}.",
        "process_id": str(process.id),
        "agent_status": process.status,
        "current_step": process.current_step,
        "current_step_display": final_step_label,
        "stopped_at_step": process.stopped_at_step,
        "stop_reason": process.stop_reason,
        "stage_results": process.stage_results,
        "total_duration_seconds": process.duration_seconds,
        "total_duration_display": process.execution_time_display,
        "wait_elapsed_seconds": round(time.time() - t0, 1),
        "details": final_status_dict
    }, indent=2, cls=DjangoJSONEncoder)


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


