import logging
import hashlib
import re
from celery import shared_task
from ...models import Workspace, Paper, PipelineRun
from ...scrapers import get_scraper_provider

logger = logging.getLogger(__name__)

def normalize_doi(doi: str) -> str:
    """
    Strips protocol prefix, doi.org base URL, spaces and converts to lowercase.
    """
    if not doi:
        return ""
    doi = doi.lower().strip()
    for prefix in ["https://doi.org/", "http://doi.org/", "doi.org/", "doi:"]:
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi

def normalize_arxiv_id(arxiv_id: str) -> str:
    """
    Strips 'arxiv:' prefix and version suffix (e.g., 'v1', 'v2') and lowercases.
    """
    if not arxiv_id:
        return ""
    arxiv_id = arxiv_id.lower().strip()
    if arxiv_id.startswith("arxiv:"):
        arxiv_id = arxiv_id[6:]
    arxiv_id = re.sub(r'v\d+$', '', arxiv_id)
    return arxiv_id

def normalize_title(title: str) -> str:
    """
    Converts to lowercase and retains only alphanumeric characters.
    """
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r'[^a-z0-9]', '', title)
    return title

@shared_task
def execute_workspace_search(workspace_id, pipeline_run_id, limit=50):
    """
    Consolidated search task that iterates over all active scrapers in the workspace,
    performs the searches using resolved providers, and saves unique paper metadata.
    Includes state-of-the-art pre-creation deduplication based on normalized titles,
    DOIs, and arXiv IDs.
    """
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
        pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id)
        
        active_scrapers = workspace.scrapers.filter(is_active=True)
        if not active_scrapers.exists():
            logger.info(f"No active scrapers configured for workspace {workspace_id}.")
            return []
            
        # Fetch existing workspace paper identifiers for in-memory deduplication checks
        existing_papers = Paper.objects.filter(workspace=workspace).only("title", "doi", "arxiv_id")
        existing_normalized_dois = {normalize_doi(p.doi) for p in existing_papers if p.doi}
        existing_normalized_arxiv_ids = {normalize_arxiv_id(p.arxiv_id) for p in existing_papers if p.arxiv_id}
        existing_normalized_titles = {normalize_title(p.title) for p in existing_papers if p.title}
        
        papers_created = []
        for scraper in active_scrapers:
            logger.info(f"Executing search for provider '{scraper.provider}' with query: '{scraper.search_query}'")
            try:
                provider = get_scraper_provider(scraper.provider)
                results = provider.search(scraper.search_query, limit=limit)
                
                for item in results:
                    arxiv_id = item['hash_id'] if item['source_database'] == 'arxiv' else None
                    doi = item['other_url'] if 'doi.org' in item['other_url'] else None
                    title = item['title']
                    
                    # Normalize incoming parameters
                    norm_doi = normalize_doi(doi)
                    norm_arxiv = normalize_arxiv_id(arxiv_id)
                    norm_title = normalize_title(title)
                    
                    # Deduplication Check
                    is_duplicate = False
                    if norm_doi and norm_doi in existing_normalized_dois:
                        is_duplicate = True
                        logger.info(f"Deduplicated paper by DOI '{doi}': '{title}'")
                    elif norm_arxiv and norm_arxiv in existing_normalized_arxiv_ids:
                        is_duplicate = True
                        logger.info(f"Deduplicated paper by arXiv ID '{arxiv_id}': '{title}'")
                    elif norm_title and norm_title in existing_normalized_titles:
                        is_duplicate = True
                        logger.info(f"Deduplicated paper by Title: '{title}'")
                        
                    if is_duplicate:
                        continue
                        
                    # Save clean normalized values
                    clean_doi = norm_doi if norm_doi else doi
                    clean_arxiv = norm_arxiv if norm_arxiv else arxiv_id
                    
                    unique_hash = hashlib.sha256(f"{item['source_database']}:{item['hash_id']}".encode()).hexdigest()
                    
                    paper, created = Paper.objects.get_or_create(
                        hash_id=unique_hash,
                        defaults={
                            "workspace": workspace,
                            "pipeline_run": pipeline_run,
                            "arxiv_id": clean_arxiv,
                            "doi": clean_doi,
                            "title": title,
                            "authors": item['authors'],
                            "abstract": item['abstract'],
                            "source_database": item['source_database'],
                            "original_pdf_path": item['pdf_url'],
                        }
                    )
                    if created:
                        papers_created.append(str(paper.id))
                        # Add newly created paper identifiers to the checking sets
                        if norm_doi:
                            existing_normalized_dois.add(norm_doi)
                        if norm_arxiv:
                            existing_normalized_arxiv_ids.add(norm_arxiv)
                        if norm_title:
                            existing_normalized_titles.add(norm_title)
            except Exception as scraper_err:
                logger.error(f"Error querying provider {scraper.provider}: {str(scraper_err)}")
                
        logger.info(f"Completed workspace search. Ingested {len(papers_created)} new papers.")
        return papers_created
    except Exception as e:
        logger.exception(f"Error executing workspace search: {str(e)}")
        return []
