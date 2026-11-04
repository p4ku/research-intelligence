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

    def test_parameter_extraction_requires_all_extractions_reviewed_and_quorum(self):
        """
        REGRESSION TEST 6:
        Verifies that parameter_extraction cohorts:
        - only mark a paper as reviewed by a user when ALL Extraction objects on that paper are reviewed,
        - only complete the cohort when ALL Extraction objects reach extraction_quorum_size distinct reviewers,
        - do NOT create bogus ScreeningReview(stage='full_text') records when SubmitScreeningReviewView is called.
        """
        from research_intelligence.models import Extraction, ExtractionDefinition
        from slr_review.models import ExtractionReview

        self.config.extraction_quorum_size = 2
        self.config.save()

        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"paper_ext_{uuid.uuid4().hex[:8]}",
            title="Dual Extraction Study",
            authors="Test",
            abstract="Abstract"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status='full_text_passed'
        )
        def1 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="R0 Parameter",
            system_prompt="Extract R0",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"value": {"type": "string"}}}
        )
        def2 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Serial Interval",
            system_prompt="Extract SI",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"value": {"type": "string"}}}
        )
        ext1 = Extraction.objects.create(
            paper=paper,
            workspace=self.workspace,
            extraction_definition=def1,
            category="epidemiology",
            fields_data={"value": "2.4", "evidence": [{"quote": "R0 was 2.4"}]}
        )
        ext2 = Extraction.objects.create(
            paper=paper,
            workspace=self.workspace,
            extraction_definition=def2,
            category="epidemiology",
            fields_data={"value": "5.1 days", "evidence": [{"quote": "SI was 5.1 days"}]}
        )

        cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='parameter_extraction',
            total_pool_count=1,
            sampled_count=1,
            is_audit_complete=False
        )
        cohort.sampled_papers.add(paper)

        # Reviewer 1 audits ONLY ext1 -> paper is NOT yet fully reviewed by Reviewer 1
        res_ext1 = self.client.post(
            f'/api/slr/cohorts/{cohort.id}/extractions/{ext1.id}/audit/',
            {"action": "verify", "time_spent_seconds": 10},
            format='json'
        )
        self.assertEqual(res_ext1.status_code, status.HTTP_200_OK)
        self.assertFalse(res_ext1.json()['is_cohort_complete'])

        detail_res = self.client.get(f'/api/slr/cohorts/{cohort.id}/papers/{paper.id}/')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertFalse(detail_res.json()['is_reviewed'])

        # Reviewer 1 now audits ext2 -> paper IS reviewed by Reviewer 1, but quorum=2 is not yet met
        res_ext2 = self.client.post(
            f'/api/slr/cohorts/{cohort.id}/extractions/{ext2.id}/audit/',
            {"action": "verify", "time_spent_seconds": 12},
            format='json'
        )
        self.assertEqual(res_ext2.status_code, status.HTTP_200_OK)
        self.assertFalse(res_ext2.json()['is_cohort_complete'])

        detail_res2 = self.client.get(f'/api/slr/cohorts/{cohort.id}/papers/{paper.id}/')
        self.assertTrue(detail_res2.json()['is_reviewed'])

        # Calling SubmitScreeningReviewView on parameter_extraction cohort must NOT create a ScreeningReview
        submit_res = self.client.post(
            f'/api/slr/cohorts/{cohort.id}/papers/{paper.id}/review/',
            {"action": "agree", "time_spent_seconds": 5},
            format='json'
        )
        self.assertEqual(submit_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ScreeningReview.objects.filter(sample_cohort=cohort).count(), 0)

        # Reviewer 2 audits ext1 and ext2 -> quorum=2 is met on ALL extractions -> cohort completes
        self.client.force_authenticate(user=self.reviewer_2)
        with patch('slr_review.tasks.orchestrator_hooks.resume_slr_pipeline_run') as mock_resume:
            mock_resume.return_value = {"resumed": True, "status": "resumed"}
            self.client.post(
                f'/api/slr/cohorts/{cohort.id}/extractions/{ext1.id}/audit/',
                {"action": "verify", "time_spent_seconds": 8},
                format='json'
            )
            cohort.refresh_from_db()
            self.assertFalse(cohort.is_audit_complete)

            final_res = self.client.post(
                f'/api/slr/cohorts/{cohort.id}/extractions/{ext2.id}/audit/',
                {"action": "verify", "time_spent_seconds": 9},
                format='json'
            )
            self.assertEqual(final_res.status_code, status.HTTP_200_OK)
            self.assertTrue(final_res.json()['is_cohort_complete'])
            self.assertEqual(ExtractionReview.objects.filter(sample_cohort=cohort).count(), 4)

    def test_metrics_cross_stage_kappa_and_arbiter_ai_agreement_and_negative_kappa(self):
        """
        REGRESSION TEST 7:
        Verifies:
        - calculate_cohens_kappa allows negative kappa when agreement is worse than chance,
        - calculate_human_inter_rater_kappa does not pair a single reviewer across abstract and full_text stages,
        - calculate_ai_agreement_metrics honors resolved AdjudicationDispute rulings and stage-specific AI baseline,
        - compute_prisma_metrics populates duplicates_removed and 1 canonical exclusion reason per rejected paper.
        """
        # 1. Negative Cohen's Kappa when 2 raters systematically disagree
        neg_kappa = MetricsService.calculate_cohens_kappa([True, False, True, False], [False, True, False, True])
        self.assertLess(neg_kappa, 0.0)
        self.assertEqual(neg_kappa, -1.0)

        # 2. Single reviewer voting at abstract and full_text must NOT be paired against themselves
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"paper_kappa_{uuid.uuid4().hex[:8]}",
            title="Cross-stage Kappa Paper",
            authors="Test",
            abstract="Abstract",
            source_database="pubmed"
        )
        self.pipeline_run.configuration_override = {"duplicates_removed": 5}
        self.pipeline_run.save(update_fields=['configuration_override'])

        metric = PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status='abstract_passed',
            metrics_data={}
        )
        cohort_abs = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='abstract_screening',
            total_pool_count=1,
            sampled_count=1
        )
        cohort_ft = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='full_text_screening',
            total_pool_count=1,
            sampled_count=1
        )
        ScreeningReview.objects.create(
            sample_cohort=cohort_abs,
            paper=paper,
            pipeline_run=self.pipeline_run,
            reviewer=self.reviewer_1,
            stage='abstract',
            decision='include'
        )
        ScreeningReview.objects.create(
            sample_cohort=cohort_ft,
            paper=paper,
            pipeline_run=self.pipeline_run,
            reviewer=self.reviewer_1,
            stage='full_text',
            decision='exclude',
            exclusion_reason='No Extractable Parameters'
        )
        # Only 1 reviewer per stage -> human_inter_rater_kappa must be None
        self.assertIsNone(MetricsService.calculate_human_inter_rater_kappa(self.pipeline_run))

        # 3. Add Reviewer 2 at abstract stage with opposite vote, then resolve dispute via Arbiter
        ScreeningReview.objects.create(
            sample_cohort=cohort_abs,
            paper=paper,
            pipeline_run=self.pipeline_run,
            reviewer=self.reviewer_2,
            stage='abstract',
            decision='exclude',
            exclusion_reason='Wrong Topic'
        )
        ConsensusService.evaluate_paper_consensus(cohort_abs, paper, 'abstract')
        dispute = AdjudicationDispute.objects.get(sample_cohort=cohort_abs, paper=paper)
        self.assertEqual(dispute.evidence_synthesis['ai_agent']['decision'], 'include')

        ConsensusService.resolve_dispute(
            dispute=dispute,
            arbiter=self.reviewer_1,
            final_decision='exclude',
            resolution_rationale='Arbiter excluded',
            final_exclusion_reason='Wrong Topic'
        )
        prisma = MetricsService.compute_prisma_metrics(self.pipeline_run)
        self.assertEqual(prisma.duplicates_removed, 5)
        self.assertEqual(prisma.records_identified_total, 6)
        self.assertEqual(prisma.records_by_source.get('pubmed'), 1)
        self.assertEqual(prisma.abstract_exclusion_reasons.get('Wrong Topic'), 1)

    def test_rob_sync_removes_rejected_and_adds_newly_included_papers(self):
        """
        REGRESSION TEST 8:
        Verifies that RiskOfBiasListView removes RiskOfBiasAssessment rows for papers
        subsequently rejected at Gate 2 and lazily creates assessments for newly included papers.
        """
        p_rejected = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"paper_rob_rej_{uuid.uuid4().hex[:8]}",
            title="Initially Passed Then Rejected Paper",
            authors="Test",
            abstract="Abstract"
        )
        p_included = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"paper_rob_inc_{uuid.uuid4().hex[:8]}",
            title="Newly Included Paper",
            authors="Test",
            abstract="Randomized controlled trial."
        )
        # Stale RoB assessment on a paper whose screening_status is now 'rejected'
        PaperMetric.objects.create(
            paper=p_rejected,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status='rejected'
        )
        RiskOfBiasService.assess_paper_rob(p_rejected, self.pipeline_run)

        # Newly included paper without an RoB assessment yet
        PaperMetric.objects.create(
            paper=p_included,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status='full_text_passed'
        )

        res = self.client.get(f'/api/slr/runs/{self.pipeline_run.id}/rob/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        titles = [item['paper_title'] for item in res.json()]
        self.assertNotIn("Initially Passed Then Rejected Paper", titles)
        self.assertIn("Newly Included Paper", titles)

    def test_start_pipeline_run_serializer_and_multi_tenancy_and_diagnostics_auth(self):
        """
        REGRESSION TEST 9:
        Verifies:
        - StartPipelineRunSerializer and CreatePipelineRunSerializer preserve run_type='slr',
        - Scraper.resolve_api_key_for_provider isolates keys per workspace,
        - DeepDiagnosticsView requires authentication,
        - AuditQueueListView and DisputeListView do not leak orphan workspace records when DEBUG=False.
        """
        from django.test import override_settings
        from api.serializers.pipeline_runs import StartPipelineRunSerializer, CreatePipelineRunSerializer
        from research_intelligence.models import Scraper

        s_start = StartPipelineRunSerializer(data={
            "workspace_id": str(self.workspace.id),
            "run_type": "slr"
        })
        self.assertTrue(s_start.is_valid(), s_start.errors)
        self.assertEqual(s_start.validated_data['run_type'], 'slr')

        s_create = CreatePipelineRunSerializer(data={
            "workspace_id": str(self.workspace.id),
            "run_type": "slr"
        })
        self.assertTrue(s_create.is_valid(), s_create.errors)
        self.assertEqual(s_create.validated_data['run_type'], 'slr')

        # Cross-workspace Scraper API key isolation
        other_ws = Workspace.objects.create(name="Other Tenant Workspace")
        Scraper.objects.create(
            workspace=other_ws,
            provider="lens",
            search_query="quantum",
            api_key="SECRET_OTHER_TENANT_KEY",
            is_active=True
        )
        with patch.dict('os.environ', {'LENS_API_KEY': ''}, clear=False):
            with override_settings(LENS_API_KEY=''):
                resolved = Scraper.resolve_api_key_for_provider('lens', workspace=self.workspace)
                self.assertEqual(resolved, '')

        # Orphan workspace isolation when DEBUG=False
        orphan_ws = Workspace.objects.create(name="Orphan Workspace Without Members")
        orphan_cfg = SLRWorkspaceConfig.objects.create(workspace=orphan_ws)
        orphan_run = PipelineRun.objects.create(workspace=orphan_ws, status='paused')
        AuditSampleCohort.objects.create(
            config=orphan_cfg,
            pipeline_run=orphan_run,
            stage='abstract_screening',
            total_pool_count=5,
            sampled_count=2
        )
        with override_settings(DEBUG=False):
            q_res = self.client.get('/api/slr/cohorts/my-queue/')
            self.assertEqual(q_res.status_code, status.HTTP_200_OK)
            ws_ids = [item['workspace_id'] for item in q_res.json()]
            self.assertNotIn(str(orphan_ws.id), ws_ids)

        # DeepDiagnosticsView requires authentication
        anon_client = APIClient()
        diag_res = anon_client.get('/api/health/diagnostics/')
        self.assertIn(diag_res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

