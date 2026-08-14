#!/usr/bin/env python
import os
import sys
import django
import hashlib
import re
from urllib.parse import parse_qs
from functools import wraps

# 1. Bootstrap Django environment
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(script_dir, "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
try:
    django.setup()
except Exception as e:
    print(f"Error bootstrapping Django: {e}", file=sys.stderr)
    sys.exit(1)

import logging

class MCPWarningFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "Received request before initialization was complete" in msg:
            return False
        if "RequestResponder must be used as a context manager" in msg:
            return False
        if "notifications/cancelled" in msg:
            return False
        return True

logging.getLogger().addFilter(MCPWarningFilter())
logging.getLogger("mcp").addFilter(MCPWarningFilter())

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from asgiref.sync import sync_to_async
from django.db import close_old_connections

from research_intelligence.models import APIKey, Workspace
from research_intelligence.mcp.tools import (
    list_workspaces_logic,
    get_workspace_logic,
    create_workspace_logic,
    update_workspace_logic,
    add_workspace_member_logic,
    list_scrapers_logic,
    get_scraper_logic,
    create_scraper_logic,
    update_scraper_logic,
    delete_scraper_logic,
    preview_search_query_logic,
    list_papers_logic,
    list_extraction_definitions_logic,
    get_extraction_definition_logic,
    create_extraction_definition_logic,
    update_extraction_definition_logic,
    delete_extraction_definition_logic,
    list_extractions_logic,
    get_extraction_logic,
    trigger_search_job_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
    get_pipeline_run_status_logic,
    get_component_run_status_logic,
    abort_job_logic,
    list_pipeline_runs_logic,
    delete_pipeline_run_logic,
    start_research_agent_logic,
    list_research_agents_logic,
    get_research_agent_status_logic,
    pause_research_agent_logic,
    resume_research_agent_logic,
    abort_research_agent_logic,
    delete_research_agent_logic,
    test_google_llm_logic,
    list_user_activity_logs_logic,
)


def with_db_connection(func):
    """Decorator to manage Django DB connections cleanly and automatically audit FastMCP tool executions."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        close_old_connections()
        import time
        t0 = time.time()
        user = None
        workspace = None
        api_key = None
        try:
            user, workspace, api_key = get_auth_context()
        except Exception:
            pass

        status = "success"
        error_msg = None
        result = None

        try:
            result = func(*args, **kwargs)
            if isinstance(result, str):
                try:
                    res_obj = json.loads(result)
                    if isinstance(res_obj, dict) and res_obj.get("status") == "error":
                        status = "failed"
                        error_msg = res_obj.get("error")
                except Exception:
                    pass
            return result
        except Exception as e:
            status = "failed"
            error_msg = str(e)
            raise
        finally:
            dt_ms = round((time.time() - t0) * 1000, 2)
            try:
                from research_intelligence.models import UserActivityLog
                api_key_id = getattr(api_key, 'key_id', None) if api_key else None
                out_sum = None
                if result:
                    if isinstance(result, str) and len(result) < 2000:
                        try:
                            out_sum = json.loads(result)
                        except Exception:
                            out_sum = {"result": result[:500]}
                    else:
                        out_sum = {"result_length": len(str(result))}

                UserActivityLog.log_action(
                    user=user,
                    workspace=workspace,
                    interface="mcp",
                    action_name=func.__name__,
                    status=status,
                    input_params=kwargs if kwargs else {"args": [str(a) for a in args]},
                    output_summary=out_sum,
                    error_message=error_msg,
                    execution_time_ms=dt_ms,
                    api_key_id=api_key_id
                )
            except Exception as audit_err:
                logger.warning(f"Failed to record UserActivityLog for {func.__name__}: {audit_err}")
            close_old_connections()

    return wrapper


# ==========================================
# 2. FastMCP Server Initialization & Directives
# ==========================================

SERVER_INSTRUCTIONS = """
You are an intelligent AI agent connected to the Schwarz Research Intelligence Platform MCP Server.
This platform manages multi-agent systematic literature reviews, automated data scraping, paper screening, parameter extraction, and report generation.

CORE WORKFLOW INSTRUCTIONS (STEP-BY-STEP USE CASE 1):

1. WORKSPACE INITIALIZATION & MANAGEMENT:
   Call `list_workspaces()` to inspect existing projects or `create_workspace(name="...", acceptance_criteria="...")` to create a new isolated research project.
   - Creating a workspace automatically sets the authenticated user as Workspace Admin.
   - Sets default LLM model ('google/gemini-3.7-flash') and OCR engine (None / auto-skipped by default to pass full PDF binaries directly to multimodal Gemini 3.7 Flash during screening).

2. DEFINE DATA SCRAPER:
   Call `create_scraper(workspace_id="...", provider="arxiv", search_query="...")`.
   - Supported providers: 'arxiv', 'openalex', 'lens'.
   - Search Query Syntax & Examples:
     * arXiv Topic & Date restriction: 'cat:cs.AI AND ti:"small llm" AND submittedDate:[202606010000 TO 202607292359]'
     * OpenAlex Search: 'display_name.search:"small language models mobile"'
     * Lens.org Search: 'title:"small llm" AND year:2026'

3. TRIGGER OR REPEAT PIPELINE RUN (STEP 1: SEARCH & INGESTION):
   Call `trigger_search_job(workspace_id="...", limit=50)`.
   - Use this tool when triggering an initial search OR when requested to repeat a search ('search again', 'repeat search', 're-run search').
   - Creates a new PipelineRun and ComponentRun ('search').
   - Launches Celery worker to fetch papers, save raw payloads to `default_storage`, deduplicate papers, and save Paper records.
   - Returns `pipeline_run_id` and `component_runs`.

4. TRIGGER PDF DOWNLOAD (STEP 2: PDF BINARY DOWNLOAD):
   Call `trigger_pdf_download_job(pipeline_run_id="...", limit=50)`.
   - Creates a ComponentRun ('download').
   - Downloads PDF binaries into `default_storage` at `workspaces/{workspace_id}/runs/{pipeline_run_id}/documents/{hash_id}/original.pdf`.
   - Updates `paper.original_pdf_path` and automatically skips already stored PDFs to prevent duplicate downloads.

CRITICAL LANGUAGE CONSTRAINT:
All output, summaries, status reports, tool responses, and tree renderings generated by AI clients MUST be strictly in English.

5. CHECK PIPELINE & STEP STATUS:
   Call `get_pipeline_run_status(pipeline_run_id="...")` or `list_pipeline_runs(workspace_id="...")`.
   - Returns overall execution status ('pending', 'running', 'completed', 'failed', 'aborted') and nested `component_runs`.
   - Always display pipeline runs as parent nodes and nested `component_runs` as indented tree leaves (`├──`, `└──`) in English.
   - When rendering paper details or fetched paper lists, ALWAYS display the Title, Authors, PDF URL, and Full Abstract for each paper.
   - For single step details: call `get_component_run_status(component_run_id="...")`.
"""

mcp = FastMCP("schwarz-research-intelligence", version="1.0.0", instructions=SERVER_INSTRUCTIONS)


SESSION_AUTH_CACHE = {}  # session_id -> (user, workspace, api_key)


def get_auth_context():
    """Retrieve authenticated user, workspace, and api_key from the active HTTP request."""
    try:
        request = get_http_request()
        if request and hasattr(request.state, "user"):
            return request.state.user, getattr(request.state, "workspace", None), getattr(request.state, "api_key", None)
    except Exception:
        pass

    # Fallback to default superuser for dev/single-user mode
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.create_superuser("admin", "admin@example.com", "schwarz123!")
        return admin_user, None, None
    except Exception:
        pass

    raise PermissionError("Authentication required. Please connect with API credentials via query params or headers.")


def check_scope(api_key_instance, required_scope: str):
    """Verify that the API Key has the required scope or wildcard access."""
    if not api_key_instance or not hasattr(api_key_instance, 'scopes'):
        return
    granted_scopes = api_key_instance.scopes or []
    if "*" not in granted_scopes and required_scope not in granted_scopes:
        raise PermissionError(
            f"Insufficient permissions. API Key lacks required scope '{required_scope}'. Granted: {granted_scopes}"
        )


# ==========================================
# 3. MCP Prompts Registration (AI Client Workflows)
# ==========================================

@mcp.prompt()
def quickstart_scraping_workflow(
    workspace_name: str = "Mobile LLM Research",
    search_topic: str = "Small LLM models on mobile",
    time_restriction: str = "last month"
) -> str:
    """Prompt template guiding AI clients through Workspace creation, Scraper setup, Job execution, and Status monitoring."""
    return f"""
You are an AI research assistant executing a systematic review on the Schwarz Research Intelligence MCP Server.

Target Parameters:
- Workspace Name: {workspace_name}
- Search Topic: {search_topic}
- Time Restriction: {time_restriction}

Follow this exact step-by-step tool execution protocol:

1. WORKSPACE CREATION:
   Call `create_workspace(
       name="{workspace_name}",
       abstract_acceptance_criteria="Target papers on {search_topic}",
       abstract_rejection_criteria="Out of domain or irrelevant topics",
       full_text_acceptance_criteria="Focus on architecture benchmarks and low-bit quantization for mobile",
       full_text_rejection_criteria="Pure hardware ASIC design without software LLM evaluation"
   )`.
   (Note: The authenticated MCP user is automatically assigned as Workspace Admin).

2. SCRAPER CONFIGURATION:
   Call `create_scraper(workspace_id="<WORKSPACE_ID>", provider="arxiv", search_query='cat:cs.AI AND "small llm" AND "mobile"')`.

3. TRIGGER AUTONOMOUS RESEARCH AGENT:
   Call `start_research_agent(workspace_id="<WORKSPACE_ID>", limit=50, date_range_days=30)`.

4. MONITOR AGENT PROCESS STATUS:
   Call `get_research_agent_status(process_id="<PROCESS_ID>")`.
   Report back the process status, active pipeline step, step history audit trail, and paper metrics.
"""


@mcp.prompt()
def autonomous_research_agent_workflow(
    workspace_id: str,
    limit: str = "50",
    date_range_days: str = "30",
    notification_email: str = None
) -> str:
    """Prompt template guiding AI clients through starting, monitoring, and managing an autonomous Research Agent process."""
    return f"""
You are an AI research assistant managing an autonomous Research Agent Process on the Schwarz Research Intelligence platform.

Target Execution Parameters:
- Workspace ID: {workspace_id}
- Paper Fetch Limit: {limit}
- Date Window (Days): {date_range_days}
- Notification Email: {notification_email or 'Workspace members and subscribers'}

Execution Protocol:
1. START AGENT PROCESS:
   Call `start_research_agent(
       workspace_id="{workspace_id}",
       limit={limit},
       date_range_days={date_range_days},
       notification_email={f'"{notification_email}"' if notification_email else 'None'}
   )`.

2. MONITOR STATE ENGINE TRANSITIONS:
   Periodically check progress by calling `get_research_agent_status(process_id="<PROCESS_ID>")`.
   The state machine automatically advances through:
   `initialized` -> `search` -> `download` -> `ocr` (skipped if ocr_provider is None) -> `screening` -> `extraction` -> `completed`.

3. LIFECYCLE CONTROLS (IF NEEDED):
   - To pause: Call `pause_research_agent(process_id="<PROCESS_ID>")`.
   - To resume: Call `resume_research_agent(process_id="<PROCESS_ID>")`.
   - To abort: Call `abort_research_agent(process_id="<PROCESS_ID>")`.
   - To clean up: Call `delete_research_agent(process_id="<PROCESS_ID>")`.
"""


@mcp.prompt()
def check_pipeline_run_status_guide(pipeline_run_id: str) -> str:
    """Prompt template instructing AI clients on inspecting pipeline run status, active steps, and storage paths."""
    return f"""
Inspect the execution state of PipelineRun '{pipeline_run_id}':

1. Call `get_pipeline_run_status(pipeline_run_id="{pipeline_run_id}")`.
2. Evaluate:
   - Overall Pipeline Status ('pending', 'running', 'completed', 'failed', 'aborted').
   - Active Component Step ('search', 'download', 'ocr', 'screening', 'extraction', 'reporting').
   - Number of papers fetched, downloaded, screened, and extracted.
   - Raw data storage path in Django default_storage.
3. For specific component step details, call `get_component_run_status(component_run_id="<COMPONENT_RUN_ID>")`.
"""


# ==========================================
# 4. MCP Tools Registration
# ==========================================

# --- Workspace Management Tools ---

@mcp.tool()
@with_db_connection
def list_workspaces() -> str:
    """List all workspaces accessible to the authenticated user along with member roles."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return list_workspaces_logic(user)


@mcp.tool()
@with_db_connection
def get_workspace(workspace_id: str) -> str:
    """
    Retrieve full configuration details, component configurations (Scrapers, OCR Engine, LLM Models, Prompt Templates, Extraction Definitions), and member roster for a workspace.
    
    GUIDELINE: Render the workspace component configurations as a structured hierarchical tree (using `├──` and `└──`), explicitly listing "Scraper Configurations", "OCR Engine", "Screening LLM Model", "Extraction Definitions", and "Prompt Templates". All output must be in English.
    
    Parameters:
    - workspace_id: The UUID of the workspace.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_workspace_logic(user, workspace_id)


@mcp.tool()
@with_db_connection
def create_workspace(
    name: str,
    abstract_acceptance_criteria: str = "",
    abstract_rejection_criteria: str = "",
    full_text_acceptance_criteria: str = "",
    full_text_rejection_criteria: str = "",
    ocr_provider: str = None,
    screening_llm_model: str = "google/gemini-3.7-flash",
    llm_provider: str = "google",
    digest_schedule: str = "0 9 * * 5",
    monthly_token_limit: int = 10000000,
    cost_limit_usd: float = 100.00
) -> str:
    """
    Create a new isolated workspace project for systematic literature reviews and competitive intelligence.
    AUTOMATICALLY ASSIGNS THE AUTHENTICATED MCP USER AS WORKSPACE ADMIN.

    Criteria Parameters:
    - abstract_acceptance_criteria: Specific inclusion criteria prompt evaluated during Step 4 Abstract Screening.
    - abstract_rejection_criteria: Specific exclusion criteria prompt evaluated during Step 4 Abstract Screening.
    - full_text_acceptance_criteria: Specific inclusion criteria prompt evaluated during Step 4 Full-Text Screening.
    - full_text_rejection_criteria: Specific exclusion criteria prompt evaluated during Step 4 Full-Text Screening.
    - ocr_provider: Defaults to None (skips Step 3 OCR). Set to 'pypdf', 'mistral', or 'gemini' ONLY if OCR layout extraction is explicitly requested by the user.

    CRITICAL FOR LLM AGENTS: Do NOT set or enable ocr_provider unless the user explicitly requests OCR layout conversion. Leave ocr_provider as None by default.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return create_workspace_logic(
        user=user,
        name=name,
        abstract_acceptance_criteria=abstract_acceptance_criteria,
        abstract_rejection_criteria=abstract_rejection_criteria,
        full_text_acceptance_criteria=full_text_acceptance_criteria,
        full_text_rejection_criteria=full_text_rejection_criteria,
        ocr_provider=ocr_provider,
        screening_llm_model=screening_llm_model,
        llm_provider=llm_provider,
        digest_schedule=digest_schedule,
        monthly_token_limit=monthly_token_limit,
        monthly_usd_limit=cost_limit_usd,
    )


@mcp.tool()
@with_db_connection
def update_workspace(
    workspace_id: str,
    name: str = None,
    abstract_acceptance_criteria: str = None,
    abstract_rejection_criteria: str = None,
    full_text_acceptance_criteria: str = None,
    full_text_rejection_criteria: str = None,
    ocr_provider: str = None,
    screening_llm_model: str = None,
    llm_provider: str = None,
    digest_schedule: str = None,
    monthly_token_limit: int = None,
    cost_limit_usd: float = None
) -> str:
    """
    Update configuration settings of an existing workspace (requires Admin or Manager role).

    Criteria Parameters:
    - abstract_acceptance_criteria: Update inclusion criteria evaluated during Step 4 Abstract Screening.
    - abstract_rejection_criteria: Update exclusion criteria evaluated during Step 4 Abstract Screening.
    - full_text_acceptance_criteria: Update inclusion criteria evaluated during Step 4 Full-Text Screening.
    - full_text_rejection_criteria: Update exclusion criteria evaluated during Step 4 Full-Text Screening.
    - ocr_provider: Set to 'pypdf', 'mistral', 'gemini', or None/'none' to skip/disable OCR step.

    CRITICAL FOR LLM AGENTS: Do NOT modify existing workspace configuration settings (criteria, ocr_provider, llm_provider, screening_llm_model) unless explicitly instructed by the user to change configuration.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return update_workspace_logic(
        user=user,
        workspace_id=workspace_id,
        name=name,
        abstract_acceptance_criteria=abstract_acceptance_criteria,
        abstract_rejection_criteria=abstract_rejection_criteria,
        full_text_acceptance_criteria=full_text_acceptance_criteria,
        full_text_rejection_criteria=full_text_rejection_criteria,
        ocr_provider=ocr_provider,
        screening_llm_model=screening_llm_model,
        llm_provider=llm_provider,
        digest_schedule=digest_schedule,
        monthly_token_limit=monthly_token_limit,
        monthly_usd_limit=cost_limit_usd,
    )


@mcp.tool()
@with_db_connection
def add_workspace_member(
    workspace_id: str,
    member_username_or_email: str,
    role: str = "researcher"
) -> str:
    """Add a user to a workspace with a specific role ('admin', 'manager', 'researcher')."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return add_workspace_member_logic(user, workspace_id, member_username_or_email, role)


# --- Scraper Management Tools ---

@mcp.tool()
@with_db_connection
def list_scrapers(workspace_id: str) -> str:
    """List all scrapers configured for a workspace."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return list_scrapers_logic(user, workspace_id)


@mcp.tool()
@with_db_connection
def get_scraper(scraper_id: str) -> str:
    """Retrieve details for a specific scraper."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return get_scraper_logic(user, scraper_id)


@mcp.tool()
@with_db_connection
def create_scraper(
    workspace_id: str,
    provider: str,
    search_query: str,
    limit: int = 50,
    sort_by: str = "relevance",
    sort_order: str = "desc",
    is_active: bool = True
) -> str:
    """Create a new academic data scraper for a workspace with sorting options and limit."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return create_scraper_logic(user, workspace_id, provider, search_query, limit, sort_by, sort_order, is_active)


@mcp.tool()
@with_db_connection
def update_scraper(
    scraper_id: str,
    provider: str | None = None,
    search_query: str | None = None,
    limit: int | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    is_active: bool | None = None
) -> str:
    """Update an existing scraper configuration with sorting options and limit."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return update_scraper_logic(user, scraper_id, provider, search_query, limit, sort_by, sort_order, is_active)


@mcp.tool()
@with_db_connection
def delete_scraper(scraper_id: str) -> str:
    """Delete a scraper definition."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return delete_scraper_logic(user, scraper_id)


@mcp.tool()
@with_db_connection
def preview_search_query(provider: str, search_query: str, limit: int = 10) -> str:
    """Execute a live search query against a scientific paper provider (arXiv, OpenAlex, Lens.org) without downloading PDFs or storing DB runs."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return preview_search_query_logic(user, provider, search_query, limit)


@mcp.tool()
@with_db_connection
def list_papers(workspace_id: str, pipeline_run_id: str | None = None, limit: int = 50) -> str:
    """List fetched paper records and search results for a workspace (optionally filtered by pipeline_run_id) without downloading PDFs."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return list_papers_logic(user, workspace_id, pipeline_run_id, limit)


# --- Extraction Definitions Management Tools ---

@mcp.tool()
@with_db_connection
def list_extraction_definitions(workspace_id: str) -> str:
    """List dynamic parameter/claim extraction definitions configured for a workspace."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:read")
    except Exception as e:
        return str(e)
    return list_extraction_definitions_logic(user, workspace_id)


