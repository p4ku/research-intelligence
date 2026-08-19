import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery import shared_task
from django.utils import timezone
from django.db import connection, close_old_connections
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from ...models import Workspace, Paper, PipelineRun, ComponentRun
from ...scrapers import get_scraper_provider
from .pdf_cache import try_reuse_cached_pdf

logger = logging.getLogger(__name__)


def _download_paper_task(paper, workspace_obj, pipeline_run_obj):
    close_old_connections()
    title_snippet = paper.title[:50] if paper.title else "Untitled"

    # Check if paper is already marked as withdrawn
    if paper.screening_status == 'withdrawn':
        reason = paper.screening_reasoning or "Paper has been withdrawn by authors."
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
        return {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": "No valid PDF source URL"}

    max_attempts = 3
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            provider = get_scraper_provider(paper.source_database or "arxiv")
            file_bytes = provider.download_file(pdf_source_url)
            if file_bytes and len(file_bytes) > 0:
                saved_path = default_storage.save(target_path, ContentFile(file_bytes))
                paper.original_pdf_path = saved_path
                paper.save(update_fields=['original_pdf_path'])
                size_bytes = len(file_bytes)
                size_kb = size_bytes / 1024
                logger.info(f"✅ [DOWNLOADED] Successfully fetched PDF [{size_kb:.1f} KB] from '{pdf_source_url}' -> saved to: '{saved_path}' (Paper: '{title_snippet}...')")
                return {
                    "status": "downloaded",
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "size_bytes": size_bytes,
                    "size_kb": round(size_kb, 1),
                    "storage_path": saved_path
                }
            else:
                logger.warning(f"⚠️ [EMPTY PDF] Received 0 bytes for paper '{title_snippet}...' from '{pdf_source_url}' (attempt {attempt}/{max_attempts})")
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
                else:
                    return {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": "0 bytes received"}
        except Exception as e:
            err_msg = str(e).lower()
            if "404" in err_msg or "withdrawn" in err_msg:
                paper.screening_status = 'withdrawn'
                paper.screening_reasoning = f"Paper withdrawn by authors or unavailable at source ({e})."
                paper.save(update_fields=['screening_status', 'screening_reasoning'])
                logger.info(f"⏭️ [WITHDRAWN 404] Paper '{title_snippet}...' marked as withdrawn ({e})")
                return {
                    "status": "withdrawn",
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "reason": paper.screening_reasoning
                }

            last_error = e
            if attempt < max_attempts:
                delay = (2 ** attempt) + (0.1 * attempt)
                logger.warning(f"⚠️ [DOWNLOAD RETRY {attempt}/{max_attempts}] Paper '{title_snippet}...' failed downloading from '{pdf_source_url}': {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                logger.warning(f"❌ [DOWNLOAD FAILED] Error downloading PDF for paper '{title_snippet}...' after {max_attempts} attempts: {e}")
                return {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": str(e)}


@shared_task(bind=True)
def execute_pdf_download_job(self, component_run_id: str, limit: int = 50, max_workers: int = 8):
    """
    Celery worker task executing Step 2 (PDF Binary Download) for papers in a ComponentRun job.
    Downloads PDF binaries concurrently using a ThreadPoolExecutor.
    """
    try:
        component_run = ComponentRun.objects.select_related('pipeline_run', 'pipeline_run__workspace').get(pk=component_run_id)
    except ComponentRun.DoesNotExist:
        logger.error(f"ComponentRun '{component_run_id}' not found.")
        return False

    pipeline_run = component_run.pipeline_run
    workspace = pipeline_run.workspace

    component_run.status = 'running'
    component_run.celery_task_id = getattr(self.request, 'id', None)
    component_run.started_at = timezone.now()
    component_run.save(update_fields=['status', 'celery_task_id', 'started_at'])

    worker_concurrency = int(os.environ.get("DOWNLOAD_PARALLEL_WORKERS", max_workers))

    # SQLite (used in unit tests) does not support multi-threaded write locks
    if connection.vendor == 'sqlite':
        worker_concurrency = 1

    try:
        start_time = time.time()
        papers = list(Paper.objects.filter(pipeline_run=pipeline_run)[:limit])
        downloaded_count = 0
        skipped_count = 0
        withdrawn_count = 0
        failed_count = 0
        downloaded_papers_summary = []

        logger.info(f"🚀 [PARALLEL PDF DOWNLOAD START] Processing {len(papers)} papers using {worker_concurrency} parallel threads...")

        def _record_result(res):
            nonlocal downloaded_count, skipped_count, withdrawn_count, failed_count
            st = res.get("status")
            if st == "downloaded":
                downloaded_count += 1
                downloaded_papers_summary.append(res)
            elif st in ["already_stored", "already_exists"]:
                skipped_count += 1
                downloaded_papers_summary.append(res)
            elif st == "withdrawn":
                withdrawn_count += 1
                downloaded_papers_summary.append(res)
            else:
                failed_count += 1

        if worker_concurrency <= 1:
            for paper in papers:
                res = _download_paper_task(paper, workspace, pipeline_run)
                _record_result(res)
        else:
            with ThreadPoolExecutor(max_workers=worker_concurrency) as executor:
                future_to_paper = {
                    executor.submit(_download_paper_task, paper, workspace, pipeline_run): paper
                    for paper in papers
                }
                for future in as_completed(future_to_paper):
                    paper = future_to_paper[future]
                    try:
                        res = future.result()
                    except Exception as fe:
                        logger.error(f"Thread execution error downloading PDF for paper '{paper.id}': {fe}")
                        res = {"status": "failed", "paper_id": str(paper.id), "title": paper.title, "error": str(fe)}
                    _record_result(res)

        # Update component run lifecycle metrics & output_data
        duration_sec = round(time.time() - start_time, 2)
        component_run.metrics = {
            "total_processed": len(papers),
            "downloaded": downloaded_count,
            "skipped": skipped_count,
            "withdrawn": withdrawn_count,
            "failed": failed_count,
            "total_duration_seconds": duration_sec
        }
        component_run.output_data = {
            "summary": f"Downloaded {downloaded_count} PDFs, skipped {skipped_count} existing, {withdrawn_count} withdrawn, {failed_count} failed in {duration_sec}s.",
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


@shared_task
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
