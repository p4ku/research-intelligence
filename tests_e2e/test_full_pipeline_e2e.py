"""
Pytest E2E Test Suite for Schwarz Research Intelligence Platform.

Usage:
  pytest tests_e2e/test_full_pipeline_e2e.py -s -v
  E2E_TARGET_ENV=prod pytest tests_e2e/test_full_pipeline_e2e.py -s -v
"""

import pytest
from tests_e2e.config import E2EConfig
from tests_e2e.scenarios.full_slr_pipeline import run_full_slr_pipeline_scenario


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
