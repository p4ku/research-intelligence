import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class DownloadNode(BaseWorkflowNode):
    """
    Step 2: Parallel PDF document download & registry caching.
    """
    name = "download"
    step_type = "download"
    component_name = "document_download"
    dependencies = ["search"]

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
        try:
            async_res = execute_pdf_download_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue download async, executing synchronously: {e}")
            res = execute_pdf_download_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res
