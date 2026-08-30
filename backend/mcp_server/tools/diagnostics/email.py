import json
import logging
from typing import Optional, List
from research_intelligence.models import Workspace, PipelineRun
from research_intelligence.tasks.auxiliary.email_digest import (
    dispatch_pipeline_subscriber_digest,
    send_pipeline_subscriber_digest_task,
)
from research_intelligence.services import check_workspace_access

logger = logging.getLogger(__name__)


def send_pipeline_run_digest_email_logic(
    user,
    workspace_id: str,
    pipeline_run_id: str,
    recipient_override: Optional[List[str]] = None,
    async_dispatch: bool = False
) -> str:
    """
    MCP logic handler to send a systematic literature review digest email to subscribers
    for a completed PipelineRun.
    """
    workspace, membership, error = check_workspace_access(
        user, workspace_id, required_roles=['admin', 'manager', 'researcher']
    )
    if error:
        return error

    # Check PipelineRun existence and completion
    try:
        pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id, workspace=workspace)
    except (PipelineRun.DoesNotExist, ValueError):
        return json.dumps({
            "error": f"PipelineRun '{pipeline_run_id}' not found in workspace '{workspace.name}'."
        })

    if pipeline_run.status != 'completed':
        return json.dumps({
            "error": (
                f"Cannot send digest: PipelineRun status is '{pipeline_run.status}'. "
                f"Digest emails can only be sent for 'completed' runs where parameters are extracted."
            )
        })

    if async_dispatch:
        task = send_pipeline_subscriber_digest_task.delay(
            workspace_id=str(workspace.id),
            pipeline_run_id=str(pipeline_run.id),
            recipient_override=recipient_override
        )
        return json.dumps({
            "status": "queued",
            "message": "Subscriber digest email task has been dispatched to background Celery workers.",
            "celery_task_id": task.id,
            "workspace_id": str(workspace.id),
            "pipeline_run_id": str(pipeline_run.id)
        }, indent=2)

    # Synchronous execution
    result = dispatch_pipeline_subscriber_digest(
        workspace_id=str(workspace.id),
        pipeline_run_id=str(pipeline_run.id),
        recipient_override=recipient_override
    )
    return json.dumps(result, indent=2)
