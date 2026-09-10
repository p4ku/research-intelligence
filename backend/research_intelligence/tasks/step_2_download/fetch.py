import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery import shared_task
from django.utils import timezone
from django.db import connection, close_old_connections
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from ...models import Workspace, Paper, PipelineRun, ComponentRun, PaperMetric
from ...scrapers import get_scraper_provider
from ...utils.memory_guard import reclaim_ram
from .pdf_cache import try_reuse_cached_pdf, register_document_pdf

logger = logging.getLogger(__name__)


def is_valid_pdf_binary(file_bytes: bytes) -> bool:
    """Validates that bytes constitute a valid PDF binary (starts with %PDF- and is not HTML/empty)."""
    if not file_bytes or len(file_bytes) < 10:
        return False
    if not file_bytes.startswith(b'%PDF-'):
        return False
    if b'<html' in file_bytes[:100].lower() or b'<!doctype html' in file_bytes[:100].lower():
        return False
    return True


def _mark_download_retrieval_failed(paper, pipeline_run_obj, error_reason: str):
    """
    Marks a paper as rejected in PaperMetric if full-text document retrieval fails permanently.
    Prevents downstream full-text screening from incorrectly screening unretrieved papers.
    """
    target_pr = (pipeline_run_obj.id if pipeline_run_obj else None) or getattr(paper, 'pipeline_run_id', None)
    if target_pr:
        try:
            pm, _ = PaperMetric.objects.update_or_create(
                paper=paper,
                pipeline_run_id=target_pr,
                defaults={
                    'workspace_id': getattr(paper, 'workspace_id', None),
                    'screening_status': 'rejected',
                    'full_text_screening_reasoning': f"Full-text retrieval failed: could not download PDF ({error_reason})."
                }
            )
            pm.screening_status = 'rejected'
            pm.full_text_screening_reasoning = f"Full-text retrieval failed: could not download PDF ({error_reason})."
            m_data = dict(pm.metrics_data or {})
            m_data["download"] = {
                "success": False,
                "error": str(error_reason),
                "screening_status": "rejected"
            }
            pm.metrics_data = m_data
            pm.save(update_fields=['screening_status', 'full_text_screening_reasoning', 'metrics_data'])
            logger.info(f"🚫 [RETRIEVAL FAILED] Paper '{paper.id}' marked as rejected (reason: {error_reason})")
        except Exception as me:
            logger.warning(f"Could not mark PaperMetric retrieval failure for paper {paper.id}: {me}")


