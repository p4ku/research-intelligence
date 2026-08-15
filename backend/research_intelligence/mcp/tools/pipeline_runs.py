import json
import uuid
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import PipelineRun, ComponentRun, Scraper, Workspace
from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job
from .workspaces import _check_workspace_access


def trigger_search_job_logic(
    user,
    workspace_id: str,
    scraper_id: str = None,
    limit: int = 50
) -> str:
    """
    Trigger a Celery background scraping job for a workspace within a PipelineRun.
    Creates ComponentRun records to track execution lifecycle, raw storage, and metrics.
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
        current_stage='search'
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
            celery_task_id = async_res.id
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


def _get_run_storage_stats(dir_path: str) -> dict:
    """Calculate total size in bytes, total files count, and human-readable formatted size for a storage directory."""
    from django.core.files.storage import default_storage
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

    workspace, membership, error = _check_workspace_access(user, str(pipeline_run.workspace.id))
    if error:
        return error

    comp_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run).select_related('scraper')
    
    # Dynamically sync pipeline_run status if all component runs are finished
    if comp_runs.exists() and not comp_runs.filter(status__in=['pending', 'running']).exists():
        if comp_runs.filter(status='failed').exists():
            pipeline_run.status = 'failed'
        elif comp_runs.filter(status='aborted').exists():
            pipeline_run.status = 'aborted'
        else:
            pipeline_run.status = 'completed'
        if not pipeline_run.completed_at:
            pipeline_run.completed_at = timezone.now()
        pipeline_run.save(update_fields=['status', 'completed_at'])

    from research_intelligence.models import Paper, Extraction, PaperMetric

    papers_qs = Paper.objects.filter(pipeline_run=pipeline_run)
    total_papers_fetched = pipeline_run.total_papers_fetched or papers_qs.count()
    downloaded_papers_count = papers_qs.filter(original_pdf_path__isnull=False).exclude(original_pdf_path='').count()
    ocr_converted_papers_count = papers_qs.filter(converted_md_path__isnull=False).exclude(converted_md_path='').count()
    screened_papers_count = PaperMetric.objects.filter(paper__pipeline_run=pipeline_run).count()
    extractions_count = Extraction.objects.filter(paper__pipeline_run=pipeline_run).count()

    # Calculate storage footprint for this run
    run_storage_dir = f"workspaces/{pipeline_run.workspace.id}/runs/{pipeline_run.id}"
    storage_stats = _get_run_storage_stats(run_storage_dir)

    runs_list = []
    for cr in comp_runs:
        runs_list.append({
            "component_run_id": str(cr.id),
            "step_type": cr.step_type,
            "component_name": cr.component_name,
            "scraper_id": str(cr.scraper.id) if cr.scraper else None,
            "celery_task_id": cr.celery_task_id,
            "status": cr.status,
            "raw_storage_path": cr.raw_storage_path,
            "input_params": cr.input_params,
            "metrics": cr.metrics,
            "output_data": cr.output_data,
            "error_message": cr.error_message,
            "started_at": cr.started_at.isoformat(),
            "completed_at": cr.completed_at.isoformat() if cr.completed_at else None
        })

    papers_sample = papers_qs.order_by('-created_at')[:10]
    papers_preview = [
        {
            "paper_id": str(p.id),
            "title": p.title,
            "authors": p.authors,
            "source_database": p.source_database,
            "pdf_url": p.original_pdf_path,
            "abstract": p.abstract,
            "abstract_preview": p.abstract[:150] + "..." if len(p.abstract) > 150 else p.abstract
        }
        for p in papers_sample
    ]

    details = {
        "pipeline_run_id": str(pipeline_run.id),
        "workspace_id": str(pipeline_run.workspace.id),
        "workspace_name": pipeline_run.workspace.name,
        "run_date": pipeline_run.run_date.isoformat(),
        "status": pipeline_run.status,
        "current_stage": pipeline_run.current_stage,
        "total_papers_fetched": total_papers_fetched,
        "downloaded_documents_count": downloaded_papers_count,
        "ocr_converted_documents_count": ocr_converted_papers_count,
        "screened_documents_count": screened_papers_count,
        "extractions_count": extractions_count,
        "tokens_in": pipeline_run.tokens_in,
        "tokens_out": pipeline_run.tokens_out,
        "tokens_consumed": pipeline_run.tokens_consumed,
        "usd_cost": float(pipeline_run.usd_cost),
        "storage": storage_stats,
        "started_at": pipeline_run.started_at.isoformat(),
        "completed_at": pipeline_run.completed_at.isoformat() if pipeline_run.completed_at else None,
        "fetched_papers_preview": papers_preview,
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

    workspace, membership, error = _check_workspace_access(user, str(cr.pipeline_run.workspace.id))
    if error:
        return error

    from research_intelligence.models import Paper
    papers_sample = Paper.objects.filter(pipeline_run=cr.pipeline_run).order_by('-created_at')[:10]
    papers_preview = [
        {
            "paper_id": str(p.id),
            "title": p.title,
            "authors": p.authors,
            "source_database": p.source_database,
            "pdf_url": p.original_pdf_path,
            "abstract": p.abstract,
            "abstract_preview": p.abstract[:150] + "..." if len(p.abstract) > 150 else p.abstract
        }
        for p in papers_sample
    ]

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
        "fetched_papers_preview": papers_preview,
        "error_message": cr.error_message,
        "started_at": cr.started_at.isoformat(),
        "completed_at": cr.completed_at.isoformat() if cr.completed_at else None
    }
    return json.dumps(details, indent=2, cls=DjangoJSONEncoder)


def abort_job_logic(user, component_run_id: str = None, pipeline_run_id: str = None) -> str:
    """Abort a running component job or full PipelineRun (requires Admin or Manager role)."""
    if component_run_id:
        try:
            cr_uuid = uuid.UUID(component_run_id)
            cr = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').get(id=cr_uuid)
        except (ValueError, ComponentRun.DoesNotExist):
            return f"Error: ComponentRun '{component_run_id}' not found."

        workspace, membership, error = _check_workspace_access(user, str(cr.pipeline_run.workspace.id), required_roles=['admin', 'manager'])
        if error:
            return error

        # Revoke Celery Task if task ID exists
        if cr.celery_task_id:
            try:
                from django_project.celery import app as celery_app
                celery_app.control.revoke(cr.celery_task_id, terminate=True)
            except Exception:
                pass

        cr.status = 'aborted'
        cr.completed_at = timezone.now()
        cr.save(update_fields=['status', 'completed_at'])

        # Check PipelineRun state
        pr = cr.pipeline_run
        if not pr.component_runs.exclude(status='aborted').exists():
            pr.status = 'aborted'
            pr.completed_at = timezone.now()
            pr.save(update_fields=['status', 'completed_at'])

        return json.dumps({
            "success": True,
            "message": f"Successfully aborted ComponentRun '{component_run_id}'.",
            "component_run_id": str(cr.id),
            "status": cr.status
        }, indent=2)

    elif pipeline_run_id:
        try:
            pr_uuid = uuid.UUID(pipeline_run_id)
            pr = PipelineRun.objects.select_related('workspace').get(id=pr_uuid)
        except (ValueError, PipelineRun.DoesNotExist):
            return f"Error: PipelineRun '{pipeline_run_id}' not found."

        workspace, membership, error = _check_workspace_access(user, str(pr.workspace.id), required_roles=['admin', 'manager'])
        if error:
            return error

        for cr in pr.component_runs.all():
            if cr.celery_task_id:
                try:
                    from django_project.celery import app as celery_app
                    celery_app.control.revoke(cr.celery_task_id, terminate=True)
                except Exception:
                    pass
            cr.status = 'aborted'
            cr.completed_at = timezone.now()
            cr.save(update_fields=['status', 'completed_at'])

        pr.status = 'aborted'
        pr.completed_at = timezone.now()
        pr.save(update_fields=['status', 'completed_at'])

        return json.dumps({
            "success": True,
            "message": f"Successfully aborted PipelineRun '{pipeline_run_id}' and all attached component jobs.",
            "pipeline_run_id": str(pr.id),
            "status": pr.status
        }, indent=2)

    else:
        return "Error: Must specify either component_run_id or pipeline_run_id to abort."


def list_pipeline_runs_logic(user, workspace_id: str, limit: int = 20) -> str:
    """List historical PipelineRun executions along with nested ComponentRuns for a workspace."""
    workspace, membership, error = _check_workspace_access(user, workspace_id)
    if error:
        return error

    limit_val = max(1, min(int(limit or 20), 100))
    runs = (
        PipelineRun.objects.filter(workspace=workspace)
        .prefetch_related('agent_processes', 'component_runs', 'component_runs__scraper')
        .order_by('-started_at')[:limit_val]
    )
    if not runs.exists():
        return json.dumps({"message": f"No pipeline runs found for workspace '{workspace.name}'."}, indent=2)

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
            "run_date": r.run_date.isoformat(),
            "status": r.status,
            "current_stage": r.current_stage,
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

    from research_intelligence.models import Paper
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

    from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job

    celery_task_id = None
    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = execute_pdf_download_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = async_res.id
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

    from research_intelligence.models import Paper
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

    from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job

    celery_task_id = None
    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = execute_ocr_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = async_res.id
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

    from research_intelligence.models import Paper
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

    from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job

    celery_task_id = None
    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = execute_screening_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = async_res.id
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

    from research_intelligence.models import Paper, ExtractionDefinition
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

    from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job

    celery_task_id = None
    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = execute_extraction_job.delay(str(comp_run.id), limit=limit)
        celery_task_id = async_res.id
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


def _recursive_delete_run_storage(dir_path: str) -> int:
    """Recursively delete all files and directory structures inside dir_path in default_storage."""
    import os
    import shutil
    from django.core.files.storage import default_storage
    deleted_count = 0
    clean_dir = dir_path.strip('/')
    if not clean_dir or clean_dir in ('', 'workspaces'):
        return 0
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

        # On local filesystem, remove the empty directory or directory tree
        if hasattr(default_storage, 'path'):
            try:
                local_dir = default_storage.path(clean_dir)
                if os.path.isdir(local_dir):
                    if not os.listdir(local_dir):
                        os.rmdir(local_dir)
                    else:
                        shutil.rmtree(local_dir, ignore_errors=True)
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
    workspace, membership, error = _check_workspace_access(user, str(workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    from research_intelligence.models import Paper, Extraction, PaperMetric, NarrativeReport
    from django.core.files.storage import default_storage

    papers_qs = Paper.objects.filter(pipeline_run=pipeline_run)
    papers_count = papers_qs.count()
    component_runs_count = pipeline_run.component_runs.count()
    extractions_count = Extraction.objects.filter(paper__pipeline_run=pipeline_run).count()
    metrics_count = PaperMetric.objects.filter(paper__pipeline_run=pipeline_run).count()
    reports_count = NarrativeReport.objects.filter(pipeline_run=pipeline_run).count()

    # Clean up physical storage files and folder recursively: workspaces/{workspace_id}/runs/{pipeline_run_id}
    run_storage_dir = f"workspaces/{workspace.id}/runs/{pipeline_run.id}"
    deleted_files_count = _recursive_delete_run_storage(run_storage_dir)

    # Extra safety check for any papers whose paths might have been saved outside the run folder:
    for paper in papers_qs.iterator():
        for path in (paper.original_pdf_path, paper.converted_md_path):
            if path and not (path.startswith("http://") or path.startswith("https://")):
                try:
                    if default_storage.exists(path):
                        default_storage.delete(path)
                        deleted_files_count += 1
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed deleting storage file {path}: {e}")

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
