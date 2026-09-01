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
from django.apps import apps
if not apps.ready and not apps.loading:
    try:
        django.setup()
    except Exception as e:
        print(f"Error bootstrapping Django: {e}", file=sys.stderr)
        sys.exit(1)

import logging
import json
import time
import asyncio
from starlette.requests import ClientDisconnect

logger = logging.getLogger(__name__)

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
from mcp_server.tools import (
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
    get_paper_extractions_matrix_logic,
    get_extraction_logic,
    trigger_search_job_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
    trigger_signal_score_job_logic,
    trigger_reporting_job_logic,
    get_pipeline_run_status_logic,
    get_component_run_status_logic,
    abort_job_logic,
    list_pipeline_runs_logic,
    delete_pipeline_run_logic,
    start_research_agent_logic,
    list_research_agents_logic,
    get_research_agent_status_logic,
    check_run_status_logic,
    pause_research_agent_logic,
    resume_research_agent_logic,
    abort_research_agent_logic,
    delete_research_agent_logic,
    get_workflow_dag_schema_logic,
    get_pipeline_logs_logic,
    get_document_registry_stats_logic,
    test_google_llm_logic,
    list_user_activity_logs_logic,
    send_pipeline_run_digest_email_logic,
    ask_paper_logic,
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
                    if isinstance(res_obj, dict):
                        if res_obj.get("status") == "error" or (not res_obj.get("success", True) and "error" in res_obj):
                            status = "failed"
                            error_msg = res_obj.get("error")
                except Exception:
                    if result.strip().startswith("Error:"):
                        status = "failed"
                        error_msg = result.strip()
            return result
        except Exception as e:
            status = "failed"
            error_msg = str(e)
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(e)
            except Exception:
                pass
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

                req = None
                try:
                    req = get_http_request()
                except Exception:
                    pass

                ip_addr = None
                ua_str = None
                if req:
                    x_fwd = req.headers.get("x-forwarded-for")
                    if x_fwd:
                        ip_addr = x_fwd.split(",")[0].strip()
                    elif hasattr(req, "client") and req.client:
                        ip_addr = req.client.host
                    ua_str = req.headers.get("user-agent", "")[:500]

                UserActivityLog.log_action(
                    user=user,
                    workspace=workspace,
                    interface="mcp",
                    action_name=func.__name__,
                    status=status,
                    input_params=kwargs if kwargs else ({"args": [str(a) for a in args]} if args else {}),
                    output_summary=out_sum,
                    error_message=error_msg,
                    execution_time_ms=dt_ms,
                    api_key_id=api_key_id,
                    ip_address=ip_addr,
                    user_agent=ua_str
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

=======================================================
CORE WORKFLOW MODES:
=======================================================

MODE 1: AUTONOMOUS END-TO-END PIPELINE (DEFAULT & RECOMMENDED)
When asked to run research, review literature, or execute the full pipeline:
1. WORKSPACE INITIALIZATION & SCRAPERS:
   - Call `list_workspaces()` or `create_workspace(name="...", abstract_acceptance_criteria="...", ...)`.
   - Call `create_scraper(workspace_id="...", provider="arxiv", search_query="...")` if no active scrapers exist.
2. LAUNCH AUTONOMOUS ORCHESTRATOR:
   - Call `start_research_agent(workspace_id="<WS_ID>", limit=50, date_range_days=30)`.
   - The state engine automatically orchestrates the pipeline sequentially:
     Search & Deduplication -> Abstract Screening (skippable) -> PDF Download -> Layout OCR (skippable) -> Full-Text Screening -> Parameter Extraction -> Composite Signal Score -> Executive Reporting -> Completed.
3. MONITOR STATUS:
   - Call `check_run_status(process_id="<PROCESS_ID>")` or `get_research_agent_status(process_id="<PROCESS_ID>")`.
4. DISPLAYING RUN RESULTS & EXTRACTED PARAMETERS (SCORECARD):
   - When asked to show run results, view extracted parameters, display a metrics scorecard, or compare parameter scores across accepted papers:
     ALWAYS call `get_paper_extractions_matrix(process_id="<PROCESS_ID>", pipeline_run_id="<RUN_ID>", workspace_id="<WS_ID>")`.
     This returns the complete aggregated matrix of all accepted papers mapped to their extracted metric scores (Novelty, Schwarz Fit, TRL, Rigour, Significance) and composite `signal_score` in a SINGLE structured response.
     DO NOT write custom bash/python scripts to combine papers and extractions.

=======================================================
CUSTOM PYTHON SIGNAL SCORE DEFINITIONS (`signal_score_code`):
=======================================================
Workspaces support custom mathematical and decision logic formulas written in sandboxed Python.
All extraction definitions and metrics are available in the scope as sanitized snake_case variables (e.g., 'TRL Level' -> `trl_level`, 'Schwarz Fit' -> `schwarz_fit` or `fit_score`, 'Novelty' -> `novelty_score`).

Supported Python Code Examples for `signal_score_code`:

Example 1 (Weighted linear sum):
```python
score = 0.4 * fit_score + 0.3 * novelty_score + 0.3 * trl_level
return round(score, 2)
```

Example 2 (Conditional branching & gating):
```python
k = fit_score + 2.0 * novelty_score + trl_level
if k > 10.0:
    return 5.0
else:
    return 99.0
```

Example 3 (Multi-variable threshold qualification):
```python
if trl_level < 3.0:
    return 0.0
base_score = 0.5 * fit_score + 0.3 * novelty_score + 0.2 * commercial_viability
multiplier = 1.2 if trl_level >= 7.0 else 1.0
return round(base_score * multiplier, 2)
```

Example 4 (Statistical normalization / min-max clamping):
```python
raw = (fit_score * 2.5) + (novelty_score * 1.5) - (5.0 if rigour_score < 4 else 0.0)
return max(0.0, min(100.0, raw))
```

MODE 2: MANUAL COMPONENT DEBUGGING (ISOLATED COMPONENTS ONLY)
Use individual `trigger_*` tools ONLY when the user explicitly requests testing or re-running a single specific component in isolation:
- `trigger_search_job(workspace_id="...")`
- `trigger_screening_job(pipeline_run_id="...", stage="abstract")`
- `trigger_pdf_download_job(pipeline_run_id="...")`
- `trigger_ocr_job(pipeline_run_id="...")`
- `trigger_screening_job(pipeline_run_id="...", stage="full_text")`
- `trigger_extraction_job(pipeline_run_id="...")`
- `trigger_signal_score_job(pipeline_run_id="...")`
- `send_pipeline_run_digest_email(workspace_id="...", pipeline_run_id="...")`

CRITICAL LANGUAGE & RENDERING CONSTRAINTS:
- All output, summaries, status reports, tool responses, and tree renderings generated by AI clients MUST be strictly in English.
- Always display pipeline runs as parent nodes and nested component runs as indented tree leaves (`├──`, `└──`) in English.
- When rendering status trees, ALWAYS format nested component steps with exact metrics:
  - Search & Metadata Ingestion (X papers fetched from <source>)
  - Abstract Screening (X screened: Y passed, Z rejected)
  - PDF Download (X PDFs downloaded)
  - Layout OCR Conversion (X converted / skipped)
  - Full-Text Screening (X screened: Y passed, Z rejected)
  - Parameter & Claim Extraction (X extractions across Y papers and Z definitions)
  - Composite Signal Score Evaluation (X papers scored, Avg: Y, Top: Z)
  - Executive Narrative Reporting (Briefing generated & notifications sent)
- When rendering paper details or fetched paper lists, ALWAYS display the Title, Authors, PDF URL, Full Abstract, and Signal Score for each paper.
"""

mcp = FastMCP("schwarz-research-intelligence", version="1.0.0", instructions=SERVER_INSTRUCTIONS)


SESSION_AUTH_CACHE = {}  # session_id -> (user, workspace, api_key)


def get_auth_context():
    """Retrieve authenticated user, workspace, and api_key from the active HTTP request."""
    try:
        request = get_http_request()
        if request:
            # 1. Check direct dictionary in request.scope['state']
            if hasattr(request, 'scope') and isinstance(request.scope.get('state'), dict):
                req_user = request.scope['state'].get('user')
                if req_user:
                    return req_user, request.scope['state'].get('workspace'), request.scope['state'].get('api_key')

            # 2. Check Starlette request.state
            if hasattr(request, 'state'):
                try:
                    req_user = getattr(request.state, 'user', None)
                    if req_user:
                        return req_user, getattr(request.state, 'workspace', None), getattr(request.state, 'api_key', None)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Could not retrieve HTTP request context: {e}")

    raise PermissionError("Authentication required. Please connect with valid API Key credentials via headers or query parameters.")


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

# ==========================================
# 3. MCP Prompts Registration (AI Client Workflows & Playbooks)
# ==========================================

@mcp.prompt()
def systematic_review_playbook(
    workspace_name: str = "Deep Tech Scouting Review",
    search_topic: str = "Energy-efficient Neuromorphic Computing",
    time_restriction: str = "last 6 months"
) -> str:
    """End-to-end SLR Playbook: Guiding AI clients through Workspace creation, Scraper setup, Agent execution, and Scorecard inspection."""
    return f"""
# 🚀 Systematic Literature Review (SLR) & Deep Tech Scouting Playbook

You are executing a systematic literature review on the Schwarz Research Intelligence platform.
Follow this standard 5-step operational protocol:

### 1. Discover or Create Workspace
- Call `list_workspaces()` to find an existing project, or create a new one:
  `create_workspace(
      name="{workspace_name}",
      abstract_acceptance_criteria="Target research on {search_topic}",
      abstract_rejection_criteria="Out-of-scope or non-peer-reviewed survey summaries",
      full_text_acceptance_criteria="Presents architectural hardware/software benchmarks or experimental energy efficiency metrics",
      full_text_rejection_criteria="High-level opinion pieces without concrete quantitative data"
  )`
  *(Note: OCR provider defaults to None, enabling direct multimodal PDF analysis with Gemini 3.7 Flash).*

### 2. Configure Academic Scrapers (If New Workspace)
- Call `create_scraper(workspace_id="<WORKSPACE_ID>", provider="arxiv", search_query='cat:cs.NE AND "neuromorphic"')`
- Optionally add OpenAlex, Lens, or PubMed scrapers for multi-source ingestion.

### 3. Launch Autonomous State Machine Agent
- Call `start_research_agent(workspace_id="<WORKSPACE_ID>", limit=50, date_range_days=180)`
- Returns a `process_id` and starts the DAG workflow engine (Search -> Abstract Screening -> Download -> OCR -> Full-Text Screening -> Extraction -> Signal Score -> Reporting).

### 4. Check Live Progress & Status
- Real-time status: Call `check_run_status(process_id="<PROCESS_ID>")` to inspect active stage, execution duration, live paper metrics, and a formatted Markdown progress card.

### 5. Retrieve Results & Parameters Scorecard
- Call `get_paper_extractions_matrix(process_id="<PROCESS_ID>")` or `get_paper_extractions_matrix(workspace_id="<WORKSPACE_ID>")`
- Presents accepted papers, extracted parameters, confidence scores, evidence quotes, and composite signal scores.
"""


@mcp.prompt()
def autonomous_research_agent_workflow(
    workspace_id: str,
    limit: str = "50",
    date_range_days: str = "30",
    notification_email: str = None
) -> str:
    """Playbook guiding AI clients through starting, monitoring, pausing, resuming, and checking status for an autonomous Research Agent process."""
    return f"""
# 🤖 Autonomous Research Agent Process Management Guide

Target Execution:
- Workspace ID: {workspace_id}
- Limit: {limit} papers
- Date Window: {date_range_days} days
- Notification Email: {notification_email or 'Active workspace subscribers'}

### 1. Launch Agent
Call `start_research_agent(
    workspace_id="{workspace_id}",
    limit={limit},
    date_range_days={date_range_days},
    notification_email={f'"{notification_email}"' if notification_email else 'None'},
    reprocess_existing=False
)`
*(Set reprocess_existing=True if you want to re-screen and re-extract existing workspace papers without querying external scrapers).*

### 2. Check Execution Status & Progress
Call `check_run_status(process_id="<PROCESS_ID>")`
Returns real-time execution progress, stage breakdown table, paper screening counts, and next-step recommendations.

### 3. Lifecycle Controls
- Pause: `pause_research_agent(process_id="<PROCESS_ID>")`
- Resume: `resume_research_agent(process_id="<PROCESS_ID>")`
- Abort: `abort_research_agent(process_id="<PROCESS_ID>")`
- Purge: `delete_research_agent(process_id="<PROCESS_ID>")`
"""


@mcp.prompt()
def parameter_extraction_and_scorecard_guide(workspace_id: str) -> str:
    """Guide for defining custom JSON parameter schemas, signal score formulas, and retrieving extractions scorecards."""
    return f"""
# 📊 Dynamic Parameter Extraction & Signal Score Playbook

Workspace: {workspace_id}

### 1. View or Create Extraction Definitions
- Call `list_extraction_definitions(workspace_id="{workspace_id}")` to inspect active schemas.
- Call `create_extraction_definition(
      workspace_id="{workspace_id}",
      name="Technical TRL & Fit",
      system_prompt="Extract technology readiness level (1-9) and fit with enterprise architecture.",
      user_prompt_template="Analyze paper: {{paper_title}}\\nAbstract: {{abstract}}\\nFullText: {{full_text}}",
      response_schema={{
          "type": "object",
          "properties": {{
              "trl_level": {{"type": "number", "minimum": 1, "maximum": 9}},
              "fit_score": {{"type": "number", "minimum": 0, "maximum": 10}},
              "novelty_score": {{"type": "number", "minimum": 0, "maximum": 10}}
          }},
          "required": ["trl_level", "fit_score", "novelty_score"]
      }},
      exit_metric="fit_score"
  )`

### 2. Define Custom Signal Score Formula (AST Sandboxed Python)
- Call `update_workspace(
      workspace_id="{workspace_id}",
      signal_score_code="score = 0.5 * fit_score + 0.3 * novelty_score + 0.2 * trl_level\\nreturn round(score, 2)"
  )`

### 3. View Aggregated Results Scorecard
- Call `get_paper_extractions_matrix(workspace_id="{workspace_id}")`
"""


# ==========================================
# 4. MCP Tools Registration
# ==========================================

# --- Workspace Management Tools ---

@mcp.tool()
@with_db_connection
def list_workspaces() -> str:
    """
    [DISCOVERY - WORKSPACES]
    List all workspaces accessible to the authenticated user along with their unique IDs, member roles, default LLM models, and criteria summaries.
    
    WHEN TO USE:
    - Call this tool first to discover available workspace IDs before starting research or listing scrapers.
    
    RETURNS:
    - JSON list of workspaces with workspace_id, name, created_at, role ('admin', 'manager', 'researcher'), and component summaries.
    """
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
    [INSPECTION - WORKSPACE]
    Retrieve complete configuration details, dual-stage criteria, scrapers, OCR engine, screening LLM, dynamic extraction definitions, and member roster for a specific workspace.
    
    WHEN TO USE:
    - Use when you need to inspect the exact abstract/full-text criteria, custom Python signal score formula, or extraction definitions configured for a workspace.
    
    PARAMETERS:
    - workspace_id: The UUID of the target workspace.
    
    RETURNS:
    - JSON payload with full workspace configuration, criteria prompts, scrapers list, extraction targets, and signal_score_code.
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
    abstract_screening_system_prompt: str = None,
    abstract_screening_user_prompt_template: str = None,
    abstract_screening_response_schema: dict = None,
    abstract_screening_exit_metric: str = None,
    full_text_screening_system_prompt: str = None,
    full_text_screening_user_prompt_template: str = None,
    full_text_screening_response_schema: dict = None,
    full_text_screening_exit_metric: str = None,
    ocr_provider: str = None,
    screening_llm_model: str = "google/gemini-3.7-flash",
    llm_provider: str = "google",
    monthly_token_limit: int = 10000000,
    cost_limit_usd: float = 100.00,
    signal_score_code: str = None,
    skip_abstract_screening: bool = False,
    reprocess_existing: bool = False
) -> str:
    """
    [PROJECT SETUP - WORKSPACE]
    Create a new isolated systematic review workspace project. The calling MCP user is automatically assigned as Workspace Admin.
    
    WHEN TO USE:
    - Use when starting a new literature review or technology scouting initiative that requires dedicated criteria, scrapers, and extractions.
    
    PARAMETERS & BEST PRACTICES:
    - name: Human-readable workspace name (e.g. 'Quantum Error Correction Review 2026').
    - abstract_acceptance_criteria: Inclusion prompt evaluated during Abstract Screening (e.g. 'Focus on surface codes and fault-tolerant architectures').
    - abstract_rejection_criteria: Exclusion prompt for abstracts (e.g. 'Pure hardware fabrication without algorithmic error correction').
    - abstract_screening_system_prompt: Optional custom system prompt for abstract screening (leave None for default).
    - abstract_screening_user_prompt_template: Optional custom user prompt template (supports {title}, {abstract}, {acceptance_criteria}, {rejection_criteria}).
    - abstract_screening_response_schema: Optional JSON schema for structured abstract screening outputs.
    - abstract_screening_exit_metric: Optional field key to extract from abstract screening as primary metric (e.g. 'decision_category', 'relevance_score').
    - full_text_acceptance_criteria: Deep full-text inclusion prompt for raw PDF screening (Full-Text Screening).
    - full_text_rejection_criteria: Deep full-text exclusion prompt for raw PDF screening (Full-Text Screening).
    - full_text_screening_system_prompt: Optional custom system prompt for full-text screening (leave None for default).
    - full_text_screening_user_prompt_template: Optional custom user prompt template (supports {title}, {abstract}, {full_text}, {acceptance_criteria}, {rejection_criteria}).
    - full_text_screening_response_schema: Optional JSON schema for structured full-text screening outputs.
    - full_text_screening_exit_metric: Optional field key to extract from full-text screening as primary metric (e.g. 'decision_category', 'fit_score').
    - skip_abstract_screening: Defaults to False. If True, skips Abstract Screening and downloads all candidate papers for direct Full-Text Screening.
    - reprocess_existing: Defaults to False. If True, sets default workspace policy to re-evaluate and re-screen existing papers on pipeline runs.
    - ocr_provider: Defaults to None (skips OCR and passes native PDF binary directly to multimodal Gemini 3.7 Flash). Set to 'pypdf', 'mistral', or 'gemini' only if text layout markdown is explicitly required.
    - screening_llm_model: Default 'google/gemini-3.7-flash'.
    - signal_score_code: Optional sandboxed Python math formula to rank papers (e.g. 'score = 0.6 * fit_score + 0.4 * novelty_score\\nreturn score').
    
    NEXT STEPS:
    - After creating a workspace, configure at least one scraper using `create_scraper(workspace_id=...)`, then launch the agent with `start_research_agent(workspace_id=...)`.
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
        abstract_screening_system_prompt=abstract_screening_system_prompt,
        abstract_screening_user_prompt_template=abstract_screening_user_prompt_template,
        abstract_screening_response_schema=abstract_screening_response_schema,
        abstract_screening_exit_metric=abstract_screening_exit_metric,
        full_text_screening_system_prompt=full_text_screening_system_prompt,
        full_text_screening_user_prompt_template=full_text_screening_user_prompt_template,
        full_text_screening_response_schema=full_text_screening_response_schema,
        full_text_screening_exit_metric=full_text_screening_exit_metric,
        ocr_provider=ocr_provider,
        screening_llm_model=screening_llm_model,
        llm_provider=llm_provider,
        monthly_token_limit=monthly_token_limit,
        monthly_usd_limit=cost_limit_usd,
        signal_score_code=signal_score_code,
        skip_abstract_screening=skip_abstract_screening,
        reprocess_existing=reprocess_existing
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
    abstract_screening_system_prompt: str = None,
    abstract_screening_user_prompt_template: str = None,
    abstract_screening_response_schema: dict = None,
    abstract_screening_exit_metric: str = None,
    full_text_screening_system_prompt: str = None,
    full_text_screening_user_prompt_template: str = None,
    full_text_screening_response_schema: dict = None,
    full_text_screening_exit_metric: str = None,
    ocr_provider: str = None,
    screening_llm_model: str = None,
    llm_provider: str = None,
    monthly_token_limit: int = None,
    cost_limit_usd: float = None,
    signal_score_code: str = None,
    skip_abstract_screening: bool = None,
    reprocess_existing: bool = None
) -> str:
    """
    [SETTINGS UPDATE]
    Update configuration settings, dual-stage criteria, dynamic screening prompts/schemas, or sandboxed Python signal score formula for an existing workspace.
    
    WHEN TO USE:
    - Call to refine screening inclusion/exclusion criteria, customize dynamic screening prompts/schemas, or install/update a custom `signal_score_code` mathematical ranking formula.
    
    KEY PARAMETERS:
    - workspace_id: The UUID of the target workspace.
    - abstract_acceptance_criteria / abstract_rejection_criteria: Inclusion/exclusion prompts for abstract screening.
    - abstract_screening_system_prompt / abstract_screening_user_prompt_template / abstract_screening_response_schema / abstract_screening_exit_metric: Dynamic abstract screening configuration.
    - full_text_acceptance_criteria / full_text_rejection_criteria: Inclusion/exclusion prompts for deep raw PDF screening.
    - full_text_screening_system_prompt / full_text_screening_user_prompt_template / full_text_screening_response_schema / full_text_screening_exit_metric: Dynamic full-text screening configuration.
    - skip_abstract_screening: Set to True to skip Abstract Screening.
    - reprocess_existing: Set default workspace policy to re-evaluate and re-screen existing workspace papers.
    - signal_score_code: Custom Python AST snippet to calculate composite scores (e.g. 'score = 0.5*fit_score + 0.3*novelty_score + 0.2*trl_level\\nreturn round(score, 2)').
    - ocr_provider: 'pypdf', 'mistral', 'gemini', or None/'none' (leave None to skip OCR and pass native PDF to Gemini).
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
        abstract_screening_system_prompt=abstract_screening_system_prompt,
        abstract_screening_user_prompt_template=abstract_screening_user_prompt_template,
        abstract_screening_response_schema=abstract_screening_response_schema,
        abstract_screening_exit_metric=abstract_screening_exit_metric,
        full_text_screening_system_prompt=full_text_screening_system_prompt,
        full_text_screening_user_prompt_template=full_text_screening_user_prompt_template,
        full_text_screening_response_schema=full_text_screening_response_schema,
        full_text_screening_exit_metric=full_text_screening_exit_metric,
        ocr_provider=ocr_provider,
        screening_llm_model=screening_llm_model,
        llm_provider=llm_provider,
        monthly_token_limit=monthly_token_limit,
        cost_limit_usd=cost_limit_usd,
        signal_score_code=signal_score_code,
        skip_abstract_screening=skip_abstract_screening,
        reprocess_existing=reprocess_existing
    )


@mcp.tool()
@with_db_connection
def add_workspace_member(
    workspace_id: str,
    member_username_or_email: str,
    role: str = "researcher"
) -> str:
    """
    [TEAM MANAGEMENT]
    Add a user to a workspace with a specific role ('admin', 'manager', 'researcher').
    """
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
    """
    [DISCOVERY - SCRAPERS]
    List all search query scrapers configured for a workspace (e.g. ArXiv, OpenAlex, Lens, PubMed).
    
    WHEN TO USE:
    - Call to check which queries and academic sources are active before starting a research agent run.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return list_scrapers_logic(user, workspace_id)


@mcp.tool()
@with_db_connection
def get_scraper(scraper_id: str) -> str:
    """
    Retrieve full configuration details for a specific academic scraper by UUID.
    """
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
    """
    [SCRAPER CONFIGURATION]
    Configure a new academic data scraper query for a workspace.
    
    WHEN TO USE:
    - Use when configuring which academic sources and query strings should be ingested during search & ingestion.
    
    SUPPORTED PROVIDERS & QUERY SYNTAX:
    - 'arxiv': Standard ArXiv syntax, e.g. `cat:cs.AI AND "machine learning"` or `all:"solid state battery"`.
    - 'openalex': Keywords and titles, e.g. `quantum computing error correction`.
    - 'lens': Open scholarly query syntax for patents and literature.
    - 'pubmed': Medical / life sciences MeSH query.
    
    NEXT STEPS:
    - After creating a scraper, call `start_research_agent(workspace_id=...)` to begin ingestion.
    """
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
    """
    Update an existing scraper query, provider, limit, or active status.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return update_scraper_logic(user, scraper_id, provider, search_query, limit, sort_by, sort_order, is_active)


@mcp.tool()
@with_db_connection
def delete_scraper(scraper_id: str) -> str:
    """
    Delete a scraper configuration from a workspace.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return delete_scraper_logic(user, scraper_id)


@mcp.tool()
@with_db_connection
def preview_search_query(provider: str, search_query: str, limit: int = 10) -> str:
    """
    [DRY RUN SEARCH]
    Execute a live search query against a provider (arXiv, OpenAlex, Lens) to inspect results without downloading PDFs or saving to DB.
    
    WHEN TO USE:
    - Use when designing and tuning queries to check the volume and quality of results before creating a scraper.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:read")
    except Exception as e:
        return str(e)
    return preview_search_query_logic(user, provider, search_query, limit)


@mcp.tool()
@with_db_connection
def list_papers(workspace_id: str, pipeline_run_id: str | None = None, limit: int = 50) -> str:
    """
    [PAPERS INSPECTION]
    List fetched papers, authors, abstracts, DOIs, and screening statuses for a workspace or pipeline run.
    """
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
    """
    [DISCOVERY - EXTRACTIONS]
    List all dynamic parameter extraction targets (schemas, system prompts, models) configured for a workspace.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:read")
    except Exception as e:
        return str(e)
    return list_extraction_definitions_logic(user, workspace_id)


@mcp.tool()
@with_db_connection
def get_extraction_definition(definition_id: str) -> str:
    """
    Retrieve full JSON schema, system prompt, user template, and model configuration for a specific extraction definition.
    """
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
    exit_metric: str = None,
    llm_model: str = "google/gemini-3.7-flash",
    version: int = 1,
    requires_consensus: bool = False,
    is_active: bool = True
) -> str:
    """
    [PARAMETER DEFINITION]
    Create a new dynamic parameter extraction definition target for a workspace.
    
    WHEN TO USE:
    - Use to define structured JSON parameters that must be extracted from accepted full-text papers during parameter extraction.
    
    PARAMETERS:
    - workspace_id: The UUID of the target workspace.
    - name: Human-readable target name (e.g. 'Schwarz Strategic Fit', 'Hardware Specs', 'TRL Assessment').
    - system_prompt: Guidance for the LLM on how to extract and evaluate fields.
    - user_prompt_template: Template with variables `{{paper_title}}`, `{{abstract}}`, `{{full_text}}`.
    - response_schema: JSON Schema dictionary defining the expected structure, field types, and constraints.
    - exit_metric: Primary key to expose in summary matrices and snake_case variable for signal scoring (e.g. 'fit_score', 'novelty_score', 'trl_level').
    - llm_model: Default 'google/gemini-3.7-flash'.
    """
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
        exit_metric=exit_metric,
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
    exit_metric: str | None = None,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    response_schema: dict | None = None,
    llm_model: str | None = None,
    version: int | None = None,
    requires_consensus: bool | None = None,
    is_active: bool | None = None
) -> str:
    """Update an existing extraction definition's schema, prompts, exit_metric key, or LLM configuration."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:write")
    except Exception as e:
        return str(e)
    return update_extraction_definition_logic(
        user=user,
        definition_id=definition_id,
        name=name,
        exit_metric=exit_metric,
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
def trigger_search_job(
    workspace_id: str,
    scraper_id: str | None = None,
    limit: int = None,
    reprocess_existing: bool = False,
    date_range_days: int | None = None,
    query_prefix: str | None = None
) -> str:
    """[MANUAL COMPONENT ONLY] Trigger Search & Metadata Ingestion. Set limit to integer (e.g. 50) or None (all results from scraper). Note: To run the full end-to-end pipeline automatically, use start_research_agent instead."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_search_job_logic(user, workspace_id, scraper_id, limit, reprocess_existing, date_range_days, query_prefix)


