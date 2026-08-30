import json
import logging
from research_intelligence.services import (
    abort_job as service_abort_job,
    delete_pipeline_run as service_delete_pipeline_run,
    recursive_delete_run_storage,
)

logger = logging.getLogger(__name__)


def abort_job_logic(user, component_run_id: str = None, pipeline_run_id: str = None) -> str:
    """Abort a running component job or full PipelineRun (requires Admin or Manager role)."""
    success, res_dict, error = service_abort_job(user, component_run_id=component_run_id, pipeline_run_id=pipeline_run_id)
    if error:
        return error
    return json.dumps(res_dict, indent=2)


def _recursive_delete_run_storage(dir_path: str) -> int:
    """Recursively delete all files and directory structures inside dir_path in default_storage."""
    return recursive_delete_run_storage(dir_path)


def delete_pipeline_run_logic(user, pipeline_run_id: str) -> str:
    """
    Deletes an entire PipelineRun along with all associated database records (Papers, Extractions, ComponentRuns,
    PaperMetrics, NarrativeReports) and cleans up all downloaded PDFs, OCR Markdown, metadata JSONs, raw scrape payloads,
    and storage directories.
    """
    success, res_dict, error = service_delete_pipeline_run(user, pipeline_run_id=pipeline_run_id)
    if error:
        return error
    return json.dumps(res_dict, indent=2)

