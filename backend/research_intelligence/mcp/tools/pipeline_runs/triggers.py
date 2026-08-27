import json
import uuid
import logging

from research_intelligence.models import (
    PipelineRun,
    ComponentRun,
    Scraper,
    Workspace,
    Paper,
    ExtractionDefinition,
)
from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job
from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job
from research_intelligence.tasks.step_6_signal_score.scorer import execute_signal_score_job
from ..workspaces import _check_workspace_access

logger = logging.getLogger(__name__)


def trigger_search_job_logic(
    user,
    workspace_id: str,
    scraper_id: str = None,
    limit: int = 50,
    reprocess_existing: bool = False
) -> str:
    """
    Trigger a Celery background scraping job for a workspace within a PipelineRun.
    Creates ComponentRun records to track execution lifecycle, raw storage, and metrics.
    Set reprocess_existing=True to re-screen and re-extract existing workspace papers.
    """
    workspace, membership, error = _check_workspace_access(user, workspace_id, required_roles=['admin', 'manager', 'researcher'])
    if error:
        return error

    # Resolve active scrapers
    if scraper_id:
        try:
            s_uuid = uuid.UUID(scraper_id)
            scrapers = Scraper.objects.filter(workspace=workspace, id=s_uuid, is_active=True)
            if not scrapers.exists():
                return f"Error: Active scraper with ID '{scraper_id}' not found in workspace '{workspace.name}'."
        except ValueError:
            return f"Error: '{scraper_id}' is not a valid UUID format."
    else:
        scrapers = Scraper.objects.filter(workspace=workspace, is_active=True)
        if not scrapers.exists():
            return f"Error: No active scrapers configured for workspace '{workspace.name}'. Please create a scraper first."

    # Create new PipelineRun
    pipeline_run = PipelineRun.objects.create(
        workspace=workspace,
        status='running',
        current_stage='search',
        reprocess_existing=bool(reprocess_existing),
        triggered_by=user if getattr(user, 'is_authenticated', False) or getattr(user, 'id', None) else None
    )

    created_runs = []
    for scraper in scrapers:
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type='search',
            component_name=f"{scraper.provider}_scraper",
            scraper=scraper,
            status='pending',
            input_params={"limit": limit, "search_query": scraper.search_query}
        )

        celery_task_id = None
        try:
            comp_run.status = 'running'
            comp_run.save(update_fields=['status'])
            async_res = execute_scraper_run_job.delay(str(comp_run.id), limit=limit)
            celery_task_id = str(async_res.id) if async_res and getattr(async_res, 'id', None) else "async_task"
            comp_run.celery_task_id = celery_task_id
            comp_run.save(update_fields=['celery_task_id'])
            comp_run.refresh_from_db()
        except Exception:
            # Execute synchronously in case Celery broker is offline
            execute_scraper_run_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            celery_task_id = comp_run.celery_task_id or "sync_execution"

        created_runs.append({
            "component_run_id": str(comp_run.id),
            "step_type": comp_run.step_type,
            "component_name": comp_run.component_name,
            "scraper_id": str(scraper.id),
            "provider": scraper.provider,
            "celery_task_id": celery_task_id,
            "status": comp_run.status
        })

    pipeline_run.refresh_from_db()

    return json.dumps({
        "success": True,
        "message": f"Successfully triggered scraping job for workspace '{workspace.name}'.",
        "pipeline_run_id": str(pipeline_run.id),
        "pipeline_status": pipeline_run.status,
        "component_runs": created_runs
    }, indent=2)


