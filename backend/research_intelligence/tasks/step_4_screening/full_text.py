import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery import shared_task
from django.db.models import Q
from django.db import connection, close_old_connections
from django.core.files.storage import default_storage
from django.utils import timezone
from ...models import Workspace, Paper, ComponentRun
from ...llm_providers import get_llm_provider

logger = logging.getLogger(__name__)


@shared_task
def screen_full_text(paper_id, workspace_id, workspace_obj=None, paper_obj=None):
    """
    Screens full paper content (OCR Markdown if present, PDF binary if available, or abstract fallback)
    against workspace inclusion/exclusion criteria using the configured screening LLM.
    Returns a dictionary with screening status, reasoning, evidence quotes, input source, and token usage.
    """
    try:
        workspace = workspace_obj or Workspace.objects.get(pk=workspace_id)
        paper = paper_obj or Paper.objects.get(pk=paper_id)
    except (Workspace.DoesNotExist, Paper.DoesNotExist) as e:
        logger.error(f"Failed to find workspace {workspace_id} or paper {paper_id}: {str(e)}")
        return {"success": False, "error": str(e)}

    t0 = time.time()

    # Check if paper is marked as withdrawn
    if paper.screening_status == 'withdrawn':
        duration_sec = round(time.time() - t0, 3)
        return {
            "success": True,
            "passed": False,
            "screening_status": "withdrawn",
            "reasoning": paper.screening_reasoning or "Paper has been withdrawn by authors.",
            "evidence_quotes": [],
            "decision_category": "WITHDRAWN",
            "input_source": "withdrawn",
            "duration_seconds": duration_sec,
            "usage": {"tokens_in": 0, "tokens_out": 0, "total_tokens": 0}
        }

    provider = get_llm_provider(workspace.llm_provider)

    # Resolve input source: 1. OCR Markdown text, 2. Multimodal PDF binary, 3. Abstract text
    md_text = None
    pdf_bytes = None
    input_source = "abstract_fallback"

    # Priority 1: Check for converted OCR Markdown
    if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
        try:
            with default_storage.open(paper.converted_md_path, 'rb') as f:
                raw_content = f.read()
            md_text = raw_content.decode("utf-8", errors="replace") if isinstance(raw_content, bytes) else str(raw_content)
            input_source = "markdown_ocr"
        except Exception as e:
            logger.warning(f"Failed reading converted MD from {paper.converted_md_path} for paper {paper_id}: {e}")

    # Priority 2: Check for original PDF binary
    if not md_text and paper.original_pdf_path and default_storage.exists(paper.original_pdf_path):
        try:
            with default_storage.open(paper.original_pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            input_source = "multimodal_pdf"
        except Exception as e:
            logger.warning(f"Failed reading PDF binary from {paper.original_pdf_path} for paper {paper_id}: {e}")

    # Resolve dynamic workspace prompt templates and schemas
    system_prompt = workspace.get_full_text_screening_system_prompt()
    user_prompt_template = workspace.get_full_text_screening_user_prompt_template()
    acceptance = workspace.get_full_text_acceptance_criteria() or "Relevant AI research"
    rejection = workspace.get_full_text_rejection_criteria() or "Out of domain"
    response_schema = workspace.get_full_text_screening_response_schema()
    exit_metric_key = workspace.get_full_text_screening_exit_metric()

    gen_kwargs = {
        "system_instruction": system_prompt,
        "response_schema": response_schema,
        "model": workspace.screening_llm_model,
        "reasoning_effort": getattr(workspace, 'reasoning_effort', 'medium'),
        "return_usage": True
    }

    if md_text:
        # Pass truncated Markdown document to prompt
        try:
            user_prompt = user_prompt_template.format(
                title=paper.title,
                full_text=md_text[:120000],
                abstract=paper.abstract or "",
                acceptance_criteria=acceptance,
                rejection_criteria=rejection,
                paper_title=paper.title,
                paper_text=md_text[:120000]
            )
        except Exception:
            user_prompt = (
                f"Title: {paper.title}\n\n"
                f"Full-Text Markdown Content:\n{md_text[:120000]}\n\n"
                f"Acceptance Criteria (must satisfy to pass):\n{acceptance}\n\n"
                f"Rejection Criteria (if matched, paper is rejected):\n{rejection}"
            )
        gen_kwargs["prompt"] = user_prompt
    elif pdf_bytes:
        # Pass PDF binary directly to Google GenAI multimodal engine
        try:
            user_prompt = user_prompt_template.format(
                title=paper.title,
                full_text="Please analyze the attached PDF document for full-text screening.",
                abstract=paper.abstract or "",
                acceptance_criteria=acceptance,
                rejection_criteria=rejection,
                paper_title=paper.title,
                paper_text="Please analyze the attached PDF document for full-text screening."
            )
        except Exception:
            user_prompt = (
                f"Title: {paper.title}\n\n"
                f"Please analyze the attached PDF document for full-text screening.\n\n"
                f"Acceptance Criteria (must satisfy to pass):\n{acceptance}\n\n"
                f"Rejection Criteria (if matched, paper is rejected):\n{rejection}"
            )
        gen_kwargs["prompt"] = user_prompt
        gen_kwargs["pdf_bytes"] = pdf_bytes
        gen_kwargs["mime_type"] = "application/pdf"
    else:
        # Fallback to abstract text if full content is unavailable
        try:
            user_prompt = user_prompt_template.format(
                title=paper.title,
                full_text=f"Abstract (Full-Text/PDF unavailable):\n{paper.abstract}",
                abstract=paper.abstract or "",
                acceptance_criteria=acceptance,
                rejection_criteria=rejection,
                paper_title=paper.title,
                paper_text=paper.abstract or ""
            )
        except Exception:
            user_prompt = (
                f"Title: {paper.title}\n\n"
                f"Abstract (Full-Text/PDF unavailable):\n{paper.abstract}\n\n"
                f"Acceptance Criteria (must satisfy to pass):\n{acceptance}\n\n"
                f"Rejection Criteria (if matched, paper is rejected):\n{rejection}"
            )
        gen_kwargs["prompt"] = user_prompt

    max_attempts = 3
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            gen_res = provider.generate(**gen_kwargs)

            if isinstance(gen_res, tuple) and len(gen_res) == 2:
                response, raw_usage = gen_res
            else:
                response, raw_usage = gen_res, {}

            p_tok = raw_usage.get("prompt_tokens", 0) or 0
            c_tok = raw_usage.get("candidates_tokens", 0) or 0
            t_tok = raw_usage.get("total_tokens", 0) or (p_tok + c_tok)

            usage = {
                "tokens_in": p_tok,
                "tokens_out": c_tok,
                "total_tokens": t_tok
            }

            parsed = response if isinstance(response, dict) else {}
            passed = parsed.get("passed", False)
            if "passed" not in parsed:
                dec_cat = str(parsed.get("decision_category", "")).lower()
                passed = ("accept" in dec_cat or "pass" in dec_cat)

            reasoning = parsed.get("reasoning", "") or str(response)
            evidence_quotes = parsed.get("evidence_quotes", [])
            decision_category = parsed.get("decision_category", "ACCEPTED" if passed else "REJECTED")

            exit_metric_val = parsed.get(exit_metric_key)
            if exit_metric_val is None:
                exit_metric_val = decision_category

            paper.screening_status = "full_text_passed" if passed else "rejected"
            paper.screening_reasoning = reasoning
            paper.save(update_fields=['screening_status', 'screening_reasoning'])

            # Store dynamic full-text output in PaperMetric if pipeline_run is present
            if paper.pipeline_run_id:
                try:
                    from ...models import PaperMetric
                    pm, _ = PaperMetric.objects.get_or_create(
                        paper=paper,
                        pipeline_run_id=paper.pipeline_run_id,
                        defaults={"workspace": workspace}
                    )
                    m_data = pm.metrics_data or {}
                    m_data["full_text_screening"] = {
                        "passed": passed,
                        "reasoning": reasoning,
                        "evidence_quotes": evidence_quotes,
                        "decision_category": decision_category,
                        "exit_metric_key": exit_metric_key,
                        "exit_metric_value": exit_metric_val,
                        "input_source": input_source,
                        "dynamic_data": parsed
                    }
                    pm.metrics_data = m_data
                    pm.save(update_fields=['metrics_data'])
                except Exception as pm_err:
                    logger.warning(f"Could not record PaperMetric for paper {paper.id}: {pm_err}")

            duration_sec = round(time.time() - t0, 3)

            return {
                "success": True,
                "passed": passed,
                "screening_status": paper.screening_status,
                "reasoning": reasoning,
                "evidence_quotes": evidence_quotes,
                "decision_category": decision_category,
                "exit_metric_key": exit_metric_key,
                "exit_metric_value": exit_metric_val,
                "dynamic_data": parsed,
                "input_source": input_source,
                "duration_seconds": duration_sec,
                "usage": usage
            }
        except Exception as e:
            last_error = e
            if attempt < max_attempts:
                delay = (2 ** attempt) + (0.1 * attempt)
                logger.warning(f"⚠️ [RETRY {attempt}/{max_attempts}] Paper '{paper.id}' ({paper.title[:30]}...) full-text screening failed: {str(e)}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                duration_sec = round(time.time() - t0, 3)
                logger.exception(f"Error screening full text for paper {paper_id} after {max_attempts} attempts: {str(e)}")
                return {
                    "success": False,
                    "error": str(e),
                    "input_source": input_source,
                    "duration_seconds": duration_sec,
                    "usage": {"tokens_in": 0, "tokens_out": 0, "total_tokens": 0}
                }


def _screen_full_text_paper_task(paper, workspace_obj):
    close_old_connections()
    res = screen_full_text(paper.id, workspace_obj.id, workspace_obj=workspace_obj, paper_obj=paper)
    return paper, res


@shared_task(bind=True)
def execute_full_text_screening_job(self, component_run_id: str, limit: int = None, max_workers: int = 4):
    """
    Celery worker task executing Full-Text Screening for papers in a ComponentRun job.
    Executes paper evaluations concurrently using a ThreadPoolExecutor.
    """
    component_run = None
    for attempt in range(4):
        try:
            close_old_connections()
            component_run = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').get(pk=component_run_id)
            break
        except ComponentRun.DoesNotExist:
            if attempt < 3:
                time.sleep(0.5)
            else:
                logger.error(f"ComponentRun '{component_run_id}' not found after 4 attempts.")
                return False

    pipeline_run = component_run.pipeline_run
    workspace = pipeline_run.workspace

    component_run.status = 'running'
    component_run.celery_task_id = getattr(self.request, 'id', None)
    component_run.started_at = timezone.now()
    component_run.completed_at = None
    component_run.error_message = ''
    component_run.save(update_fields=['status', 'celery_task_id', 'started_at', 'completed_at', 'error_message'])

    job_t0 = time.time()
    worker_concurrency = int(os.environ.get("SCREENING_PARALLEL_WORKERS", max_workers))

    # SQLite (used in unit tests) does not support multi-threaded write locks
    if connection.vendor == 'sqlite':
        worker_concurrency = 1

    try:
        # Determine paper subset to screen based on pipeline history:
        # 1. If an Abstract Screening component run exists, target 'abstract_passed' papers.
        # 2. Otherwise, target non-withdrawn papers with downloaded PDFs or converted OCR MDs.
        has_abstract_screening_run = ComponentRun.objects.filter(
            pipeline_run=pipeline_run,
            step_type='screening',
            component_name__icontains='abstract'
        ).exists()

        if has_abstract_screening_run:
            papers_qs = Paper.objects.filter(pipeline_run=pipeline_run, screening_status='abstract_passed')
            if not papers_qs.exists():
                papers_qs = Paper.objects.filter(pipeline_run=pipeline_run).exclude(screening_status__in=['rejected', 'withdrawn'])
            logger.info(f"🔍 [FULL-TEXT SCREENING FILTER] Prior Abstract Screening job detected. Targeting {papers_qs.count()} papers with status='abstract_passed'.")
        else:
            from django.db.models import Q
            papers_qs = Paper.objects.filter(
                pipeline_run=pipeline_run
            ).exclude(
                screening_status='withdrawn'
            ).filter(
                Q(original_pdf_path__isnull=False) | Q(converted_md_path__isnull=False)
            )
            if not papers_qs.exists():
                papers_qs = Paper.objects.filter(pipeline_run=pipeline_run).exclude(screening_status='withdrawn')
            logger.info(f"🔍 [FULL-TEXT SCREENING FILTER] No prior Abstract Screening job found. Targeting {papers_qs.count()} downloaded/OCR papers.")

        papers = list(papers_qs[:limit] if (limit and limit > 0) else papers_qs)
        passed_count = 0
        rejected_count = 0
        withdrawn_count = 0
        failed_count = 0
        total_prompt_tokens = 0
        total_candidates_tokens = 0
        total_tokens = 0
        papers_summary = []

        logger.info(f"🚀 [PARALLEL FULL-TEXT SCREENING START] Processing {len(papers)} papers using {worker_concurrency} parallel threads...")

        def _record_result(paper, res):
            nonlocal passed_count, rejected_count, withdrawn_count, failed_count
            nonlocal total_prompt_tokens, total_candidates_tokens, total_tokens

            title_snippet = paper.title[:50] if paper.title else "Untitled"
            if res.get("success"):
                status = res.get("screening_status")
                usage = res.get("usage", {})
                duration_sec = res.get("duration_seconds", 0.0)
                src = res.get("input_source", "unknown")
                p_tok = usage.get("tokens_in", 0)
                c_tok = usage.get("tokens_out", 0)
                t_tok = usage.get("total_tokens", 0) or (p_tok + c_tok)

                total_prompt_tokens += p_tok
                total_candidates_tokens += c_tok
                total_tokens += t_tok

                if status == "full_text_passed":
                    passed_count += 1
                    logger.info(f"✅ [FULL-TEXT PASSED] Paper '{title_snippet}...' (src: {src}) | Time: {duration_sec}s | Tokens: {t_tok} | Reasoning: {res.get('reasoning')}")
                elif status == "withdrawn":
                    withdrawn_count += 1
                    logger.info(f"⏭️ [WITHDRAWN] Paper '{title_snippet}...' | Time: {duration_sec}s | Reason: {res.get('reasoning')}")
                else:
                    rejected_count += 1
                    logger.info(f"❌ [FULL-TEXT REJECTED] Paper '{title_snippet}...' (src: {src}) | Time: {duration_sec}s | Tokens: {t_tok} | Reasoning: {res.get('reasoning')}")

                papers_summary.append({
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "doi": paper.doi,
                    "arxiv_id": paper.arxiv_id,
                    "screening_status": status,
                    "passed": res.get("passed", False),
                    "input_source": src,
                    "duration_seconds": duration_sec,
                    "tokens": {
                        "tokens_in": p_tok,
                        "tokens_out": c_tok,
                        "total_tokens": t_tok
                    },
                    "reasoning": res.get("reasoning"),
                    "evidence_quotes": res.get("evidence_quotes", []),
                    "decision_category": res.get("decision_category", "ACCEPTED" if status == "full_text_passed" else "REJECTED")
                })
            else:
                duration_sec = res.get("duration_seconds", 0.0)
                logger.warning(f"⚠️ [FULL-TEXT SCREENING FAILED] Error processing paper '{title_snippet}...' ({duration_sec}s): {res.get('error')}")
                failed_count += 1

            # Flush live progress metrics to DB for real-time monitoring by MCP and Admin
            processed_so_far = passed_count + rejected_count + withdrawn_count + failed_count
            total_papers = len(papers)
            pct = round((processed_so_far / total_papers * 100.0), 1) if total_papers > 0 else 100.0
            try:
                latest_badge = "PASSED" if res.get("screening_status") == "full_text_passed" else ("FAILED" if not res.get("success") else "REJECTED")
                component_run.metrics = {
                    "model_used": workspace.screening_llm_model,
                    "parallel_workers": worker_concurrency,
                    "total_screened": processed_so_far,
                    "total_to_screen": total_papers,
                    "passed": passed_count,
                    "rejected": rejected_count,
                    "withdrawn": withdrawn_count,
                    "failed": failed_count,
                    "percent_complete": pct,
                    "latest_processed": f"[{latest_badge}] {title_snippet}",
                    "elapsed_seconds": round(time.time() - job_t0, 1),
                }
                component_run.save(update_fields=['metrics'])
            except Exception as me:
                logger.debug(f"Metrics live flush note: {me}")

        if worker_concurrency <= 1:
            for paper in papers:
                try:
                    res = screen_full_text(paper.id, workspace.id, workspace_obj=workspace, paper_obj=paper)
                except Exception as pe:
                    logger.error(f"Error screening paper '{paper.id}': {pe}")
                    res = {"success": False, "error": str(pe), "input_source": "error", "duration_seconds": 0.0, "usage": {}}
                _record_result(paper, res)
        else:
            batch_timeout_sec = max(600.0, (len(papers) / max(1, worker_concurrency)) * 300.0)
            completed_paper_ids = set()
            with ThreadPoolExecutor(max_workers=worker_concurrency) as executor:
                future_to_paper = {
                    executor.submit(_screen_full_text_paper_task, paper, workspace): paper
                    for paper in papers
                }
                try:
                    for future in as_completed(future_to_paper, timeout=batch_timeout_sec):
                        paper = future_to_paper[future]
                        completed_paper_ids.add(paper.id)
                        try:
                            _, res = future.result(timeout=300.0)
                        except Exception as fe:
                            logger.error(f"Thread execution error for paper '{paper.id}': {fe}")
                            res = {"success": False, "error": str(fe), "input_source": "unknown", "duration_seconds": 0.0, "usage": {}}
                        _record_result(paper, res)
                except Exception as batch_err:
                    logger.warning(f"⚠️ [BATCH TIMEOUT / ERROR] Full-text screening batch interrupted: {batch_err}")

                # Ensure any hanging futures are safely terminated and recorded as failed
                for future, paper in future_to_paper.items():
                    if paper.id not in completed_paper_ids:
                        future.cancel()
                        logger.warning(f"⚠️ [TIMEOUT RECOVERY] Paper '{paper.id}' ({paper.title[:40]}...) timed out during full-text screening. Recording as failed.")
                        res = {"success": False, "error": "Operation timed out during full-text screening batch execution.", "input_source": "timeout", "duration_seconds": 0.0, "usage": {}}
                        _record_result(paper, res)

        job_duration_sec = round(time.time() - job_t0, 3)
        avg_duration_sec = round(job_duration_sec / len(papers), 3) if papers else 0.0

        from decimal import Decimal
        from ...llm_providers.pricing import calculate_llm_cost

        cost = calculate_llm_cost(workspace.screening_llm_model, total_prompt_tokens, total_candidates_tokens)

        component_run.metrics = {
            "model_used": workspace.screening_llm_model,
            "parallel_workers": worker_concurrency,
            "total_screened": len(papers),
            "passed": passed_count,
            "rejected": rejected_count,
            "withdrawn": withdrawn_count,
            "failed": failed_count,
            "tokens_in": total_prompt_tokens,
            "tokens_out": total_candidates_tokens,
            "total_tokens": total_tokens,
            "usd_cost": float(cost),
            "total_duration_seconds": job_duration_sec,
            "avg_duration_per_paper_seconds": avg_duration_sec
        }
        component_run.output_data = {
            "summary": f"Full-text screened {len(papers)} papers using {workspace.screening_llm_model} in {job_duration_sec}s ({worker_concurrency}x parallel): {passed_count} passed, {rejected_count} rejected, {withdrawn_count} withdrawn, {failed_count} failed.",
            "model_used": workspace.screening_llm_model,
            "total_tokens_consumed": total_tokens,
            "total_duration_seconds": job_duration_sec,
            "usd_cost": float(cost),
            "screened_papers": papers_summary
        }
        component_run.status = 'completed'
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['metrics', 'output_data', 'status', 'completed_at'])

        # Aggregate tokens, cost, and final passed paper count to PipelineRun
        pipeline_run.refresh_from_db()
        pipeline_run.tokens_in = (pipeline_run.tokens_in or 0) + total_prompt_tokens
        pipeline_run.tokens_out = (pipeline_run.tokens_out or 0) + total_candidates_tokens
        pipeline_run.tokens_consumed = (pipeline_run.tokens_consumed or 0) + total_tokens
        pipeline_run.usd_cost = (pipeline_run.usd_cost or Decimal('0.0000')) + cost
        pipeline_run.total_papers_passed_screening = Paper.objects.filter(pipeline_run=pipeline_run, screening_status='full_text_passed').count()
        pipeline_run.save(update_fields=['tokens_in', 'tokens_out', 'tokens_consumed', 'usd_cost', 'total_papers_passed_screening'])

        # Record monthly quota usage on Workspace
        workspace.record_token_usage(total_prompt_tokens, total_candidates_tokens, workspace.screening_llm_model)

        logger.info(f"📊 [FULL-TEXT SCREENING COMPLETED] Model: {workspace.screening_llm_model} | Screened: {len(papers)} | Time: {job_duration_sec}s | Tokens: {total_tokens} (In: {total_prompt_tokens}, Out: {total_candidates_tokens}) | Cost: ${cost}")

        pipeline_run.refresh_from_db()
        pending_or_running = ComponentRun.objects.filter(pipeline_run_id=pipeline_run.id, status__in=['pending', 'running']).exists()
        has_failed = ComponentRun.objects.filter(pipeline_run_id=pipeline_run.id, status='failed').exists()
        has_aborted = ComponentRun.objects.filter(pipeline_run_id=pipeline_run.id, status='aborted').exists()
        is_managed_by_agent = pipeline_run.agent_processes.filter(status='running').exists()

        if not pending_or_running and not is_managed_by_agent:
            if has_failed:
                pipeline_run.status = 'failed'
            elif has_aborted:
                pipeline_run.status = 'aborted'
            elif pipeline_run.current_stage == 'completed':
                pipeline_run.status = 'completed'
                pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])

        # Notify autonomous orchestrator to advance to next step
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return True
    except Exception as e:
        logger.exception(f"Error in Full-Text Screening ComponentRun '{component_run_id}': {e}")
        component_run.status = 'failed'
        component_run.error_message = str(e)
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['status', 'error_message', 'completed_at'])
        pipeline_run.status = 'failed'
        pipeline_run.save(update_fields=['status'])

        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return False