@mcp.tool()
@with_db_connection
def trigger_pdf_download_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = None) -> str:
    """[MANUAL COMPONENT ONLY] Trigger PDF Binary Download. If limit is None, downloads all papers in the run. Note: To run the full end-to-end pipeline automatically, use start_research_agent instead."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_pdf_download_job_logic(user, pipeline_run_id, workspace_id, limit)


@mcp.tool()
@with_db_connection
def trigger_ocr_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = None) -> str:
    """[MANUAL COMPONENT ONLY] Trigger Layout OCR Extraction. If limit is None, converts all downloaded PDFs in the run. Note: To run the full end-to-end pipeline automatically, use start_research_agent instead."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_ocr_job_logic(user, pipeline_run_id, workspace_id, limit)


@mcp.tool()
@with_db_connection
def trigger_screening_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = None, stage: str = "abstract") -> str:
    """[MANUAL COMPONENT ONLY] Trigger Abstract or Full-Text Screening. If limit is None, screens all candidate papers. Supports stage='abstract' or stage='full_text'. Note: To run the full end-to-end pipeline automatically, use start_research_agent instead."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_screening_job_logic(user, pipeline_run_id, workspace_id, limit, stage=stage)


@mcp.tool()
@with_db_connection
def trigger_extraction_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = None) -> str:
    """[MANUAL COMPONENT ONLY] Trigger Parameter & Claim Extraction. If limit is None, extracts parameters from all accepted papers. Note: To run the full end-to-end pipeline automatically, use start_research_agent instead."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_extraction_job_logic(user, pipeline_run_id, workspace_id, limit)