def trigger_pdf_download_job_logic(
    user,
    pipeline_run_id: str = None,
    workspace_id: str = None,
    limit: int = 50
) -> str:
    """
    Trigger Step 2 of the processing pipeline (PDF Binary Download) for papers in a PipelineRun or Workspace.
    Downloads PDF binaries into default_storage (MinIO/S3), updates paper.original_pdf_path, and skips already downloaded PDFs.
    """
    if not pipeline_run_id and not workspace_id:
        return "Error: Must specify either pipeline_run_id or workspace_id to download PDFs."

    pipeline_run = None
    if pipeline_run_id:
        try:
            pr_uuid = uuid.UUID(pipeline_run_id)
            pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
        except (ValueError, PipelineRun.DoesNotExist):
            return f"Error: PipelineRun '{pipeline_run_id}' not found."
        workspace = pipeline_run.workspace
    else:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            workspace = Workspace.objects.get(id=ws_uuid)
            pipeline_run = PipelineRun.objects.filter(workspace=workspace).order_by('-started_at').first()
            if not pipeline_run:
                return f"Error: No recent PipelineRun found for workspace '{workspace.name}'."
        except (ValueError, Workspace.DoesNotExist):
            return f"Error: Workspace '{workspace_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(workspace.id), required_roles=['admin', 'manager', 'researcher'])
    if error:
        return error

    papers_count = Paper.objects.filter(pipeline_run=pipeline_run).count()
    if papers_count == 0:
        return f"Error: No papers found in PipelineRun '{pipeline_run.id}'. Please run Step 1 (trigger_scraping_job) first."

    # Update pipeline_run status and current_stage
    pipeline_run.status = 'running'
    pipeline_run.current_stage = 'download'
    pipeline_run.save(update_fields=['status', 'current_stage'])

    # Create ComponentRun for Step 2 (PDF Download)
    comp_run = ComponentRun.objects.create(
        pipeline_run=pipeline_run,
        step_type='download',
        component_name="pdf_downloader",
        status='pending',
        input_params={"limit": limit, "pipeline_run_id": str(pipeline_run.id)}
    )

    celery_task_id = None
    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = execute_pdf_download_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = str(async_res.id) if async_res and getattr(async_res, 'id', None) else "async_task"
        comp_run.celery_task_id = celery_task_id
        comp_run.save(update_fields=['celery_task_id'])
        comp_run.refresh_from_db()
    except Exception:
        # Fallback to sync execution if Celery broker is offline
        execute_pdf_download_job(str(comp_run.id), limit=limit)
        comp_run.refresh_from_db()
        celery_task_id = comp_run.celery_task_id or "sync_execution"

    return json.dumps({
        "success": True,
        "message": f"Successfully launched PDF Download job for PipelineRun '{pipeline_run.id}'. Processing up to {limit} papers.",
        "pipeline_run_id": str(pipeline_run.id),
        "component_run_id": str(comp_run.id),
        "status": comp_run.status,
        "celery_task_id": celery_task_id,
        "total_papers_queued": min(papers_count, limit)
    }, indent=2)


def trigger_ocr_job_logic(
    user,
    pipeline_run_id: str = None,
    workspace_id: str = None,
    limit: int = 50
) -> str:
    """
    Trigger Step 3 of the processing pipeline (Layout OCR Extraction) for papers in a PipelineRun or Workspace.
    Converts downloaded PDFs into structured Markdown text using the workspace's configured OCR provider.
    """
    if not pipeline_run_id and not workspace_id:
        return "Error: Must specify either pipeline_run_id or workspace_id to trigger OCR."

    pipeline_run = None
    if pipeline_run_id:
        try:
            pr_uuid = uuid.UUID(pipeline_run_id)
            pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
        except (ValueError, PipelineRun.DoesNotExist):
            return f"Error: PipelineRun '{pipeline_run_id}' not found."
        workspace = pipeline_run.workspace
    else:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            workspace = Workspace.objects.get(id=ws_uuid)
            pipeline_run = PipelineRun.objects.filter(workspace=workspace).order_by('-started_at').first()
            if not pipeline_run:
                return f"Error: No recent PipelineRun found for workspace '{workspace.name}'."
        except (ValueError, Workspace.DoesNotExist):
            return f"Error: Workspace '{workspace_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(workspace.id), required_roles=['admin', 'manager', 'researcher'])
    if error:
        return error

    papers_count = Paper.objects.filter(pipeline_run=pipeline_run, original_pdf_path__isnull=False).count()
    if papers_count == 0:
        return f"Error: No papers with downloaded PDFs found in PipelineRun '{pipeline_run.id}'. Please run Step 2 (trigger_pdf_download_job) first."

    # Update pipeline_run status and current_stage
    pipeline_run.status = 'running'
    pipeline_run.current_stage = 'ocr'
    pipeline_run.save(update_fields=['status', 'current_stage'])

    # Create ComponentRun for Step 3 (OCR Conversion)
    comp_run = ComponentRun.objects.create(
        pipeline_run=pipeline_run,
        step_type='ocr',
        component_name=f"{workspace.ocr_provider}_ocr",
        status='pending',
        input_params={"limit": limit, "pipeline_run_id": str(pipeline_run.id), "ocr_provider": workspace.ocr_provider}
    )

    celery_task_id = None
    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = execute_ocr_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = str(async_res.id) if async_res and getattr(async_res, 'id', None) else "async_task"
        comp_run.celery_task_id = celery_task_id
        comp_run.save(update_fields=['celery_task_id'])
        comp_run.refresh_from_db()
    except Exception:
        # Fallback to sync execution if Celery broker is offline
        execute_ocr_job(str(comp_run.id), limit=limit)
        comp_run.refresh_from_db()
        celery_task_id = comp_run.celery_task_id or "sync_execution"

    return json.dumps({
        "success": True,
        "message": f"Successfully launched OCR Conversion job for PipelineRun '{pipeline_run.id}' using provider '{workspace.ocr_provider}'. Processing up to {limit} papers.",
        "pipeline_run_id": str(pipeline_run.id),
        "component_run_id": str(comp_run.id),
        "status": comp_run.status,
        "celery_task_id": celery_task_id,
        "ocr_provider": workspace.ocr_provider,
        "total_papers_queued": min(papers_count, limit)
    }, indent=2)


