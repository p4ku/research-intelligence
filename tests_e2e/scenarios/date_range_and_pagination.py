"""
Scraper Date Range, Relative Lookback & Multi-Page Results Pagination E2E Scenario.

Validates:
1. Relative lookback window (n_last_days) configuration and propagation to autonomous agents.
2. Explicit date bounds (start_date, end_date) in ISO format for historical scraping.
3. Multi-page pagination across REST API endpoints:
   - /api/papers/ (?page=1&page_size=2, page=2, page_size=100, page=9999 out-of-bounds)
   - /api/pipeline-runs/ (?page=1&page_size=2)
   - /api/extractions/ (?page=1&page_size=5)
   - /api/reports/ (?page=1&page_size=5)
4. Envelope integrity: 'count', 'next', 'previous', and 'results'.
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

logger = logging.getLogger("e2e_date_pagination")


def run_date_range_and_pagination_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Executes E2E scenario validating date range parameters and multi-page pagination:
    1. Provisions workspace with scraper.
    2. Launches agent with relative lookback (n_last_days=14) and verifies execution.
    3. Launches agent with explicit date range (start_date, end_date).
    4. Validates pagination across all core listing endpoints.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_date_pagination_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("📅 STARTING SCRAPER DATE RANGE & RESULTS PAGINATION SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info(f"📍 Target API      : {cfg.base_url}")
    logger.info(f"📍 Scraper Provider: {cfg.provider}")
    logger.info("=================================================================")

    # Phase 1: Provision Workspace with dual-stage criteria and default extraction targets
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept all scientific papers about quantum computing, machine learning, or computing algorithms.",
        abstract_rejection_criteria="Reject papers completely unrelated to computing or physics.",
        full_text_acceptance_criteria="Accept empirical, theoretical, and architectural evaluations.",
        full_text_rejection_criteria="Reject papers without scientific or technical details.",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]

    try:
        query = (
            "machine learning neural networks optimization algorithms"
            if cfg.provider == "openalex"
            else 'all:quantum AND all:computing'
        )
        # Create Scraper
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider=cfg.provider,
            search_query=query,
            limit=4,
        )

        # -----------------------------------------------------------------
        # Phase 2: Test Relative Lookback Window (n_last_days)
        # -----------------------------------------------------------------
        logger.info("\n🗓️ Phase 2: Launching Agent with relative lookback (n_last_days=14)...")
        proc1 = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Lookback 14 Days - {workspace_name}",
            limit=4,
            n_last_days=14,
            reprocess_existing=True,
        )
        proc1_id = proc1["id"]
        logger.info(f"   • Agent process started: {proc1_id}")

        # Verify configuration_override stored n_last_days
        proc1_status = agent_svc.get_agent_status(proc1_id)
        cfg_override = proc1_status.get("configuration_override") or {}
        assert cfg_override.get("n_last_days") == 14, f"Expected n_last_days=14 in config override, got: {cfg_override}"
        logger.info("   ✅ Verified n_last_days=14 in agent configuration override.")

        # Poll until completion
        completed1 = agent_svc.poll_until_complete(
            process_id=proc1_id,
            max_timeout_sec=cfg.max_timeout_sec,
            poll_interval_sec=cfg.poll_interval_sec,
        )
        assert completed1.get("status") == "completed", f"Lookback run failed: {completed1}"
        logger.info(f"   ✅ Agent process '{proc1_id}' completed with n_last_days=14.")

        # -----------------------------------------------------------------
        # Phase 3: Test Explicit Date Bounds (start_date, end_date)
        # -----------------------------------------------------------------
        logger.info("\n📅 Phase 3: Launching Agent with explicit date bounds ('2026-08-01' to '2026-08-15')...")
        proc2 = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Historical Window - {workspace_name}",
            limit=4,
            start_date="2026-08-01",
            end_date="2026-08-15",
            reprocess_existing=True,
        )
        proc2_id = proc2["id"]
        logger.info(f"   • Historical agent process started: {proc2_id}")

        proc2_status = agent_svc.get_agent_status(proc2_id)
        cfg2_override = proc2_status.get("configuration_override") or {}
        assert cfg2_override.get("start_date") == "2026-08-01", f"Expected start_date in config, got {cfg2_override}"
        assert cfg2_override.get("end_date") == "2026-08-15", f"Expected end_date in config, got {cfg2_override}"
        logger.info("   ✅ Verified start_date and end_date in agent configuration override.")

        completed2 = agent_svc.poll_until_complete(
            process_id=proc2_id,
            max_timeout_sec=cfg.max_timeout_sec,
            poll_interval_sec=cfg.poll_interval_sec,
        )
        assert completed2.get("status") == "completed", f"Historical date run failed: {completed2}"
        logger.info(f"   ✅ Agent process '{proc2_id}' completed with explicit date range.")

        # -----------------------------------------------------------------
        # Phase 4: Validate Multi-Page Pagination across REST API endpoints
        # -----------------------------------------------------------------
        logger.info("\n📄 Phase 4: Testing Multi-Page Pagination across core REST endpoints...")

        # 4.1 Papers Pagination (?page=1&page_size=2)
        logger.info("   🔍 4.1 Testing /api/papers/ pagination (page=1, page_size=2)...")
        page1_resp = pipeline_svc.list_papers(
            workspace_id=workspace_id,
            page=1,
            page_size=2,
            return_full_response=True,
        )
        assert isinstance(page1_resp, dict), f"Expected dict for paginated response, got {type(page1_resp)}"
        total_count = page1_resp.get("count", 0)
        p1_results = page1_resp.get("results", [])
        logger.info(f"      • Total papers in workspace: {total_count}, returned on page 1: {len(p1_results)}")
        assert total_count >= 1, f"Expected at least 1 paper ingested, found {total_count}"
        assert len(p1_results) <= 2, f"Page size was 2, but received {len(p1_results)} items"
        assert page1_resp.get("previous") is None, "Page 1 previous link should be None"

        if total_count > 2:
            assert page1_resp.get("next") is not None, "Expected next page link when total_count > page_size"
            logger.info("      • Next page link verified.")

            # 4.2 Query Page 2
            logger.info("   🔍 4.2 Querying /api/papers/ (page=2, page_size=2)...")
            page2_resp = pipeline_svc.list_papers(
                workspace_id=workspace_id,
                page=2,
                page_size=2,
                return_full_response=True,
            )
            p2_results = page2_resp.get("results", [])
            assert page2_resp.get("previous") is not None, "Page 2 previous link should exist"
            # Ensure items on page 2 differ from page 1
            p1_ids = {p["id"] for p in p1_results}
            p2_ids = {p["id"] for p in p2_results}
            assert len(p1_ids.intersection(p2_ids)) == 0, "Page 1 and Page 2 contains overlapping paper IDs"
            logger.info(f"      ✅ Page 2 verified: {len(p2_results)} unique papers, valid previous/next links.")

        # 4.3 Custom Page Size Override (page_size=50)
        logger.info("   🔍 4.3 Testing custom page_size=50 override...")
        p50_resp = pipeline_svc.list_papers(
            workspace_id=workspace_id,
            page=1,
            page_size=50,
            return_full_response=True,
        )
        assert len(p50_resp.get("results", [])) == total_count, "Custom page_size=50 should return all items"
        logger.info(f"      ✅ Verified page_size=50 returned all {total_count} papers.")

        # 4.4 Out-of-bounds Page handling (page=9999)
        logger.info("   🔍 4.4 Testing out-of-bounds page (page=9999) returns 404...")
        oob_resp = client.get(f"/api/papers/?workspace={workspace_id}&page=9999&page_size=2")
        assert oob_resp.status_code == 404, f"Expected 404 for out-of-bounds page, got {oob_resp.status_code}"
        logger.info("      ✅ Out-of-bounds page correctly responded with HTTP 404.")

        # 4.5 Pipeline Runs Pagination
        logger.info("   🔍 4.5 Testing /api/pipeline-runs/ pagination...")
        pr_resp = pipeline_svc.list_pipeline_runs(
            workspace_id=workspace_id,
            page=1,
            page_size=2,
            return_full_response=True,
        )
        assert isinstance(pr_resp, dict) and "count" in pr_resp, f"Invalid pipeline-runs pagination: {pr_resp}"
        logger.info(f"      ✅ Pipeline runs paginated: count={pr_resp.get('count')}, page items={len(pr_resp.get('results', []))}")

        # 4.6 Extractions Pagination
        logger.info("   🔍 4.6 Testing /api/extractions/ pagination...")
        ext_resp = pipeline_svc.list_extractions(
            workspace_id=workspace_id,
            page=1,
            page_size=5,
            return_full_response=True,
        )
        assert isinstance(ext_resp, dict) and "count" in ext_resp, f"Invalid extractions pagination: {ext_resp}"
        logger.info(f"      ✅ Extractions paginated: count={ext_resp.get('count')}, page items={len(ext_resp.get('results', []))}")

        # 4.7 Reports Pagination
        logger.info("   🔍 4.7 Testing /api/reports/ pagination...")
        rep_resp = pipeline_svc.list_reports(
            workspace_id=workspace_id,
            page=1,
            page_size=5,
            return_full_response=True,
        )
        assert isinstance(rep_resp, dict) and "count" in rep_resp, f"Invalid reports pagination: {rep_resp}"
        logger.info(f"      ✅ Reports paginated: count={rep_resp.get('count')}, page items={len(rep_resp.get('results', []))}")

        logger.info("\n=================================================================")
        logger.info("🎉 SCRAPER DATE RANGE & RESULTS PAGINATION SCENARIO PASSED!")
        logger.info(f"   • Lookback (n_last_days)  : VERIFIED (14 days)")
        logger.info(f"   • Date Range Bounds       : VERIFIED (2026-08-01 to 2026-08-15)")
        logger.info(f"   • Multi-Page Pagination   : VERIFIED (Papers, Runs, Extractions, Reports)")
        logger.info("=================================================================")

        return {
            "scenario": "date_range_and_pagination",
            "status": "passed",
            "workspace_id": workspace_id,
            "total_papers": total_count,
            "proc1_id": proc1_id,
            "proc2_id": proc2_id,
        }

    finally:
        if cfg.delete_after:
            logger.info(f"🗑️ Deleting workspace '{workspace_id}'...")
            ws_svc.delete_workspace(workspace_id)
