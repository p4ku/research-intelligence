import json
import uuid
import logging
from django.utils import timezone
from django.db.models import F
from django.core.serializers.json import DjangoJSONEncoder
from django.core.files.storage import default_storage

from research_intelligence.models import (
    PipelineRun,
    ComponentRun,
    Workspace,
    Paper,
    Extraction,
    PaperMetric,
)
from research_intelligence.services import check_workspace_access

logger = logging.getLogger(__name__)


def _get_run_storage_stats(dir_path: str) -> dict:
    """Calculate total size in bytes, total files count, and human-readable formatted size for a storage directory."""
    total_bytes = 0
    total_files = 0
    clean_dir = dir_path.strip('/')

    def _format_size(size_bytes: int) -> str:
        if size_bytes is None or size_bytes == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        val = float(size_bytes)
        while val >= 1024.0 and idx < len(units) - 1:
            val /= 1024.0
            idx += 1
        return f"{val:.2f} {units[idx]}"

    def _traverse(current_dir: str):
        nonlocal total_bytes, total_files
        try:
            dirs, files = default_storage.listdir(current_dir)
            for f in files:
                f_path = f"{current_dir}/{f}"
                try:
                    size = default_storage.size(f_path)
                    total_bytes += size
                    total_files += 1
                except Exception:
                    pass
            for d in dirs:
                d_path = f"{current_dir}/{d}"
                _traverse(d_path)
        except Exception:
            pass

    if clean_dir:
        _traverse(clean_dir)

    return {
        "storage_path": clean_dir,
        "total_files": total_files,
        "size_bytes": total_bytes,
        "size_formatted": _format_size(total_bytes)
    }


