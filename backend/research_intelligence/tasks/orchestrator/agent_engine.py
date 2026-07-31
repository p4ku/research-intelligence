import logging
import time
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections
from research_intelligence.models import Workspace, PipelineRun, ComponentRun, ResearchAgentProcess, Scraper

logger = logging.getLogger(__name__)


def _send_agent_notification(agent_process: ResearchAgentProcess):
    """
    Sends an email notification / log summary when an agent process completes or fails.
    Notifies all workspace member users, active subscribers, and any explicit override email.
    """
    recipients = set()

    # Explicit override in config or workspace setting
    override_email = (
        agent_process.configuration_override.get("notification_email")
        or agent_process.workspace.notification_email
    )
    if override_email:
        recipients.add(override_email)

    # Workspace Members
    from research_intelligence.models import WorkspaceMember
    memberships = WorkspaceMember.objects.filter(workspace=agent_process.workspace).select_related('user')
    for m in memberships:
        if m.user and m.user.email:
            recipients.add(m.user.email)

    # Workspace Subscribers
    subscribers = agent_process.workspace.subscribers.filter(is_active=True)
    for s in subscribers:
        if s.email:
            recipients.add(s.email)

    title = agent_process.name
    ws_name = agent_process.workspace.name
    status = agent_process.status
    pr_id = agent_process.pipeline_run.id if agent_process.pipeline_run else "N/A"

    recipient_list_str = ", ".join(sorted(recipients)) if recipients else "System Log (No members/subscribers found)"
    summary_msg = f"Research Agent '{title}' for Workspace '{ws_name}' finished with status: {status.upper()} (Run ID: {pr_id})."
    logger.info(f"📧 [NOTIFICATION SENT] To: [{recipient_list_str}] | {summary_msg}")