@mcp.tool()
@with_db_connection
def get_extraction_definition(definition_id: str) -> str:
    """Retrieve detailed view of an extraction definition including prompts, response schema, and LLM configuration."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:read")
    except Exception as e:
        return str(e)
    return get_extraction_definition_logic(user, definition_id)


@mcp.tool()
@with_db_connection
def create_extraction_definition(
    workspace_id: str,
    name: str,
    system_prompt: str,
    user_prompt_template: str,
    response_schema: dict,
    llm_model: str = "google/gemini-3.7-flash",
    version: int = 1,
    requires_consensus: bool = False,
    is_active: bool = True
) -> str:
    """Create a new dynamic extraction definition target for a workspace (e.g. 'ML Methods', 'Benchmark Metrics')."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:write")
    except Exception as e:
        return str(e)
    return create_extraction_definition_logic(
        user=user,
        workspace_id=workspace_id,
        name=name,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        response_schema=response_schema,
        llm_model=llm_model,
        version=version,
        requires_consensus=requires_consensus,
        is_active=is_active
    )


@mcp.tool()
@with_db_connection
def update_extraction_definition(
    definition_id: str,
    name: str | None = None,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    response_schema: dict | None = None,
    llm_model: str | None = None,
    version: int | None = None,
    requires_consensus: bool | None = None,
    is_active: bool | None = None
) -> str:
    """Update an existing extraction definition's schema, prompts, or LLM configuration."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:write")
    except Exception as e:
        return str(e)
    return update_extraction_definition_logic(
        user=user,
        definition_id=definition_id,
        name=name,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        response_schema=response_schema,
        llm_model=llm_model,
        version=version,
        requires_consensus=requires_consensus,
        is_active=is_active
    )


@mcp.tool()
@with_db_connection
def delete_extraction_definition(definition_id: str) -> str:
    """Delete an extraction definition from a workspace."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:write")
    except Exception as e:
        return str(e)
    return delete_extraction_definition_logic(user, definition_id)


