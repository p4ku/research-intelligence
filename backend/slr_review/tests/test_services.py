import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from research_intelligence.models import (
    Workspace,
    Paper,
    PaperMetric,
    PipelineRun,
    ComponentRun,
)
from slr_review.models import (
    SLRWorkspaceConfig,
    AuditSampleCohort,
    ScreeningReview,
    AdjudicationDispute,
    RiskOfBiasAssessment,
    SLRPRISMAMetrics,
)
from slr_review.services import (
    SamplingService,
    ConsensusService,
    RiskOfBiasService,
    MetricsService,
)
from slr_review.tasks.orchestrator_hooks import (
    intercept_component_completion,
    resume_slr_pipeline_run,
    should_pause_at_gate,
)

User = get_user_model()


class SLRServicesTestCase(TestCase):
    """Test suite for SLR domain services and Celery DAG orchestrator hooks."""

    def setUp(self):
        self.user1 = User.objects.create_user(username='reviewer_a', password='pw1')
        self.user2 = User.objects.create_user(username='reviewer_b', password='pw2')
        self.arbiter = User.objects.create_user(username='arbiter_pi', password='pw3')

        self.workspace = Workspace.objects.create(name="Ebola Vaccine SLR")
        self.config = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace,
            checkpoint_gate_mode='two_stage_split',
            screening_quorum_size=2,
            sampling_mode='uncertainty_stratified',
            abstract_sample_percentage=20.0,
            full_text_sample_percentage=20.0,
            negative_control_percentage=10.0,
            designated_arbiter=self.arbiter
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Run #1",
            status="running"
        )

        # Create a pool of papers with metrics
        self.papers = []
        for i in range(10):
            p = Paper.objects.create(
                workspace=self.workspace,
                hash_id=f"hash_{i}_{uuid.uuid4().hex}",
                title=f"Paper #{i+1} on Ebola Vaccine",
                authors="Author et al.",
                abstract=f"Abstract for paper {i+1}..."
            )
            # 2 borderline, 3 rejected, 5 passed
            if i < 2:
                status = 'borderline'
            elif i < 5:
                status = 'rejected'
            else:
                status = 'abstract_passed'

            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status=status
            )
            self.papers.append(p)

    def test_sampling_service_uncertainty_stratified(self):
        """Verifies uncertainty-stratified sampling captures borderline and negative controls."""
        cohort = SamplingService.generate_sample_cohort(
            pipeline_run=self.pipeline_run,
            stage='abstract_screening',
            seed=42
        )

        self.assertIsInstance(cohort, AuditSampleCohort)
        self.assertEqual(cohort.stage, 'abstract_screening')
        self.assertEqual(cohort.total_pool_count, 10)
        self.assertGreater(cohort.sampled_count, 0)

        sampled_p_ids = set(cohort.sampled_papers.values_list('id', flat=True))
        # Verify both borderline papers were sampled
        borderline_ids = set(PaperMetric.objects.filter(
            pipeline_run=self.pipeline_run,
            screening_status='borderline'
        ).values_list('paper_id', flat=True))
        self.assertTrue(borderline_ids.issubset(sampled_p_ids))

    def test_consensus_service_unanimous_agreement(self):
        """Verifies consensus when 2 reviewers agree on Include."""
        cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='full_text_screening',
            total_pool_count=1,
            sampled_count=1
        )
        paper = self.papers[0]
        cohort.sampled_papers.add(paper)

        # Reviewer 1 votes include
        ConsensusService.record_screening_review(
            sample_cohort=cohort,
            paper=paper,
            reviewer=self.user1,
            stage='full_text',
            decision='include'
        )
        self.assertFalse(cohort.is_audit_complete)

        # Reviewer 2 votes include -> quorum reached and consensus unanimous
        ConsensusService.record_screening_review(
            sample_cohort=cohort,
            paper=paper,
            reviewer=self.user2,
            stage='full_text',
            decision='include'
        )

        cohort.refresh_from_db()
        self.assertTrue(cohort.is_audit_complete)
        self.assertIsNotNone(cohort.completed_at)

    def test_consensus_service_split_vote_creates_dispute(self):
        """Verifies split votes escalate to AdjudicationDispute."""
        cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='full_text_screening',
            total_pool_count=1,
            sampled_count=1
        )
        paper = self.papers[0]
        cohort.sampled_papers.add(paper)

        # Reviewer 1 votes include
        ConsensusService.record_screening_review(
            sample_cohort=cohort,
            paper=paper,
            reviewer=self.user1,
            stage='full_text',
            decision='include'
        )

        # Reviewer 2 votes exclude
        ConsensusService.record_screening_review(
            sample_cohort=cohort,
            paper=paper,
            reviewer=self.user2,
            stage='full_text',
            decision='exclude',
            exclusion_reason='Wrong Population'
        )

        cohort.refresh_from_db()
        # Not complete because dispute is pending
        self.assertFalse(cohort.is_audit_complete)

        dispute = AdjudicationDispute.objects.filter(sample_cohort=cohort, paper=paper).first()
        self.assertIsNotNone(dispute)
        self.assertEqual(dispute.status, 'pending')
        self.assertIn('reviewer_1', list(dispute.evidence_synthesis.keys())[0])

        # Senior arbiter resolves dispute
        ConsensusService.resolve_dispute(
            dispute=dispute,
            arbiter=self.arbiter,
            final_decision='include',
            resolution_rationale='Inclusion justified per Section 3 criteria.'
        )

        dispute.refresh_from_db()
        self.assertEqual(dispute.status, 'resolved')
        self.assertEqual(dispute.final_decision, 'include')

        cohort.refresh_from_db()
        self.assertTrue(cohort.is_audit_complete)

    def test_rob_service_traffic_light(self):
        """Tests Cochrane RoB 2 appraisal and traffic light calculation."""
        scores_low = {
            "D1_randomization": {"rating": "low_risk"},
            "D2_deviations": {"rating": "low_risk"},
            "D3_missing_data": {"rating": "low_risk"},
            "D4_measurement": {"rating": "low_risk"},
            "D5_selection": {"rating": "low_risk"}
        }
        overall, color = RiskOfBiasService.calculate_overall_bias(scores_low)
        self.assertEqual(overall, 'low_risk')
        self.assertEqual(color, 'green')

        scores_concerns = dict(scores_low)
        scores_concerns["D3_missing_data"] = {"rating": "some_concerns"}
        overall, color = RiskOfBiasService.calculate_overall_bias(scores_concerns)
        self.assertEqual(overall, 'some_concerns')
        self.assertEqual(color, 'yellow')

        scores_high = dict(scores_low)
        scores_high["D1_randomization"] = {"rating": "high_risk"}
        overall, color = RiskOfBiasService.calculate_overall_bias(scores_high)
        self.assertEqual(overall, 'high_risk')
        self.assertEqual(color, 'red')

    def test_metrics_service_cohens_kappa(self):
        """Tests Cohen's Kappa calculation on perfect and imperfect agreement."""
        r1 = ['include', 'include', 'exclude', 'exclude', 'include']
        r2 = ['include', 'include', 'exclude', 'exclude', 'include']
        self.assertEqual(MetricsService.calculate_cohens_kappa(r1, r2), 1.0)

        r2_split = ['include', 'exclude', 'exclude', 'include', 'include']
        kappa = MetricsService.calculate_cohens_kappa(r1, r2_split)
        self.assertIsInstance(kappa, float)
        self.assertLess(kappa, 1.0)

    def test_orchestrator_hooks_intercept_and_resume(self):
        """Tests DAG pause interception at Gate 1 and clean resumption."""
        # Run is running
        self.assertEqual(self.pipeline_run.status, 'running')

        # Abstract screening completes -> gate triggers
        res = intercept_component_completion(self.pipeline_run, 'abstract_screening')
        self.assertTrue(res["halt"])

        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, 'paused')
        self.assertIn('awaiting_abstract_screening_audit', self.pipeline_run.current_stage)

        cohort = AuditSampleCohort.objects.get(pk=res["cohort_id"])
        self.assertFalse(cohort.is_audit_complete)

        # Attempting resume before audit is complete should fail
        resume_res = resume_slr_pipeline_run(self.pipeline_run)
        self.assertFalse(resume_res["resumed"])

        # Manually complete cohort to simulate all papers being reviewed
        cohort.is_audit_complete = True
        cohort.save()

        # Resuming now should succeed
        resume_res2 = resume_slr_pipeline_run(self.pipeline_run)
        self.assertTrue(resume_res2["resumed"])

        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, 'running')
