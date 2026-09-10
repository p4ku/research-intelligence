import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class DownloadNode(BaseWorkflowNode):
    """
    PDF Download: Parallel PDF document download & registry caching.

    Inputs:
        - Ingested Paper records with valid `pdf_url` fields.
        - Global SHA-256 DocumentRegistry cache.
    Outputs:
        - Downloaded binary PDF saved to workspace storage:
          'workspaces/{ws_id}/runs/{run_id}/documents/{sha256}/original.pdf'.
        - Updated Paper.pdf_file and Paper.document_hash fields.
        - ComponentRun.metrics: total, downloaded, from_cache, failed.
    """
    name = "download"
    step_type = "download"
    component_name = "document_download"
    description = "Downloads original full-text PDF documents in parallel with global SHA-256 deduplication."
    dependencies = ["abstract_screening"]

    input_contract = {
        "papers": "QuerySet[Paper] (papers attached to pipeline_run with pdf_url)",
        "document_registry": "DocumentRegistry (global content-addressable storage cache)",
    }

    output_contract = {
        "storage_artifacts": "workspaces/{ws_id}/runs/{run_id}/documents/{sha256}/original.pdf",
        "updated_models": {
            "Paper.pdf_file": "FileField path to downloaded PDF",
            "Paper.document_hash": "SHA-256 hexadecimal string",
        },
        "component_run_metrics": {
            "total": "int",
            "downloaded": "int",
            "from_cache": "int",
            "failed": "int",
        },
    }

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        if status == 'completed' and comp_run:
            metrics = comp_run.metrics or {}
            down = metrics.get('downloaded', 0)
            from_cache = metrics.get('from_cache', metrics.get('cached', 0))
            failed = metrics.get('failed', 0)
            return f"Download: {down} downloaded, {from_cache} cached, {failed} failed."
        return super().generate_stage_summary(comp_run, status=status)

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        params = super().get_input_params(pipeline_run, workspace, config, limit=limit)
        skip_abs = bool(config.get("skip_abstract_screening", getattr(workspace, 'skip_abstract_screening', False)))
        params["target_mode"] = "all_ingested" if skip_abs else "abstract_passed"
        return params

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
        return self.dispatch_celery_task(execute_pdf_download_job, comp_run, limit=limit)
