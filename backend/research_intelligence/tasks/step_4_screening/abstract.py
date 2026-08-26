import os
import time
import logging
from django.utils import timezone
from celery import shared_task
from ...models import Workspace, Paper
from ...llm_providers import get_llm_provider

logger = logging.getLogger(__name__)

@shared_task
def screen_abstract(paper_id, workspace_id, workspace_obj=None, paper_obj=None):
    """
    Screens a paper abstract against workspace inclusion/exclusion criteria
    using the configured screening LLM.
    Returns a dictionary with screening status, reasoning, and evidence quotes.
    """
    try:
        workspace = workspace_obj or Workspace.objects.get(pk=workspace_id)
        paper = paper_obj or Paper.objects.get(pk=paper_id)
    except (Workspace.DoesNotExist, Paper.DoesNotExist) as e:
        logger.error(f"Failed to find workspace {workspace_id} or paper {paper_id}: {str(e)}")
        return {"success": False, "error": str(e)}

    import time
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
            "duration_seconds": duration_sec,
            "usage": {"tokens_in": 0, "tokens_out": 0, "total_tokens": 0}
        }

    provider = get_llm_provider(workspace.llm_provider)
    
    system_prompt = workspace.get_abstract_screening_system_prompt()
    user_prompt_template = workspace.get_abstract_screening_user_prompt_template()
    acceptance = workspace.get_abstract_acceptance_criteria() or "Relevant AI research"
    rejection = workspace.get_abstract_rejection_criteria() or "Out of domain"
    response_schema = workspace.get_abstract_screening_response_schema()
    exit_metric_key = workspace.get_abstract_screening_exit_metric()

    try:
        user_prompt = user_prompt_template.format(
            title=paper.title,
            abstract=paper.abstract or "",
            acceptance_criteria=acceptance,
            rejection_criteria=rejection,
            paper_title=paper.title,
            paper_abstract=paper.abstract or ""
        )
    except Exception:
        user_prompt = (
            f"Title: {paper.title}\n"
            f"Abstract:\n{paper.abstract}\n\n"
            f"Acceptance Criteria (must satisfy to pass):\n{acceptance}\n\n"
            f"Rejection Criteria (if matched, paper is rejected):\n{rejection}"
        )

    max_attempts = 3
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            gen_res = provider.generate(
                prompt=user_prompt,
                system_instruction=system_prompt,
                response_schema=response_schema,
                model=workspace.screening_llm_model,
                return_usage=True
            )
            
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

            paper.screening_status = "abstract_passed" if passed else "rejected"
            paper.screening_reasoning = reasoning
            paper.save(update_fields=['screening_status', 'screening_reasoning'])

            # Store dynamic output in PaperMetric if pipeline_run is present
            if paper.pipeline_run_id:
                try:
                    from ...models import PaperMetric
                    pm, _ = PaperMetric.objects.get_or_create(
                        paper=paper,
                        pipeline_run_id=paper.pipeline_run_id,
                        defaults={"workspace": workspace}
                    )
                    m_data = pm.metrics_data or {}
                    m_data["abstract_screening"] = {
                        "passed": passed,
                        "reasoning": reasoning,
                        "evidence_quotes": evidence_quotes,
                        "decision_category": decision_category,
                        "exit_metric_key": exit_metric_key,
                        "exit_metric_value": exit_metric_val,
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
                "duration_seconds": duration_sec,
                "usage": usage
            }
        except Exception as e:
            last_error = e
            if attempt < max_attempts:
                delay = (2 ** attempt) + (0.1 * attempt)
                logger.warning(f"⚠️ [RETRY {attempt}/{max_attempts}] Paper '{paper.id}' ({paper.title[:30]}...) abstract screening failed: {str(e)}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                duration_sec = round(time.time() - t0, 3)
                logger.exception(f"Error screening abstract for paper {paper_id} after {max_attempts} attempts: {str(e)}")
                return {"success": False, "error": str(e), "duration_seconds": duration_sec, "usage": {"tokens_in": 0, "tokens_out": 0, "total_tokens": 0}}


def _screen_paper_task(paper, workspace_obj):
    from django.db import close_old_connections
    close_old_connections()
    res = screen_abstract(paper.id, workspace_obj.id, workspace_obj=workspace_obj, paper_obj=paper)
    return paper, res


@shared_task(bind=True)
def execute_screening_job(self, component_run_id: str, limit: int = 50, max_workers: int = 8):
    """
    Celery worker task executing Step 4 (Abstract Screening) for papers in a ComponentRun job.
    Executes paper screening concurrently using a ThreadPoolExecutor.
    """
    import os
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from django.db import connection, close_old_connections
    from django.utils import timezone
    from ...models import ComponentRun

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
    component_run.save(update_fields=['status', 'celery_task_id', 'started_at'])

    job_t0 = time.time()
    worker_concurrency = int(os.environ.get("SCREENING_PARALLEL_WORKERS", max_workers))

    # SQLite (used in unit tests) does not support multi-threaded write locks
    if connection.vendor == 'sqlite':
        worker_concurrency = 1

    try:
        papers = list(Paper.objects.filter(pipeline_run=pipeline_run)[:limit])
        passed_count = 0
        rejected_count = 0
        withdrawn_count = 0
        failed_count = 0
        total_prompt_tokens = 0
        total_candidates_tokens = 0
        total_tokens = 0
        papers_summary = []

        logger.info(f"🚀 [PARALLEL SCREENING START] Processing {len(papers)} papers using {worker_concurrency} parallel threads...")

        def _record_result(paper, res):
            nonlocal passed_count, rejected_count, withdrawn_count, failed_count
            nonlocal total_prompt_tokens, total_candidates_tokens, total_tokens

            title_snippet = paper.title[:50] if paper.title else "Untitled"
            if res.get("success"):
                status = res.get("screening_status")
                usage = res.get("usage", {})
                duration_sec = res.get("duration_seconds", 0.0)
                p_tok = usage.get("tokens_in", 0)
                c_tok = usage.get("tokens_out", 0)
                t_tok = usage.get("total_tokens", 0) or (p_tok + c_tok)

                total_prompt_tokens += p_tok
                total_candidates_tokens += c_tok
                total_tokens += t_tok

                if status == "abstract_passed":
                    passed_count += 1
                    logger.info(f"✅ [ACCEPTED] Paper '{title_snippet}...' | Time: {duration_sec}s | Tokens: {t_tok} (In: {p_tok}, Out: {c_tok}) | Reasoning: {res.get('reasoning')}")
                elif status == "withdrawn":
                    withdrawn_count += 1
                    logger.info(f"⏭️ [WITHDRAWN] Paper '{title_snippet}...' | Time: {duration_sec}s | Reason: {res.get('reasoning')}")
                else:
                    rejected_count += 1
                    logger.info(f"❌ [REJECTED] Paper '{title_snippet}...' | Time: {duration_sec}s | Tokens: {t_tok} (In: {p_tok}, Out: {c_tok}) | Reasoning: {res.get('reasoning')}")

                papers_summary.append({
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "doi": paper.doi,
                    "arxiv_id": paper.arxiv_id,
                    "screening_status": status,
                    "passed": res.get("passed", False),
                    "duration_seconds": duration_sec,
                    "tokens": {
                        "tokens_in": p_tok,
                        "tokens_out": c_tok,
                        "total_tokens": t_tok
                    },
                    "reasoning": res.get("reasoning"),
                    "evidence_quotes": res.get("evidence_quotes", []),
                    "decision_category": res.get("decision_category", "ACCEPTED" if status == "abstract_passed" else "REJECTED")
                })
            else:
                duration_sec = res.get("duration_seconds", 0.0)
                logger.warning(f"⚠️ [SCREENING FAILED] Error processing paper '{title_snippet}...' ({duration_sec}s): {res.get('error')}")
                failed_count += 1

        if worker_concurrency <= 1:
            for paper in papers:
                res = screen_abstract(paper.id, workspace.id, workspace_obj=workspace, paper_obj=paper)
                _record_result(paper, res)
        else:
            with ThreadPoolExecutor(max_workers=worker_concurrency) as executor:
                future_to_paper = {
                    executor.submit(_screen_paper_task, paper, workspace): paper
                    for paper in papers
                }
                for future in as_completed(future_to_paper):
                    paper = future_to_paper[future]
                    try:
                        _, res = future.result()
                    except Exception as fe:
                        logger.error(f"Thread execution error for paper '{paper.id}': {fe}")
                        res = {"success": False, "error": str(fe), "duration_seconds": 0.0, "usage": {}}
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
            "summary": f"Screened {len(papers)} papers using {workspace.screening_llm_model} in {job_duration_sec}s (8x parallel): {passed_count} passed, {rejected_count} rejected, {withdrawn_count} withdrawn, {failed_count} failed.",
            "model_used": workspace.screening_llm_model,
            "total_tokens_consumed": total_tokens,
            "total_duration_seconds": job_duration_sec,
            "usd_cost": float(cost),
            "screened_papers": papers_summary
        }
        component_run.status = 'completed'
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['metrics', 'output_data', 'status', 'completed_at'])

        # Aggregate tokens and cost to PipelineRun
        pipeline_run.refresh_from_db()
        pipeline_run.tokens_in = (pipeline_run.tokens_in or 0) + total_prompt_tokens
        pipeline_run.tokens_out = (pipeline_run.tokens_out or 0) + total_candidates_tokens
        pipeline_run.tokens_consumed = (pipeline_run.tokens_consumed or 0) + total_tokens
        pipeline_run.usd_cost = (pipeline_run.usd_cost or Decimal('0.0000')) + cost
        if passed_count > 0:
            pipeline_run.total_papers_passed_screening = (pipeline_run.total_papers_passed_screening or 0) + passed_count
        pipeline_run.save(update_fields=['tokens_in', 'tokens_out', 'tokens_consumed', 'usd_cost', 'total_papers_passed_screening'])

        # Record monthly quota usage on Workspace
        workspace.record_token_usage(total_prompt_tokens, total_candidates_tokens, workspace.screening_llm_model)

        logger.info(f"📊 [SCREENING COMPLETED] Model: {workspace.screening_llm_model} | Screened: {len(papers)} | Tokens: {total_tokens} (In: {total_prompt_tokens}, Out: {total_candidates_tokens}) | Cost: ${cost}")

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
        logger.exception(f"Error in Screening ComponentRun '{component_run_id}': {e}")
        component_run.status = 'failed'
        component_run.error_message = str(e)
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['status', 'error_message', 'completed_at'])
        pipeline_run.status = 'failed'
        pipeline_run.save(update_fields=['status'])

        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return False
