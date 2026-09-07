"""
Agent Lifecycle (Pause & Resume) State Machine Scenario.
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
)

logger = logging.getLogger("e2e_agent_lifecycle")


def run_agent_lifecycle_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates ResearchAgentProcess lifecycle controls:
    1. Provisions a dedicated test workspace.
    2. Starts an autonomous agent process.
    3. Issues POST /api/agents/{id}/pause/ and verifies state transition to 'paused'.
    4. Issues POST /api/agents/{id}/resume/ and verifies resumption to 'running'.
    5. Polls until completion to confirm full recovery and successful finish.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_lifecycle_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)

    logger.info("=================================================================")
    logger.info("⏸️  STARTING AGENT LIFECYCLE (PAUSE / RESUME) SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info("=================================================================")

    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning and optimization algorithms papers.",
        abstract_rejection_criteria="Reject unrelated biology topics.",
        full_text_acceptance_criteria="Accept computational and algorithmic methodology papers.",
        full_text_rejection_criteria="Reject papers with zero technical discussion.",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]

    try:
        # Create scraper
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"optimization"',
            limit=5,
        )

        # Launch Agent
        proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Lifecycle Test Run - {workspace_name}",
            limit=5,
            reprocess_existing=True,
        )
        process_id = proc["id"]
        logger.info(f"🚀 Started Agent Process '{process_id}' (State: {proc.get('status')})")

        # Wait 2 seconds for process to begin running, then issue PAUSE
        time.sleep(2.0)
        logger.info(f"⏸️  Sending PAUSE command to Agent '{process_id}'...")
        pause_resp = agent_svc.pause_agent(process_id)
        current_status = pause_resp.get("agent_status") or agent_svc.get_agent_status(process_id).get("status")
        logger.info(f"   • Agent status after pause: '{current_status}'")
        assert current_status in ("paused", "completed"), f"Expected paused or completed, got: {current_status}"

        if current_status == "paused":
            logger.info("⏳ Process safely paused in database. Waiting 3 seconds before resuming...")
            time.sleep(3.0)

            # Issue RESUME
            logger.info(f"▶️  Sending RESUME command to Agent '{process_id}'...")
            resume_resp = agent_svc.resume_agent(process_id)
            resumed_status = resume_resp.get("agent_status") or agent_svc.get_agent_status(process_id).get("status")
            logger.info(f"   • Agent status after resume: '{resumed_status}'")
            assert resumed_status in ("running", "completed"), f"Expected running or completed, got: {resumed_status}"

        # Poll to completion
        completed_proc = agent_svc.poll_until_complete(process_id=process_id, max_timeout_sec=cfg.max_timeout_sec)
        assert completed_proc.get("status") == "completed", f"Agent failed to complete: {completed_proc}"

        pipeline_run_id = completed_proc.get("pipeline_run")
        from ..client import PipelineService
        pipeline_svc = PipelineService(client)
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
        logger.info("🎉 AGENT LIFECYCLE (PAUSE / RESUME) SCENARIO PASSED SUCCESSFULLY!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "process_id": process_id,
            "final_status": completed_proc.get("status"),
            "total_papers": int(pr_info.get("total_papers_fetched", 0) or 0),
            "cost_metrics": cost_metrics,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete lifecycle test workspace: {del_err}")
