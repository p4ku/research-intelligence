import os
import json
import uuid
import shutil
import logging
from django.utils import timezone
from django.core.files.storage import default_storage

from research_intelligence.models import (
    PipelineRun,
    ComponentRun,
    Paper,
    Extraction,
    PaperMetric,
    NarrativeReport,
)
from research_intelligence.services import (
    check_workspace_access,
    recursive_delete_run_storage as _recursive_delete_run_storage,
    abort_job as service_abort_job,
    delete_pipeline_run as service_delete_pipeline_run,
)

logger = logging.getLogger(__name__)


def abort_job_logic(user, component_run_id: str = None, pipeline_run_id: str = None) -> str:
    """Abort a running component job or full PipelineRun (requires Admin or Manager role)."""
    if component_run_id:
        try:
            cr_uuid = uuid.UUID(component_run_id)
            cr = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').get(id=cr_uuid)
        except (ValueError, ComponentRun.DoesNotExist):
            return f"Error: ComponentRun '{component_run_id}' not found."

        workspace, membership, error = check_workspace_access(user, str(cr.pipeline_run.workspace.id), required_roles=['admin', 'manager'])
        if error:
            return error

        # Revoke Celery Task if task ID exists
        if cr.celery_task_id:
            try:
                from django_project.celery import app as celery_app
                celery_app.control.revoke(cr.celery_task_id, terminate=True)
            except Exception:
                pass

        if cr.status in ['completed', 'failed', 'aborted']:
            return f"Error: ComponentRun '{component_run_id}' is in status '{cr.status}' and cannot be aborted."

        cr.status = 'aborted'
        cr.completed_at = timezone.now()
        cr.save(update_fields=['status', 'completed_at'])

        # Check if parent PipelineRun should be updated
        pipeline_run = cr.pipeline_run
        remaining_active = ComponentRun.objects.filter(pipeline_run=pipeline_run, status__in=['pending', 'running']).exists()
        if not remaining_active:
            pipeline_run.status = 'aborted'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])

        return json.dumps({
            "status": "success",
            "success": True,
            "message": f"ComponentRun '{component_run_id}' has been aborted.",
            "component_run_id": str(cr.id),
            "pipeline_run_id": str(pipeline_run.id)
        }, indent=2)

    elif pipeline_run_id:
        try:
            pr_uuid = uuid.UUID(pipeline_run_id)
            pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
        except (ValueError, PipelineRun.DoesNotExist):
            return f"Error: PipelineRun '{pipeline_run_id}' not found."

        workspace, membership, error = check_workspace_access(user, str(pipeline_run.workspace.id), required_roles=['admin', 'manager'])
        if error:
            return error

        if pipeline_run.status in ['completed', 'failed', 'aborted']:
            return f"Error: PipelineRun '{pipeline_run_id}' is already in status '{pipeline_run.status}'."

        # Mark all pending/running component runs as aborted
        active_comp_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, status__in=['pending', 'running'])
        count = active_comp_runs.count()
        active_comp_runs.update(status='aborted', completed_at=timezone.now())

        pipeline_run.status = 'aborted'
        pipeline_run.completed_at = timezone.now()
        pipeline_run.save(update_fields=['status', 'completed_at'])

        return json.dumps({
            "status": "success",
            "success": True,
            "message": f"PipelineRun '{pipeline_run_id}' and {count} active component run(s) have been aborted.",
            "pipeline_run_id": str(pipeline_run.id)
        }, indent=2)

    return "Error: Must specify either component_run_id or pipeline_run_id to abort."