# --- Pipeline Runs & Execution Tools ---

@mcp.tool()
@with_db_connection
def trigger_search_job(workspace_id: str, scraper_id: str | None = None, limit: int = 50) -> str:
    """Trigger or repeat Step 1 of the processing pipeline (Scraping & Metadata Search) for a workspace. Use this tool when starting a new search, repeating a search ('search again'), or re-fetching paper metadata."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return trigger_search_job_logic(user, workspace_id, scraper_id, limit)


@mcp.tool()
@with_db_connection
def trigger_pdf_download_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = 50) -> str:
    """Trigger Step 2 of the processing pipeline (PDF Binary Download) for papers ingested during a PipelineRun."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return trigger_pdf_download_job_logic(user, pipeline_run_id, workspace_id, limit)


@mcp.tool()
@with_db_connection
def trigger_ocr_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = 50) -> str:
    """Trigger Step 3 of the processing pipeline (Layout OCR Extraction) to convert downloaded PDF papers into layout Markdown text using the workspace's configured OCR provider."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return trigger_ocr_job_logic(user, pipeline_run_id, workspace_id, limit)


@mcp.tool()
@with_db_connection
def trigger_screening_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = 50) -> str:
    """Trigger Step 4 of the processing pipeline (Abstract Screening) to evaluate paper abstracts against workspace criteria using the LLM."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return trigger_screening_job_logic(user, pipeline_run_id, workspace_id, limit)


