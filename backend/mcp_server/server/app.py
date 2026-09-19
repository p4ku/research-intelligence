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
    set_extraction_frontend_metrics_logic,
    list_extractions_logic,
    get_paper_extractions_matrix_logic,
    get_extraction_logic,
    get_paper_scoreboard_logic,
    trigger_search_job_logic,
    start_pipeline_run_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
    trigger_signal_score_job_logic,
    trigger_reporting_job_logic,
    get_pipeline_run_status_logic,
    get_component_run_status_logic,
    pause_pipeline_run_logic,
    resume_pipeline_run_logic,
    rerun_pipeline_from_step_logic,
    reexecute_component_run_logic,
    tick_pipeline_run_logic,
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
    list_users_logic,
    get_user_logic,
    create_user_logic,
    update_user_logic,
    delete_user_logic,
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
                    # Ids and outcome only, never the tool's answer: ask_paper
                    # returns the whole reply, and admins read these rows.
                    parsed = None
                    if isinstance(result, str) and len(result) < 2000:
                        try:
                            parsed = json.loads(result)
                        except Exception:
                            pass
                    out_sum = {
                        "result_length": len(str(result)),
                        **UserActivityLog.summarise_output(parsed),
                    }

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
   - Call `start_research_agent(workspace_id="<WS_ID>", limit=50, n_last_days=30)`.
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

=======================================================
STRICT BEHAVIOR RULES FOR RUNNING & MONITORING BACKGROUND PIPELINES:
=======================================================
1. NEVER MODIFY SOURCE CODE WHILE A PIPELINE RUN IS IN PROGRESS:
   - Pipeline stages (Search, Screening, PDF Download, OCR, Extraction, Signal Scoring) run asynchronously on Celery background workers.
   - Processing multimodal papers with reasoning LLMs (Gemini 3.8 Flash Thinking) takes 15-30 seconds PER PAPER/DEFINITION. An extraction run with 130 items naturally takes 10 to 20 minutes!
   - This delay is completely normal. NEVER assume the pipeline is broken because it takes time.
   - NEVER open, edit, or modify codebase files (e.g. extract.py, settings.py, models.py, etc.) while waiting for a run or when a run is active. Modifying source code while background workers are processing corrupts jobs and is strictly forbidden.

2. PROGRESS MONITORING & STATUS REPORTING:
   - Call `check_run_status(process_id="...")` or `get_pipeline_run_status(pipeline_run_id="...")`.
   - Inspect the `active_progress` field:
     * When `is_progressing: true`: Explain clearly to the user which stage is active, the exact count and percentage (e.g. "Currently on Parameter & Claim Extraction: 55/130 completed (42.3%), running for 13m 23s"), and reassure them that progress is advancing normally.
     * When `is_stalled: true`: Report honestly to the user: "Progress appears stalled at 55/130 for X minutes without new items completed. The background Celery worker or network socket may be hung." Offer to check worker logs or re-trigger the step, but DO NOT modify code!
     * When `is_finished: true`: Report the final scorecard and results using `get_paper_extractions_matrix`.

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


from .session_cache import FastMCPSessionCache

SESSION_AUTH_CACHE = FastMCPSessionCache(max_size=1000, ttl_seconds=900.0)


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
  *(Note: OCR provider defaults to None, enabling direct multimodal PDF analysis with Gemini 3.8 Flash).*

### 2. Configure Academic Scrapers (If New Workspace)
- Call `create_scraper(workspace_id="<WORKSPACE_ID>", provider="arxiv", search_query='cat:cs.NE AND "neuromorphic"')`
- Optionally add OpenAlex or Lens scrapers for multi-source ingestion.

