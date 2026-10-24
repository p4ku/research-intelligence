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
)
from slr_review.models import (
    SLRWorkspaceConfig,
    AuditSampleCohort,
    ScreeningReview,
    AdjudicationDispute,
)
from slr_review.services import ConsensusService

User = get_user_model()


class SLRAuditPerformanceAndSecurityTestCase(TestCase):
    """
    Dedicated tests verifying:
    1. Performance: Eliminating N+1 queries in check_cohort_completion using single aggregation
    2. Quorum boundary conditions: Partial quorum, open disputes blocking completion
    3. Security: Strict blind review isolation (zero cross-reviewer data leakage)
    4. Security: IDOR rejection when attempting to review foreign papers
    5. Security: RBAC enforcement on dispute resolution & replay attack prevention
    """

    def setUp(self):
        self.client = APIClient()
        self.user_a = User.objects.create_user(username='reviewer_alpha', password='pw1')
        self.user_b = User.objects.create_user(username='reviewer_beta', password='pw2')
        self.arbiter = User.objects.create_user(username='senior_arbiter', password='pw3')
        self.unauthorized_user = User.objects.create_user(username='outsider', password='pw4')

        self.workspace = Workspace.objects.create(name="Audit Security & Perf Lab")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user_a, role='member')
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user_b, role='member')
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.arbiter, role='admin')

        self.config = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace,
            screening_quorum_size=2,
            designated_arbiter=self.arbiter,
            tie_breaker_strategy='designated_arbiter'
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="SLR Audit Run",
            status="paused",
            current_stage="awaiting_abstract_screening_audit"
        )

        # Create 10 papers
        self.papers = []
        for i in range(10):
            p = Paper.objects.create(
                workspace=self.workspace,
                hash_id=f"hash_perf_{i}_{uuid.uuid4().hex}",
                title=f"Oncology Article #{i+1}",
                authors="Researcher et al.",
                abstract=f"Trial results for cohort #{i+1}."
            )
            PaperMetric.objects.create(
                paper=p,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status='abstract_passed',
                abstract_screening_reasoning="Clinical evidence."
            )
            self.papers.append(p)

        self.cohort = AuditSampleCohort.objects.create(
            config=self.config,
            pipeline_run=self.pipeline_run,
            stage="abstract_screening",
            total_pool_count=10,
            sampled_count=10
        )
        self.cohort.sampled_papers.add(*self.papers)

    def test_n_plus_one_elimination_in_cohort_completion(self):
        """
        PERFORMANCE AUDIT TEST:
        Demonstrates that check_cohort_completion executes in a constant O(1) number of queries
        rather than O(N) queries for N sampled papers.
        """
        # User A votes on all 10 papers
        for p in self.papers:
            ScreeningReview.objects.create(
                sample_cohort=self.cohort,
                paper=p,
                pipeline_run=self.pipeline_run,
                reviewer=self.user_a,
                stage="abstract",
                decision="include"
            )

        # User B votes on 9 out of 10 papers
        for p in self.papers[:9]:
            ScreeningReview.objects.create(
                sample_cohort=self.cohort,
                paper=p,
                pipeline_run=self.pipeline_run,
                reviewer=self.user_b,
                stage="abstract",
                decision="include"
            )

        # Before optimization, this would run 1 query for sampled_papers + 10 count queries in loop = 11+ queries.
        # With single aggregate Count + HAVING and select_for_update lock, it evaluates quorum in exactly 1 aggregate query (+ savepoint and lock overhead).
        with self.assertNumQueries(5):  # 2 savepoint queries + 1 locked cohort/config + 1 sampled_papers + 1 aggregate quorum check
            is_complete = ConsensusService.check_cohort_completion(self.cohort)
            self.assertFalse(is_complete)

        # Now complete the 10th paper
        ScreeningReview.objects.create(
            sample_cohort=self.cohort,
            paper=self.papers[9],
            pipeline_run=self.pipeline_run,
            reviewer=self.user_b,
            stage="abstract",
            decision="include"
        )

        # Test finalization
        is_complete = ConsensusService.check_cohort_completion(self.cohort)
        self.assertTrue(is_complete)

        self.cohort.refresh_from_db()
        self.assertTrue(self.cohort.is_audit_complete)
        self.assertIsNotNone(self.cohort.completed_at)

    def test_pending_dispute_blocks_cohort_completion_even_with_full_votes(self):
        """
        AUDIT LOGIC TEST:
        Ensures that even if all papers reached required vote count,
        any unresolved dispute strictly blocks cohort finalization.
        """
        # Create votes with split decision on paper 0
        for p in self.papers:
            ScreeningReview.objects.create(
                sample_cohort=self.cohort,
                paper=p,
                pipeline_run=self.pipeline_run,
                reviewer=self.user_a,
                stage="abstract",
                decision="include"
            )

        for idx, p in enumerate(self.papers):
            decision = "exclude" if idx == 0 else "include"
            ScreeningReview.objects.create(
                sample_cohort=self.cohort,
                paper=p,
                pipeline_run=self.pipeline_run,
                reviewer=self.user_b,
                stage="abstract",
                decision=decision,
                exclusion_reason="Wrong Population" if idx == 0 else None
            )

        # Escalates split vote on paper 0 to dispute
        ConsensusService.evaluate_paper_consensus(self.cohort, self.papers[0], "abstract")

        # Quorum is reached on all 10 papers (each has 2 votes), but dispute is pending
        is_complete = ConsensusService.check_cohort_completion(self.cohort)
        self.assertFalse(is_complete)
        self.cohort.refresh_from_db()
        self.assertFalse(self.cohort.is_audit_complete)

        # Now resolve the dispute
        dispute = AdjudicationDispute.objects.get(sample_cohort=self.cohort, paper=self.papers[0])
        ConsensusService.resolve_dispute(
            dispute=dispute,
            arbiter=self.arbiter,
            final_decision="include",
            resolution_rationale="Inclusion confirmed."
        )

        # Now cohort should be completed
        self.cohort.refresh_from_db()
        self.assertTrue(self.cohort.is_audit_complete)

    def test_blind_review_prevents_peer_leakage(self):
        """
        SECURITY AUDIT TEST:
        Confirms that reviewer B cannot see reviewer A's decision, notes, or exclusion reasons
        when fetching paper details via GET /api/slr/cohorts/{id}/papers/{paper_id}/.
        """
        target_paper = self.papers[0]

        # Reviewer A submits a detailed negative assessment
        ScreeningReview.objects.create(
            sample_cohort=self.cohort,
            paper=target_paper,
            pipeline_run=self.pipeline_run,
            reviewer=self.user_a,
            stage="abstract",
            decision="exclude",
            exclusion_reason="In-Vitro / Lab Only",
            reviewer_notes="CONFIDENTIAL_NOTE_FROM_REVIEWER_A: Patient numbers were fabricated in vitro.",
            evidence_quotes=[{"quote": "Fabricated trial line", "page_number": 2}]
        )

        # Reviewer B accesses the same paper
        self.client.force_authenticate(user=self.user_b)
        url = f"/api/slr/cohorts/{self.cohort.id}/papers/{target_paper.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Reviewer B must NOT see Reviewer A's notes or decision
        self.assertFalse(data['is_reviewed'], "Reviewer B should be flagged as not yet reviewed.")
        self.assertIsNone(data['reviewer_decision'])
        self.assertIsNone(data['exclusion_reason'])
        self.assertIsNone(data['reviewer_note'])
        self.assertNotIn("CONFIDENTIAL_NOTE_FROM_REVIEWER_A", str(data))

    def test_idor_protection_on_paper_review(self):
        """
        SECURITY AUDIT TEST:
        Confirms that attempting to review a paper that belongs to another workspace / not in cohort
        is strictly rejected with HTTP 404 and does not pollute cohort consensus.
        """
        foreign_ws = Workspace.objects.create(name="Foreign Unrelated Workspace")
        foreign_paper = Paper.objects.create(
            workspace=foreign_ws,
            hash_id=f"foreign_{uuid.uuid4().hex}",
            title="Foreign Secret Study",
            authors="Foreign Author",
            abstract="Not part of this review."
        )

        self.client.force_authenticate(user=self.user_a)
        url = f"/api/slr/cohorts/{self.cohort.id}/papers/{foreign_paper.id}/review/"
        payload = {"action": "agree", "time_spent_seconds": 10}

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("not part of this audit cohort", response.json().get('error', ''))

    def test_dispute_rbac_and_replay_attack_prevention(self):
        """
        SECURITY AUDIT TEST:
        1. Regular reviewer cannot resolve disputes (HTTP 403)
        2. Designated Senior Arbiter can resolve dispute (HTTP 200)
        3. Re-resolving an already resolved dispute is blocked (HTTP 400)
        """
        target_paper = self.papers[0]
        dispute = AdjudicationDispute.objects.create(
            sample_cohort=self.cohort,
            paper=target_paper,
            stage="abstract",
            status="pending",
            evidence_synthesis={"reviewer_1": {"decision": "include"}, "reviewer_2": {"decision": "exclude"}}
        )

        resolve_url = f"/api/slr/disputes/{dispute.id}/resolve/"
        payload = {
            "final_decision": "include",
            "resolution_rationale": "Arbiter verdict based on primary trial end-point."
        }

        # 1. Non-arbiter member attempts to resolve -> 403 Forbidden
        self.client.force_authenticate(user=self.user_a)
        res_unauth = self.client.post(resolve_url, payload, format='json')
        self.assertEqual(res_unauth.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Designated Senior Arbiter resolves -> 200 OK
        self.client.force_authenticate(user=self.arbiter)
        res_ok = self.client.post(resolve_url, payload, format='json')
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        self.assertTrue(res_ok.json().get('success'))

        dispute.refresh_from_db()
        self.assertEqual(dispute.status, "resolved")
        self.assertEqual(dispute.final_decision, "include")

        # 3. Replay attack: Attempting to resolve an already resolved dispute -> 400 Bad Request
        res_replay = self.client.post(resolve_url, payload, format='json')
        self.assertEqual(res_replay.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been resolved", res_replay.json().get('error', ''))

    def test_unassigned_workspace_access_security(self):
        """
        SECURITY AUDIT TEST:
        An orphan workspace with no configured members must reject unassigned users
        with 403 Forbidden in production (DEBUG=False), preventing open-access vulnerabilities.
        """
        orphan_workspace = Workspace.objects.create(name="Orphan Confidential SLR Workspace")
        SLRWorkspaceConfig.objects.create(workspace=orphan_workspace)

        config_url = f"/api/slr/workspaces/{orphan_workspace.id}/config/"
        self.client.force_authenticate(user=self.user_a)

        # 1. When DEBUG=False (production default), access must be denied (403 Forbidden)
        with self.settings(DEBUG=False):
            res_prod = self.client.get(config_url)
            self.assertEqual(res_prod.status_code, status.HTTP_403_FORBIDDEN)
            self.assertIn("not a member of this workspace", res_prod.json().get('error', ''))

        # 2. When DEBUG=True, open unassigned workspace is accessible for development
        with self.settings(DEBUG=True):
            res_debug = self.client.get(config_url)
            self.assertEqual(res_debug.status_code, status.HTTP_200_OK)

