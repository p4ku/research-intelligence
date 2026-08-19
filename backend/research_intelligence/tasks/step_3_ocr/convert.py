import os
import time
import tempfile
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery import shared_task
from django.db import connection, close_old_connections
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from ...models import Workspace, Paper, PipelineRun, ComponentRun
from ...ocr_providers.factory import get_ocr_provider

logger = logging.getLogger(__name__)


@shared_task
def run_ocr_conversion(paper_id, output_format="markdown", paper_obj=None):
    """
    Downloads the paper PDF from storage, parses it into text using the Workspace's configured OCR provider,
    and saves the resulting layout (Markdown or HTML) back to storage.
    """
    try:
        paper = paper_obj or Paper.objects.get(pk=paper_id)
        if not paper.original_pdf_path:
            logger.warning(f"Paper {paper_id} has no source PDF path configured. Cannot run OCR.")
            return {"success": False, "error": "No original PDF path"}

        if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
            logger.info(f"Paper {paper_id} is already converted to {output_format} at {paper.converted_md_path}")
            return {"success": True, "already_exists": True, "storage_path": paper.converted_md_path}

        # Priority storage path: workspaces/{workspace_id}/runs/{pipeline_run_id}/documents/{hash_id}/ocr.md
        if paper.pipeline_run and paper.hash_id:
            doc_folder = f"workspaces/{paper.workspace.id}/runs/{paper.pipeline_run.id}/documents/{paper.hash_id}"
            target_path = f"{doc_folder}/ocr.md"
        elif paper.workspace_id and paper.hash_id:
            target_path = f"workspaces/{paper.workspace.id}/documents/{paper.hash_id}/ocr.md"
        else:
            target_path = f"workspaces/{paper.workspace_id}/documents/{paper.id}/ocr.md"

        if default_storage.exists(target_path):
            paper.converted_md_path = target_path
            paper.save(update_fields=['converted_md_path'])
            return {"success": True, "already_exists": True, "storage_path": target_path}

        logger.info(f"Starting OCR conversion for paper {paper.id} from {paper.original_pdf_path} using {paper.workspace.ocr_provider}")

        # 1. Download PDF to a local temporary file
        with default_storage.open(paper.original_pdf_path, 'rb') as pdf_file:
            pdf_bytes = pdf_file.read()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        # 2. Extract text using configured OCR Provider with retries
        max_attempts = 3
        converted_content = None
        for attempt in range(1, max_attempts + 1):
            try:
                provider = get_ocr_provider(paper.workspace.ocr_provider)
                converted_content = provider.convert(temp_pdf_path, title=paper.title, output_format=output_format)
                if converted_content:
                    break
            except Exception as parse_err:
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
                else:
                    logger.error(f"Failed to parse PDF {temp_pdf_path} for paper {paper.id}: {str(parse_err)}")
                    if os.path.exists(temp_pdf_path):
                        os.remove(temp_pdf_path)
                    return {"success": False, "error": str(parse_err)}

        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

        if not converted_content:
            return {"success": False, "error": "Empty OCR output"}

        # 3. Save converted output to storage
        saved_path = default_storage.save(target_path, ContentFile(converted_content.encode("utf-8")))

        # 4. Update Paper model
        paper.converted_md_path = saved_path
        paper.save(update_fields=['converted_md_path'])

        logger.info(f"Successfully converted paper {paper.id} to Markdown at {saved_path}")
        return {"success": True, "already_exists": False, "storage_path": saved_path, "character_count": len(converted_content)}

    except Paper.DoesNotExist:
        logger.error(f"Paper {paper_id} does not exist.")
        return {"success": False, "error": "Paper does not exist"}
    except Exception as e:
        logger.exception(f"Error during OCR conversion for paper {paper_id}: {str(e)}")
        return {"success": False, "error": str(e)}


def _ocr_paper_task(paper):
    close_old_connections()
    res = run_ocr_conversion(paper.id, paper_obj=paper)
    return paper, res


@shared_task(bind=True)
def execute_ocr_job(self, component_run_id: str, limit: int = 50, max_workers: int = 8):
    """
    Celery worker task executing Step 3 (Layout OCR Extraction) for papers in a ComponentRun job.
    Executes OCR conversion concurrently using a ThreadPoolExecutor.
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

    job_t0 = time.time()
    worker_concurrency = int(os.environ.get("OCR_PARALLEL_WORKERS", max_workers))

    if connection.vendor == 'sqlite':
        worker_concurrency = 1

    try:
        papers_qs = Paper.objects.filter(
            pipeline_run=pipeline_run,
            original_pdf_path__isnull=False
        ).exclude(screening_status='withdrawn')

        papers = list(papers_qs[:limit])
        converted_count = 0
        skipped_count = 0
        failed_count = 0
        ocr_summary = []

        logger.info(f"🚀 [PARALLEL OCR START] Processing {len(papers)} papers using {worker_concurrency} parallel threads ({workspace.ocr_provider})...")

        def _record_result(paper, res):
            nonlocal converted_count, skipped_count, failed_count
            title_snippet = paper.title[:50] if paper.title else "Untitled"
            if res.get("success"):
                if res.get("already_exists"):
                    skipped_count += 1
                    logger.info(f"⏩ [SKIPPED OCR] Already converted: '{title_snippet}...'")
                else:
                    converted_count += 1
                    logger.info(f"✅ [OCR CONVERTED] Paper '{title_snippet}...' -> {res.get('storage_path')}")
                ocr_summary.append({
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "status": "already_exists" if res.get("already_exists") else "converted",
                    "storage_path": res.get("storage_path")
                })
            else:
                failed_count += 1
                logger.warning(f"⚠️ [OCR FAILED] Paper '{title_snippet}...': {res.get('error')}")

        if worker_concurrency <= 1:
            for paper in papers:
                res = run_ocr_conversion(paper.id, paper_obj=paper)
                _record_result(paper, res)
        else:
            with ThreadPoolExecutor(max_workers=worker_concurrency) as executor:
                future_to_paper = {
                    executor.submit(_ocr_paper_task, paper): paper
                    for paper in papers
                }
                for future in as_completed(future_to_paper):
                    paper = future_to_paper[future]
                    try:
                        _, res = future.result()
                    except Exception as fe:
                        logger.error(f"Thread execution error converting OCR for paper '{paper.id}': {fe}")
                        res = {"success": False, "error": str(fe)}
                    _record_result(paper, res)

        job_duration_sec = round(time.time() - job_t0, 3)

        component_run.metrics = {
            "ocr_provider": workspace.ocr_provider,
            "parallel_workers": worker_concurrency,
            "total_processed": len(papers),
            "converted": converted_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "duration_seconds": job_duration_sec
        }
        component_run.output_data = {
            "summary": f"Converted {converted_count} PDFs to Markdown using {workspace.ocr_provider}, skipped {skipped_count} existing, {failed_count} failed in {job_duration_sec}s.",
            "converted_papers": ocr_summary
        }
        component_run.raw_storage_path = f"workspaces/{workspace.id}/runs/{pipeline_run.id}/documents/"
        component_run.status = 'completed'
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['metrics', 'output_data', 'raw_storage_path', 'status', 'completed_at'])

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
        logger.exception(f"Fatal error in execute_ocr_job '{component_run_id}': {e}")
        component_run.status = 'failed'
        component_run.error_message = str(e)
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['status', 'error_message', 'completed_at'])

        pipeline_run.status = 'failed'
        pipeline_run.save(update_fields=['status'])

        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return False
