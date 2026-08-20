import logging
import time
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections
from research_intelligence.models import Workspace, PipelineRun, ComponentRun, ResearchAgentProcess, Scraper

logger = logging.getLogger(__name__)


def notify_pipeline_orchestrator_tick(pipeline_run_id_or_obj):
    """
    Called whenever a ComponentRun finishes to trigger the autonomous state machine
    for any running ResearchAgentProcesses attached to this PipelineRun.
    """
    if not pipeline_run_id_or_obj:
        return
    try:
        if isinstance(pipeline_run_id_or_obj, str):
            pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id_or_obj)
        else:
            pipeline_run = pipeline_run_id_or_obj

        running_agents = list(pipeline_run.agent_processes.filter(status='running'))
        if running_agents:
            for agent_proc in running_agents:
                try:
                    run_agent_process_tick.delay(str(agent_proc.id))
                except Exception:
                    # If Celery queueing fails or in sync environment, tick directly
                    try:
                        tick_agent_process(str(agent_proc.id))
                    except Exception as sync_err:
                        logger.warning(f"Fallback tick execution failed for agent '{agent_proc.id}': {sync_err}")
        else:
            # Check if all component runs are done for this pipeline run
            pending_runs = pipeline_run.component_runs.filter(status__in=['pending', 'running'])
            if not pending_runs.exists() and pipeline_run.component_runs.filter(status='completed').exists():
                last_comp = pipeline_run.component_runs.order_by('-completed_at', '-id').first()
                if last_comp and last_comp.step_type in ['signal_score', 'extraction']:
                    pipeline_run.status = 'completed'
                    pipeline_run.current_stage = 'completed'
                    if not pipeline_run.completed_at:
                        pipeline_run.completed_at = timezone.now()
                    pipeline_run.save(update_fields=['status', 'current_stage', 'completed_at'])
    except Exception as e:
        logger.warning(f"Failed to notify orchestrator tick: {e}")


