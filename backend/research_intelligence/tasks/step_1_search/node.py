import logging
from typing import Dict, Any, Optional, Tuple

from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


class SearchNode(BaseWorkflowNode):
    """
    Search & Ingestion: Multi-source search & paper ingestion (ArXiv, OpenAlex, Lens, PubMed).
    
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
            "total_fetched": "int",
            "total_created": "int",
            "duplicates_count": "int",
        },
    }

    def should_halt_pipeline(self, pipeline_run, workspace, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        from research_intelligence.models import ComponentRun, Paper
        search_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run, step_type='search')
        # Only check search halt condition if a search run was completed for this pipeline run
        if not search_runs.filter(status='completed').exists():
            return False, None

        reprocess = config.get("reprocess_existing", getattr(pipeline_run, 'reprocess_existing', getattr(workspace, 'reprocess_existing', False)))
        papers_count = pipeline_run.get_papers().count() if hasattr(pipeline_run, 'get_papers') else pipeline_run.papers.count()

        if papers_count == 0:
            last_run = search_runs.filter(status='completed').last()
            metrics = last_run.metrics if (last_run and last_run.metrics) else {}
            duplicates = metrics.get("duplicates_count", 0)
            total_fetched = metrics.get("total_fetched", 0)
            if duplicates > 0 or total_fetched > 0:
                msg = (
                    f"Search: 0 papers were found matching criteria (0 new papers ingested - "
                    f"found {total_fetched} on data sources, but all {duplicates} were already ingested in prior runs). "
                    f"Pipeline halted cleanly. (Enable 'reprocess_existing' to re-screen/extract existing workspace papers)."
                )
            else:
                msg = (
                    f"Search: 0 papers were found matching criteria for workspace '{workspace.name}'. "
                    f"Check scraper query parameters or provider connectivity. Pipeline halted cleanly."
                )
            return True, msg
        return False, None

    def generate_stage_summary(self, comp_run, status: str = "pending") -> str:
        if status == 'completed' and comp_run:
            metrics = comp_run.metrics or {}
            total = metrics.get('total_fetched', 0)
            ingested = metrics.get('total_created', 0)
            dups = metrics.get('duplicates_count', 0)
            if total == 0 and ingested == 0:
                return "Search: 0 papers returned by queries."
            elif ingested == 0 and dups > 0:
                return f"Search: 0 new papers ({total} fetched, all {dups} were duplicates/already in workspace)."
            return f"Search: {total} fetched, {ingested} created (new), {dups} duplicates."
        return super().generate_stage_summary(comp_run, status=status)

    def get_input_params(self, pipeline_run, workspace, config: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
        params = super().get_input_params(pipeline_run, workspace, config, limit=limit)
        params["scrapers"] = [
            {"provider": s.provider, "query": s.search_query, "limit": s.limit, "n_last_days": getattr(s, 'n_last_days', 7)}
            for s in workspace.scrapers.filter(is_active=True)
        ]
        params["reprocess_existing"] = bool(config.get("reprocess_existing", getattr(pipeline_run, 'reprocess_existing', getattr(workspace, 'reprocess_existing', False))))
        if "start_date" in config and config["start_date"]:
            params["start_date"] = config["start_date"]
        if "end_date" in config and config["end_date"]:
            params["end_date"] = config["end_date"]
        n_last_days = config.get("n_last_days")
        if n_last_days is not None:
            params["n_last_days"] = n_last_days
        return params

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

        additional_runs = []
        for additional_scraper in scrapers[1:]:
            add_run = ComponentRun.objects.create(
                pipeline_run=pipeline_run,
                step_type='search',
                component_name=f"{additional_scraper.provider}_scraper",
                scraper=additional_scraper,
                status='running',
                input_params=comp_run.input_params
            )
            additional_runs.append(add_run)

        return self.dispatch_multiple_celery_tasks(execute_scraper_run_job, [comp_run] + additional_runs, limit=limit)
