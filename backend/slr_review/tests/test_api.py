import uuid
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
)

User = get_user_model()


class SLRRestAPITestCase(TestCase):
    """Test suite for SLR Review REST API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='reviewer_1', password='testpassword123')
        self.arbiter = User.objects.create_user(username='arbiter_pi', password='testpassword123')
        self.client.force_authenticate(user=self.user)

        self.workspace = Workspace.objects.create(name="Lassa Therapeutics SLR")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.arbiter, role="admin")

        self.config = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace,
            screening_quorum_size=1,  # 1 for solo fast-track test
            designated_arbiter=self.arbiter
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="SLR Run #1",
            status="paused",
            current_stage="awaiting_full_text_screening_audit"
        )

        self.paper1 = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"hash_1_{uuid.uuid4().hex}",
            title="Favipiravir Clinical Trial",
            authors="Smith et al.",
            abstract="Evaluated 120 patients with acute Lassa fever."
        )
        self.paper2 = Paper.objects.create(
            workspace=self.workspace,
            hash_id=f"hash_2_{uuid.uuid4().hex}",
            title="Ribavirin in Guinea",
            authors="Doe et al.",
            abstract="Retrospective study on Ribavirin therapy."
        )

        # AI metrics
        PaperMetric.objects.create(
            paper=self.paper1,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status='full_text_passed',
            full_text_screening_reasoning="Clinical trial in human patients.",
            metrics_data={"confidence": 0.95, "matched_criteria": ["Human", "Lassa"]}
        )
        PaperMetric.objects.create(
            paper=self.paper2,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status='rejected',
            full_text_screening_reasoning="Animal study only.",
            metrics_data={"confidence": 0.88, "matched_criteria": ["Animal"]}
        )

        # Create cohort with 2 papers
        self.cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage='full_text_screening',
            total_pool_count=2,
            sampled_count=2
        )
        self.cohort.sampled_papers.add(self.paper1, self.paper2)

    def test_audit_queue_list(self):
        """Tests GET /api/slr/cohorts/my-queue/."""
        response = self.client.get('/api/slr/cohorts/my-queue/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)
        item = data[0]
        self.assertEqual(item['cohort_id'], str(self.cohort.id))
        self.assertEqual(item['assigned_count'], 2)
        self.assertEqual(item['completed_count'], 0)
        self.assertEqual(item['remaining_count'], 2)
        self.assertEqual(item['status'], 'pending')

    def test_audit_paper_detail_payload(self):
        """Tests GET /api/slr/cohorts/{id}/papers/{pid}/ dual-pane data."""
        url = f'/api/slr/cohorts/{self.cohort.id}/papers/{self.paper1.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data['title'], "Favipiravir Clinical Trial")
        self.assertEqual(data['ai_decision'], 'include')
        self.assertEqual(data['ai_confidence'], 0.95)
        self.assertIn("Clinical trial", data['ai_reasoning'])
        self.assertFalse(data['is_reviewed'])
        self.assertEqual(data['current_index'], 1)
        self.assertEqual(data['total_count'], 2)
        self.assertIsNotNone(data['next_paper_id'])

    def test_submit_screening_review_agree_and_auto_advance(self):
        """Tests POST /api/slr/cohorts/{id}/papers/{pid}/review/ with Agree action."""
        url = f'/api/slr/cohorts/{self.cohort.id}/papers/{self.paper1.id}/review/'
        payload = {
            "action": "agree",
            "time_spent_seconds": 30
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertFalse(data['is_cohort_complete'])  # 1 of 2 papers reviewed
        self.assertEqual(data['next_paper_id'], str(self.paper2.id))
        self.assertEqual(data['completed_count'], 1)

        # Check recorded review
        review = ScreeningReview.objects.get(sample_cohort=self.cohort, paper=self.paper1)
        self.assertEqual(review.decision, 'include')
        self.assertEqual(review.reviewer, self.user)

    def test_submit_screening_review_override_exclude(self):
        """Tests override to Exclude requiring an exclusion reason."""
        url = f'/api/slr/cohorts/{self.cohort.id}/papers/{self.paper1.id}/review/'
        # Missing exclusion reason should fail
        bad_payload = {"action": "override_exclude"}
        bad_res = self.client.post(url, bad_payload, format='json')
        self.assertEqual(bad_res.status_code, status.HTTP_400_BAD_REQUEST)

        good_payload = {
            "action": "override_exclude",
            "exclusion_reason": "No Control Group",
            "reviewer_note": "Paper lacks a placebo or comparator arm.",
            "evidence_citation": "Page 2: all patients received open-label drug."
        }
        good_res = self.client.post(url, good_payload, format='json')
        self.assertEqual(good_res.status_code, status.HTTP_200_OK)

        review = ScreeningReview.objects.get(sample_cohort=self.cohort, paper=self.paper1)
        self.assertEqual(review.decision, 'exclude')
        self.assertEqual(review.exclusion_reason, "No Control Group")

    def test_full_cohort_review_and_resume_pipeline(self):
        """Verifies review of all papers flips cohort to complete and resumes pipeline."""
        # Review paper 1
        self.client.post(
            f'/api/slr/cohorts/{self.cohort.id}/papers/{self.paper1.id}/review/',
            {"action": "agree"},
            format='json'
        )
        # Review paper 2
        res2 = self.client.post(
            f'/api/slr/cohorts/{self.cohort.id}/papers/{self.paper2.id}/review/',
            {"action": "agree"},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        data = res2.json()
        self.assertTrue(data['is_cohort_complete'])

        self.cohort.refresh_from_db()
        self.assertTrue(self.cohort.is_audit_complete)

        # Pipeline run automatically resumes to running
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.status, 'running')

    def test_prisma_metrics_endpoint(self):
        """Tests GET /api/slr/runs/{run_id}/prisma/."""
        response = self.client.get(f'/api/slr/runs/{self.pipeline_run.id}/prisma/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('records_identified_total', data)
        self.assertEqual(data['records_identified_total'], 2)