### 3. Launch Autonomous State Machine Agent
- Date Filtering Options:
  * Option A (Relative Days): `start_research_agent(workspace_id="<WORKSPACE_ID>", limit=50, n_last_days=180)`
  * Option B (Explicit Range): `start_research_agent(workspace_id="<WORKSPACE_ID>", limit=50, start_date="2026-03-01", end_date="2026-09-01")`
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
    n_last_days: str = "7",
    start_date: str = "",
    end_date: str = "",
    notification_email: str = None
) -> str:
    """Playbook guiding AI clients through starting, monitoring, pausing, resuming, and checking status for an autonomous Research Agent process."""
    date_desc = f"Explicit range [{start_date} to {end_date}]" if (start_date or end_date) else f"{n_last_days} days lookback"
    return f"""
# 🤖 Autonomous Research Agent Process Management Guide

Target Execution:
- Workspace ID: {workspace_id}
- Limit: {limit} papers
- Date Window: {date_desc}
- Notification Email: {notification_email or 'Active workspace subscribers'}

### 1. Launch Agent
Call `start_research_agent(
    workspace_id="{workspace_id}",
    limit={limit},
    n_last_days={n_last_days if not (start_date or end_date) else 'None'},
    start_date={f'"{start_date}"' if start_date else 'None'},
    end_date={f'"{end_date}"' if end_date else 'None'},
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
      exit_metrics=["fit_score"],
      primary_frontend_metric="fit_score",
      secondary_frontend_metrics=["novelty_score", "trl_level"]
  )`
- Or call `set_extraction_frontend_metrics(definition_id="...", primary_frontend_metric="fit_score", secondary_frontend_metrics=["novelty_score"])` to reconfigure metrics anytime.

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
    abstract_screening_system_prompt: str | None = None,
    abstract_screening_user_prompt_template: str | None = None,
    abstract_screening_response_schema: dict | None = None,
    abstract_screening_exit_metric: str | None = None,
    full_text_screening_system_prompt: str | None = None,
    full_text_screening_user_prompt_template: str | None = None,
    full_text_screening_response_schema: dict | None = None,
    full_text_screening_exit_metric: str | None = None,
    narrative_report_prompt: str | None = None,
    narrative_report_system_prompt: str | None = None,
    narrative_report_top_n_papers: int = 10,
    ocr_provider: str | None = None,
    screening_llm_model: str = "google/gemini-3.8-flash",
    llm_provider: str = "google",
    monthly_token_limit: int = 10000000,
    cost_limit_usd: float = 100.00,
    signal_score_code: str | None = None,
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
    - narrative_report_prompt: Optional custom user prompt template for Step 7 Executive Briefing narrative generation. If set, an LLM synthesizes an executive briefing based on the top N accepted papers ranked by signal score. If empty/None, a deterministic markdown summary is generated.
      Available prompt variables:
      * {papers}: Formatted numbered catalog of top N papers including title, authors, publication date, DOI/URL, signal score, abstract, and extracted score vectors.
      * {papers_json}: Structured JSON list of top papers with metadata and all score vectors/variables.
      * {score_vectors_summary}: High-level summary of score variables and weights across top papers.
      * {workspace_name}: Name of the workspace.
      * {run_date}: Execution date/time of the pipeline run.
      * {run_id}: Pipeline run UUID.
      * {total_papers}: Total papers processed in the run.
      * {accepted_papers_count}: Total accepted papers count.
      * {rejected_papers_count}: Total rejected papers count.
      * {avg_signal_score}: Average signal score across accepted papers.
      * {top_n_papers_count}: Number of top papers provided to this prompt (e.g. 10).
    - narrative_report_system_prompt: Optional custom system instruction for the LLM generating the narrative briefing (defaults to 'You are an elite research intelligence strategist and executive briefing specialist.').
    - narrative_report_top_n_papers: Number of top accepted papers ranked by signal score to feed into the briefing prompt (default: 10, clamped 1-50).
    - skip_abstract_screening: Defaults to False. If True, skips Abstract Screening and downloads all candidate papers for direct Full-Text Screening.
    - reprocess_existing: Defaults to False. If True, sets default workspace policy to re-evaluate and re-screen existing papers on pipeline runs.
    - ocr_provider: Defaults to None (skips OCR and passes native PDF binary directly to multimodal Gemini 3.8 Flash). Set to 'pypdf', 'mistral', or 'gemini' only if text layout markdown is explicitly required.
    - screening_llm_model: Default 'google/gemini-3.8-flash'.
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
        narrative_report_prompt=narrative_report_prompt,
        narrative_report_system_prompt=narrative_report_system_prompt,
        narrative_report_top_n_papers=narrative_report_top_n_papers,
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
    name: str | None = None,
    abstract_acceptance_criteria: str | None = None,
    abstract_rejection_criteria: str | None = None,
    full_text_acceptance_criteria: str | None = None,
    full_text_rejection_criteria: str | None = None,
    abstract_screening_system_prompt: str | None = None,
    abstract_screening_user_prompt_template: str | None = None,
    abstract_screening_response_schema: dict | None = None,
    abstract_screening_exit_metric: str | None = None,
    full_text_screening_system_prompt: str | None = None,
    full_text_screening_user_prompt_template: str | None = None,
    full_text_screening_response_schema: dict | None = None,
    full_text_screening_exit_metric: str | None = None,
    narrative_report_prompt: str | None = None,
    narrative_report_system_prompt: str | None = None,
    narrative_report_top_n_papers: int | None = None,
    ocr_provider: str | None = None,
    screening_llm_model: str | None = None,
    llm_provider: str | None = None,
    monthly_token_limit: int | None = None,
    cost_limit_usd: float | None = None,
    signal_score_code: str | None = None,
    skip_abstract_screening: bool | None = None,
    reprocess_existing: bool | None = None
) -> str:
    """
    [SETTINGS UPDATE]
    Update configuration settings, dual-stage criteria, dynamic screening prompts/schemas, or sandboxed Python signal score formula for an existing workspace.
    
    WHEN TO USE:
    - Call to refine screening inclusion/exclusion criteria, customize dynamic screening prompts/schemas, install/update a custom `signal_score_code` mathematical ranking formula, or customize executive briefing prompts.
    
    KEY PARAMETERS:
    - workspace_id: The UUID of the target workspace.
    - abstract_acceptance_criteria / abstract_rejection_criteria: Inclusion/exclusion prompts for abstract screening.
    - abstract_screening_system_prompt / abstract_screening_user_prompt_template / abstract_screening_response_schema / abstract_screening_exit_metric: Dynamic abstract screening configuration.
    - full_text_acceptance_criteria / full_text_rejection_criteria: Inclusion/exclusion prompts for deep raw PDF screening.
    - full_text_screening_system_prompt / full_text_screening_user_prompt_template / full_text_screening_response_schema / full_text_screening_exit_metric: Dynamic full-text screening configuration.
    - narrative_report_prompt: Custom user prompt template for Step 7 Executive Briefing narrative generation (supports {papers}, {papers_json}, {score_vectors_summary}, {workspace_name}, {run_date}, {run_id}, {total_papers}, {accepted_papers_count}, {rejected_papers_count}, {avg_signal_score}, {top_n_papers_count}).
    - narrative_report_system_prompt: Custom system instruction for narrative briefing synthesis.
    - narrative_report_top_n_papers: Number of top accepted papers ranked by signal score to pass to the briefing prompt (e.g. 10).
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
        narrative_report_prompt=narrative_report_prompt,
        narrative_report_system_prompt=narrative_report_system_prompt,
        narrative_report_top_n_papers=narrative_report_top_n_papers,
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
    List all search query scrapers configured for a workspace (e.g. ArXiv, OpenAlex, Lens).
    
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
    limit: int = 2000,
    sort_by: str = "relevance",
    sort_order: str = "desc",
    n_last_days: int = 7,
    is_active: bool = True
) -> str:
    """
    [SCRAPER CONFIGURATION]
    Configure a new academic data scraper query for a workspace.
    
    WHEN TO USE:
    - Use when configuring which academic sources and query strings should be ingested during search & ingestion.
    
    DEFAULT DATE LOOKBACK CONFIGURATION:
    - `n_last_days` (default: 7): Sets the baseline lookback window in days for this scraper.
      When a pipeline run or agent runs without explicit start_date / end_date, it queries papers published
      within the last N days (`now() - N days` to `now()`).
    
    SUPPORTED PROVIDERS & QUERY SYNTAX:
    - 'arxiv': Standard ArXiv syntax, e.g. `cat:cs.AI AND "machine learning"` or `all:"solid state battery"`.
    - 'openalex': Keywords and titles, e.g. `quantum computing error correction`.
    - 'lens': Open scholarly query syntax for patents and literature.
    
    NEXT STEPS:
    - After creating a scraper, call `start_research_agent(workspace_id=...)` to begin ingestion.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return create_scraper_logic(user, workspace_id, provider, search_query, limit, sort_by, sort_order, n_last_days, is_active)


@mcp.tool()
@with_db_connection
def update_scraper(
    scraper_id: str,
    provider: str | None = None,
    search_query: str | None = None,
    limit: int | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    n_last_days: int | None = None,
    is_active: bool | None = None
) -> str:
    """
    Update an existing scraper query, provider, limit, default lookback days (n_last_days), or active status.
    
    PARAMETERS:
    - scraper_id: UUID of the scraper to update (required).
    - n_last_days: Default past days lookback window (e.g. 7, 14, 30) used when pipeline runs omit explicit start_date / end_date.
    - limit: Max candidate results to fetch per run.
    - is_active: Enable (True) or disable (False) this scraper.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "scrapers:write")
    except Exception as e:
        return str(e)
    return update_scraper_logic(user, scraper_id, provider, search_query, limit, sort_by, sort_order, n_last_days, is_active)


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
def preview_search_query(
    provider: str,
    search_query: str,
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
    n_last_days: int | None = 7,
    workspace_id: str | None = None,
    api_key: str | None = None,
) -> str:
    """
    [DRY RUN SEARCH]
    Execute a live search query against a provider (arXiv, OpenAlex, Lens, Google Patents) to inspect results without downloading PDFs or saving to DB.
    
    WHEN TO USE:
    - Use when designing and tuning queries to check the volume and quality of results before creating a scraper.
    
    DATE FILTERING MODES (EITHER RELATIVE DAYS OR EXPLICIT DATES):
    You can test queries using EITHER a relative lookback window OR explicit calendar dates:
    1. RELATIVE LOOKBACK (Option A):
       - Pass `n_last_days` (e.g. 7, 14, 30). Searches literature published from `now() - N days` to `now()`.
       - Defaults to 7 if start_date and end_date are omitted.
    2. EXPLICIT DATE RANGE (Option B):
       - Pass `start_date` ('YYYY-MM-DD') and/or `end_date` ('YYYY-MM-DD').
       - If both provided: searches precisely within [start_date TO end_date].
       - If only start_date: searches from start_date to now().
       - If only end_date: searches from (end_date - n_last_days) to end_date.
    
    PARAMETERS:
    - provider: Academic provider ('arxiv', 'openalex', 'lens', 'google_patents').
    - search_query: Query string to test against the provider.
    - limit: Max candidate results to return (1-50, default: 10).
    - start_date: Optional ISO start date string (e.g. '2026-08-01').
    - end_date: Optional ISO end date string (e.g. '2026-08-31').
    - n_last_days: Optional lookback window in days (default: 7).
    - workspace_id: Optional workspace UUID string to prioritize workspace-configured scraper API keys.
    - api_key: Optional explicit API key override (e.g. SerpApi or Lens API key).
    """

    try:
        user, workspace, auth_api_key = get_auth_context()
        check_scope(auth_api_key, "scrapers:read")
    except Exception as e:
        return str(e)

    effective_ws_id = workspace_id or (str(workspace.id) if workspace else None)
    return preview_search_query_logic(
        user,
        provider,
        search_query,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        n_last_days=n_last_days,
        workspace_id=effective_ws_id,
        api_key=api_key,
    )



