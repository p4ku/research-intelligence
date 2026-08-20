import logging
from typing import Dict, Any, Optional, Tuple

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class SearchNode(BaseWorkflowNode):
    """
    Step 1: Multi-source search & paper ingestion (ArXiv, OpenAlex, Lens, PubMed).
    
    Inputs:
        - Active Scraper configurations on Workspace.
        - Parameters: 'limit' (int), 'reprocess_existing' (bool).
    Outputs:
        - Ingested & deduplicated Paper records attached to PipelineRun.
        - ComponentRun.metrics: total_found, ingested_new, duplicates_skipped.
    """
    name = "search"
    step_type = "search"
    component_name = "workspace_search"
    description = "Queries academic data sources (ArXiv, OpenAlex, Lens, PubMed) and deduplicates paper records."
    dependencies = []

    input_contract = {
        "scrapers": "List[Scraper] (workspace.scrapers.filter(is_active=True))",
        "limit": "Optional[int] (max papers to fetch per provider)",
        "reprocess_existing": "bool (if True, reuse already ingested workspace papers)",
    }

    output_contract = {
        "papers": "QuerySet[Paper] (ingested Paper objects with title, abstract, DOI, arXiv ID, PDF URL)",
        "component_run_metrics": {
            "total_found": "int",
            "ingested_new": "int",
            "duplicates_skipped": "int",
        },
    }

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        from research_intelligence.models import ComponentRun, Paper
        search_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='search')
        # Only check search halt condition if a search run was completed for this pipeline run
        if not search_runs.filter(status='completed').exists():
            return False, None

        reprocess = config.get("reprocess_existing", getattr(pipeline_run, 'reprocess_existing', False))
        if reprocess:
            papers_count = Paper.objects.filter(workspace=workspace).count()
        else:
            papers_count = pipeline_run.papers.count()

        if papers_count == 0:
            return True, f"Search completed but 0 papers were found matching criteria for workspace '{workspace.name}'. Halting pipeline."
        return False, None

    def execute(self, pipeline_run, comp_run, limit: Optional[int] = None) -> Any:
        from research_intelligence.models import ComponentRun
        from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job
        workspace = pipeline_run.workspace
        scrapers = list(workspace.scrapers.filter(is_active=True))

        if not scrapers:
            comp_run.status = 'failed'
            comp_run.error_message = f"No active scrapers configured for workspace '{workspace.name}'."
            comp_run.save(update_fields=['status', 'error_message'])
            return False

        first_scraper = scrapers[0]
        comp_run.scraper = first_scraper
        comp_run.component_name = f"{first_scraper.provider}_scraper"
        comp_run.save(update_fields=['scraper', 'component_name'])

        try:
            async_res = execute_scraper_run_job.delay(str(comp_run.id), limit=limit)
            comp_run.celery_task_id = async_res.id
            comp_run.save(update_fields=['celery_task_id'])

            for additional_scraper in scrapers[1:]:
                add_run = ComponentRun.objects.create(
                    pipeline_run=pipeline_run,
                    step_type='search',
                    component_name=f"{additional_scraper.provider}_scraper",
                    scraper=additional_scraper,
                    status='running',
                    input_params=comp_run.input_params
                )
                try:
                    add_async = execute_scraper_run_job.delay(str(add_run.id), limit=limit)
                    add_run.celery_task_id = add_async.id
                    add_run.save(update_fields=['celery_task_id'])
                except Exception:
                    execute_scraper_run_job(str(add_run.id), limit=limit)
            return async_res
        except Exception as e:
            logger.warning(f"Failed to queue search scraper async, executing synchronously: {e}")
            res = execute_scraper_run_job(str(comp_run.id), limit=limit)
            comp_run.refresh_from_db()
            for additional_scraper in scrapers[1:]:
                add_run = ComponentRun.objects.create(
                    pipeline_run=pipeline_run,
                    step_type='search',
                    component_name=f"{additional_scraper.provider}_scraper",
                    scraper=additional_scraper,
                    status='running',
                    input_params=comp_run.input_params
                )
                execute_scraper_run_job(str(add_run.id), limit=limit)
            return res
