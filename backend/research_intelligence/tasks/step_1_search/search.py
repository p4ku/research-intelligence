import json
import logging
import hashlib
import re
import time
from typing import Optional, Dict, Any, List
from celery import shared_task
from django.utils import timezone
from django.db import connection, close_old_connections, transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from ...models import Workspace, Paper, PaperMetric, PipelineRun, ComponentRun, Scraper
from ...scrapers import get_scraper_provider

logger = logging.getLogger(__name__)


from .dedup import normalize_doi, normalize_arxiv_id, normalize_title, one_line


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=2, default_retry_delay=10)
def execute_scraper_run_job(self, component_run_id: str, limit: Optional[int] = None):
    """
    Celery worker task executing an individual scraping ComponentRun job.
    Stores raw scraped payload in Django default_storage, updates ComponentRun lifecycle
    (running, completed, failed, aborted), deduplicates papers, and registers new Paper records.
    """
    component_run = None
    for attempt in range(4):
        try:
            close_old_connections()
            component_run = ComponentRun.objects.select_related('pipeline_run', 'scraper', 'scraper__workspace').get(pk=component_run_id)
            break
        except ComponentRun.DoesNotExist:
            if attempt < 3:
                time.sleep(0.5)
            else:
                logger.error(f"ComponentRun with ID '{component_run_id}' not found after 4 attempts.")
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

    # Record Celery Task ID and update status to running, resetting started_at and completed_at
    task_id = self.request.id if getattr(self, 'request', None) and self.request.id else "local_execution"
    component_run.celery_task_id = task_id
    component_run.status = 'running'
    component_run.started_at = timezone.now()
    component_run.completed_at = None
    component_run.error_message = ''
    component_run.save(update_fields=['celery_task_id', 'status', 'started_at', 'completed_at', 'error_message'])

    if pipeline_run.status != 'running':
        pipeline_run.status = 'running'
        pipeline_run.save(update_fields=['status'])

    logger.info(f"Starting ComponentRun '{component_run.id}' (Step: {component_run.step_type}, Component: {component_run.component_name}, Query: '{scraper.search_query}')")

    try:
        start_time = time.time()
        input_params = component_run.input_params or {}
        config_override = getattr(pipeline_run, 'configuration_override', {}) or {}

        start_date = input_params.get('start_date') or config_override.get('start_date')
        end_date = input_params.get('end_date') or config_override.get('end_date')
        n_last_days_raw = input_params.get('n_last_days')
        if n_last_days_raw is None:
            n_last_days_raw = config_override.get('n_last_days')
        if n_last_days_raw is None:
            n_last_days_raw = getattr(scraper, 'n_last_days', 7)
        try:
            n_last_days = int(n_last_days_raw) if n_last_days_raw is not None else 7
        except (ValueError, TypeError):
            n_last_days = 7

        provider = get_scraper_provider(scraper.provider, n_last_days=n_last_days)
        final_limit = limit if limit is not None else (getattr(scraper, 'limit', 50) or 50)
        sort_by = getattr(scraper, 'sort_by', 'relevance')
        sort_order = getattr(scraper, 'sort_order', 'desc')

        logger.info(
            f"🔎 [SEARCH START] Querying '{scraper.provider}' for workspace '{workspace.name}' | "
            f"Limit: {final_limit} | Sort: {sort_by} ({sort_order}) | "
            f"Date Range: {start_date} to {end_date} (n_last_days={n_last_days}) | "
            f"Query: {scraper.search_query[:120]}..."
        )

        results = provider.search(
            scraper.search_query,
            limit=final_limit,
            sort_by=sort_by,
            sort_order=sort_order,
            start_date=start_date,
            end_date=end_date,
            n_last_days=n_last_days
        )
        fetch_elapsed = round(time.time() - start_time, 2)
        logger.info(f"📦 [SEARCH FETCHED] Provider '{scraper.provider}' returned {len(results)} candidate papers in {fetch_elapsed}s.")
        
        # 1. Update component run metrics
        component_run.metrics['total_fetched'] = len(results)
        component_run.save(update_fields=['metrics'])

        # 2. Prepare in-memory deduplication index
        existing_papers = list(Paper.objects.filter(workspace_id=workspace.id).values("title", "doi", "arxiv_id"))
        existing_normalized_dois = {normalize_doi(p["doi"]) for p in existing_papers if p.get("doi")}
        existing_normalized_arxiv_ids = {normalize_arxiv_id(p["arxiv_id"]) for p in existing_papers if p.get("arxiv_id")}
        existing_normalized_titles = {normalize_title(p["title"]) for p in existing_papers if p.get("title")}

        logger.info(f"💾 [INGESTION] Starting deduplication against {len(existing_papers)} existing workspace papers...")

        created_count = 0
        skipped_count = 0
        created_paper_ids = []
        total_items = len(results)

        for idx, item in enumerate(results):
            # Periodically re-check abort status mid-loop
            if idx % 10 == 0:
                component_run.refresh_from_db(fields=['status'])
                if component_run.status == 'aborted':
                    logger.warning(f"ComponentRun '{component_run_id}' was aborted during item processing.")
                    return False

            arxiv_id = item.get('arxiv_id') or (item.get('hash_id') if item.get('source_database') == 'arxiv' else None)
            doi = item.get('doi') or (item.get('other_url') if 'doi.org' in item.get('other_url', '') else None)
            # Normalized here, once, rather than in each provider: every source
            # reaches the corpus through this loop.
            title = one_line(item['title'])

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
                clean_doi = norm_doi if norm_doi else doi
                clean_arxiv = norm_arxiv if norm_arxiv else arxiv_id
                from django.db.models import Q
                conds = Q(workspace=workspace)
                match_q = Q()
                if norm_doi:
                    match_q |= Q(doi__iexact=clean_doi)
                if norm_arxiv:
                    match_q |= Q(arxiv_id__iexact=clean_arxiv)
                if norm_title:
                    # Rows ingested before titles were single-lined still hold
                    # the provider's raw wrap; match either spelling so they
                    # keep receiving the DOI/arXiv/PDF backfill below.
                    match_q |= Q(title__iexact=title) | Q(title__iexact=item['title'])

                with transaction.atomic():
                    existing_p = Paper.objects.filter(conds & match_q).first()
                    if existing_p:
                        # Enrich existing paper with any newly found fields
                        updated_fields = []
                        if not existing_p.original_pdf_path and (item.get('pdf_url') or item.get('original_pdf_path')):
                            existing_p.original_pdf_path = item.get('pdf_url') or item.get('original_pdf_path')
                            updated_fields.append('original_pdf_path')
                        if not existing_p.doi and clean_doi:
                            existing_p.doi = clean_doi
                            updated_fields.append('doi')
                        if not existing_p.arxiv_id and clean_arxiv:
                            existing_p.arxiv_id = clean_arxiv
                            updated_fields.append('arxiv_id')
                        if not existing_p.meta and item.get('meta'):
                            existing_p.meta = item.get('meta')
                            updated_fields.append('meta')
                        clean_source = item.get('other_url') or (f"https://doi.org/{clean_doi}" if clean_doi else None) or (f"https://arxiv.org/abs/{clean_arxiv}" if clean_arxiv else None) or item.get('pdf_url')
                        if not existing_p.source_url and clean_source:
                            existing_p.source_url = clean_source[:1024]
                            updated_fields.append('source_url')
                        if updated_fields:
                            existing_p.save(update_fields=updated_fields)

                        if getattr(pipeline_run, 'reprocess_existing', False):
                            PaperMetric.objects.get_or_create(
                                paper=existing_p,
                                pipeline_run=pipeline_run,
                                defaults={'workspace': workspace, 'screening_status': 'pending'}
                            )
                            created_count += 1
                            created_paper_ids.append(str(existing_p.id))
                            continue
                skipped_count += 1
                continue

            clean_doi = norm_doi if norm_doi else doi
            clean_arxiv = norm_arxiv if norm_arxiv else arxiv_id
            
            # Canonical unique hash across providers to prevent duplicates when multiple scrapers run in parallel
            if norm_doi:
                unique_hash = hashlib.sha256(f"{workspace.id}:doi:{norm_doi}".encode()).hexdigest()
            elif norm_arxiv:
                unique_hash = hashlib.sha256(f"{workspace.id}:arxiv:{norm_arxiv}".encode()).hexdigest()
            elif norm_title:
                unique_hash = hashlib.sha256(f"{workspace.id}:title:{norm_title}".encode()).hexdigest()
            else:
                unique_hash = hashlib.sha256(f"{workspace.id}:{item['source_database']}:{item['hash_id']}".encode()).hexdigest()

            is_withdrawn = item.get('is_withdrawn', False)
            screening_status = 'withdrawn' if is_withdrawn else 'pending'
            screening_reasoning = item.get('withdrawn_reason', '') if is_withdrawn else None

            with transaction.atomic():
                from django.db.models import Q
                match_q = Q(hash_id=unique_hash)
                if norm_doi:
                    match_q |= Q(doi__iexact=clean_doi)
                if norm_arxiv:
                    match_q |= Q(arxiv_id__iexact=clean_arxiv)
                if norm_title:
                    # Rows ingested before titles were single-lined still hold
                    # the provider's raw wrap; match either spelling so they
                    # keep receiving the DOI/arXiv/PDF backfill below.
                    match_q |= Q(title__iexact=title) | Q(title__iexact=item['title'])

                paper = Paper.objects.filter(Q(workspace=workspace) & match_q).first()
                if paper:
                    created = False
                    updated_fields = []
                    if not paper.original_pdf_path and (item.get('pdf_url') or item.get('original_pdf_path')):
                        paper.original_pdf_path = item.get('pdf_url') or item.get('original_pdf_path')
                        updated_fields.append('original_pdf_path')
                    if not paper.doi and clean_doi:
                        paper.doi = clean_doi
                        updated_fields.append('doi')
                    if not paper.arxiv_id and clean_arxiv:
                        paper.arxiv_id = clean_arxiv
                        updated_fields.append('arxiv_id')
                    if not paper.meta and item.get('meta'):
                        paper.meta = item.get('meta')
                        updated_fields.append('meta')
                    clean_source = item.get('other_url') or (f"https://doi.org/{clean_doi}" if clean_doi else None) or (f"https://arxiv.org/abs/{clean_arxiv}" if clean_arxiv else None) or item.get('pdf_url')
                    if not paper.source_url and clean_source:
                        paper.source_url = clean_source[:1024]
                        updated_fields.append('source_url')
                    if updated_fields:
                        paper.save(update_fields=updated_fields)
                else:
                    clean_source = item.get('other_url') or (f"https://doi.org/{clean_doi}" if clean_doi else None) or (f"https://arxiv.org/abs/{clean_arxiv}" if clean_arxiv else None) or item.get('pdf_url')
                    paper, created = Paper.objects.get_or_create(
                        workspace=workspace,
                        hash_id=unique_hash,
                        defaults={
                            "arxiv_id": clean_arxiv,
                            "doi": clean_doi,
                            "title": title,
                            "authors": item.get('authors', ''),
                            "abstract": one_line(item.get('abstract', '')),
                            "source_database": item.get('source_database', 'arxiv'),
                            "source_url": clean_source[:1024] if clean_source else None,
                            "original_pdf_path": item.get('pdf_url', '') or item.get('original_pdf_path', ''),
                            "meta": item.get('meta') or {}
                        }
                    )

                if not created and item.get('meta') and not paper.meta:
                    paper.meta = item.get('meta')
                    paper.save(update_fields=['meta'])
                if paper.document_registry and not paper.document_registry.meta and paper.meta:
                    paper.document_registry.meta = paper.meta
                    paper.document_registry.save(update_fields=['meta'])

                PaperMetric.objects.get_or_create(
                    paper=paper,
                    pipeline_run=pipeline_run,
                    defaults={
                        'workspace': workspace,
                        'screening_status': screening_status,
                        'screening_reasoning': screening_reasoning
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

            if (idx + 1) % 25 == 0 or (idx + 1) == total_items:
                logger.info(f"💾 [INGESTION PROGRESS] Processed {idx + 1}/{total_items} papers ({created_count} new, {skipped_count} duplicates/skipped)...")

        # If reprocess_existing is True, ensure ALL existing workspace papers are linked to this active run
        if getattr(pipeline_run, 'reprocess_existing', False):
            existing_ws_papers = Paper.objects.filter(workspace=workspace)
            for ws_p in existing_ws_papers:
                pm, pm_created = PaperMetric.objects.get_or_create(
                    paper=ws_p,
                    pipeline_run=pipeline_run,
                    defaults={'workspace': workspace, 'screening_status': 'pending'}
                )
                if pm_created:
                    created_count += 1
                    created_paper_ids.append(str(ws_p.id))

        # Build complete list of all fetched papers for output_data
        fetched_papers_sample = []
        for r in results:
            preview_abstract = one_line(r.get("abstract"))
            fetched_papers_sample.append({
                "title": one_line(r.get("title")),
                "authors": r.get("authors"),
                "source_database": r.get("source_database"),
                "pdf_url": r.get("pdf_url"),
                "doi": r.get("doi"),
                "arxiv_id": r.get("arxiv_id") or r.get("hash_id"),
                "published_date": r.get("published_date"),
                "abstract_preview": (preview_abstract[:250] + "...") if len(preview_abstract) > 250 else preview_abstract
            })

        # Update component run lifecycle metrics & output_data
        duration_sec = round(time.time() - start_time, 2)
        component_run.metrics['total_fetched'] = len(results)
        component_run.metrics['total_created'] = created_count
        component_run.metrics['duplicates_count'] = skipped_count
        component_run.metrics['total_duration_seconds'] = duration_sec
        component_run.output_data = {
            "total_results": len(results),
            "total_created": created_count,
            "duplicates_count": skipped_count,
            "created_paper_ids": created_paper_ids,
            "papers_preview": fetched_papers_sample,
            "total_duration_seconds": duration_sec
        }
        component_run.status = 'completed'
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['metrics', 'output_data', 'status', 'completed_at'])

        # Update aggregated PipelineRun metrics
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

        pipeline_run.total_papers_fetched = pipeline_run.get_papers().count()
        pipeline_run.save(update_fields=['total_papers_fetched'])

        logger.info(f"Completed ComponentRun '{component_run_id}'. Fetched: {len(results)}, Created: {created_count}, Duplicates: {skipped_count}.")

        # Notify autonomous orchestrator to advance to next step
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return True

    except Exception as e:
        logger.exception(f"Error in ComponentRun '{component_run_id}': {e}")
        component_run.status = 'failed'
        component_run.error_message = str(e)
        component_run.completed_at = timezone.now()
        component_run.save(update_fields=['status', 'error_message', 'completed_at'])

        pipeline_run.refresh_from_db()
        sibling_runs = ComponentRun.objects.filter(pipeline_run_id=pipeline_run.id, step_type='search')
        has_pending = sibling_runs.filter(status__in=['pending', 'running']).exists()
        has_succeeded = sibling_runs.filter(status='completed').exists()
        total_ingested = pipeline_run.get_papers().count()

        # Only mark entire pipeline_run as failed if all sibling scrapers finished without ingesting any papers
        if not has_pending and not has_succeeded and total_ingested == 0:
            pipeline_run.status = 'failed'
            pipeline_run.save(update_fields=['status'])

        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        notify_pipeline_orchestrator_tick(pipeline_run)

        return False


@shared_task(acks_late=True, reject_on_worker_lost=True)
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
    config_override = getattr(pipeline_run, 'configuration_override', {}) or {}
    for scraper in active_scrapers:
        scraper_limit = limit if limit is not None else getattr(scraper, 'limit', 50)
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type='search',
            component_name=f"{scraper.provider}_scraper",
            scraper=scraper,
            status='pending',
            input_params={
                "limit": scraper_limit,
                "sort_by": getattr(scraper, 'sort_by', 'relevance'),
                "sort_order": getattr(scraper, 'sort_order', 'desc'),
                "search_query": scraper.search_query,
                "start_date": config_override.get('start_date'),
                "end_date": config_override.get('end_date'),
                "n_last_days": config_override.get('n_last_days') or getattr(scraper, 'n_last_days', 7)
            }
        )
        execute_scraper_run_job(str(comp_run.id), limit=scraper_limit)
        comp_run.refresh_from_db()
        if comp_run.output_data and "created_paper_ids" in comp_run.output_data:
            created_ids.extend(comp_run.output_data["created_paper_ids"])

    return created_ids
