import os
import time
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery import shared_task, group
from django.db import connection, close_old_connections, transaction
from django.utils import timezone
from django.core.files.storage import default_storage
from ...models import Workspace, Paper, Extraction, ExtractionDefinition, ComponentRun, PipelineRun
from ...llm_providers import get_llm_provider

logger = logging.getLogger(__name__)


class SafeFormatterDict(dict):
    """
    Dictionary helper that returns the key wrapped in curly braces if missing.
    Prevents KeyError during string formatting when optional/accidental braces exist.
    """
    def __missing__(self, key):
        return f"{{{key}}}"


def _run_single_extraction_worker(paper, definition, workspace):
    close_old_connections()
    t0 = time.time()

    # 1. Retrieve layout markdown text or PDF binary or abstract fallback
    paper_text = None
    pdf_bytes = None
    input_source = "abstract_fallback"

    # Priority 1: Converted Markdown from OCR
    if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
        try:
            with default_storage.open(paper.converted_md_path, 'rb') as f:
                raw_content = f.read()
            paper_text = raw_content.decode("utf-8", errors="replace") if isinstance(raw_content, bytes) else str(raw_content)
            input_source = "markdown_ocr"
        except Exception as e:
            logger.warning(f"Error reading MD for paper {paper.id}: {e}")

    # Priority 2: Original PDF binary for direct Multimodal Gemini extraction
    if not paper_text and paper.original_pdf_path and default_storage.exists(paper.original_pdf_path):
        try:
            with default_storage.open(paper.original_pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            input_source = "multimodal_pdf"
            paper_text = "Please analyze the attached full-text PDF document for dynamic parameter extraction."
        except Exception as e:
            logger.warning(f"Error reading PDF binary for paper {paper.id}: {e}")

    # Priority 3: Abstract fallback
    if not paper_text:
        paper_text = paper.abstract or paper.title

    llm_provider = get_llm_provider(workspace.llm_provider)
    
    format_data = SafeFormatterDict(
        paper_text=paper_text[:120000],
        title=paper.title or "",
        abstract=paper.abstract or "",
        authors=paper.authors or "",
        published_date=str(getattr(paper, "published_date", "")) if getattr(paper, "published_date", None) else "",
        source_database=paper.source_database or "",
        arxiv_id=paper.arxiv_id or "",
        doi=paper.doi or ""
    )
    user_prompt = definition.user_prompt_template.format_map(format_data)

    system_prompt = (
        f"{definition.system_prompt}\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "- Extract all target parameters accurately from the provided paper text or attached PDF document.\n"
        "- Return a schema-validated JSON object containing the exact fields requested in the response schema."
    )

    # Use definition.response_schema if defined
    schema_to_use = definition.response_schema if (definition.response_schema and isinstance(definition.response_schema, dict)) else {
        "type": "object",
        "properties": {
            "result": {"type": "string"}
        }
    }

    gen_kwargs = {
        "prompt": user_prompt,
        "system_instruction": system_prompt,
        "response_schema": schema_to_use,
        "model": definition.llm_model,
        "reasoning_effort": getattr(workspace, 'reasoning_effort', 'medium'),
        "return_usage": True,
    }
    if pdf_bytes:
        gen_kwargs["pdf_bytes"] = pdf_bytes
        gen_kwargs["mime_type"] = "application/pdf"

    max_attempts = 3
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            gen_res = llm_provider.generate(**gen_kwargs)

            if isinstance(gen_res, tuple) and len(gen_res) == 2:
                response_data, raw_usage = gen_res
            else:
                response_data, raw_usage = gen_res, {}

            p_tok = raw_usage.get("prompt_tokens", 0) or 0
            c_tok = raw_usage.get("candidates_tokens", 0) or 0
            t_tok = raw_usage.get("total_tokens", 0) or (p_tok + c_tok)

            usage = {"tokens_in": p_tok, "tokens_out": c_tok, "total_tokens": t_tok}

            fields_dict = {}
            if isinstance(response_data, dict):
                if "fields" in response_data and isinstance(response_data["fields"], dict):
                    fields_dict = response_data["fields"]
                else:
                    fields_dict = response_data

            # Compute confidence and validation status
            avg_confidence = 0.9
            if isinstance(fields_dict, dict) and fields_dict:
                if "confidence_score" in fields_dict and isinstance(fields_dict["confidence_score"], (int, float)):
                    avg_confidence = float(fields_dict["confidence_score"])
                else:
                    conf_list = [
                        float(v["confidence"]) for v in fields_dict.values()
                        if isinstance(v, dict) and "confidence" in v and isinstance(v["confidence"], (int, float))
                    ]
                    if conf_list:
                        avg_confidence = sum(conf_list) / len(conf_list)

            review_required = False
            validation_status = "pass"

            if avg_confidence < 0.65:
                review_required = True
                validation_status = "warn"

            version_info = {
                "version": definition.version,
                "llm_model": definition.llm_model,
                "provider": workspace.llm_provider
            }

            # Save or update Extraction model atomically
            with transaction.atomic():
                extraction, created = Extraction.objects.update_or_create(
                    paper=paper,
                    extraction_definition=definition,
                    defaults={
                        "workspace": workspace,
                        "category": definition.name,
                        "fields_data": fields_dict if isinstance(fields_dict, dict) else {},
                        "version_info": version_info,
                        "validation_status": validation_status,
                        "review_required": review_required,
                        "confidence_score": avg_confidence,
                        "confidence_method": "single_pass"
                    }
                )

            duration_sec = round(time.time() - t0, 3)

            return {
                "success": True,
                "paper_id": str(paper.id),
                "paper_title": paper.title,
                "definition_id": str(definition.id),
                "definition_name": definition.name,
                "input_source": input_source,
                "validation_status": validation_status,
                "confidence_score": avg_confidence,
                "duration_seconds": duration_sec,
                "usage": usage,
                "extracted_fields_count": len(fields_dict) if isinstance(fields_dict, dict) else 0
            }
        except Exception as e:
            last_error = e
            if attempt < max_attempts:
                delay = (2 ** attempt) + (0.1 * attempt)
                logger.warning(f"⚠️ [EXTRACTION RETRY {attempt}/{max_attempts}] Paper '{paper.id}' with def '{definition.name}' failed: {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                duration_sec = round(time.time() - t0, 3)
                logger.exception(f"Error executing extraction for paper {paper.id} with definition {definition.name} after {max_attempts} attempts: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "paper_id": str(paper.id),
                    "definition_id": str(definition.id),
                    "definition_name": definition.name,
                    "duration_seconds": duration_sec,
                    "usage": {"tokens_in": 0, "tokens_out": 0, "total_tokens": 0}
                }


@shared_task(bind=True)
def execute_extraction_job(self, component_run_id: str, limit: int = None, max_workers: int = 4):
    """
    Celery worker task executing Step 5 (Parameter & Claim Extraction) for papers in a ComponentRun job.
    Executes extractions for all active ExtractionDefinitions in parallel using a ThreadPoolExecutor.
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
    worker_concurrency = int(os.environ.get("EXTRACTION_PARALLEL_WORKERS", max_workers))

    if connection.vendor == 'sqlite':
        worker_concurrency = 1

    try:
        active_definitions = list(ExtractionDefinition.objects.filter(workspace=workspace, is_active=True))
        if not active_definitions:
            logger.warning(f"⚠️ No active extraction definitions found for workspace '{workspace.name}'.")
            component_run.metrics = {
                "total_papers": 0,
                "total_definitions": 0,
                "extractions_created": 0,
                "total_tokens": 0,
                "total_duration_seconds": 0.0
            }
            component_run.output_data = {
                "summary": "No active extraction definitions found for workspace.",
                "extractions": []
            }
            component_run.status = 'completed'
            component_run.completed_at = timezone.now()
            component_run.save(update_fields=['metrics', 'output_data', 'status', 'completed_at'])

            from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
            notify_pipeline_orchestrator_tick(pipeline_run)
            return True

        # Target paper selection: strictly evaluate based on screening jobs in pipeline history
        has_full_text_run = ComponentRun.objects.filter(
            pipeline_run=pipeline_run,
            step_type='screening',
            component_name__icontains='full_text'
        ).exists()
        has_abstract_run = ComponentRun.objects.filter(
            pipeline_run=pipeline_run,
            step_type='screening',
            component_name__icontains='abstract'
        ).exists()

        if has_full_text_run:
            papers_qs = Paper.objects.filter(pipeline_run=pipeline_run, screening_status__in=['full_text_passed', 'accepted'])
            logger.info(f"🔍 [EXTRACTION FILTER] Prior Full-Text Screening job detected. Targeting {papers_qs.count()} papers with status='full_text_passed'.")
        elif has_abstract_run:
            papers_qs = Paper.objects.filter(pipeline_run=pipeline_run, screening_status__in=['abstract_passed', 'accepted'])
            logger.info(f"🔍 [EXTRACTION FILTER] Prior Abstract Screening job detected. Targeting {papers_qs.count()} papers with status='abstract_passed'.")
        else:
            papers_qs = Paper.objects.filter(pipeline_run=pipeline_run).exclude(screening_status__in=['rejected', 'withdrawn'])
            logger.info(f"🔍 [EXTRACTION FILTER] No prior Screening jobs found. Targeting {papers_qs.count()} papers.")

        papers = list(papers_qs[:limit] if (limit and limit > 0) else papers_qs)

        # Prepare (paper, definition) work items
        work_items = [(paper, definition) for paper in papers for definition in active_definitions]
        logger.info(f"🚀 [PARALLEL EXTRACTION START] Running {len(work_items)} extractions ({len(papers)} papers x {len(active_definitions)} definitions) with {worker_concurrency} threads...")

        succeeded_count = 0
        failed_count = 0
        total_prompt_tokens = 0
        total_candidates_tokens = 0
        total_tokens = 0
        extractions_summary = []

        def _record_result(res):
            nonlocal succeeded_count, failed_count
            nonlocal total_prompt_tokens, total_candidates_tokens, total_tokens

            if res.get("success"):
                succeeded_count += 1
                usage = res.get("usage", {})
                duration_sec = res.get("duration_seconds", 0.0)
                p_tok = usage.get("tokens_in", 0)
                c_tok = usage.get("tokens_out", 0)
                t_tok = usage.get("total_tokens", 0) or (p_tok + c_tok)

                total_prompt_tokens += p_tok
                total_candidates_tokens += c_tok
                total_tokens += t_tok

                extractions_summary.append({
                    "paper_id": res.get("paper_id"),
                    "paper_title": res.get("paper_title"),
                    "definition_id": res.get("definition_id"),
                    "definition_name": res.get("definition_name"),
                    "validation_status": res.get("validation_status"),
                    "confidence_score": res.get("confidence_score"),
                    "duration_seconds": duration_sec,
                    "tokens": {
                        "tokens_in": p_tok,
                        "tokens_out": c_tok,
                        "total_tokens": t_tok
                    },
                    "fields_extracted": res.get("extracted_fields_count", 0)
                })
                p_title = res.get('paper_title') or 'Untitled'
                logger.info(f"✅ [EXTRACTION COMPLETED] Paper '{p_title[:40]}...' | Definition '{res.get('definition_name')}' | Time: {duration_sec}s | Tokens: {t_tok}")
            else:
                failed_count += 1
                logger.warning(f"⚠️ [EXTRACTION FAILED] Paper ID {res.get('paper_id')} | Def '{res.get('definition_name')}': {res.get('error')}")

        if worker_concurrency <= 1:
            for paper, definition in work_items:
                try:
                    res = _run_single_extraction_worker(paper, definition, workspace)
                except Exception as pe:
                    logger.error(f"Error extracting paper '{paper.id}' with def '{definition.name}': {pe}")
                    res = {
                        "success": False,
                        "error": str(pe),
                        "paper_id": str(paper.id),
                        "definition_id": str(definition.id),
                        "definition_name": definition.name,
                        "duration_seconds": 0.0,
                        "usage": {}
                    }
                _record_result(res)
        else:
            batch_timeout_sec = max(300.0, (len(work_items) / max(1, worker_concurrency)) * 180.0)
            completed_item_keys = set()
            with ThreadPoolExecutor(max_workers=worker_concurrency) as executor:
                future_to_item = {
                    executor.submit(_run_single_extraction_worker, paper, definition, workspace): (paper, definition)
                    for paper, definition in work_items
                }
                try:
                    for future in as_completed(future_to_item, timeout=batch_timeout_sec):
                        paper, definition = future_to_item[future]
                        item_key = (str(paper.id), str(definition.id))
                        completed_item_keys.add(item_key)
                        try:
                            res = future.result(timeout=180.0)
                        except Exception as fe:
                            logger.error(f"Thread execution error for paper '{paper.id}' with def '{definition.name}': {fe}")
                            res = {
                                "success": False,
                                "error": str(fe),
                                "paper_id": str(paper.id),
                                "definition_id": str(definition.id),
                                "definition_name": definition.name,
                                "duration_seconds": 0.0,
                                "usage": {}
                            }
                        _record_result(res)
                except Exception as batch_err:
                    logger.warning(f"⚠️ [BATCH TIMEOUT / ERROR] Parameter extraction batch interrupted: {batch_err}")

                # Ensure any hanging futures are safely terminated and recorded as failed
                for future, (paper, definition) in future_to_item.items():
                    item_key = (str(paper.id), str(definition.id))
                    if item_key not in completed_item_keys:
                        future.cancel()
                        logger.warning(f"⚠️ [TIMEOUT RECOVERY] Paper '{paper.id}' def '{definition.name}' timed out during extraction. Recording as failed.")
                        res = {
                            "success": False,
                            "error": "Operation timed out during parameter extraction batch execution.",
                            "paper_id": str(paper.id),
                            "definition_id": str(definition.id),
                            "definition_name": definition.name,
                            "duration_seconds": 0.0,
                            "usage": {}
                        }
                        _record_result(res)

        job_duration_sec = round(time.time() - job_t0, 3)
        avg_duration_sec = round(job_duration_sec / len(work_items), 3) if work_items else 0.0

        from decimal import Decimal
        from ...llm_providers.pricing import calculate_llm_cost

        cost = calculate_llm_cost(workspace.screening_llm_model, total_prompt_tokens, total_candidates_tokens)

        component_run.metrics = {
            "model_used": workspace.screening_llm_model,
            "parallel_workers": worker_concurrency,
            "total_papers": len(papers),
            "total_definitions": len(active_definitions),
            "total_extractions_attempted": len(work_items),
            "extractions_created": succeeded_count,
            "failed": failed_count,
            "tokens_in": total_prompt_tokens,
            "tokens_out": total_candidates_tokens,
            "total_tokens": total_tokens,
            "usd_cost": float(cost),
            "total_duration_seconds": job_duration_sec,
            "avg_duration_per_extraction_seconds": avg_duration_sec
        }
        component_run.output_data = {
            "summary": f"Extracted data for {len(papers)} papers across {len(active_definitions)} active definitions in {job_duration_sec}s ({worker_concurrency}x parallel): {succeeded_count} succeeded, {failed_count} failed.",
            "total_tokens_consumed": total_tokens,
            "total_duration_seconds": job_duration_sec,
            "usd_cost": float(cost),
            "extractions": extractions_summary
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
        pipeline_run.save(update_fields=['tokens_in', 'tokens_out', 'tokens_consumed', 'usd_cost'])

        # Record monthly quota usage on Workspace
        workspace.record_token_usage(total_prompt_tokens, total_candidates_tokens, workspace.screening_llm_model)

        logger.info(f"📊 [STEP 5 EXTRACTION JOB COMPLETED] Total Extractions: {succeeded_count} | Time: {job_duration_sec}s | Tokens: {total_tokens} (In: {total_prompt_tokens}, Out: {total_candidates_tokens}) | Cost: ${cost}")

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
            else:
                pipeline_run.status = 'completed'
                pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'completed_at'])

        logger.info(f"🎉 [EXTRACTION COMPLETE] ComponentRun '{component_run_id}' finished in {job_duration_sec}s. Succeeded: {succeeded_count}, Failed: {failed_count}, Tokens: {total_tokens}")

        # Notify autonomous orchestrator to advance to completed state
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return True

    except Exception as e:
        logger.exception(f"Error in ComponentRun '{component_run_id}': {e}")
        component_run.status = 'failed'
        component_run.error_message = str(e)
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['status', 'error_message', 'completed_at'])

        pipeline_run.status = 'failed'
        pipeline_run.save(update_fields=['status'])

        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return False


def run_extraction_for_definition(paper_id: str, definition_id: str):
    """Backwards-compatible helper wrapper for single paper-definition extraction."""
    try:
        paper = Paper.objects.select_related('workspace').get(pk=paper_id)
        definition = ExtractionDefinition.objects.get(pk=definition_id)
        res = _run_single_extraction_worker(paper, definition, paper.workspace)
        return res.get("success", False)
    except Exception as e:
        logger.exception(f"Error in run_extraction_for_definition: {e}")
        return False


def extract_custom_variables(paper_id: str, workspace_id: str):
    """Backwards-compatible helper wrapper executing extractions across active definitions."""
    try:
        paper = Paper.objects.get(pk=paper_id)
        workspace = Workspace.objects.get(pk=workspace_id)
        active_defs = ExtractionDefinition.objects.filter(workspace=workspace, is_active=True)
        results = []
        for d in active_defs:
            res = _run_single_extraction_worker(paper, d, workspace)
            results.append(res)
        return results
    except Exception as e:
        logger.exception(f"Error in extract_custom_variables: {e}")
        return []
