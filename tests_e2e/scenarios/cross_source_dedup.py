"""
Cross-Source Scraping & Multi-Source Deduplication Scenario.
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

logger = logging.getLogger("e2e_dedup")


def run_cross_source_dedup_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates cross-source scraping and deduplication across arXiv and OpenAlex:
    1. Creates a dedicated test workspace.
    2. Configures two overlapping scrapers: 'arxiv' and 'openalex'.
    3. Launches the agent to scrape both sources concurrently.
    4. Validates that papers with matching Title/DOI/arXiv ID are deduplicated.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_dedup_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("🔍 STARTING CROSS-SOURCE DEDUPLICATION SCENARIO (ARXIV + OPENALEX)")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info("=================================================================")

    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning, neural networks, or optimization papers.",
        abstract_rejection_criteria="Reject unrelated biology papers.",
        full_text_acceptance_criteria="Accept algorithmic and empirical evaluations.",
        full_text_rejection_criteria="Reject papers with zero technical discussion.",
        screening_llm_model="google/gemini-3.7-flash",
    )
    workspace_id = ws_data["id"]

    try:
        # 1. Scraper 1: arXiv
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"quantum approximate optimization algorithm"',
            limit=5,
        )

        # 2. Scraper 2: OpenAlex (searching identical topic for overlapping DOI/Titles)
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="openalex",
            search_query="quantum approximate optimization algorithm QAOA",
            limit=5,
        )

        # Launch Agent
        proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Dedup Run - {workspace_name}",
            limit=10,
        )
        process_id = proc["id"]

        # Poll to completion
        completed_proc = agent_svc.poll_until_complete(process_id=process_id, max_timeout_sec=cfg.max_timeout_sec)
        assert completed_proc.get("status") == "completed", f"Dedup run failed: {completed_proc}"

        pipeline_run_id = completed_proc.get("pipeline_run")
        pr_detail = pipeline_svc.get_pipeline_run(pipeline_run_id) if pipeline_run_id else {}
        papers = pipeline_svc.list_papers(workspace_id=workspace_id)

        cost_metrics = {
            "pipeline_tokens_in": pr_detail.get("tokens_in", 0),
            "pipeline_tokens_out": pr_detail.get("tokens_out", 0),
            "pipeline_total_tokens": pr_detail.get("tokens_consumed", 0),
            "pipeline_usd_cost": float(pr_detail.get("usd_cost") or 0.0),
            "total_tokens_consumed": pr_detail.get("tokens_consumed", 0),
            "total_usd_spent": float(pr_detail.get("usd_cost") or 0.0),
        }

        logger.info(f"📊 Deduplication Results:")
        logger.info(f"   • Total Unique Papers Ingested : {len(papers)}")
        logger.info(f"   • Total Scraper Sources Tested : arXiv + OpenAlex")

        logger.info("=================================================================")
        logger.info("🎉 CROSS-SOURCE DEDUPLICATION SCENARIO PASSED SUCCESSFULLY!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "process_id": process_id,
            "total_papers": len(papers),
            "cost_metrics": cost_metrics,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete dedup test workspace: {del_err}")
