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
    try:
        return _run_single_extraction_impl(paper, definition, workspace)
    finally:
        close_old_connections()


def _run_single_extraction_impl(paper, definition, workspace):
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
    if not paper_text and paper.original_pdf_path and not paper.original_pdf_path.startswith(("http://", "https://")) and default_storage.exists(paper.original_pdf_path):
        try:
            with default_storage.open(paper.original_pdf_path, 'rb') as f:
                raw_bytes = f.read()
            from ..step_2_download.fetch import is_valid_pdf_binary
            if is_valid_pdf_binary(raw_bytes):
                # Pre-check: If PDF is larger than 15MB, Gemini inline multimodal API rejects it with 400 INVALID_ARGUMENT
                # (inline payload limit is 20MB base64) and causes high memory usage. Extract text via PyPDF instead!
                if len(raw_bytes) > 15 * 1024 * 1024:
                    from ...utils.pdf_extractor import extract_text_from_pdf_bytes
                    logger.info(f"📄 Paper '{paper.id}' PDF is large ({len(raw_bytes)/(1024*1024):.1f} MB > 15 MB). Extracting text to avoid 400 INVALID_ARGUMENT.")
                    extracted_text = extract_text_from_pdf_bytes(raw_bytes, max_chars=120000)
                    if extracted_text:
                        paper_text = extracted_text
                        input_source = "pdf_text_extracted"
                    else:
                        pdf_bytes = raw_bytes
                        input_source = "multimodal_pdf"
                        paper_text = "Please analyze the attached full-text PDF document for dynamic parameter extraction."
                else:
                    pdf_bytes = raw_bytes
                    input_source = "multimodal_pdf"
                    paper_text = "Please analyze the attached full-text PDF document for dynamic parameter extraction."
            else:
                logger.warning(f"Stored file for paper {paper.id} at {paper.original_pdf_path} is not a valid PDF. Falling back to abstract.")
        except Exception as e:
            logger.warning(f"Error reading PDF binary for paper {paper.id}: {e}")

    # Priority 3: Abstract fallback
    if not paper_text:
        paper_text = paper.abstract or paper.title

    llm_provider = get_llm_provider(workspace.llm_provider)
    
    raw_tmpl = definition.user_prompt_template or ""
    # Normalize double-curly {{var}} to {var} if present
    import re
    normalized_tmpl = re.sub(r'\{\{([a-zA-Z0-9_]+)\}\}', r'{\1}', raw_tmpl)

    format_data = SafeFormatterDict(
        paper_text=paper_text[:120000] if paper_text else "",
        full_text=paper_text[:120000] if paper_text else "",
        title=paper.title or "",
        paper_title=paper.title or "",
        abstract=paper.abstract or "",
        paper_abstract=paper.abstract or "",
        authors=paper.authors or "",
        published_date=str(getattr(paper, "published_date", "")) if getattr(paper, "published_date", None) else "",
        source_database=paper.source_database or "",
        arxiv_id=paper.arxiv_id or "",
        doi=paper.doi or ""
    )
    user_prompt = normalized_tmpl.format_map(format_data)

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

            # Dynamic JSON Schema and exit_metric validation
            schema_validation_errors = []
            if definition.response_schema and isinstance(definition.response_schema, dict):
                try:
                    import jsonschema
                    validator = jsonschema.Draft7Validator(definition.response_schema)
                    for err in validator.iter_errors(fields_dict if isinstance(fields_dict, dict) else {}):
                        schema_validation_errors.append(err.message)
                except Exception as val_e:
                    logger.debug(f"JSON schema validation error check: {val_e}")
            
            exit_metric_missing = False
            if definition.exit_metrics:
                exit_metrics = definition.get_exit_metrics_list()
                if isinstance(fields_dict, dict):
                    extracted_keys = {k.strip().lower().replace(" ", "_") for k in fields_dict.keys()}
                    missing_metrics = [
                        em for em in exit_metrics
                        if em.lower().replace(" ", "_") not in extracted_keys
                    ]
                else:
                    missing_metrics = list(exit_metrics)

                if missing_metrics:
                    primary_metric = definition.get_primary_exit_metric()
                    if primary_metric in missing_metrics or len(missing_metrics) == len(exit_metrics):
                        exit_metric_missing = True
                    schema_validation_errors.append(
                        f"Expected exit_metrics '{', '.join(missing_metrics)}' were missing from extracted fields."
                    )

            review_required = False
            validation_status = "pass"

            if schema_validation_errors:
                review_required = True
                # Severe: missing exit metric or multiple violations -> 'fail', minor -> 'warn'
                if exit_metric_missing or len(schema_validation_errors) > 1:
                    validation_status = "fail"
                else:
                    validation_status = "warn"
            elif avg_confidence < 0.65:
                review_required = True
                validation_status = "warn"

            version_info = {
                "version": definition.version,
                "llm_model": definition.llm_model,
                "provider": workspace.llm_provider,
                "validation_errors": schema_validation_errors
            }

            # Code-based postprocessing on extracted fields if configured
            if definition.postprocessing_code and definition.postprocessing_code.strip():
                try:
                    from ...utils.sandbox import execute_sandboxed_postprocessing
                    from ..step_6_signal_score.scorer import _sanitize_identifier

                    def_slug = _sanitize_identifier(definition.name)
                    raw_context = dict(fields_dict) if isinstance(fields_dict, dict) else {}
                    post_res = execute_sandboxed_postprocessing(
                        code_snippet=definition.postprocessing_code,
                        fields_data=raw_context,
                        context_vars={
                            "title": paper.title or "",
                            "abstract": paper.abstract or "",
                            "arxiv_id": paper.arxiv_id or "",
                            "doi": paper.doi or ""
                        },
                        timeout_seconds=2.0
                    )
                    primary_exit = definition.get_primary_exit_metric()

                    if isinstance(fields_dict, dict):
                        if isinstance(post_res, dict):
                            fields_dict.update(post_res)
                            if len(post_res) == 1:
                                single_k, single_v = next(iter(post_res.items()))
                                unpacked_v = single_v
                                if isinstance(unpacked_v, dict):
                                    if "value" in unpacked_v and len(unpacked_v) <= 2:
                                        unpacked_v = unpacked_v["value"]
                                    elif len(unpacked_v) == 1:
                                        unpacked_v = next(iter(unpacked_v.values()))
                                fields_dict[single_k] = unpacked_v
                                fields_dict[f"{def_slug}_postprocessed"] = unpacked_v
                                fields_dict[f"{def_slug}_computed"] = unpacked_v
                                if primary_exit:
                                    fields_dict[f"{primary_exit}_postprocessed"] = unpacked_v
                                    fields_dict[f"{primary_exit}_computed"] = unpacked_v
                            else:
                                # > 1 keys: all are secondary metrics unless one explicitly matches def_slug_postprocessed
                                main_k = f"{def_slug}_postprocessed"
                                found_main = None
                                for k, v in post_res.items():
                                    if k.lower().replace(" ", "_") == main_k:
                                        found_main = v
                                        break
                                if found_main is not None:
                                    fields_dict[main_k] = found_main
                                    fields_dict[f"{def_slug}_computed"] = found_main
                                    if primary_exit:
                                        fields_dict[f"{primary_exit}_postprocessed"] = found_main
                                        fields_dict[f"{primary_exit}_computed"] = found_main
                        elif post_res is not None:
                            fields_dict[f"{def_slug}_postprocessed"] = post_res
                            fields_dict[f"{def_slug}_computed"] = post_res
                            if primary_exit:
                                fields_dict[f"{primary_exit}_postprocessed"] = post_res
                                fields_dict[f"{primary_exit}_computed"] = post_res
                        logger.info(f"✨ [EXTRACTION POSTPROCESSING] Paper '{paper.title[:30]}...' -> '{def_slug}_postprocessed': {fields_dict.get(f'{def_slug}_postprocessed')}")
                except Exception as post_err:
                    logger.warning(f"⚠️ [EXTRACTION POSTPROCESSING ERROR] Definition '{definition.name}' for Paper '{paper.id}': {post_err}")
                    version_info["postprocessing_error"] = str(post_err)
                    primary_exit = definition.get_primary_exit_metric()
                    if isinstance(fields_dict, dict):
                        fields_dict[f"{def_slug}_postprocessed"] = 0.0
                        fields_dict[f"{def_slug}_computed"] = 0.0
                        if primary_exit:
                            fields_dict[f"{primary_exit}_postprocessed"] = 0.0
                            fields_dict[f"{primary_exit}_computed"] = 0.0

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
                "llm_model": getattr(definition, 'llm_model', None) or getattr(workspace, 'screening_llm_model', None),
                "extracted_fields_count": len(fields_dict) if isinstance(fields_dict, dict) else 0
            }
        except Exception as e:
            last_error = e
            err_str = str(e)
            if ("400" in err_str or "INVALID_ARGUMENT" in err_str) and gen_kwargs.get("pdf_bytes"):
                logger.warning(
                    f"⚠️ [EXTRACTION 400 FALLBACK] Gemini rejected PDF binary for paper '{paper.id}' "
                    f"({paper.title[:30]}...). Extracting text and retrying without binary attachment."
                )
                from ...utils.pdf_extractor import extract_text_from_pdf_bytes
                extracted_text = extract_text_from_pdf_bytes(gen_kwargs.pop("pdf_bytes", None), max_chars=120000) or paper.abstract or ""
                gen_kwargs.pop("mime_type", None)
                input_source = "pdf_fallback_text" if extracted_text else "abstract_fallback"
                format_data = SafeFormatterDict(
                    paper_text=extracted_text[:120000] if extracted_text else "",
                    full_text=extracted_text[:120000] if extracted_text else "",
                    title=paper.title or "",
                    paper_title=paper.title or "",
                    abstract=paper.abstract or "",
                    paper_abstract=paper.abstract or "",
                    authors=paper.authors or "",
                    published_date=str(getattr(paper, "published_date", "")) if getattr(paper, "published_date", None) else "",
                    source_database=paper.source_database or "",
                    arxiv_id=paper.arxiv_id or "",
                    doi=paper.doi or ""
                )
                gen_kwargs["prompt"] = normalized_tmpl.format_map(format_data)
                continue

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


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=3, default_retry_delay=15)
def execute_extraction_job(self, component_run_id: str, limit: int = None, max_workers: int = 4):
    """
    Celery worker task executing Parameter & Claim Extraction for papers in a ComponentRun job.
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

    # Snapshot extraction prompt definitions into component_run.input_params for auditability
    try:
        current_input_params = component_run.input_params or {}
        current_input_params.update(workspace.get_extraction_prompt_snapshot())
        component_run.input_params = current_input_params
    except Exception as snap_err:
        logger.warning(f"Could not snapshot extraction definitions into component_run.input_params: {snap_err}")

    component_run.save(update_fields=['status', 'celery_task_id', 'started_at', 'completed_at', 'error_message', 'input_params'])

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
        screening_step_names = set(
            ComponentRun.objects.filter(
                pipeline_run=pipeline_run,
                step_type='screening'
            ).values_list('component_name', flat=True)
        )
        has_full_text_run = any('full_text' in str(c).lower() for c in screening_step_names)
        has_abstract_run = any('abstract' in str(c).lower() for c in screening_step_names)

        if has_full_text_run:
            papers_qs = pipeline_run.get_papers(screening_status=['full_text_passed', 'accepted'])
            papers = list(papers_qs[:limit] if (limit and limit > 0) else papers_qs)
            logger.info(f"🔍 [EXTRACTION FILTER] Prior Full-Text Screening job detected. Targeting {len(papers)} papers with status='full_text_passed'.")
        elif has_abstract_run:
            papers_qs = pipeline_run.get_papers(screening_status=['abstract_passed', 'accepted'])
            papers = list(papers_qs[:limit] if (limit and limit > 0) else papers_qs)
            logger.info(f"🔍 [EXTRACTION FILTER] Prior Abstract Screening job detected. Targeting {len(papers)} papers with status='abstract_passed'.")
        else:
            papers_qs = pipeline_run.get_papers(exclude_status=['rejected', 'withdrawn'])
            papers = list(papers_qs[:limit] if (limit and limit > 0) else papers_qs)
            logger.info(f"🔍 [EXTRACTION FILTER] No prior Screening jobs found. Targeting {len(papers)} papers.")

        succeeded_count = 0
        failed_count = 0
        total_prompt_tokens = 0
        total_candidates_tokens = 0
        total_tokens = 0
        tokens_by_model = {}
        extractions_summary = []

        # Prepare (paper, definition) work items
        all_work_items = [(paper, definition) for paper in papers for definition in active_definitions]

        # Resume resilience: check already successfully extracted pairs in this workspace
        # If pipeline_run.reprocess_existing or force_reextract is enabled, re-extract everything
        force_reextract = getattr(pipeline_run, 'reprocess_existing', False) or (component_run.input_params or {}).get("force_reextract", False)
        existing_extractions = {}
        if not force_reextract:
            existing_extractions = {
                (str(ext.paper_id), str(ext.extraction_definition_id)): ext
                for ext in Extraction.objects.filter(
                    workspace=workspace,
                    paper__in=papers,
                    extraction_definition__in=active_definitions
                ).exclude(validation_status='fail')
            }

        work_items = []
        for paper, definition in all_work_items:
            key = (str(paper.id), str(definition.id))
            if key in existing_extractions:
                existing_ext = existing_extractions[key]
                succeeded_count += 1
                extractions_summary.append({
                    "paper_id": str(paper.id),
                    "paper_title": paper.title,
                    "definition_id": str(definition.id),
                    "definition_name": definition.name,
                    "validation_status": existing_ext.validation_status,
                    "confidence_score": existing_ext.confidence_score,
                    "duration_seconds": 0.0,
                    "tokens": {"tokens_in": 0, "tokens_out": 0, "total_tokens": 0},
                    "fields_extracted": len(existing_ext.fields_data) if isinstance(existing_ext.fields_data, dict) else 0,
                    "resumed_from_cache": True
                })
            else:
                work_items.append((paper, definition))

        if existing_extractions:
            logger.info(f"🔄 [EXTRACTION RESUME] Found {len(existing_extractions)} already extracted items. Processing remaining {len(work_items)} items with {worker_concurrency} threads...")
        else:
            logger.info(f"🚀 [PARALLEL EXTRACTION START] Running {len(work_items)} extractions ({len(papers)} papers x {len(active_definitions)} definitions) with {worker_concurrency} threads...")

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

                used_model = res.get("llm_model") or getattr(workspace, 'screening_llm_model', 'google/gemini-3.8-flash')
                if used_model not in tokens_by_model:
                    tokens_by_model[used_model] = {"tokens_in": 0, "tokens_out": 0}
                tokens_by_model[used_model]["tokens_in"] += p_tok
                tokens_by_model[used_model]["tokens_out"] += c_tok

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

            # Flush live progress metrics to DB for real-time monitoring by MCP, Admin, and E2E polling
            processed_so_far = succeeded_count + failed_count
            total_items = len(all_work_items)
            pct = round((processed_so_far / total_items * 100.0), 1) if total_items > 0 else 100.0
            p_title = res.get('paper_title') or 'Untitled'
            def_name = res.get('definition_name') or 'Target'
            badge = "PASSED" if res.get("success") else "FAILED"
            try:
                component_run.metrics = {
                    "total_work_items": total_items,
                    "completed_extractions": succeeded_count,
                    "failed_extractions": failed_count,
                    "total_processed": processed_so_far,
                    "total_papers": len(papers),
                    "total_definitions": len(active_definitions),
                    "percent_complete": pct,
                    "latest_processed": f"[{badge}] {def_name}: {p_title[:35]}...",
                    "last_progress_at": timezone.now().isoformat(),
                    "elapsed_seconds": round(time.time() - job_t0, 1),
                }
                component_run.save(update_fields=['metrics'])
            except Exception as me:
                logger.debug(f"Extraction metrics live flush note: {me}")

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
            batch_timeout_sec = max(600.0, (len(work_items) / max(1, worker_concurrency)) * 300.0)
            completed_item_keys = set()
            executor = ThreadPoolExecutor(max_workers=worker_concurrency)
            try:
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
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

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
            "total_extractions_attempted": len(all_work_items),
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

        # Check for total catastrophic failure: if work was attempted and 0 succeeded
        if len(all_work_items) > 0 and succeeded_count == 0 and failed_count > 0:
            error_msg = f"All {failed_count} extractions failed (provider timeout, network drop, or schema errors)."
            logger.error(f"❌ [EXTRACTION TOTAL FAILURE] {error_msg}")
            component_run.status = 'failed'
            component_run.error_message = error_msg
            component_run.completed_at = timezone.now()
            component_run.save(update_fields=['metrics', 'output_data', 'status', 'error_message', 'completed_at'])

            pipeline_run.status = 'failed'
            pipeline_run.status_message = f"Pipeline terminated: Extraction step failed completely ({error_msg})"
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'status_message', 'completed_at'])

            from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
            notify_pipeline_orchestrator_tick(pipeline_run)
            return False

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

        # Record monthly quota usage on Workspace and persist into global LLM usage ledger
        if tokens_by_model:
            for m_name, m_usage in tokens_by_model.items():
                workspace.record_token_usage(
                    tokens_in=m_usage["tokens_in"],
                    tokens_out=m_usage["tokens_out"],
                    model_name=m_name,
                    operation_type="extraction",
                    user=pipeline_run.triggered_by,
                    pipeline_run_id=str(pipeline_run.id),
                    component_run_id=str(component_run.id)
                )
        else:
            workspace.record_token_usage(
                tokens_in=total_prompt_tokens,
                tokens_out=total_candidates_tokens,
                model_name=workspace.screening_llm_model,
                operation_type="extraction",
                user=pipeline_run.triggered_by,
                pipeline_run_id=str(pipeline_run.id),
                component_run_id=str(component_run.id)
            )

        logger.info(f"📊 [EXTRACTION JOB COMPLETED] Total Extractions: {succeeded_count} | Time: {job_duration_sec}s | Tokens: {total_tokens} (In: {total_prompt_tokens}, Out: {total_candidates_tokens}) | Cost: ${cost}")

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

        logger.info(f"🎉 [EXTRACTION COMPLETE] ComponentRun '{component_run_id}' finished in {job_duration_sec}s. Succeeded: {succeeded_count}, Failed: {failed_count}, Tokens: {total_tokens}")

        # Notify autonomous orchestrator to advance to completed state
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return True

    except Exception as e:
        logger.exception(f"Error in ComponentRun '{component_run_id}': {e}")
        retries = getattr(self.request, 'retries', 0) if hasattr(self, 'request') else 0
        max_retries = getattr(self, 'max_retries', 3)
        if retries < max_retries:
            countdown = 15 * (2 ** retries)
            logger.warning(f"⚠️ [TASK RETRY {retries + 1}/{max_retries}] Retrying execute_extraction_job for ComponentRun '{component_run_id}' in {countdown}s due to: {e}")
            try:
                if component_run:
                    component_run.error_message = f"Transient task failure (attempt {retries + 1}/{max_retries}): {e}. Retrying in {countdown}s..."
                    component_run.save(update_fields=['error_message'])
                raise self.retry(exc=e, countdown=countdown)
            except Exception as retry_err:
                if retry_err is not e and not isinstance(retry_err, getattr(self, 'MaxRetriesExceededError', Exception)):
                    raise

        if component_run:
            component_run.status = 'failed'
            component_run.error_message = f"Extraction failed after {max_retries} task retries: {str(e)}"
            component_run.completed_at = timezone.now()
            component_run.save(update_fields=['status', 'error_message', 'completed_at'])

        if pipeline_run:
            pipeline_run.status = 'failed'
            pipeline_run.status_message = f"Pipeline terminated: Extraction step failed after {max_retries} retries ({str(e)})"
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save(update_fields=['status', 'status_message', 'completed_at'])

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
