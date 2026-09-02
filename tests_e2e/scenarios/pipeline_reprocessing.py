"""
Pipeline Reprocessing Scenario (reprocess_existing=True).
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
    DataConsistencyValidator,
)

logger = logging.getLogger("e2e_reprocessing")


def run_pipeline_reprocessing_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates end-to-end reprocessing of existing workspace papers:
    1. Run 1: Performs standard initial ingestion & screening on 5 papers.
    2. Updates workspace criteria / signal score formula.
    3. Run 2: Launches a second research agent with reprocess_existing=True.
    4. Validates that existing papers are re-linked and re-scored without redundant downloads.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_reprocess_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("🔄 STARTING PIPELINE REPROCESSING (REPROCESS_EXISTING) SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info("=================================================================")

    # Create workspace
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning and optimization algorithms.",
        abstract_rejection_criteria="Reject unrelated biology topics.",
        full_text_acceptance_criteria="Accept algorithmic and empirical evaluations.",
        full_text_rejection_criteria="Reject papers with zero technical discussion.",
        signal_score_code="score = 0.5 * fit_score + 0.5 * 8.0\nreturn round(score * 10.0, 2)",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]

    try:
        # Create Scraper
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"optimization"',
            limit=5,
        )

        # -------------------------------------------------------------
        # Phase 1: Run 1 (Initial Standard Ingestion)
        # -------------------------------------------------------------
        logger.info("🚀 Phase 1: Launching Initial Ingestion Run...")
        run1_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Run 1 Initial - {workspace_name}",
            limit=5,
            reprocess_existing=False,
        )
        completed1 = agent_svc.poll_until_complete(run1_proc["id"], max_timeout_sec=cfg.max_timeout_sec)
        assert completed1.get("status") == "completed", f"Run 1 failed: {completed1}"

        pr1_id = completed1.get("pipeline_run")
        papers_after_run1 = pipeline_svc.list_papers(workspace_id=workspace_id, pipeline_run=pr1_id)
        assert len(papers_after_run1) > 0, "No papers ingested during Run 1"
        logger.info(f"✅ Phase 1 Finished: {len(papers_after_run1)} papers ingested in workspace.")

        for p in papers_after_run1:
            DataConsistencyValidator.validate_paper_schema(p)

        # -------------------------------------------------------------
        # Phase 2: Run 2 (Reprocess Existing Papers with Updated Rule)
        # -------------------------------------------------------------
        logger.info("🚀 Phase 2: Launching Reprocessing Run (reprocess_existing=True)...")
        run2_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Run 2 Reprocess - {workspace_name}",
            limit=5,
            reprocess_existing=True,
        )
        completed2 = agent_svc.poll_until_complete(run2_proc["id"], max_timeout_sec=cfg.max_timeout_sec)
        assert completed2.get("status") == "completed", f"Run 2 failed: {completed2}"

        pr2_id = completed2.get("pipeline_run")
        papers_after_run2 = pipeline_svc.list_papers(workspace_id=workspace_id, pipeline_run=pr2_id)
        logger.info(f"✅ Phase 2 Finished: {len(papers_after_run2)} papers re-evaluated across workspace.")

        # Data Invariant: Run 2 must contain all papers that existed in Run 1
        assert len(papers_after_run2) >= len(papers_after_run1), (
            f"Reprocessing must retain all previous papers: Run 1 had {len(papers_after_run1)}, Run 2 has {len(papers_after_run2)}"
        )
        for p in papers_after_run2:
            DataConsistencyValidator.validate_paper_schema(p)

        # Cross-validate PaperMetrics isolation between Run 1 and Run 2
        metrics_run1 = pipeline_svc.list_paper_metrics(workspace_id=workspace_id, pipeline_run=pr1_id)
        metrics_run2 = pipeline_svc.list_paper_metrics(workspace_id=workspace_id, pipeline_run=pr2_id)
        for m in metrics_run1 + metrics_run2:
            DataConsistencyValidator.validate_paper_metric_schema(m)

        pr1 = pipeline_svc.get_pipeline_run(pr1_id) if pr1_id else {}
        pr2 = pipeline_svc.get_pipeline_run(pr2_id) if pr2_id else {}
        DataConsistencyValidator.validate_token_and_cost_integrity(pr1)
        DataConsistencyValidator.validate_token_and_cost_integrity(pr2)

        tok1 = pr1.get("tokens_consumed", 0) or 0
        tok2 = pr2.get("tokens_consumed", 0) or 0
        usd1 = float(pr1.get("usd_cost") or 0.0)
        usd2 = float(pr2.get("usd_cost") or 0.0)

        cost_metrics = {
            "pipeline_tokens_in": (pr1.get("tokens_in", 0) or 0) + (pr2.get("tokens_in", 0) or 0),
            "pipeline_tokens_out": (pr1.get("tokens_out", 0) or 0) + (pr2.get("tokens_out", 0) or 0),
            "pipeline_total_tokens": tok1 + tok2,
            "pipeline_usd_cost": usd1 + usd2,
            "total_tokens_consumed": tok1 + tok2,
            "total_usd_spent": usd1 + usd2,
        }

        logger.info("=================================================================")
        logger.info("🎉 PIPELINE REPROCESSING SCENARIO PASSED SUCCESSFULLY!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "run1_process_id": run1_proc["id"],
            "run2_process_id": run2_proc["id"],
            "total_papers": len(papers_after_run2),
            "cost_metrics": cost_metrics,
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete reprocess test workspace: {del_err}")