def _send_agent_notification(agent_process: ResearchAgentProcess):
    """
    Sends an email notification with formatted metrics when an agent process completes or fails.
    Notifies all workspace active subscribers, workspace member users, and any explicit override email.
    """
    recipients = set()

    # Explicit override in config or workspace setting
    override_email = (
        agent_process.configuration_override.get("notification_email")
        or agent_process.workspace.notification_email
    )
    if override_email:
        recipients.add(override_email.strip())

    # Workspace Members
    from research_intelligence.models import WorkspaceMember, Paper, Extraction
    memberships = WorkspaceMember.objects.filter(workspace=agent_process.workspace).select_related('user')
    for m in memberships:
        if m.user and m.user.email:
            recipients.add(m.user.email.strip())

    # Workspace Subscribers
    subscribers = agent_process.workspace.subscribers.filter(is_active=True)
    for s in subscribers:
        if s.email:
            recipients.add(s.email.strip())

    title = agent_process.name
    ws_name = agent_process.workspace.name
    status = agent_process.status
    pr = agent_process.pipeline_run
    pr_id = str(pr.id) if pr else "N/A"

    recipient_list = sorted(list(recipients))
    if not recipient_list:
        logger.info(f"📧 [NOTIFICATION] No recipients/subscribers found for Workspace '{ws_name}'.")
        return

    subject = f"[{status.upper()}] Research Intelligence Pipeline: {title} ({ws_name})"

    # Calculate metrics
    papers_count = Paper.objects.filter(pipeline_run=pr).count() if pr else 0
    passed_count = Paper.objects.filter(pipeline_run=pr, screening_status__in=['abstract_passed', 'full_text_passed']).count() if pr else 0
    extractions_count = Extraction.objects.filter(paper__pipeline_run=pr).count() if pr else 0
    tokens_in = pr.tokens_in if pr else 0
    tokens_out = pr.tokens_out if pr else 0
    usd_cost = float(pr.usd_cost) if pr else 0.0

    plain_message = (
        f"Schwarz Research Intelligence - Pipeline Execution Report\n"
        f"===========================================================\n"
        f"Workspace: {ws_name}\n"
        f"Agent Name: {title}\n"
        f"Status: {status.upper()}\n"
        f"Pipeline Run ID: {pr_id}\n\n"
        f"Execution Metrics:\n"
        f"- Papers Fetched: {papers_count}\n"
        f"- Papers Passed Screening: {passed_count}\n"
        f"- Extractions Created: {extractions_count}\n"
        f"- Tokens Consumed: {tokens_in + tokens_out:,} (In: {tokens_in:,}, Out: {tokens_out:,})\n"
        f"- Total Cost (USD): ${usd_cost:.4f}\n"
    )

    if agent_process.error_message:
        plain_message += f"\nError Details:\n{agent_process.error_message}\n"

    error_html = (
        f"<div style='margin-top: 15px; padding: 10px; background-color: #f8d7da; color: #721c24; border-radius: 4px;'>"
        f"<strong>Error:</strong> {agent_process.error_message}</div>"
        if agent_process.error_message else ""
    )
    status_color = "#198754" if status == "completed" else "#dc3545"

    html_message = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: {status_color}; margin-top: 0;">
            Research Agent {status.upper()}
        </h2>
        <p><strong>Workspace:</strong> {ws_name}</p>
        <p><strong>Agent Name:</strong> {title}</p>
        <p><strong>Pipeline Run ID:</strong> <code>{pr_id}</code></p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
        <h3 style="color: #333;">Pipeline Summary</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 6px 0; color: #666;">Papers Fetched:</td><td style="padding: 6px 0; font-weight: bold;">{papers_count}</td></tr>
            <tr><td style="padding: 6px 0; color: #666;">Passed Screening:</td><td style="padding: 6px 0; font-weight: bold;">{passed_count}</td></tr>
            <tr><td style="padding: 6px 0; color: #666;">Extractions Created:</td><td style="padding: 6px 0; font-weight: bold;">{extractions_count}</td></tr>
            <tr><td style="padding: 6px 0; color: #666;">Token Usage:</td><td style="padding: 6px 0; font-weight: bold;">{tokens_in + tokens_out:,} (In: {tokens_in:,}, Out: {tokens_out:,})</td></tr>
            <tr><td style="padding: 6px 0; color: #666;">Estimated Cost:</td><td style="padding: 6px 0; font-weight: bold; color: #0d6efd;">${usd_cost:.4f} USD</td></tr>
        </table>
        {error_html}
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
        <p style="font-size: 12px; color: #999;">Automated notification from Schwarz Research Intelligence Platform.</p>
    </div>
    """

    try:
        from django.core.mail import send_mail
        from django.conf import settings
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@schwarz-digits.cloud')
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False
        )
        logger.info(f"📧 [EMAIL NOTIFICATION SENT] To: [{', '.join(recipient_list)}] | Subject: '{subject}'")
    except Exception as mail_err:
        logger.warning(f"⚠️ Failed to send notification email: {mail_err}")


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
        reprocess_existing = config.get("reprocess_existing", False)
        pipeline_run = PipelineRun.objects.create(
            workspace=workspace,
            status='running',
            current_stage='search',
            reprocess_existing=reprocess_existing,
            triggered_by=process.triggered_by
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
                status='running',
                input_params={"limit": limit, "search_query": query, "date_range_days": config.get("date_range_days")}
            )
            try:
                async_res = execute_scraper_run_job.delay(str(comp_run.id), limit=limit)
                comp_run.celery_task_id = async_res.id
                comp_run.save(update_fields=['celery_task_id'])
            except Exception as e:
                logger.warning(f"Failed to queue scraper job async, executing synchronously: {e}")
                execute_scraper_run_job(str(comp_run.id), limit=limit)
                comp_run.refresh_from_db()

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

        # Check for failures in search component runs
        failed_search_runs = search_runs.filter(status='failed')
        if failed_search_runs.exists():
            error_msg = "; ".join([r.error_message for r in failed_search_runs if r.error_message]) or "Search scraper job failed."
            logger.error(f"Agent '{process.name}': Search failed with error: {error_msg}")
            process.status = 'failed'
            process.error_message = error_msg
            process.completed_at = timezone.now()
            history.append({
                "step": "search",
                "event": "failed",
                "error": error_msg,
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['status', 'error_message', 'completed_at', 'step_history', 'updated_at'])

            pipeline_run.status = 'failed'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])
            return {"success": False, "status": "failed", "error": error_msg}

        # Check papers ingested
        papers_count = pipeline_run.papers.count()
        reprocess_existing = config.get("reprocess_existing", getattr(pipeline_run, "reprocess_existing", False))
        if papers_count == 0:
            from research_intelligence.models import Paper
            if reprocess_existing:
                ws_papers = Paper.objects.filter(workspace=workspace)
                if ws_papers.exists():
                    ws_papers.update(pipeline_run=pipeline_run)
                    papers_count = pipeline_run.papers.count()
                    logger.info(f"Agent '{process.name}': reprocess_existing=True. Linked {papers_count} existing workspace paper(s) to this run.")
            else:
                # Check if pending papers exist in workspace (e.g. from prior ingestion or deduplication)
                pending_ws_papers = Paper.objects.filter(workspace=workspace, screening_status='pending')
                if pending_ws_papers.exists():
                    pending_ws_papers.update(pipeline_run=pipeline_run)
                    papers_count = pipeline_run.papers.count()

        history.append({
            "step": "search",
            "event": "completed",
            "papers_fetched": papers_count,
            "timestamp": timezone.now().isoformat()
        })

        if papers_count == 0:
            msg = f"Search completed but 0 papers were found matching criteria for workspace '{workspace.name}'. Halting pipeline."
            logger.warning(f"Agent '{process.name}': {msg}")
            process.status = 'completed'
            process.current_step = 'completed'
            process.completed_at = timezone.now()
            history.append({
                "step": "search",
                "event": "halted_zero_papers",
                "papers_fetched": 0,
                "message": msg,
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['status', 'current_step', 'completed_at', 'step_history', 'updated_at'])

            pipeline_run.status = 'completed'
            pipeline_run.current_stage = 'completed'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'current_stage', 'completed_at'])

            _send_agent_notification(process)
            return {"success": True, "status": "completed", "current_step": "completed", "message": msg}

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
            status='running',
            input_params={"limit": limit, "pipeline_run_id": str(pipeline_run.id)}
        )

        from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
        try:
            async_res = execute_pdf_download_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
        except Exception as e:
            logger.warning(f"Failed to queue pdf download async, executing synchronously: {e}")
            execute_pdf_download_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()

        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Transitioned to 'download'. Launched PDF download job for {papers_count} paper(s)."
        }

    # 3. State: DOWNLOAD -> Check completion, launch Step 3 (OCR if configured) or Step 4 (Screening)
    if process.current_step == 'download':
        download_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='download')
        if download_runs.filter(status__in=['pending', 'running']).exists():
            return {"success": True, "status": process.status, "current_step": "download", "message": "Download jobs still running."}

        failed_dl_runs = download_runs.filter(status='failed')
        if failed_dl_runs.exists() and not download_runs.filter(status='completed').exists():
            error_msg = "; ".join([r.error_message for r in failed_dl_runs if r.error_message]) or "PDF download job failed."
            logger.error(f"Agent '{process.name}': Download failed with error: {error_msg}")
            process.status = 'failed'
            process.error_message = error_msg
            process.completed_at = timezone.now()
            history.append({
                "step": "download",
                "event": "failed",
                "error": error_msg,
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['status', 'error_message', 'completed_at', 'step_history', 'updated_at'])

            pipeline_run.status = 'failed'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])
            return {"success": False, "status": "failed", "error": error_msg}

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
                status='running',
                input_params={"limit": limit, "ocr_provider": workspace.ocr_provider}
            )
            from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
            try:
                async_res = execute_ocr_job.delay(str(comp_run.id), limit=limit)
                comp_run.celery_task_id = async_res.id
                comp_run.save(update_fields=['celery_task_id'])
            except Exception as e:
                logger.warning(f"Failed to queue OCR async, executing synchronously: {e}")
                execute_ocr_job(str(comp_run.id), limit=limit)
                comp_run.refresh_from_db()

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

        failed_ocr_runs = ocr_runs.filter(status='failed')
        if failed_ocr_runs.exists() and not ocr_runs.filter(status='completed').exists():
            error_msg = "; ".join([r.error_message for r in failed_ocr_runs if r.error_message]) or "OCR conversion job failed."
            logger.error(f"Agent '{process.name}': OCR failed with error: {error_msg}")
            process.status = 'failed'
            process.error_message = error_msg
            process.completed_at = timezone.now()
            history.append({
                "step": "ocr",
                "event": "failed",
                "error": error_msg,
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['status', 'error_message', 'completed_at', 'step_history', 'updated_at'])

            pipeline_run.status = 'failed'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])
            return {"success": False, "status": "failed", "error": error_msg}

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

        failed_scr_runs = screening_runs.filter(status='failed')
        if failed_scr_runs.exists() and not screening_runs.filter(status='completed').exists():
            error_msg = "; ".join([r.error_message for r in failed_scr_runs if r.error_message]) or "Screening job failed."
            logger.error(f"Agent '{process.name}': Screening failed with error: {error_msg}")
            process.status = 'failed'
            process.error_message = error_msg
            process.completed_at = timezone.now()
            history.append({
                "step": "screening",
                "event": "failed",
                "error": error_msg,
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['status', 'error_message', 'completed_at', 'step_history', 'updated_at'])

            pipeline_run.status = 'failed'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])
            return {"success": False, "status": "failed", "error": error_msg}

        # Check if 2-stage screening: abstract completed, full_text not yet run
        has_abstract_run = screening_runs.filter(component_name__icontains='abstract').exists()
        has_full_text_run = screening_runs.filter(component_name__icontains='full_text').exists()

        if has_abstract_run and not has_full_text_run:
            from research_intelligence.models import Paper
            abstract_run = screening_runs.filter(component_name__icontains='abstract').first()
            abstract_passed = abstract_run.metrics.get('passed', 0) if (abstract_run and abstract_run.metrics) else Paper.objects.filter(pipeline_run=pipeline_run, screening_status='abstract_passed').count()
            abstract_screened = abstract_run.metrics.get('total_screened', 0) if (abstract_run and abstract_run.metrics) else pipeline_run.papers.count()
            abstract_rejected = abstract_run.metrics.get('rejected', 0) if (abstract_run and abstract_run.metrics) else (abstract_screened - abstract_passed)

            history.append({
                "step": "abstract_screening",
                "event": "completed",
                "total_screened": abstract_screened,
                "passed": abstract_passed,
                "rejected": abstract_rejected,
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['step_history', 'updated_at'])

            if abstract_passed > 0:
                logger.info(f"Agent '{process.name}': Abstract Screening completed ({abstract_passed}/{abstract_screened} passed). Launching Stage 4b: Full-Text Screening.")
                comp_run = ComponentRun.objects.create(
                    pipeline_run=pipeline_run,
                    step_type='screening',
                    component_name="full_text_screening",
                    status='running',
                    input_params={"limit": limit, "stage": "full_text"}
                )
                from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
                try:
                    async_res = execute_full_text_screening_job.delay(str(comp_run.id), limit=limit)
                    comp_run.celery_task_id = async_res.id
                    comp_run.save(update_fields=['celery_task_id'])
                except Exception as e:
                    logger.warning(f"Failed to queue full-text screening async, executing synchronously: {e}")
                    execute_full_text_screening_job(str(comp_run.id), limit=limit)
                    comp_run.refresh_from_db()

                return {
                    "success": True,
                    "status": process.status,
                    "current_step": "screening",
                    "message": f"Stage 4a (Abstract Screening) completed ({abstract_passed} passed). Launched Stage 4b (Full-Text Screening)."
                }
            else:
                logger.info(f"Agent '{process.name}': 0 papers passed Abstract Screening. Skipping Full-Text Screening and proceeding to Extraction.")

        # If screening stage(s) completed, record completion in history
        from research_intelligence.models import Paper
        final_screening_run = screening_runs.filter(component_name__icontains='full_text').first() or screening_runs.first()
        ft_passed = final_screening_run.metrics.get('passed', 0) if (final_screening_run and final_screening_run.metrics) else Paper.objects.filter(pipeline_run=pipeline_run, screening_status='full_text_passed').count()
        ft_screened = final_screening_run.metrics.get('total_screened', 0) if (final_screening_run and final_screening_run.metrics) else 0
        ft_rejected = final_screening_run.metrics.get('rejected', 0) if (final_screening_run and final_screening_run.metrics) else (ft_screened - ft_passed)

        history.append({
            "step": "full_text_screening" if has_full_text_run else "screening",
            "event": "completed",
            "total_screened": ft_screened,
            "passed": ft_passed,
            "rejected": ft_rejected,
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
            status='running',
            input_params={"limit": limit}
        )

        from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job
        try:
            async_res = execute_extraction_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
        except Exception as e:
            logger.warning(f"Failed to queue extraction async, executing synchronously: {e}")
            execute_extraction_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()

        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Screening completed. Transitioned to 'extraction'."
        }

    # 6. State: EXTRACTION -> Check completion, transition to Signal Score
    if process.current_step == 'extraction':
        extraction_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='extraction')
        if extraction_runs.filter(status__in=['pending', 'running']).exists():
            return {"success": True, "status": process.status, "current_step": "extraction", "message": "Extraction jobs still running."}

        failed_ext_runs = extraction_runs.filter(status='failed')
        if failed_ext_runs.exists() and not extraction_runs.filter(status='completed').exists():
            error_msg = "; ".join([r.error_message for r in failed_ext_runs if r.error_message]) or "Parameter extraction job failed."
            logger.error(f"Agent '{process.name}': Extraction failed with error: {error_msg}")
            process.status = 'failed'
            process.error_message = error_msg
            process.completed_at = timezone.now()
            history.append({
                "step": "extraction",
                "event": "failed",
                "error": error_msg,
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['status', 'error_message', 'completed_at', 'step_history', 'updated_at'])

            pipeline_run.status = 'failed'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])
            return {"success": False, "status": "failed", "error": error_msg}

        history.append({
            "step": "extraction",
            "event": "completed",
            "timestamp": timezone.now().isoformat()
        })

        pipeline_run.current_stage = 'signal_score'
        pipeline_run.save(update_fields=['current_stage'])

        process.current_step = 'signal_score'
        process.step_history = history
        process.save(update_fields=['current_step', 'step_history', 'updated_at'])

        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type='signal_score',
            component_name="signal_score_evaluation",
            status='running',
            input_params={"limit": limit}
        )

        from research_intelligence.tasks.step_6_signal_score.scorer import execute_signal_score_job
        try:
            async_res = execute_signal_score_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])
        except Exception as e:
            logger.warning(f"Failed to queue signal score async, executing synchronously: {e}")
            execute_signal_score_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()

        return {
            "success": True,
            "status": process.status,
            "current_step": process.current_step,
            "message": f"Extraction completed. Transitioned to 'signal_score' (Step 6)."
        }

    # 7. State: SIGNAL_SCORE -> Check completion, mark COMPLETED
    if process.current_step == 'signal_score':
        signal_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='signal_score')
        if signal_runs.filter(status__in=['pending', 'running']).exists():
            return {"success": True, "status": process.status, "current_step": "signal_score", "message": "Signal score calculation jobs still running."}

        failed_sig_runs = signal_runs.filter(status='failed')
        if failed_sig_runs.exists() and not signal_runs.filter(status='completed').exists():
            error_msg = "; ".join([r.error_message for r in failed_sig_runs if r.error_message]) or "Signal score evaluation job failed."
            logger.error(f"Agent '{process.name}': Signal scoring failed with error: {error_msg}")
            process.status = 'failed'
            process.error_message = error_msg
            process.completed_at = timezone.now()
            history.append({
                "step": "signal_score",
                "event": "failed",
                "error": error_msg,
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['status', 'error_message', 'completed_at', 'step_history', 'updated_at'])

            pipeline_run.status = 'failed'
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])
            return {"success": False, "status": "failed", "error": error_msg}

        history.append({
            "step": "signal_score",
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
            "message": f"Research Agent process '{process.name}' completed full pipeline cycle (with Step 6 Signal Scoring) successfully!"
        }

    return {"success": True, "status": process.status, "current_step": process.current_step, "message": "No action required."}


def _launch_screening_step(process, pipeline_run, workspace, config, limit):
    skip_abstract = config.get("skip_abstract_screening", workspace.skip_abstract_screening)
    comp_name = "full_text_screening" if skip_abstract else "abstract_screening"

    comp_run = ComponentRun.objects.create(
        pipeline_run=pipeline_run,
        step_type='screening',
        component_name=comp_name,
        status='running',
        input_params={"limit": limit, "skip_abstract_screening": skip_abstract}
    )

    if skip_abstract:
        from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
        func = execute_full_text_screening_job
    else:
        from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
        func = execute_screening_job

    try:
        async_res = func.delay(str(comp_run.id), limit=limit)
        comp_run.celery_task_id = async_res.id
        comp_run.save(update_fields=['celery_task_id'])
    except Exception as e:
        logger.warning(f"Failed to queue screening async, executing synchronously: {e}")
        func(str(comp_run.id), limit=limit)
        comp_run.refresh_from_db()


@shared_task(bind=True)
def run_agent_process_tick(self, process_id: str):
    """
    Celery task that executes a single state transition tick for a ResearchAgentProcess.
    """
    return tick_agent_process(process_id)
