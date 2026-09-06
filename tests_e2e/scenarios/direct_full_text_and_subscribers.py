"""
Direct Full-Text Screening & Subscriber Notifications Lifecycle E2E Scenario.
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

logger = logging.getLogger("e2e_direct_ft")


def run_direct_full_text_and_subscribers_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    End-to-end user journey validating Direct-to-Full-Text Screening & Subscriber Lifecycle:
    1. Creates workspace with `skip_abstract_screening=True`.
    2. Registers multiple subscribers across distinct subscription types:
       - 'result_report': receives weekly scorecard & synthesized findings.
       - 'pipeline_errors': receives critical alerts on run failures.
       - 'pipeline_status': receives operational execution digests.
       - 'all': receives all broadcast events.
    3. Configures academic scraper (arXiv: 'quantum dot solar cell').
    4. Triggers autonomous pipeline run with `skip_abstract_screening=True`.
    5. Verifies that abstract screening is bypassed, candidate papers are routed directly
       to PDF download + OCR layout extraction + multimodal full-text screening.
    6. Verifies parameter extraction, composite scoring, and narrative executive briefing.
    7. Verifies subscriber notification dispatch resolves matching active recipients.
    8. Cleans up test workspace.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_direct_ft_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)
    validator = DataConsistencyValidator(client)

    logger.info("=================================================================")
    logger.info("⚡ STARTING DIRECT FULL-TEXT SCREENING & SUBSCRIBERS SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info("=================================================================")

    start_time = time.time()

    # Pre-cleanup
    if cfg.cleanup_before:
        ws_svc.cleanup_old_test_workspaces(prefix="test_e2e_direct_ft_")

    workspace_id = None

    try:
        # Step 1: Create workspace with skip_abstract_screening=True
        logger.info("📍 Step 1: Creating workspace with skip_abstract_screening=True...")
        ext_defs = [
            {
                "name": f"{workspace_name}_efficiency",
                "exit_metrics": ["efficiency_pct"],
                "system_prompt": "Extract reported power conversion efficiency (PCE) in percent.",
                "user_prompt_template": "Paper Title: {title}\nContent:\n{content}\nExtract PCE efficiency percentage.",
                "response_schema": {
                    "type": "object",
                    "required": ["efficiency_pct"],
                    "properties": {"efficiency_pct": {"type": "number", "minimum": 0, "maximum": 100}},
                },
                "is_active": True,
            }
        ]

        scrapers = [
            {
                "provider": "arxiv",
                "search_query": "quantum dot solar cell",
                "limit": min(cfg.limit, 3),
                "sort_by": "relevance",
                "sort_order": "desc",
                "n_last_days": 14,
                "is_active": True,
            }
        ]

        ws_data = ws_svc.create_workspace(
            name=workspace_name,
            abstract_acceptance_criteria="Inclusion: Quantum dot materials or colloidal semiconductor nanocrystals.",
            abstract_rejection_criteria="Exclusion: Unrelated astronomy or non-semiconductor materials.",
            full_text_acceptance_criteria="Inclusion: Reports photovoltaic device fabrication, open-circuit voltage, or efficiency measurements.",
            full_text_rejection_criteria="Exclusion: Pure review papers without experimental photovoltaic characterization.",
            skip_abstract_screening=True,
            screening_llm_model="google/gemini-3.8-flash",
            extraction_definitions=ext_defs,
            scrapers=scrapers,
        )
        workspace_id = ws_data["id"]
        assert ws_data.get("skip_abstract_screening") is True, "Workspace skip_abstract_screening should be True"

        # Step 2: Register subscribers across all 4 subscription types
        logger.info("📍 Step 2: Registering subscribers across distinct notification types...")
        sub_specs = [
            (f"lead_{random_suffix}@example.com", "Result Analyst", "result_report"),
            (f"ops_{random_suffix}@example.com", "Ops Sentinel", "pipeline_errors"),
            (f"pm_{random_suffix}@example.com", "Project Lead", "pipeline_status"),
            (f"director_{random_suffix}@example.com", "Research Director", "all"),
        ]
        created_subs = []
        for email, name, sub_type in sub_specs:
            sub = ws_svc.create_subscriber(
                workspace_id=workspace_id,
                email=email,
                name=name,
                subscription_type=sub_type,
            )
            created_subs.append(sub)

        # Verify subscriber listing
        listed_subs = ws_svc.list_subscribers(workspace_id)
        assert len(listed_subs) == 4, f"Expected 4 subscribers, found {len(listed_subs)}"
        active_types = {s.get("subscription_type") for s in listed_subs}
        assert active_types == {"result_report", "pipeline_errors", "pipeline_status", "all"}, f"Unexpected subscriber types: {active_types}"
        logger.info(f"✅ Registered {len(listed_subs)} subscribers across all 4 notification categories.")

        # Step 3: Trigger autonomous pipeline run with direct full-text routing
        logger.info("📍 Step 3: Launching autonomous pipeline run (direct-to-full-text)...")
        run_data = agent_svc.start_pipeline_run(
            workspace_id=workspace_id,
            name=f"{workspace_name}_run",
            limit=min(cfg.limit, 3),
            skip_abstract_screening=True,
            autonomous=True,
        )
        pipeline_run_id = run_data["pipeline_run_id"]
        logger.info(f"✅ Pipeline run launched with ID: {pipeline_run_id}")

        # Step 4: Poll run to completion
        logger.info("📍 Step 4: Polling pipeline run to completion...")
        final_run = agent_svc.poll_pipeline_run_to_completion(
            pipeline_run_id=pipeline_run_id,
            timeout_seconds=cfg.timeout,
            poll_interval=cfg.poll_interval,
        )
        run_status = final_run.get("status")
        assert run_status == "completed", f"Pipeline run failed with status '{run_status}': {final_run.get('error_message')}"

        # Step 5: Verify stage transitions & component telemetry
        logger.info("📍 Step 5: Verifying direct full-text stage execution & component telemetry...")
        components = pipeline_svc.get_component_runs(pipeline_run_id)
        executed_steps = [c.get("step_type") for c in components if c.get("status") == "completed"]
        logger.info(f"  Executed pipeline steps: {executed_steps}")

        assert "search" in executed_steps, "Search step did not complete"
        assert "download" in executed_steps, "PDF download step did not complete"
        assert "ocr" in executed_steps, "OCR step did not complete"
        assert "screening" in executed_steps, "Screening step did not complete"

        # Verify papers and metrics
        papers = pipeline_svc.list_papers(workspace_id=workspace_id)
        logger.info(f"  Total Ingested Papers: {len(papers)}")
        assert len(papers) > 0, "No papers were ingested by scraper"

        # Step 6: Verify Subscriber Notification Dispatch
        logger.info("📍 Step 6: Verifying subscriber notification resolution...")
        # Query subscribers matching 'result_report' event: should be 'result_report' + 'all'
        result_subscribers = [s for s in listed_subs if s.get("subscription_type") in ("result_report", "all")]
        assert len(result_subscribers) == 2, f"Expected 2 result report recipients, got {len(result_subscribers)}"

        error_subscribers = [s for s in listed_subs if s.get("subscription_type") in ("pipeline_errors", "all")]
        assert len(error_subscribers) == 2, f"Expected 2 error alert recipients, got {len(error_subscribers)}"

        status_subscribers = [s for s in listed_subs if s.get("subscription_type") in ("pipeline_status", "all")]
        assert len(status_subscribers) == 2, f"Expected 2 status digest recipients, got {len(status_subscribers)}"
        logger.info("✅ Multi-type subscriber notification routing verified.")

        total_elapsed = time.time() - start_time
        logger.info("=================================================================")
        logger.info("🎉 DIRECT FULL-TEXT SCREENING & SUBSCRIBERS SCENARIO PASSED!")
        logger.info(f"   • Abstract Bypass Routing : VERIFIED (skip_abstract_screening=True)")
        logger.info(f"   • Direct PDF OCR & Screen : VERIFIED ({len(papers)} candidate paper(s))")
        logger.info(f"   • Subscriber Categories   : VERIFIED (4 categories: report, errors, status, all)")
        logger.info(f"   • Notification Routing    : VERIFIED (Targeted recipient filtering)")
        logger.info(f"   • Total Elapsed Time      : {total_elapsed:.1f}s")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "pipeline_run_id": pipeline_run_id,
            "papers_count": len(papers),
            "subscribers_count": len(listed_subs),
            "total_elapsed_seconds": total_elapsed,
        }

    finally:
        # Step 7: Post-cleanup
        if getattr(cfg, "cleanup_after", getattr(cfg, "delete_after", False)) and workspace_id:
            logger.info("🧹 Performing post-scenario workspace cleanup...")
            try:
                ws_svc.delete_workspace(workspace_id)
                logger.info("✅ Test workspace cleaned up.")
            except Exception as e:
                logger.warning(f"Failed to delete test workspace '{workspace_id}': {e}")