def _recursive_delete_run_storage(dir_path: str) -> int:
    """Recursively delete all files and directory structures inside dir_path in default_storage."""
    deleted_count = 0
    clean_dir = dir_path.strip('/')
    if not clean_dir or clean_dir in ('', 'workspaces'):
        return 0

    # 1. S3 / MinIO direct bucket prefix purge if available
    if hasattr(default_storage, 'bucket') and default_storage.bucket is not None:
        try:
            prefix = clean_dir if clean_dir.endswith('/') else f"{clean_dir}/"
            objects_to_delete = default_storage.bucket.objects.filter(Prefix=prefix)
            for obj in objects_to_delete:
                obj.delete()
                deleted_count += 1
            try:
                default_storage.bucket.objects.filter(Prefix=clean_dir).delete()
            except Exception:
                pass
            return deleted_count
        except Exception:
            pass

    # 2. Standard recursive listdir deletion
    try:
        dirs, files = default_storage.listdir(clean_dir)
        for f in files:
            full_f_path = f"{clean_dir}/{f}"
            try:
                if default_storage.exists(full_f_path):
                    default_storage.delete(full_f_path)
                    deleted_count += 1
            except Exception:
                pass
        for d in dirs:
            full_d_path = f"{clean_dir}/{d}"
            deleted_count += _recursive_delete_run_storage(full_d_path)

        # 3. On local filesystem, remove the empty directory or directory tree
        local_path = None
        if hasattr(default_storage, 'path'):
            try:
                local_path = default_storage.path(clean_dir)
            except Exception:
                pass
        if not local_path and hasattr(default_storage, 'location'):
            try:
                local_path = os.path.join(default_storage.location, clean_dir)
            except Exception:
                pass

        if local_path and os.path.exists(local_path):
            try:
                if os.path.isdir(local_path):
                    shutil.rmtree(local_path, ignore_errors=True)
                elif os.path.isfile(local_path):
                    os.remove(local_path)
            except Exception:
                pass
    except Exception:
        pass
    return deleted_count


def delete_pipeline_run_logic(user, pipeline_run_id: str) -> str:
    """
    Deletes an entire PipelineRun along with all associated database records (Papers, Extractions, ComponentRuns,
    PaperMetrics, NarrativeReports) and cleans up all downloaded PDFs, OCR Markdown, metadata JSONs, raw scrape payloads,
    and storage directories.
    """
    try:
        pr_uuid = uuid.UUID(pipeline_run_id)
        pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
    except (ValueError, PipelineRun.DoesNotExist):
        return f"Error: PipelineRun '{pipeline_run_id}' not found."

    workspace = pipeline_run.workspace
    workspace, membership, error = check_workspace_access(user, str(workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    from django.db.models import Q
    papers_qs = Paper.objects.filter(pipeline_run=pipeline_run)
    papers_count = papers_qs.count()
    component_runs_count = pipeline_run.component_runs.count()
    extractions_count = Extraction.objects.filter(paper__pipeline_run=pipeline_run).count()
    metrics_count = PaperMetric.objects.filter(Q(pipeline_run=pipeline_run) | Q(paper__pipeline_run=pipeline_run)).distinct().count()
    reports_count = NarrativeReport.objects.filter(pipeline_run=pipeline_run).count()

    # Clean up physical storage files and folder recursively: workspaces/{workspace_id}/runs/{pipeline_run_id}
    run_storage_dir = f"workspaces/{workspace.id}/runs/{pipeline_run.id}"
    deleted_files_count = _recursive_delete_run_storage(run_storage_dir)

    # Extra safety check: only delete paths strictly inside this run's directory
    for paper in papers_qs.iterator():
        for path in (paper.original_pdf_path, paper.converted_md_path):
            if path and path.startswith(run_storage_dir):
                try:
                    if default_storage.exists(path):
                        default_storage.delete(path)
                        deleted_files_count += 1
                except Exception as e:
                    logger.warning(f"Failed deleting storage file '{path}': {e}")

    pr_id_str = str(pipeline_run.id)
    ws_id_str = str(workspace.id)

    # Perform DB deletion (CASCADE deletes Papers, Extractions, ComponentRuns, PaperMetrics, NarrativeReports)
    pipeline_run.delete()

    return json.dumps({
        "status": "success",
        "message": f"PipelineRun '{pr_id_str}' and all associated Papers, Extractions, ComponentRuns, and storage files were successfully deleted.",
        "pipeline_run_id": pr_id_str,
        "workspace_id": ws_id_str,
        "deleted_counts": {
            "papers": papers_count,
            "extractions": extractions_count,
            "paper_metrics": metrics_count,
            "component_runs": component_runs_count,
            "narrative_reports": reports_count,
            "storage_files": deleted_files_count
        }
    }, indent=2)
