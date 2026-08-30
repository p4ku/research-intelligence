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
)


class TestFullPipelineE2E:
    """
    State-of-the-Art End-to-End Test Suite against Staging / Production API.
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
    def test_chat_multiturn_conversational_grounding(self):
        config = E2EConfig.from_env()
        # Run a quick review to get a validated paper
        slr_results = run_full_slr_pipeline_scenario(config)
        ws_id = slr_results["workspace_id"]
        top_papers = slr_results.get("top_papers", [])

        if top_papers:
            from tests_e2e.client import APIClient, PipelineService
            client = APIClient(config.base_url)
            client.set_auth_token(config.password)  # Re-used in service
            pipeline_svc = PipelineService(client)
            papers = pipeline_svc.list_papers(workspace_id=ws_id, screening_status="full_text_passed")
            if papers:
                target_paper_id = papers[0]["id"]
                chat_res = run_chat_multiturn_scenario(ws_id, target_paper_id, config)
                assert chat_res["status"] == "completed"
                assert chat_res["session_id"] != ""
