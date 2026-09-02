import logging
from typing import Dict, Any, Optional, List
from django.utils import timezone
from .base import BaseSubscriptionReporter
from research_intelligence.models import ComponentRun, Paper

logger = logging.getLogger(__name__)


class PipelineStatusReporter(BaseSubscriptionReporter):
    """
    Generates execution milestone digests and stage progression summaries
    for running or completed pipeline workflows.
    """
    subscription_type = "pipeline_status"
    display_name = "Pipeline Status"
    description = "Stage progression timeline, document throughput, and resource consumption digest."
    template_name = "emails/pipeline_status"

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

        status_str = (agent_process.status if agent_process else (pipeline_run.status if pipeline_run else "completed")).upper()
        duration_str = pipeline_run.execution_time_display if pipeline_run else "N/A"

        # Stage breakdown
        stages = []
        if pipeline_run:
            components = ComponentRun.objects.filter(pipeline_run=pipeline_run).order_by('started_at')
            for c in components:
                stages.append({
                    "step_type": c.get_step_type_display() if hasattr(c, 'get_step_type_display') else c.step_type,
                    "status": c.status.upper(),
                    "duration": c.execution_time_display,
                    "metrics": c.metrics or {},
                })


        total_papers = pipeline_run.get_papers().count() if pipeline_run else 0
        passed_papers = pipeline_run.get_papers().filter(
            screening_status__in=['full_text_passed', 'accepted', 'abstract_passed']
        ).count() if pipeline_run else 0

        cost_val = float(pipeline_run.usd_cost or 0.0) if pipeline_run else 0.0
        tokens_val = int(pipeline_run.tokens_consumed or 0) if pipeline_run else 0

        subject = f"⚡ [Pipeline Status: {status_str}] {ws_name} ({passed_papers}/{total_papers} Papers Qualified)"

        stats = {
            "status": status_str,
            "total_papers": total_papers,
            "passed_papers": passed_papers,
            "stages_count": len(stages),
            "cost_formatted": f"${cost_val:.4f}",
            "tokens_formatted": f"{tokens_val:,}",
            "duration": duration_str,
            "run_date": run_date_str,
        }

        context = {
            "workspace_name": ws_name,
            "workspace_id": str(workspace.id) if workspace else "",
            "pipeline_run_id": str(pipeline_run.id) if pipeline_run else "",
            "process_id": str(agent_process.id) if agent_process else "",
            "status": status_str,
            "duration": duration_str,
            "stages": stages,
            "stats": stats,
            "run_date": run_date_str,
            "subject": subject,
        }

        return {
            "subject": subject,
            "context": context,
            "stats": stats,
            "template_name": self.template_name,
        }