@mcp.tool()
@with_db_connection
def list_papers(workspace_id: str, pipeline_run_id: str | None = None, limit: int = 2000) -> str:
    """
    [PAPERS INSPECTION]
    List fetched papers, metadata, PDF/Markdown paths, and independent screening evaluations for a workspace or pipeline run.

    RETURNS:
    - JSON list of papers with:
      • paper_id, workspace_id, pipeline_run
      • title, authors, abstract, doi, arxiv_id, source_database
      • source_url: Canonical public web URL to article landing page or repository
      • pdf_url, original_pdf_path, converted_md_path
      • screening_status: Review decision ('abstract_passed', 'full_text_passed', 'accepted', 'rejected', 'withdrawn', 'pending')
      • abstract_screening_reasoning: LLM justification from Stage 1 Abstract Screening
      • full_text_screening_reasoning: LLM justification from Stage 2 Full-Text Screening
      • is_evaluation_benchmark: Boolean flag if paper is marked as ground-truth benchmark
      • evaluation_label: Benchmark evaluation ('passed' | 'rejected' | null)
      • signal_score: Evaluated composite signal score (float)
      • signal_score_details: Audit dictionary showing individual metric variables and formula weights
      • metrics_data: Extracted parameter dictionaries from screening and extraction stages
      • created_at: Ingestion timestamp
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
    exit_metrics: list[str] | None = None,
    primary_frontend_metric: str | None = None,
    secondary_frontend_metrics: list[str] | None = None,
    postprocessing_code: str | None = None,
    llm_model: str = "google/gemini-3.8-flash",
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
    - exit_metrics: List of field keys (e.g. ['rigour_score', 'param1', 'param2']) to unpack from extracted JSON for Signal Score.
    - primary_frontend_metric: Optional explicit headline field key displayed on the frontend dimension badge (e.g. 'fit_score' or 'trl_level').
    - secondary_frontend_metrics: Optional explicit list of sub-metric field keys displayed with progress bars and insight prose on frontend (e.g. ['novelty', 'significance']).
    - postprocessing_code: Optional Python snippet executed in a secure AST sandbox with full access to `data`, `response`, `json_response` and extracted fields. Computes an extra variable `<primary_metric>_postprocessed` for Signal Score.
    - llm_model: Default 'google/gemini-3.8-flash'.
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
        exit_metrics=exit_metrics,
        primary_frontend_metric=primary_frontend_metric,
        secondary_frontend_metrics=secondary_frontend_metrics,
        postprocessing_code=postprocessing_code,
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
    exit_metrics: list[str] | None = None,
    primary_frontend_metric: str | None = None,
    secondary_frontend_metrics: list[str] | None = None,
    postprocessing_code: str | None = None,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    response_schema: dict | None = None,
    llm_model: str | None = None,
    version: int | None = None,
    requires_consensus: bool | None = None,
    is_active: bool | None = None
) -> str:
    """
    [PARAMETER DEFINITION UPDATE]
    Update an existing extraction definition's schema, prompts, exit metrics list, primary/secondary frontend metrics, postprocessing code, or LLM configuration.
    
    PARAMETERS:
    - definition_id: UUID of the extraction definition.
    - exit_metrics: List of exit parameter keys (e.g. ['rigour_score', 'param1']) to expose for Signal Score.
    - primary_frontend_metric: Optional explicit headline field key displayed on the frontend dimension badge (e.g. 'fit_score').
    - secondary_frontend_metrics: Optional explicit list of sub-metric field keys displayed on frontend (e.g. ['novelty', 'significance']).
    - postprocessing_code: Python snippet executed in secure AST sandbox. Set empty string to clear.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:write")
    except Exception as e:
        return str(e)
    return update_extraction_definition_logic(
        user=user,
        definition_id=definition_id,
        name=name,
        exit_metrics=exit_metrics,
        primary_frontend_metric=primary_frontend_metric,
        secondary_frontend_metrics=secondary_frontend_metrics,
        postprocessing_code=postprocessing_code,
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
def set_extraction_frontend_metrics(
    definition_id: str,
    primary_frontend_metric: str | None = None,
    secondary_frontend_metrics: list[str] | None = None,
) -> str:
    """
    [FRONTEND DISPLAY METRICS]
    Explicitly configure which extracted parameters are displayed as the primary headline badge and secondary sub-metrics on the frontend scorecard.
    
    WHEN TO USE:
    - Use when you want to define or reconfigure which field key appears on the frontend dimension headline badge
      and which field keys appear as secondary sub-measures (with progress bars, band badges, insights, and quotes)
      without needing to re-send the full schema, prompts, or postprocessing code.
      
    PARAMETERS:
    - definition_id: UUID of the target extraction definition.
    - primary_frontend_metric: Optional field key for the headline dimension badge (e.g. 'fit_score', 'trl_level').
    - secondary_frontend_metrics: Optional list of field keys for sub-metrics (e.g. ['novelty', 'significance']).
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "prompts:write")
    except Exception as e:
        return str(e)
    return set_extraction_frontend_metrics_logic(
        user=user,
        definition_id=definition_id,
        primary_frontend_metric=primary_frontend_metric,
        secondary_frontend_metrics=secondary_frontend_metrics,
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
    reprocess_existing: bool = None,
    query_prefix: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    n_last_days: int | None = None
) -> str:
    """
    [MANUAL COMPONENT ONLY] Trigger Search & Academic Metadata Ingestion for a workspace.
    
    DATE FILTERING OPTIONS (CHOOSE ONE MODE):
    You can filter scraped papers by publication date using EITHER relative days OR explicit dates:
    - MODE 1: Relative Lookback Days (Default)
      Pass `n_last_days` (e.g. 7, 14, 30). Ingests literature published from `now() - N days` to `now()`.
      Defaults to 7 days if neither start_date nor end_date is specified.
    - MODE 2: Explicit Date Range
      Pass `start_date` ('YYYY-MM-DD') and/or `end_date` ('YYYY-MM-DD').
      * Both provided: Ingests literature published within [start_date TO end_date].
      * Only start_date provided: Ingests from start_date to now().
      * Only end_date provided: Ingests from (end_date - n_last_days) to end_date.
    
    PARAMETERS:
    - workspace_id: Target workspace UUID (required).
    - scraper_id: Optional UUID of a specific scraper (if omitted, triggers all active scrapers in workspace).
    - limit: Max papers to ingest per scraper (default: None = all available).
    - start_date: ISO format start date (e.g. '2026-08-01' or '2026-08-01T00:00:00Z'). Used in explicit date mode.
    - end_date: ISO format end date (e.g. '2026-08-31' or '2026-08-31T23:59:59Z'). Used in explicit date mode.
    - n_last_days: Relative past days window (e.g. 7, 14, 30). Used in relative mode (default: 7).
    - query_prefix: Optional keyword prepended to active scraper queries.
    - reprocess_existing: If True, forces re-screening of existing papers. If None, inherits workspace default policy.
    
    NOTE: To run the full end-to-end pipeline automatically, use `start_research_agent` instead.
    """

    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_search_job_logic(
        user,
        workspace_id=workspace_id,
        scraper_id=scraper_id,
        limit=limit,
        reprocess_existing=reprocess_existing,
        query_prefix=query_prefix,
        start_date=start_date,
        end_date=end_date,
        n_last_days=n_last_days
    )


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
    """
    [MANUAL COMPONENT ONLY] Trigger Abstract or Full-Text Screening.
    
    PARAMETERS:
    - pipeline_run_id: Target PipelineRun UUID
    - workspace_id: Target Workspace UUID (if pipeline_run_id omitted, uses latest run)
    - stage: Screening stage to execute:
      • 'abstract' (default): Evaluates paper title & abstract against abstract criteria.
        Sets screening_status to 'abstract_passed' or 'rejected'.
        Writes justification strictly to `abstract_screening_reasoning`.
      • 'full_text': Evaluates OCR markdown or multimodal PDF against full-text criteria.
        Sets screening_status to 'full_text_passed' or 'rejected'.
        Writes justification strictly to `full_text_screening_reasoning`.
    - limit: Maximum number of candidate papers to screen (default None = all candidates).
    
    Note: To run the full end-to-end pipeline automatically, use start_research_agent instead.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return trigger_screening_job_logic(user, pipeline_run_id, workspace_id, limit, stage=stage)


@mcp.tool()
@with_db_connection
def trigger_extraction_job(pipeline_run_id: str = None, workspace_id: str = None, limit: int = None) -> str:
    """[MANUAL COMPONENT ONLY] Trigger Parameter Extraction against accepted papers. Note: To run the full end-to-end pipeline automatically, use start_research_agent instead."""
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
    - Aggregated list of papers with:
      • paper_id, title, authors, doi, arxiv_id, pdf_url, original_pdf_path, converted_md_path, abstract
      • screening_status: Stage decision ('abstract_passed', 'full_text_passed', 'accepted', 'rejected')
      • abstract_screening_reasoning: LLM justification from Stage 1 Abstract Screening
      • full_text_screening_reasoning: LLM justification from Stage 2 Full-Text Screening
      • is_evaluation_benchmark: Benchmark evaluation flag (bool)
      • evaluation_label: Benchmark ground-truth label ('passed' | 'rejected' | null)
      • signal_score: Evaluated composite score (float)
      • signal_score_details: Mathematical formula inputs and metric breakdown
      • metrics_summary: Quick key-value dictionary of primary exit metrics (e.g. fit_score, trl_level)
      • extractions: Full array of dynamic parameter extractions with quotes, confidence, and HITL flags
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_paper_extractions_matrix_logic(user, workspace_id, pipeline_run_id, process_id, screening_status, limit)


@mcp.tool()
@with_db_connection
def paper_scoreboard(
    paper_id: str,
    pipeline_run_id: str | None = None,
) -> str:
    """
    [PAPER SCOREBOARD & METRICS SCORECARD]
    Retrieve the complete, dynamic scorecard and scoreboard payload for a single paper,
    matching the GET /api/papers/{id}/scorecard/ frontend aggregate contract.

    WHEN TO USE:
    - Inspect a paper's full scoreboard, primary & secondary metrics (including unpacked exit metrics),
      unflattened fields_data, JSON response schemas, stage reasonings, composite signal score,
      and executive narrative report before or independently of the frontend UI.

    PARAMETERS:
    - paper_id: UUID of the paper to inspect (required).
    - pipeline_run_id: Optional UUID of a specific pipeline run, or 'latest'.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_paper_scoreboard_logic(user, paper_id, pipeline_run_id)


@mcp.tool()
@with_db_connection
def get_paper_scoreboard(
    paper_id: str,
    pipeline_run_id: str | None = None,
) -> str:
    """
    [ALIAS]
    Alias for `paper_scoreboard`. Retrieves the complete dynamic scorecard for a paper.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return get_paper_scoreboard_logic(user, paper_id, pipeline_run_id)


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
    Retrieve execution state, active component step, paper count metrics, storage footprint, and result previews for a PipelineRun.

    CRITICAL AI DIRECTIVE:
    - Inspect `active_progress`:
      * `is_progressing: true`: DO NOT MODIFY SOURCE CODE. Background workers are actively running. Inform the user of current items completed, percentage, and elapsed time.
      * `is_stalled: true`: DO NOT MODIFY SOURCE CODE. Inform the user that the worker has shown no progress for `stalled_minutes` and may need worker restart.

    RETURNS:
    - active_progress: Real-time progress block with `is_progressing`, `is_stalled`, `progress_summary`, `percent_complete`, `latest_processed_item`, and `guidance_for_ai`
    - Execution state: status ('pending', 'running', 'completed', 'failed', 'paused', 'aborted'), current_stage, token usage, cost
    - Component runs breakdown: status and runtime of search, download, ocr, screening, extraction, scoring, reporting
    - fetched_papers_preview: List of papers with status, abstract_screening_reasoning, full_text_screening_reasoning, signal_score, and benchmark flags
    - extractions_matrix_preview: Quick scorecard table of top-scored papers and their extracted exit metrics
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
def rerun_pipeline_from_step(pipeline_run_id: str, step_name: str | None = None) -> str:
    """
    [RERUN / RESUME PIPELINE FROM STEP - RESILIENCE TOOL]
    Rerun a PipelineRun from a specific step forward, or automatically resume from the step that failed/aborted.
    
    Resets the target step and all downstream dependent steps in the DAG, sets the pipeline run
    status back to 'running', and immediately dispatches the step task(s) to Celery workers.
    
    Idempotent: Already downloaded PDFs, converted OCR files, and screened papers are preserved and skipped!
    
    Args:
        pipeline_run_id: UUID of the PipelineRun to rerun/resume.
        step_name: Step to restart from: 'search', 'download', 'ocr', 'abstract_screening',
                   'full_text_screening', 'extraction', 'signal_score', 'reporting'.
                   If omitted (None) or set to 'auto' / 'failed', automatically detects the stage
                   where the run halted or failed.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return rerun_pipeline_from_step_logic(user, pipeline_run_id, step_name)


@mcp.tool()
@with_db_connection
def reexecute_component_run(component_run_id: str) -> str:
    """
    [RE-EXECUTE SINGLE COMPONENT TASK]
    Re-dispatches an isolated single ComponentRun task to Celery workers without resetting downstream steps.
    Ideal for quickly retrying a single failed or stalled component (e.g., a specific download or OCR task)
    while keeping the rest of the pipeline DAG untouched.
    
    Args:
        component_run_id: UUID of the ComponentRun to re-execute.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return reexecute_component_run_logic(user, component_run_id)


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
def start_pipeline_run(
    workspace_id: str,
    name: str | None = None,
    limit: int | None = None,
    query_prefix: str | None = None,
    skip_abstract_screening: bool | None = None,
    notification_email: str | None = None,
    reprocess_existing: bool | None = None,
    autonomous: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
    n_last_days: int | None = None
) -> str:
    """
    [AUTONOMOUS PIPELINE EXECUTION - RECOMMENDED]
    Launch an autonomous end-to-end PipelineRun for a workspace.
    Executes the full SLR state machine (Search -> Screening -> Download -> OCR -> Extraction -> Signal Score -> Reporting).
    
    DATE FILTERING OPTIONS (CHOOSE ONE MODE):
    You can filter scraped papers by publication date using EITHER relative days OR explicit dates:
    - MODE 1: Relative Lookback Days (Default)
      Pass `n_last_days` (e.g. 7, 14, 30). Ingests literature published from `now() - N days` to `now()`.
      Defaults to 7 days if neither start_date nor end_date is specified.
    - MODE 2: Explicit Date Range
      Pass `start_date` ('YYYY-MM-DD') and/or `end_date` ('YYYY-MM-DD').
      * Both provided: Ingests literature published within [start_date TO end_date].
      * Only start_date provided: Ingests from start_date to now().
      * Only end_date provided: Ingests from (end_date - n_last_days) to end_date.
    
    PARAMETERS:
    - workspace_id: Target workspace UUID (required).
    - name: Optional descriptive name for the pipeline run.
    - limit: Optional max papers limit across scrapers (e.g. 50, 100).
    - start_date: ISO start date string (e.g. '2026-08-01' or '2026-08-01T00:00:00Z'). Used in explicit date mode.
    - end_date: ISO end date string (e.g. '2026-08-31' or '2026-08-31T23:59:59Z'). Used in explicit date mode.
    - n_last_days: Relative past days window (e.g. 7, 14, 30). Used in relative mode or when start_date is omitted (default: 7).
    - query_prefix: Optional keyword prepended to active scraper queries.
    - skip_abstract_screening: If True, skips Abstract Screening and routes candidate papers directly to Full-Text Screening.
    - notification_email: Optional single-run email override to receive Mailgun completion report.
    - reprocess_existing: If True, forces re-screening of existing papers even if no new papers are found.
    - autonomous: If True (default), automatically advances stages upon completion.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return start_pipeline_run_logic(
        user,
        workspace_id=workspace_id,
        name=name,
        limit=limit,
        query_prefix=query_prefix,
        skip_abstract_screening=skip_abstract_screening,
        notification_email=notification_email,
        reprocess_existing=reprocess_existing,
        autonomous=autonomous,
        start_date=start_date,
        end_date=end_date,
        n_last_days=n_last_days
    )


@mcp.tool()
@with_db_connection
def pause_pipeline_run(pipeline_run_id: str, reason: str = "Paused via MCP") -> str:
    """
    Pause an active PipelineRun without losing execution state.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return pause_pipeline_run_logic(user, pipeline_run_id=pipeline_run_id, reason=reason)


@mcp.tool()
@with_db_connection
def resume_pipeline_run(pipeline_run_id: str) -> str:
    """
    Resume a paused PipelineRun and continue autonomous DAG state transitions.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return resume_pipeline_run_logic(user, pipeline_run_id=pipeline_run_id)


@mcp.tool()
@with_db_connection
def tick_pipeline_run(pipeline_run_id: str) -> str:
    """
    Execute a single state transition tick for a PipelineRun.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "runs:write")
    except Exception as e:
        return str(e)
    return tick_pipeline_run_logic(user, pipeline_run_id=pipeline_run_id)