def _download_paper_task(paper, workspace_obj, pipeline_run_obj, withdrawn_info_map=None):
    close_old_connections()
    title_snippet = paper.title[:50] if paper.title else "Untitled"

    # Check if paper is already marked as withdrawn
    if withdrawn_info_map is not None:
        reason = withdrawn_info_map.get(paper.id)
        if reason is not None:
            logger.info(f"⏭️ [WITHDRAWN] Skipped paper '{title_snippet}...' ({reason})")
            return {
                "status": "withdrawn",
                "paper_id": str(paper.id),
                "title": paper.title,
                "reason": reason
            }
    else:
        pm = PaperMetric.objects.filter(paper=paper, pipeline_run=pipeline_run_obj).first()
        if pm and pm.screening_status == 'withdrawn':
            reason = pm.latest_screening_reasoning or "Paper has been withdrawn by authors."
            logger.info(f"⏭️ [WITHDRAWN] Skipped paper '{title_snippet}...' ({reason})")
            return {
                "status": "withdrawn",
                "paper_id": str(paper.id),
                "title": paper.title,
                "reason": reason
            }

    # Storage path convention: workspaces/{workspace_id}/runs/{pipeline_run_id}/documents/{hash_id}/original.pdf
    doc_folder = f"workspaces/{workspace_obj.id}/runs/{pipeline_run_obj.id}/documents/{paper.hash_id}"
    target_path = f"{doc_folder}/original.pdf"

    # Check idempotency: If already downloaded to storage, skip downloading!
    if paper.original_pdf_path and not (paper.original_pdf_path.startswith("http://") or paper.original_pdf_path.startswith("https://")):
        if default_storage.exists(paper.original_pdf_path):
            logger.info(f"⏩ [SKIPPED] PDF already stored at: '{paper.original_pdf_path}' for paper '{title_snippet}...'")
            return {
                "status": "already_stored",
                "paper_id": str(paper.id),
                "title": paper.title,
                "storage_path": paper.original_pdf_path
            }

    # If default_storage target_path already exists, link and skip
    if default_storage.exists(target_path):
        paper.original_pdf_path = target_path
        paper.save(update_fields=['original_pdf_path'])
        logger.info(f"⏩ [SKIPPED] PDF target already exists at: '{target_path}' for paper '{title_snippet}...'")
        return {
            "status": "already_exists",
            "paper_id": str(paper.id),
            "title": paper.title,
            "storage_path": target_path
        }

    # Cross-Workspace / Cross-Run PDF Cache Reuse (Zero-Network Fast Path)
    cache_result = try_reuse_cached_pdf(paper, target_path, title_snippet)
    if cache_result:
        return cache_result

    # Resolve source URL
    pdf_source_url = paper.original_pdf_path
    if not pdf_source_url or not (pdf_source_url.startswith("http://") or pdf_source_url.startswith("https://")):
        if paper.arxiv_id:
            pdf_source_url = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"

    if not pdf_source_url:
        logger.warning(f"⚠️ [NO URL] Paper '{paper.id}' ({title_snippet}) has no valid PDF source URL.")
        _mark_download_retrieval_failed(paper, pipeline_run_obj, "No valid PDF source URL")
        return {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": "No valid PDF source URL"}

    from ...utils.url_guard import is_safe_external_url
    if not is_safe_external_url(pdf_source_url):
        logger.warning(f"⚠️ [BLOCKED SSRF URL] PDF URL '{pdf_source_url}' for paper '{paper.id}' rejected by SSRF guard.")
        _mark_download_retrieval_failed(paper, pipeline_run_obj, f"Disallowed private / internal IP URL: {pdf_source_url}")
        return {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": f"Disallowed private / internal IP URL: {pdf_source_url}"}

    max_attempts = 3
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            provider = get_scraper_provider(paper.source_database or "arxiv")
            file_bytes = provider.download_file(pdf_source_url)
            if file_bytes and len(file_bytes) > 0:
                if not is_valid_pdf_binary(file_bytes):
                    logger.warning(f"⚠️ [NON-PDF CONTENT] Downloaded {len(file_bytes)} bytes from '{pdf_source_url}' for paper '{title_snippet}...' but content is not a valid PDF (HTML landing page or corrupted).")
                    _mark_download_retrieval_failed(paper, pipeline_run_obj, "Downloaded content is not a valid PDF (HTML/corrupt)")
                    return {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": "Downloaded content is not a valid PDF (HTML/corrupt)"}

                if default_storage.exists(target_path):
                    default_storage.delete(target_path)
                saved_path = default_storage.save(target_path, ContentFile(file_bytes))
                paper.original_pdf_path = saved_path
                paper.save(update_fields=['original_pdf_path'])
                doc_reg = register_document_pdf(paper, file_bytes)
                size_bytes = len(file_bytes)
                del file_bytes
                size_kb = size_bytes / 1024
                logger.info(f"✅ [DOWNLOADED] Successfully fetched PDF [{size_kb:.1f} KB] from '{pdf_source_url}' -> saved to: '{saved_path}' (Registered in DocumentRegistry: {doc_reg.id if doc_reg else 'None'})")
                return {
                    "status": "downloaded",
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "size_bytes": size_bytes,
                    "size_kb": round(size_kb, 1),
                    "storage_path": saved_path,
                    "registry_id": str(doc_reg.id) if doc_reg else None
                }
            else:
                logger.warning(f"⚠️ [EMPTY PDF] Received 0 bytes for paper '{title_snippet}...' from '{pdf_source_url}' (attempt {attempt}/{max_attempts})")
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
                else:
                    _mark_download_retrieval_failed(paper, pipeline_run_obj, "0 bytes received")
                    return {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": "0 bytes received"}
        except Exception as e:
            err_msg = str(e).lower()
            if "404" in err_msg or "withdrawn" in err_msg:
                target_pr = (pipeline_run_obj.id if pipeline_run_obj else None) or getattr(paper, 'pipeline_run_id', None)
                if target_pr:
                    PaperMetric.objects.update_or_create(
                        paper=paper,
                        pipeline_run_id=target_pr,
                        defaults={
                            'workspace_id': getattr(paper, 'workspace_id', None),
                            'screening_status': 'withdrawn',
                            'abstract_screening_reasoning': f"Paper withdrawn by authors or unavailable at source ({e})."
                        }
                    )
                logger.info(f"⏭️ [WITHDRAWN 404] Paper '{title_snippet}...' marked as withdrawn ({e})")
                return {
                    "status": "withdrawn",
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "reason": f"Paper withdrawn by authors or unavailable at source ({e})."
                }

            last_error = e
            if attempt < max_attempts:
                delay = (2 ** attempt) + (0.1 * attempt)
                logger.warning(f"⚠️ [DOWNLOAD RETRY {attempt}/{max_attempts}] Paper '{title_snippet}...' failed downloading from '{pdf_source_url}': {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                logger.warning(f"❌ [DOWNLOAD FAILED] Error downloading PDF for paper '{title_snippet}...' after {max_attempts} attempts: {e}")
                _mark_download_retrieval_failed(paper, pipeline_run_obj, str(e))
                return {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": str(e)}


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=2, default_retry_delay=10)
def execute_pdf_download_job(self, component_run_id: str, limit: int = None, max_workers: int = 4):
    """
    Celery worker task executing PDF Binary Download for papers in a ComponentRun job.
    Downloads PDF binaries concurrently using a ThreadPoolExecutor.
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

    worker_concurrency = int(os.environ.get("DOWNLOAD_PARALLEL_WORKERS", max_workers))

    # SQLite (used in unit tests) does not support multi-threaded write locks
    if connection.vendor == 'sqlite':
        worker_concurrency = 1

    try:
        start_time = time.time()
        # Paper selection logic:
        # 1. If Abstract Screening was completed in this run (and not skipped), download ONLY papers with screening_status='abstract_passed'.
        # 2. If Abstract Screening was skipped or not executed, download all papers in pipeline_run (excluding withdrawn/rejected).
        abstract_run = ComponentRun.objects.filter(
            pipeline_run=pipeline_run,
            component_name='abstract_screening',
            status='completed'
        ).first()

        if abstract_run:
            papers_qs = pipeline_run.get_papers(screening_status='abstract_passed')
            papers = list(papers_qs[:limit] if (limit and limit > 0) else papers_qs)
            logger.info(f"🔍 [PDF DOWNLOAD FILTER] Prior Abstract Screening job completed. Targeting {len(papers)} papers with status='abstract_passed'.")
        else:
            papers_qs = pipeline_run.get_papers(exclude_status=['rejected', 'withdrawn'])
            papers = list(papers_qs[:limit] if (limit and limit > 0) else papers_qs)
            logger.info(f"🔍 [PDF DOWNLOAD FILTER] Abstract Screening was skipped or absent. Targeting {len(papers)} total candidate papers.")

        paper_lookup = {str(p.id): p for p in papers}

        # Pre-fetch withdrawn papers map once to avoid N database queries in threads
        withdrawn_info_map = {
            pm.paper_id: (pm.latest_screening_reasoning or "Paper has been withdrawn by authors.")
            for pm in PaperMetric.objects.filter(pipeline_run=pipeline_run, screening_status='withdrawn')
        }
        downloaded_count = 0
        cached_count = 0
        skipped_count = 0
        withdrawn_count = 0
        failed_count = 0
        downloaded_papers_summary = []

        logger.info(f"🚀 [PARALLEL PDF DOWNLOAD START] Processing {len(papers)} papers using {worker_concurrency} parallel threads...")

        def _record_result(res):
            nonlocal downloaded_count, cached_count, skipped_count, withdrawn_count, failed_count
            st = res.get("status")
            if st == "downloaded":
                downloaded_count += 1
                if res.get("from_cache") or res.get("cache_hit"):
                    cached_count += 1
                downloaded_papers_summary.append(res)
            elif st in ["already_stored", "already_exists"]:
                skipped_count += 1
                downloaded_papers_summary.append(res)
            elif st == "withdrawn":
                withdrawn_count += 1
                downloaded_papers_summary.append(res)
            else:
                failed_count += 1
                p_id = res.get("paper_id")
                if p_id and p_id in paper_lookup:
                    _mark_download_retrieval_failed(paper_lookup[p_id], pipeline_run, res.get("error") or "PDF download failed")

            # Flush live progress metrics to DB
            processed_so_far = downloaded_count + skipped_count + withdrawn_count + failed_count
            total_papers = len(papers)
            pct = round((processed_so_far / total_papers * 100.0), 1) if total_papers > 0 else 100.0
            p_title = res.get('title') or 'Untitled'
            is_cached = bool(res.get("from_cache") or res.get("cache_hit"))
            badge = "CACHED" if is_cached else ("DOWNLOADED" if st == "downloaded" else st.upper())
            try:
                component_run.metrics = {
                    "total_processed": processed_so_far,
                    "total_to_process": total_papers,
                    "downloaded": downloaded_count,
                    "cached": cached_count,
                    "skipped": skipped_count,
                    "failed": failed_count,
                    "percent_complete": pct,
                    "latest_processed": f"[{badge}] {p_title[:40]}...",
                    "elapsed_seconds": round(time.time() - start_time, 1),
                }
                component_run.save(update_fields=['metrics'])
            except Exception as me:
                logger.debug(f"Download metrics live flush note: {me}")

        chunk_size = int(os.environ.get("DOWNLOAD_CHUNK_SIZE", 25))
        chunks = [papers[i:i + chunk_size] for i in range(0, len(papers), chunk_size)]
        total_chunks = len(chunks)

        def _safe_call_download_task(paper_item, ws, run, w_map):
            try:
                return _download_paper_task(paper_item, ws, run, withdrawn_info_map=w_map)
            except TypeError:
                return _download_paper_task(paper_item, ws, run)

        for chunk_idx, chunk in enumerate(chunks):
            if worker_concurrency <= 1:
                for paper in chunk:
                    res = _safe_call_download_task(paper, workspace, pipeline_run, withdrawn_info_map)
                    _record_result(res)
            else:
                chunk_timeout_sec = max(180.0, (len(chunk) / max(1, worker_concurrency)) * 180.0)
                completed_paper_ids = set()
                with ThreadPoolExecutor(max_workers=worker_concurrency) as executor:
                    future_to_paper = {
                        executor.submit(_safe_call_download_task, paper, workspace, pipeline_run, withdrawn_info_map): paper
                        for paper in chunk
                    }
                    try:
                        for future in as_completed(future_to_paper, timeout=chunk_timeout_sec):
                            paper = future_to_paper[future]
                            completed_paper_ids.add(paper.id)
                            try:
                                res = future.result(timeout=180.0)
                            except Exception as fe:
                                logger.error(f"Thread execution error downloading PDF for paper '{paper.id}': {fe}")
                                res = {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": str(fe)}
                            _record_result(res)
                    except Exception as batch_err:
                        logger.warning(f"⚠️ [BATCH TIMEOUT / ERROR] PDF download batch {chunk_idx + 1}/{total_chunks} interrupted: {batch_err}")

                    # Ensure any hanging futures are safely terminated and recorded as failed
                    for future, paper in future_to_paper.items():
                        if paper.id not in completed_paper_ids:
                            future.cancel()
                            logger.warning(f"⚠️ [TIMEOUT RECOVERY] Paper '{paper.id}' ({paper.title[:40]}...) timed out during PDF download. Recording as failed.")
                            res = {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": "Download timed out."}
                            _record_result(res)

            # Aggressively reclaim memory after every batch of PDFs
            reclaim_ram(f"download_batch_{chunk_idx + 1}_of_{total_chunks}")

        # Update component run lifecycle metrics & output_data
        duration_sec = round(time.time() - start_time, 2)
        component_run.metrics = {
            "total_processed": len(papers),
            "downloaded": downloaded_count,
            "cached": cached_count,
            "from_cache": cached_count,
            "skipped": skipped_count,
            "withdrawn": withdrawn_count,
            "failed": failed_count,
            "total_duration_seconds": duration_sec
        }
        cached_info = f" ({downloaded_count - cached_count} from web, {cached_count} cached)" if cached_count > 0 else ""
        component_run.output_data = {
            "summary": f"Downloaded {downloaded_count} PDFs{cached_info}, skipped {skipped_count} existing, {withdrawn_count} withdrawn, {failed_count} failed in {duration_sec}s.",
            "downloaded_papers": downloaded_papers_summary,
            "total_duration_seconds": duration_sec
        }
        component_run.raw_storage_path = f"workspaces/{workspace.id}/runs/{pipeline_run.id}/documents/"
        component_run.status = 'completed'
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['metrics', 'output_data', 'raw_storage_path', 'status', 'completed_at'])

        # Update aggregated PipelineRun status
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

        logger.info(f"Completed PDF Download ComponentRun '{component_run_id}'. Downloaded: {downloaded_count}, Skipped: {skipped_count}, Failed: {failed_count}.")

        # Notify autonomous orchestrator to advance to next step
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return True

    except Exception as e:
        logger.exception(f"Error in PDF Download ComponentRun '{component_run_id}': {e}")
        component_run.status = 'failed'
        component_run.error_message = str(e)
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['status', 'error_message', 'completed_at'])

        pipeline_run.status = 'failed'
        pipeline_run.save(update_fields=['status'])

        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return False


@shared_task(acks_late=True, reject_on_worker_lost=True)
def download_pdf_to_s3(paper_id):
    """
    Downloads paper PDF using the appropriate scraper provider and uploads it to storage.
    """
    try:
        paper = Paper.objects.get(pk=paper_id)
        if not paper.original_pdf_path:
            logger.warning(f"Paper {paper_id} has no source PDF URL configured.")
            return False
            
        if not (paper.original_pdf_path.startswith("http://") or paper.original_pdf_path.startswith("https://")):
            return True

        provider = get_scraper_provider(paper.source_database or "arxiv")
        file_bytes = provider.download_file(paper.original_pdf_path)
        if not file_bytes:
            return False
            
        if paper.pipeline_run_id and paper.hash_id:
            target_path = f"workspaces/{paper.workspace_id}/runs/{paper.pipeline_run_id}/documents/{paper.hash_id}/original.pdf"
        elif paper.workspace_id and paper.hash_id:
            target_path = f"workspaces/{paper.workspace_id}/documents/{paper.hash_id}/original.pdf"
        else:
            target_path = f"workspaces/{paper.workspace_id}/documents/{paper.id}/original.pdf"

        default_storage.save(target_path, ContentFile(file_bytes))
        
        paper.original_pdf_path = target_path
        paper.save(update_fields=['original_pdf_path'])
        return True
    except Paper.DoesNotExist:
        return False
    except Exception as e:
        logger.exception(f"Error downloading PDF for paper {paper_id}: {str(e)}")
        return False