@mcp.tool()
@with_db_connection
def trigger_extraction_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = 50) -> str:
    """Trigger Step 5 of the processing pipeline (Parameter & Claim Extraction) to extract structured fields across all active ExtractionDefinitions for the workspace."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return trigger_extraction_job_logic(user, pipeline_run_id, workspace_id, limit)


@mcp.tool()
@with_db_connection
def list_extractions(
    workspace_id: str = None,
    paper_id: str = None,
    category: str = None,
    validation_status: str = None,
    limit: int = 50
) -> str:
    """List extracted structured fields and claim records (Step 5 outputs). Supports filtering by workspace_id, paper_id, category, or validation_status."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return list_extractions_logic(user, workspace_id, paper_id, category, validation_status, limit)


@mcp.tool()
@with_db_connection
def get_extraction(extraction_id: str) -> str:
    """Retrieve full details for a single Extraction object by UUID (e.g., '18f71398-2659-462f-8c71-5d76e02dc2ef'), including fields_data, prompts, paper title, and confidence scores."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_extraction_logic(user, extraction_id)


@mcp.tool()
@with_db_connection
def get_pipeline_run_status(pipeline_run_id: str) -> str:
    """Retrieve full execution status, active step, metrics, component run states, and fetched paper previews for a PipelineRun."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return get_pipeline_run_status_logic(user, pipeline_run_id)


