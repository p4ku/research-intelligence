"""
Full SLR Review Gates & Checkpoints E2E Scenario.

Tests the complete Systematic Literature Review (SLR) human-in-the-loop lifecycle:
1. Workspace provisioning with SLR Policy Engine:
   - Checkpoint gate mode: 'two_stage_split' (Abstract Gate + Full-Text Gate)
   - Enable extraction gate: True (Parameter Extraction Gate)
   - Quorum size: 1 (fast-track) or 2 (blind dual-review)
   - Sampling mode: 'uncertainty_stratified' (100% borderline + controls)
2. Scraper ingestion (arXiv or OpenAlex query) & Extraction Targets definition.
3. Pipeline run launch -> Ingestion & Abstract Screening execution.
4. GATE 1 (Abstract Screening Checkpoint):
   - Pipeline pauses with status 'paused' and current_stage 'awaiting_abstract_screening_audit'.
   - Audit cohort is discovered in reviewer's queue (/api/slr/cohorts/my-queue/).
   - Auditor votes on sampled papers (Agree with AI or Override).
   - Cohort completes -> pipeline automatically wakes up and resumes!
5. GATE 2 (Full-Text Screening Checkpoint):
   - Pipeline downloads PDFs, performs multimodal full-text screening.
   - Pipeline pauses at 'awaiting_full_text_screening_audit'.
   - Full-text cohort is verified, papers reviewed with verbatim evidence citations.
   - Cohort completes -> pipeline automatically resumes!
6. GATE 3 (Parameter Extraction Audit Gate):
   - Pipeline extracts structured parameters.
   - Pipeline pauses at 'awaiting_parameter_extraction_audit'.
   - Auditor audits parameter extractions (verify/modify/reject).
   - Cohort completes -> pipeline resumes!
7. Final Pipeline Completion & SLR Reporting Verification:
   - Pipeline finishes with status 'completed'.
   - Verifies PRISMA 2020 Flow Diagram metrics (/api/slr/runs/{id}/prisma/).
   - Verifies Cochrane RoB 2 / ROBINS-I methodological appraisals (/api/slr/runs/{id}/rob/).
"""

import logging
import os
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
    SLRService,
    DataConsistencyValidator,
)

logger = logging.getLogger("e2e_slr_gates")


def wait_for_pipeline_status(
    pipeline_svc: PipelineService,
    pipeline_run_id: str,
    target_status: str,
    expected_stage_substring: Optional[str] = None,
    timeout_seconds: int = 420,
    poll_interval: float = 3.0,
) -> Dict[str, Any]:
    """Polls pipeline run until target status (e.g. 'paused', 'completed') is reached."""
    t0 = time.time()
    last_status = None
    last_stage = None

    while time.time() - t0 < timeout_seconds:
        run_data = pipeline_svc.get_pipeline_run(pipeline_run_id)
        last_status = run_data.get("status")
        last_stage = run_data.get("current_stage")

        if last_status == target_status:
            if expected_stage_substring:
                if expected_stage_substring in (last_stage or ""):
                    return run_data
            else:
                return run_data

        if target_status != "failed" and last_status in ("failed", "aborted"):
            raise RuntimeError(
                f"Pipeline run {pipeline_run_id} unexpectedly terminated with status '{last_status}' "
                f"at stage '{last_stage}'. Message: {run_data.get('status_message')}"
            )

        time.sleep(poll_interval)

    raise TimeoutError(
        f"Timed out after {timeout_seconds}s waiting for pipeline run {pipeline_run_id} to reach "
        f"status='{target_status}' (stage matching '{expected_stage_substring}'). "
        f"Last status='{last_status}', stage='{last_stage}'"
    )


