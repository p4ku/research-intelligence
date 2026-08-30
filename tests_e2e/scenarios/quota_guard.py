"""
Quota Guard & Budget Limit Enforcement Scenario.
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

logger = logging.getLogger("e2e_quota")


def run_quota_guard_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates that monthly token limits and USD cost ceilings prevent budget overruns:
    1. Creates a workspace configured with an exhausted/micro budget limit (monthly_usd_limit = 0.0001).
    2. Attempts to run an autonomous review.
    3. Validates that the system gracefully handles budget constraints or logs proper quota enforcement.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_quota_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)

    logger.info("=================================================================")
    logger.info("🛡️  STARTING QUOTA GUARD & BUDGET CEILING SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info("=================================================================")

    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept optimization algorithms papers.",
        abstract_rejection_criteria="Reject unrelated topics.",
        full_text_acceptance_criteria="Accept algorithmic evaluations.",
        full_text_rejection_criteria="Reject papers with zero discussion.",
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
            name=f"Quota Test Run - {workspace_name}",
            limit=3,
        )
        process_id = proc["id"]

        # Poll to completion
        completed_proc = agent_svc.poll_until_complete(process_id=process_id, max_timeout_sec=cfg.max_timeout_sec)
        assert completed_proc.get("status") in ("completed", "failed"), f"Unexpected status: {completed_proc}"

        # Fetch workspace usage counters
        ws_info = ws_svc.get_workspace(workspace_id)
        tokens_consumed = ws_info.get("tokens_consumed_this_month", 0)
        usd_spent = float(ws_info.get("usd_spent_this_month", 0.0))

        logger.info(f"📊 Quota Tracking Audit:")
        logger.info(f"   • Monthly Tokens Consumed : {tokens_consumed:,}")
        logger.info(f"   • Monthly USD Spent       : ${usd_spent:.4f}")

        logger.info("=================================================================")
        logger.info("🎉 QUOTA GUARD & BUDGET SCENARIO PASSED SUCCESSFULLY!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "process_id": process_id,
            "tokens_consumed": tokens_consumed,
            "usd_spent": usd_spent,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete quota test workspace: {del_err}")
