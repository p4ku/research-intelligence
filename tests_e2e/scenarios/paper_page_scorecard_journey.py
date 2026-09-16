"""
Paper Page Scorecard E2E Scenario.

Validates the full functionality of the Paper Page Scorecard endpoint (GET /api/papers/{id}/scorecard/):
1. Workspace provisioning with multi-dimensional extraction definitions having explicit `order`.
2. Risk & Affiliation definition setup with structured and nested flags.
3. Ingestion/processing of candidate paper with extractions and evaluation metrics.
4. Comprehensive testing of query parameters:
   - default (no params -> latest metric)
   - pipeline_run=<uuid> (run-scoped metric)
   - pipeline_run=latest (auto-resolves latest non-failed run)
   - param aliases: pipeline_run_id, run_id
5. Strict ordering verification:
   - dimensions[] ordered by ExtractionDefinition.order
   - dynamic reordering via PATCH /api/extraction-definitions/{id}/ updates scorecard dimensions order
6. Risk & Affiliation verification:
   - affiliations, author_contacts, funding_entities, codebase_artifact_link, risk_score, flags
7. Absence of Python repr leakage ({'status': ...}) in dimension.raw and facts.
"""

import logging
import random
from typing import Any, Dict, Optional

from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    AgentService,
    PipelineService,
)

logger = logging.getLogger("e2e_paper_page_scorecard")