def get_pipeline_run_status_logic(user, pipeline_run_id: str) -> str:
    """Retrieve full status, metrics, downloaded paper counts, storage footprint, and component run states for a PipelineRun."""
    try:
        pr_uuid = uuid.UUID(pipeline_run_id)
    except ValueError:
        return f"Error: '{pipeline_run_id}' is not a valid UUID format."

    try:
        pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
    except PipelineRun.DoesNotExist:
        return f"Error: PipelineRun with ID '{pipeline_run_id}' does not exist."

    workspace, membership, error = check_workspace_access(user, str(pipeline_run.workspace.id))
    if error:
        return error

    comp_runs_list = list(ComponentRun.objects.filter(pipeline_run=pipeline_run).select_related('scraper'))
    
    # Dynamically sync pipeline_run status if all component runs are finished and no active research agent is driving it
    has_active = any(cr.status in ['pending', 'running'] for cr in comp_runs_list)
    has_failed = any(cr.status == 'failed' for cr in comp_runs_list)
    has_aborted = any(cr.status == 'aborted' for cr in comp_runs_list)
    has_active_agent = pipeline_run.agent_processes.filter(status__in=['running', 'paused']).exists()

    if comp_runs_list and not has_active and not has_active_agent:
        if has_failed and pipeline_run.status != 'aborted':
            pipeline_run.status = 'failed'
        elif has_aborted:
            pipeline_run.status = 'aborted'
        else:
            pipeline_run.status = 'completed'
        if not pipeline_run.completed_at:
            pipeline_run.completed_at = timezone.now()
        pipeline_run.save(update_fields=['status', 'completed_at'])

    from django.db.models import Count, Q
    paper_stats = pipeline_run.get_papers().aggregate(
        total_fetched=Count('id'),
        downloaded_count=Count('id', filter=Q(original_pdf_path__isnull=False) & ~Q(original_pdf_path='')),
        ocr_count=Count('id', filter=Q(converted_md_path__isnull=False) & ~Q(converted_md_path='')),
        abstract_passed=Count('id', filter=Q(screening_status__in=['abstract_passed', 'full_text_passed'])),
        abstract_screened=Count('id', filter=Q(screening_status__in=['abstract_passed', 'full_text_passed', 'rejected'])),
        full_text_passed=Count('id', filter=Q(screening_status='full_text_passed')),
        rejected_count=Count('id', filter=Q(screening_status='rejected')),
    )

    total_papers_fetched = pipeline_run.total_papers_fetched or paper_stats['total_fetched']
    downloaded_papers_count = paper_stats['downloaded_count']
    ocr_converted_papers_count = paper_stats['ocr_count']
    
    abstract_run = next((cr for cr in comp_runs_list if cr.step_type == 'screening' and 'abstract' in (cr.component_name or '').lower()), None)
    full_text_run = next((cr for cr in comp_runs_list if cr.step_type == 'screening' and 'full_text' in (cr.component_name or '').lower()), None)

    abstract_metrics = abstract_run.metrics if (abstract_run and abstract_run.metrics) else {}
    full_text_metrics = full_text_run.metrics if (full_text_run and full_text_run.metrics) else {}

    abstract_screened = abstract_metrics.get("total_screened", paper_stats['abstract_screened']) if abstract_run else 0
    abstract_passed = abstract_metrics.get("passed", paper_stats['abstract_passed']) if abstract_run else 0
    abstract_rejected = abstract_metrics.get("rejected", paper_stats['rejected_count']) if abstract_run else 0

    full_text_screened = full_text_metrics.get("total_screened", paper_stats['full_text_passed'] + paper_stats['rejected_count']) if full_text_run else 0
    full_text_passed = full_text_metrics.get("passed", paper_stats['full_text_passed']) if full_text_run else 0
    full_text_rejected = full_text_metrics.get("rejected", paper_stats['rejected_count']) if full_text_run else 0

    extractions_count = Extraction.objects.filter(paper__in=pipeline_run.get_papers()).count()
    paper_metrics_count = PaperMetric.objects.filter(Q(pipeline_run=pipeline_run) | Q(paper__in=pipeline_run.get_papers())).distinct().count()

    # Calculate physical storage footprint for run directory
    run_storage_dir = f"workspaces/{pipeline_run.workspace.id}/runs/{pipeline_run.id}"
    storage_stats = _get_run_storage_stats(run_storage_dir)

    search_runs = [cr for cr in comp_runs_list if cr.step_type == 'search']
    duplicates_count = sum(
        int((cr.metrics or {}).get("duplicates_count", (cr.metrics or {}).get("total_duplicates", (cr.metrics or {}).get("duplicates_skipped", (cr.metrics or {}).get("total_duplicates_skipped", 0)))) or 0)
        for cr in search_runs
    )

    runs_list = []
    for cr in comp_runs_list:
        runs_list.append({
            "component_run_id": str(cr.id),
            "step_type": cr.step_type,
            "component_name": cr.component_name,
            "scraper_id": str(cr.scraper.id) if cr.scraper else None,
            "celery_task_id": cr.celery_task_id,
            "status": cr.status,
            "metrics": cr.metrics,
            "output_data": cr.output_data,
            "duration_seconds": cr.duration_seconds,
            "execution_time": cr.execution_time_display,
            "raw_storage_path": cr.raw_storage_path,
            "input_params": cr.input_params,
            "error_message": cr.error_message,
            "started_at": cr.started_at.isoformat(),
            "completed_at": cr.completed_at.isoformat() if cr.completed_at else None
        })

    # Fetched papers previews
    papers_qs = pipeline_run.get_papers()
    papers_preview = []
    for p in papers_qs[:20]:
        papers_preview.append({
            "id": str(p.id),
            "title": p.title,
            "authors": p.authors,
            "doi": p.doi,
            "arxiv_id": p.arxiv_id,
            "source_database": p.source_database,
            "original_pdf_path": p.original_pdf_path,
            "converted_md_path": p.converted_md_path,
            "screening_status": p.screening_status,
            "signal_score": p.signal_score,
            "created_at": p.created_at.isoformat()
        })

    details = {
        "pipeline_run_id": str(pipeline_run.id),
        "workspace_id": str(pipeline_run.workspace.id),
        "workspace_name": pipeline_run.workspace.name,
        "schedule_id": str(pipeline_run.schedule.id) if pipeline_run.schedule else None,
        "schedule_name": pipeline_run.schedule.name if pipeline_run.schedule else None,
        "reprocess_existing": pipeline_run.reprocess_existing,
        "status_message": pipeline_run.status_message,
        "status": pipeline_run.status,
        "current_stage": pipeline_run.current_stage,
        "triggered_by": {
            "id": str(pipeline_run.triggered_by.id) if pipeline_run.triggered_by else None,
            "username": pipeline_run.triggered_by.username if pipeline_run.triggered_by else "system",
            "email": pipeline_run.triggered_by.email if pipeline_run.triggered_by else None
        },
        "total_papers_fetched": total_papers_fetched,
        "duplicates_count": duplicates_count,
        "downloaded_documents_count": downloaded_papers_count,
        "ocr_converted_documents_count": ocr_converted_papers_count,
        "screening_metrics": {
            "abstract_stage": {
                "total_screened": abstract_screened,
                "passed": abstract_passed,
                "rejected": abstract_rejected
            },
            "full_text_stage": {
                "total_screened": full_text_screened,
                "passed": full_text_passed,
                "rejected": full_text_rejected
            }
        },
        "extractions_count": extractions_count,
        "paper_metrics_count": paper_metrics_count,
        "storage": storage_stats,
        "tokens_in": pipeline_run.tokens_in,
        "tokens_out": pipeline_run.tokens_out,
        "tokens_consumed": pipeline_run.tokens_consumed,
        "usd_cost": float(pipeline_run.usd_cost),
        "duration_seconds": pipeline_run.duration_seconds,
        "execution_time": pipeline_run.execution_time_display,
        "started_at": pipeline_run.started_at.isoformat(),
        "completed_at": pipeline_run.completed_at.isoformat() if pipeline_run.completed_at else None,
        "fetched_papers_preview": papers_preview,
        "extractions_matrix_preview": [
            {
                "paper_id": str(p.id),
                "title": p.title,
                "screening_status": p.screening_status,
                "signal_score": p.signal_score,
                "metrics": {
                    (e.extraction_definition.name if e.extraction_definition else e.category): (e.exit_metric or e.get_exit_metric())
                    for e in p.extractions.all()
                    if (e.extraction_definition or e.category)
                }
            }
            for p in Paper.objects.filter(
                pipeline_run=pipeline_run,
                screening_status__in=['full_text_passed', 'abstract_passed', 'accepted']
            ).order_by(F('signal_score').desc(nulls_last=True), '-created_at').prefetch_related('extractions', 'extractions__extraction_definition')[:30]
        ],
        "component_runs": runs_list
    }
    return json.dumps(details, indent=2, cls=DjangoJSONEncoder)