@mcp.tool()
@with_db_connection
def get_component_run_status(component_run_id: str) -> str:
    """Retrieve details, execution status, step_type, metrics, and raw storage path for a specific ComponentRun."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return get_component_run_status_logic(user, component_run_id)


@mcp.tool()
@with_db_connection
def abort_job(component_run_id: str | None = None, pipeline_run_id: str | None = None) -> str:
    """Abort a running component step or full PipelineRun (requires Admin or Manager role)."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return abort_job_logic(user, component_run_id, pipeline_run_id)


@mcp.tool()
@with_db_connection
def list_pipeline_runs(workspace_id: str, limit: int = 20) -> str:
    """List recent PipelineRuns for a workspace with stage, status, paper count, and duration metrics."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return list_pipeline_runs_logic(user, workspace_id, limit)


@mcp.tool()
@with_db_connection
def delete_pipeline_run(pipeline_run_id: str) -> str:
    """Delete an entire PipelineRun along with all associated Papers, Extractions, ComponentRuns, PaperMetrics, NarrativeReports, and cleans up physical original PDF and OCR Markdown files from storage."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return delete_pipeline_run_logic(user, pipeline_run_id)


@mcp.tool()
@with_db_connection
def start_research_agent(
    workspace_id: str,
    name: str = None,
    limit: int = 50,
    date_range_days: int = None,
    query_prefix: str = None,
    skip_abstract_screening: bool = None,
    notification_email: str = None
) -> str:
    """
    Start an autonomous Research Agent Process to execute a complete ingestion and intelligence cycle (Search -> Download -> OCR (skipped if unconfigured) -> Screening -> Extraction). Supports parallel runs, dynamic query modifiers, date windowing, and notification settings.

    CRITICAL FOR LLM AGENTS: Calling start_research_agent executes the pipeline using the EXISTING workspace configuration. Do NOT modify workspace settings or criteria prior to launching an agent process unless explicitly instructed by the user.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return start_research_agent_logic(user, workspace_id, name, limit, date_range_days, query_prefix, skip_abstract_screening, notification_email)


@mcp.tool()
@with_db_connection
def list_research_agents(workspace_id: str = None, limit: int = 20) -> str:
    """List recent or active autonomous Research Agent Processes for a workspace or across accessible workspaces."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return list_research_agents_logic(user, workspace_id, limit)