@mcp.tool()
@with_db_connection
def start_research_agent(
    workspace_id: str,
    name: str = None,
    limit: int = None,
    start_date: str = None,
    end_date: str = None,
    n_last_days: int = None,
    query_prefix: str = None,
    skip_abstract_screening: bool = None,
    notification_email: str = None,
    reprocess_existing: bool = None
) -> str:
    """
    [PRIMARY SLR ORCHESTRATOR - RECOMMENDED ENTRYPOINT]
    Launch an autonomous state engine process (ResearchAgentProcess) executing the complete end-to-end SLR pipeline:
    Search & Ingestion -> Download PDFs -> OCR (auto-skipped if None) -> Dual-Stage Screening (Abstract + Full-Text via Gemini 3.8) -> Dynamic Parameter Extraction -> Composite Signal Scoring -> Executive Narrative.
    
    WHEN TO USE:
    - Primary entrypoint to run a systematic review. Do not trigger individual manual steps unless debugging.
    
    DATE FILTERING OPTIONS (CHOOSE ONE MODE):
    You can filter harvested literature by publication date using EITHER relative days OR explicit dates:
    - MODE 1: Relative Lookback Days (Default)
      Pass `n_last_days` (e.g. 7, 14, 30). Searches literature published from `now() - N days` to `now()`.
      Defaults to 7 days (or the scraper's configured default) if neither start_date nor end_date is specified.
    - MODE 2: Explicit Date Range
      Pass `start_date` ('YYYY-MM-DD') and/or `end_date` ('YYYY-MM-DD').
      * Both provided: Ingests literature published within [start_date TO end_date].
      * Only start_date provided: Ingests from start_date to now().
      * Only end_date provided: Ingests from (end_date - n_last_days) to end_date.
    
    KEY PARAMETERS:
    - workspace_id: The target workspace UUID (required).
    - name: Optional human-readable name for the research process.
    - limit: Optional maximum number of papers to ingest and process across all steps (default: None = all papers found by scrapers).
    - start_date: ISO start date string (e.g. '2026-08-01' or '2026-08-01T00:00:00Z'). Used in explicit date mode.
    - end_date: ISO end date string (e.g. '2026-08-31' or '2026-08-31T23:59:59Z'). Used in explicit date mode.
    - n_last_days: Relative past days lookback window (e.g. 7, 14, 30). Used in relative mode (default: 7).
    - query_prefix: Optional query modifier prepended to workspace scrapers.
    - reprocess_existing: Reprocessing policy override. When None (default), inherits the workspace-level default policy (`workspace.reprocess_existing`). Set explicitly to True to re-screen and re-extract all existing workspace papers even if no new papers were found; set False to only process newly scraped papers.
    - notification_email: Optional single-run email override to receive Mailgun completion report (default: sends to all active workspace Subscribers).
    - skip_abstract_screening: If True, skips Abstract Screening and routes all candidate papers directly to Full-Text Screening (default: inherits `workspace.skip_abstract_screening`).
    
    NEXT STEPS:
    - Immediately after calling this, call `check_run_status(process_id=...)` to check real-time progress without blocking, or query `get_paper_extractions_matrix(process_id=...)` once complete.
    """

    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:write")
    except Exception as e:
        return str(e)
    return start_research_agent_logic(
        user=user,
        workspace_id=workspace_id,
        name=name,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        n_last_days=n_last_days,
        query_prefix=query_prefix,
        skip_abstract_screening=skip_abstract_screening,
        notification_email=notification_email,
        reprocess_existing=reprocess_existing
    )


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
    - `active_progress`: Real-time progress block containing `is_progressing`, `is_stalled`, `progress_summary`, `latest_processed_item`, and `guidance_for_ai`.
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

    CRITICAL AI DIRECTIVE:
    - If `active_progress.is_progressing` is True: DO NOT MODIFY CODE. Background workers are actively running. Inform the user of current items completed and percentage.
    - If `active_progress.is_stalled` is True: DO NOT MODIFY CODE. Inform the user that the worker has had no progress for X minutes and may need restart/checking.
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

        if secret_list:
            logger.warning(
                "SECURITY ADVISORY: API secret was provided via URL query parameter '?api_secret=...'. "
                "Secrets in query parameters can be logged by web servers and proxies. "
                "Please migrate to passing credentials via HTTP header 'x-api-secret' or 'Authorization: Bearer <key_id>:<secret>'."
            )

        if not key_id and auth_header.startswith("Bearer "):
            token_parts = auth_header[7:].split(":")
            if len(token_parts) == 2:
                key_id, secret = token_parts[0], token_parts[1]

        # 1. Check if auth is cached for this SSE session_id
        if session_id and not (key_id and secret):
            cached_auth = SESSION_AUTH_CACHE.get(session_id)
            if cached_auth:
                user, workspace, api_key = cached_auth
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
                SESSION_AUTH_CACHE.set(session_id, user_obj, ws_obj, api_key_obj)

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
    Test connectivity to Google Cloud GenAI / Vertex AI models (e.g. gemini-3.8-flash) and verify current API credentials.
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
    Asks the workspace's configured LLM a question about one ingested paper, grounded in that
    paper's full text and the platform's annotations on it. Use it to examine what a paper
    reports, check its methodology or numbers, or find out why the review pipeline accepted,
    rejected or scored it the way it did. Get the paper's UUID from `list_papers(workspace_id)`.

    The model sees, in this order: the paper's metadata and full text (OCR markdown, or the PDF
    itself when no markdown exists); the latest screening status with its rationale; the extracted
    parameters with confidence scores; the composite signal score, its computation details and the
    workspace's scoring formula; and earlier turns of the session. Answers may contain inline
    markers `[Page X, Fig Y, quote: "..."]` (`Page X` and `box_2d` only when the PDF itself was
    attached; OCR markdown has no page numbers, so there the marker is `[Fig Y, quote: "..."]`);
    these are parsed into `visual_citations`, and quoted text is checked against the document.
    `hallucination_guard` reports how many quotes matched.

    Without `paper_id` the model only gets the workspace name, description, and the titles and
    signal scores of its top ten accepted papers - not their text - so use that mode for
    orientation, not for cross-paper synthesis of content.

    Multi-turn: the first call returns a `session_id`; pass it back to continue the same
    conversation with its history. The paper is sent as a stable prefix so the provider's
    implicit prompt cache can reuse it across turns.

    Parameters:
    - workspace_id: workspace UUID; the API key needs the `workspaces:read` scope and the
      caller admin, manager or researcher membership.
    - question: the question or instruction, in the language the answer should be in.
    - paper_id: paper UUID to ask about (optional, see above).
    - session_id: existing session UUID to continue (optional).
    - deep_thinking: raises the model's thinking budget to "high" (the workspace's
      `reasoning_effort` applies otherwise), returns its thought trace in `thinking_process`,
      and asks it to verify numerical claims against the document. Slower and costs more
      output tokens.

    Returns a JSON string. On success: `{ "status": "completed", "session_id", "message_id",
    "paper_id", "paper_title", "answer", "thinking_process", "citations", "visual_citations",
    "hallucination_guard", "deep_thinking", "llm_model", "tokens_in", "tokens_out",
    "tokens_cached", "total_tokens", "usd_cost", "session_total_tokens",
    "session_total_usd_cost", "workspace_monthly_tokens", "workspace_monthly_usd" }`.
    On a bad request (missing arguments, no access, unknown paper or session):
    `{ "status": "error", "error": "..." }`. When generation itself fails or the workspace
    quota is exhausted: `{ "status": "failed", "message_id", "session_id", "error" }`.
    An authentication or scope failure returns the error message as a plain string.
    """
    try:
        user, workspace, api_key = get_auth_context()
        check_scope(api_key, "workspaces:read")
    except Exception as e:
        return str(e)
    return ask_paper_logic(user, workspace_id, question, paper_id=paper_id, session_id=session_id, deep_thinking=deep_thinking)


# ---------------------------------------------------------------------------
# 11. User Management Tools (Staff & Superuser Only)
# ---------------------------------------------------------------------------

@mcp.tool()
@with_db_connection
def list_users(
    search: str = None,
    is_active: bool = None,
    is_staff: bool = None,
    is_superuser: bool = None,
    limit: int = 50
) -> str:
    """
    List Django user accounts with optional filtering by search query (username, email, name), active status, or staff/superuser roles.
    Requires staff member or superuser privileges in Django.
    """
    user, workspace, api_key = get_auth_context()
    return list_users_logic(user, search=search, is_active=is_active, is_staff=is_staff, is_superuser=is_superuser, limit=limit)


@mcp.tool()
@with_db_connection
def get_user(
    user_id_or_username: str
) -> str:
    """
    Retrieve profile and workspace memberships for a specified user by numeric ID or username.
    Staff members and superusers can view any user profile.
    Regular (non-staff) users can only view their own profile.
    """
    user, workspace, api_key = get_auth_context()
    return get_user_logic(user, user_id_or_username=user_id_or_username)


@mcp.tool()
@with_db_connection
def create_user(
    username: str,
    password: str,
    email: str = "",
    first_name: str = "",
    last_name: str = "",
    is_staff: bool = False,
    is_superuser: bool = False,
    is_active: bool = True
) -> str:
    """
    Create a new Django user account with an encrypted password and role flags.
    Requires staff member or superuser privileges in Django. Regular users cannot manage or create users.
    Non-superusers cannot create superuser accounts.
    """
    user, workspace, api_key = get_auth_context()
    return create_user_logic(
        user=user,
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_staff=is_staff,
        is_superuser=is_superuser,
        is_active=is_active
    )


@mcp.tool()
@with_db_connection
def update_user(
    user_id_or_username: str,
    email: str = None,
    first_name: str = None,
    last_name: str = None,
    password: str = None,
    is_staff: bool = None,
    is_superuser: bool = None,
    is_active: bool = None
) -> str:
    """
    Update attributes, password, or administrative flags for a user account.
    PERMISSIONS:
    - Superusers and staff members can manage users.
    - Regular users (non-staff, non-superuser) CANNOT manage other users. They can at most update their OWN password, first_name, and last_name.
    - Protected user 'admin' cannot be deactivated or have administrative access revoked.
    - Staff members cannot modify superusers or grant superuser privileges.
    """
    user, workspace, api_key = get_auth_context()
    return update_user_logic(
        user=user,
        user_id_or_username=user_id_or_username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
        is_staff=is_staff,
        is_superuser=is_superuser,
        is_active=is_active
    )


@mcp.tool()
@with_db_connection
def delete_user(
    user_id_or_username: str
) -> str:
    """
    Delete a user account from Django.
    CRITICAL SAFETY RULES:
    - User 'admin' CANNOT be deleted via MCP.
    - An authenticated user cannot delete their own active account via MCP.
    - Staff members cannot delete superuser accounts.
    Requires staff member or superuser privileges in Django.
    """
    user, workspace, api_key = get_auth_context()
    return delete_user_logic(user=user, user_id_or_username=user_id_or_username)


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

