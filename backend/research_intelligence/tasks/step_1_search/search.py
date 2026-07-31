import json
import logging
import hashlib
import re
from celery import shared_task
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from ...models import Workspace, Paper, PipelineRun, ComponentRun, Scraper
from ...scrapers import get_scraper_provider

logger = logging.getLogger(__name__)


def normalize_doi(doi: str) -> str:
    """Strips protocol prefix, doi.org base URL, spaces and converts to lowercase."""
    if not doi:
        return ""
    doi = doi.lower().strip()
    for prefix in ["https://doi.org/", "http://doi.org/", "doi.org/", "doi:"]:
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def normalize_arxiv_id(arxiv_id: str) -> str:
    """Strips 'arxiv:' prefix and version suffix (e.g., 'v1', 'v2') and lowercases."""
    if not arxiv_id:
        return ""
    arxiv_id = arxiv_id.lower().strip()
    if arxiv_id.startswith("arxiv:"):
        arxiv_id = arxiv_id[6:]
    arxiv_id = re.sub(r'v\d+$', '', arxiv_id)
    return arxiv_id


def normalize_title(title: str) -> str:
    """Converts to lowercase and retains only alphanumeric characters."""
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r'[^a-z0-9]', '', title)
    return title


@shared_task(bind=True)
def execute_scraper_run_job(self, component_run_id: str, limit: int = 50):
    """
    Celery worker task executing an individual scraping ComponentRun job.
    Stores raw scraped payload in Django default_storage, updates ComponentRun lifecycle
    (running, completed, failed, aborted), deduplicates papers, and registers new Paper records.
    """
    try:
        component_run = ComponentRun.objects.select_related('pipeline_run', 'scraper', 'scraper__workspace').get(pk=component_run_id)
    except ComponentRun.DoesNotExist:
        logger.error(f"ComponentRun with ID '{component_run_id}' not found.")
        return False

    # Check if already aborted before execution starts
    if component_run.status == 'aborted':
        logger.info(f"ComponentRun '{component_run_id}' was aborted before task start.")
        return False

    pipeline_run = component_run.pipeline_run
    scraper = component_run.scraper
    if not scraper:
        logger.error(f"ComponentRun '{component_run_id}' has no associated scraper.")
        return False

    workspace = scraper.workspace

    # Record Celery Task ID and update status to running
    task_id = self.request.id if getattr(self, 'request', None) and self.request.id else "local_execution"
    component_run.celery_task_id = task_id
    component_run.status = 'running'
    component_run.save(update_fields=['celery_task_id', 'status'])

    if pipeline_run.status != 'running':
        pipeline_run.status = 'running'
        pipeline_run.save(update_fields=['status'])

    logger.info(f"Starting ComponentRun '{component_run.id}' (Step: {component_run.step_type}, Component: {component_run.component_name}, Query: '{scraper.search_query}')")

    try:
        provider = get_scraper_provider(scraper.provider)
        results = provider.search(scraper.search_query, limit=limit)
        
        # 1. Save raw response payload in Django default_storage (Orthogonal Path Structure)
        raw_storage_path = f"workspaces/{workspace.id}/runs/{pipeline_run.id}/scrapes/{scraper.provider}/{component_run.id}_raw.json"
        if default_storage.exists(raw_storage_path):
            default_storage.delete(raw_storage_path)
            
        raw_content = json.dumps(results, indent=2, ensure_ascii=False)
        default_storage.save(raw_storage_path, ContentFile(raw_content.encode('utf-8')))

        component_run.raw_storage_path = raw_storage_path
        component_run.metrics['total_fetched'] = len(results)
        component_run.save(update_fields=['raw_storage_path', 'metrics'])

        # 2. Prepare in-memory deduplication index
        existing_papers = list(Paper.objects.filter(workspace_id=workspace.id).values("title", "doi", "arxiv_id"))
        existing_normalized_dois = {normalize_doi(p["doi"]) for p in existing_papers if p.get("doi")}
        existing_normalized_arxiv_ids = {normalize_arxiv_id(p["arxiv_id"]) for p in existing_papers if p.get("arxiv_id")}
        existing_normalized_titles = {normalize_title(p["title"]) for p in existing_papers if p.get("title")}

        created_count = 0
        skipped_count = 0
        created_paper_ids = []
        for item in results:
            # Re-check abort status mid-loop
            component_run.refresh_from_db(fields=['status'])
            if component_run.status == 'aborted':
                logger.warning(f"ComponentRun '{component_run_id}' was aborted during item processing.")
                return False

            arxiv_id = item.get('arxiv_id') or (item.get('hash_id') if item.get('source_database') == 'arxiv' else None)
            doi = item.get('doi') or (item.get('other_url') if 'doi.org' in item.get('other_url', '') else None)
            title = item['title']

            norm_doi = normalize_doi(doi)
            norm_arxiv = normalize_arxiv_id(arxiv_id)
            norm_title = normalize_title(title)

            is_duplicate = False
            if norm_doi and norm_doi in existing_normalized_dois:
                is_duplicate = True
            if norm_arxiv and norm_arxiv in existing_normalized_arxiv_ids:
                is_duplicate = True
            if norm_title and norm_title in existing_normalized_titles:
                is_duplicate = True

            if is_duplicate:
                skipped_count += 1
                continue

            clean_doi = norm_doi if norm_doi else doi
            clean_arxiv = norm_arxiv if norm_arxiv else arxiv_id
            unique_hash = hashlib.sha256(f"{item['source_database']}:{item['hash_id']}".encode()).hexdigest()

            # Save individual document metadata in default_storage
            doc_meta_path = f"workspaces/{workspace.id}/runs/{pipeline_run.id}/documents/{unique_hash}/metadata.json"
            if not default_storage.exists(doc_meta_path):
                default_storage.save(doc_meta_path, ContentFile(json.dumps(item, indent=2).encode('utf-8')))

            is_withdrawn = item.get('is_withdrawn', False)
            screening_status = 'withdrawn' if is_withdrawn else 'pending'
            screening_reasoning = item.get('withdrawn_reason', '') if is_withdrawn else None

            paper, created = Paper.objects.get_or_create(
                hash_id=unique_hash,
                defaults={
                    "workspace": workspace,
                    "pipeline_run": pipeline_run,
                    "arxiv_id": clean_arxiv,
                    "doi": clean_doi,
                    "title": title,
                    "authors": item.get('authors', ''),
                    "abstract": item.get('abstract', ''),
                    "source_database": item.get('source_database', 'arxiv'),
                    "original_pdf_path": item.get('pdf_url', '') or item.get('original_pdf_path', ''),
                    "screening_status": screening_status,
                    "screening_reasoning": screening_reasoning
                }
            )

            if created:
                created_count += 1
                created_paper_ids.append(str(paper.id))
                if norm_doi:
                    existing_normalized_dois.add(norm_doi)
                if norm_arxiv:
                    existing_normalized_arxiv_ids.add(norm_arxiv)
                if norm_title:
                    existing_normalized_titles.add(norm_title)
            else:
                skipped_count += 1

        # Build preview of top fetched papers for output_data
        fetched_papers_sample = []
        for r in results[:10]:
            fetched_papers_sample.append({
                "title": r.get("title"),
                "authors": r.get("authors"),
                "source_database": r.get("source_database"),
                "pdf_url": r.get("pdf_url"),
                "abstract_preview": (r.get("abstract")[:150] + "...") if r.get("abstract") and len(r.get("abstract")) > 150 else r.get("abstract")
            })

        # Update component run lifecycle metrics & output_data
        component_run.metrics['total_created'] = created_count
        component_run.metrics['total_duplicates_skipped'] = skipped_count
        component_run.output_data = {
            "total_results": len(results),
            "created_paper_ids": created_paper_ids,
            "raw_storage_path": raw_storage_path,
            "papers_preview": fetched_papers_sample
        }
        component_run.status = 'completed'
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['metrics', 'output_data', 'status', 'completed_at'])

        # Update aggregated PipelineRun metrics
        pipeline_run.refresh_from_db()
        pending_or_running = ComponentRun.objects.filter(pipeline_run_id=pipeline_run.id, status__in=['pending', 'running']).exists()
        has_failed = ComponentRun.objects.filter(pipeline_run_id=pipeline_run.id, status='failed').exists()
        has_aborted = ComponentRun.objects.filter(pipeline_run_id=pipeline_run.id, status='aborted').exists()

        if not pending_or_running:
            if has_failed:
                pipeline_run.status = 'failed'
            elif has_aborted:
                pipeline_run.status = 'aborted'
            else:
                pipeline_run.status = 'completed'
            pipeline_run.completed_at = timezone.now()

        pipeline_run.total_papers_fetched = Paper.objects.filter(pipeline_run_id=pipeline_run.id).count()
        pipeline_run.save(update_fields=['total_papers_fetched', 'status', 'completed_at'])

        logger.info(f"Completed ComponentRun '{component_run_id}'. Fetched: {len(results)}, Created: {created_count}, Skipped: {skipped_count}.")
        return True

    except Exception as e:
        logger.exception(f"Error in ComponentRun '{component_run_id}': {e}")
        component_run.status = 'failed'
        component_run.error_message = str(e)
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['status', 'error_message', 'completed_at'])

        pipeline_run.status = 'failed'
        pipeline_run.save(update_fields=['status'])
        return False


@shared_task
def execute_workspace_search(workspace_id, pipeline_run_id, limit=50):
    """
    Backwards-compatible consolidated search task that launches ComponentRun jobs
    for all active scrapers in the workspace.
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
        pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id)
    except (Workspace.DoesNotExist, PipelineRun.DoesNotExist):
        return []

    created_ids = []
    active_scrapers = workspace.scrapers.filter(is_active=True)
    for scraper in active_scrapers:
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type='search',
            component_name=f"{scraper.provider}_scraper",
            scraper=scraper,
            status='pending',
            input_params={"limit": limit, "search_query": scraper.search_query}
        )
        execute_scraper_run_job(str(comp_run.id), limit=limit)
        comp_run.refresh_from_db()
        if comp_run.output_data and "created_paper_ids" in comp_run.output_data:
            created_ids.extend(comp_run.output_data["created_paper_ids"])

    return created_ids