@mcp.tool()
@with_db_connection
def get_research_agent_status(process_id: str) -> str:
    """Retrieve full status, step history audit log, pipeline run ID, and component metrics for an autonomous Research Agent Process by UUID."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_research_agent_status_logic(user, process_id)


@mcp.tool()
@with_db_connection
def pause_research_agent(process_id: str) -> str:
    """Pause a running autonomous Research Agent Process (requires Admin or Manager role)."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return pause_research_agent_logic(user, process_id)


@mcp.tool()
@with_db_connection
def resume_research_agent(process_id: str) -> str:
    """Resume a paused autonomous Research Agent Process and trigger the state engine to continue execution."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return resume_research_agent_logic(user, process_id)


@mcp.tool()
@with_db_connection
def abort_research_agent(process_id: str) -> str:
    """Abort a running or paused autonomous Research Agent Process and terminate attached Celery background tasks."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return abort_research_agent_logic(user, process_id)


@mcp.tool()
@with_db_connection
def delete_research_agent(process_id: str) -> str:
    """Delete a Research Agent Process record and cleanup associated PipelineRun database and storage data."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return delete_research_agent_logic(user, process_id)


@mcp.tool()
@with_db_connection
def list_user_activity_logs(
    workspace_id: str | None = None,
    interface: str | None = None,
    status: str | None = None,
    limit: int = 50
) -> str:
    """List operational audit activity logs for a workspace or across user actions (FastMCP tools and REST API endpoints)."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return list_user_activity_logs_logic(user, workspace_id, interface, status, limit)