def trigger_screening_job_logic(
    user,
    pipeline_run_id: str = None,
    workspace_id: str = None,
    limit: int = 50
) -> str:
    """
    Trigger Step 4 of the processing pipeline (Abstract Screening) for papers in a PipelineRun or Workspace.
    Screens paper abstracts against acceptance and rejection criteria using the workspace LLM.
    """
    if not pipeline_run_id and not workspace_id:
        return "Error: Must specify either pipeline_run_id or workspace_id to run screening."

    pipeline_run = None
    if pipeline_run_id:
        try:
            pr_uuid = uuid.UUID(pipeline_run_id)
            pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
        except (ValueError, PipelineRun.DoesNotExist):
            return f"Error: PipelineRun '{pipeline_run_id}' not found."
        workspace = pipeline_run.workspace
    else:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            workspace = Workspace.objects.get(id=ws_uuid)
            pipeline_run = PipelineRun.objects.filter(workspace=workspace).order_by('-started_at').first()
            if not pipeline_run:
                return f"Error: No recent PipelineRun found for workspace '{workspace.name}'."
        except (ValueError, Workspace.DoesNotExist):
            return f"Error: Workspace '{workspace_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(workspace.id), required_roles=['admin', 'manager', 'researcher'])
    if error:
        return error

    papers_count = Paper.objects.filter(pipeline_run=pipeline_run).count()
    if papers_count == 0:
        return f"Error: No papers found in PipelineRun '{pipeline_run.id}'. Please run Step 1 (trigger_search_job) first."

    pipeline_run.status = 'running'
    pipeline_run.current_stage = 'screening'
    pipeline_run.save(update_fields=['status', 'current_stage'])

    comp_run = ComponentRun.objects.create(
        pipeline_run=pipeline_run,
        step_type='screening',
        component_name="abstract_screening",
        status='pending',
        input_params={"limit": limit, "pipeline_run_id": str(pipeline_run.id)}
    )

    celery_task_id = None
    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = execute_screening_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = str(async_res.id) if async_res and getattr(async_res, 'id', None) else "async_task"
        comp_run.celery_task_id = celery_task_id
        comp_run.save(update_fields=['celery_task_id'])
        comp_run.refresh_from_db()
    except Exception:
        execute_screening_job(str(comp_run.id), limit=limit)
        comp_run.refresh_from_db()
        celery_task_id = comp_run.celery_task_id or "sync_execution"

    return json.dumps({
        "success": True,
        "message": f"Successfully launched Abstract Screening job for PipelineRun '{pipeline_run.id}'. Processing up to {limit} papers.",
        "pipeline_run_id": str(pipeline_run.id),
        "component_run_id": str(comp_run.id),
        "status": comp_run.status,
        "celery_task_id": celery_task_id,
        "total_papers_queued": min(papers_count, limit)
    }, indent=2)


