import logging
from typing import Dict, Any, Optional

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class DownloadNode(BaseWorkflowNode):
    """
    Step 2: Parallel PDF document download & registry caching.

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
    dependencies = ["search"]

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
