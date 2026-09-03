import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class OCRNode(BaseWorkflowNode):
    """
    Document Layout OCR Conversion (Optional / Skippable if ocr_provider is None).

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

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        if status == 'skipped':
            return "OCR: Skipped (Direct Multimodal PDF mode active)."
        if status == 'completed' and comp_run:
            metrics = comp_run.metrics or {}
            conv = metrics.get('converted', metrics.get('total_converted', 0))
            return f"OCR: {conv} documents converted to Markdown."
        return super().generate_stage_summary(comp_run, status=status)

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        params = super().get_input_params(pipeline_run, workspace, config, limit=limit)
        params["ocr_provider"] = config.get("ocr_provider", workspace.ocr_provider)
        return params

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
        return self.dispatch_celery_task(execute_ocr_job, comp_run, limit=limit)
