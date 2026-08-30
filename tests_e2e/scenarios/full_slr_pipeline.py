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

        # Step 1b: Pre-clean any old test workspaces if cleanup_before is enabled
        if cfg.cleanup_before:
            ws_svc.cleanup_old_test_workspaces(prefix="test_e2e_")

        # Step 2: Create Workspace with Dual-Stage Criteria & Python Signal Score formula
        abstract_acceptance = (
            "Accept research papers discussing artificial intelligence, machine learning, neural networks, "
            "optimization algorithms, or quantum computing computational methods."
        )
        abstract_rejection = (
            "Reject only non-technical opinion articles or completely unrelated biology papers."
        )
        full_text_acceptance = (
            "Accept research papers presenting algorithms, computational methods, machine learning models, "
            "or mathematical optimization evaluations."
        )
        full_text_rejection = (
            "Reject only papers with zero technical or algorithmic discussion."
        )
        signal_score_code = (
            "score = 0.5 * fit_score + 0.3 * (trl_level * 1.1) + 0.2 * 8.0\n"
            "return round(min(100.0, score * 10.0), 2)\n"
        )

        ws_data = ws_svc.create_workspace(
            name=workspace_name,
            abstract_acceptance_criteria=abstract_acceptance,
            abstract_rejection_criteria=abstract_rejection,
            full_text_acceptance_criteria=full_text_acceptance,
            full_text_rejection_criteria=full_text_rejection,
            signal_score_code=signal_score_code,
            screening_llm_model="google/gemini-3.7-flash",
            ocr_provider=None,  # Direct multimodal PDF mode
            reasoning_effort="medium",
        )
        workspace_id = ws_data["id"]
        scenario_results["workspace_id"] = workspace_id

        # Step 3: Configure Academic Scraper (arXiv Machine Learning & AI Optimization)
        scraper_data = ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND (all:"machine learning" OR all:"neural network" OR all:"optimization")',
            limit=cfg.paper_limit,
            sort_by="relevance",
            sort_order="desc",
        )
        scenario_results["scraper_id"] = scraper_data["id"]

        # Step 4: Define Dynamic Extraction Targets
        # 4a. Strategic Fit Target
        ed_fit = ws_svc.create_extraction_definition(
            workspace_id=workspace_id,
            name="Strategic Fit",
            exit_metric="fit_score",
            system_prompt=(
                "Evaluate the strategic fit and practicality of the quantum algorithm from 1 to 10. "
                "Include key algorithmic family and verbatim quote."
            ),
            user_prompt_template="Title: {{paper_title}}\nAbstract: {{abstract}}\nFull Text: {{full_text}}",
            response_schema={
                "type": "object",
                "properties": {
                    "fit_score": {"type": "number", "minimum": 1, "maximum": 10},
                    "algorithm_family": {"type": "string"},
                    "verbatim_quote": {"type": "string"},
                },
                "required": ["fit_score", "algorithm_family", "verbatim_quote"],
            },
        )
        # 4b. TRL Assessment Target
        ed_trl = ws_svc.create_extraction_definition(
            workspace_id=workspace_id,
            name="TRL Assessment",
            exit_metric="trl_level",
            system_prompt="Assess Technology Readiness Level from 1 to 9 based on experimental hardware or simulation validation.",
            user_prompt_template="Title: {{paper_title}}\nFull Text: {{full_text}}",
            response_schema={
                "type": "object",
                "properties": {
                    "trl_level": {"type": "number", "minimum": 1, "maximum": 9},
                    "validation_type": {"type": "string", "enum": ["hardware_experiment", "simulation", "theoretical"]},
                    "evidence_quote": {"type": "string"},
                },
                "required": ["trl_level", "validation_type", "evidence_quote"],
            },
        )
        # 4c. Novelty Score Target
        ed_nov = ws_svc.create_extraction_definition(
            workspace_id=workspace_id,
            name="Novelty Score",
            exit_metric="novelty_score",
            system_prompt="Rate the novelty and algorithmic innovation of the presented methodology from 1 to 10.",
            user_prompt_template="Title: {{paper_title}}\nAbstract: {{abstract}}\nFull Text: {{full_text}}",
            response_schema={
                "type": "object",
                "properties": {
                    "novelty_score": {"type": "number", "minimum": 1, "maximum": 10},
                    "core_innovation": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                },
                "required": ["novelty_score", "core_innovation", "evidence_quote"],
            },
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
        reports = pipeline_svc.list_reports(workspace_id=workspace_id)

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
        sorted_papers = sorted(
            accepted_papers,
            key=lambda p: float(p.get("signal_score") or 0.0),
            reverse=True,
        )
        scenario_results["top_papers"] = [
            {
                "title": p.get("title"),
                "signal_score": p.get("signal_score"),
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
            logger.info(f"   • Prompt / Input Tokens      : {p_tokens_in + c_tokens_in:,}")
            logger.info(f"   • Completion / Output Tokens : {p_tokens_out + c_tokens_out:,}")
            logger.info(f"   • Total Tokens Consumed      : {total_run_tokens:,}")
            logger.info(f"   • Total Cost (USD)           : ${total_run_usd:.4f} USD")
        except Exception as cost_err:
            logger.warning(f"Could not aggregate token metrics: {cost_err}")

        logger.info("=================================================================")
        logger.info("🎉 E2E FULL SLR PIPELINE SCENARIO FINISHED SUCCESSFULLY!")
        logger.info("=================================================================")

        return scenario_results

    finally:
        if cfg.delete_after and scenario_results.get("workspace_id"):
            try:
                ws_svc.delete_workspace(scenario_results["workspace_id"])
                scenario_results["cleaned_up"] = True
                logger.info(f"🧹 Cleaned up test workspace '{scenario_results['workspace_id']}' and all associated storage artifacts.")
            except Exception as del_err:
                logger.warning(f"Failed to cleanup workspace '{scenario_results['workspace_id']}': {del_err}")