def run_slr_review_gates_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    workspace_name = f"test_e2e_slr_gates_{random_suffix}"

    logger.info("=================================================================")
    logger.info("🔬 STARTING FULL SLR REVIEW GATES & CHECKPOINTS E2E SCENARIO")
    logger.info(f"📍 Target Environment : {cfg.target_env.upper()} ({cfg.base_url})")
    logger.info(f"👤 Primary Reviewer    : {cfg.username}")
    logger.info(f"🏷️  Workspace Name      : {workspace_name}")
    logger.info("=================================================================")

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    ws_svc = WorkspaceService(client)
    agent_svc = AgentService(client)
    pipeline_svc = PipelineService(client)
    slr_svc = SLRService(client)

    scenario_results = {
        "workspace_id": None,
        "workspace_name": workspace_name,
        "pipeline_run_id": None,
        "gate_1_abstract": {},
        "gate_2_full_text": {},
        "gate_3_extraction": {},
        "prisma_metrics": None,
        "rob_assessments_count": 0,
        "status": "IN_PROGRESS",
    }

    test_reviewers = ["reviewer_alice", "reviewer_bob"]
    arbiter_auth = None

    try:
        # Step 1: Authenticate Multi-Reviewer Team & Senior Arbiter
        r1_name = cfg.username
        auth_data = auth.login(r1_name, cfg.password)
        scenario_results["user_id"] = auth_data.get("user_id")

        # Senior Arbiter (for resolving reviewer conflicts/disputes)
        arbiter_client = APIClient(cfg.base_url)
        arbiter_auth = AuthService(arbiter_client)
        arbiter_name = os.getenv("ADMIN_USERNAME", "admin")
        arbiter_pass = os.getenv("ADMIN_PASSWORD", "schwarz123!")
        arbiter_auth.login(arbiter_name, arbiter_pass)
        arbiter_slr_svc = SLRService(arbiter_client)

        # Ensure multi-reviewer team accounts exist (self-bootstrapping)
        r2_name = "reviewer_alice"
        r3_name = "reviewer_bob"
        r_default_pass = "Password123!#"
        test_reviewers = [r2_name, r3_name]

        if cfg.cleanup_before:
            ws_svc.cleanup_old_test_workspaces(prefix="test_e2e_slr_gates_")
            logger.info("🧹 Purging any lingering test reviewer accounts from previous runs...")
            for rev_user in test_reviewers:
                arbiter_auth.delete_user(rev_user)

        # Freshly bootstrap Reviewer 2 & Reviewer 3 accounts
        arbiter_auth.create_user_if_missing(r2_name, r_default_pass, "alice@example.com")
        arbiter_auth.create_user_if_missing(r3_name, r_default_pass, "bob@example.com")

        # Authenticate Reviewer 2 & Reviewer 3
        r2_client = APIClient(cfg.base_url)
        r2_auth = AuthService(r2_client)
        r2_auth.login(r2_name, r_default_pass)
        r2_slr_svc = SLRService(r2_client)

        r3_client = APIClient(cfg.base_url)
        r3_auth = AuthService(r3_client)
        r3_auth.login(r3_name, r_default_pass)
        r3_slr_svc = SLRService(r3_client)

        logger.info(f"👥 Reviewer Team Active: R1='{r1_name}', R2='{r2_name}', R3='{r3_name}', Arbiter='{arbiter_name}'")

        # Step 2: Create Workspace with 100% Complete Production SLR Configuration
        logger.info("\n🏛️ Step 1: Provisioning SLR Workspace with full production configuration (prompts, schemas, exit metrics, signal score, extractions)...")
        abstract_acceptance = (
            "Accept all peer-reviewed research papers presenting computational methods, deep learning, "
            "optimization algorithms, or artificial intelligence architectures."
        )
        abstract_rejection = "Reject non-scientific opinion articles and non-technical announcements."
        full_text_acceptance = "Accept papers with empirical evaluations, benchmarks, or mathematical derivations."
        full_text_rejection = "Reject papers with zero empirical metrics or absent methodology."

        abstract_system_prompt = (
            "You are an expert AI Research Reviewer. Screen the provided academic abstract against "
            "the workspace Acceptance Criteria and Rejection Criteria with publication-grade rigor. "
            "Evaluate methodological relevance, algorithmic soundness, and domain scope. "
            "Output strictly valid JSON conforming to the response schema."
        )
        abstract_user_template = (
            "<UNTRUSTED_DOCUMENT_CONTENT>\n"
            "Title: {title}\n"
            "Abstract:\n{abstract}\n"
            "</UNTRUSTED_DOCUMENT_CONTENT>\n\n"
            "Acceptance Criteria (must satisfy):\n{acceptance_criteria}\n\n"
            "Rejection Criteria (if matched, exclude):\n{rejection_criteria}"
        )
        abstract_schema = {
            "type": "object",
            "required": ["passed", "reasoning", "evidence_quotes", "decision_category", "fit_score"],
            "properties": {
                "passed": {"type": "boolean", "description": "Whether the paper satisfies inclusion criteria."},
                "reasoning": {"type": "string", "description": "Concise justification for abstract screening decision."},
                "evidence_quotes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Direct quotes from abstract supporting the decision.",
                },
                "decision_category": {"type": "string", "description": "Classification category (e.g. Core Architecture, Excluded Domain)."},
                "fit_score": {"type": "number", "minimum": 0, "maximum": 10, "description": "Relevance fit score from 0.0 to 10.0."},
            },
        }

        full_text_system_prompt = (
            "You are a Senior Principal AI Researcher and Systematic Reviewer. Conduct a comprehensive full-text "
            "appraisal of the provided paper against the defined criteria. Scrutinize the mathematical derivations, "
            "empirical baselines, experimental convergence, and statistical significance."
        )
        full_text_user_template = (
            "<UNTRUSTED_DOCUMENT_CONTENT>\n"
            "Title: {title}\n\n"
            "Full-Text Content:\n{full_text}\n"
            "</UNTRUSTED_DOCUMENT_CONTENT>\n\n"
            "Acceptance Criteria:\n{acceptance_criteria}\n\n"
            "Rejection Criteria:\n{rejection_criteria}"
        )
        full_text_schema = {
            "type": "object",
            "required": ["passed", "reasoning", "evidence_quotes", "decision_category", "novelty_score"],
            "properties": {
                "passed": {"type": "boolean", "description": "Whether full text satisfies inclusion criteria."},
                "reasoning": {"type": "string", "description": "Detailed appraisal justification citing sections and findings."},
                "evidence_quotes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Technical quotes or key phrases extracted from full text.",
                },
                "decision_category": {"type": "string", "description": "Decision category label (e.g. Benchmark Verified, Missing Baselines)."},
                "novelty_score": {"type": "number", "minimum": 0, "maximum": 10, "description": "Novelty and quality score from 0.0 to 10.0."},
            },
        }

        signal_score_formula = (
            "# Composite Production Signal Score Formula (AST Sandboxed Python 3)\n"
            "# Signals available from extraction definitions & screening exit metrics:\n"
            "# fit_score, novelty_score, accuracy_pct, latency_ms, innovation_score, trl_level\n"
            "fit = float(fit_score) if fit_score else 8.0\n"
            "nov = float(novelty_score) if novelty_score else 7.5\n"
            "acc = float(accuracy_pct) if accuracy_pct else 92.0\n"
            "inv = float(innovation_score) if innovation_score else 7.0\n\n"
            "# Normalize accuracy percentage to 0.0-10.0 scale\n"
            "norm_acc = min(max(acc / 10.0, 0.0), 10.0)\n\n"
            "# Composite weighted score: 25% fit, 30% novelty, 25% accuracy, 20% innovation\n"
            "composite = round(0.25 * fit + 0.30 * nov + 0.25 * norm_acc + 0.20 * inv, 2)\n"
            "return composite\n"
        )

        narrative_system = (
            "You are an expert Chief Scientific Officer and Senior Systematic Literature Reviewer. "
            "Synthesize a publication-grade Executive Research Briefing in Markdown format based on "
            "the top breakthrough papers, their experimental metrics, and composite signal scores."
        )
        narrative_prompt = (
            "Synthesize an Executive Systematic Review Briefing for workspace '{workspace_name}' (Pipeline Run: {run_id}).\n\n"
            "Identified Papers Total: {total_papers}\n"
            "Accepted Studies: {accepted_papers_count}\n"
            "Average Composite Signal Score: {avg_signal_score}\n\n"
            "Top Accepted Breakthrough Papers Catalog:\n{papers}\n\n"
            "Structured Score Vectors & Extracted Parameters Summary:\n{score_vectors_summary}\n\n"
            "Structure the Executive Briefing as follows:\n"
            "1. Executive Summary & Breakthrough Highlights\n"
            "2. Cross-Study Methodological Synthesis\n"
            "3. Empirical Benchmark Landscape & Performance Metrics Table\n"
            "4. Strategic Recommendations & Technology Translation Roadmap"
        )

        model_to_use = getattr(config, "screening_llm_model", os.getenv("E2E_LLM_MODEL", "google/gemini-3.8-flash"))
        provider_to_use = getattr(config, "llm_provider", os.getenv("E2E_LLM_PROVIDER", "google"))

        ext_defs_payload = [
            {
                "name": f"Performance_Metrics_{random_suffix}",
                "order": 1,
                "primary_frontend_metric": "accuracy_pct",
                "secondary_frontend_metrics": ["latency_ms", "benchmark_dataset"],
                "exit_metrics": ["accuracy_pct", "latency_ms"],
                "system_prompt": "Extract quantitative model performance metrics, benchmark evaluation dataset, and inference latency from the research paper.",
                "user_prompt_template": "Paper: {title}\nContent:\n{content}\nExtract accuracy percentage, benchmark dataset, and inference latency.",
                "response_schema": {
                    "type": "object",
                    "required": ["accuracy_pct", "benchmark_dataset", "justification"],
                    "properties": {
                        "accuracy_pct": {"type": "number", "minimum": 0, "maximum": 100, "description": "Reported accuracy or benchmark percentage (0-100)"},
                        "benchmark_dataset": {"type": "string", "description": "Benchmark or dataset evaluated on (e.g. ImageNet, GLUE, SQuAD)"},
                        "latency_ms": {"type": "number", "description": "Reported inference latency in milliseconds"},
                        "justification": {"type": "string", "description": "Direct citation or table reference from text"},
                    },
                },
                "postprocessing_code": (
                    "# Normalize accuracy percentage to 0-10 scale for signal scoring\n"
                    "acc = float(accuracy_pct) if 'accuracy_pct' in locals() and accuracy_pct is not None else 0.0\n"
                    "norm_val = round(min(max(acc / 10.0, 0.0), 10.0), 2)\n"
                    "return {'accuracy_pct_postprocessed': norm_val, 'normalized_acc': norm_val}\n"
                ),
                "llm_model": model_to_use,
                "version": 1,
                "requires_consensus": False,
                "is_active": True,
            },
            {
                "name": f"Readiness_Assessment_{random_suffix}",
                "order": 2,
                "primary_frontend_metric": "innovation_score",
                "secondary_frontend_metrics": ["trl_level"],
                "exit_metrics": ["innovation_score", "trl_level"],
                "system_prompt": "Evaluate the architectural innovation (1-10) and Technology Readiness Level (TRL 1-9) of the presented research.",
                "user_prompt_template": "Paper: {title}\nContent:\n{content}\nEvaluate architectural novelty (1-10) and assess TRL level (1-9).",
                "response_schema": {
                    "type": "object",
                    "required": ["innovation_score", "trl_level", "justification"],
                    "properties": {
                        "innovation_score": {"type": "number", "minimum": 1, "maximum": 10, "description": "Architectural novelty and originality score (1-10)"},
                        "trl_level": {"type": "integer", "minimum": 1, "maximum": 9, "description": "Technology Readiness Level (1-9)"},
                        "justification": {"type": "string", "description": "Rationale justifying innovation and TRL assessment"},
                    },
                },
                "postprocessing_code": (
                    "# Compute combined readiness index\n"
                    "innov = float(innovation_score) if 'innovation_score' in locals() and innovation_score is not None else 5.0\n"
                    "trl = float(trl_level) if 'trl_level' in locals() and trl_level is not None else 3.0\n"
                    "readiness_index = round(0.6 * innov + 0.4 * (trl * 1.1), 2)\n"
                    "return {'readiness_index': readiness_index, 'innovation_score_postprocessed': innov}\n"
                ),
                "llm_model": model_to_use,
                "version": 1,
                "requires_consensus": False,
                "is_active": True,
            },
        ]

        ws_data = ws_svc.create_workspace(
            name=workspace_name,
            abstract_acceptance_criteria=abstract_acceptance,
            abstract_rejection_criteria=abstract_rejection,
            abstract_screening_system_prompt=abstract_system_prompt,
            abstract_screening_user_prompt_template=abstract_user_template,
            abstract_screening_response_schema=abstract_schema,
            abstract_screening_exit_metric="fit_score",
            full_text_acceptance_criteria=full_text_acceptance,
            full_text_rejection_criteria=full_text_rejection,
            full_text_screening_system_prompt=full_text_system_prompt,
            full_text_screening_user_prompt_template=full_text_user_template,
            full_text_screening_response_schema=full_text_schema,
            full_text_screening_exit_metric="novelty_score",
            signal_score_code=signal_score_formula,
            narrative_report_system_prompt=narrative_system,
            narrative_report_prompt=narrative_prompt,
            narrative_report_top_n_papers=10,
            screening_llm_model=model_to_use,
            llm_provider=provider_to_use,
            ocr_provider="pypdf",
            reasoning_effort="medium",
            monthly_token_limit=10000000,
            monthly_usd_limit=100.0,
            extraction_definitions=ext_defs_payload,
        )
        workspace_id = ws_data["id"]
        scenario_results["workspace_id"] = workspace_id
        DataConsistencyValidator.validate_uuid(workspace_id, "workspace_id")

        # Step 1b: Add team reviewers to workspace for queue visibility & review distribution
        ws_svc.add_member(workspace_id, r2_name, role="researcher")
        ws_svc.add_member(workspace_id, r3_name, role="researcher")

        # Validate that all dynamic fields, prompts, schemas, metrics & formulas were persisted
        assert ws_data.get("abstract_screening_system_prompt") is not None, "Missing abstract_screening_system_prompt"
        assert ws_data.get("abstract_screening_user_prompt_template") is not None, "Missing abstract_screening_user_prompt_template"
        assert ws_data.get("abstract_screening_response_schema") is not None, "Missing abstract_screening_response_schema"
        assert ws_data.get("abstract_screening_exit_metric") == "fit_score", f"Unexpected abstract exit metric: {ws_data.get('abstract_screening_exit_metric')}"
        assert ws_data.get("full_text_screening_system_prompt") is not None, "Missing full_text_screening_system_prompt"
        assert ws_data.get("full_text_screening_user_prompt_template") is not None, "Missing full_text_screening_user_prompt_template"
        assert ws_data.get("full_text_screening_response_schema") is not None, "Missing full_text_screening_response_schema"
        assert ws_data.get("full_text_screening_exit_metric") == "novelty_score", f"Unexpected full text exit metric: {ws_data.get('full_text_screening_exit_metric')}"
        assert ws_data.get("signal_score_code") is not None, "Missing signal_score_code"
        assert ws_data.get("narrative_report_prompt") is not None, "Missing narrative_report_prompt"
        assert len(ws_data.get("extraction_definitions", [])) >= 2, f"Expected at least 2 extraction definitions, found: {len(ws_data.get('extraction_definitions', []))}"

        logger.info(f"   ✓ Workspace '{workspace_name}' provisioned with 100% complete production configuration:")
        logger.info(f"     • Reviewer Team: '{r1_name}' (admin), '{r2_name}' (researcher), '{r3_name}' (researcher)")
        logger.info(f"     • Abstract Gate: exit='{ws_data.get('abstract_screening_exit_metric')}', schema validated")
        logger.info(f"     • Full-Text Gate: exit='{ws_data.get('full_text_screening_exit_metric')}', schema validated")
        logger.info(f"     • Signal Score: AST-sandboxed Python composite formula active")
        logger.info(f"     • Executive Briefing: Custom narrative synthesis prompt active (Top {ws_data.get('narrative_report_top_n_papers')} studies)")
        logger.info(f"     • Extraction Definitions: {len(ws_data.get('extraction_definitions', []))} multi-metric targets with postprocessing code & frontend metrics")

        # Step 3: Configure SLR Policy Engine with Dual Review Quorum & Arbiter Strategy
        logger.info("⚙️  Step 2: Configuring SLR Policy Engine (dual-review quorum, checkpoint gates & arbiter)...")
        slr_config_payload = {
            "checkpoint_gate_mode": "two_stage_split",  # Gate 1 (Abstract) + Gate 2 (Full-Text)
            "enable_extraction_gate": True,             # Gate 3 (Extraction)
            "screening_quorum_size": 2,                 # Dual Review Quorum!
            "extraction_quorum_size": 1,
            "sampling_mode": "full_audit",              # Sample 100% of papers so accept, reject and conflict cases all execute
            "abstract_sample_percentage": 100.0,
            "full_text_sample_percentage": 100.0,
            "extraction_sample_percentage": 100.0,
            "negative_control_percentage": 0.0,
            "enable_rob_assessment": True,
            "rob_framework": "auto_detect",
            "tie_breaker_strategy": "arbiter_ruling",   # Escalates split votes to Senior Arbiter
        }
        slr_config = slr_svc.update_workspace_config(workspace_id, slr_config_payload)
        assert slr_config.get("checkpoint_gate_mode") == "two_stage_split", f"Config update failed: {slr_config}"
        assert slr_config.get("screening_quorum_size") == 2, f"Quorum update failed: {slr_config}"
        logger.info(f"   ✓ SLR Policy Active: mode={slr_config.get('checkpoint_gate_mode')}, quorum={slr_config.get('screening_quorum_size')}, tie_breaker={slr_config.get('tie_breaker_strategy')}")

        # Step 4: Configure Scraper with higher paper limit (12 papers)
        paper_count = 12
        logger.info(f"📡 Step 3: Configuring Academic Ingestion Scraper (limit: {paper_count} papers)...")
        scraper = ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND (all:"neural" OR all:"transformer" OR all:"deep learning" OR all:"reinforcement" OR all:"optimization")',
            limit=paper_count,
        )
        scenario_results["scraper_id"] = scraper["id"]

        # Step 5: Start Autonomous Research Agent
        logger.info("🚀 Step 4: Starting SLR Pipeline Run...")
        agent_proc = agent_svc.start_research_agent(
            workspace_id=workspace_id,
            name=f"SLR Run - {workspace_name}",
            limit=paper_count,
            reprocess_existing=True,
        )
        pipeline_run_id = agent_proc.get("pipeline_run") or agent_proc["id"]
        scenario_results["pipeline_run_id"] = pipeline_run_id
        logger.info(f"   ✓ Pipeline Run dispatched: ID={pipeline_run_id}")

        # =====================================================================
        # CHECKPOINT GATE 1: Abstract Screening (Quorum=2, Accept, Reject, Conflict)
        # =====================================================================
        logger.info("\n⏸️  Step 5: Monitoring DAG progression toward Gate 1 (Abstract Screening)...")
        paused_run_g1 = wait_for_pipeline_status(
            pipeline_svc,
            pipeline_run_id,
            target_status="paused",
            expected_stage_substring="awaiting_abstract_screening_audit",
            timeout_seconds=cfg.max_timeout_sec,
        )
        logger.info(f"   🛑 Checkpoint 1 Reached: status='{paused_run_g1.get('status')}', stage='{paused_run_g1.get('current_stage')}'")

        queue_items = slr_svc.get_my_queue()
        matching_cohorts = [
            q for q in queue_items
            if q.get("pipeline_run_id") == pipeline_run_id and q.get("gate") == "abstract_screening"
        ]
        assert matching_cohorts, f"No Gate 1 cohort found in my-queue for run {pipeline_run_id}. Queue: {queue_items}"
        cohort_g1_summary = matching_cohorts[0]
        cohort_g1_id = cohort_g1_summary["cohort_id"]
        logger.info(f"   📋 Found Gate 1 AuditSampleCohort: ID={cohort_g1_id}, papers to review={cohort_g1_summary.get('remaining_count')}")

        cohort_g1_detail = slr_svc.get_cohort(cohort_g1_id)
        sampled_papers_g1 = cohort_g1_detail.get("papers", [])
        assert len(sampled_papers_g1) >= 10, f"Cohort {cohort_g1_id} expected ~12 papers for full case coverage! Found: {len(sampled_papers_g1)}"

        # 3-way reviewer rotation for dual-review quorum (2 votes per paper):
        # Paper 0 (i=0): R1 & R2
        # Paper 1 (i=1): R2 & R3
        # Paper 2 (i=2): R3 & R1
        # Balanced distribution across all 3 human reviewers!
        reviewer_pairs = [
            (slr_svc, r2_slr_svc, r1_name, r2_name),
            (r2_slr_svc, r3_slr_svc, r2_name, r3_name),
            (r3_slr_svc, slr_svc, r3_name, r1_name),
        ]

        # Case 1: Unanimous Acceptance (Paper 0)
        p0 = sampled_papers_g1[0]
        r_a, r_b, name_a, name_b = reviewer_pairs[0]
        p_det_0 = slr_svc.get_cohort_paper(cohort_g1_id, p0["paper_id"])
        act_0 = "agree" if p_det_0.get("ai_decision") == "include" else "override_include"
        logger.info(f"   ✍️ [Gate 1 Case 1 - Unanimous Accept ({name_a} + {name_b})] Paper: '{p0.get('title', p0['paper_id'])[:45]}...' (action={act_0})")
        r_a.submit_screening_review(cohort_id=cohort_g1_id, paper_id=p0["paper_id"], action=act_0, reviewer_note=f"[{name_a}] Abstract matches inclusion criteria.")
        r_b.submit_screening_review(cohort_id=cohort_g1_id, paper_id=p0["paper_id"], action=act_0, reviewer_note=f"[{name_b}] Abstract satisfies inclusion criteria.")
        logger.info("      ✓ Both reviewers voted Agree (Include) -> Quorum met, consensus reached.")

        # Case 2: Unanimous Rejection (Paper 1 - only 1 paper excluded at Abstract stage)
        p1 = sampled_papers_g1[1]
        r_a, r_b, name_a, name_b = reviewer_pairs[1]
        logger.info(f"   ✍️ [Gate 1 Case 2 - Unanimous Reject ({name_a} + {name_b})] Paper: '{p1.get('title', p1['paper_id'])[:45]}...'")
        r_a.submit_screening_review(
            cohort_id=cohort_g1_id, paper_id=p1["paper_id"],
            action="override_exclude", exclusion_reason="Wrong Study Population",
            reviewer_note=f"[{name_a}] Study population outside trial scope."
        )
        r_b.submit_screening_review(
            cohort_id=cohort_g1_id, paper_id=p1["paper_id"],
            action="override_exclude", exclusion_reason="Wrong Study Population",
            reviewer_note=f"[{name_b}] Confirmed non-target study population."
        )
        logger.info("      ✓ Both reviewers voted Override Exclude -> Quorum met, paper excluded.")

        # Case 3: Reviewer Conflict (Split Vote) & Senior Arbiter Resolution to INCLUDE (Paper 2)
        p2 = sampled_papers_g1[2]
        r_a, r_b, name_a, name_b = reviewer_pairs[2]
        logger.info(f"   ✍️ [Gate 1 Case 3 - Reviewer Conflict & Arbiter Ruling ({name_a} vs {name_b})] Paper: '{p2.get('title', p2['paper_id'])[:45]}...'")
        r_a.submit_screening_review(
            cohort_id=cohort_g1_id, paper_id=p2["paper_id"],
            action="override_include", reviewer_note=f"[{name_a}] Novel architecture warrants full-text review."
        )
        r_b.submit_screening_review(
            cohort_id=cohort_g1_id, paper_id=p2["paper_id"],
            action="override_exclude", exclusion_reason="Insufficient Quantitative Data Reported",
            reviewer_note=f"[{name_b}] Abstract lacks empirical benchmark metrics."
        )
        logger.info("      ⚖️ Split votes registered (1 Include vs 1 Exclude) -> Escalated to Senior Arbiter.")

        # Vote to INCLUDE on all remaining papers (Papers 3..11) so they reach the final stage
        for idx, p_rem in enumerate(sampled_papers_g1[3:], start=3):
            r_a, r_b, name_a, name_b = reviewer_pairs[idx % len(reviewer_pairs)]
            p_det = slr_svc.get_cohort_paper(cohort_g1_id, p_rem["paper_id"])
            act = "agree" if p_det.get("ai_decision") == "include" else "override_include"
            r_a.submit_screening_review(cohort_id=cohort_g1_id, paper_id=p_rem["paper_id"], action=act, reviewer_note=f"[{name_a}] Abstract verified against protocol.")
            r_b.submit_screening_review(cohort_id=cohort_g1_id, paper_id=p_rem["paper_id"], action=act, reviewer_note=f"[{name_b}] Concurs with inclusion.")

        # Verify cohort remains paused while dispute is pending
        cohort_g1_mid = slr_svc.get_cohort(cohort_g1_id)
        assert cohort_g1_mid.get("is_audit_complete") is False, "Cohort must NOT complete while an adjudication dispute is pending!"
        logger.info("   ✓ Verified: Gate 1 cohort is paused awaiting Senior Arbiter ruling.")

        # Senior Arbiter resolves dispute in favor of INCLUDE so paper advances!
        pending_disputes_g1 = arbiter_slr_svc.list_disputes(status="pending")
        matching_dispute_g1 = next(
            (d for d in pending_disputes_g1 if str(d.get("paper")) == str(p2["paper_id"]) or d.get("sample_cohort") == cohort_g1_id),
            None
        )
        assert matching_dispute_g1 is not None, f"No pending dispute found for Gate 1 paper {p2['paper_id']}! Disputes: {pending_disputes_g1}"
        logger.info(f"   🧑‍⚖️ Senior Arbiter ruling on dispute {matching_dispute_g1['id']} for '{matching_dispute_g1.get('paper_title', p2['paper_id'])[:45]}...'")
        resolve_resp_g1 = arbiter_slr_svc.resolve_dispute(
            dispute_id=matching_dispute_g1["id"],
            final_decision="include",
            resolution_rationale="Senior Arbiter ruling: Computational architecture meets eligibility protocol; proceed to full-text assessment."
        )
        assert resolve_resp_g1.get("status") == "resolved", f"Dispute resolution failed: {resolve_resp_g1}"
        logger.info("   ✓ Gate 1 dispute resolved cleanly (final_decision='include'). 11 papers advance!")

        # Verify cohort completion
        cohort_g1_detail_after = slr_svc.get_cohort(cohort_g1_id)
        assert cohort_g1_detail_after.get("is_audit_complete") is True, f"Gate 1 cohort not marked complete after dispute resolution: {cohort_g1_detail_after}"
        scenario_results["gate_1_abstract"] = {
            "cohort_id": cohort_g1_id,
            "sampled_count": len(sampled_papers_g1),
            "status": "COMPLETED_AND_RESUMED",
            "dispute_resolved": matching_dispute_g1["id"],
        }
        logger.info("   ✅ Gate 1 Audit completed (Accept + Reject + Conflict resolved)! Pipeline auto-resumed.")

        # =====================================================================
        # CHECKPOINT GATE 2: Full-Text Screening (Quorum=2, Accept, Reject, Conflict)
        # =====================================================================
        logger.info("\n⏸️  Step 6: Monitoring DAG progression toward Gate 2 (Full-Text Screening)...")
        paused_run_g2 = wait_for_pipeline_status(
            pipeline_svc,
            pipeline_run_id,
            target_status="paused",
            expected_stage_substring="awaiting_full_text_screening_audit",
            timeout_seconds=cfg.max_timeout_sec,
        )
        logger.info(f"   🛑 Checkpoint 2 Reached: status='{paused_run_g2.get('status')}', stage='{paused_run_g2.get('current_stage')}'")

        queue_items_g2 = slr_svc.get_my_queue()
        matching_cohorts_g2 = [
            q for q in queue_items_g2
            if q.get("pipeline_run_id") == pipeline_run_id and q.get("gate") == "full_text_screening"
        ]
        assert matching_cohorts_g2, f"No Gate 2 cohort found in my-queue. Queue: {queue_items_g2}"
        cohort_g2_id = matching_cohorts_g2[0]["cohort_id"]
        cohort_g2_detail = slr_svc.get_cohort(cohort_g2_id)
        sampled_papers_g2 = cohort_g2_detail.get("papers", [])
        assert len(sampled_papers_g2) >= 9, f"Gate 2 cohort expected ~11 papers! Found: {len(sampled_papers_g2)}"

        # Case 1: Unanimous Full-Text Acceptance (Paper 0)
        p2_0 = sampled_papers_g2[0]
        r_a, r_b, name_a, name_b = reviewer_pairs[0]
        p_det_g2_0 = slr_svc.get_cohort_paper(cohort_g2_id, p2_0["paper_id"])
        act_g2_0 = "agree" if p_det_g2_0.get("ai_decision") == "include" else "override_include"
        logger.info(f"   ✍️ [Gate 2 Case 1 - Unanimous Full-Text Accept ({name_a} + {name_b})] Paper: '{p2_0.get('title', p2_0['paper_id'])[:45]}...' (action={act_g2_0})")
        r_a.submit_screening_review(
            cohort_id=cohort_g2_id, paper_id=p2_0["paper_id"], action=act_g2_0,
            evidence_citation="Section 3: Empirical evaluation corroborates trial convergence.",
            reviewer_note=f"[{name_a}] Methodology and empirical results verified."
        )
        r_b.submit_screening_review(
            cohort_id=cohort_g2_id, paper_id=p2_0["paper_id"], action=act_g2_0,
            evidence_citation="Section 4: Baseline comparison benchmarks confirmed.",
            reviewer_note=f"[{name_b}] Agrees with full-text inclusion."
        )
        logger.info("      ✓ Both reviewers agreed on Full-Text inclusion with verified citations.")

        # Case 2: Full-Text Rejection (Paper 1 - only 1 paper excluded at Full-Text stage)
        p2_1 = sampled_papers_g2[1]
        r_a, r_b, name_a, name_b = reviewer_pairs[1]
        logger.info(f"   ✍️ [Gate 2 Case 2 - Unanimous Full-Text Reject ({name_a} + {name_b})] Paper: '{p2_1.get('title', p2_1['paper_id'])[:45]}...'")
        r_a.submit_screening_review(
            cohort_id=cohort_g2_id, paper_id=p2_1["paper_id"],
            action="override_exclude", exclusion_reason="No Control / Comparator Group",
            reviewer_note=f"[{name_a}] Trial lacks baseline control group."
        )
        r_b.submit_screening_review(
            cohort_id=cohort_g2_id, paper_id=p2_1["paper_id"],
            action="override_exclude", exclusion_reason="No Control / Comparator Group",
            reviewer_note=f"[{name_b}] Absence of comparator group confirmed."
        )
        logger.info("      ✓ Both reviewers voted Override Exclude on Full-Text.")

        # Case 3: Reviewer Conflict (Split Vote) & Senior Arbiter Resolution to INCLUDE (Paper 2)
        p2_2 = sampled_papers_g2[2]
        r_a, r_b, name_a, name_b = reviewer_pairs[2]
        logger.info(f"   ✍️ [Gate 2 Case 3 - Full-Text Reviewer Conflict & Arbiter Ruling ({name_a} vs {name_b})] Paper: '{p2_2.get('title', p2_2['paper_id'])[:45]}...'")
        r_a.submit_screening_review(
            cohort_id=cohort_g2_id, paper_id=p2_2["paper_id"],
            action="override_include",
            evidence_citation="Section 4.2 presents robust trial sensitivity analysis.",
            reviewer_note=f"[{name_a}] Trial sensitivity analysis satisfies criteria."
        )
        r_b.submit_screening_review(
            cohort_id=cohort_g2_id, paper_id=p2_2["paper_id"],
            action="override_exclude", exclusion_reason="Insufficient Quantitative Data Reported",
            reviewer_note=f"[{name_b}] Missing raw variance metrics in Table 2."
        )
        logger.info("      ⚖️ Split votes registered on Full-Text -> Escalated to Senior Arbiter.")

        # Vote to INCLUDE on all remaining papers (Papers 3..10) so they advance to Extraction Gate
        for idx, p_rem in enumerate(sampled_papers_g2[3:], start=3):
            r_a, r_b, name_a, name_b = reviewer_pairs[idx % len(reviewer_pairs)]
            p_det_rem = slr_svc.get_cohort_paper(cohort_g2_id, p_rem["paper_id"])
            act_rem = "agree" if p_det_rem.get("ai_decision") == "include" else "override_include"
            r_a.submit_screening_review(
                cohort_id=cohort_g2_id, paper_id=p_rem["paper_id"], action=act_rem,
                evidence_citation="Section 4: Evaluation benchmarks corroborated.",
                reviewer_note=f"[{name_a}] Full-text meets criteria.",
            )
            r_b.submit_screening_review(
                cohort_id=cohort_g2_id, paper_id=p_rem["paper_id"], action=act_rem,
                evidence_citation="Section 5: Mathematical formulations verified.",
                reviewer_note=f"[{name_b}] Concurs with full-text inclusion.",
            )

        # Check cohort paused
        cohort_g2_mid = slr_svc.get_cohort(cohort_g2_id)
        assert cohort_g2_mid.get("is_audit_complete") is False, "Cohort must remain paused while Gate 2 dispute is pending!"

        # Senior Arbiter resolves dispute in favor of INCLUDE so paper advances!
        pending_disputes_g2 = arbiter_slr_svc.list_disputes(status="pending")
        matching_dispute_g2 = next(
            (d for d in pending_disputes_g2 if str(d.get("paper")) == str(p2_2["paper_id"]) or d.get("sample_cohort") == cohort_g2_id),
            None
        )
        assert matching_dispute_g2 is not None, f"No pending dispute found for Gate 2 paper {p2_2['paper_id']}! Disputes: {pending_disputes_g2}"
        logger.info(f"   🧑‍⚖️ Senior Arbiter ruling on Gate 2 dispute {matching_dispute_g2['id']}...")
        resolve_resp_g2 = arbiter_slr_svc.resolve_dispute(
            dispute_id=matching_dispute_g2["id"],
            final_decision="include",
            resolution_rationale="Senior Arbiter ruling: Table 2 confidence intervals allow deriving required variance; full-text inclusion approved."
        )
        assert resolve_resp_g2.get("status") == "resolved"
        dispute_g2_id = matching_dispute_g2["id"]
        logger.info("   ✓ Gate 2 dispute resolved cleanly (final_decision='include'). 10 papers advance!")

        cohort_g2_detail_after = slr_svc.get_cohort(cohort_g2_id)
        assert cohort_g2_detail_after.get("is_audit_complete") is True
        scenario_results["gate_2_full_text"] = {
            "cohort_id": cohort_g2_id,
            "sampled_count": len(sampled_papers_g2),
            "status": "COMPLETED_AND_RESUMED",
            "dispute_resolved": dispute_g2_id,
        }
        logger.info("   ✅ Gate 2 Audit completed (Full-Text consensus + Dispute resolved)! Pipeline auto-resumed.")

        # =====================================================================
        # CHECKPOINT GATE 3: Parameter Extraction Audit (Verify, Modify, Reject)
        # =====================================================================
        logger.info("\n⏸️  Step 7: Monitoring DAG progression toward Gate 3 (Extraction Audit)...")
        paused_run_g3 = wait_for_pipeline_status(
            pipeline_svc,
            pipeline_run_id,
            target_status="paused",
            expected_stage_substring="awaiting_parameter_extraction_audit",
            timeout_seconds=cfg.max_timeout_sec,
        )
        logger.info(f"   🛑 Checkpoint 3 Reached: status='{paused_run_g3.get('status')}', stage='{paused_run_g3.get('current_stage')}'")

        queue_items_g3 = slr_svc.get_my_queue()
        matching_cohorts_g3 = [
            q for q in queue_items_g3
            if q.get("pipeline_run_id") == pipeline_run_id and q.get("gate") == "parameter_extraction"
        ]
        assert matching_cohorts_g3, f"No Gate 3 cohort found in my-queue. Queue: {queue_items_g3}"
        cohort_g3_id = matching_cohorts_g3[0]["cohort_id"]
        cohort_g3_detail = slr_svc.get_cohort(cohort_g3_id)
        sampled_papers_g3 = cohort_g3_detail.get("papers", [])
        assert len(sampled_papers_g3) >= 8, f"Gate 3 cohort expected ~10 papers! Found: {len(sampled_papers_g3)}"

        # Rotate 3 auditors across the extracted parameters
        auditors = [
            (slr_svc, r1_name),
            (r2_slr_svc, r2_name),
            (r3_slr_svc, r3_name),
        ]

        audit_count = 0
        verified_count = 0
        modified_count = 0
        rejected_count = 0

        for p_idx, p_info in enumerate(sampled_papers_g3):
            pid = p_info["paper_id"]
            paper_audit = slr_svc.get_cohort_paper(cohort_g3_id, pid)
            extractions = paper_audit.get("extractions", [])
            logger.info(f"   ✍️ Auditing Extractions for paper '{p_info.get('title', pid)[:45]}...' ({len(extractions)} parameter(s))")

            for ext_idx, ext in enumerate(extractions):
                ext_id = ext.get("extraction_id") or ext.get("id")
                if not ext_id:
                    continue

                auditor_slr, auditor_name = auditors[audit_count % len(auditors)]
                act_mod = audit_count % 6
                if act_mod in (0, 1, 3, 4):
                    # Action: Verify (majority of parameters kept clean)
                    audit_resp = auditor_slr.submit_extraction_audit(
                        cohort_id=cohort_g3_id,
                        extraction_id=ext_id,
                        action="verify",
                        reviewer_notes=f"[{auditor_name}] Reported parameter verified against experimental figures.",
                    )
                    verified_count += 1
                elif act_mod == 2:
                    # Action: Modify
                    p_name = str(ext.get("parameter_name") or ext.get("category") or "").lower()
                    if "readiness" in p_name or "innovation" in p_name:
                        c_fields = {"innovation_score": 8.5, "trl_level": 5, "justification": f"[{auditor_name}] Adjusted novelty to 8.5 and TRL to 5 based on Figure 4."}
                        r_notes = f"[{auditor_name}] Adjusted innovation score to 8.5 and verified prototype readiness."
                    else:
                        c_fields = {"accuracy_pct": 95.8, "benchmark_dataset": "ImageNet-1k", "justification": f"[{auditor_name}] Corrected baseline metric to match Table 3 empirical data."}
                        r_notes = f"[{auditor_name}] Corrected reported baseline accuracy from 93.0% to 95.8%."

                    audit_resp = auditor_slr.submit_extraction_audit(
                        cohort_id=cohort_g3_id,
                        extraction_id=ext_id,
                        action="modify",
                        corrected_fields=c_fields,
                        reviewer_notes=r_notes,
                    )
                    modified_count += 1
                else:  # act_mod == 5
                    # Action: Reject
                    audit_resp = auditor_slr.submit_extraction_audit(
                        cohort_id=cohort_g3_id,
                        extraction_id=ext_id,
                        action="reject",
                        reviewer_notes=f"[{auditor_name}] Parameter hallucinated and not substantiated by source text.",
                    )
                    rejected_count += 1

                assert audit_resp.get("success") is True or audit_resp.get("status") in ("audited", "reviewed")
                audit_count += 1

        cohort_g3_detail_after = slr_svc.get_cohort(cohort_g3_id)
        assert cohort_g3_detail_after.get("is_audit_complete") is True
        scenario_results["gate_3_extraction"] = {
            "cohort_id": cohort_g3_id,
            "audited_extractions_count": audit_count,
            "verified": verified_count,
            "modified": modified_count,
            "rejected": rejected_count,
            "status": "COMPLETED_AND_RESUMED",
        }
        logger.info(f"   ✅ Gate 3 Extraction Audit completed: {verified_count} verified, {modified_count} modified, {rejected_count} rejected across 3 reviewers. Pipeline auto-resumed.")

        # =====================================================================
        # Step 8: Final Pipeline Completion
        # =====================================================================
        logger.info("\n🏁 Step 8: Waiting for Final SLR Pipeline Completion...")
        completed_run = wait_for_pipeline_status(
            pipeline_svc,
            pipeline_run_id,
            target_status="completed",
            timeout_seconds=cfg.max_timeout_sec,
        )
        assert completed_run.get("status") == "completed"
        logger.info(f"   🎉 Pipeline Run {pipeline_run_id} reached terminal state 'completed'!")

        # =====================================================================
        # Step 9: Verify PRISMA, Risk of Bias & Disputes Audit Trails
        # =====================================================================
        logger.info("\n📊 Step 9: Verifying PRISMA Flow Diagram, Risk of Bias & Disputes Audit Trails...")
        prisma_data = slr_svc.get_prisma_metrics(pipeline_run_id)
        identified = prisma_data.get("records_identified_total") if "records_identified_total" in prisma_data else prisma_data.get("identified")
        screened = prisma_data.get("records_screened_abstract") if "records_screened_abstract" in prisma_data else prisma_data.get("screened")
        excluded_abs = prisma_data.get("records_excluded_abstract") if "records_excluded_abstract" in prisma_data else prisma_data.get("excluded_abstract")
        ft_assessed = prisma_data.get("full_text_assessed") if "full_text_assessed" in prisma_data else prisma_data.get("full_text_assessed")
        included = prisma_data.get("studies_included_synthesis") if "studies_included_synthesis" in prisma_data else (prisma_data.get("studies_included_meta_analysis") or prisma_data.get("included"))

        assert identified is not None and identified >= 10, f"PRISMA missing identified count: {prisma_data}"
        assert screened is not None and screened >= 10, f"PRISMA missing screened count: {prisma_data}"
        assert excluded_abs is not None and excluded_abs == 1, f"Expected 1 abstract exclusion: {prisma_data}"
        assert ft_assessed is not None and ft_assessed >= 9, f"PRISMA missing full_text_assessed: {prisma_data}"
        assert included is not None and included >= 8, f"PRISMA expected ~10 included studies: {prisma_data}"
        scenario_results["prisma_metrics"] = prisma_data
        logger.info(f"   ✓ PRISMA Flow: Identified={identified}, Screened={screened}, Excluded={excluded_abs}, FullTextAssessed={ft_assessed}, Included={included}")

        rob_assessments = slr_svc.get_rob_assessments(pipeline_run_id)
        scenario_results["rob_assessments_count"] = len(rob_assessments)
        assert len(rob_assessments) >= 7, f"Expected at least 7 RoB assessments, found: {len(rob_assessments)}"
        logger.info(f"   ✓ Risk of Bias Assessments generated: {len(rob_assessments)} studies appraised.")

        # Verify Disputes Audit Trail
        pending_disputes = arbiter_slr_svc.list_disputes(status="pending")
        assert len(pending_disputes) == 0, f"Expected 0 pending disputes, found: {pending_disputes}"
        resolved_disputes = arbiter_slr_svc.list_disputes(status="resolved")
        assert len(resolved_disputes) >= 2, f"Expected at least 2 resolved disputes, found: {len(resolved_disputes)}"
        logger.info(f"   ✓ Disputes Audit Trail: 0 pending, {len(resolved_disputes)} resolved by Senior Arbiter.")

        scenario_results["status"] = "PASSED"
        logger.info("=================================================================")
        logger.info("🎉 FULL SLR REVIEW GATES & CHECKPOINTS SCENARIO PASSED!")
        logger.info("=================================================================")

    finally:
        # Cleanup members & test reviewers if cleanup_after / delete_after is requested
        if cfg.delete_after:
            logger.info("\n🧹 Post-test Cleanup: Purging test members, reviewer accounts & temporary SLR workspace...")
            ws_id = scenario_results.get("workspace_id")
            if ws_id:
                for rev_user in test_reviewers:
                    try:
                        ws_svc.remove_member(ws_id, rev_user)
                    except Exception as e:
                        logger.debug(f"Could not remove member '{rev_user}' from workspace '{ws_id}': {e}")

            if arbiter_auth:
                for rev_user in test_reviewers:
                    try:
                        arbiter_auth.delete_user(rev_user)
                    except Exception as e:
                        logger.warning(f"Could not delete test reviewer account '{rev_user}': {e}")

            if ws_id:
                try:
                    ws_svc.delete_workspace(ws_id)
                    logger.info(f"   ✓ Workspace '{ws_id}' deleted.")
                except Exception as e:
                    logger.warning(f"Could not delete workspace '{ws_id}': {e}")
            logger.info("✅ Post-test Cleanup completed successfully.")

    return scenario_results

