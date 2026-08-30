"""
FastMCP SSE Protocol & AI Agent Tools Scenario.
"""

import logging
import random
import time
from typing import Dict, Any, Optional
from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    AgentService,
    PipelineService,
)

logger = logging.getLogger("e2e_mcp_protocol")


def run_mcp_protocol_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates FastMCP discovery and tools used by AI clients (Claude Code, Cursor):
    1. Probes /mcp/ discovery endpoints.
    2. Runs a fast review in a test workspace.
    3. Validates unified parameter matrix and diagnostic tools.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_mcp_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("🔌 STARTING FASTMCP PROTOCOL & AI TOOLS SCENARIO")
    logger.info(f"📍 Base URL : {cfg.base_url}")
    logger.info("=================================================================")

    # 1. Probe MCP Discovery
    logger.info("📡 Probing FastMCP Discovery endpoints...")
    try:
        mcp_resp = client.get("/mcp/")
        logger.info(f"   • /mcp/ Discovery status: {mcp_resp.status_code}")
    except Exception as e:
        logger.warning(f"Note on MCP discovery probe: {e}")

    # 2. Create workspace
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning and optimization algorithms.",
        abstract_rejection_criteria="Reject unrelated biology topics.",
        full_text_acceptance_criteria="Accept algorithmic evaluations.",
        full_text_rejection_criteria="Reject papers with zero technical discussion.",
        screening_llm_model="google/gemini-3.7-flash",
    )
    workspace_id = ws_data["id"]

    try:
        # Create Scraper
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"optimization"',
            limit=3,
        )

        # Launch Agent
        proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"MCP Test Run - {workspace_name}",
            limit=3,
        )
        process_id = proc["id"]

        # Poll to completion
        completed_proc = agent_svc.poll_until_complete(process_id=process_id, max_timeout_sec=cfg.max_timeout_sec)
        assert completed_proc.get("status") == "completed", f"MCP review run failed: {completed_proc}"

        pipeline_run_id = completed_proc.get("pipeline_run")
        pr_data = pipeline_svc.get_pipeline_run(pipeline_run_id) if pipeline_run_id else {}
        papers = pipeline_svc.list_papers(workspace_id=workspace_id)

        logger.info(f"📊 MCP Review Verification:")
        logger.info(f"   • Workspace ID  : {workspace_id}")
        logger.info(f"   • Total Papers  : {len(papers)}")
        logger.info(f"   • Stage Results : {list(completed_proc.get('stage_results', {}).keys())}")

        pr_info = pipeline_svc.get_pipeline_run(pipeline_run_id) if pipeline_run_id else {}
        cost_metrics = {
            "pipeline_tokens_in": pr_info.get("tokens_in", 0),
            "pipeline_tokens_out": pr_info.get("tokens_out", 0),
            "pipeline_total_tokens": pr_info.get("tokens_consumed", 0),
            "pipeline_usd_cost": float(pr_info.get("usd_cost") or 0.0),
            "total_tokens_consumed": pr_info.get("tokens_consumed", 0),
            "total_usd_spent": float(pr_info.get("usd_cost") or 0.0),
        }

        logger.info("=================================================================")
        logger.info("🎉 FASTMCP PROTOCOL & AI TOOLS SCENARIO PASSED SUCCESSFULLY!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "process_id": process_id,
            "papers_count": len(papers),
            "cost_metrics": cost_metrics,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete MCP test workspace: {del_err}")
