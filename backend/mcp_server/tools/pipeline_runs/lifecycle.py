import json
import uuid
import logging
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import PipelineRun
from research_intelligence.services import (
    check_workspace_access,
    abort_job as service_abort_job,
    delete_pipeline_run as service_delete_pipeline_run,
    recursive_delete_run_storage,
)

logger = logging.getLogger(__name__)


def abort_job_logic(user, component_run_id: str = None, pipeline_run_id: str = None) -> str:
    """Abort a running component job or full PipelineRun (requires Admin or Manager role)."""
    success, res_dict, error = service_abort_job(user, component_run_id=component_run_id, pipeline_run_id=pipeline_run_id)
    if error:
        return error
    return json.dumps(res_dict, indent=2)


def pause_pipeline_run_logic(user, pipeline_run_id: str, reason: str = "Paused by user") -> str:
    """Pause an active PipelineRun (requires Admin or Manager role)."""
    try:
        pr_uuid = uuid.UUID(pipeline_run_id)
        pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
    except (ValueError, PipelineRun.DoesNotExist):
        return json.dumps({"status": "error", "error": f"PipelineRun '{pipeline_run_id}' not found."}, indent=2)

    workspace, membership, error = check_workspace_access(user, str(pipeline_run.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    ok = pipeline_run.pause(reason=reason)
    if not ok:
        return json.dumps({"status": "error", "error": f"PipelineRun is in status '{pipeline_run.status}' and cannot be paused."}, indent=2)

    # Sync any linked agent processes
    for ap in pipeline_run.agent_processes.filter(status='running'):
        ap.status = 'paused'
        history = list(ap.step_history or [])
        history.append({
            "step": ap.current_step,
            "event": "paused",
            "message": reason,
            "timestamp": timezone.now().isoformat()
        })
        ap.step_history = history
        ap.save(update_fields=['status', 'step_history', 'updated_at'])

    return json.dumps({
        "status": "success",
        "message": f"PipelineRun '{pipeline_run.id}' was successfully paused.",
        "pipeline_run_id": str(pipeline_run.id),
        "run_status": pipeline_run.status,
        "current_stage": pipeline_run.current_stage
    }, indent=2)


def resume_pipeline_run_logic(user, pipeline_run_id: str) -> str:
    """Resume a paused PipelineRun and continue autonomous execution."""
    try:
        pr_uuid = uuid.UUID(pipeline_run_id)
        pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
    except (ValueError, PipelineRun.DoesNotExist):
        return json.dumps({"status": "error", "error": f"PipelineRun '{pipeline_run_id}' not found."}, indent=2)

    workspace, membership, error = check_workspace_access(user, str(pipeline_run.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    ok = pipeline_run.resume()
    if not ok:
        return json.dumps({"status": "error", "error": f"PipelineRun is in status '{pipeline_run.status}' and cannot be resumed."}, indent=2)

    # Sync any linked agent processes
    for ap in pipeline_run.agent_processes.filter(status='paused'):
        ap.status = 'running'
        history = list(ap.step_history or [])
        history.append({
            "step": ap.current_step,
            "event": "resumed",
            "timestamp": timezone.now().isoformat()
        })
        ap.step_history = history
        ap.save(update_fields=['status', 'step_history', 'updated_at'])

    return json.dumps({
        "status": "success",
        "message": f"PipelineRun '{pipeline_run.id}' was successfully resumed.",
        "pipeline_run_id": str(pipeline_run.id),
        "run_status": pipeline_run.status,
        "current_stage": pipeline_run.current_stage
    }, indent=2)


def tick_pipeline_run_logic(user, pipeline_run_id: str) -> str:
    """Advance a PipelineRun state machine by executing a single tick."""
    try:
        pr_uuid = uuid.UUID(pipeline_run_id)
        pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
    except (ValueError, PipelineRun.DoesNotExist):
        return json.dumps({"status": "error", "error": f"PipelineRun '{pipeline_run_id}' not found."}, indent=2)

    workspace, membership, error = check_workspace_access(user, str(pipeline_run.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    res = pipeline_run.tick()
    pipeline_run.refresh_from_db()
    return json.dumps({
        "status": "success" if res.get("success", False) else "error",
        "pipeline_run_id": str(pipeline_run.id),
        "run_status": pipeline_run.status,
        "current_stage": pipeline_run.current_stage,
        "tick_result": res
    }, indent=2, cls=DjangoJSONEncoder)


def _recursive_delete_run_storage(dir_path: str) -> int:
    """Recursively delete all files and directory structures inside dir_path in default_storage."""
    return recursive_delete_run_storage(dir_path)


def delete_pipeline_run_logic(user, pipeline_run_id: str) -> str:
    """
    Deletes an entire PipelineRun along with all associated database records (Papers, Extractions, ComponentRuns,
    PaperMetrics, NarrativeReports) and cleans up all downloaded PDFs, OCR Markdown, metadata JSONs, raw scrape payloads,
    and storage directories.
    """
    success, res_dict, error = service_delete_pipeline_run(user, pipeline_run_id=pipeline_run_id)
    if error:
        return error
    return json.dumps(res_dict, indent=2)


def rerun_pipeline_from_step_logic(user, pipeline_run_id: str, step_name: str | None = None) -> str:
    """
    Rerun a PipelineRun from a specific step forward, or automatically resume from the step that failed.
    Resets the target step and all downstream dependent steps in the DAG, sets the pipeline run
    status to 'running', dispatches the step task(s) to Celery workers, and triggers the orchestrator.

    Args:
        user: Requesting User instance (checked for admin/manager role).
        pipeline_run_id: UUID string of the PipelineRun.
        step_name: Optional name of the step to rerun from ('search', 'download', 'ocr',
                   'abstract_screening', 'full_text_screening', 'extraction', 'signal_scoring',
                   'reporting'). If None or 'auto' or 'failed', automatically detects the stage
                   where the pipeline halted or failed.
    """
    try:
        pr_uuid = uuid.UUID(pipeline_run_id)
        pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
    except (ValueError, PipelineRun.DoesNotExist):
        return json.dumps({"status": "error", "error": f"PipelineRun '{pipeline_run_id}' not found."}, indent=2)

    workspace, membership, error = check_workspace_access(user, str(pipeline_run.workspace.id), required_roles=['admin'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    from research_intelligence.tasks.orchestrator.dag import build_default_slr_dag
    from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
    from research_intelligence.models import ComponentRun

    dag = build_default_slr_dag(pipeline_run.workspace)

    # 1. Resolve target node in the DAG
    target_node = None
    if step_name and str(step_name).strip().lower() not in ("auto", "failed", "none", ""):
        cleaned_step = str(step_name).strip().lower()
        if cleaned_step in dag.nodes:
            target_node = cleaned_step
        else:
            step_alias_map = {
                "search": "search",
                "scrape": "search",
                "abstract": "abstract_screening",
                "abstract_screening": "abstract_screening",
                "screening": "abstract_screening",
                "download": "download",
                "pdf": "download",
                "ocr": "ocr",
                "full_text": "full_text_screening",
                "full_text_screening": "full_text_screening",
                "extraction": "extraction",
                "extract": "extraction",
                "signal_score": "signal_score",
                "scoring": "signal_score",
                "reporting": "reporting",
                "report": "reporting",
            }
            target_node = step_alias_map.get(cleaned_step)
            if not target_node:
                for n_name, node in dag.nodes.items():
                    if node.step_type == cleaned_step:
                        target_node = n_name
                        break
        if not target_node:
            valid_steps = list(dag.nodes.keys())
            return json.dumps({
                "status": "error",
                "error": f"Invalid step_name '{step_name}'. Valid steps: {valid_steps}"
            }, indent=2)

    # If step_name was auto/failed/None, automatically detect the halted/failed step
    if not target_node:
        failed_comp = pipeline_run.component_runs.filter(status__in=['failed', 'aborted']).order_by('-started_at').first()
        if failed_comp:
            if failed_comp.component_name in dag.nodes:
                target_node = failed_comp.component_name
            else:
                for n_name, node in dag.nodes.items():
                    if node.step_type == failed_comp.step_type:
                        target_node = n_name
                        break
        elif pipeline_run.stopped_at_stage and pipeline_run.stopped_at_stage in dag.nodes:
            target_node = pipeline_run.stopped_at_stage
        elif pipeline_run.current_stage in dag.nodes:
            target_node = pipeline_run.current_stage
        else:
            target_node = "search"

    # 2. Reset DAG downstream from target node
    dag.rerun_from_node(pipeline_run, target_node)

    # 3. Update PipelineRun state
    pipeline_run.stopped_at_stage = None
    pipeline_run.status = 'running'
    pipeline_run.status_message = f"Rerun triggered from step '{target_node}' forward."
    pipeline_run.completed_at = None
    history = list(pipeline_run.step_history or [])
    history.append({
        "step": target_node,
        "event": "rerun_from_step",
        "message": f"Execution resumed from step '{target_node}' by {getattr(user, 'username', 'user')}.",
        "timestamp": timezone.now().isoformat()
    })
    pipeline_run.step_history = history
    pipeline_run.save(update_fields=['status', 'status_message', 'stopped_at_stage', 'completed_at', 'step_history'])

    # 4. Sync linked agent processes if any
    for ap in pipeline_run.agent_processes.filter(status__in=['failed', 'aborted', 'paused', 'completed']):
        ap.status = 'running'
        ap.current_step = dag.nodes[target_node].step_type
        ap.stopped_at_step = None
        ap.stop_reason = ""
        ap.completed_at = None
        ap_hist = list(ap.step_history or [])
        ap_hist.append({
            "step": target_node,
            "event": "rerun_from_step",
            "timestamp": timezone.now().isoformat()
        })
        ap.step_history = ap_hist
        ap.save(update_fields=['status', 'current_step', 'stopped_at_step', 'stop_reason', 'completed_at', 'step_history', 'updated_at'])

    # 5. Evaluate and dispatch ready node(s) synchronously
    dispatch_res = dag.evaluate_and_dispatch(pipeline_run)

    # 6. Notify asynchronous orchestrator ticker
    notify_pipeline_orchestrator_tick(pipeline_run)

    return json.dumps({
        "status": "success",
        "message": f"PipelineRun '{pipeline_run.id}' successfully resumed from step '{target_node}'.",
        "pipeline_run_id": str(pipeline_run.id),
        "resumed_from_step": target_node,
        "current_stage": pipeline_run.current_stage,
        "run_status": pipeline_run.status,
        "dispatch_result": dispatch_res
    }, indent=2, cls=DjangoJSONEncoder)


def reexecute_component_run_logic(user, component_run_id: str) -> str:
    """
    Re-execute a single ComponentRun task on Celery workers without resetting downstream steps.
    Ideal for retrying an isolated failed task (e.g. download or OCR) without re-running other steps.
    """
    try:
        cr_uuid = uuid.UUID(component_run_id)
        from research_intelligence.models import ComponentRun
        component_run = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').get(id=cr_uuid)
    except (ValueError, ComponentRun.DoesNotExist):
        return json.dumps({"status": "error", "error": f"ComponentRun '{component_run_id}' not found."}, indent=2)

    workspace, membership, error = check_workspace_access(user, str(component_run.pipeline_run.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    from research_intelligence.tasks.orchestrator.dag import build_default_slr_dag
    dag = build_default_slr_dag(component_run.pipeline_run.workspace)

    # Find the matching node
    target_node = None
    if component_run.component_name in dag.nodes:
        target_node = dag.nodes[component_run.component_name]
    else:
        for n_name, node in dag.nodes.items():
            if node.step_type == component_run.step_type:
                target_node = node
                break

    if not target_node:
        return json.dumps({
            "status": "error",
            "error": f"Could not find DAG node definition for component '{component_run.component_name}' (step_type: {component_run.step_type})."
        }, indent=2)

    pr = component_run.pipeline_run
    if pr.status in ['failed', 'aborted', 'paused']:
        pr.status = 'running'
        pr.status_message = f"Re-executing component '{component_run.component_name}'"
        pr.save(update_fields=['status', 'status_message'])

    component_run.status = 'running'
    component_run.error_message = ''
    component_run.completed_at = None
    component_run.started_at = timezone.now()
    component_run.save(update_fields=['status', 'error_message', 'completed_at', 'started_at'])

    # Execute the node directly on Celery
    target_node.execute(pr, component_run)

    return json.dumps({
        "status": "success",
        "message": f"Successfully re-dispatched component run '{component_run.id}' ({component_run.component_name}) on Celery.",
        "component_run_id": str(component_run.id),
        "component_name": component_run.component_name,
        "step_type": component_run.step_type,
        "pipeline_run_id": str(pr.id),
        "component_status": component_run.status
    }, indent=2)



