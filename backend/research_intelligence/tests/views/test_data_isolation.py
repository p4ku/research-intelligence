"""
Security Tests — Workspace Data Isolation (BOLA Protection)
============================================================
Verifies that REST API ViewSets enforce workspace-scoped data isolation:
- User A (member of Workspace A) MUST NOT see data belonging to Workspace B.
- Superusers CAN see all data across all workspaces.
- Each ViewSet must only return records scoped to the user's workspace memberships.
"""
import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Paper,
    PipelineRun,
    ComponentRun,
    Extraction,
    ExtractionDefinition,
    HITLCorrection,
    NarrativeReport,
    ResearchAgentProcess,
    UserActivityLog,
)

User = get_user_model()


class WorkspaceDataIsolationTest(TestCase):
    """
    CRITICAL SECURITY TEST:
    Two users, two separate workspaces.
    User A must NEVER see User B's workspace data through REST API endpoints.
    """

    def setUp(self):
        # ── User A ──
        self.user_a = User.objects.create_user(
            username="alice", email="alice@corp.com", password="pass123"
        )
        self.workspace_a = Workspace.objects.create(
            name="Alice's Research Lab",
            abstract_acceptance_criteria="Criteria A"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace_a, user=self.user_a, role="admin"
        )

        # ── User B ──
        self.user_b = User.objects.create_user(
            username="bob", email="bob@corp.com", password="pass456"
        )
        self.workspace_b = Workspace.objects.create(
            name="Bob's Secret Project",
            abstract_acceptance_criteria="Criteria B"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace_b, user=self.user_b, role="admin"
        )

        # ── Shared fixture data ──
        self.pipeline_a = PipelineRun.objects.create(workspace=self.workspace_a)
        self.pipeline_b = PipelineRun.objects.create(workspace=self.workspace_b)

        self.paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.pipeline_a,
            hash_id="hash_alice_001",
            title="Alice's Paper on Quantum AI",
            authors="Alice Author",
            abstract="Secret abstract A",
            source_database="arxiv"
        )
        self.paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.pipeline_b,
            hash_id="hash_bob_001",
            title="Bob's Confidential Research",
            authors="Bob Author",
            abstract="Secret abstract B",
            source_database="openalex"
        )

        self.extraction_a = Extraction.objects.create(
            workspace=self.workspace_a,
            paper=self.paper_a,
            category="ml_method",
            fields_data={"method": "Transformer"}
        )
        self.extraction_b = Extraction.objects.create(
            workspace=self.workspace_b,
            paper=self.paper_b,
            category="patent_claim",
            fields_data={"claim": "Novel architecture"}
        )

        self.hitl_a = HITLCorrection.objects.create(
            extraction=self.extraction_a,
            action="verify",
            human_operator="alice@corp.com",
            original_value={"method": "Transformer"}
        )
        self.hitl_b = HITLCorrection.objects.create(
            extraction=self.extraction_b,
            action="modify",
            human_operator="bob@corp.com",
            original_value={"claim": "Novel architecture"},
            corrected_value={"claim": "Improved architecture"}
        )

        self.report_a = NarrativeReport.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.pipeline_a,
            title="Alice's Weekly Report",
            content_markdown="# Report A"
        )
        self.report_b = NarrativeReport.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.pipeline_b,
            title="Bob's Weekly Report",
            content_markdown="# Report B"
        )

        self.agent_a = ResearchAgentProcess.objects.create(
            workspace=self.workspace_a,
            name="Alice's Agent Run"
        )
        self.agent_b = ResearchAgentProcess.objects.create(
            workspace=self.workspace_b,
            name="Bob's Agent Run"
        )

        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

    # ─────────────────────────────────────────────
    # WORKSPACE ISOLATION
    # ─────────────────────────────────────────────

    def test_workspace_isolation(self):
        """User A should only see Workspace A, not Workspace B."""
        resp = self.client_a.get("/api/workspaces/")
        self.assertEqual(resp.status_code, 200)
        names = [w["name"] for w in resp.data]
        self.assertIn("Alice's Research Lab", names)
        self.assertNotIn("Bob's Secret Project", names,
                         "🔴 BOLA: User A can see User B's workspace!")

    def test_workspace_detail_forbidden(self):
        """User A should NOT be able to retrieve Workspace B by UUID."""
        resp = self.client_a.get(f"/api/workspaces/{self.workspace_b.id}/")
        self.assertEqual(resp.status_code, 404,
                         "🔴 BOLA: User A can access User B's workspace detail!")

    # ─────────────────────────────────────────────
    # PAPER ISOLATION
    # ─────────────────────────────────────────────

    def test_paper_isolation(self):
        """User A should only see papers from Workspace A."""
        resp = self.client_a.get("/api/papers/")
        self.assertEqual(resp.status_code, 200)
        titles = [p["title"] for p in resp.data]
        self.assertIn("Alice's Paper on Quantum AI", titles)
        self.assertNotIn("Bob's Confidential Research", titles,
                         "🔴 BOLA: User A can see User B's papers!")

    def test_paper_detail_forbidden(self):
        """User A should NOT be able to retrieve User B's paper by UUID."""
        resp = self.client_a.get(f"/api/papers/{self.paper_b.id}/")
        self.assertEqual(resp.status_code, 404,
                         "🔴 BOLA: User A can access User B's paper detail!")

    # ─────────────────────────────────────────────
    # EXTRACTION ISOLATION
    # ─────────────────────────────────────────────

    def test_extraction_isolation(self):
        """User A should only see extractions from Workspace A."""
        resp = self.client_a.get("/api/extractions/")
        self.assertEqual(resp.status_code, 200)
        categories = [e["category"] for e in resp.data]
        self.assertIn("ml_method", categories)
        self.assertNotIn("patent_claim", categories,
                         "🔴 BOLA: User A can see User B's extractions!")

    # ─────────────────────────────────────────────
    # HITL CORRECTION ISOLATION
    # ─────────────────────────────────────────────

    def test_hitl_isolation(self):
        """User A should only see HITL corrections from Workspace A."""
        resp = self.client_a.get("/api/hitl/")
        self.assertEqual(resp.status_code, 200)
        operators = [h["human_operator"] for h in resp.data]
        self.assertIn("alice@corp.com", operators)
        self.assertNotIn("bob@corp.com", operators,
                         "🔴 BOLA: User A can see User B's HITL corrections!")

    # ─────────────────────────────────────────────
    # REPORT ISOLATION
    # ─────────────────────────────────────────────

    def test_report_isolation(self):
        """User A should only see reports from Workspace A."""
        resp = self.client_a.get("/api/reports/")
        self.assertEqual(resp.status_code, 200)
        titles = [r["title"] for r in resp.data]
        self.assertIn("Alice's Weekly Report", titles)
        self.assertNotIn("Bob's Weekly Report", titles,
                         "🔴 BOLA: User A can see User B's reports!")

    # ─────────────────────────────────────────────
    # AGENT PROCESS ISOLATION
    # ─────────────────────────────────────────────

    def test_agent_isolation(self):
        """User A should only see agent processes from Workspace A."""
        resp = self.client_a.get("/api/agents/")
        self.assertEqual(resp.status_code, 200)
        names = [a["name"] for a in resp.data]
        self.assertIn("Alice's Agent Run", names)
        self.assertNotIn("Bob's Agent Run", names,
                         "🔴 BOLA: User A can see User B's agent processes!")

    # ─────────────────────────────────────────────
    # ACTIVITY LOG ISOLATION
    # ─────────────────────────────────────────────

    def test_activity_log_isolation(self):
        """User A should only see activity logs for their own workspaces."""
        UserActivityLog.log_action(
            user=self.user_a, workspace=self.workspace_a,
            interface="mcp", action_name="test_a", status="success"
        )
        UserActivityLog.log_action(
            user=self.user_b, workspace=self.workspace_b,
            interface="mcp", action_name="test_b", status="success"
        )

        resp = self.client_a.get("/api/activity-logs/")
        self.assertEqual(resp.status_code, 200)
        action_names = [l["action_name"] for l in resp.data]
        self.assertNotIn("test_b", action_names,
                         "🔴 BOLA: User A can see User B's activity logs!")

    # ─────────────────────────────────────────────
    # SUPERUSER SEES EVERYTHING
    # ─────────────────────────────────────────────

    def test_superuser_sees_all_workspaces(self):
        """A superuser should see ALL workspaces across all users."""
        superuser = User.objects.create_superuser(
            username="superadmin", email="super@corp.com", password="super123"
        )
        client_super = APIClient()
        client_super.force_authenticate(user=superuser)

        resp = client_super.get("/api/workspaces/")
        self.assertEqual(resp.status_code, 200)
        names = [w["name"] for w in resp.data]
        self.assertIn("Alice's Research Lab", names)
        self.assertIn("Bob's Secret Project", names)

    def test_superuser_sees_all_papers(self):
        """A superuser should see ALL papers across all workspaces."""
        superuser = User.objects.create_superuser(
            username="superadmin2", email="super2@corp.com", password="super123"
        )
        client_super = APIClient()
        client_super.force_authenticate(user=superuser)

        resp = client_super.get("/api/papers/")
        self.assertEqual(resp.status_code, 200)
        titles = [p["title"] for p in resp.data]
        self.assertIn("Alice's Paper on Quantum AI", titles)
        self.assertIn("Bob's Confidential Research", titles)

    # ─────────────────────────────────────────────
    # CHAT WORKSPACE ACCESS CONTROL
    # ─────────────────────────────────────────────

    def test_chat_rejects_unauthorized_workspace(self):
        """User A should NOT be able to send a chat query to Workspace B."""
        resp = self.client_a.post("/api/chat/", {
            "question": "What is the state of the art?",
            "workspace_id": str(self.workspace_b.id)
        }, format="json")
        self.assertEqual(resp.status_code, 403,
                         "🔴 User A can chat in User B's workspace!")

    def test_chat_allows_own_workspace(self):
        """User A SHOULD be able to chat in their own workspace."""
        resp = self.client_a.post("/api/chat/", {
            "question": "What is the state of the art?",
            "workspace_id": str(self.workspace_a.id)
        }, format="json")
        self.assertEqual(resp.status_code, 200)