@mcp.tool()
@with_db_connection
def trigger_signal_score_job(pipeline_run_id: str, limit: int = None) -> str:
    """[MANUAL COMPONENT ONLY] Trigger Composite Signal Score Evaluation. If limit is None, evaluates signal score for all screened and accepted papers."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_signal_score_job_logic(user, pipeline_run_id, limit)


@mcp.tool()
@with_db_connection
def trigger_reporting_job(pipeline_run_id: str, recipient_override: list[str] = None) -> str:
    """[MANUAL COMPONENT ONLY] Trigger Executive Narrative Reporting & Notification Dispatch. Compiles executive briefing and dispatches email digests."""
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_reporting_job_logic(user, pipeline_run_id, recipient_override)


@mcp.tool()
@with_db_connection
def list_extractions(
    workspace_id: str = None,
    pipeline_run_id: str = None,
    process_id: str = None,
    paper_id: str = None,
    category: str = None,
    validation_status: str = None,
    limit: int = 100
) -> str:
    """
    [EXTRACTIONS QUERY]
    Query raw dynamic extraction objects with confidence scores, validation flags ('pass', 'warn', 'fail'), and evidence quotes.
    
    WHEN TO USE:
    - Call to inspect low-level extraction items filtered by workspace, pipeline run, paper, category, or validation status.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return list_extractions_logic(user, workspace_id, pipeline_run_id, process_id, paper_id, category, validation_status, limit)


