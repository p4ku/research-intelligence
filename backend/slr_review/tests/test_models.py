import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.core.exceptions import ValidationError

from research_intelligence.models import (
    Workspace,
    Paper,
    PipelineRun,
    ExtractionDefinition,
    Extraction,
)
from slr_review.models import (
    SLRWorkspaceConfig,
    SLRProtocol,
    ProtocolAmendment,
    AuditSampleCohort,
    ScreeningReview,
    ExtractionReview,
    AdjudicationDispute,
    RiskOfBiasAssessment,
    SLRPRISMAMetrics,
    SearchQueryRecord,
    MetaAnalysisOutcomeData,
    get_default_exclusion_reasons,
)

User = get_user_model()


class SLRModelsTestCase(TestCase):
    """Unit tests for all SLR Review models."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='reviewer_1',
            email='reviewer1@example.com',
            password='testpassword123'
        )
        self.arbiter_user = User.objects.create_user(
            username='arbiter_lead',
            email='arbiter@example.com',
            password='testpassword123'
        )
        self.workspace = Workspace.objects.create(
            name="Lassa Fever Therapeutics SLR"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="SLR Run #1 - Lassa",
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="dummyhash1234567890abcdef1234567890abcdef1234567890abcdef12345678",
            doi="10.1016/j.jbi.2026.100001",
            title="Efficacy of Favipiravir in Lassa Fever: A Randomized Trial",
            authors="Smith J., Doe A.",
            abstract="We evaluated oral favipiravir versus placebo in adult patients with acute Lassa fever."
        )

    def test_slr_workspace_config_defaults_and_str(self):
        """Tests SLRWorkspaceConfig creation, default values, and string formatting."""
        config = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace,
            designated_arbiter=self.arbiter_user
        )

        self.assertIsInstance(config.id, uuid.UUID)
        self.assertEqual(config.checkpoint_gate_mode, 'two_stage_split')
        self.assertTrue(config.enable_extraction_gate)
        self.assertEqual(config.screening_quorum_size, 2)
        self.assertEqual(config.extraction_quorum_size, 1)
        self.assertTrue(config.require_blind_review)
        self.assertEqual(config.sampling_mode, 'uncertainty_stratified')
        self.assertEqual(config.abstract_sample_percentage, 10.0)
        self.assertEqual(config.full_text_sample_percentage, 20.0)
        self.assertEqual(config.extraction_sample_percentage, 10.0)
        self.assertEqual(config.negative_control_percentage, 5.0)
        self.assertTrue(config.enable_rob_assessment)
        self.assertEqual(config.rob_framework, 'auto_detect')
        self.assertTrue(config.require_human_rob_validation)
        self.assertEqual(config.designated_arbiter, self.arbiter_user)
        self.assertEqual(config.tie_breaker_strategy, 'arbiter_ruling')
        self.assertTrue(config.require_evidence_on_exclusion)
        self.assertTrue(config.require_evidence_on_override)
        self.assertTrue(config.notify_reviewers_on_pause)
        self.assertEqual(config.stale_queue_reminder_days, 3)

        # Exclusion reasons list defaults
        self.assertGreater(len(config.exclusion_reasons), 0)
        self.assertIn("Wrong Study Population", config.exclusion_reasons)

        # __str__ representation
        self.assertIn("Lassa Fever Therapeutics SLR", str(config))
        self.assertIn("two_stage_split", str(config))

        # Related name from workspace
        self.assertEqual(self.workspace.slr_config, config)

    def test_slr_protocol_and_amendments(self):
        """Tests SLRProtocol and ProtocolAmendment models."""
        protocol = SLRProtocol.objects.create(
            workspace=self.workspace,
            title="Systematic Review of Antiviral Therapy in Lassa Fever",
            review_question="Does favipiravir reduce 28-day mortality in hospitalized Lassa fever patients?",
            pico_population="Hospitalized patients with RT-PCR confirmed Lassa fever",
            pico_intervention="Favipiravir or ribavirin therapy",
            pico_comparison="Standard supportive care or placebo",
            pico_outcome="28-day all-cause mortality, viral clearance time",
            study_design_criteria="Randomized controlled trials, prospective cohort studies",
            prospero_registration_id="CRD42026123456",
            is_locked=True,
            version=1,
            created_by=self.user
        )

        self.assertIsInstance(protocol.id, uuid.UUID)
        self.assertEqual(protocol.workspace, self.workspace)
        self.assertTrue(protocol.is_locked)
        self.assertIn("LOCKED", str(protocol))
        self.assertIn("CRD42026123456", protocol.prospero_registration_id)

        # Test protocol amendment
        amendment = ProtocolAmendment.objects.create(
            protocol=protocol,
            amendment_number=1,
            rationale="Added secondary endpoint for renal replacement therapy requirement.",
            changes_diff={"pico_outcome": {"old": "28-day mortality", "new": "28-day mortality + RRT"}},
            approved_by=self.arbiter_user
        )
        self.assertIsInstance(amendment.id, uuid.UUID)
        self.assertEqual(amendment.protocol, protocol)
        self.assertEqual(protocol.amendments.count(), 1)
        self.assertIn("Amendment #1", str(amendment))

    def test_audit_sample_cohort(self):
        """Tests AuditSampleCohort creation, M2M paper linking, and status tracking."""
        config = SLRWorkspaceConfig.objects.create(workspace=self.workspace)
        cohort = AuditSampleCohort.objects.create(
            config=config,
            pipeline_run=self.pipeline_run,
            stage='full_text_screening',
            total_pool_count=100,
            sampled_count=10,
            sampling_strategy={"mode": "uncertainty_stratified", "percentage": 10.0}
        )

        cohort.sampled_papers.add(self.paper)
        self.assertEqual(cohort.sampled_papers.count(), 1)
        self.assertFalse(cohort.is_audit_complete)
        self.assertIn("full_text_screening", str(cohort))
        self.assertIn("10/100", str(cohort))

        # Complete cohort
        cohort.is_audit_complete = True
        cohort.save()
        self.assertTrue(cohort.is_audit_complete)

    def test_screening_review_blind_vote_and_quotes(self):
        """Tests ScreeningReview model with verbatim quotes and unique constraints."""
        config = SLRWorkspaceConfig.objects.create(workspace=self.workspace)
        cohort = AuditSampleCohort.objects.create(
            config=config,
            pipeline_run=self.pipeline_run,
            stage='abstract_screening',
            total_pool_count=50,
            sampled_count=5
        )

        evidence = [
            {
                "quote": "Favipiravir was administered at 1800mg BID on day 1...",
                "page_number": 3,
                "section": "Methods / Dosage",
                "annotation_type": "eligibility_confirmation"
            }
        ]

        review = ScreeningReview.objects.create(
            sample_cohort=cohort,
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            reviewer=self.user,
            stage='abstract',
            decision='include',
            evidence_quotes=evidence,
            time_spent_seconds=45
        )

        self.assertIsInstance(review.id, uuid.UUID)
        self.assertEqual(review.decision, 'include')
        self.assertEqual(len(review.evidence_quotes), 1)
        self.assertEqual(review.evidence_quotes[0]["page_number"], 3)
        self.assertIn("INCLUDE", str(review))

        # Enforce unique together (same cohort, paper, reviewer, stage)
        with self.assertRaises(IntegrityError):
            ScreeningReview.objects.create(
                sample_cohort=cohort,
                paper=self.paper,
                pipeline_run=self.pipeline_run,
                reviewer=self.user,
                stage='abstract',
                decision='exclude'
            )

    def test_extraction_review(self):
        """Tests ExtractionReview model with verified and modified fields."""
        config = SLRWorkspaceConfig.objects.create(workspace=self.workspace)
        cohort = AuditSampleCohort.objects.create(
            config=config,
            pipeline_run=self.pipeline_run,
            stage='parameter_extraction',
            total_pool_count=20,
            sampled_count=5
        )

        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Clinical Outcomes",
            system_prompt="Extract outcomes",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"mortality_rate": {"type": "number"}}}
        )

        extraction = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=ext_def,
            category="clinical_trial",
            fields_data={"mortality_rate": 0.14, "sample_size": 120}
        )

        ext_review = ExtractionReview.objects.create(
            sample_cohort=cohort,
            paper=self.paper,
            extraction=extraction,
            reviewer=self.user,
            action='modify',
            original_fields={"mortality_rate": 0.14},
            corrected_fields={"mortality_rate": 0.12},
            verified_evidence_quotes=[{"quote": "12 out of 100 died (12%)", "page_number": 5}],
            reviewer_notes="Table 2 shows 12% rather than 14%. Corrected.",
            time_spent_seconds=90
        )

        self.assertIsInstance(ext_review.id, uuid.UUID)
        self.assertEqual(ext_review.action, 'modify')
        self.assertEqual(ext_review.corrected_fields["mortality_rate"], 0.12)
        self.assertIn("MODIFY", str(ext_review))

    def test_adjudication_dispute(self):
        """Tests AdjudicationDispute formed on split votes and resolved by arbiter."""
        config = SLRWorkspaceConfig.objects.create(workspace=self.workspace)
        cohort = AuditSampleCohort.objects.create(
            config=config,
            pipeline_run=self.pipeline_run,
            stage='full_text_screening',
            total_pool_count=40,
            sampled_count=8
        )

        dispute = AdjudicationDispute.objects.create(
            sample_cohort=cohort,
            paper=self.paper,
            stage='full_text',
            status='pending',
            evidence_synthesis={
                "reviewer_1": {"decision": "include", "quote": "All patients were randomized"},
                "reviewer_2": {"decision": "exclude", "reason": "Wrong Population"}
            }
        )

        self.assertEqual(dispute.status, 'pending')
        self.assertIn("PENDING", str(dispute))

        # Arbiter resolves dispute
        dispute.arbiter = self.arbiter_user
        dispute.final_decision = 'include'
        dispute.resolution_rationale = "Paper meets all inclusion criteria. Reviewer 2 misclassified adult cohort."
        dispute.status = 'resolved'
        dispute.save()

        self.assertEqual(dispute.status, 'resolved')
        self.assertEqual(dispute.final_decision, 'include')
        self.assertIn("RESOLVED", str(dispute))

    def test_risk_of_bias_assessment(self):
        """Tests RiskOfBiasAssessment with Cochrane RoB 2 domain scoring."""
        domain_scores = {
            "D1_randomization": {"rating": "low_risk", "quote": "Computer-generated sequence", "page": 2},
            "D2_deviations": {"rating": "low_risk", "quote": "Double-blind allocation", "page": 3},
            "D3_missing_data": {"rating": "some_concerns", "quote": "8% lost to follow-up", "page": 5},
            "D4_measurement": {"rating": "low_risk", "quote": "Standardized PCR protocol", "page": 4},
            "D5_selection": {"rating": "low_risk", "quote": "Pre-registered protocol", "page": 2}
        }

        rob = RiskOfBiasAssessment.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            framework='rob2',
            domain_scores=domain_scores,
            overall_bias='some_concerns',
            traffic_light_color='yellow'
        )

        self.assertIsInstance(rob.id, uuid.UUID)
        self.assertEqual(rob.framework, 'rob2')
        self.assertEqual(rob.overall_bias, 'some_concerns')
        self.assertEqual(rob.traffic_light_color, 'yellow')
        self.assertFalse(rob.is_human_verified)
        self.assertIn("RoB (rob2)", str(rob))

        # Test human verification
        rob.is_human_verified = True
        rob.verified_by = self.arbiter_user
        rob.human_notes = "Verified domain ratings; some concerns on attrition is justified."
        rob.save()

        self.assertTrue(rob.is_human_verified)
        self.assertEqual(rob.verified_by, self.arbiter_user)

    def test_slr_prisma_metrics(self):
        """Tests SLRPRISMAMetrics flow counters and Cohen's Kappa reliability."""
        prisma = SLRPRISMAMetrics.objects.create(
            pipeline_run=self.pipeline_run,
            records_identified_total=1250,
            records_by_source={"pubmed": 600, "openalex": 450, "arxiv": 200},
            duplicates_removed=180,
            records_screened_abstract=1070,
            records_excluded_abstract=890,
            abstract_exclusion_reasons={"Wrong Population": 520, "Animal Study": 370},
            full_text_assessed=180,
            full_text_excluded=140,
            full_text_exclusion_reasons={"No Control Group": 95, "Insufficient Data": 45},
            studies_included_synthesis=40,
            studies_included_meta_analysis=25,
            human_inter_rater_kappa=0.88,
            ai_vs_human_kappa=0.82,
            ai_sensitivity=0.96,
            ai_specificity=0.91
        )

        self.assertIsInstance(prisma.id, uuid.UUID)
        self.assertEqual(prisma.records_identified_total, 1250)
        self.assertEqual(prisma.studies_included_synthesis, 40)
        self.assertEqual(prisma.human_inter_rater_kappa, 0.88)
        self.assertEqual(prisma.ai_sensitivity, 0.96)
        self.assertIn("40 Studies Included", str(prisma))

    def test_search_query_record(self):
        """Tests SearchQueryRecord for search strategy auditability."""
        protocol = SLRProtocol.objects.create(
            workspace=self.workspace,
            title="Lassa Protocol",
            review_question="Favipiravir efficacy",
            pico_population="Lassa",
            pico_intervention="Favipiravir",
            pico_comparison="Placebo",
            pico_outcome="Mortality",
            created_by=self.user
        )

        sq = SearchQueryRecord.objects.create(
            protocol=protocol,
            database_name="PubMed",
            raw_query_string='("Lassa fever"[tiab] OR "Lassa virus"[MeSH]) AND ("favipiravir"[tiab] OR "T-705"[tiab])',
            filters_applied={"date_min": "2015-01-01", "date_max": "2026-10-01", "humans_only": True},
            total_yield=420
        )

        self.assertIsInstance(sq.id, uuid.UUID)
        self.assertEqual(sq.total_yield, 420)
        self.assertEqual(sq.protocol, protocol)
        self.assertIn("PubMed search", str(sq))

    def test_meta_analysis_outcome_data(self):
        """Tests MetaAnalysisOutcomeData continuous and dichotomous schemas."""
        outcome = MetaAnalysisOutcomeData.objects.create(
            paper=self.paper,
            outcome_name="28-Day Mortality",
            outcome_type="dichotomous",
            int_sample_size=60,
            int_events=6,
            ctrl_sample_size=60,
            ctrl_events=18,
            effect_size_estimate=0.33,
            ci_lower=0.14,
            ci_upper=0.78,
            p_value=0.012
        )

        self.assertIsInstance(outcome.id, uuid.UUID)
        self.assertEqual(outcome.outcome_type, "dichotomous")
        self.assertEqual(outcome.effect_size_estimate, 0.33)
        self.assertIn("28-Day Mortality", str(outcome))
