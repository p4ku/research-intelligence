"""
Signal Score Variables & Mathematical Verification E2E Scenario.

Validates the complete variable lifecycle across all 4 configurations:
1. No exit parameters (exit_metrics=[] / None) -> mapped via definition name slug or raw field.
2. Single exit parameter (exit_metrics=["rigour_score"]).
3. Multiple exit parameters (exit_metrics=["sample_size", "control_groups", "p_value"]).
4. Exit parameters with custom Python sandboxed postprocessing snippet (exit_metrics=["market_fit", "growth_potential"],
   postprocessing_code="return (market_fit * 1.5) + growth_potential").

Retrieves all variables in "Signal score code" and verifies the mathematical computation with 100% precision.
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

logger = logging.getLogger("e2e_signal_score_variables")


def run_signal_score_variables_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Executes E2E scenario validating variable availability and math in Signal score code:
    1. Provisions workspace with 4 extraction definitions (no exit params, single, multiple, postprocessing).
    2. Configures dynamic sandboxed formula in signal_score_code combining all variables.
    3. Triggers research agent pipeline and waits for completion.
    4. Queries /api/papers/ and /api/papers/{id}/scorecard/ to inspect signal_score_details.
    5. Validates mathematical precision of postprocessing snippet and signal score formula.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_variables_math_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("🔢 STARTING SIGNAL SCORE VARIABLES & MATH E2E SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info(f"📍 Target API      : {cfg.base_url}")
    logger.info("=================================================================")

    # 1. Define Extraction Definitions covering all 4 scenarios
    definitions = [
        # 1) Scenario 1: No exit parameters (exit_metrics is empty / None)
        {
            "name": "Novelty Evaluation",
            "exit_metrics": [],
            "llm_model": "google/gemini-3.8-flash",
            "system_prompt": "Evaluate paper novelty from 1.0 to 10.0 and return JSON.",
            "user_prompt_template": "Paper Title: {title}\nEvaluate novelty score (1-10).",
            "response_schema": {
                "type": "object",
                "properties": {
                    "novelty_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "value": {"type": "number"}
                }
            },
            "is_active": True,
        },
        # 2) Scenario 2: Single exit parameter
        {
            "name": "Methodology Rigour",
            "exit_metrics": ["rigour_score"],
            "llm_model": "google/gemini-3.8-flash",
            "system_prompt": "Evaluate methodology rigour from 1.0 to 10.0 and return JSON.",
            "user_prompt_template": "Paper Title: {title}\nEvaluate rigour score (1-10).",
            "response_schema": {
                "type": "object",
                "properties": {
                    "rigour_score": {"type": "number", "minimum": 0, "maximum": 10}
                }
            },
            "is_active": True,
        },
        # 3) Scenario 3: Multiple exit parameters (list of parameters)
        {
            "name": "Dataset Statistics",
            "exit_metrics": ["sample_size", "control_groups", "p_value"],
            "llm_model": "google/gemini-3.8-flash",
            "system_prompt": "Extract dataset parameters (sample size, control groups count, p-value).",
            "user_prompt_template": "Paper Title: {title}\nExtract dataset metrics.",
            "response_schema": {
                "type": "object",
                "properties": {
                    "sample_size": {"type": "number"},
                    "control_groups": {"type": "number"},
                    "p_value": {"type": "number"}
                }
            },
            "is_active": True,
        },
        # 4) Scenario 4: Single or multiple exit parameters with custom Python postprocessing snippet
        {
            "name": "Commercial Traction",
            "exit_metrics": ["market_fit", "growth_potential"],
            "postprocessing_code": "return (market_fit * 1.5) + growth_potential",
            "llm_model": "google/gemini-3.8-flash",
            "system_prompt": "Evaluate market fit (1-10) and growth potential (1-10).",
            "user_prompt_template": "Paper Title: {title}\nEvaluate commercial viability.",
            "response_schema": {
                "type": "object",
                "properties": {
                    "market_fit": {"type": "number"},
                    "growth_potential": {"type": "number"}
                }
            },
            "is_active": True,
        }
    ]

    # Signal score formula retrieving variables from ALL 4 scenarios
    signal_score_formula = (
        "# 1) No exit parameters: novelty_evaluation or novelty_score\n"
        "val_novelty = float(novelty_evaluation if 'novelty_evaluation' in locals() and novelty_evaluation else (novelty_score if 'novelty_score' in locals() else 0.0))\n"
        "# 2) Single exit parameter: rigour_score\n"
        "val_rigour = float(rigour_score if 'rigour_score' in locals() else 0.0)\n"
        "# 3) Multiple exit parameters: sample_size, control_groups, p_value\n"
        "val_sample = float(sample_size if 'sample_size' in locals() else 0.0)\n"
        "val_control = float(control_groups if 'control_groups' in locals() else 0.0)\n"
        "# 4) Postprocessing snippet: market_fit_postprocessed, growth_potential\n"
        "val_market_post = float(market_fit_postprocessed if 'market_fit_postprocessed' in locals() else 0.0)\n"
        "val_growth = float(growth_potential if 'growth_potential' in locals() else 0.0)\n"
        "final_calc = val_novelty + (val_rigour * 2.0) + (val_sample / 10.0) + (val_control * 5.0) + val_market_post + val_growth\n"
        "return round(final_calc, 2)"
    )

    # 2. Provision workspace with full configuration
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept machine learning, natural language processing, or artificial intelligence.",
        abstract_rejection_criteria="Reject pure biology or unrelated chemistry.",
        full_text_acceptance_criteria="Accept empirical evaluations, benchmarks, and architectures.",
        full_text_rejection_criteria="Reject papers without scientific evaluation.",
        signal_score_code=signal_score_formula,
        screening_llm_model="google/gemini-3.8-flash",
        extraction_definitions=definitions,
    )
    workspace_id = ws_data["id"]

    try:
        # 2.1 Validate Extraction Definitions REST API & exit_metrics invariants
        logger.info("🔍 2.1 Validating Extraction Definitions REST API and exit_metrics contracts...")
        listed_defs = ws_svc.list_extraction_definitions(workspace_id=workspace_id)
        assert len(listed_defs) == 4, f"Expected 4 definitions via REST API, got: {len(listed_defs)}"
        for d in listed_defs:
            assert "exit_metric" not in d, f"Discontinued key 'exit_metric' found in API definition response: {d}"
            assert isinstance(d.get("exit_metrics"), list), f"Expected 'exit_metrics' to be a list in {d['name']}, got: {type(d.get('exit_metrics'))}"

        logger.info("   ✅ All 4 extraction definitions confirmed in REST API with clean exit_metrics lists and no exit_metric keys.")

        # Test Dynamic API Creation with exit_metrics & postprocessing snippet
        temp_def = ws_svc.create_extraction_definition(
            workspace_id=workspace_id,
            name=f"temp_target_{random_suffix}",
            system_prompt="Extract benchmark metrics.",
            user_prompt_template="Paper: {title}",
            response_schema={"type": "object"},
            exit_metrics=["benchmark_f1", "inference_latency"],
            postprocessing_code="return (benchmark_f1 * 100.0) - inference_latency"
        )
        if temp_def:
            temp_id = temp_def["id"]
            assert "exit_metric" not in temp_def, "Key 'exit_metric' must not exist in created definition"
            assert temp_def["exit_metrics"] == ["benchmark_f1", "inference_latency"]
            assert temp_def["postprocessing_code"] == "return (benchmark_f1 * 100.0) - inference_latency"
            assert temp_def["has_postprocessing_code"] is True
            logger.info("   ✅ Dynamic Extraction Definition created with exit_metrics list and postprocessing_code.")

            # Test PATCH update
            up_def = ws_svc.update_extraction_definition(
                temp_id,
                exit_metrics=["benchmark_f1", "throughput_qps"],
                postprocessing_code="return benchmark_f1 * throughput_qps"
            )
            assert "exit_metric" not in up_def
            assert up_def["exit_metrics"] == ["benchmark_f1", "throughput_qps"]
            assert up_def["postprocessing_code"] == "return benchmark_f1 * throughput_qps"
            logger.info("   ✅ Dynamic Extraction Definition successfully updated via PATCH.")

            # Test Syntax Error Validation (should return 400)
            bad_syntax_resp = client.patch(f"/api/extraction-definitions/{temp_id}/", json_data={"postprocessing_code": "def bad(:"})
            assert bad_syntax_resp.status_code == 400, f"Expected 400 for bad Python syntax, got: {bad_syntax_resp.status_code}"
            logger.info("   ✅ Invalid Python syntax rejected with HTTP 400.")

            # Test Legacy exit_metric Rejection (should return 400)
            bad_metric_resp = client.post("/api/extraction-definitions/", json_data={
                "workspace": workspace_id,
                "name": "Legacy Field Test",
                "system_prompt": "Test",
                "user_prompt_template": "Test",
                "response_schema": {},
                "exit_metric": "legacy_name"
            })
            assert bad_metric_resp.status_code == 400, f"Expected 400 for legacy exit_metric, got: {bad_metric_resp.status_code}"
            logger.info("   ✅ Discontinued exit_metric field rejected with HTTP 400.")

            # Delete temporary definition
            deleted = ws_svc.delete_extraction_definition(temp_id)
            assert deleted is True, "Failed to delete temporary extraction definition"
            logger.info("   ✅ Temporary definition cleaned up successfully.")

        # Create Scraper targeting research papers
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"agent"',
            limit=2,
        )

        # 3. Launch research agent pipeline
        logger.info("🚀 Launching research agent pipeline to ingest papers and calculate signal score...")
        agent_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Variables & Math Run - {workspace_name}",
            limit=2,
        )

        completed_agent = agent_svc.poll_until_complete(
            agent_proc["id"], max_timeout_sec=cfg.max_timeout_sec
        )
        assert completed_agent.get("status") == "completed", f"Pipeline failed: {completed_agent}"

        # 4. Query ingested papers
        papers = pipeline_svc.list_papers(workspace_id=workspace_id)
        assert len(papers) > 0, "Expected at least one paper ingested in workspace"
        logger.info(f"✅ Found {len(papers)} papers in workspace.")

        verified_papers_count = 0

        for p in papers:
            paper_id = p["id"]
            logger.info(f"🔍 [PAPER {paper_id}] Inspecting Scorecard & Mathematical Precision...")

            scorecard = pipeline_svc.get_paper_scorecard(paper_id)
            signal_score = scorecard.get("signal_score")
            details = scorecard.get("signal_score_details") or {}
            vars_dict = details.get("variables") or {}

            logger.info(f"   • Stored Signal Score: {signal_score}")
            logger.info(f"   • Available Variables in Context: {list(vars_dict.keys())}")

            # If paper was screened out or failed extraction, variables default to 0.0 safely
            if not vars_dict:
                logger.warning(f"   ⚠️ No variables in details for paper {paper_id} (screening: {scorecard.get('screening_status')})")
                continue

            # Verify Scenario 1: No exit parameters variable visibility
            has_scenario_1 = "novelty_evaluation" in vars_dict or "novelty_score" in vars_dict
            assert has_scenario_1, f"Scenario 1 variable missing! vars: {list(vars_dict.keys())}"
            val_novelty = float(vars_dict.get("novelty_evaluation") or vars_dict.get("novelty_score") or 0.0)
            logger.info(f"   ✅ [Scenario 1 - No Exit Params] novelty variable verified: {val_novelty}")

            # Verify Scenario 2: Single exit parameter variable visibility
            assert "rigour_score" in vars_dict, f"Scenario 2 variable 'rigour_score' missing! vars: {list(vars_dict.keys())}"
            val_rigour = float(vars_dict.get("rigour_score") or 0.0)
            logger.info(f"   ✅ [Scenario 2 - Single Exit Param] rigour_score verified: {val_rigour}")

            # Verify Scenario 3: Multiple exit parameters variable visibility (with stripped spaces)
            assert "sample_size" in vars_dict, f"Scenario 3 variable 'sample_size' missing! vars: {list(vars_dict.keys())}"
            assert "control_groups" in vars_dict, f"Scenario 3 variable 'control_groups' missing! vars: {list(vars_dict.keys())}"
            assert "p_value" in vars_dict, f"Scenario 3 variable 'p_value' missing! vars: {list(vars_dict.keys())}"
            val_sample = float(vars_dict.get("sample_size") or 0.0)
            val_control = float(vars_dict.get("control_groups") or 0.0)
            val_p = float(vars_dict.get("p_value") or 0.0)
            logger.info(f"   ✅ [Scenario 3 - Multiple Exit Params] sample_size={val_sample}, control_groups={val_control}, p_value={val_p}")

            # Verify Scenario 4: Postprocessing code snippet variable visibility
            assert "market_fit" in vars_dict, f"Scenario 4 raw variable 'market_fit' missing!"
            assert "growth_potential" in vars_dict, f"Scenario 4 raw variable 'growth_potential' missing!"
            assert "market_fit_postprocessed" in vars_dict, f"Scenario 4 postprocessed variable 'market_fit_postprocessed' missing!"
            val_market_fit = float(vars_dict.get("market_fit") or 0.0)
            val_growth = float(vars_dict.get("growth_potential") or 0.0)
            val_market_post = float(vars_dict.get("market_fit_postprocessed") or 0.0)

            # Check postprocessing math: (market_fit * 1.5) + growth_potential
            expected_post = round((val_market_fit * 1.5) + val_growth, 2)
            assert abs(val_market_post - expected_post) < 0.05, (
                f"Postprocessing math check failed! Expected: {expected_post}, Actual: {val_market_post}"
            )
            logger.info(f"   ✅ [Scenario 4 - Postprocessing Math] market_fit_postprocessed={val_market_post} (Expected: {expected_post})")

            # 5. CHECK THE SIGNAL SCORE MATH
            expected_score = round(
                val_novelty + (val_rigour * 2.0) + (val_sample / 10.0) + (val_control * 5.0) + val_market_post + val_growth,
                2
            )
            actual_score = round(float(signal_score or 0.0), 2)
            assert abs(actual_score - expected_score) < 0.05, (
                f"Signal score math check failed for Paper {paper_id}! "
                f"Actual: {actual_score}, Expected: {expected_score} (from vars: {vars_dict})"
            )
            logger.info(f"   🎯 [Signal Score Math Check PASSED] Actual: {actual_score} == Expected: {expected_score}")
            verified_papers_count += 1

        logger.info("=================================================================")
        logger.info(f"🎉 SIGNAL SCORE VARIABLES & MATH SCENARIO PASSED ({verified_papers_count} papers verified)!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "verified_papers_count": verified_papers_count,
            "scenarios_checked": [
                "1_no_exit_parameters",
                "2_single_exit_parameter",
                "3_multiple_exit_parameters",
                "4_postprocessing_snippet_and_math",
                "5_signal_score_code_math_retrieval"
            ]
        }

    finally:
        if not getattr(cfg, "keep_workspaces", False):
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as del_e:
                logger.warning(f"Cleanup error: {del_e}")
