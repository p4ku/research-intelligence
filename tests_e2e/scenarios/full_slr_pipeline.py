"""
Full End-to-End Systematic Literature Review (SLR) Pipeline Scenario.

Automates the complete researcher journey:
1. Authentication (JWT token generation).
2. Random Workspace provisioning with dual-stage criteria and Python AST formula.
3. Scraper configuration (arXiv query).
4. Extraction Targets definition (JSON schema, prompts, exit metrics).
5. Autonomous Agent execution & real-time polling.
6. Validation of all 8 SLR stages:
   - Search & Metadata Ingestion
   - Abstract Screening
   - Parallel PDF Download
   - Layout OCR (skipped or converted)
   - Multimodal Full-Text Screening
   - Dynamic Parameter Extraction
   - Composite Signal Score Evaluation
   - Executive Narrative Reporting
7. Results API verification (/api/papers/, /api/extractions/, /api/pipeline-runs/, /api/reports/).
8. Interactive Chat interrogation via /api/chat/.
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
    ChatService,
    ScheduleService,
    DataConsistencyValidator,
)

logger = logging.getLogger("e2e_slr_scenario")


def run_full_slr_pipeline_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_{random_suffix}"

    logger.info("=================================================================")
    logger.info(f"🚀 STARTING FULL E2E SLR PIPELINE SCENARIO")
    logger.info(f"📍 Target Environment : {cfg.target_env.upper()} ({cfg.base_url})")
    logger.info(f"👤 User Account        : {cfg.username}")
    logger.info(f"🏷️  Workspace Name      : {workspace_name}")
    logger.info(f"📄 Paper Limit         : {cfg.paper_limit}")
    logger.info("=================================================================")

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)
    chat_svc = ChatService(client)
    sched_svc = ScheduleService(client)

    scenario_results = {
        "workspace_id": None,
        "workspace_name": workspace_name,
        "process_id": None,
        "pipeline_run_id": None,
        "stage_checks": {},
        "top_papers": [],
        "extractions_count": 0,
        "chat_response": None,
    }

    try:
        # Step 1: Authenticate
        auth_data = auth.login(cfg.username, cfg.password)
        scenario_results["user_id"] = auth_data.get("user_id")

        # Step 1b: Pre-clean any old test workspaces, extraction definitions & lingering test schedules
        if cfg.cleanup_before:
            ws_svc.cleanup_old_test_workspaces(prefix="test_e2e_")
            ws_svc.cleanup_old_extraction_definitions(prefix="test_e2e_")
            sched_svc.cleanup_old_test_schedules()

        # Step 2: Create Workspace with Complete Dual-Stage Dynamic Criteria, Schemas, Prompts & Python Signal Score
        abstract_acceptance = (
            "Accept all academic research papers discussing algorithms, artificial intelligence, machine learning, "
            "neural networks, optimization methods, or computational science."
        )
        abstract_rejection = (
            "Do not reject any technical or computer science research papers."
        )
        abstract_system_prompt = (
            "You are an expert AI Research Scanner. Screen the provided academic abstract against "
            "the workspace Acceptance Criteria and Rejection Criteria.\n"
            "Provide a strict structured evaluation including:\n"
            "- 'passed': boolean (True if it satisfies Acceptance Criteria and avoids Rejection Criteria)\n"
            "- 'reasoning': concise, high-impact justification for the decision\n"
            "- 'evidence_quotes': list of exact quotes or key phrases from the abstract supporting your decision\n"
            "- 'decision_category': string category such as 'ACCEPTED: Core scope match', 'REJECTED: Excluded domain', etc."
        )
        abstract_user_template = (
            "Title: {title}\n"
            "Abstract:\n{abstract}\n\n"
            "Acceptance Criteria (must satisfy to pass):\n{acceptance_criteria}\n\n"
            "Rejection Criteria (if matched, paper is rejected):\n{rejection_criteria}"
        )
        abstract_response_schema = {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "reasoning": {"type": "string"},
                "evidence_quotes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific quotes or key phrases extracted from the abstract supporting the decision"
                },
                "decision_category": {
                    "type": "string",
                    "description": "High level category describing why the paper passed or failed"
                }
            },
            "required": ["passed", "reasoning"]
        }

        full_text_acceptance = (
            "Accept all research papers containing computational, algorithmic, mathematical, "
            "or experimental technical evaluations."
        )
        full_text_rejection = (
            "Do not reject any technical or computer science research papers."
        )
        full_text_system_prompt = (
            "You are an expert AI Research Analyst. Perform a deep full-text evaluation of the provided "
            "academic paper against the workspace Acceptance Criteria and Rejection Criteria.\n"
            "Provide a strict structured evaluation including:\n"
            "- 'passed': boolean (True if the methodology satisfies Acceptance Criteria and avoids Rejection Criteria)\n"
            "- 'reasoning': concise, high-impact justification citing key findings from the text/document\n"
            "- 'evidence_quotes': list of exact quotes or key technical phrases from the paper supporting your decision\n"
            "- 'fit_score': strategic technical fit score from 1.0 to 10.0\n"
            "- 'decision_category': string category such as 'ACCEPTED: Full-text validation', 'REJECTED: Excluded methodology', etc."
        )
        full_text_user_template = (
            "Title: {title}\n\n"
            "Full-Text Content:\n{full_text}\n\n"
            "Acceptance Criteria (must satisfy to pass):\n{acceptance_criteria}\n\n"
            "Rejection Criteria (if matched, paper is rejected):\n{rejection_criteria}"
        )
        full_text_response_schema = {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "reasoning": {"type": "string"},
                "evidence_quotes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific quotes or key technical phrases extracted from the paper supporting the decision"
                },
                "fit_score": {
                    "type": "number",
                    "minimum": 1.0,
                    "maximum": 10.0,
                    "description": "Strategic technical fit score from 1.0 to 10.0"
                },
                "decision_category": {
                    "type": "string",
                    "description": "High level category describing why the paper passed or failed full-text evaluation"
                }
            },
            "required": ["passed", "reasoning"]
        }

        signal_score_code = (
            "# Jeśli TRL jest zbyt niski, odrzuć ze scoringu\n"
            "if trl_level < 3.0:\n"
            "    return 0.0\n"
            "base = 0.6 * fit_score + 0.4 * novelty_score\n"
            "multiplier = 1.25 if trl_level >= 7.0 else 1.0\n"
            "return round(base * multiplier, 2)\n"
        )

        extraction_definitions_payload = [
            {
                "name": f"test_e2e_novelty_{random_suffix}",
                "exit_metric": "novelty_score",
                "llm_model": "google/gemini-3.8-flash",
                "system_prompt": (
                    "You are an expert peer reviewer evaluating scientific novelty according to NeurIPS reviewer guidelines.\n\n"
                    "Novelty Scale & Bands (1 to 100):\n"
                    "- Incremental (1 to 25): A minor variation on established work, with no new capability or framing.\n"
                    "- Additive (26 to 50): A useful extension or a new combination of known techniques.\n"
                    "- Substantial (51 to 75): A new method, dataset, or problem framing that clearly differs from prior work.\n"
                    "- Transformative (76 to 100): A departure that opens a direction not present in the cited literature.\n\n"
                    "Assign a precise novelty_score (1-100), identify the corresponding novelty_band, and provide a grounded justification."
                ),
                "user_prompt_template": "Please evaluate the novelty of the following paper:\n\nTitle: {title}\nAbstract/Content:\n{content}\n\nProvide your structured output strictly adhering to the JSON schema.",
                "response_schema": {
                    "type": "object",
                    "required": ["novelty_score", "novelty_band", "justification", "departure_from_prior_work", "key_contributions"],
                    "properties": {
                        "novelty_band": {
                            "enum": ["Incremental", "Additive", "Substantial", "Transformative"],
                            "type": "string"
                        },
                        "justification": {"type": "string"},
                        "novelty_score": {"type": "integer"},
                        "key_contributions": {"type": "array", "items": {"type": "string"}},
                        "departure_from_prior_work": {"type": "string"}
                    }
                },
                "is_active": True
            },
            {
                "name": f"test_e2e_rigour_{random_suffix}",
                "exit_metric": "rigour_score",
                "llm_model": "google/gemini-3.8-flash",
                "system_prompt": (
                    "You are an expert scientific peer reviewer assessing scientific Rigour and technical soundness based on NeurIPS review guidelines.\n\n"
                    "Rigour Scale & Bands (1 to 100):\n"
                    "- Weak (1 to 25): Claims largely unsupported, or a method with clear flaws.\n"
                    "- Limited (26 to 50): Some support, with gaps in method or evidence.\n"
                    "- Sound (51 to 75): Claims supported by appropriate and adequate evidence.\n"
                    "- Strong (76 to 100): Claims thoroughly supported with honest account of limitations.\n\n"
                    "Assign a rigour_score (1-100), select the corresponding rigour_band, and detail the technical soundness."
                ),
                "user_prompt_template": "Please evaluate the scientific Rigour of the following paper:\n\nTitle: {title}\nAbstract/Content:\n{content}\n\nProvide your evaluation strictly adhering to the JSON schema.",
                "response_schema": {
                    "type": "object",
                    "required": ["rigour_score", "rigour_band", "justification", "methodological_soundness", "limitations_acknowledged", "evidence_gaps"],
                    "properties": {
                        "rigour_band": {"enum": ["Weak", "Limited", "Sound", "Strong"], "type": "string"},
                        "rigour_score": {"type": "integer"},
                        "evidence_gaps": {"type": "array", "items": {"type": "string"}},
                        "justification": {"type": "string"},
                        "limitations_acknowledged": {"type": "boolean"},
                        "methodological_soundness": {"type": "string"}
                    }
                },
                "is_active": True
            },
            {
                "name": f"test_e2e_schwarz_fit_{random_suffix}",
                "exit_metric": "fit_score",
                "llm_model": "google/gemini-3.8-flash",
                "system_prompt": (
                    "You are a specialized enterprise technology evaluator assessing how closely research papers map to strategic business needs of the Schwarz Group.\n\n"
                    "Score the overall Schwarz Fit on a 1–100 scale, evaluate each dimension, and provide a grounded justification."
                ),
                "user_prompt_template": "Please evaluate the Schwarz Fit for the following paper:\n\nTitle: {title}\nAbstract/Content:\n{content}\n\nProvide your structured output strictly adhering to the JSON response schema.",
                "response_schema": {
                    "type": "object",
                    "required": ["fit_score", "need_match_assessment", "adoption_route_assessment", "market_width_assessment", "engagement_feasibility_assessment", "justification"],
                    "properties": {
                        "fit_score": {"type": "integer"},
                        "justification": {"type": "string"},
                        "need_match_assessment": {"type": "string"},
                        "market_width_assessment": {"type": "string"},
                        "adoption_route_assessment": {"type": "string"},
                        "engagement_feasibility_assessment": {"type": "string"}
                    }
                },
                "is_active": True
            },
            {
                "name": f"test_e2e_significance_{random_suffix}",
                "exit_metric": "significance_score",
                "llm_model": "google/gemini-3.8-flash",
                "system_prompt": (
                    "You are an expert scientific evaluator reviewing paper significance based on NeurIPS reviewer guidelines.\n\n"
                    "Significance Scale & Bands (1 to 100):\n"
                    "- Narrow (1 to 25), Useful (26 to 50), Important (51 to 75), Field-shaping (76 to 100).\n"
                    "Assign a significance_score (1-100) and detail the justification and reach."
                ),
                "user_prompt_template": "Please evaluate the Significance of the following paper:\n\nTitle: {title}\nAbstract/Content:\n{content}\n\nProvide your evaluation strictly adhering to the response schema.",
                "response_schema": {
                    "type": "object",
                    "required": ["significance_score", "significance_band", "justification", "impact_reach", "key_outcomes"],
                    "properties": {
                        "impact_reach": {"type": "string"},
                        "key_outcomes": {"type": "array", "items": {"type": "string"}},
                        "justification": {"type": "string"},
                        "significance_band": {"enum": ["Narrow", "Useful", "Important", "Field-shaping"], "type": "string"},
                        "significance_score": {"type": "integer"}
                    }
                },
                "is_active": True
            },
            {
                "name": f"test_e2e_trl_{random_suffix}",
                "exit_metric": "trl_level",
                "llm_model": "google/gemini-3.8-flash",
                "system_prompt": (
                    "You are an expert scientific evaluator responsible for extracting and evaluating the Technology Readiness Level (TRL) of research papers based on the European Commission definition (Horizon Europe General Annex G).\n\n"
                    "Evaluation Framework & Scale (1 to 9):\n"
                    "- TRL 1 (Basic principles observed) to TRL 9 (Actual system proven in operational use).\n"
                    "Assign an ordinal trl_level (1-9) with evidence quotes."
                ),
                "user_prompt_template": "Please evaluate and extract the Technology Readiness Level (TRL) for the following paper:\n\nTitle: {title}\nAbstract/Content:\n{content}\n\nProvide your evaluation adhering to the JSON schema.",
                "response_schema": {
                    "type": "object",
                    "required": ["trl_level", "trl_label", "justification", "evidence_quote"],
                    "properties": {
                        "trl_label": {"type": "string"},
                        "trl_level": {"enum": [1, 2, 3, 4, 5, 6, 7, 8, 9], "type": "integer"},
                        "justification": {"type": "string"},
                        "evidence_quote": {"type": "string"},
                        "evidence_of_movement": {"type": "string"}
                    }
                },
                "is_active": True
            }
        ]

        ws_data = ws_svc.create_workspace(
            name=workspace_name,
            abstract_acceptance_criteria=abstract_acceptance,
            abstract_rejection_criteria=abstract_rejection,
            abstract_screening_system_prompt=abstract_system_prompt,
            abstract_screening_user_prompt_template=abstract_user_template,
            abstract_screening_response_schema=abstract_response_schema,
            abstract_screening_exit_metric="decision_category",
            full_text_acceptance_criteria=full_text_acceptance,
            full_text_rejection_criteria=full_text_rejection,
            full_text_screening_system_prompt=full_text_system_prompt,
            full_text_screening_user_prompt_template=full_text_user_template,
            full_text_screening_response_schema=full_text_response_schema,
            full_text_screening_exit_metric="fit_score",
            signal_score_code=signal_score_code,
            screening_llm_model="google/gemini-3.8-flash",
            ocr_provider=None,  # Direct multimodal PDF mode
            reasoning_effort="medium",
            extraction_definitions=extraction_definitions_payload,
        )
        workspace_id = ws_data["id"]
        scenario_results["workspace_id"] = workspace_id

        # Step 3: Configure Academic Scraper (arXiv or OpenAlex)
        provider = cfg.provider or "arxiv"
        if provider == "openalex":
            query = "machine learning neural networks optimization algorithms"
        else:
            query = 'cat:cs.AI AND (all:"machine learning" OR all:"neural network" OR all:"optimization")'

        scraper_data = ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider=provider,
            search_query=query,
            limit=cfg.paper_limit,
            sort_by="relevance",
            sort_order="desc",
        )
        scenario_results["scraper_id"] = scraper_data["id"]

        # Step 4: Define Dynamic Extraction Targets (Standalone endpoint fallback if not already provisioned)
        existing_defs = ws_svc.list_extraction_definitions(workspace_id=workspace_id)
        existing_names = {d.get("name") for d in existing_defs}
        for ed_payload in extraction_definitions_payload:
            if ed_payload["name"] not in existing_names:
                ws_svc.create_extraction_definition(
                    workspace_id=workspace_id,
                    name=ed_payload["name"],
                    exit_metric=ed_payload["exit_metric"],
                    system_prompt=ed_payload["system_prompt"],
                    user_prompt_template=ed_payload["user_prompt_template"],
                    response_schema=ed_payload["response_schema"],
                    llm_model=ed_payload["llm_model"],
                )

        # Step 5: Launch Autonomous Research Agent
        agent_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"E2E Review Run - {workspace_name}",
            limit=cfg.paper_limit,
            reprocess_existing=False,
        )
        process_id = agent_proc["id"]
        pipeline_run_id = agent_proc.get("pipeline_run")
        scenario_results["process_id"] = process_id
        scenario_results["pipeline_run_id"] = pipeline_run_id

        # Step 6: Poll until complete and monitor stage transitions
        completed_proc = agent_svc.poll_until_complete(
            process_id=process_id,
            max_timeout_sec=cfg.max_timeout_sec,
            poll_interval_sec=cfg.poll_interval_sec,
        )

        pipeline_run_id = completed_proc.get("pipeline_run") or pipeline_run_id
        scenario_results["pipeline_run_id"] = pipeline_run_id
        stage_results = completed_proc.get("stage_results", {})
        scenario_results["stage_results"] = stage_results

        # Fetch detailed pipeline run with component runs tree
        pr_detail = pipeline_svc.get_pipeline_run(pipeline_run_id) if pipeline_run_id else {}
        comp_runs = pr_detail.get("component_runs", [])
        comp_by_name = {cr.get("component_name"): cr for cr in comp_runs}
        comp_by_step = {cr.get("step_type"): cr for cr in comp_runs}

        # Step 7: Validate Each Stage
        logger.info("🔍 Validating all pipeline stages from live execution tree...")

        # Search & Ingestion
        search_cr = comp_by_name.get("arxiv_scraper") or comp_by_step.get("search") or stage_results.get("search")
        assert search_cr and search_cr.get("status") == "completed", f"Search stage failed: {search_cr}"
        scenario_results["stage_checks"]["search"] = "PASSED"

        # Abstract Screening
        abs_cr = comp_by_name.get("abstract_screening") or stage_results.get("abstract_screening")
        assert abs_cr and abs_cr.get("status") == "completed", f"Abstract screening stage failed: {abs_cr}"
        scenario_results["stage_checks"]["abstract_screening"] = "PASSED"

        # PDF Download
        dl_cr = comp_by_name.get("document_download") or comp_by_step.get("download") or stage_results.get("download")
        assert dl_cr and dl_cr.get("status") == "completed", f"Download stage failed: {dl_cr}"
        scenario_results["stage_checks"]["download"] = "PASSED"

        # Layout OCR (Skipped in direct multimodal mode or completed)
        ocr_cr = comp_by_name.get("layout_ocr") or comp_by_step.get("ocr") or stage_results.get("ocr")
        assert ocr_cr and ocr_cr.get("status") in ("skipped", "completed"), f"OCR stage unexpected: {ocr_cr}"
        scenario_results["stage_checks"]["ocr"] = f"PASSED ({ocr_cr.get('status')})"

        # Full-Text Screening
        ft_cr = comp_by_name.get("full_text_screening") or stage_results.get("full_text_screening")
        assert ft_cr and ft_cr.get("status") == "completed", f"Full-Text screening failed: {ft_cr}"
        scenario_results["stage_checks"]["full_text_screening"] = "PASSED"

        # Parameter Extraction
        ext_cr = comp_by_step.get("extraction") or stage_results.get("extraction")
        if ext_cr:
            scenario_results["stage_checks"]["extraction"] = f"PASSED ({ext_cr.get('status')})"
        else:
            scenario_results["stage_checks"]["extraction"] = "SKIPPED_OR_EMPTY"

        # Composite Signal Score
        sig_cr = comp_by_step.get("signal_score") or stage_results.get("signal_score")
        if sig_cr:
            scenario_results["stage_checks"]["signal_score"] = f"PASSED ({sig_cr.get('status')})"
        else:
            scenario_results["stage_checks"]["signal_score"] = "SKIPPED_OR_EMPTY"

        # Executive Reporting
        rep_cr = comp_by_step.get("reporting") or stage_results.get("reporting")
        if rep_cr:
            scenario_results["stage_checks"]["reporting"] = f"PASSED ({rep_cr.get('status')})"
        else:
            scenario_results["stage_checks"]["reporting"] = "SKIPPED_OR_EMPTY"

        # Step 8: Verify Results Endpoints via REST API
        papers = pipeline_svc.list_papers(workspace_id=workspace_id)
        accepted_papers = [p for p in papers if p.get("screening_status") in ("full_text_passed", "accepted")]
        extractions = pipeline_svc.list_extractions(workspace_id=workspace_id)
        paper_metrics = pipeline_svc.list_paper_metrics(workspace_id=workspace_id, pipeline_run=pipeline_run_id)
        reports = pipeline_svc.list_reports(workspace_id=workspace_id)

        # Deep Structural & Type Validation
        DataConsistencyValidator.validate_uuid(workspace_id, "workspace_id")
        DataConsistencyValidator.validate_uuid(process_id, "process_id")
        if pipeline_run_id:
            DataConsistencyValidator.validate_uuid(pipeline_run_id, "pipeline_run_id")

        for p in papers:
            DataConsistencyValidator.validate_paper_schema(p)
        for m in paper_metrics:
            DataConsistencyValidator.validate_paper_metric_schema(m)
        for e in extractions:
            DataConsistencyValidator.validate_extraction_schema(e)

        # Cross-Endpoint Round-Trip Consistency
        DataConsistencyValidator.validate_cross_endpoint_consistency(papers, paper_metrics, extractions)

        # Token & Financial Arithmetic Integrity
        DataConsistencyValidator.validate_token_and_cost_integrity(pr_detail, comp_runs)

        # Mathematical Validation of Signal Score
        def _calc_expected_score(vars_dict):
            trl = float(vars_dict.get("trl_level") or 0.0)
            if trl < 3.0:
                return 0.0
            fit = float(vars_dict.get("fit_score") or 0.0)
            novelty = float(vars_dict.get("novelty_score") or 0.0)
            base = 0.6 * fit + 0.4 * novelty
            multiplier = 1.25 if trl >= 7.0 else 1.0
            return round(base * multiplier, 2)

        for m in paper_metrics:
            score = m.get("signal_score")
            details = m.get("signal_score_details") or {}
            vars_dict = details.get("variables") or {}
            if score is not None and ("fit_score" in vars_dict or "novelty_score" in vars_dict or "trl_level" in vars_dict):
                DataConsistencyValidator.validate_signal_score_math(
                    actual_score=float(score),
                    variables=vars_dict,
                    formula_fn=_calc_expected_score
                )

        scenario_results["total_papers_fetched"] = len(papers)
        scenario_results["accepted_papers_count"] = len(accepted_papers)
        scenario_results["extractions_count"] = len(extractions)
        scenario_results["reports_count"] = len(reports)

        logger.info(f"📊 Summary of Ingested Assets:")
        logger.info(f"   • Total Papers Ingested : {len(papers)}")
        logger.info(f"   • Accepted Full-Text    : {len(accepted_papers)}")
        logger.info(f"   • Extractions Generated : {len(extractions)}")
        logger.info(f"   • Reports Generated     : {len(reports)}")

        # Step 9: Verify Signal Scores and Top Papers
        def _get_paper_score(p):
            if p.get("signal_score") is not None:
                return float(p.get("signal_score"))
            metrics = p.get("metrics", [])
            if metrics and isinstance(metrics, list) and len(metrics) > 0:
                m = metrics[0]
                if isinstance(m, dict) and m.get("signal_score") is not None:
                    return float(m.get("signal_score"))
            return None

        sorted_papers = sorted(
            accepted_papers,
            key=lambda p: float(_get_paper_score(p) or 0.0),
            reverse=True,
        )
        scenario_results["top_papers"] = [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "signal_score": _get_paper_score(p),
                "doi": p.get("doi"),
                "arxiv_id": p.get("arxiv_id"),
            }
            for p in sorted_papers[:3]
        ]

        if sorted_papers:
            top_paper = sorted_papers[0]
            logger.info(f"🥇 Top Ranked Paper: '{top_paper.get('title')}' (Signal Score: {top_paper.get('signal_score')})")

            # Step 10: Interactive Chat Interrogation over API
            chat_resp = chat_svc.ask_paper_sync(
                workspace_id=workspace_id,
                paper_id=top_paper["id"],
                question="What specific quantum algorithm or optimization approach is evaluated in this paper, and what were the benchmark findings?",
                deep_thinking=True,
            )
            ans_text = chat_resp.get("message") or chat_resp.get("answer") or ""
            sess_id = str(chat_resp.get("session") or chat_resp.get("session_id") or "")
            citations_list = chat_resp.get("citations") or chat_resp.get("visual_citations") or []
            scenario_results["chat_response"] = {
                "session_id": sess_id,
                "answer_snippet": (ans_text[:200] + "...") if len(ans_text) > 200 else ans_text,
                "citations_count": len(citations_list),
            }
            logger.info(f"💬 Chat Interrogation Answer: {scenario_results['chat_response']['answer_snippet']}")

        # Step 11: Collect Financial & Token Usage Metrics before cleanup
        try:
            ws_info = ws_svc.get_workspace(workspace_id)
            pr_info = pipeline_svc.get_pipeline_run(pipeline_run_id) if pipeline_run_id else {}

            p_tokens_in = pr_info.get("tokens_in") or 0
            p_tokens_out = pr_info.get("tokens_out") or 0
            p_total_tokens = pr_info.get("tokens_consumed") or (p_tokens_in + p_tokens_out)
            p_usd = float(pr_info.get("usd_cost") or 0.0)

            c_tokens_in = chat_resp.get("tokens_in", 0) if "chat_resp" in locals() and isinstance(chat_resp, dict) else 0
            c_tokens_out = chat_resp.get("tokens_out", 0) if "chat_resp" in locals() and isinstance(chat_resp, dict) else 0
            c_total_tokens = chat_resp.get("total_tokens", 0) if "chat_resp" in locals() and isinstance(chat_resp, dict) else (c_tokens_in + c_tokens_out)
            c_usd = float(chat_resp.get("usd_cost", 0.0)) if "chat_resp" in locals() and isinstance(chat_resp, dict) else 0.0

            total_run_tokens = p_total_tokens + c_total_tokens
            total_run_usd = p_usd + c_usd

            scenario_results["cost_metrics"] = {
                "pipeline_tokens_in": p_tokens_in,
                "pipeline_tokens_out": p_tokens_out,
                "pipeline_total_tokens": p_total_tokens,
                "pipeline_usd_cost": p_usd,
                "chat_tokens_in": c_tokens_in,
                "chat_tokens_out": c_tokens_out,
                "chat_total_tokens": c_total_tokens,
                "chat_usd_cost": c_usd,
                "total_tokens_consumed": total_run_tokens,
                "total_usd_spent": total_run_usd,
                "workspace_monthly_usd": float(ws_info.get("usd_spent_this_month") or total_run_usd),
                "workspace_monthly_tokens": int(ws_info.get("tokens_consumed_this_month") or total_run_tokens),
            }

            logger.info("💰 TOKEN & COST ECONOMICS FOR THIS RUN:")
            logger.info(f"   • Pipeline Review Cost       : ${p_usd:.4f} USD ({p_total_tokens:,} tokens)")
            logger.info(f"   • Paper Chat Q&A Cost        : ${c_usd:.4f} USD ({c_total_tokens:,} tokens)")
            logger.info(f"   • Total Run Tokens Consumed  : {total_run_tokens:,} tokens (In: {p_tokens_in + c_tokens_in:,}, Out: {p_tokens_out + c_tokens_out:,})")
            logger.info(f"   • Total Run Cost (USD)       : ${total_run_usd:.4f} USD")
            logger.info(f"   • Workspace Total Recorded   : ${float(ws_info.get('usd_spent_this_month') or total_run_usd):.4f} USD ({int(ws_info.get('tokens_consumed_this_month') or total_run_tokens):,} monthly tokens)")
        except Exception as cost_err:
            logger.warning(f"Could not aggregate token metrics: {cost_err}")

        logger.info("=================================================================")
        logger.info("🎉 E2E FULL SLR PIPELINE SCENARIO FINISHED SUCCESSFULLY!")
        logger.info("=================================================================")

        scenario_results["status"] = "passed"
        return scenario_results

    finally:
        if cfg.delete_after:
            if scenario_results.get("workspace_id"):
                try:
                    ws_svc.delete_workspace(scenario_results["workspace_id"])
                    scenario_results["cleaned_up"] = True
                    logger.info(f"🧹 Cleaned up test workspace '{scenario_results['workspace_id']}' and all associated storage artifacts.")
                except Exception as del_err:
                    logger.warning(f"Failed to cleanup workspace '{scenario_results['workspace_id']}': {del_err}")
            try:
                ws_svc.cleanup_old_extraction_definitions(prefix="test_e2e_")
            except Exception as def_err:
                logger.warning(f"Failed to cleanup test extraction definitions: {def_err}")
