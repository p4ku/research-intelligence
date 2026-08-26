import logging
from typing import Dict, Any, Optional, List
from django.utils import timezone
from .base import BaseSubscriptionReporter
from research_intelligence.models import ComponentRun

logger = logging.getLogger(__name__)


class PipelineErrorsReporter(BaseSubscriptionReporter):
    """
    Generates high-priority incident alerts and troubleshooting summaries
    when pipeline runs or component stages fail.
    """
    subscription_type = "pipeline_errors"
    display_name = "Pipeline Errors"
    description = "Incident alerts and error logs dispatched upon execution failure or step exceptions."
    template_name = "emails/pipeline_errors"

    def build_payload(
        self,
        workspace: Any,
        pipeline_run: Optional[Any] = None,
        agent_process: Optional[Any] = None,
        error_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        ws_name = workspace.name if workspace else "Research Workspace"
        run_date_str = timezone.now().strftime("%B %d, %Y %H:%M UTC")

        error_context = error_context or {}
        main_error = (
            error_context.get("error")
            or error_context.get("error_message")
            or (agent_process.error_message if agent_process else None)
            or (pipeline_run.error_message if (pipeline_run and hasattr(pipeline_run, 'error_message')) else None)
            or "An unexpected error interrupted pipeline execution."
        )

        failed_stage = (
            error_context.get("stage")
            or (agent_process.current_step if agent_process else None)
            or (pipeline_run.current_stage if pipeline_run else "Unknown Stage")
        )

        # Collect failed component runs
        failed_components = []
        if pipeline_run:
            failed_runs = ComponentRun.objects.filter(
                pipeline_run=pipeline_run,
                status='failed'
            ).order_by('-started_at')
            for cr in failed_runs:
                failed_components.append({
                    "step_type": cr.get_step_type_display() if hasattr(cr, 'get_step_type_display') else cr.step_type,
                    "error_log": cr.error_message or "No detailed stack trace captured.",
                    "duration": cr.execution_time_display,
                    "started_at": cr.started_at.strftime("%H:%M:%S UTC") if cr.started_at else "-",
                })


        subject = f"🚨 [Pipeline Alert] Execution Failed in {ws_name} (Stage: {failed_stage.upper()})"

        stats = {
            "failed_stage": failed_stage,
            "failed_components_count": len(failed_components),
            "run_date": run_date_str,
        }

        context = {
            "workspace_name": ws_name,
            "workspace_id": str(workspace.id) if workspace else "",
            "pipeline_run_id": str(pipeline_run.id) if pipeline_run else "",
            "process_id": str(agent_process.id) if agent_process else "",
            "failed_stage": failed_stage,
            "main_error": main_error,
            "failed_components": failed_components,
            "run_date": run_date_str,
            "subject": subject,
        }

        return {
            "subject": subject,
            "context": context,
            "stats": stats,
            "template_name": self.template_name,
        }