@mcp.tool()
@with_db_connection
def get_paper_extractions_matrix(
    workspace_id: str = None,
    pipeline_run_id: str = None,
    process_id: str = None,
    screening_status: str = "full_text_passed",
    limit: int = 100
) -> str:
    """
    [PRIMARY TOOL FOR RUN RESULTS & PARAMETERS SCORECARD]
    Retrieve aggregated parameter & claim extraction results per paper for all accepted/screened papers in a single structured call.
    
    WHEN TO USE:
    - ALWAYS call this tool when asked to:
      • "Show review results"
      • "Display extracted parameters / metrics"
      • "Show technology scorecard"
      • "What papers passed screening and what were their scores?"
    
    RETURNS:
    - Aggregated list of papers with titles, authors, DOI, arXiv ID, PDF paths, abstracts, screening reasons, and all extracted definitions (e.g. Schwarz Fit, Novelty, TRL, Rigour) with evidence quotes and composite signal scores.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_paper_extractions_matrix_logic(user, workspace_id, pipeline_run_id, process_id, screening_status, limit)


@mcp.tool()
@with_db_connection
def get_extraction(extraction_id: str) -> str:
    """
    Retrieve full details for a single Extraction record by UUID, including raw LLM prompt, extracted JSON data, evidence quotes, and validation history.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_extraction_logic(user, extraction_id)