def get_component_run_status_logic(user, component_run_id: str) -> str:
    """Retrieve status, raw storage path, metrics, and output preview for a specific ComponentRun."""
    try:
        cr_uuid = uuid.UUID(component_run_id)
    except ValueError:
        return f"Error: '{component_run_id}' is not a valid UUID format."

    try:
        cr = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace', 'scraper').get(id=cr_uuid)
    except ComponentRun.DoesNotExist:
        return f"Error: ComponentRun with ID '{component_run_id}' does not exist."

    workspace, membership, error = check_workspace_access(user, str(cr.pipeline_run.workspace.id))
    if error:
        return error

    papers_preview = cr.output_data.get("papers_preview", [])
    details = {
        "component_run_id": str(cr.id),
        "pipeline_run_id": str(cr.pipeline_run.id),
        "workspace_id": str(cr.pipeline_run.workspace.id),
        "workspace_name": cr.pipeline_run.workspace.name,
        "step_type": cr.step_type,
        "component_name": cr.component_name,
        "scraper_id": str(cr.scraper.id) if cr.scraper else None,
        "celery_task_id": cr.celery_task_id,
        "status": cr.status,
        "raw_storage_path": cr.raw_storage_path,
        "input_params": cr.input_params,
        "metrics": cr.metrics,
        "output_data": cr.output_data,
        "duration_seconds": cr.duration_seconds,
        "execution_time": cr.execution_time_display,
        "fetched_papers_preview": papers_preview,
        "error_message": cr.error_message,
        "started_at": cr.started_at.isoformat(),
        "completed_at": cr.completed_at.isoformat() if cr.completed_at else None
    }
    return json.dumps(details, indent=2, cls=DjangoJSONEncoder)


def list_pipeline_runs_logic(user, workspace_id: str = None, limit: int = 20) -> str:
    """List pipeline runs and their component run status tree (filtered by workspace)."""
    if workspace_id:
        workspace, membership, error = check_workspace_access(user, workspace_id)
        if error:
            return json.dumps({"status": "error", "error": error}, indent=2)
        runs_qs = PipelineRun.objects.filter(workspace=workspace).select_related('workspace', 'triggered_by').prefetch_related('component_runs', 'agent_processes').order_by('-started_at')
    else:
        accessible_ws = Workspace.objects.filter(memberships__user=user)
        runs_qs = PipelineRun.objects.filter(workspace__in=accessible_ws).select_related('workspace', 'triggered_by').prefetch_related('component_runs', 'agent_processes').order_by('-started_at')

    runs = list(runs_qs[:limit]) if limit else list(runs_qs)
    result = []
    for r in runs:
        comp_runs_tree = []
        for cr in r.component_runs.all():
            comp_runs_tree.append({
                "component_run_id": str(cr.id),
                "step_type": cr.step_type,
                "component_name": cr.component_name,
                "scraper_id": str(cr.scraper.id) if cr.scraper else None,
                "status": cr.status,
                "celery_task_id": cr.celery_task_id,
                "metrics": cr.metrics,
                "duration_seconds": cr.duration_seconds,
                "execution_time": cr.execution_time_display,
                "raw_storage_path": cr.raw_storage_path,
                "input_params": cr.input_params,
                "error_message": cr.error_message,
                "started_at": cr.started_at.isoformat(),
                "completed_at": cr.completed_at.isoformat() if cr.completed_at else None
            })

        agent_procs = list(r.agent_processes.all())
        agent_proc = agent_procs[0] if agent_procs else None
        run_name = agent_proc.name if agent_proc else f"Pipeline Run {r.run_date.strftime('%Y-%m-%d %H:%M')}"

        result.append({
            "pipeline_run_id": str(r.id),
            "name": run_name,
            "agent_process_id": str(agent_proc.id) if agent_proc else None,
            "schedule_id": str(r.schedule.id) if r.schedule else None,
            "schedule_name": r.schedule.name if r.schedule else None,
            "reprocess_existing": r.reprocess_existing,
            "status_message": r.status_message,
            "run_date": r.run_date.isoformat(),
            "status": r.status,
            "current_stage": r.current_stage,
            "triggered_by": {
                "id": str(r.triggered_by.id) if r.triggered_by else None,
                "username": r.triggered_by.username if r.triggered_by else "system",
                "email": r.triggered_by.email if r.triggered_by else None
            },
            "total_papers_fetched": r.total_papers_fetched,
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
            "tokens_consumed": r.tokens_consumed,
            "usd_cost": float(r.usd_cost),
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "component_runs": comp_runs_tree
        })
    return json.dumps(result, indent=2, cls=DjangoJSONEncoder)
