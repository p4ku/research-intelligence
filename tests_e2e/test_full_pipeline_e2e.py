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