@mcp.tool()
@with_db_connection
def get_pipeline_run_status(pipeline_run_id: str) -> str:
    """
    Retrieve execution state, active component step, paper count metrics, and storage footprint for a PipelineRun.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:read")
    except Exception as e:
        return str(e)
    return get_pipeline_run_status_logic(user, pipeline_run_id)


@mcp.tool()
@with_db_connection
def get_component_run_status(component_run_id: str) -> str:
    """
    Retrieve status, logs, error tracebacks, and execution metrics for a single component step run.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:read")
    except Exception as e:
        return str(e)
    return get_component_run_status_logic(user, component_run_id)


@mcp.tool()
@with_db_connection
def abort_job(component_run_id: str | None = None, pipeline_run_id: str | None = None) -> str:
    """
    Abort a running component step or full PipelineRun (requires Admin or Manager role).
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return abort_job_logic(user, component_run_id, pipeline_run_id)


@mcp.tool()
@with_db_connection
def list_pipeline_runs(workspace_id: str, limit: int = 20) -> str:
    """
    List recent PipelineRuns for a workspace with stage, status, paper counts, duration, and token usage.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:read")
    except Exception as e:
        return str(e)
    return list_pipeline_runs_logic(user, workspace_id, limit)


@mcp.tool()
@with_db_connection
def delete_pipeline_run(pipeline_run_id: str) -> str:
    """
    Purge a PipelineRun record from database and recursively delete all storage artifacts (PDFs, Markdown, JSON) from disk.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return delete_pipeline_run_logic(user, pipeline_run_id)


@mcp.tool()
@with_db_connection
def start_research_agent(
    workspace_id: str,
    name: str = None,
    limit: int = None,
    date_range_days: int = None,
    query_prefix: str = None,
    skip_abstract_screening: bool = None,
    notification_email: str = None,
    reprocess_existing: bool = False
) -> str:
    """
    [PRIMARY SLR ORCHESTRATOR - RECOMMENDED ENTRYPOINT]
    Launch an autonomous state engine process (ResearchAgentProcess) executing the complete end-to-end SLR pipeline:
    Search & Ingestion -> Download PDFs -> OCR (auto-skipped if None) -> Dual-Stage Screening (Abstract + Full-Text via Gemini 3.7) -> Dynamic Parameter Extraction -> Composite Signal Scoring -> Executive Narrative.
    
    WHEN TO USE:
    - Primary entrypoint to run a review. Do not trigger individual steps manually unless debugging.
    
    KEY PARAMETERS:
    - workspace_id: The target workspace UUID.
    - limit: Optional maximum number of papers to ingest and process across all steps (default: None = all papers found by scrapers).
    - date_range_days: Optional date window filter (e.g. 30, 90, 180, 365).
    - query_prefix: Optional query modifier prepended to workspace scrapers.
    - reprocess_existing: Set to True to re-screen and re-extract parameters from already-ingested workspace papers.
    - notification_email: Optional email to notify via Mailgun upon pipeline completion.
    
    NEXT STEPS:
    - Immediately after calling this, call `check_run_status(process_id=...)` to check real-time progress without blocking, or query `get_paper_extractions_matrix(process_id=...)` once complete.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return start_research_agent_logic(user, workspace_id, name, limit, date_range_days, query_prefix, skip_abstract_screening, notification_email, reprocess_existing)


