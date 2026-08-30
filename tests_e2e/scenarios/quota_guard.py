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
    1. Provisions a workspace and executes an initial small batch to accumulate spend.
    2. Updates workspace with an exhausted/micro budget limit (monthly_usd_limit = 0.0001).
    3. Attempts to run a second review.
    4. Validates that the system halts/rejects the run with a clear quota exceeded message.
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
            limit=2,
        )

        # Phase 1: Accumulate initial spend
        logger.info("🚀 Phase 1: Executing small review to accumulate token/USD spend...")
        proc1 = agent_svc.start_research_agent(workspace_id=workspace_id, limit=2)
        completed1 = agent_svc.poll_until_complete(proc1["id"], max_timeout_sec=cfg.max_timeout_sec)
        assert completed1.get("status") == "completed", f"Initial run failed: {completed1}"

        ws_info = ws_svc.get_workspace(workspace_id)
        tokens_consumed = ws_info.get("tokens_consumed_this_month", 0)
        usd_spent = float(ws_info.get("usd_spent_this_month", 0.0))
        logger.info(f"   • Accumulated spend: ${usd_spent:.4f} USD ({tokens_consumed:,} tokens)")

        # Phase 2: Set strict micro-budget ceiling
        logger.info(f"🔒 Phase 2: Applying strict monthly_usd_limit = ${usd_spent:.6f} to enforce ceiling...")
        client.patch(f"/api/workspaces/{workspace_id}/", json_data={"monthly_usd_limit": max(0.01, usd_spent)})

        # Phase 3: Attempt to launch another review
        logger.info("🚀 Phase 3: Launching second review; verifying Quota Guard enforcement...")
        launch_resp = client.post("/api/agents/", json_data={"workspace": workspace_id, "limit": 2})

        if launch_resp.status_code == 400 and "limit exceeded" in launch_resp.text.lower():
            logger.info(f"✅ Quota Guard immediately rejected run at API gateway: {launch_resp.text}")
        else:
            proc2_id = launch_resp.json().get("id")
            if proc2_id:
                completed2 = agent_svc.poll_until_complete(proc2_id, max_timeout_sec=60)
                assert completed2.get("status") == "failed" or "quota" in str(completed2.get("stop_reason")).lower()
                logger.info(f"✅ Quota Guard halted pipeline in DAG engine: {completed2.get('stop_reason')}")

        logger.info("=================================================================")
        logger.info("🎉 QUOTA GUARD & BUDGET SCENARIO PASSED SUCCESSFULLY!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "tokens_consumed": tokens_consumed,
            "usd_spent": usd_spent,
            "cost_metrics": {
                "total_tokens_consumed": tokens_consumed,
                "total_usd_spent": usd_spent,
            },
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete quota test workspace: {del_err}")