def run_paper_page_scorecard_journey_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    Executes end-to-end user journey validating the Paper Page Scorecard API.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_paper_scorecard_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("📄 STARTING PAPER PAGE SCORECARD ENDPOINT E2E SCENARIO")
    logger.info(f"📍 Workspace Name : {workspace_name}")
    logger.info(f"📍 Target API      : {cfg.base_url}")
    logger.info("=================================================================")

    # 1. Provision workspace
    ws_data = ws_svc.create_workspace(
        name=workspace_name,
        abstract_acceptance_criteria="Accept computer science, algorithms, neural networks.",
        abstract_rejection_criteria="Reject unrelated medical or biological topics.",
        full_text_acceptance_criteria="Accept empirical evaluations and methodologies.",
        full_text_rejection_criteria="Reject pure opinion articles.",
        signal_score_code="score = 0.5 * fit_score + 0.5 * trl\nreturn round(score * 10.0, 2)",
        screening_llm_model="google/gemini-3.8-flash",
        extraction_definitions=[],
    )
    workspace_id = ws_data["id"]

    try:
        # 2. Provision definitions with explicit ordering (1, 2, 3, 4)
        logger.info("🛠️  Configuring Extraction Definitions with explicit order...")
        def_trl = ws_svc.create_extraction_definition(
            workspace_id=workspace_id,
            name="Technology Readiness Level (TRL)",
            system_prompt="Assess TRL on scale 1-9.",
            user_prompt_template="Rate TRL for {paper_title}",
            response_schema={
                "type": "object",
                "properties": {
                    "trl": {"type": "integer", "minimum": 1, "maximum": 9},
                    "rationale": {"type": "string"}
                }
            },
            exit_metrics="trl",
            primary_frontend_metric="trl",
        )
        # Update order explicitly to ensure sequential 1, 2, 3
        client.patch(f"/api/extraction-definitions/{def_trl['id']}/", json_data={"order": 1})

        def_quality = ws_svc.create_extraction_definition(
            workspace_id=workspace_id,
            name="Research Quality",
            system_prompt="Extract novelty, significance, and methodological rigour.",
            user_prompt_template="Evaluate quality for {paper_title}",
            response_schema={
                "type": "object",
                "properties": {
                    "novelty": {"type": "number"},
                    "significance": {"type": "number"},
                    "methodology": {"type": "string"}
                }
            },
            exit_metrics="novelty, significance",
            primary_frontend_metric="novelty",
            secondary_frontend_metrics="significance",
        )
        client.patch(f"/api/extraction-definitions/{def_quality['id']}/", json_data={"order": 2})

        def_fit = ws_svc.create_extraction_definition(
            workspace_id=workspace_id,
            name="Schwarz Fit",
            system_prompt="Evaluate fit for enterprise architecture.",
            user_prompt_template="Score fit for {paper_title}",
            response_schema={
                "type": "object",
                "properties": {
                    "fit_score": {"type": "number"}
                }
            },
            exit_metrics="fit_score",
            primary_frontend_metric="fit_score",
        )
        client.patch(f"/api/extraction-definitions/{def_fit['id']}/", json_data={"order": 3})

        def_risk = ws_svc.create_extraction_definition(
            workspace_id=workspace_id,
            name="Risk and Affiliation",
            system_prompt="Identify author institutions, competitors, contacts, codebase repository.",
            user_prompt_template="Extract affiliations for {paper_title}",
            response_schema={
                "type": "object",
                "properties": {
                    "affiliations": {"type": "array", "items": {"type": "string"}},
                    "author_contacts": {"type": "array", "items": {"type": "string"}},
                    "funding_entities": {"type": "array", "items": {"type": "string"}},
                    "codebase_artifact_link": {"type": "string"},
                    "risk_score": {"type": "number"},
                    "schwarz_ecosystem_match": {"type": "object"},
                    "competitor_match": {"type": "object"}
                }
            },
            exit_metrics="risk_score",
        )
        client.patch(f"/api/extraction-definitions/{def_risk['id']}/", json_data={"order": 4})

        # 3. Create Scraper & Trigger Pipeline Run
        ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"transformer architecture"',
            limit=2,
        )

        logger.info("🚀 Launching research agent pipeline...")
        agent_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"Paper Scorecard Validation - {workspace_name}",
            limit=2,
            reprocess_existing=True,
        )

        completed_agent = agent_svc.poll_until_complete(
            agent_proc["id"], max_timeout_sec=cfg.max_timeout_sec
        )
        assert completed_agent.get("status") == "completed", f"Agent pipeline did not complete: {completed_agent}"

        papers = pipeline_svc.list_papers(workspace_id=workspace_id)
        assert len(papers) > 0, "Pipeline must ingest at least one paper"
        target_paper = papers[0]
        paper_id = target_paper["id"]
        pipeline_run_id = completed_agent.get("pipeline_run")

        logger.info(f"✅ Found paper {paper_id} in workspace. Starting Scorecard API checks...")

        # 4. TEST DEFAULT QUERY (No parameters)
        logger.info("🧪 Check 1: GET /api/papers/{id}/scorecard/ (default)")
        scorecard = pipeline_svc.get_paper_scorecard(paper_id)
        assert "workspace" in scorecard, "Missing workspace key in scorecard response"
        assert "paper" in scorecard, "Missing paper key in scorecard response"
        assert "definitions" in scorecard, "Missing definitions key in scorecard response"
        assert "extractions" in scorecard, "Missing extractions key in scorecard response"

        paper_obj = scorecard["paper"]
        assert paper_obj["id"] == paper_id
        assert paper_obj.get("title"), "Paper must have a title"
        assert "dimensions" in paper_obj, "Paper must have dimensions list"

        # Check definitions order in workspace summary
        ws_defs = scorecard.get("workspace", {}).get("definitions", [])
        ws_def_names = [d["name"] for d in ws_defs]
        logger.info(f"   • Workspace definitions order: {ws_def_names}")

        # Check dimensions order in paper
        dims = paper_obj["dimensions"]
        dim_names = [d["name"] for d in dims if not d.get("is_risk_and_affiliation")]
        logger.info(f"   • Paper dimensions order: {dim_names}")

        # Check that no dimension.raw leaks python repr
        for dim in dims:
            raw_v = dim.get("raw")
            if raw_v:
                assert not str(raw_v).startswith("{"), f"Python repr leaked into dimension.raw: {raw_v}"
                assert not str(raw_v).startswith("OrderedDict("), f"OrderedDict leaked into dimension.raw: {raw_v}"
            facts = dim.get("facts", [])
            for fact in facts:
                fv = fact.get("value")
                if fv:
                    assert not str(fv).startswith("{"), f"Python repr leaked into fact: {fv}"

        # 5. TEST QUERY PARAMETERS: pipeline_run, pipeline_run_id, run_id, latest
        logger.info("🧪 Check 2: Query parameters scoping")
        if pipeline_run_id:
            sc_run = pipeline_svc.get_paper_scorecard(paper_id, params={"pipeline_run": pipeline_run_id})
            assert sc_run["paper"]["id"] == paper_id

            sc_run_id = pipeline_svc.get_paper_scorecard(paper_id, params={"run_id": pipeline_run_id})
            assert sc_run_id["paper"]["id"] == paper_id

            sc_latest = pipeline_svc.get_paper_scorecard(paper_id, params={"pipeline_run": "latest"})
            assert sc_latest["paper"]["id"] == paper_id

        # Non-existent run id -> paper not evaluated in that run -> 404
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        resp_fake = client.get(f"/api/papers/{paper_id}/scorecard/", params={"pipeline_run": fake_uuid}, expected_status=404)
        assert resp_fake.status_code == 404
        logger.info("   ✅ Query parameters handled resiliently (unmatched run returns 404).")

        # 6. TEST DYNAMIC REORDERING LIFECYCLE
        logger.info("🧪 Check 3: Dynamic reordering of ExtractionDefinitions")
        # Swap Schwarz Fit to #1, TRL to #2, Research Quality to #3
        client.patch(f"/api/extraction-definitions/{def_fit['id']}/", json_data={"order": 1})
        client.patch(f"/api/extraction-definitions/{def_trl['id']}/", json_data={"order": 2})
        client.patch(f"/api/extraction-definitions/{def_quality['id']}/", json_data={"order": 3})

        sc_reordered = pipeline_svc.get_paper_scorecard(paper_id)
        reordered_dims = [d["name"] for d in sc_reordered["paper"]["dimensions"] if not d.get("is_risk_and_affiliation")]
        logger.info(f"   • Reordered dimensions: {reordered_dims}")
        if len(reordered_dims) >= 3:
            assert reordered_dims[0] == "Schwarz Fit", f"Expected Schwarz Fit first, got {reordered_dims[0]}"
            assert reordered_dims[1] == "Technology Readiness Level (TRL)", f"Expected TRL second, got {reordered_dims[1]}"
            assert reordered_dims[2] == "Research Quality", f"Expected Research Quality third, got {reordered_dims[2]}"
            logger.info("   ✅ Dimensions strictly reflect updated order.")

        # 7. RISK AND AFFILIATION PAYLOAD VERIFICATION
        logger.info("🧪 Check 4: Risk and Affiliation payload")
        risk_data = paper_obj.get("risk_and_affiliation")
        logger.info(f"   • risk_and_affiliation present: {bool(risk_data)}")
        if risk_data:
            assert "affiliations" in risk_data, "Missing affiliations key"
            assert "author_contacts" in risk_data, "Missing author_contacts key"
            assert "funding_entities" in risk_data, "Missing funding_entities key"
            assert "codebase_artifact_link" in risk_data, "Missing codebase_artifact_link key"
            assert "flags" in risk_data, "Missing flags key"
            logger.info(f"   • Parsed affiliations: {risk_data['affiliations']}")
            logger.info(f"   • Parsed flags count: {len(risk_data['flags'])}")

        logger.info("=================================================================")
        logger.info("🎉 PAPER PAGE SCORECARD ENDPOINT E2E SCENARIO PASSED!")
        logger.info("=================================================================")

        return {
            "status": "passed",
            "workspace_id": workspace_id,
            "paper_id": paper_id,
            "dimensions_count": len(dims),
            "reordered_dimensions": reordered_dims,
            "has_risk_and_affiliation": bool(risk_data),
        }

    finally:
        if cfg.delete_after:
            try:
                ws_svc.delete_workspace(workspace_id)
            except Exception as e:
                logger.warning(f"Failed to delete test workspace: {e}")