@mcp.tool()
@with_db_connection
def list_research_agents(workspace_id: str = None, limit: int = 20) -> str:
    """
    List active or recent autonomous Research Agent Processes with current state, execution time, and paper counts.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return list_research_agents_logic(user, workspace_id, limit)


@mcp.tool()
@with_db_connection
def check_run_status(process_id: str = None, pipeline_run_id: str = None, run_id: str = None) -> str:
    """
    [PRIMARY LIVE RUN STATUS & REAL-TIME PROGRESS INSPECTOR]
    Checks the real-time execution status of an autonomous SLR Research Agent Process or Pipeline Run.
    Non-blocking: advances the state machine if active and returns the active stage, execution duration,
    what has already completed vs in-progress vs pending, paper metrics, token/cost usage, and a beautiful
    visual Markdown progress card (summary_markdown) with progress bars and timeline tables.

    WHEN TO USE:
    - Primary tool to monitor pipeline progress immediately after `start_research_agent`.
    - Check what stage is currently executing, paper screening counts, and next-step recommendations.

    PARAMETERS:
    - process_id (str, optional): UUID of the ResearchAgentProcess returned by `start_research_agent`.
    - pipeline_run_id (str, optional): UUID of a PipelineRun.
    - run_id (str, optional): Alias for process_id or pipeline_run_id.

    RETURNS:
    - `summary_markdown`: Formatted Markdown report with ASCII progress bars, stage timeline table, paper counts, and top papers.
    - `is_finished`: Boolean indicating whether execution completed, failed, or was aborted/halted.
    - `status`: Current state ('running', 'completed', 'failed', 'paused', 'aborted').
    - `current_step` & `current_step_display`: Active/final SLR stage name (e.g. 'Dual-Stage Screening').
    - `progress_percent`: Estimated percentage of total pipeline completion (0-100%).
    - `duration_seconds` & `execution_time`: Total execution elapsed time (e.g. 45.2, '45s').
    - `stages_breakdown`: Detailed breakdown of all 7 SLR stages (Search, Download, OCR, Screening, Extraction, Signal Score, Reporting).
    - `paper_metrics`: Live paper counts (ingested, downloaded, abstract/full-text screened, accepted, extractions count, AI tokens, USD cost).
    - `top_papers_preview`: Preview of top accepted papers with signal scores and extracted parameters.
    - `next_action_recommendation`: Contextual advice on what tool to call next.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return check_run_status_logic(user, process_id=process_id, pipeline_run_id=pipeline_run_id, run_id=run_id)


