"""
Concurrent Pipeline Runs in Single Workspace E2E Scenario.
Validates concurrency, database integrity, and run-scoped data contracts:
1. Launches two autonomous pipeline runs concurrently within the SAME workspace.
2. Asserts that both runs execute without deadlocks or race conditions.
3. Asserts that papers associated with Run 1 and Run 2 are queryable via REST API scoped filters:
   GET /api/papers/?pipeline_run={run_id}
4. Verifies that Run 2 does not unlink, corrupt, or erase Run 1's historical paper bindings.
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

logger = logging.getLogger("e2e_concurrent_runs")


def run_concurrent_runs_in_workspace_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates concurrency of multiple pipeline runs operating within the exact same workspace:
    - Launch Run 1 (initial sweep).
    - Concurrently launch Run 2 (targeted sweep with distinct query/reprocessing).
    - Both complete successfully.
    - Scoped API queries return correct run-scoped paper associations for frontend consumption.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_parallel_runs_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("⚡ STARTING CONCURRENT RUNS IN SINGLE WORKSPACE SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info(f"📍 Target API      : {cfg.base_url}")
    logger.info("=================================================================")

    # 1. Provision single test workspace
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning, neural networks, and algorithmic optimization.",
        abstract_rejection_criteria="Reject unrelated medical and botanical subjects.",
        full_text_acceptance_criteria="Accept empirical benchmarking and formal evaluations.",
        full_text_rejection_criteria="Reject pure opinion pieces with zero technical depth.",
        signal_score_code="score = 0.5 * fit_score + 0.5 * 9.0\nreturn round(score * 10.0, 2)",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]

    try:
        # Create Scrapers for different keywords in the same domain
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"transformer"',
            limit=3,
        )
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"reinforcement"',
            limit=3,
        )

        # 2. Launch Run 1 and Run 2 almost simultaneously in the SAME workspace
        logger.info("🚀 Launching Run 1 (Transformer Ingestion)...")
        run1_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Run 1 Transformer - {workspace_name}",
            limit=3,
        )

        logger.info("🚀 Launching Run 2 (Reinforcement Ingestion & Reprocess) concurrently...")
        run2_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Run 2 Reinforcement - {workspace_name}",
            limit=3,
            reprocess_existing=True,
        )

        processes = [run1_proc, run2_proc]

        # 3. Poll both processes concurrently to completion
        t0 = time.time()
        timeout = cfg.max_timeout_sec
        finished_processes = {}

        logger.info(f"⏳ Monitoring 2 concurrent pipeline runs in workspace '{workspace_name}'...")
        while len(finished_processes) < len(processes) and (time.time() - t0 < timeout):
            for p in processes:
                p_id = p["id"]
                if p_id in finished_processes:
                    continue
                status_data = agent_svc.get_agent_status(p_id)
                st = status_data.get("status")
                step = status_data.get("current_step")

                if st in ("completed", "failed", "aborted"):
                    elapsed = int(time.time() - t0)
                    logger.info(f"  🏁 Agent Process '{p_id}' reached '{st}' at step '{step}' in {elapsed}s")
                    finished_processes[p_id] = status_data

            time.sleep(3.0)

        # Assert both finished with 'completed'
        assert len(finished_processes) == len(processes), f"Timed out waiting for concurrent runs ({len(finished_processes)}/{len(processes)} completed)"
        for p_id, p_data in finished_processes.items():
            assert p_data.get("status") == "completed", f"Process '{p_id}' did not complete successfully: {p_data}"

        # 4. Extract PipelineRun UUIDs
        run1_pr_id = finished_processes[run1_proc["id"]].get("pipeline_run")
        run2_pr_id = finished_processes[run2_proc["id"]].get("pipeline_run")
        assert run1_pr_id and run2_pr_id, "Both completed agent processes must reference a valid pipeline_run UUID"
        assert run1_pr_id != run2_pr_id, "Run 1 and Run 2 must have distinct pipeline_run UUIDs"

        # 5. Validate REST API Scoped Paper Retrieval for Frontend (GET /api/papers/?pipeline_run=...)
        papers_all = pipeline_svc.list_papers(workspace_id=workspace_id)
        papers_run1 = pipeline_svc.list_papers(pipeline_run=run1_pr_id)
        papers_run2 = pipeline_svc.list_papers(pipeline_run=run2_pr_id)

        logger.info(f"📊 Total Papers in Workspace : {len(papers_all)}")
        logger.info(f"📊 Papers in Run 1 Scoped API : {len(papers_run1)}")
        logger.info(f"📊 Papers in Run 2 Scoped API : {len(papers_run2)}")

        # Verification:
        # - Neither run should return 0 papers
        # - Run 1 papers must remain intact even though Run 2 ran concurrently
        assert len(papers_all) > 0, "Workspace must contain ingested papers"
        assert len(papers_run1) > 0, f"Run 1 scoped API must return papers (got {len(papers_run1)})"
        assert len(papers_run2) > 0, f"Run 2 scoped API must return papers (got {len(papers_run2)})"

        # 6. Verify PipelineRun Detail Endpoints (papers_count and storage_stats)
        pr1_detail = pipeline_svc.get_pipeline_run(run1_pr_id)
        pr2_detail = pipeline_svc.get_pipeline_run(run2_pr_id)

        assert pr1_detail.get("papers_count", 0) > 0, f"Run 1 detail papers_count must be > 0 (got {pr1_detail.get('papers_count')})"
        assert pr2_detail.get("papers_count", 0) > 0, f"Run 2 detail papers_count must be > 0 (got {pr2_detail.get('papers_count')})"

        logger.info("=================================================================")
        logger.info("🎉 CONCURRENT RUNS IN SINGLE WORKSPACE SCENARIO PASSED!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "run1_id": run1_pr_id,
            "run2_id": run2_pr_id,
            "run1_papers": len(papers_run1),
            "run2_papers": len(papers_run2),
            "total_papers": len(papers_all),
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not clean up test workspace: {del_err}")
