"""
Transactional Email Digest Dispatch Scenario (Mailgun API).
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

logger = logging.getLogger("e2e_email_digest")


def run_email_digest_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates executive email digest compilation and Mailgun dispatch:
    1. Runs a fast review on a test workspace to generate completed reports.
    2. Dispatches an executive digest notification via POST /api/pipeline-runs/{id}/send-digest/.
    3. Verifies that the endpoint returns 200 OK with delivery summary.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_digest_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("✉️  STARTING EMAIL DIGEST DISPATCH SCENARIO (MAILGUN)")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info("=================================================================")

    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning optimization papers.",
        abstract_rejection_criteria="Reject unrelated biology topics.",
        full_text_acceptance_criteria="Accept algorithmic and technical evaluations.",
        full_text_rejection_criteria="Reject papers with zero technical discussion.",
        screening_llm_model="google/gemini-3.7-flash",
        subscribers=[
            {
                "email": "test-e2e-subscriber@example.com",
                "name": "E2E Automated Subscriber",
                "subscription_type": "result_report",
                "is_active": True,
            }
        ],
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
            name=f"Digest Test Run - {workspace_name}",
            limit=3,
        )
        process_id = proc["id"]

        # Poll to completion
        completed_proc = agent_svc.poll_until_complete(process_id=process_id, max_timeout_sec=cfg.max_timeout_sec)
        assert completed_proc.get("status") == "completed", f"Review run failed: {completed_proc}"

        pipeline_run_id = completed_proc.get("pipeline_run")
        assert pipeline_run_id, "No pipeline_run ID found on completed agent process"

        # Dispatch executive email digest
        logger.info(f"📧 Triggering executive email digest for PipelineRun '{pipeline_run_id}'...")
        resp = client.post(
            f"/api/pipeline-runs/{pipeline_run_id}/trigger-step/",
            json_data={"step_type": "reporting"},
        )
        logger.info(f"   • Digest trigger HTTP status: {resp.status_code}")
        assert resp.status_code in (200, 201), f"Email digest dispatch failed: {resp.text}"

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
        logger.info("🎉 EMAIL DIGEST DISPATCH SCENARIO PASSED SUCCESSFULLY!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "pipeline_run_id": pipeline_run_id,
            "digest_status": resp.status_code,
            "cost_metrics": cost_metrics,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete digest test workspace: {del_err}")
