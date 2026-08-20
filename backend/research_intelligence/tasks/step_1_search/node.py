import logging
from typing import Dict, Any, Optional, Tuple

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class SearchNode(BaseWorkflowNode):
    """
    Step 1: Multi-source search & paper ingestion (ArXiv, OpenAlex, Lens, PubMed).
    """
    name = "search"
    step_type = "search"
    component_name = "workspace_search"
    dependencies = []

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        reprocess = config.get("reprocess_existing", False)
        from research_intelligence.models import Paper
        papers_count = Paper.objects.filter(workspace=workspace).count()
        if papers_count == 0 and not reprocess:
            return True, f"Search completed but 0 papers were found matching criteria for workspace '{workspace.name}'. Halting pipeline."
        return False, None

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_1_search.search import execute_workspace_search
        try:
            async_res = execute_workspace_search.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue search async, executing synchronously: {e}")
            res = execute_workspace_search(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res
