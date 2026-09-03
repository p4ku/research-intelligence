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

    workspace, membership, error = check_workspace_access(user, str(pipeline_run.workspace.id), required_roles=['admin', 'manager', 'researcher'])
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


