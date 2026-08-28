import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class ReportingNode(BaseWorkflowNode):
    """
    Step 8 / Auxiliary: Executive Narrative & Notification Dispatch.

    Inputs:
        - All accepted Paper objects, Extraction data, and calculated signal scores.
        - Workspace subscribers & notification settings.
    Outputs:
        - NarrativeReport DB record and markdown file in storage.
        - Outbound transactional email sent via Mailgun.
        - ComponentRun.metrics: report_generated, emails_sent.
    """
    name = "reporting"
    step_type = "reporting"
    component_name = "executive_narrative"
    description = "Generates executive narrative reports and dispatches email digests via Mailgun."
    dependencies = ["signal_score"]

    input_contract = {
        "accepted_papers": "QuerySet[Paper] (screened & scored papers)",
        "subscribers": "QuerySet[WorkspaceSubscriber] (active workspace subscribers)",
        "generate_narrative_report": "bool (whether to generate deep markdown executive briefing)",
    }

    output_contract = {
        "storage_artifacts": "workspaces/{ws_id}/runs/{run_id}/narrative_report.md",
        "narrative_report": "NarrativeReport (DB model with executive summary and key findings)",
        "component_run_metrics": {
            "report_generated": "bool",
            "emails_sent": "int",
        },
    }

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        # Generates executive narrative report by default; only skippable if explicitly set to False
        return config.get("generate_narrative_report") is False

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        if status == 'completed':
            return "Reporting: Narrative SLR executive report compiled."
        return super().generate_stage_summary(comp_run, status=status)

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from django.utils import timezone
        from research_intelligence.tasks.orchestrator.dag.base_node import safe_dispatch_on_commit
        from research_intelligence.tasks.step_7_reporting.narrative import generate_executive_narrative_report
        
        metrics = dict(comp_run.metrics or {})
        comp_run.started_at = comp_run.started_at or timezone.now()
        try:
            res = generate_executive_narrative_report(pipeline_run)
            metrics["report_generated"] = res.get("success", True)
            metrics["report_id"] = res.get("report_id")
            metrics["storage_path"] = res.get("storage_path")
            comp_run.metrics = metrics
            comp_run.output_data = res
            comp_run.status = "completed"
            comp_run.completed_at = timezone.now()
        except Exception as e:
            logger.warning(f"Error generating narrative report for run {pipeline_run.id}: {e}")
            metrics["report_generated"] = False
            comp_run.metrics = metrics
            comp_run.status = "completed"
            comp_run.completed_at = timezone.now()
            comp_run.error_message = str(e)

        comp_run.save(update_fields=['metrics', 'output_data', 'status', 'started_at', 'completed_at', 'error_message'])
        
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        safe_dispatch_on_commit(lambda: notify_pipeline_orchestrator_tick(pipeline_run))
        return {"status": comp_run.status}
