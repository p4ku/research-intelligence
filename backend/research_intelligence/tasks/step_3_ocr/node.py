import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class OCRNode(BaseWorkflowNode):
    """
    Step 3: Document Layout OCR Conversion (Optional / Skippable if ocr_provider is None).
    """
    name = "ocr"
    step_type = "ocr"
    component_name = "layout_ocr"
    dependencies = ["download"]

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        provider = config.get("ocr_provider", workspace.ocr_provider)
        return not provider or provider in ("None", "none", "")

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
        try:
            async_res = execute_ocr_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue OCR async, executing synchronously: {e}")
            res = execute_ocr_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            return res