@mcp.tool()
@with_db_connection
def get_pipeline_logs(process_id: str = None, pipeline_run_id: str = None, run_id: str = None, limit: int = 50) -> str:
    """
    [LIVE TERMINAL & WORKER LOGS INSPECTOR]
    Retrieves live execution logs, active Celery worker thread status, and progress telemetry for a running pipeline.
    
    WHEN TO USE:
    - Inspect real-time console/terminal output to see what papers are currently being processed or screened.
    - Check if a background task is actively computing or if an error occurred.
    - Avoid infinite sleep loops by checking immediate worker telemetry.
    
    PARAMETERS:
    - process_id (str, optional): UUID of the ResearchAgentProcess.
    - pipeline_run_id (str, optional): UUID of the PipelineRun.
    - limit (int, optional): Number of recent log lines to return (default 50).
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_pipeline_logs_logic(user, process_id=process_id, pipeline_run_id=pipeline_run_id, run_id=run_id, limit=limit)


@mcp.tool()
@with_db_connection
def get_research_agent_status(process_id: str) -> str:
    """
    [REAL-TIME AGENT MONITORING]
    Retrieve state machine status, active step, full audit trail, component runs tree, token usage, USD cost, and scorecard preview for an agent process.
    
    WHEN TO USE:
    - Use to inspect agent progress during asynchronous execution or to examine detailed step execution times and error tracebacks.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_research_agent_status_logic(user, process_id)


@mcp.tool()
@with_db_connection
def pause_research_agent(process_id: str) -> str:
    """
    Pause a running autonomous Research Agent Process without losing state.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return pause_research_agent_logic(user, process_id)


@mcp.tool()
@with_db_connection
def resume_research_agent(process_id: str) -> str:
    """
    Resume a paused Research Agent Process and trigger the DAG state engine to continue execution from the active step.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return resume_research_agent_logic(user, process_id)


@mcp.tool()
@with_db_connection
def abort_research_agent(process_id: str) -> str:
    """
    Abort an active Research Agent Process and cancel all associated background Celery worker tasks.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return abort_research_agent_logic(user, process_id)


@mcp.tool()
@with_db_connection
def delete_research_agent(process_id: str) -> str:
    """
    Purge a Research Agent Process record, pipeline run, downloaded documents from storage, and database extractions.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return delete_research_agent_logic(user, process_id)


@mcp.tool()
@with_db_connection
def get_workflow_dag_schema(workspace_id: str | None = None) -> str:
    """
    [DAG INTROSPECTION & CONTRACTS]
    Returns the complete Systematic Literature Review (SLR) Workflow DAG schema, execution topology,
    dependencies, input contracts, and output contracts for each node.
    
    WHEN TO USE:
    - Call whenever you want to inspect how the pipeline is wired, what prerequisites each step has, what data models are mutated, and what storage artifacts are produced.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_workflow_dag_schema_logic(user, workspace_id)



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


@mcp.tool()
@with_db_connection
def get_document_registry_stats() -> str:
    """
    Returns global efficiency analytics and cache metrics for the DocumentRegistry:
    - Total cached papers and binary footprint (bytes/MB/GB)
    - Total cache hits / reuse count (bandwidth and OCR compute saved)
    - Top reused research documents across workspaces
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_document_registry_stats_logic(user)


