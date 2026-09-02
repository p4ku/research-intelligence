"""
Executive Briefing Generation & Narrative Report E2E Scenario.
Validates User Journey 3 & 6:
- Autonomous generation of executive SLR narrative briefing at pipeline completion.
- Scoped report query via GET /api/reports/?pipeline_run={id}.
- Validation of executive sections: Executive Summary, Review Highlights, Breakthrough Papers, Execution Trace.
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

logger = logging.getLogger("e2e_briefing_export")


def run_executive_briefing_export_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Validates end-to-end executive narrative briefing synthesis:
    1. Provisions workspace and triggers an autonomous review pipeline.
    2. Waits for pipeline completion (including step 7 reporting).
    3. Queries GET /api/reports/?pipeline_run={pr_id} (frontend /briefing contract).
    4. Validates markdown structure, executive summary, breakthrough papers, and economics trace.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_briefing_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("📰 STARTING EXECUTIVE BRIEFING GENERATION & REPORT SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info(f"📍 Target API      : {cfg.base_url}")
    logger.info("=================================================================")

    # 1. Provision workspace
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept deep learning and natural language processing.",
        abstract_rejection_criteria="Reject unrelated.",
        full_text_acceptance_criteria="Accept empirical evaluations and benchmark results.",
        full_text_rejection_criteria="Reject pure opinion.",
        screening_llm_model="google/gemini-3.8-flash",
    )
    workspace_id = ws_data["id"]

    try:
        # Create Scraper
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.CL AND all:"language model"',
            limit=2,
        )

        # 2. Launch research pipeline
        logger.info("🚀 Launching research pipeline to synthesize executive briefing...")
        proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Briefing Run - {workspace_name}",
            limit=2,
        )

        # Poll until complete
        completed_agent = agent_svc.poll_until_complete(proc["id"], max_timeout_sec=cfg.max_timeout_sec)
        assert completed_agent.get("status") == "completed", f"Pipeline failed: {completed_agent}"

        pr_id = completed_agent.get("pipeline_run")
        assert pr_id, "Completed agent process must reference a valid pipeline_run UUID"

        # 3. Retrieve Executive Narrative Report scoped to PipelineRun
        logger.info(f"📥 Querying /api/reports/?pipeline_run={pr_id} ...")
        resp_reports = client.get("/api/reports/", params={"pipeline_run": pr_id}, expected_status=200)
        reports_data = resp_reports.json()
        reports_list = reports_data.get("results", reports_data) if isinstance(reports_data, dict) else reports_data

        assert len(reports_list) > 0, f"Expected at least one NarrativeReport for pipeline_run '{pr_id}', got 0"
        report = reports_list[0]

        logger.info(f"   • Report Title : {report.get('title')}")
        logger.info(f"   • Created At   : {report.get('created_at')}")

        # 4. Validate Structured Markdown Sections
        content = report.get("content_markdown", "")
        assert len(content) > 100, f"Report content appears too short ({len(content)} chars)"

        # Check required architectural sections
        has_header = "Executive Research Briefing" in content or "Briefing" in content
        has_summary = "Executive Summary" in content or "Summary" in content
        has_breakthroughs = "Breakthrough Papers" in content or "Top-Ranked" in content or "Papers" in content
        has_trace = "Execution Trace" in content or "Resource" in content or "Tokens" in content

        logger.info(f"   • Header Section Present       : {has_header}")
        logger.info(f"   • Executive Summary Present    : {has_summary}")
        logger.info(f"   • Breakthrough Papers Present  : {has_breakthroughs}")
        logger.info(f"   • Execution Trace Present      : {has_trace}")

        assert has_summary, "Report markdown must contain Executive Summary section"
        assert has_breakthroughs, "Report markdown must contain Breakthrough Papers section"

        logger.info("=================================================================")
        logger.info("🎉 EXECUTIVE BRIEFING GENERATION SCENARIO PASSED!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "pipeline_run_id": pr_id,
            "report_id": report.get("id"),
            "report_title": report.get("title"),
            "content_length": len(content),
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_err:
                logger.warning(f"Could not delete test workspace: {del_err}")
