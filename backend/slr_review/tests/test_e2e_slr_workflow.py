import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Paper,
    PaperMetric,
    PipelineRun,
    UserActivityLog,
)
from slr_review.models import (
    SLRWorkspaceConfig,
    AuditSampleCohort,
    ScreeningReview,
    AdjudicationDispute,
    SLRPRISMAMetrics,
)
from slr_review.tasks.orchestrator_hooks import intercept_component_completion

User = get_user_model()


class SLREndToEndWorkflowTestCase(TestCase):
    """
    Comprehensive End-to-End Test for the Systematic Literature Review (SLR) HITL Engine.
    Executes the entire lifecycle step by step exclusively via REST API and orchestrator hooks:
      1. Corpus Ingestion & Realistic Paper Fixtures (Clear Includes, Clear Excludes, Borderlines, Negative Controls)
      2. Checkpoint Gate Interception & Uncertainty-Stratified Subsampling
      3. Reviewer 1 (Dr. Smith) Queue Retrieval & Blind Review Voting
      4. Reviewer 2 (Dr. Jones) Blind Dual-Review Voting & Conflict Detection (Dispute Generation)
      5. Senior Arbiter Dispute Inspection (Evidence Synthesis) & Binding Resolution
      6. Cohort Finalization & Automated Celery DAG Pipeline Resumption
      7. PRISMA 2020 Statement Generation & Cohen's Kappa Statistical Reliability Calculation
      8. Immutable Audit Trails Verification (UserActivityLog, Blind Review Logs, Dispute History)
    """

    def setUp(self):
        # 1. Setup API Client & Reviewers
        self.client = APIClient()

        self.reviewer_alpha = User.objects.create_user(
            username='dr_smith_screener1',
            email='smith@research.org',
            password='Password123!'
        )
        self.reviewer_beta = User.objects.create_user(
            username='dr_jones_screener2',
            email='jones@research.org',
            password='Password123!'
        )
        self.senior_arbiter = User.objects.create_user(
            username='prof_vance_arbiter',
            email='vance@research.org',
            password='Password123!'
        )

        # 2. Setup Dedicated SLR Workspace
        self.workspace = Workspace.objects.create(
            name="Lassa Virus Therapeutics SLR 2026",
            screening_llm_model="gpt-4o"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.reviewer_alpha, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.reviewer_beta, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.senior_arbiter, role="admin")

        # 3. Setup SLR Workspace Policy Config
        self.slr_config = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace,
            checkpoint_gate_mode='two_stage_split',
            screening_quorum_size=2,  # Dual blind review
            sampling_mode='uncertainty_stratified',
            abstract_sample_percentage=40.0,
            negative_control_percentage=20.0,
            tie_breaker_strategy='arbiter_adjudication',
            designated_arbiter=self.senior_arbiter,
        )

        # 4. Setup Pipeline Run
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="SLR Lassa Systematic Review Run #1",
            status="running",
            current_stage="abstract_screening",
            configuration_override={"run_type": "slr"}
        )

        # 5. Populate Realistic Paper Corpus Fixtures (10 Papers)
        self._populate_paper_corpus()

    def _populate_paper_corpus(self):
        """Creates 10 diverse papers simulating automated search ingestion & AI screening."""
        self.papers = []
        self.metrics = []

        paper_defs = [
            # Paper 0: Clear Include 1 (RCT in humans)
            {
                "title": "Efficacy of Favipiravir in Human Lassa Fever Cohort: Double-Blind RCT",
                "authors": "Smith, J., Traore, M., Diallo, A.",
                "journal": "The Lancet Infectious Diseases",
                "year": 2024,
                "doi": "10.1016/S1473-3099(24)00112-1",
                "abstract": "We conducted a double-blind, randomized controlled trial evaluating favipiravir versus ribavirin in 142 adult human patients hospitalized with confirmed Lassa fever.",
                "ai_status": "abstract_passed",
                "confidence": 0.96,
                "reasoning": "Eligible human randomized controlled trial with active comparator and standardized clinical outcome measures.",
                "matched": ["Human Cohort", "Lassa Virus", "Antiviral Therapy", "Randomized Controlled Trial"],
                "quotes": [{"quote": "142 adult human patients hospitalized with confirmed Lassa fever", "page_number": 1}],
                "exclusion_reason": None,
            },
            # Paper 1: Clear Include 2 (Multicenter trial)
            {
                "title": "Ribavirin and Monoclonal Antibodies in Acute Lassa: A Controlled Cohort",
                "authors": "Okonkwo, P., Conteh, I., Brown, K.",
                "journal": "New England Journal of Medicine",
                "year": 2025,
                "doi": "10.1056/NEJMoa2408991",
                "abstract": "Prospective cohort study investigating monoclonal antibody cocktail therapy compared to historical ribavirin control in acute severe Lassa virus infection.",
                "ai_status": "abstract_passed",
                "confidence": 0.94,
                "reasoning": "Prospective human study with comparator and therapeutic intervention against Lassa virus.",
                "matched": ["Human Cohort", "Lassa Virus", "Monoclonal Antibodies", "Controlled Study"],
                "quotes": [{"quote": "Prospective cohort study investigating monoclonal antibody cocktail", "page_number": 1}],
                "exclusion_reason": None,
            },
            # Paper 2: Clear Exclude 1 (Animal study)
            {
                "title": "Pharmacokinetics of Favipiravir in Cynomolgus Macaques Infected with Arenavirus",
                "authors": "Macleod, R., Bauer, T.",
                "journal": "Journal of Virology",
                "year": 2023,
                "doi": "10.1128/jvi.00445-23",
                "abstract": "Non-human primate pharmacokinetic modeling of favipiravir dosing regimens in cynomolgus macaques.",
                "ai_status": "rejected",
                "confidence": 0.98,
                "reasoning": "Exclusively an animal model study (cynomolgus macaques); no human subjects evaluated.",
                "matched": ["Animal Model"],
                "quotes": [{"quote": "in cynomolgus macaques", "page_number": 1}],
                "exclusion_reason": "Animal / In-Vitro Model (Non-Human)",
            },
            # Paper 3: Clear Exclude 2 (In-vitro plaque assay)
            {
                "title": "In-Vitro Plaque Reduction Neutralization Assays of Small Molecules Against Arenaviridae",
                "authors": "Zhang, W., Li, H.",
                "journal": "Antiviral Research",
                "year": 2023,
                "doi": "10.1016/j.antiviral.2023.105589",
                "abstract": "Vero E6 cell culture screening of novel nucleoside analogues against Lassa Josiah strain.",
                "ai_status": "rejected",
                "confidence": 0.99,
                "reasoning": "Cell culture assay without clinical or in-vivo therapeutic validation.",
                "matched": ["In-Vitro Assay"],
                "quotes": [{"quote": "Vero E6 cell culture screening", "page_number": 1}],
                "exclusion_reason": "Animal / In-Vitro Model (Non-Human)",
            },
            # Paper 4: Clear Exclude 3 (Reservoir epidemiology)
            {
                "title": "Ecological and Rodent Reservoir Surveillance of Mastomys natalensis in Sierra Leone",
                "authors": "Kamara, B., Sesay, F.",
                "journal": "Emerging Microbes & Infections",
                "year": 2022,
                "doi": "10.1080/22221751.2022.2045561",
                "abstract": "Field surveillance of rodent host reservoirs in Kenema district; no antiviral intervention tested.",
                "ai_status": "rejected",
                "confidence": 0.97,
                "reasoning": "Observational animal reservoir ecology; does not test any medical intervention.",
                "matched": ["Epidemiological Survey"],
                "quotes": [{"quote": "Field surveillance of rodent host reservoirs", "page_number": 1}],
                "exclusion_reason": "Off-Target Intervention / Method",
            },
            # Paper 5: Borderline Paper (Controversial Case Series - Candidates for Dual-Review Split)
            {
                "title": "Compassionate Remdesivir Treatment in West African Viral Hemorrhagic Fevers",
                "authors": "Dupont, G., Toure, S.",
                "journal": "Clinical Infectious Diseases",
                "year": 2024,
                "doi": "10.1093/cid/ciae104",
                "abstract": "Retrospective case series of 14 patients treated with remdesivir under emergency access protocol. Lacks parallel control arm.",
                "ai_status": "borderline",
                "confidence": 0.64,
                "reasoning": "Human patients with confirmed disease, but uncontrolled emergency series with uncertain comparator validity.",
                "matched": ["Human Cohort", "Antiviral Therapy"],
                "quotes": [{"quote": "Retrospective case series of 14 patients treated with remdesivir", "page_number": 2}],
                "exclusion_reason": None,
            },
            # Paper 6: Borderline Paper 2 (Matched cohort missing standard outcomes)
            {
                "title": "Convalescent Immune Plasma Administration in Hospitalized Arenavirus Infection",
                "authors": "Tshibangu, N., Koffi, J.",
                "journal": "Transfusion Medicine",
                "year": 2024,
                "doi": "10.1111/tme.13024",
                "abstract": "Small observational cohort comparing 18 plasma recipients with matched supportive care.",
                "ai_status": "borderline",
                "confidence": 0.69,
                "reasoning": "Small sample size with non-randomized allocation, borderline quantitative outcome metrics.",
                "matched": ["Human Cohort", "Plasma Therapy"],
                "quotes": [{"quote": "comparing 18 plasma recipients with matched supportive care", "page_number": 1}],
                "exclusion_reason": None,
            },
            # Paper 7: Passed Candidate 3
            {
                "title": "Phase II Safety and Tolerability of Humanized Nanobody L9 against Lassa Virus",
                "authors": "Mendez, L., Sanchez, E.",
                "journal": "Journal of Clinical Investigation",
                "year": 2025,
                "doi": "10.1172/JCI178921",
                "abstract": "Phase II clinical trial evaluating dose-escalation safety of monoclonal antibody L9 in healthy volunteers and acute patients.",
                "ai_status": "abstract_passed",
                "confidence": 0.92,
                "reasoning": "Human Phase II clinical safety and efficacy evaluation.",
                "matched": ["Human Cohort", "Phase II Clinical Trial"],
                "quotes": [{"quote": "Phase II clinical trial evaluating dose-escalation safety", "page_number": 1}],
                "exclusion_reason": None,
            },
            # Paper 8: Passed Candidate 4
            {
                "title": "Combined Interferon-Beta and Ribavirin in Severe Arenaviral Disease",
                "authors": "Bamba, K., Sylla, C.",
                "journal": "Antiviral Therapy",
                "year": 2024,
                "doi": "10.3851/IMP3422",
                "abstract": "Open-label randomized trial testing combination therapy versus monotherapy in 88 patients.",
                "ai_status": "abstract_passed",
                "confidence": 0.91,
                "reasoning": "Randomized comparative study with human patients.",
                "matched": ["Human Cohort", "Randomized Trial"],
                "quotes": [{"quote": "Open-label randomized trial testing combination therapy", "page_number": 1}],
                "exclusion_reason": None,
            },
            # Paper 9: Clear Exclude 4 (Negative Control candidate - In-Silico Docking)
            {
                "title": "High-Throughput In-Silico Molecular Docking of Lassa Glycoprotein Inhibitors",
                "authors": "Gupta, R., Sharma, V.",
                "journal": "Journal of Molecular Graphics & Modelling",
                "year": 2023,
                "doi": "10.1016/j.jmgm.2023.108455",
                "abstract": "Computational docking of 500,000 compound libraries against Lassa GP1 structure without laboratory assays.",
                "ai_status": "rejected",
                "confidence": 0.99,
                "reasoning": "Exclusively computational in-silico simulation; no biological or clinical data.",
                "matched": ["In-Silico Simulation"],
                "quotes": [{"quote": "Computational docking of 500,000 compound libraries", "page_number": 1}],
                "exclusion_reason": "Off-Target Intervention / Method",
            },
        ]

        for p_def in paper_defs:
            paper = Paper.objects.create(
                workspace=self.workspace,
                hash_id=f"hash_{uuid.uuid4().hex[:16]}",
                title=p_def["title"],
                authors=p_def["authors"],
                abstract=p_def["abstract"],
                doi=p_def["doi"],
                original_pdf_path=f"storage/papers/{p_def['doi'].replace('/', '_')}.pdf",
                source_database="pubmed",
                meta={"journal": p_def["journal"], "year": p_def["year"]}
            )
            metric = PaperMetric.objects.create(
                paper=paper,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status=p_def["ai_status"],
                abstract_screening_reasoning=p_def["reasoning"],
                metrics_data={
                    "confidence": p_def["confidence"],
                    "matched_criteria": p_def["matched"],
                    "evidence_quotes": p_def["quotes"],
                    "exclusion_reason": p_def["exclusion_reason"]
                }
            )
            self.papers.append(paper)
            self.metrics.append(metric)

    def test_complete_slr_lifecycle_end_to_end(self):
        """
        Executes and validates the end-to-end SLR process step-by-step.
        """
        # =========================================================================
        # STEP 1: DAG Checkpoint Gate Interception & Uncertainty-Stratified Sampling
        # =========================================================================
        interception = intercept_component_completion(self.pipeline_run, 'abstract_screening')
        self.assertTrue(interception["halt"], "Pipeline DAG should be halted at abstract_screening gate.")
        self.assertIn("cohort_id", interception)
        cohort_id = interception["cohort_id"]

        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, "paused", "PipelineRun must be set to 'paused'.")
        self.assertEqual(self.pipeline_run.current_stage, "awaiting_abstract_screening_audit")
        self.assertTrue(self.pipeline_run.status_message.startswith("Awaiting audit (0/"))

        cohort = AuditSampleCohort.objects.get(id=cohort_id)
        self.assertFalse(cohort.is_audit_complete)
        sampled_papers = list(cohort.sampled_papers.all())
        sampled_ids = {p.id for p in sampled_papers}

        # Verify Uncertainty-Stratified Subsampling:
        # Both borderline papers (Paper 5 and Paper 6) MUST be sampled (100% of borderline cases)
        self.assertIn(self.papers[5].id, sampled_ids, "Borderline Paper 5 must be sampled.")
        self.assertIn(self.papers[6].id, sampled_ids, "Borderline Paper 6 must be sampled.")
        # At least one negative control (AI-rejected paper) must be sampled
        rejected_ids = {self.papers[2].id, self.papers[3].id, self.papers[4].id, self.papers[9].id}
        sampled_negatives = sampled_ids.intersection(rejected_ids)
        self.assertGreaterEqual(len(sampled_negatives), 1, "Must sample at least one negative control.")
        # Total sampled count conforms to config target
        self.assertGreaterEqual(len(sampled_papers), 3)

        # =========================================================================
        # STEP 2: Reviewer 1 (Dr. Smith) Queue Retrieval & Detail Inspection
        # =========================================================================
        self.client.force_authenticate(user=self.reviewer_alpha)

        # 2a. Fetch active audit queue
        resp_queue = self.client.get('/api/slr/cohorts/my-queue/')
        self.assertEqual(resp_queue.status_code, status.HTTP_200_OK)
        queue_data = resp_queue.json()
        self.assertEqual(len(queue_data), 1)
        self.assertEqual(queue_data[0]["cohort_id"], str(cohort.id))
        self.assertEqual(queue_data[0]["status"], "pending")
        self.assertEqual(queue_data[0]["completed_count"], 0)
        self.assertEqual(queue_data[0]["assigned_count"], len(sampled_papers))

        # 2b. Fetch cohort navigation overview
        resp_cohort = self.client.get(f'/api/slr/cohorts/{cohort.id}/')
        self.assertEqual(resp_cohort.status_code, status.HTTP_200_OK)
        cohort_data = resp_cohort.json()
        self.assertEqual(cohort_data["total_papers"], len(sampled_papers))
        self.assertIsNotNone(cohort_data["first_unreviewed_paper_id"])

        # 2c. Inspect individual paper details for the first sampled paper
        first_sampled = sampled_papers[0]
        resp_paper = self.client.get(f'/api/slr/cohorts/{cohort.id}/papers/{first_sampled.id}/')
        self.assertEqual(resp_paper.status_code, status.HTTP_200_OK)
        paper_detail = resp_paper.json()
        self.assertEqual(paper_detail["title"], first_sampled.title)
        self.assertFalse(paper_detail["is_reviewed"])
        self.assertIsNotNone(paper_detail["pdf_url"])
        self.assertTrue(paper_detail["has_full_text"])

        # =========================================================================
        # STEP 3: Reviewer 1 (Dr. Smith) Submits Votes for All Sampled Papers
        # =========================================================================
        for p in sampled_papers:
            if p.id == self.papers[5].id:
                # Reviewer 1 votes 'override_include' on Borderline Paper 5
                resp = self.client.post(
                    f'/api/slr/cohorts/{cohort.id}/papers/{p.id}/review/',
                    data={
                        "action": "override_include",
                        "reviewer_note": "Includes 14 emergency PCR human cases with documented viral load clearance.",
                        "evidence_citation": "case series of 14 patients treated with remdesivir",
                        "time_spent_seconds": 90
                    },
                    format='json'
                )
            else:
                # Agree with AI
                resp = self.client.post(
                    f'/api/slr/cohorts/{cohort.id}/papers/{p.id}/review/',
                    data={"action": "agree", "time_spent_seconds": 35},
                    format='json'
                )
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertFalse(resp.json()["is_cohort_complete"], "Quorum is 2, cohort cannot be complete yet.")

        # Check queue status for Reviewer 1: should now show completed for him
        resp_q1 = self.client.get('/api/slr/cohorts/my-queue/')
        self.assertEqual(resp_q1.json()[0]["completed_count"], len(sampled_papers))
        self.assertEqual(resp_q1.json()[0]["status"], "completed")

        # But cohort overall is NOT complete because Reviewer 2 hasn't voted yet!
        cohort.refresh_from_db()
        self.assertFalse(cohort.is_audit_complete)
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, "paused")

        # =========================================================================
        # STEP 4: Reviewer 2 (Dr. Jones) Blind Dual-Review & Dispute Triggering
        # =========================================================================
        self.client.force_authenticate(user=self.reviewer_beta)

        for p in sampled_papers:
            if p.id == self.papers[5].id:
                # Reviewer 2 votes 'override_exclude' on Borderline Paper 5 -> Conflict / Dispute!
                resp = self.client.post(
                    f'/api/slr/cohorts/{cohort.id}/papers/{p.id}/review/',
                    data={
                        "action": "override_exclude",
                        "exclusion_reason": "No Control / Comparator Group",
                        "reviewer_note": "Lacks any control arm or comparator baseline. High risk of selection bias.",
                        "evidence_citation": "Lacks parallel control arm.",
                        "time_spent_seconds": 80
                    },
                    format='json'
                )
            else:
                # Agree with AI -> Unanimous agreement with Reviewer 1
                resp = self.client.post(
                    f'/api/slr/cohorts/{cohort.id}/papers/{p.id}/review/',
                    data={"action": "agree", "time_spent_seconds": 30},
                    format='json'
                )
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Quorum is reached on all papers, but Paper 5 has an active pending dispute!
        # Cohort must NOT complete until Senior Arbiter resolves the dispute.
        cohort.refresh_from_db()
        self.assertFalse(cohort.is_audit_complete, "Cohort cannot complete while an adjudication dispute is pending.")
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, "paused")

        # =========================================================================
        # STEP 5: Senior Arbiter Adjudication via REST API
        # =========================================================================
        self.client.force_authenticate(user=self.senior_arbiter)

        # 5a. Fetch pending disputes
        resp_disputes = self.client.get('/api/slr/disputes/?status=pending')
        self.assertEqual(resp_disputes.status_code, status.HTTP_200_OK)
        disputes_list = resp_disputes.json()
        self.assertEqual(len(disputes_list), 1, "Exactly one dispute must be pending.")
        dispute = disputes_list[0]
        self.assertEqual(dispute["paper"], str(self.papers[5].id))

        # 5b. Inspect Evidence Synthesis
        synth = dispute["evidence_synthesis"]
        self.assertIn("ai_agent", synth)
        self.assertTrue(any("smith" in k for k in synth.keys()))
        self.assertTrue(any("jones" in k for k in synth.keys()))

        # 5c. Senior Arbiter issues binding ruling: EXCLUDE with rationale
        dispute_id = dispute["id"]
        resp_resolve = self.client.post(
            f'/api/slr/disputes/{dispute_id}/resolve/',
            data={
                "final_decision": "exclude",
                "final_exclusion_reason": "No Control / Comparator Group",
                "resolution_rationale": "Per SLR Protocol Section 3.2, uncontrolled case series without comparator are excluded from synthesis."
            },
            format='json'
        )
        self.assertEqual(resp_resolve.status_code, status.HTTP_200_OK)
        resolved_dispute = resp_resolve.json()
        self.assertEqual(resolved_dispute["status"], "resolved")
        self.assertEqual(resolved_dispute["final_decision"], "exclude")

        # Verify PaperMetric for Paper 5 was updated according to Arbiter's ruling
        m5 = PaperMetric.objects.get(paper=self.papers[5], pipeline_run=self.pipeline_run)
        self.assertEqual(m5.screening_status, "rejected")
        self.assertEqual(m5.metrics_data.get("human_exclusion_reason"), "No Control / Comparator Group")
        self.assertEqual(m5.metrics_data.get("original_ai_screening_status"), "borderline")

        # =========================================================================
        # STEP 6: Automated Cohort Finalization & Pipeline Resumption
        # =========================================================================
        cohort.refresh_from_db()
        self.assertTrue(cohort.is_audit_complete, "Cohort must be marked complete once dispute is resolved.")
        self.assertIsNotNone(cohort.completed_at)

        # PipelineRun was automatically woken up and resumed
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, "running", "PipelineRun must be resumed to 'running'.")
        self.assertEqual(self.pipeline_run.status_message, "Audit completed. Resuming pipeline...")

        # =========================================================================
        # STEP 7: PRISMA 2020 Flow Statement & Reliability Agreement Metrics
        # =========================================================================
        resp_prisma = self.client.get(f'/api/slr/runs/{self.pipeline_run.id}/prisma/')
        self.assertEqual(resp_prisma.status_code, status.HTTP_200_OK)
        prisma_data = resp_prisma.json()

        # Check PRISMA counts
        self.assertEqual(prisma_data["records_identified_total"], 10)
        self.assertEqual(prisma_data["records_screened_abstract"], 10)
        self.assertGreaterEqual(prisma_data["records_excluded_abstract"], 5)
        # Check exclusion reasons tally includes human arbiter reason
        reasons = prisma_data["abstract_exclusion_reasons"]
        self.assertIn("No Control / Comparator Group", reasons)
        self.assertIn("Animal / In-Vitro Model (Non-Human)", reasons)

        # Check Reliability Metrics
        self.assertIsNotNone(prisma_data["human_inter_rater_kappa"])
        self.assertGreaterEqual(prisma_data["human_inter_rater_kappa"], 0.0)
        self.assertLessEqual(prisma_data["human_inter_rater_kappa"], 1.0)

        self.assertIsNotNone(prisma_data["ai_vs_human_kappa"])
        self.assertIsNotNone(prisma_data["ai_sensitivity"])
        self.assertIsNotNone(prisma_data["ai_specificity"])

        # =========================================================================
        # STEP 8: Immutable Audit Trails & Activity Logs Verification
        # =========================================================================
        # 8a. UserActivityLog entries for API calls
        target_users = [self.reviewer_alpha, self.reviewer_beta, self.senior_arbiter]
        logs = list(UserActivityLog.objects.filter(user__in=target_users))
        self.assertGreaterEqual(len(logs), 10, "Activity log must record all REST API interactions.")
        
        usernames_logged = {l.user_username for l in logs}
        self.assertIn(self.reviewer_alpha.username, usernames_logged)
        self.assertIn(self.reviewer_beta.username, usernames_logged)
        self.assertIn(self.senior_arbiter.username, usernames_logged)

        actions_logged = {l.action_name for l in logs}
        self.assertTrue(any("my-queue" in a for a in actions_logged))
        self.assertTrue(any("review" in a for a in actions_logged))
        self.assertTrue(any("resolve" in a for a in actions_logged))

        # 8b. ScreeningReview audit trails
        reviews = list(ScreeningReview.objects.filter(sample_cohort=cohort))
        self.assertEqual(len(reviews), len(sampled_papers) * 2, "Each sampled paper must have exactly 2 independent reviews.")
        for r in reviews:
            self.assertIsNotNone(r.submitted_at)
            self.assertIn(r.decision, ['include', 'exclude', 'uncertain'])

        # 8c. AdjudicationDispute audit trails
        adjudication = AdjudicationDispute.objects.get(sample_cohort=cohort, paper=self.papers[5])
        self.assertEqual(adjudication.status, "resolved")
        self.assertEqual(adjudication.arbiter, self.senior_arbiter)
        self.assertEqual(adjudication.final_decision, "exclude")
        self.assertIsNotNone(adjudication.resolved_at)
        self.assertIn("Section 3.2", adjudication.resolution_rationale)
