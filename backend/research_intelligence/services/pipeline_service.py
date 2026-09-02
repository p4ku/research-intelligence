import os
import uuid
import shutil
import logging
from typing import Optional, Tuple, Dict, Any, Union
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
from .workspace_service import check_workspace_access

logger = logging.getLogger(__name__)


def recursive_delete_run_storage(dir_path: str) -> int:
    """Recursively deletes all files and subdirectories inside dir_path in Django default_storage."""
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
            deleted_count += recursive_delete_run_storage(full_d_path)

        # 3. On local filesystem, remove the empty directory tree
        if hasattr(default_storage, 'path'):
            try:
                local_dir = default_storage.path(clean_dir)
                if os.path.exists(local_dir) and os.path.isdir(local_dir):
                    shutil.rmtree(local_dir, ignore_errors=True)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Storage purge note for path '{clean_dir}': {e}")

    return deleted_count


def abort_job(
    user,
    component_run_id: Optional[Union[str, uuid.UUID]] = None,
    pipeline_run_id: Optional[Union[str, uuid.UUID]] = None
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Aborts a running component job or full PipelineRun.
    Requires Admin or Manager role in the target workspace.

    Returns:
        (success, result_dict, error_message)
    """
    if component_run_id:
        try:
            cr_uuid = uuid.UUID(str(component_run_id))
            cr = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').get(id=cr_uuid)
        except (ValueError, ComponentRun.DoesNotExist):
            return False, {}, f"Error: ComponentRun '{component_run_id}' not found."

        workspace, membership, error = check_workspace_access(user, str(cr.pipeline_run.workspace.id), required_roles=['admin', 'manager'])
        if error:
            return False, {}, error

        # Revoke Celery Task if task ID exists
        if cr.celery_task_id:
            try:
                from django_project.celery import app as celery_app
                celery_app.control.revoke(cr.celery_task_id, terminate=True)
            except Exception:
                pass

        if cr.status in ['completed', 'failed', 'aborted']:
            return False, {}, f"Error: ComponentRun '{component_run_id}' is in status '{cr.status}' and cannot be aborted."

        cr.status = 'aborted'
        cr.completed_at = timezone.now()
        cr.save(update_fields=['status', 'completed_at'])

        pipeline_run = cr.pipeline_run
        remaining_active = ComponentRun.objects.filter(pipeline_run=pipeline_run, status__in=['pending', 'running']).exists()
        if not remaining_active:
            pipeline_run.status = 'aborted'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])

        return True, {
            "success": True,
            "status": "success",
            "message": f"ComponentRun '{component_run_id}' has been aborted.",
            "component_run_id": str(cr.id),
            "pipeline_run_id": str(pipeline_run.id)
        }, None

    elif pipeline_run_id:
        try:
            pr_uuid = uuid.UUID(str(pipeline_run_id))
            pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
        except (ValueError, PipelineRun.DoesNotExist):
            return False, {}, f"Error: PipelineRun '{pipeline_run_id}' not found."

        workspace, membership, error = check_workspace_access(user, str(pipeline_run.workspace.id), required_roles=['admin', 'manager'])
        if error:
            return False, {}, error

        if pipeline_run.status in ['completed', 'failed', 'aborted']:
            return False, {}, f"Error: PipelineRun '{pipeline_run_id}' is already in status '{pipeline_run.status}'."

        active_comp_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, status__in=['pending', 'running'])
        count = active_comp_runs.count()
        active_comp_runs.update(status='aborted', completed_at=timezone.now())

        pipeline_run.status = 'aborted'
        pipeline_run.completed_at = timezone.now()
        pipeline_run.save(update_fields=['status', 'completed_at'])

        return True, {
            "success": True,
            "status": "success",
            "message": f"PipelineRun '{pipeline_run_id}' and {count} active component run(s) have been aborted.",
            "pipeline_run_id": str(pipeline_run.id)
        }, None

    return False, {}, "Error: Must specify either component_run_id or pipeline_run_id to abort."


def delete_pipeline_run(user, pipeline_run_id: Union[str, uuid.UUID]) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Deletes a PipelineRun, cascading to ComponentRuns, Papers, Extractions, Metrics,
    and purges all associated files in default_storage.
    """
    try:
        pr_uuid = uuid.UUID(str(pipeline_run_id))
        pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
    except (ValueError, PipelineRun.DoesNotExist):
        return False, {}, f"Error: PipelineRun '{pipeline_run_id}' not found."

    workspace = pipeline_run.workspace
    ws_id_str = str(workspace.id)

    _, _, error = check_workspace_access(user, ws_id_str, required_roles=['admin', 'manager'])
    if error:
        return False, {}, error

    from django.db.models import Q, Count
    papers_qs = pipeline_run.get_papers()
    papers_count = papers_qs.count()
    comp_runs_count = pipeline_run.component_runs.count()
    extractions_count = Extraction.objects.filter(paper__in=pipeline_run.get_papers()).count()
    metrics_count = PaperMetric.objects.filter(Q(pipeline_run=pipeline_run) | Q(paper__in=pipeline_run.get_papers())).distinct().count()
    reports_count = NarrativeReport.objects.filter(pipeline_run=pipeline_run).count()

    orphan_papers = list(Paper.objects.filter(metrics__pipeline_run=pipeline_run).annotate(
        total_runs=Count('metrics__pipeline_run', distinct=True)
    ).filter(total_runs__lte=1))
    orphan_paper_ids = [p.id for p in orphan_papers]

    run_storage_dir = f"workspaces/{ws_id_str}/runs/{str(pipeline_run.id)}"
    files_purged = recursive_delete_run_storage(run_storage_dir)

    for paper in papers_qs.iterator():
        for path in (paper.original_pdf_path, paper.converted_md_path):
            if path and path.startswith(run_storage_dir):
                try:
                    if default_storage.exists(path):
                        default_storage.delete(path)
                        files_purged += 1
                except Exception as e:
                    logger.warning(f"Failed deleting storage file '{path}': {e}")

    pr_id_str = str(pipeline_run.id)
    pipeline_run.delete()
    if orphan_paper_ids:
        Paper.objects.filter(id__in=orphan_paper_ids).delete()

    return True, {
        "success": True,
        "status": "success",
        "message": f"PipelineRun '{pr_id_str}' and all associated Papers, Extractions, ComponentRuns, and storage files were successfully deleted.",
        "pipeline_run_id": pr_id_str,
        "workspace_id": ws_id_str,
        "deleted_counts": {
            "papers": papers_count,
            "extractions": extractions_count,
            "paper_metrics": metrics_count,
            "component_runs": comp_runs_count,
            "narrative_reports": reports_count,
            "storage_files": files_purged
        }
    }, None
