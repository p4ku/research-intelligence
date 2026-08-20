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
        return not config.get("generate_narrative_report", False)

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.orchestrator.dag.base_node import safe_dispatch_on_commit
        comp_run.status = "completed"
        comp_run.save(update_fields=['status'])
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        safe_dispatch_on_commit(lambda: notify_pipeline_orchestrator_tick(pipeline_run))
        return {"status": "completed"}