def tick_agent_process(process_id: str) -> dict:
    """
    Autonomous State Machine Orchestrator logic function.
    Evaluates current step of a ResearchAgentProcess and drives it to the next pipeline stage.
    """
    close_old_connections()
    try:
        process = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').get(pk=process_id)
    except ResearchAgentProcess.DoesNotExist:
        logger.error(f"ResearchAgentProcess '{process_id}' not found.")
        return {"success": False, "error": f"ResearchAgentProcess '{process_id}' not found."}

    # If agent is in terminal or paused state, do not advance
    if process.status in ['paused', 'aborted', 'failed', 'completed']:
        logger.info(f"Agent process '{process.id}' is in status '{process.status}'. No state transition taken.")
        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Agent process is in status '{process.status}'."
        }

    workspace = process.workspace
    config = process.configuration_override or {}
    limit = config.get("limit", 50)
    history = process.step_history or []

    # 1. State: INITIALIZED -> Launch Step 1 (Search & Ingestion)
    if process.current_step == 'initialized':
        pipeline_run = PipelineRun.objects.create(
            workspace=workspace,
            status='running',
            current_stage='search'
        )
        process.pipeline_run = pipeline_run
        process.status = 'running'
        process.current_step = 'search'

        history.append({
            "step": "search",
            "event": "started",
            "pipeline_run_id": str(pipeline_run.id),
            "timestamp": timezone.now().isoformat()
        })
        process.step_history = history
        process.save(update_fields=['pipeline_run', 'status', 'current_step', 'step_history', 'updated_at'])

        # Launch Search Scraper Jobs
        scrapers = Scraper.objects.filter(workspace=workspace, is_active=True)
        if not scrapers.exists():
            process.status = 'failed'
            process.error_message = f"No active scrapers configured for workspace '{workspace.name}'."
            process.save(update_fields=['status', 'error_message', 'updated_at'])
            return {"success": False, "error": process.error_message}

        from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job

        for scraper in scrapers:
            query = scraper.search_query
            if config.get("query_prefix"):
                query = f"{config['query_prefix']} {query}"

            comp_run = ComponentRun.objects.create(
                pipeline_run=pipeline_run,
                step_type='search',
                component_name=f"{scraper.provider}_scraper",
                scraper=scraper,
                status='pending',
                input_params={"limit": limit, "search_query": query, "date_range_days": config.get("date_range_days")}
            )
            try:
                comp_run.status = 'running'
                comp_run.save(update_fields=['status'])
                async_res = execute_scraper_run_job.delay(str(comp_run.id), limit=limit)
                comp_run.celery_task_id = async_res.id
                comp_run.save(update_fields=['celery_task_id'])
            except Exception:
                execute_scraper_run_job(str(comp_run.id), limit=limit)

        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Transitioned to 'search'. Launched scraper jobs for PipelineRun '{pipeline_run.id}'."
        }

    pipeline_run = process.pipeline_run
    if not pipeline_run:
        process.status = 'failed'
        process.error_message = "Missing PipelineRun reference."
        process.save(update_fields=['status', 'error_message', 'updated_at'])
        return {"success": False, "error": "Missing PipelineRun reference."}

    # 2. State: SEARCH -> Check completion, launch Step 2 (PDF Download)
    if process.current_step == 'search':
        search_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='search')
        if search_runs.filter(status__in=['pending', 'running']).exists():
            return {"success": True, "status": process.status, "current_step": "search", "message": "Search jobs still running."}

        # Check papers ingested
        papers_count = pipeline_run.papers.count()
        history.append({
            "step": "search",
            "event": "completed",
            "papers_fetched": papers_count,
            "timestamp": timezone.now().isoformat()
        })

        if papers_count == 0:
            logger.warning(f"Agent '{process.name}': 0 papers fetched during search step.")

        # Transition to Download
        pipeline_run.current_stage = 'download'
        pipeline_run.save(update_fields=['current_stage'])

        process.current_step = 'download'
        process.step_history = history
        process.save(update_fields=['current_step', 'step_history', 'updated_at'])

        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type='download',
            component_name="pdf_downloader",
            status='pending',
            input_params={"limit": limit, "pipeline_run_id": str(pipeline_run.id)}
        )

        from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
        try:
            comp_run.status = 'running'
            comp_run.save(update_fields=['status'])
            async_res = execute_pdf_download_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
        except Exception:
            execute_pdf_download_job(str(comp_run.id), limit=limit)

        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Transitioned to 'download'. Launched PDF download job."
        }

    # 3. State: DOWNLOAD -> Check completion, launch Step 3 (OCR if configured) or Step 4 (Screening)
    if process.current_step == 'download':
        download_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='download')
        if download_runs.filter(status__in=['pending', 'running']).exists():
            return {"success": True, "status": process.status, "current_step": "download", "message": "Download jobs still running."}

        history.append({
            "step": "download",
            "event": "completed",
            "timestamp": timezone.now().isoformat()
        })

        # Check if workspace has OCR provider configured (not None and not empty)
        has_ocr_provider = bool(workspace.ocr_provider and str(workspace.ocr_provider).strip().lower() != 'none')

        if has_ocr_provider:
            # Transition to OCR
            pipeline_run.current_stage = 'ocr'
            pipeline_run.save(update_fields=['current_stage'])

            process.current_step = 'ocr'
            process.step_history = history
            process.save(update_fields=['current_step', 'step_history', 'updated_at'])

            comp_run = ComponentRun.objects.create(
                pipeline_run=pipeline_run,
                step_type='ocr',
                component_name=f"{workspace.ocr_provider}_ocr",
                status='pending',
                input_params={"limit": limit, "ocr_provider": workspace.ocr_provider}
            )
            from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
            try:
                comp_run.status = 'running'
                comp_run.save(update_fields=['status'])
                async_res = execute_ocr_job.delay(str(comp_run.id), limit=limit)
                comp_run.celery_task_id = async_res.id
                comp_run.save(update_fields=['celery_task_id'])
            except Exception:
                execute_ocr_job(str(comp_run.id), limit=limit)

            return {
                "success": True,
                "status": process.status,
                "current_step": process.current_step,
                "message": f"Transitioned to 'ocr' using provider '{workspace.ocr_provider}'."
            }
        else:
            # Skip OCR step, transition directly to Screening
            logger.info(f"Agent '{process.name}': OCR provider is None/unconfigured. Skipping OCR step and proceeding to Screening.")
            pipeline_run.current_stage = 'screening'
            pipeline_run.save(update_fields=['current_stage'])

            process.current_step = 'screening'
            process.step_history = history
            process.save(update_fields=['current_step', 'step_history', 'updated_at'])

            _launch_screening_step(process, pipeline_run, workspace, config, limit)
            return {
                "success": True,
                "status": process.status,
                "current_step": process.current_step,
                "message": f"OCR skipped (unconfigured). Transitioned directly to 'screening'."
            }

    # 4. State: OCR -> Check completion, launch Step 4 (Screening)
    if process.current_step == 'ocr':
        ocr_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='ocr')
        if ocr_runs.filter(status__in=['pending', 'running']).exists():
            return {"success": True, "status": process.status, "current_step": "ocr", "message": "OCR jobs still running."}

        history.append({
            "step": "ocr",
            "event": "completed",
            "timestamp": timezone.now().isoformat()
        })

        pipeline_run.current_stage = 'screening'
        pipeline_run.save(update_fields=['current_stage'])

        process.current_step = 'screening'
        process.step_history = history
        process.save(update_fields=['current_step', 'step_history', 'updated_at'])

        _launch_screening_step(process, pipeline_run, workspace, config, limit)
        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Transitioned to 'screening'."
        }

    # 5. State: SCREENING -> Check completion, launch Step 5 (Extraction)
    if process.current_step == 'screening':
        screening_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='screening')
        if screening_runs.filter(status__in=['pending', 'running']).exists():
            return {"success": True, "status": process.status, "current_step": "screening", "message": "Screening jobs still running."}

        history.append({
            "step": "screening",
            "event": "completed",
            "timestamp": timezone.now().isoformat()
        })

        pipeline_run.current_stage = 'extraction'
        pipeline_run.save(update_fields=['current_stage'])

        process.current_step = 'extraction'
        process.step_history = history
        process.save(update_fields=['current_step', 'step_history', 'updated_at'])

        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type='extraction',
            component_name="parameter_extraction",
            status='pending',
            input_params={"limit": limit}
        )

        from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job
        try:
            comp_run.status = 'running'
            comp_run.save(update_fields=['status'])
            async_res = execute_extraction_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
        except Exception:
            execute_extraction_job(str(comp_run.id), limit=limit)

        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Transitioned to 'extraction'."
        }

    # 6. State: EXTRACTION -> Check completion, mark COMPLETED
    if process.current_step == 'extraction':
        extraction_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='extraction')
        if extraction_runs.filter(status__in=['pending', 'running']).exists():
            return {"success": True, "status": process.status, "current_step": "extraction", "message": "Extraction jobs still running."}

        history.append({
            "step": "extraction",
            "event": "completed",
            "timestamp": timezone.now().isoformat()
        })

        pipeline_run.status = 'completed'
        pipeline_run.current_stage = 'completed'
        pipeline_run.completed_at = timezone.now()
        pipeline_run.save(update_fields=['status', 'current_stage', 'completed_at'])

        process.status = 'completed'
        process.current_step = 'completed'
        process.completed_at = timezone.now()
        process.step_history = history
        process.save(update_fields=['status', 'current_step', 'completed_at', 'step_history', 'updated_at'])

        _send_agent_notification(process)

        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Research Agent process '{process.name}' completed full pipeline cycle successfully!"
        }

    return {"success": True, "status": process.status, "current_step": process.current_step, "message": "No action required."}


def _launch_screening_step(process, pipeline_run, workspace, config, limit):
    skip_abstract = config.get("skip_abstract_screening", workspace.skip_abstract_screening)
    comp_name = "full_text_screening" if skip_abstract else "abstract_screening"

    comp_run = ComponentRun.objects.create(
        pipeline_run=pipeline_run,
        step_type='screening',
        component_name=comp_name,
        status='pending',
        input_params={"limit": limit, "skip_abstract_screening": skip_abstract}
    )

    if skip_abstract:
        from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
        func = execute_full_text_screening_job
    else:
        from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
        func = execute_screening_job

    try:
        comp_run.status = 'running'
        comp_run.save(update_fields=['status'])
        async_res = func.delay(str(comp_run.id), limit=limit)
        comp_run.celery_task_id = async_res.id
        comp_run.save(update_fields=['celery_task_id'])
    except Exception:
        func(str(comp_run.id), limit=limit)


@shared_task(bind=True)
def run_agent_process_tick(self, process_id: str):
    """
    Celery task that executes a single state transition tick for a ResearchAgentProcess.
    """
    return tick_agent_process(process_id)