# 3. Pure ASGI HTTP/SSE Request Authentication Middleware
class QueryParamAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        if path in ["/", "/health", "/docs", "/openapi.json"]:
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers", []))
        query_string = scope.get("query_string", b"").decode("utf-8")
        from urllib.parse import parse_qs
        query_params = parse_qs(query_string)

        session_id_list = query_params.get("session_id")
        session_id = session_id_list[0] if session_id_list else None

        auth_header = headers.get(b"authorization", b"").decode("utf-8")
        
        key_id_list = query_params.get("api_key_id")
        key_id = key_id_list[0] if key_id_list else headers.get(b"x-api-key-id", b"").decode("utf-8")
        secret_list = query_params.get("api_secret")
        secret = secret_list[0] if secret_list else headers.get(b"x-api-secret", b"").decode("utf-8")

        if not key_id and auth_header.startswith("Bearer "):
            token_parts = auth_header[7:].split(":")
            if len(token_parts) == 2:
                key_id, secret = token_parts[0], token_parts[1]

        # 1. Check if auth is cached for this SSE session_id
        if session_id and session_id in SESSION_AUTH_CACHE and not (key_id and secret):
            user, workspace, api_key = SESSION_AUTH_CACHE[session_id]
            class ScopeState:
                pass
            state = ScopeState()
            state.user = user
            state.workspace = workspace
            state.api_key = api_key
            scope["state"] = state
            return await self.app(scope, receive, send)

        async def send_error(status_code: int, error_message: str):
            body = f'{{"error": "{error_message}"}}'.encode('utf-8')
            await send({
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode('utf-8'))
                ]
            })
            await send({
                "type": "http.response.body",
                "body": body
            })

        try:
            @sync_to_async
            def verify_or_fallback():
                close_old_connections()
                if key_id and secret:
                    try:
                        key_obj = APIKey.objects.select_related('user', 'workspace').get(key_id=key_id, is_active=True)
                        if key_obj.check_secret(secret):
                            key_obj.update_last_used()
                            return key_obj.user, key_obj.workspace, key_obj
                    except APIKey.DoesNotExist:
                        pass
                
                # Auto-provision default admin user & key
                from django.contrib.auth import get_user_model
                User = get_user_model()
                admin_user = User.objects.filter(is_superuser=True).first()
                if not admin_user:
                    admin_user = User.objects.create_superuser("admin", "admin@example.com", "schwarz123!")
                
                key_obj = APIKey.objects.filter(key_id="admin_mcp_key").first()
                if not key_obj:
                    key_obj = APIKey.objects.create(
                        name="Default Admin Key",
                        user=admin_user,
                        key_id="admin_mcp_key",
                        scopes=["*"]
                    )
                    key_obj.set_secret("schwarz123!")
                    key_obj.save()
                return admin_user, None, key_obj

            user_obj, ws_obj, api_key_obj = await verify_or_fallback()

            if session_id:
                SESSION_AUTH_CACHE[session_id] = (user_obj, ws_obj, api_key_obj)

            class ScopeState:
                pass

            state = ScopeState()
            state.user = user_obj
            state.workspace = ws_obj
            state.api_key = api_key_obj
            scope["state"] = state

        except Exception as e:
            return await send_error(500, f"Authentication internal error: {str(e)}")

        return await self.app(scope, receive, send)


@mcp.tool()
@with_db_connection
def test_google_llm(
    prompt: str | None = None,
    model: str | None = None,
    location: str | None = None
) -> str:
    """
    Test connectivity to Google Cloud GenAI / Vertex AI models (e.g. gemini-3.7-flash) and verify current API credentials.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return test_google_llm_logic(user, prompt, model, location)


def create_app():
    starlette_app = mcp.http_app(transport="sse", middleware=[])
    from starlette.middleware import Middleware
    starlette_app.user_middleware.insert(0, Middleware(QueryParamAuthMiddleware))
    starlette_app.middleware_stack = starlette_app.build_middleware_stack()
    return starlette_app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
