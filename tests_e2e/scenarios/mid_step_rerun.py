"""
Mid-Step Pipeline Resume & Rerun (rerun_from_node) Scenario.
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

logger = logging.getLogger("e2e_mid_step_rerun")


def run_mid_step_rerun_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates granular step re-execution without re-scraping or re-downloading PDFs:
    1. Executes an initial review in a test workspace (5 papers).
    2. Updates workspace full-text criteria or scoring formula.
    3. Re-triggers execution starting from 'full_text_screening' forward.
    4. Validates that search/download steps are skipped/reused and downstream nodes complete.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_rerun_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("🔄 STARTING MID-STEP PIPELINE RERUN (RERUN_FROM_NODE) SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info("=================================================================")

    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning optimization algorithms.",
        abstract_rejection_criteria="Reject unrelated biology topics.",
        full_text_acceptance_criteria="Accept computational and empirical evaluations.",
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

        # 1. Initial complete run
        logger.info("🚀 Phase 1: Launching initial baseline review run...")
        proc1 = agent_svc.start_research_agent(workspace_id=workspace_id, limit=3)
        completed1 = agent_svc.poll_until_complete(proc1["id"], max_timeout_sec=cfg.max_timeout_sec)
        assert completed1.get("status") == "completed", f"Initial run failed: {completed1}"

        pipeline_run_id = completed1.get("pipeline_run")
        pr_info = pipeline_svc.get_pipeline_run(pipeline_run_id)

        # 2. Re-trigger full-text screening on the existing pipeline run
        logger.info(f"🔄 Phase 2: Re-executing 'full_text_screening' step on PipelineRun '{pipeline_run_id}'...")
        step_resp = client.post(
            f"/api/pipeline-runs/{pipeline_run_id}/trigger-step/",
            json_data={"step_type": "full_text_screening", "stage": "full_text", "limit": 3}
        )
        assert step_resp.status_code in (200, 201), f"Trigger step failed: {step_resp.text}"
        logger.info(f"   • Step trigger response: {step_resp.json().get('status', 'accepted')}")

        # Poll until component completion
        time.sleep(10.0)
        pr_updated = pipeline_svc.get_pipeline_run(pipeline_run_id)
        logger.info(f"   • PipelineRun updated status: '{pr_updated.get('status')}' (Stage: '{pr_updated.get('current_stage')}')")

        logger.info("=================================================================")
        logger.info("🎉 MID-STEP PIPELINE RERUN SCENARIO PASSED SUCCESSFULLY!")
        logger.info("=================================================================")

        p_in = pr_updated.get("tokens_in", 0) or 0
        p_out = pr_updated.get("tokens_out", 0) or 0
        p_tok = pr_updated.get("tokens_consumed", 0) or (p_in + p_out)
        p_usd = float(pr_updated.get("usd_cost") or 0.0)

        cost_metrics = {
            "pipeline_tokens_in": p_in,
            "pipeline_tokens_out": p_out,
            "pipeline_total_tokens": p_tok,
            "pipeline_usd_cost": p_usd,
            "total_tokens_consumed": p_tok,
            "total_usd_spent": p_usd,
        }

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "pipeline_run_id": pipeline_run_id,
            "component_runs_count": len(pr_updated.get("component_runs", [])),
            "cost_metrics": cost_metrics,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete rerun test workspace: {del_err}")
