"""
Pytest E2E Test Suite for Schwarz Research Intelligence Platform.

Usage:
  pytest tests_e2e/test_full_pipeline_e2e.py -s -v
  E2E_TARGET_ENV=prod pytest tests_e2e/test_full_pipeline_e2e.py -s -v
"""

import pytest
from tests_e2e.config import E2EConfig
from tests_e2e.scenarios import (
    run_full_slr_pipeline_scenario,
    run_slr_review_gates_scenario,
    run_chat_multiturn_scenario,
    run_agent_lifecycle_scenario,
    run_pipeline_reprocessing_scenario,
    run_cross_source_dedup_scenario,
    run_quota_guard_scenario,
    run_mcp_protocol_scenario,
    run_rbac_data_isolation_scenario,
    run_mid_step_rerun_scenario,
    run_chat_hallucination_guard_scenario,
    run_concurrent_agents_load_scenario,
    run_concurrent_runs_in_workspace_scenario,
    run_workflow_schedule_scenario,
    run_paper_evidence_and_pdf_scenario,
    run_researcher_rbac_guard_scenario,
    run_executive_briefing_export_scenario,
    run_signal_score_variables_scenario,
    run_date_range_and_pagination_scenario,
    run_ask_paper_journey_scenario,
    run_workspace_import_export_scenario,
    run_direct_full_text_and_subscribers_scenario,
    run_hitl_validation_journey_scenario,
    run_stars_curation_journey_scenario,
    run_paper_page_scorecard_journey_scenario,
    run_run_admission_guard_scenario,
    run_briefing_filters_and_pagination_scenario,
    run_three_personas_rbac_journey_scenario,
)


