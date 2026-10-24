import uuid
from datetime import timedelta
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
    ComponentRun,
    ResearchAgentProcess,
    Extraction,
    WorkflowSchedule,
)
from slr_review.models import (
    SLRWorkspaceConfig,
    AuditSampleCohort,
    ScreeningReview,
    AdjudicationDispute,
    RiskOfBiasAssessment,
    SLRPRISMAMetrics,
)
from slr_review.tasks.orchestrator_hooks import intercept_component_completion
from research_intelligence.tasks.auxiliary.zombie_watchdog import reap_zombie_tasks
from research_intelligence.tasks.auxiliary.schedule_dispatcher import dispatch_due_workflow_schedules

User = get_user_model()


class SLRVisibilityAndCornerCasesTestCase(TestCase):
    """
    Comprehensive test suite verifying:
    1. Strict persona visibility and multi-tenancy isolation (preventing cross-workspace data leaks).
    2. Blind dual-review isolation (no peer vote, notes, or evidence leakage).
    3. Senior Arbiter role authorization and dispute immutability.
    4. Operational corner cases (idempotent voting, validation, empty cohorts, resume guards).
    5. Celery cron / Zombie Watchdog immunity for HITL runs waiting days/weeks for human input.
    """

    def setUp(self):
        self.client = APIClient()

        # =====================================================================
        # Workspace A (Oncology Systematic Review)
        # Personas:
        # - Alice: Reviewer 1 (role='member')
        # - Carol: Reviewer 2 (role='member')
        # - Arbiter: Designated Arbiter (role='member')
        # - Admin: Workspace Admin (role='admin')
        # - Viewer: Read-only Viewer (role='viewer')
        # =====================================================================
        self.alice_member_a = User.objects.create_user(username='alice_a', password='Password123!')
        self.carol_member_a = User.objects.create_user(username='carol_a', password='Password123!')
        self.arbiter_a = User.objects.create_user(username='arbiter_a', password='Password123!')
        self.admin_a = User.objects.create_user(username='admin_a', password='Password123!')
        self.viewer_a = User.objects.create_user(username='viewer_a', password='Password123!')

        self.workspace_a = Workspace.objects.create(name="Oncology Systematic Review")
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.alice_member_a, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.carol_member_a, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.arbiter_a, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.admin_a, role="admin")
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.viewer_a, role="viewer")

        self.config_a = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace_a,
            screening_quorum_size=2,
            designated_arbiter=self.arbiter_a,
            require_blind_review=True,
            tie_breaker_strategy='arbiter_adjudication'
        )

        self.run_a = PipelineRun.objects.create(
            workspace=self.workspace_a,
            name="Oncology Run 1",
            status="paused",
            current_stage="awaiting_abstract_screening_audit"
        )

        self.paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            hash_id=f"hash_a_{uuid.uuid4().hex[:12]}",
            title="Immune Checkpoint Inhibitor RCT in NSCLC",
            authors="Carter et al."
        )
        PaperMetric.objects.create(
            paper=self.paper_a,
            pipeline_run=self.run_a,
            workspace=self.workspace_a,
            screening_status="abstract_passed"
        )
        self.cohort_a = AuditSampleCohort.objects.create(
            config=self.config_a,
            pipeline_run=self.run_a,
            stage="abstract_screening",
            total_pool_count=1,
            sampled_count=1
        )
        self.cohort_a.sampled_papers.add(self.paper_a)

        # =====================================================================
        # Workspace B (Cardiology Systematic Review)
        # Personas:
        # - Bob: Reviewer in Workspace B (role='member')
        # - Arbiter B: Arbiter in Workspace B (role='admin')
        # =====================================================================
        self.bob_member_b = User.objects.create_user(username='bob_b', password='Password123!')
        self.arbiter_b = User.objects.create_user(username='arbiter_b', password='Password123!')

        self.workspace_b = Workspace.objects.create(name="Cardiology Systematic Review")
        WorkspaceMember.objects.create(workspace=self.workspace_b, user=self.bob_member_b, role="member")
        WorkspaceMember.objects.create(workspace=self.workspace_b, user=self.arbiter_b, role="admin")

        self.config_b = SLRWorkspaceConfig.objects.create(
            workspace=self.workspace_b,
            screening_quorum_size=2,
            designated_arbiter=self.arbiter_b,
        )

        self.run_b = PipelineRun.objects.create(
            workspace=self.workspace_b,
            name="Cardiology Run 1",
            status="paused",
            current_stage="awaiting_abstract_screening_audit"
        )

        self.paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            hash_id=f"hash_b_{uuid.uuid4().hex[:12]}",
            title="SGLT2 Inhibitors in Heart Failure Trial",
            authors="Muller et al."
        )
        PaperMetric.objects.create(
            paper=self.paper_b,
            pipeline_run=self.run_b,
            workspace=self.workspace_b,
            screening_status="abstract_passed"
        )
        self.cohort_b = AuditSampleCohort.objects.create(
            config=self.config_b,
            pipeline_run=self.run_b,
            stage="abstract_screening",
            total_pool_count=1,
            sampled_count=1
        )
        self.cohort_b.sampled_papers.add(self.paper_b)

        # Unaffiliated User & Superuser
        self.stranger = User.objects.create_user(username='stranger_nobody', password='Password123!')
        self.superuser = User.objects.create_superuser(username='super_boss', email='boss@example.com', password='Password123!')

    # =========================================================================
    # PART 1: Multi-Tenancy & Persona Data Leak Prevention Tests
    # =========================================================================

    def test_audit_queue_isolation_between_workspaces(self):
        """Reviewers in Workspace A must only see Workspace A cohorts; Workspace B reviewers only see Workspace B."""
        # Alice sees only cohort_a
        self.client.force_authenticate(user=self.alice_member_a)
        resp_a = self.client.get('/api/slr/cohorts/my-queue/')
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        ids_a = [item["cohort_id"] for item in resp_a.json()]
        self.assertIn(str(self.cohort_a.id), ids_a)
        self.assertNotIn(str(self.cohort_b.id), ids_a)

        # Bob sees only cohort_b
        self.client.force_authenticate(user=self.bob_member_b)
        resp_b = self.client.get('/api/slr/cohorts/my-queue/')
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        ids_b = [item["cohort_id"] for item in resp_b.json()]
        self.assertIn(str(self.cohort_b.id), ids_b)
        self.assertNotIn(str(self.cohort_a.id), ids_b)

        # Stranger sees nothing
        self.client.force_authenticate(user=self.stranger)
        resp_s = self.client.get('/api/slr/cohorts/my-queue/')
        self.assertEqual(resp_s.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_s.json()), 0)

        # Superuser sees all cohorts
        self.client.force_authenticate(user=self.superuser)
        resp_su = self.client.get('/api/slr/cohorts/my-queue/')
        self.assertEqual(resp_su.status_code, status.HTTP_200_OK)
        ids_su = [item["cohort_id"] for item in resp_su.json()]
        self.assertIn(str(self.cohort_a.id), ids_su)
        self.assertIn(str(self.cohort_b.id), ids_su)

    def test_audit_queue_personal_progress_isolation(self):
        """
        When Reviewer 1 votes, Reviewer 1's queue shows 1 completed, 0 remaining.
        Peer Reviewer 2 (who hasn't voted) must see 0 completed, 1 remaining.
        No individual progress leak between screeners.
        """
        # Alice votes
        self.client.force_authenticate(user=self.alice_member_a)
        self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={"action": "agree"},
            format='json'
        )

        # Check Alice's queue
        resp_alice = self.client.get('/api/slr/cohorts/my-queue/')
        item_alice = next(item for item in resp_alice.json() if item["cohort_id"] == str(self.cohort_a.id))
        self.assertEqual(item_alice["completed_count"], 1)
        self.assertEqual(item_alice["remaining_count"], 0)
        self.assertEqual(item_alice["status"], "completed")

        # Check Carol's queue (Carol has not voted yet)
        self.client.force_authenticate(user=self.carol_member_a)
        resp_carol = self.client.get('/api/slr/cohorts/my-queue/')
        item_carol = next(item for item in resp_carol.json() if item["cohort_id"] == str(self.cohort_a.id))
        self.assertEqual(item_carol["completed_count"], 0)
        self.assertEqual(item_carol["remaining_count"], 1)
        self.assertEqual(item_carol["status"], "pending")

    def test_cross_workspace_direct_access_prohibited(self):
        """Direct access to cohort details, paper details, or reviews from another workspace returns 403 Forbidden."""
        self.client.force_authenticate(user=self.bob_member_b)

        # Bob tries to access Cohort A detail
        resp_cohort = self.client.get(f'/api/slr/cohorts/{self.cohort_a.id}/')
        self.assertEqual(resp_cohort.status_code, status.HTTP_403_FORBIDDEN)

        # Bob tries to access Paper A detail in Cohort A
        resp_paper = self.client.get(f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/')
        self.assertEqual(resp_paper.status_code, status.HTTP_403_FORBIDDEN)

        # Bob tries to submit a review vote in Cohort A
        resp_vote = self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={"action": "agree"},
            format='json'
        )
        self.assertEqual(resp_vote.status_code, status.HTTP_403_FORBIDDEN)

    def test_paper_not_in_cohort_returns_404(self):
        """Submitting a review or requesting a paper that is not part of the cohort returns 404."""
        self.client.force_authenticate(user=self.alice_member_a)

        # Paper B is in Workspace B, not in Cohort A
        resp = self.client.get(f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_b.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        resp_vote = self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_b.id}/review/',
            data={"action": "agree"},
            format='json'
        )
        self.assertEqual(resp_vote.status_code, status.HTTP_404_NOT_FOUND)

    def test_blind_review_vote_isolation(self):
        """
        Under blind review, screeners cannot inspect each other's decisions, notes, or highlights.
        Each reviewer only receives their own review state.
        """
        # Alice votes override_include with confidential notes
        self.client.force_authenticate(user=self.alice_member_a)
        self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={
                "action": "override_include",
                "reviewer_note": "Confidential finding: Biomarker subgroup shows 80% response.",
                "evidence_citation": "80% response in EGFR mutant subgroup"
            },
            format='json'
        )

        # Carol (peer reviewer who hasn't voted yet) inspects the paper details
        self.client.force_authenticate(user=self.carol_member_a)
        resp_carol = self.client.get(f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/')
        self.assertEqual(resp_carol.status_code, status.HTTP_200_OK)
        data_carol = resp_carol.json()

        # Carol sees unreviewed state for herself, and zero information about Alice's vote
        self.assertFalse(data_carol["is_reviewed"])
        self.assertIsNone(data_carol["reviewer_decision"])
        self.assertIsNone(data_carol["reviewer_note"])
        self.assertIsNone(data_carol["evidence_citation"])

        # Carol submits her own independent vote
        self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={
                "action": "override_exclude",
                "exclusion_reason": "Non-randomized single-arm cohort",
                "reviewer_note": "Carol independent assessment: Phase II study."
            },
            format='json'
        )

        # Carol refreshes paper details - sees ONLY her own vote and notes
        resp_carol_after = self.client.get(f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/')
        self.assertEqual(resp_carol_after.status_code, status.HTTP_200_OK)
        data_carol_after = resp_carol_after.json()
        self.assertTrue(data_carol_after["is_reviewed"])
        self.assertEqual(data_carol_after["reviewer_decision"], "override_exclude")
        self.assertEqual(data_carol_after["reviewer_note"], "Carol independent assessment: Phase II study.")
        self.assertNotIn("Confidential finding", data_carol_after["reviewer_note"])

    def test_dispute_listing_and_senior_arbiter_role_enforcement(self):
        """Only users from the workspace see disputes, and only designated arbiters/admins can resolve them."""
        # Create a dispute in Workspace A
        dispute_a = AdjudicationDispute.objects.create(
            sample_cohort=self.cohort_a,
            paper=self.paper_a,
            stage="abstract_screening",
            status="pending",
            evidence_synthesis={"ai_agent": {"status": "abstract_passed"}}
        )

        # Bob (Workspace B) calls /api/slr/disputes/ -> dispute_a must not leak
        self.client.force_authenticate(user=self.bob_member_b)
        resp_disputes_b = self.client.get('/api/slr/disputes/')
        self.assertEqual(resp_disputes_b.status_code, status.HTTP_200_OK)
        ids_b = [d["id"] for d in resp_disputes_b.json()]
        self.assertNotIn(str(dispute_a.id), ids_b)

        # Bob tries to resolve dispute_a -> 403 Forbidden
        resp_res_b = self.client.post(
            f'/api/slr/disputes/{dispute_a.id}/resolve/',
            data={"final_decision": "exclude", "resolution_rationale": "Illicit attempt."},
            format='json'
        )
        self.assertEqual(resp_res_b.status_code, status.HTTP_403_FORBIDDEN)

        # Alice (regular member in Workspace A, but NOT arbiter and NOT admin) tries to resolve -> 403 Forbidden
        self.client.force_authenticate(user=self.alice_member_a)
        resp_res_alice = self.client.post(
            f'/api/slr/disputes/{dispute_a.id}/resolve/',
            data={"final_decision": "exclude", "resolution_rationale": "Regular member trying to rule."},
            format='json'
        )
        self.assertEqual(resp_res_alice.status_code, status.HTTP_403_FORBIDDEN)

        # Designated Arbiter A resolves -> 200 OK
        self.client.force_authenticate(user=self.arbiter_a)
        resp_res_arb = self.client.post(
            f'/api/slr/disputes/{dispute_a.id}/resolve/',
            data={"final_decision": "include", "resolution_rationale": "Authoritative ruling by PI."},
            format='json'
        )
        self.assertEqual(resp_res_arb.status_code, status.HTTP_200_OK)
        dispute_a.refresh_from_db()
        self.assertEqual(dispute_a.status, "resolved")
        self.assertEqual(dispute_a.final_decision, "include")

    def test_dispute_cannot_be_re_resolved_after_arbitration(self):
        """Once a dispute is resolved by arbitration, attempting to resolve it again returns 400."""
        dispute = AdjudicationDispute.objects.create(
            sample_cohort=self.cohort_a,
            paper=self.paper_a,
            stage="abstract_screening",
            status="resolved",
            final_decision="include",
            resolution_rationale="Initial binding ruling",
            resolved_at=timezone.now()
        )

        self.client.force_authenticate(user=self.arbiter_a)
        resp = self.client.post(
            f'/api/slr/disputes/{dispute.id}/resolve/',
            data={"final_decision": "exclude", "resolution_rationale": "Attempt to overturn binding ruling"},
            format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been resolved", resp.json().get("error", ""))

    def test_workspace_slr_config_modification_requires_admin(self):
        """Reading SLR config allows regular members; modifying config requires workspace admin role."""
        # Alice (regular member) can GET config -> 200 OK
        self.client.force_authenticate(user=self.alice_member_a)
        resp_get_alice = self.client.get(f'/api/slr/workspaces/{self.workspace_a.id}/config/')
        self.assertEqual(resp_get_alice.status_code, status.HTTP_200_OK)

        # Alice tries to update config -> 403 Forbidden
        resp_put_alice = self.client.put(
            f'/api/slr/workspaces/{self.workspace_a.id}/config/',
            data={"screening_quorum_size": 3},
            format='json'
        )
        self.assertEqual(resp_put_alice.status_code, status.HTTP_403_FORBIDDEN)

        # Bob (Workspace B) cannot GET or PUT config of Workspace A -> 403 Forbidden
        self.client.force_authenticate(user=self.bob_member_b)
        resp_get_bob = self.client.get(f'/api/slr/workspaces/{self.workspace_a.id}/config/')
        self.assertEqual(resp_get_bob.status_code, status.HTTP_403_FORBIDDEN)

        # Admin A updates config -> 200 OK
        self.client.force_authenticate(user=self.admin_a)
        resp_put_admin = self.client.put(
            f'/api/slr/workspaces/{self.workspace_a.id}/config/',
            data={"screening_quorum_size": 3},
            format='json'
        )
        self.assertEqual(resp_put_admin.status_code, status.HTTP_200_OK)
        self.config_a.refresh_from_db()
        self.assertEqual(self.config_a.screening_quorum_size, 3)

    def test_metrics_and_risk_of_bias_cross_workspace_isolation(self):
        """PRISMA metrics and Risk of Bias endpoints reject cross-workspace access with 403 Forbidden."""
        # Setup sample RiskOfBiasAssessment
        RiskOfBiasAssessment.objects.create(
            pipeline_run=self.run_a,
            paper=self.paper_a,
            framework='rob2',
            domain_scores={'D1_randomization': {'rating': 'low_risk'}},
            overall_bias='low_risk'
        )

        # Bob (Workspace B) tries to view PRISMA metrics for Run A -> 403
        self.client.force_authenticate(user=self.bob_member_b)
        resp_metrics_b = self.client.get(f'/api/slr/runs/{self.run_a.id}/prisma/')
        self.assertEqual(resp_metrics_b.status_code, status.HTTP_403_FORBIDDEN)

        # Bob tries to view Risk of Bias for Run A -> 403
        resp_rob_b = self.client.get(f'/api/slr/runs/{self.run_a.id}/rob/')
        self.assertEqual(resp_rob_b.status_code, status.HTTP_403_FORBIDDEN)

        # Stranger tries to view Run A -> 403
        self.client.force_authenticate(user=self.stranger)
        resp_rob_s = self.client.get(f'/api/slr/runs/{self.run_a.id}/rob/')
        self.assertEqual(resp_rob_s.status_code, status.HTTP_403_FORBIDDEN)

        # Alice (Workspace A member) views both -> 200 OK
        self.client.force_authenticate(user=self.alice_member_a)
        resp_metrics_a = self.client.get(f'/api/slr/runs/{self.run_a.id}/prisma/')
        self.assertEqual(resp_metrics_a.status_code, status.HTTP_200_OK)

        resp_rob_a = self.client.get(f'/api/slr/runs/{self.run_a.id}/rob/')
        self.assertEqual(resp_rob_a.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_rob_a.json()), 1)

    def test_extraction_review_cross_workspace_and_cohort_paper_validation(self):
        """Submitting an extraction review rejects cross-workspace callers (403) and extractions outside cohort (404)."""
        # Create extraction for Paper B (Workspace B)
        ext_b = Extraction.objects.create(
            workspace=self.workspace_b,
            paper=self.paper_b,
            category="clinical_metrics",
            fields_data={"hazard_ratio": 0.72, "sample_size": 4200}
        )

        # Alice (Workspace A) tries to submit review for ext_b on cohort_a -> 404 (Paper B is not in Cohort A)
        self.client.force_authenticate(user=self.alice_member_a)
        resp_alice = self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/extractions/{ext_b.id}/audit/',
            data={"action": "verify"},
            format='json'
        )
        self.assertEqual(resp_alice.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("does not belong", resp_alice.json().get("error", ""))

        # Bob (Workspace B) tries to review ext_b on cohort_a -> 403 Forbidden (cross-workspace)
        self.client.force_authenticate(user=self.bob_member_b)
        resp_bob = self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/extractions/{ext_b.id}/audit/',
            data={"action": "verify"},
            format='json'
        )
        self.assertEqual(resp_bob.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # PART 2: Operational Corner Cases Tests
    # =========================================================================

    def test_reviewer_vote_idempotency_and_update(self):
        """A reviewer can update their vote without creating duplicate records or inflating quorum."""
        self.client.force_authenticate(user=self.alice_member_a)

        # Initial vote: agree
        resp1 = self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={"action": "agree"},
            format='json'
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(ScreeningReview.objects.filter(sample_cohort=self.cohort_a, paper=self.paper_a).count(), 1)

        # Alice updates vote to override_exclude
        resp2 = self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={
                "action": "override_exclude",
                "exclusion_reason": "Ineligible study design (retrospective)",
                "reviewer_note": "Corrected decision upon reading full methods."
            },
            format='json'
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        # Verify only 1 review object exists and values are updated
        reviews = ScreeningReview.objects.filter(sample_cohort=self.cohort_a, paper=self.paper_a)
        self.assertEqual(reviews.count(), 1)
        review = reviews.first()
        self.assertEqual(review.decision, "exclude")
        self.assertEqual(review.exclusion_reason, "Ineligible study design (retrospective)")

    def test_override_exclude_validation_requires_reason(self):
        """Overriding to Exclude requires an explicit exclusion reason; omitting it returns 400."""
        self.client.force_authenticate(user=self.alice_member_a)
        resp = self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={"action": "override_exclude"},  # missing exclusion_reason
            format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exclusion_reason", resp.json())

    def test_corner_case_conservative_include_auto_resolution(self):
        """When tie_breaker_strategy is conservative_include, any Include vote automatically breaks a tie."""
        self.config_a.tie_breaker_strategy = 'conservative_include'
        self.config_a.screening_quorum_size = 2
        self.config_a.save()

        # Alice votes include
        self.client.force_authenticate(user=self.alice_member_a)
        self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={"action": "override_include"},
            format='json'
        )

        # Admin A votes exclude
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            f'/api/slr/cohorts/{self.cohort_a.id}/papers/{self.paper_a.id}/review/',
            data={"action": "override_exclude", "exclusion_reason": "Doubtful methodology"},
            format='json'
        )

        # Verify dispute was automatically resolved via conservative_include without pending state
        dispute = AdjudicationDispute.objects.get(sample_cohort=self.cohort_a, paper=self.paper_a)
        self.assertEqual(dispute.status, 'resolved')
        self.assertEqual(dispute.final_decision, 'include')
        self.assertIn("conservative_include", dispute.resolution_rationale)

        # Metric was updated to included
        metric = PaperMetric.objects.get(paper=self.paper_a, pipeline_run=self.run_a)
        self.assertEqual(metric.screening_status, 'abstract_passed')

        # Cohort completed automatically
        self.cohort_a.refresh_from_db()
        self.assertTrue(self.cohort_a.is_audit_complete)

    def test_corner_case_cannot_resume_while_cohort_incomplete(self):
        """Calling resume API on a pipeline run with incomplete audit cohorts returns 400 Bad Request."""
        self.client.force_authenticate(user=self.admin_a)

        # Cohort is not yet complete
        self.assertFalse(self.cohort_a.is_audit_complete)
        resp = self.client.post(f'/api/slr/runs/{self.run_a.id}/resume/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", resp.json())
        self.assertFalse(resp.json().get("resumed", True))

    def test_corner_case_empty_cohort_auto_completion(self):
        """When 0 papers qualify for sampling, the cohort auto-completes and DAG execution does not halt."""
        # Create pipeline run with no papers
        empty_run = PipelineRun.objects.create(
            workspace=self.workspace_a,
            name="Empty Pool Run",
            status="running"
        )
        gate_res = intercept_component_completion(empty_run, "abstract_screening")
        self.assertFalse(gate_res.get("halt"))
        empty_run.refresh_from_db()
        self.assertEqual(empty_run.status, "running")

    # =========================================================================
    # PART 3: Celery Cron / Watchdog Immunity for Human-in-the-Loop Runs
    # =========================================================================

    def test_corner_case_zombie_watchdog_never_kills_paused_hitl_runs_or_components(self):
        """
        Zombie Watchdog must NEVER reap or fail runs, components, or agents that are
        paused awaiting human audit/input, even if they have been waiting for weeks (21 days).
        """
        # Age the pipeline run by 21 days
        old_time = timezone.now() - timedelta(days=21)
        self.run_a.started_at = old_time
        self.run_a.status = 'paused'
        self.run_a.current_stage = 'awaiting_abstract_screening_audit'
        self.run_a.save(update_fields=['started_at', 'status', 'current_stage'])

        # Create an associated ComponentRun aged 21 days
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.run_a,
            step_type='screening',
            component_name='abstract_screening',
            status='running',
            started_at=old_time
        )

        # Trigger zombie watchdog with aggressive 5-minute timeout and force=False
        stats = reap_zombie_tasks(
            max_component_age_minutes=5,
            max_pipeline_age_minutes=5,
            force=False
        )

        # Verify PipelineRun and ComponentRun were NOT reaped
        self.run_a.refresh_from_db()
        comp_run.refresh_from_db()

        self.assertEqual(self.run_a.status, 'paused', "Paused SLR run awaiting human audit must survive watchdog.")
        self.assertEqual(self.run_a.current_stage, 'awaiting_abstract_screening_audit')
        self.assertEqual(comp_run.status, 'running', "Component of paused SLR run must survive watchdog.")

        self.assertEqual(stats["reaped_pipelines"], 0)
        self.assertEqual(stats["reaped_components"], 0)

    def test_corner_case_schedule_dispatcher_respects_paused_run_overlap(self):
        """Schedule dispatcher overlap guard must treat paused runs as in-flight and not dispatch duplicate runs."""
        now = timezone.now()
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace_a,
            name="Weekly Oncology SLR Schedule",
            cron_expression="0 0 * * 1",  # Weekly
            is_active=True,
            next_run_at=now - timedelta(minutes=5),  # Due now
            prevent_overlap=True,
            last_pipeline_run=self.run_a  # Previous run is paused waiting for human audit!
        )

        res = dispatch_due_workflow_schedules(dry_run=False)
        self.assertEqual(len(res["dispatched"]), 0, "Should not dispatch while previous run is paused awaiting audit.")
        self.assertEqual(len(res["skipped_overlap"]), 1)
        self.assertEqual(res["skipped_overlap"][0]["schedule_id"], str(schedule.id))
        self.assertEqual(res["skipped_overlap"][0]["previous_run_status"], "paused")