def trigger_extraction_job_logic(
    user,
    pipeline_run_id: str = None,
    workspace_id: str = None,
    limit: int = 50
) -> str:
    """
    Trigger Step 5 of the processing pipeline (Parameter & Claim Extraction) for papers in a PipelineRun or Workspace.
    Runs extraction for all active ExtractionDefinitions configured for the workspace.
    """
    if not pipeline_run_id and not workspace_id:
        return "Error: Must specify either pipeline_run_id or workspace_id to run extractions."

    pipeline_run = None
    if pipeline_run_id:
        try:
            pr_uuid = uuid.UUID(pipeline_run_id)
            pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
        except (ValueError, PipelineRun.DoesNotExist):
            return f"Error: PipelineRun '{pipeline_run_id}' not found."
        workspace = pipeline_run.workspace
    else:
        try:
            ws_uuid = uuid.UUID(workspace_id)
            workspace = Workspace.objects.get(id=ws_uuid)
            pipeline_run = PipelineRun.objects.filter(workspace=workspace).order_by('-started_at').first()
            if not pipeline_run:
                return f"Error: No recent PipelineRun found for workspace '{workspace.name}'."
        except (ValueError, Workspace.DoesNotExist):
            return f"Error: Workspace '{workspace_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(workspace.id), required_roles=['admin', 'manager', 'researcher'])
    if error:
        return error

    active_definitions_count = ExtractionDefinition.objects.filter(workspace=workspace, is_active=True).count()
    if active_definitions_count == 0:
        return f"Error: No active ExtractionDefinitions configured for workspace '{workspace.name}'. Please create an extraction definition first."

    papers_count = Paper.objects.filter(pipeline_run=pipeline_run).count()
    if papers_count == 0:
        return f"Error: No papers found in PipelineRun '{pipeline_run.id}'. Please run Step 1 (trigger_search_job) first."

    pipeline_run.status = 'running'
    pipeline_run.current_stage = 'extraction'
    pipeline_run.save(update_fields=['status', 'current_stage'])

    comp_run = ComponentRun.objects.create(
        pipeline_run=pipeline_run,
        step_type='extraction',
        component_name="parameter_extraction",
        status='pending',
        input_params={"limit": limit, "pipeline_run_id": str(pipeline_run.id), "active_definitions_count": active_definitions_count}
    )

    celery_task_id = None
    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = execute_extraction_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = str(async_res.id) if async_res and getattr(async_res, 'id', None) else "async_task"
        comp_run.celery_task_id = celery_task_id
        comp_run.save(update_fields=['celery_task_id'])
        comp_run.refresh_from_db()
    except Exception:
        execute_extraction_job(str(comp_run.id), limit=limit)
        comp_run.refresh_from_db()
        celery_task_id = comp_run.celery_task_id or "sync_execution"

    return json.dumps({
        "success": True,
        "message": f"Successfully launched Parameter Extraction job for PipelineRun '{pipeline_run.id}'. Running {active_definitions_count} definitions across up to {limit} papers.",
        "pipeline_run_id": str(pipeline_run.id),
        "component_run_id": str(comp_run.id),
        "status": comp_run.status,
        "celery_task_id": celery_task_id,
        "active_definitions_count": active_definitions_count,
        "total_papers_queued": min(papers_count, limit)
    }, indent=2)


def trigger_signal_score_job_logic(
    user,
    pipeline_run_id: str,
    limit: int = 50
) -> str:
    """
    Trigger Step 6 (Composite Signal Score Evaluation) for a PipelineRun.
    Evaluates the sandboxed Python signal score logic for all screened and accepted papers.
    """
    try:
        pr_uuid = uuid.UUID(pipeline_run_id)
        pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
    except (ValueError, PipelineRun.DoesNotExist):
        return f"Error: PipelineRun '{pipeline_run_id}' not found."

    workspace, membership, error = _check_workspace_access(user, str(pipeline_run.workspace.id), required_roles=['admin', 'manager', 'researcher'])
    if error:
        return error

    accepted_statuses = ['accepted', 'full_text_passed', 'abstract_passed']
    papers_qs = Paper.objects.filter(pipeline_run=pipeline_run, screening_status__in=accepted_statuses)
    papers_count = papers_qs.count()

    if papers_count == 0:
        return f"Error: No accepted papers found in PipelineRun '{pipeline_run_id}' to score."

    pipeline_run.status = 'running'
    pipeline_run.current_stage = 'signal_score'
    pipeline_run.save(update_fields=['status', 'current_stage'])

    comp_run = ComponentRun.objects.create(
        pipeline_run=pipeline_run,
        step_type='signal_score',
        component_name="signal_score_evaluation",
        status='running',
        input_params={"limit": limit}
    )

    celery_task_id = None
    try:
        async_res = execute_signal_score_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = async_res.id
        comp_run.celery_task_id = celery_task_id
        comp_run.save(update_fields=['celery_task_id'])
    except Exception:
        execute_signal_score_job(str(comp_run.id), limit=limit)
        comp_run.refresh_from_db()
        celery_task_id = comp_run.celery_task_id or "sync_execution"

    return json.dumps({
        "success": True,
        "message": f"Successfully launched Step 6 Signal Score evaluation for PipelineRun '{pipeline_run.id}' across {papers_count} papers.",
        "pipeline_run_id": str(pipeline_run.id),
        "component_run_id": str(comp_run.id),
        "status": comp_run.status,
        "celery_task_id": celery_task_id,
        "total_papers_queued": min(papers_count, limit) if limit else papers_count
    }, indent=2)