class TestFullPipelineE2E:
    """
    State-of-the-Art End-to-End Test Suite against Staging / Production API.
    Every test method represents a strictly orthogonal, self-contained scenario.
    """

    @pytest.mark.e2e
    def test_full_slr_pipeline_execution(self):
        config = E2EConfig.from_env()
        results = run_full_slr_pipeline_scenario(config)

        assert results["workspace_id"] is not None
        assert results["process_id"] is not None
        assert results["stage_checks"]["search"] == "PASSED"
        assert results["stage_checks"]["abstract_screening"] == "PASSED"
        assert results["stage_checks"]["download"] == "PASSED"
        assert results["stage_checks"]["full_text_screening"] == "PASSED"
        assert results["stage_checks"]["extraction"].startswith("PASSED")
        assert results["stage_checks"]["signal_score"].startswith("PASSED")
        assert results["stage_checks"]["reporting"].startswith("PASSED")
        assert results["total_papers_fetched"] > 0
        assert results["accepted_papers_count"] >= 0
        assert results["extractions_count"] >= 0

        # Cost and token invariants
        cost_m = results.get("cost_metrics", {})
        assert cost_m.get("total_tokens_consumed", 0) >= 0
        assert cost_m.get("total_usd_spent", 0.0) >= 0.0

        # Verify sorted invariant for top_papers:
        top_papers = results.get("top_papers", [])
        scores = [p["signal_score"] for p in top_papers if p.get("signal_score") is not None]
        assert scores == sorted(scores, reverse=True), f"Top papers must be strictly sorted by signal_score descending: {scores}"

    @pytest.mark.e2e
    def test_slr_review_gates_lifecycle(self):
        config = E2EConfig.from_env()
        results = run_slr_review_gates_scenario(config)
        assert results["status"] == "PASSED"
        assert results["gate_1_abstract"].get("status") == "COMPLETED_AND_RESUMED"
        assert results["gate_2_full_text"].get("status") == "COMPLETED_AND_RESUMED"
        assert results["gate_3_extraction"].get("status") == "COMPLETED_AND_RESUMED"
        assert results["prisma_metrics"] is not None

    @pytest.mark.e2e
    def test_agent_lifecycle_pause_resume(self):
        config = E2EConfig.from_env()
        results = run_agent_lifecycle_scenario(config)
        assert results["status"] == "passed"
        assert results["final_status"] == "completed"

    @pytest.mark.e2e
    def test_pipeline_reprocessing_existing_papers(self):
        config = E2EConfig.from_env()
        results = run_pipeline_reprocessing_scenario(config)
        assert results["status"] == "passed"
        assert results["total_papers"] > 0

    @pytest.mark.e2e
    def test_cross_source_deduplication(self):
        config = E2EConfig.from_env()
        results = run_cross_source_dedup_scenario(config)
        assert results["status"] == "passed"
        assert results["total_papers"] > 0

    @pytest.mark.e2e
    def test_quota_guard_limits(self):
        config = E2EConfig.from_env()
        results = run_quota_guard_scenario(config)
        assert results["status"] == "passed"

    @pytest.mark.e2e
    def test_mcp_protocol_tools(self):
        config = E2EConfig.from_env()
        results = run_mcp_protocol_scenario(config)
        assert results["status"] == "passed"
        assert results["papers_count"] > 0

    @pytest.mark.e2e
    def test_rbac_multi_tenancy_data_isolation(self):
        config = E2EConfig.from_env()
        results = run_rbac_data_isolation_scenario(config)
        assert results["status"] == "passed"

    @pytest.mark.e2e
    def test_mid_step_pipeline_rerun(self):
        config = E2EConfig.from_env()
        results = run_mid_step_rerun_scenario(config)
        assert results["status"] == "passed"
        assert results["component_runs_count"] > 0

    @pytest.mark.e2e
    def test_chat_hallucination_guard(self):
        config = E2EConfig.from_env()
        results = run_chat_hallucination_guard_scenario(config)
        assert results["status"] == "passed"
        assert results["factual_answer_length"] > 0

    @pytest.mark.e2e
    def test_concurrent_agents_load(self):
        config = E2EConfig.from_env()
        results = run_concurrent_agents_load_scenario(config, num_agents=2)
        assert results["status"] == "passed"
        assert results["agents_count"] == 2

    @pytest.mark.e2e
    def test_chat_multiturn_conversational_grounding(self):
        config = E2EConfig.from_env()
        slr_results = run_full_slr_pipeline_scenario(config)
        ws_id = slr_results["workspace_id"]
        top_papers = slr_results.get("top_papers", [])

        if top_papers:
            from tests_e2e.client import APIClient, AuthService, PipelineService
            client = APIClient(config.base_url)
            auth = AuthService(client)
            auth.login(config.username, config.password)
            pipeline_svc = PipelineService(client)
            papers = pipeline_svc.list_papers(workspace_id=ws_id, screening_status="full_text_passed")
            if papers:
                target_paper_id = papers[0]["id"]
                chat_res = run_chat_multiturn_scenario(ws_id, target_paper_id, config)
                assert chat_res["status"] == "completed"
                assert chat_res["session_id"] != ""

    @pytest.mark.e2e
    def test_workflow_schedule_execution_and_observability(self):
        config = E2EConfig.from_env()
        results = run_workflow_schedule_scenario(config)
        assert results["status"] == "passed"
        assert results["schedule_status"] == "completed"
        assert results["schedule_id"] is not None

    @pytest.mark.e2e
    def test_paper_evidence_and_pdf(self):
        config = E2EConfig.from_env()
        results = run_paper_evidence_and_pdf_scenario(config)
        assert results["status"] == "passed"
        assert results["inspected_paper_id"] is not None

    @pytest.mark.e2e
    def test_executive_briefing_export(self):
        config = E2EConfig.from_env()
        results = run_executive_briefing_export_scenario(config)
        assert results["status"] == "passed"
        assert results["report_id"] is not None
        assert len(results["report_title"]) > 0

    @pytest.mark.e2e
    def test_researcher_rbac_guard(self):
        config = E2EConfig.from_env()
        results = run_researcher_rbac_guard_scenario(config)
        assert results["status"] == "passed"

    @pytest.mark.e2e
    def test_concurrent_runs_in_workspace(self):
        config = E2EConfig.from_env()
        results = run_concurrent_runs_in_workspace_scenario(config)
        assert results["status"] == "passed"

    @pytest.mark.e2e
    def test_run_admission_guard(self):
        config = E2EConfig.from_env()
        results = run_run_admission_guard_scenario(config)
        assert results["status"] == "passed"
        assert results["burst_status_codes"].count(409) == 1

    @pytest.mark.e2e
    def test_signal_score_variables_and_math(self):
        config = E2EConfig.from_env()
        results = run_signal_score_variables_scenario(config)
        assert results["status"].lower() in ("passed", "completed")
        assert results["workspace_id"] is not None
        assert "4_postprocessing_snippet_and_math" in results["scenarios_checked"]
        assert "5_signal_score_code_math_retrieval" in results["scenarios_checked"]

    @pytest.mark.e2e
    def test_workspace_import_export_journey(self):
        config = E2EConfig.from_env()
        results = run_workspace_import_export_scenario(config)
        assert results["status"].lower() in ("passed", "completed")
        assert results["source_workspace_id"] is not None
        assert results["target_workspace_id"] is not None
        assert results["definitions_count"] >= 2
        assert results["scrapers_count"] >= 2
        assert results["subscribers_count"] >= 2

    @pytest.mark.e2e
    def test_direct_full_text_and_subscribers(self):
        config = E2EConfig.from_env()
        results = run_direct_full_text_and_subscribers_scenario(config)
        assert results["status"].lower() in ("passed", "completed")
        assert results["workspace_id"] is not None
        assert results["pipeline_run_id"] is not None
        assert results["subscribers_count"] >= 4

    @pytest.mark.e2e
    def test_hitl_validation_journey(self):
        config = E2EConfig.from_env()
        results = run_hitl_validation_journey_scenario(config)
        assert results["status"].lower() in ("passed", "completed")
        assert results["workspace_id"] is not None
        assert results["extraction_id"] is not None
        assert results["correction_id"] is not None

    @pytest.mark.e2e
    def test_date_range_and_pagination(self):
        config = E2EConfig.from_env()
        results = run_date_range_and_pagination_scenario(config)
        assert results["status"] == "passed"
        assert results["workspace_id"] is not None

    @pytest.mark.e2e
    def test_ask_paper_journey(self):
        config = E2EConfig.from_env()
        results = run_ask_paper_journey_scenario(config)
        assert results["status"] == "passed"
        assert results["paper_id"] is not None
        assert results["turns_count"] >= 1

    @pytest.mark.e2e
    def test_stars_curation_journey(self):
        config = E2EConfig.from_env()
        results = run_stars_curation_journey_scenario(config)
        assert results["status"] == "PASSED"
        assert results["tested_isolation_guard"] is True

    @pytest.mark.e2e
    def test_paper_page_scorecard_journey(self):
        config = E2EConfig.from_env()
        results = run_paper_page_scorecard_journey_scenario(config)
        assert results["status"] == "passed"
        assert results["dimensions_count"] > 0
        assert results["paper_id"] is not None

    @pytest.mark.e2e
    def test_briefing_filters_and_pagination(self):
        config = E2EConfig.from_env()
        results = run_briefing_filters_and_pagination_scenario(config)
        assert results["status"] == "passed"
        assert results["checks"]["scope_included"] == "PASSED"
        assert results["checks"]["scope_excluded"] == "PASSED"
        assert results["checks"]["pagination"] == "PASSED"
        assert results["checks"]["sorting"] == "PASSED"

    @pytest.mark.e2e
    def test_three_personas_rbac_journey(self):
        config = E2EConfig.from_env()
        results = run_three_personas_rbac_journey_scenario(config)
        assert results["status"] == "passed"
        assert results["persona_checks"]["admin_full_lifecycle"] == "PASSED"



class TestE2EConfig:
    """Unit validation for E2EConfig attributes and options."""

    def test_cleanup_after_and_delete_after_interchangeable(self):
        cfg1 = E2EConfig(delete_after=True)
        assert cfg1.cleanup_after is True
        assert cfg1.delete_after is True

        cfg2 = E2EConfig(cleanup_after=True)
        assert cfg2.cleanup_after is True
        assert cfg2.delete_after is True

        cfg3 = E2EConfig(delete_after=False)
        assert cfg3.cleanup_after is False
        assert cfg3.delete_after is False
        cfg3.cleanup_after = True
        assert cfg3.delete_after is True
        assert cfg3.cleanup_after is True

        cfg4 = E2EConfig.from_env()
        assert hasattr(cfg4, "cleanup_after")
        assert hasattr(cfg4, "delete_after")
        assert cfg4.cleanup_after == cfg4.delete_after

