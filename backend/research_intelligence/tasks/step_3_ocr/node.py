import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class OCRNode(BaseWorkflowNode):
    """
    Step 3: Document Layout OCR Conversion (Optional / Skippable if ocr_provider is None).

    Inputs:
        - Downloaded PDF binaries in storage.
        - Workspace.ocr_provider ('pypdf', 'mistral', 'gemini', or None).
    Outputs:
        - Converted Markdown text saved to storage:
          'workspaces/{ws_id}/runs/{run_id}/documents/{sha256}/extracted_text.md'.
        - Updated Paper.ocr_text_path and Paper.ocr_provider.
        - Skipped if workspace.ocr_provider is None (PDF passed directly to multimodal Gemini).
        - ComponentRun.metrics: total_converted, skipped, failed.
    """
    name = "ocr"
    step_type = "ocr"
    component_name = "layout_ocr"
    description = "Converts PDF document layout to structured Markdown text (skipped if ocr_provider=None)."
    dependencies = ["download"]

    input_contract = {
        "pdf_files": "Storage files (workspaces/{ws_id}/runs/{run_id}/documents/{sha256}/original.pdf)",
        "ocr_provider": "Optional[str] (workspace.ocr_provider: 'pypdf', 'mistral', 'gemini', or None)",
    }

    output_contract = {
        "storage_artifacts": "workspaces/{ws_id}/runs/{run_id}/documents/{sha256}/extracted_text.md",
        "updated_models": {
            "Paper.ocr_text_path": "Path to extracted markdown text",
            "Paper.ocr_provider": "OCR engine identifier",
        },
        "component_run_metrics": {
            "total_converted": "int",
            "skipped": "int",
            "failed": "int",
        },
    }

    def is_skippable(self, pipeline_run, workspace, config: Dict[str, Any]) -> bool:
        provider = config.get("ocr_provider", workspace.ocr_provider)
        return not provider or provider in ("None", "none", "")

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.orchestrator.dag.base_node import safe_dispatch_on_commit
        from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
        def _dispatch():
            try:
                async_res = execute_ocr_job.delay(str(comp_run.id), limit=limit)
                comp_run.celery_task_id = async_res.id
                comp_run.save(update_fields=['celery_task_id'])
            except Exception as e:
                logger.warning(f"Failed to queue OCR async, executing synchronously: {e}")
                execute_ocr_job(str(comp_run.id), limit=limit)

        safe_dispatch_on_commit(_dispatch)
        return {"status": "dispatched"}
