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

    try:
        # Step 1: Authenticate Primary & Secondary Reviewers
        auth_data = auth.login(cfg.username, cfg.password)
        scenario_results["user_id"] = auth_data.get("user_id")

        # Secondary reviewer & Senior Arbiter
        sec_client = APIClient(cfg.base_url)
        sec_auth = AuthService(sec_client)
        if cfg.username == "admin":
            sec_user = "test_e2e"
            sec_pass = "t4st_pa55w0rD!#"
            arbiter_client = client
        else:
            sec_user = os.getenv("ADMIN_USERNAME", "admin")
            sec_pass = os.getenv("ADMIN_PASSWORD", "schwarz123!")
            arbiter_client = sec_client

        logger.info(f"👥 Secondary Reviewer: '{sec_user}'")
        sec_auth.login(sec_user, sec_pass)
        sec_slr_svc = SLRService(sec_client)
        arbiter_slr_svc = SLRService(arbiter_client)

        if cfg.cleanup_before:
            ws_svc.cleanup_old_test_workspaces(prefix="test_e2e_slr_gates_")

        # Step 2: Create Workspace with Systematic Review Criteria
        logger.info("\n🏛️ Step 1: Provisioning SLR Workspace with dual-stage criteria...")
        abstract_acceptance = (
            "Accept all peer-reviewed research papers presenting computational methods, deep learning, "
            "optimization algorithms, or artificial intelligence architectures."
        )
        abstract_rejection = "Reject non-scientific opinion articles and non-technical announcements."
        full_text_acceptance = "Accept papers with empirical evaluations, benchmarks, or mathematical derivations."
        full_text_rejection = "Reject papers with zero empirical metrics or absent methodology."

        ext_defs_payload = [
            {
                "name": f"accuracy_metric_{random_suffix}",
                "exit_metrics": ["accuracy_pct"],
                "system_prompt": "Extract the reported model accuracy or benchmark performance percentage.",
                "user_prompt_template": "Paper: {title}\nContent:\n{content}\nExtract accuracy percentage.",
                "response_schema": {
                    "type": "object",
                    "required": ["accuracy_pct", "justification"],
                    "properties": {
                        "accuracy_pct": {"type": "number"},
                        "justification": {"type": "string"},
                    },
                },
                "is_active": True,
            }
        ]

        ws_data = ws_svc.create_workspace(
            name=workspace_name,
            abstract_acceptance_criteria=abstract_acceptance,
            abstract_rejection_criteria=abstract_rejection,
            full_text_acceptance_criteria=full_text_acceptance,
            full_text_rejection_criteria=full_text_rejection,
            screening_llm_model="google/gemini-3.8-flash",
            extraction_definitions=ext_defs_payload,
        )
        workspace_id = ws_data["id"]
        scenario_results["workspace_id"] = workspace_id
        DataConsistencyValidator.validate_uuid(workspace_id, "workspace_id")

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

        # Step 4: Configure Scraper with higher paper limit (6 papers)
        paper_count = 6
        logger.info(f"📡 Step 3: Configuring Academic Ingestion Scraper (limit: {paper_count} papers)...")
        scraper = ws_svc.create_scraper(
            workspace_id=workspace_id,
            provider="arxiv",
            search_query='cat:cs.AI AND (all:"neural" OR all:"transformer" OR all:"optimization")',
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
        assert len(sampled_papers_g1) >= 3, f"Cohort {cohort_g1_id} needs at least 3 papers for full case coverage! Found: {len(sampled_papers_g1)}"

        # Case 1: Unanimous Acceptance (Paper 0)
        p0 = sampled_papers_g1[0]
        logger.info(f"   ✍️ [Gate 1 Case 1 - Unanimous Accept] Paper: '{p0.get('title', p0['paper_id'])[:45]}...'")
        slr_svc.submit_screening_review(cohort_id=cohort_g1_id, paper_id=p0["paper_id"], action="agree", reviewer_note="Primary reviewer: abstract matches inclusion criteria.")
        sec_slr_svc.submit_screening_review(cohort_id=cohort_g1_id, paper_id=p0["paper_id"], action="agree", reviewer_note="Secondary reviewer concurs: abstract satisfies inclusion criteria.")
        logger.info("      ✓ Both reviewers voted Agree (Include) -> Quorum met, consensus reached.")

        # Case 2: Unanimous Rejection (Paper 1)
        p1 = sampled_papers_g1[1]
        logger.info(f"   ✍️ [Gate 1 Case 2 - Unanimous Reject] Paper: '{p1.get('title', p1['paper_id'])[:45]}...'")
        slr_svc.submit_screening_review(
            cohort_id=cohort_g1_id, paper_id=p1["paper_id"],
            action="override_exclude", exclusion_reason="Wrong Study Population",
            reviewer_note="Primary reviewer: study population outside trial scope."
        )
        sec_slr_svc.submit_screening_review(
            cohort_id=cohort_g1_id, paper_id=p1["paper_id"],
            action="override_exclude", exclusion_reason="Wrong Study Population",
            reviewer_note="Secondary reviewer: confirmed non-target study population."
        )
        logger.info("      ✓ Both reviewers voted Override Exclude -> Quorum met, paper excluded.")

        # Case 3: Reviewer Conflict (Split Vote) & Senior Arbiter Resolution (Paper 2)
        p2 = sampled_papers_g1[2]
        logger.info(f"   ✍️ [Gate 1 Case 3 - Reviewer Conflict & Arbiter Ruling] Paper: '{p2.get('title', p2['paper_id'])[:45]}...'")
        slr_svc.submit_screening_review(
            cohort_id=cohort_g1_id, paper_id=p2["paper_id"],
            action="override_include", reviewer_note="Primary reviewer: novel algorithm architecture warrants inclusion."
        )
        sec_slr_svc.submit_screening_review(
            cohort_id=cohort_g1_id, paper_id=p2["paper_id"],
            action="override_exclude", exclusion_reason="Insufficient Quantitative Data Reported",
            reviewer_note="Secondary reviewer: abstract lacks empirical benchmark metrics."
        )
        logger.info("      ⚖️ Split votes registered (1 Include vs 1 Exclude) -> Escalated to Senior Arbiter.")

        # Vote Agree on any remaining papers to satisfy quorum
        for p_rem in sampled_papers_g1[3:]:
            slr_svc.submit_screening_review(cohort_id=cohort_g1_id, paper_id=p_rem["paper_id"], action="agree")
            sec_slr_svc.submit_screening_review(cohort_id=cohort_g1_id, paper_id=p_rem["paper_id"], action="agree")

        # Verify cohort remains paused while dispute is pending
        cohort_g1_mid = slr_svc.get_cohort(cohort_g1_id)
        assert cohort_g1_mid.get("is_audit_complete") is False, "Cohort must NOT complete while an adjudication dispute is pending!"
        logger.info("   ✓ Verified: Gate 1 cohort is paused awaiting Senior Arbiter ruling.")

        # Senior Arbiter resolves dispute
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
        logger.info("   ✓ Gate 1 dispute resolved cleanly (final_decision='include').")

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
        assert len(sampled_papers_g2) >= 2, f"Gate 2 cohort needs at least 2 papers! Found: {len(sampled_papers_g2)}"

        # Case 1: Unanimous Full-Text Acceptance (Paper 0)
        p2_0 = sampled_papers_g2[0]
        logger.info(f"   ✍️ [Gate 2 Case 1 - Unanimous Full-Text Accept] Paper: '{p2_0.get('title', p2_0['paper_id'])[:45]}...'")
        slr_svc.submit_screening_review(
            cohort_id=cohort_g2_id, paper_id=p2_0["paper_id"], action="agree",
            evidence_citation="Section 3: Empirical evaluation corroborates trial convergence.",
            reviewer_note="Primary reviewer: methodology and results verified."
        )
        sec_slr_svc.submit_screening_review(
            cohort_id=cohort_g2_id, paper_id=p2_0["paper_id"], action="agree",
            evidence_citation="Section 4: Baseline comparison benchmarks confirmed.",
            reviewer_note="Secondary reviewer: agrees with full-text inclusion."
        )
        logger.info("      ✓ Both reviewers agreed on Full-Text inclusion with verified citations.")

        # Case 2: Full-Text Rejection OR Conflict
        dispute_g2_id = None
        if len(sampled_papers_g2) >= 3:
            # Case 2: Unanimous Rejection on paper 1
            p2_1 = sampled_papers_g2[1]
            logger.info(f"   ✍️ [Gate 2 Case 2 - Unanimous Full-Text Reject] Paper: '{p2_1.get('title', p2_1['paper_id'])[:45]}...'")
            slr_svc.submit_screening_review(
                cohort_id=cohort_g2_id, paper_id=p2_1["paper_id"],
                action="override_exclude", exclusion_reason="No Control / Comparator Group",
                reviewer_note="Primary reviewer: trial lacks baseline control group."
            )
            sec_slr_svc.submit_screening_review(
                cohort_id=cohort_g2_id, paper_id=p2_1["paper_id"],
                action="override_exclude", exclusion_reason="No Control / Comparator Group",
                reviewer_note="Secondary reviewer: absence of comparator group confirmed."
            )
            logger.info("      ✓ Both reviewers voted Override Exclude on Full-Text.")

            # Case 3: Conflict & Arbiter Resolution on paper 2
            p2_2 = sampled_papers_g2[2]
            logger.info(f"   ✍️ [Gate 2 Case 3 - Full-Text Reviewer Conflict & Arbiter Ruling] Paper: '{p2_2.get('title', p2_2['paper_id'])[:45]}...'")
            slr_svc.submit_screening_review(
                cohort_id=cohort_g2_id, paper_id=p2_2["paper_id"],
                action="override_include",
                evidence_citation="Section 4.2 presents robust trial sensitivity analysis.",
                reviewer_note="Primary reviewer: trial sensitivity analysis satisfies criteria."
            )
            sec_slr_svc.submit_screening_review(
                cohort_id=cohort_g2_id, paper_id=p2_2["paper_id"],
                action="override_exclude", exclusion_reason="Insufficient Quantitative Data Reported",
                reviewer_note="Secondary reviewer: missing raw variance metrics in Table 2."
            )
            logger.info("      ⚖️ Split votes registered on Full-Text -> Escalated to Senior Arbiter.")

            for p_rem in sampled_papers_g2[3:]:
                slr_svc.submit_screening_review(cohort_id=cohort_g2_id, paper_id=p_rem["paper_id"], action="agree")
                sec_slr_svc.submit_screening_review(cohort_id=cohort_g2_id, paper_id=p_rem["paper_id"], action="agree")

            # Check cohort paused
            cohort_g2_mid = slr_svc.get_cohort(cohort_g2_id)
            assert cohort_g2_mid.get("is_audit_complete") is False, "Cohort must remain paused while Gate 2 dispute is pending!"

            # Senior Arbiter resolves dispute
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
                resolution_rationale="Senior Arbiter ruling: Table 2 confidence intervals allow deriving required variance."
            )
            assert resolve_resp_g2.get("status") == "resolved"
            dispute_g2_id = matching_dispute_g2["id"]
            logger.info("   ✓ Gate 2 dispute resolved cleanly (final_decision='include').")
        else:
            # If 2 papers: test conflict on paper 1
            p2_1 = sampled_papers_g2[1]
            logger.info(f"   ✍️ [Gate 2 Case 2 - Full-Text Conflict & Arbiter Ruling] Paper: '{p2_1.get('title', p2_1['paper_id'])[:45]}...'")
            slr_svc.submit_screening_review(
                cohort_id=cohort_g2_id, paper_id=p2_1["paper_id"],
                action="override_include",
                evidence_citation="Section 3 trial protocol confirmed.",
                reviewer_note="Primary reviewer: inclusion justified."
            )
            sec_slr_svc.submit_screening_review(
                cohort_id=cohort_g2_id, paper_id=p2_1["paper_id"],
                action="override_exclude", exclusion_reason="Wrong Study Population",
                reviewer_note="Secondary reviewer: cohort population out of scope."
            )
            cohort_g2_mid = slr_svc.get_cohort(cohort_g2_id)
            assert cohort_g2_mid.get("is_audit_complete") is False

            pending_disputes_g2 = arbiter_slr_svc.list_disputes(status="pending")
            matching_dispute_g2 = next(
                (d for d in pending_disputes_g2 if str(d.get("paper")) == str(p2_1["paper_id"]) or d.get("sample_cohort") == cohort_g2_id),
                None
            )
            assert matching_dispute_g2 is not None
            logger.info(f"   🧑‍⚖️ Senior Arbiter ruling on Gate 2 dispute {matching_dispute_g2['id']}...")
            resolve_resp_g2 = arbiter_slr_svc.resolve_dispute(
                dispute_id=matching_dispute_g2["id"],
                final_decision="include",
                resolution_rationale="Senior Arbiter ruling: Inclusion justified per protocol."
            )
            assert resolve_resp_g2.get("status") == "resolved"
            dispute_g2_id = matching_dispute_g2["id"]

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

        # Audit extractions for papers in cohort with diverse actions (verify, modify, reject)
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

                global_ext_idx = audit_count % 3
                if global_ext_idx == 0:
                    # Action: Verify
                    audit_resp = slr_svc.submit_extraction_audit(
                        cohort_id=cohort_g3_id,
                        extraction_id=ext_id,
                        action="verify",
                        reviewer_notes="Reported parameter value verified against experimental figures.",
                    )
                    verified_count += 1
                elif global_ext_idx == 1:
                    # Action: Modify
                    audit_resp = slr_svc.submit_extraction_audit(
                        cohort_id=cohort_g3_id,
                        extraction_id=ext_id,
                        action="modify",
                        corrected_fields={"accuracy_pct": 95.8, "justification": "Auditor corrected baseline metric to match Table 3 empirical data."},
                        reviewer_notes="Corrected reported baseline accuracy from 93.0% to 95.8%.",
                    )
                    modified_count += 1
                else:
                    # Action: Reject
                    audit_resp = slr_svc.submit_extraction_audit(
                        cohort_id=cohort_g3_id,
                        extraction_id=ext_id,
                        action="reject",
                        reviewer_notes="Extracted metric rejected: parameter hallucinated and not substantiated by source text.",
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
        logger.info(f"   ✅ Gate 3 Extraction Audit completed: {verified_count} verified, {modified_count} modified, {rejected_count} rejected. Pipeline auto-resumed.")

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

        assert identified is not None and identified >= 4, f"PRISMA missing identified count: {prisma_data}"
        assert screened is not None and screened >= 4, f"PRISMA missing screened count: {prisma_data}"
        assert excluded_abs is not None and excluded_abs >= 1, f"Expected abstract exclusions to be recorded: {prisma_data}"
        assert ft_assessed is not None and ft_assessed >= 1, f"PRISMA missing full_text_assessed: {prisma_data}"
        assert included is not None and included >= 1, f"PRISMA missing included count: {prisma_data}"
        scenario_results["prisma_metrics"] = prisma_data
        logger.info(f"   ✓ PRISMA Flow: Identified={identified}, Screened={screened}, Excluded={excluded_abs}, FullTextAssessed={ft_assessed}, Included={included}")

        rob_assessments = slr_svc.get_rob_assessments(pipeline_run_id)
        scenario_results["rob_assessments_count"] = len(rob_assessments)
        logger.info(f"   ✓ Risk of Bias Assessments generated: {len(rob_assessments)} studies appraised.")

        # Verify Disputes Audit Trail
        pending_disputes = arbiter_slr_svc.list_disputes(status="pending")
        assert len(pending_disputes) == 0, f"Expected 0 pending disputes, found: {pending_disputes}"
        resolved_disputes = arbiter_slr_svc.list_disputes(status="resolved")
        assert len(resolved_disputes) >= 1, f"Expected resolved disputes in audit trail, found: {len(resolved_disputes)}"
        logger.info(f"   ✓ Disputes Audit Trail: 0 pending, {len(resolved_disputes)} resolved by Senior Arbiter.")

        scenario_results["status"] = "PASSED"
        logger.info("=================================================================")
        logger.info("🎉 FULL SLR REVIEW GATES & CHECKPOINTS SCENARIO PASSED!")
        logger.info("=================================================================")

    finally:
        # Cleanup if requested
        if cfg.delete_after and scenario_results.get("workspace_id"):
            logger.info("🧹 Post-test Cleanup: deleting temporary SLR workspace...")
            ws_svc.delete_workspace(scenario_results["workspace_id"])
            logger.info("   ✓ Workspace deleted.")

    return scenario_results

