import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class ReportingNode(BaseWorkflowNode):
    """
    Step 8 / Auxiliary: Executive Narrative & Notification Dispatch.
    """
    name = "reporting"
    step_type = "reporting"
    component_name = "executive_narrative"
    dependencies = ["signal_score"]

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        return not config.get("generate_narrative_report", False)

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        comp_run.status = "completed"
        comp_run.save(update_fields=['status'])
        return {"status": "completed"}
