"""
FastMCP Tool Implementations by Logical Domain.
Exposes tool logic with on-demand lazy imports to prevent circular dependency deadlocks.
"""
import importlib

__all__ = [
    "_check_workspace_access",
    "ask_paper_logic",
    "get_document_registry_stats_logic",
    "list_workspaces_logic",
    "get_workspace_logic",
    "create_workspace_logic",
    "update_workspace_logic",
    "add_workspace_member_logic",
    "list_scrapers_logic",
    "get_scraper_logic",
    "create_scraper_logic",
    "update_scraper_logic",
    "delete_scraper_logic",
    "preview_search_query_logic",
    "list_papers_logic",
    "list_extraction_definitions_logic",
    "get_extraction_definition_logic",
    "create_extraction_definition_logic",
    "update_extraction_definition_logic",
    "delete_extraction_definition_logic",
    "list_extractions_logic",
    "get_paper_extractions_matrix_logic",
    "get_extraction_logic",
    "trigger_search_job_logic",
    "trigger_pdf_download_job_logic",
    "trigger_ocr_job_logic",
    "trigger_screening_job_logic",
    "trigger_extraction_job_logic",
    "trigger_signal_score_job_logic",
    "get_pipeline_run_status_logic",
    "get_component_run_status_logic",
    "abort_job_logic",
    "list_pipeline_runs_logic",
    "delete_pipeline_run_logic",
    "start_research_agent_logic",
    "list_research_agents_logic",
    "get_research_agent_status_logic",
    "check_run_status_logic",
    "pause_research_agent_logic",
    "resume_research_agent_logic",
    "abort_research_agent_logic",
    "delete_research_agent_logic",
    "get_workflow_dag_schema_logic",
    "test_google_llm_logic",
    "list_user_activity_logs_logic",
    "send_pipeline_run_digest_email_logic",
]

_TOOL_DOMAIN_MAP = {
    # Workspaces
    "_check_workspace_access": "workspaces",
    "list_workspaces_logic": "workspaces",
    "get_workspace_logic": "workspaces",
    "create_workspace_logic": "workspaces",
    "update_workspace_logic": "workspaces",
    "add_workspace_member_logic": "workspaces",
    # Scrapers & Search
    "list_scrapers_logic": "scrapers",
    "get_scraper_logic": "scrapers",
    "create_scraper_logic": "scrapers",
    "update_scraper_logic": "scrapers",
    "delete_scraper_logic": "scrapers",
    "preview_search_query_logic": "scrapers",
    "list_papers_logic": "scrapers",
    # Extractions
    "list_extraction_definitions_logic": "extractions",
    "get_extraction_definition_logic": "extractions",
    "create_extraction_definition_logic": "extractions",
    "update_extraction_definition_logic": "extractions",
    "delete_extraction_definition_logic": "extractions",
    "list_extractions_logic": "extractions",
    "get_paper_extractions_matrix_logic": "extractions",
    "get_extraction_logic": "extractions",
    # Pipeline Runs
    "trigger_search_job_logic": "pipeline_runs",
    "trigger_pdf_download_job_logic": "pipeline_runs",
    "trigger_ocr_job_logic": "pipeline_runs",
    "trigger_screening_job_logic": "pipeline_runs",
    "trigger_extraction_job_logic": "pipeline_runs",
    "trigger_signal_score_job_logic": "pipeline_runs",
    "get_pipeline_run_status_logic": "pipeline_runs",
    "get_component_run_status_logic": "pipeline_runs",
    "abort_job_logic": "pipeline_runs",
    "list_pipeline_runs_logic": "pipeline_runs",
    "delete_pipeline_run_logic": "pipeline_runs",
    # Agents
    "start_research_agent_logic": "agents",
    "list_research_agents_logic": "agents",
    "get_research_agent_status_logic": "agents",
    "check_run_status_logic": "agents",
    "pause_research_agent_logic": "agents",
    "resume_research_agent_logic": "agents",
    "abort_research_agent_logic": "agents",
    "delete_research_agent_logic": "agents",
    "get_workflow_dag_schema_logic": "agents",
    # Diagnostics
    "get_document_registry_stats_logic": "diagnostics",
    "test_google_llm_logic": "diagnostics",
    "list_user_activity_logs_logic": "diagnostics",
    "send_pipeline_run_digest_email_logic": "diagnostics",
    # Chat
    "ask_paper_logic": "chat",
}


def __getattr__(name: str):
    domain = _TOOL_DOMAIN_MAP.get(name)
    if domain:
        module = importlib.import_module(f".{domain}", package=__name__)
        val = getattr(module, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    return list(globals().keys()) + __all__