# 3. Pure ASGI HTTP/SSE Request Authentication Middleware
class QueryParamAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        response_started = False

        async def wrapped_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        path = scope.get("path", "")
        if path in ["/", "/health", "/health/", "/docs", "/openapi.json"]:
            try:
                return await self.app(scope, receive, wrapped_send)
            except (asyncio.CancelledError, ClientDisconnect):
                return
            except Exception:
                if response_started:
                    return
                raise

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
            scope.setdefault("state", {})
            scope["state"]["user"] = user
            scope["state"]["workspace"] = workspace
            scope["state"]["api_key"] = api_key
            try:
                return await self.app(scope, receive, wrapped_send)
            except (asyncio.CancelledError, ClientDisconnect):
                return
            except Exception:
                if response_started:
                    return
                raise

        async def send_error(status_code: int, error_message: str):
            if response_started:
                return
            body = f'{{"error": "{error_message}"}}'.encode('utf-8')
            await wrapped_send({
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode('utf-8'))
                ]
            })
            await wrapped_send({
                "type": "http.response.body",
                "body": body
            })

        try:
            @sync_to_async
            def verify_credentials():
                from django.db import connection
                try:
                    if connection.vendor != 'sqlite':
                        close_old_connections()
                    if key_id and secret:
                        try:
                            key_obj = APIKey.objects.select_related('user', 'workspace').get(key_id=key_id, is_active=True)
                            if key_obj.check_secret(secret):
                                key_obj.update_last_used()
                                return key_obj.user, key_obj.workspace, key_obj
                        except APIKey.DoesNotExist:
                            pass
                    return None, None, None
                finally:
                    if connection.vendor != 'sqlite':
                        close_old_connections()

            user_obj, ws_obj, api_key_obj = await verify_credentials()

            if not user_obj:
                return await send_error(
                    401,
                    "Authentication required. Please provide valid api_key_id and api_secret credentials via headers (x-api-key-id / x-api-secret) or query parameters."
                )

            if session_id:
                SESSION_AUTH_CACHE[session_id] = (user_obj, ws_obj, api_key_obj)

            scope.setdefault("state", {})
            scope["state"]["user"] = user_obj
            scope["state"]["workspace"] = ws_obj
            scope["state"]["api_key"] = api_key_obj

        except Exception as e:
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(e)
            except Exception:
                pass
            return await send_error(500, f"Authentication internal error: {str(e)}")

        try:
            return await self.app(scope, receive, wrapped_send)
        except (asyncio.CancelledError, ClientDisconnect):
            return
        except Exception as exc:
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(exc)
            except Exception:
                pass
            if response_started:
                return
            raise


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


@mcp.tool()
@with_db_connection
def send_pipeline_run_digest_email(
    workspace_id: str,
    pipeline_run_id: str,
    recipient_override: list[str] | None = None,
    async_dispatch: bool = False
) -> str:
    """
    Send an executive email report and parameter extraction scorecard to all active workspace subscribers (or custom recipients) for a completed PipelineRun.
    Requires that the pipeline run is completed and has extractions ready.
    Generates a responsive HTML email with KPI metrics (papers fetched, screened, accepted, cost, tokens) and accepted paper parameter summaries via Mailgun.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return send_pipeline_run_digest_email_logic(user, workspace_id, pipeline_run_id, recipient_override, async_dispatch)


# --- Interactive Knowledge Explorer & Paper Chat Tools ---

@mcp.tool()
@with_db_connection
def ask_paper(
    workspace_id: str,
    question: str,
    paper_id: str | None = None,
    session_id: str | None = None,
    deep_thinking: bool = False
) -> str:
    """
    [INTERACTIVE Q&A - KNOWLEDGE EXPLORER / ASK PAPER]
    Interrogates an ingested academic paper or whole workspace with deep scientific reasoning using the workspace LLM (Google Gemini 3.7 Flash).
    
    WHEN TO USE:
    - Use when the researcher or agent needs to examine a specific paper, verify experimental methodology, analyze claims,
      clarify why the SLR pipeline accepted or rejected it, or deep-dive into computed composite signal scores and extracted parameters.
    
    WORKFLOW & USAGE PATTERN FOR AI CLIENTS:
    1. Locate the target paper's UUID via `list_papers(workspace_id)` (or omit `paper_id` for workspace-level synthesis).
    2. Turn 1 (Start session): Call `ask_paper(workspace_id=..., question=..., paper_id=..., deep_thinking=True/False)`.
       The JSON response returns a unique `session_id`.
    3. Turn 2+ (Continue dialogue): Pass the returned `session_id` in subsequent calls to maintain conversational memory and multi-turn context with Gemini Context Caching.
    
    AUTOMATICALLY INJECTED SCIENTIFIC CONTEXT:
    - Full Document Content: Layout OCR Markdown or native multimodal PDF binary from storage.
    - SLR Screening Decision: Status (`screening_status`), decision rationale (`screening_reasoning`), and workspace acceptance/rejection criteria.
    - Parameter Extraction Matrix: All extracted parameter definitions, JSON values, evidence quotes, and HITL validation flags.
    - Composite Signal Score: Calculated score (`paper.signal_score`), audit details (`signal_score_details`), and the sandboxed Python formula (`workspace.signal_score_code`).
    - Multi-Turn History: All preceding questions and answers within the conversation thread.
    - Visual Grounding: Automatically parses and verifies figure/table/page citations with bounding boxes.
    - Hallucination Guard: Validates quoted claims against the source document.
    - Gemini Context Cache: Automatically reuses server-side cached tokens for repeated turns.
    
    PARAMETERS:
    - workspace_id: Target workspace UUID.
    - question: Detailed research question or instruction.
    - paper_id: (Optional) Target Paper UUID to interrogate. Omit to query workspace overview.
    - session_id: (Optional) UUID of an existing conversation session to continue. Omit to start a new session.
    - deep_thinking: (Optional) Set to True to enable deep mathematical/thermodynamic derivation scratchpad reasoning.
    
    OUTPUT:
    JSON string containing `{ "status": "completed", "session_id": "...", "message_id": "...", "paper_id": "...", "paper_title": "...", "answer": "...", "citations": [...], "visual_citations": [...], "hallucination_guard": {...}, "deep_thinking": bool, "tokens_in": int, "tokens_out": int, "usd_cost": float, "cached_content": str }`.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return ask_paper_logic(user, workspace_id, question, paper_id=paper_id, session_id=session_id, deep_thinking=deep_thinking)


def create_app():
    starlette_app = mcp.http_app(transport="sse", middleware=[])
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def health_endpoint(request):
        return JSONResponse({"status": "healthy", "service": "fastmcp"})

    starlette_app.routes.append(Route("/health", health_endpoint, methods=["GET"]))
    starlette_app.routes.append(Route("/health/", health_endpoint, methods=["GET"]))

    from starlette.middleware import Middleware
    starlette_app.user_middleware.insert(0, Middleware(QueryParamAuthMiddleware))
    starlette_app.middleware_stack = starlette_app.build_middleware_stack()
    return starlette_app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)

