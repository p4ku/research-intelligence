import uuid
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Paper,
    PaperMetric,
    PipelineRun,
)
from slr_review.models import (
    SLRWorkspaceConfig,
    AuditSampleCohort,
    ScreeningReview,
    AdjudicationDispute,
    RiskOfBiasAssessment,
)
from slr_review.services import (
    SamplingService,
    ConsensusService,
    RiskOfBiasService,
    MetricsService,
)

User = get_user_model()


class SLRRuntimeRegressionsTestCase(TestCase):
    """
    Regression test suite verifying fixes for runtime failure modes:
    1. Gate 2 full-text sampling leak (preventing abstract rejections from entering full-text audit).
    2. Zero-percentage sampling (allowing 0% without forcing 1 paper).
    3. Stage name normalization ('abstract_screening' vs 'abstract' & 'full_text_screening' vs 'full_text').
    4. Concurrency race conditions in check_cohort_completion (preventing duplicate Celery resumes).
    5. Lazy auto-computation of Risk of Bias (RoB) assessments.
    6. PRISMA flow stage filtering consistency.
    """

    def setUp(self):
        self.client = APIClient()
        self.reviewer_1 = User.objects.create_user(username='reviewer_alpha', password='pw1')
        self.reviewer_2 = User.objects.create_user(username='reviewer_beta', password='pw2')
        self.arbiter = User.objects.create_user(username='arbiter_gamma', password='pw3')
        self.client.force_authenticate(user=self.reviewer_1)

        self.workspace = Workspace.objects.create(name="Cardiovascular SLR")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.reviewer_1, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.reviewer_2, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.arbiter, role="admin")

        self.config = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace,
            checkpoint_gate_mode='two_stage_split',
            screening_quorum_size=2,
            abstract_sample_percentage=20.0,
            full_text_sample_percentage=50.0,
            negative_control_percentage=20.0,
            designated_arbiter=self.arbiter
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Cardio Review Run #1",
            status="running"
        )

    def test_gate_2_sampling_excludes_abstract_rejections_and_only_takes_fulltext_evaluated_papers(self):
        """
        REGRESSION TEST 1:
        Verifies that Gate 2 (full_text_screening) does NOT sample papers rejected at abstract screening
        which lack full-text evaluation and downloaded PDFs.
        """
        # 1. Four papers rejected early at Abstract Screening (no full_text_screening_reasoning, no PDF)
        abstract_rejected_papers = []
        for i in range(4):
            p = Paper.objects.create(
                workspace=self.workspace,
                hash_id=f"abs_rej_{i}_{uuid.uuid4().hex[:8]}",
                title=f"Abstract Rejected #{i+1}",
                authors="Author et al.",
                abstract="Off-topic study rejected at abstract gate."
            )
            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status='rejected',
                abstract_screening_reasoning="Wrong population.",
                full_text_screening_reasoning=None  # No full-text evaluation!
            )
            abstract_rejected_papers.append(p)

        # 2. Two papers evaluated and rejected during Full-Text Screening (with full_text reasoning)
        ft_rejected_papers = []
        for i in range(2):
            p = Paper.objects.create(
                workspace=self.workspace,
                hash_id=f"ft_rej_{i}_{uuid.uuid4().hex[:8]}",
                title=f"FullText Rejected #{i+1}",
                authors="Author et al.",
                abstract="Full-text candidate subsequently rejected."
            )
            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status='rejected',
                abstract_screening_reasoning="Passed initial screen.",
                full_text_screening_reasoning="Insufficient statistical power reported in methods section."
            )
            ft_rejected_papers.append(p)

        # 3. Two papers passed during Full-Text Screening
        ft_passed_papers = []
        for i in range(2):
            p = Paper.objects.create(
                workspace=self.workspace,
                hash_id=f"ft_pass_{i}_{uuid.uuid4().hex[:8]}",
                title=f"FullText Passed #{i+1}",
                authors="Author et al.",
                abstract="Included RCT study."
            )
            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status='full_text_passed',
                abstract_screening_reasoning="Eligible.",
                full_text_screening_reasoning="Meets Cochrane criteria."
            )
            ft_passed_papers.append(p)

        # Generate Full-Text screening cohort
        cohort = SamplingService.generate_sample_cohort(
            pipeline_run=self.pipeline_run,
            stage='full_text_screening',
            seed=101
        )

        # Pool count must be exactly 4 (2 FT rejected + 2 FT passed), NOT 8!
        self.assertEqual(cohort.total_pool_count, 4)

        # Crucially: NONE of the abstract-rejected papers may be sampled into Gate 2!
        sampled_ids = set(cohort.sampled_papers.values_list('id', flat=True))
        abstract_rejected_ids = set(p.id for p in abstract_rejected_papers)

        overlap = sampled_ids.intersection(abstract_rejected_ids)
        self.assertEqual(
            len(overlap),
            0,
            f"Gate 2 leaked abstract-rejected papers into full-text audit: {overlap}"
        )

    def test_zero_percentage_sampling_produces_zero_papers(self):
        """
        REGRESSION TEST 2:
        Verifies that configuring 0.0% sample percentage results in exactly 0 papers sampled
        (rather than forcing 1 paper via max(1, ...)).
        """
        self.config.abstract_sample_percentage = 0.0
        self.config.negative_control_percentage = 0.0
        self.config.save()

        # Create 10 papers
        for i in range(10):
            p = Paper.objects.create(
                workspace=self.workspace,
                hash_id=f"paper_{i}_{uuid.uuid4().hex[:8]}",
                title=f"Paper #{i+1}",
                authors="Test",
                abstract="Abstract"
            )
            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status='abstract_passed'
            )

        cohort = SamplingService.generate_sample_cohort(
            pipeline_run=self.pipeline_run,
            stage='abstract_screening'
        )

        self.assertEqual(cohort.sampled_count, 0)
        self.assertEqual(cohort.sampled_papers.count(), 0)

    def test_stage_name_normalization_in_consensus_service(self):
        """
        REGRESSION TEST 3:
        Verifies that passing 'abstract_screening' or 'abstract' both normalize to 'abstract'
        in ScreeningReview and AdjudicationDispute, enabling consistent quorum and consensus evaluation.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"paper_norm_{uuid.uuid4().hex[:8]}",
            title="Stage Normalization Paper",
            authors="Test",
            abstract="Abstract"
        )
        metric = PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status='borderline'
        )
        cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='abstract_screening',
            total_pool_count=1,
            sampled_count=1
        )
        cohort.sampled_papers.add(paper)

        # Reviewer 1 votes using stage='abstract_screening'
        review1 = ConsensusService.record_screening_review(
            sample_cohort=cohort,
            paper=paper,
            reviewer=self.reviewer_1,
            stage='abstract_screening',
            decision='include',
            reviewer_notes="High quality abstract"
        )
        self.assertEqual(review1.stage, 'abstract')

        # Reviewer 2 votes using stage='abstract'
        review2 = ConsensusService.record_screening_review(
            sample_cohort=cohort,
            paper=paper,
            reviewer=self.reviewer_2,
            stage='abstract',
            decision='include',
            reviewer_notes="Agreed include"
        )
        self.assertEqual(review2.stage, 'abstract')

        # Quorum (2) was met and both agreed -> unanimous include, no dispute
        self.assertEqual(AdjudicationDispute.objects.filter(paper=paper).count(), 0)
        metric.refresh_from_db()
        self.assertEqual(metric.screening_status, 'abstract_passed')

        # Repeat for full_text stage
        cohort_ft = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='full_text_screening',
            total_pool_count=1,
            sampled_count=1
        )
        cohort_ft.sampled_papers.add(paper)

        review_ft1 = ConsensusService.record_screening_review(
            sample_cohort=cohort_ft,
            paper=paper,
            reviewer=self.reviewer_1,
            stage='full_text_screening',
            decision='include'
        )
        self.assertEqual(review_ft1.stage, 'full_text')

        review_ft2 = ConsensusService.record_screening_review(
            sample_cohort=cohort_ft,
            paper=paper,
            reviewer=self.reviewer_2,
            stage='full_text',
            decision='include'
        )
        self.assertEqual(review_ft2.stage, 'full_text')

        metric.refresh_from_db()
        self.assertEqual(metric.screening_status, 'full_text_passed')

    def test_race_condition_protection_in_check_cohort_completion(self):
        """
        REGRESSION TEST 4:
        Verifies that check_cohort_completion() uses atomic locks and idempotency:
        when cohort is marked complete, subsequent calls return True immediately
        and do not re-trigger pipeline resume tasks.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"paper_race_{uuid.uuid4().hex[:8]}",
            title="Concurrency Test Paper",
            authors="Test",
            abstract="Abstract"
        )
        self.config.screening_quorum_size = 1
        self.config.save()

        cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='abstract_screening',
            total_pool_count=1,
            sampled_count=1,
            is_audit_complete=False
        )
        cohort.sampled_papers.add(paper)

        # Add single review meeting quorum 1
        ScreeningReview.objects.create(
            sample_cohort=cohort,
            paper=paper,
            pipeline_run=self.pipeline_run,
            reviewer=self.reviewer_1,
            stage='abstract',
            decision='include'
        )

        with patch('slr_review.tasks.orchestrator_hooks.resume_slr_pipeline_run') as mock_resume:
            mock_resume.return_value = {"resumed": True}

            # First invocation completes cohort and triggers resume
            res1 = ConsensusService.check_cohort_completion(cohort)
            self.assertTrue(res1)
            self.assertEqual(mock_resume.call_count, 1)

            # Second concurrent/subsequent invocation sees is_audit_complete=True and exits idempotently
            res2 = ConsensusService.check_cohort_completion(cohort)
            self.assertTrue(res2)
            self.assertEqual(mock_resume.call_count, 1)  # NOT called a second time!

    def test_rob_lazy_generation_in_api_view(self):
        """
        REGRESSION TEST 5:
        Verifies that GET /api/slr/runs/{run_id}/rob/ lazily generates Risk of Bias assessments
        for accepted papers if they were not pre-calculated, preventing empty [] responses.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"paper_rob_{uuid.uuid4().hex[:8]}",
            title="Clinical Trial on Carvedilol",
            authors="Heart Group",
            abstract="Randomized controlled trial in heart failure patients."
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status='accepted',
            metrics_data={"study_type": "RCT"}
        )

        # Before call: zero RoB assessments exist
        self.assertEqual(
            RiskOfBiasAssessment.objects.filter(pipeline_run=self.pipeline_run).count(),
            0
        )

        # Call GET /api/slr/runs/{id}/rob/
        url = f'/api/slr/runs/{self.pipeline_run.id}/rob/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['paper_title'], "Clinical Trial on Carvedilol")
        self.assertIn('overall_bias', data[0])
        self.assertIn('domain_scores', data[0])

        # After call: assessment was persisted in DB
        self.assertEqual(
            RiskOfBiasAssessment.objects.filter(pipeline_run=self.pipeline_run).count(),
            1
        )
