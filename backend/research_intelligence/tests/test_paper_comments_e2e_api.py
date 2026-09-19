"""
End-to-End API Test Suite for Paper Comments & Collaboration Lifecycle.

Covers the full collaborative workflow exclusively via REST API endpoints:
1. Multiple researchers (Lead, Peer, Admin, External) in isolated workspaces.
2. Ingesting paper and inspecting initial placeholder messages state.
3. Users commenting on the paper via API (top-level questions and threaded replies).
4. Emoji reactions and comment editing via API.
5. Reading back the paper detail, scorecard, and comments list (verifying ordering, thread relations, reactions).
6. Resolving threads via API.
7. Cross-tenant leakage penetration tests (verifying external users cannot read or post).
8. Full deletion lifecycle via API (soft-delete and hard-delete), restoring clean slate.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Paper,
    PaperMetric,
    PipelineRun,
    PaperComment,
    PaperCommentReaction,
)

User = get_user_model()


class PaperCommentsE2EAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users: Lead Researcher, Peer Researcher, Workspace Admin, External Outsider
        self.lead_researcher = User.objects.create_user(
            username="dr_curie",
            email="curie@schwarz-research.internal",
            password="secure_password_123!"
        )
        self.peer_researcher = User.objects.create_user(
            username="becquerel",
            email="becquerel@schwarz-research.internal",
            password="secure_password_123!"
        )
        self.workspace_admin = User.objects.create_user(
            username="lab_director",
            email="director@schwarz-research.internal",
            password="secure_password_123!"
        )
        self.external_user = User.objects.create_user(
            username="outsider_spy",
            email="spy@external-competitor.org",
            password="secure_password_123!"
        )

        # Workspaces: Target Research Lab and Competitor Lab
        self.lab_workspace = Workspace.objects.create(name="Applied Physics & ML Lab")
        self.competitor_workspace = Workspace.objects.create(name="External Competitor Corp")

        # Memberships
        WorkspaceMember.objects.create(workspace=self.lab_workspace, user=self.lead_researcher, role="researcher")
        WorkspaceMember.objects.create(workspace=self.lab_workspace, user=self.peer_researcher, role="researcher")
        WorkspaceMember.objects.create(workspace=self.lab_workspace, user=self.workspace_admin, role="admin")
        WorkspaceMember.objects.create(workspace=self.competitor_workspace, user=self.external_user, role="researcher")

        # Ingested Paper & Pipeline Run
        self.paper = Paper.objects.create(
            workspace=self.lab_workspace,
            hash_id="e2e_paper_hash_radiology_ml",
            title="Self-Supervised Pretraining for High-Resolution Medical Imaging",
            authors="Marie Curie, Henri Becquerel, Wilhelm Rontgen",
            abstract="We present an efficient self-supervised objective for 3D volumetric medical scans.",
            source_database="arxiv",
            source_url="https://arxiv.org/abs/2609.12345"
        )
        self.run = PipelineRun.objects.create(
            workspace=self.lab_workspace,
            name="Weekly Screening Edition #42"
        )
        self.metric = PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run,
            signal_score=94.5,
            screening_status="accepted"
        )

    def test_full_collaboration_and_deletion_lifecycle_e2e(self):
        """
        Executes complete multi-user E2E journey via REST API:
        1. Read initial paper with placeholders
        2. Lead comments on paper
        3. Peer replies and reacts
        4. Lead reacts to peer
        5. Peer edits reply
        6. Verify chronological chat ordering and payload structure in paper & scorecard
        7. Lead resolves discussion
        8. Cross-workspace leak protection check
        9. Soft and hard deletion via API to clean slate
        """
        # =========================================================================
        # 1. INITIAL STATE: Read paper before any user comments exist
        # =========================================================================
        self.client.force_authenticate(user=self.lead_researcher)

        # Paper Comments endpoint
        res_comments_initial = self.client.get(f"/api/papers/{self.paper.id}/comments/")
        self.assertEqual(res_comments_initial.status_code, status.HTTP_200_OK)
        initial_comments = res_comments_initial.json()
        self.assertGreater(len(initial_comments), 0)  # Has placeholder
        self.assertTrue(initial_comments[0]["id"].startswith("00000000-0000"))

        # Scorecard endpoint
        res_scorecard_initial = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run.id}")
        self.assertEqual(res_scorecard_initial.status_code, status.HTTP_200_OK)
        self.assertIn("messages", res_scorecard_initial.json())
        self.assertTrue(res_scorecard_initial.json()["messages"][0]["id"].startswith("00000000-0000"))

        # =========================================================================
        # 2. COMMENTING: Lead Researcher posts a top-level question on the paper
        # =========================================================================
        comment_1_payload = {
            "content": "Notice the benchmark comparison on page 4 — how does their rotary embedding scaling compare to our internal baseline?",
            "comment_type": "question",
            "pipeline_run": str(self.run.id),
            "anchor_text": "We evaluate rotary positional embeddings across all 48 attention heads.",
            "anchor_context": {"page": 4, "section": "Methodology"},
        }
        res_c1 = self.client.post(
            f"/api/papers/{self.paper.id}/comments/",
            comment_1_payload,
            format="json"
        )
        self.assertEqual(res_c1.status_code, status.HTTP_201_CREATED)
        c1_data = res_c1.json()
        c1_id = c1_data["id"]
        self.assertEqual(c1_data["user"]["username"], self.lead_researcher.username)
        self.assertEqual(c1_data["comment_type"], "question")
        self.assertEqual(c1_data["content"], comment_1_payload["content"])
        self.assertFalse(c1_data["is_resolved"])

        # =========================================================================
        # 3. THREADED REPLY: Peer Researcher replies to Lead Researcher's comment
        # =========================================================================
        self.client.force_authenticate(user=self.peer_researcher)

        reply_payload = {
            "paper": str(self.paper.id),
            "parent": str(c1_id),
            "content": "Rechecked table 3: throughput improves by ~18% with zero degradation on retrieval accuracy.",
            "comment_type": "finding",
            "pipeline_run": str(self.run.id),
        }
        res_c2 = self.client.post("/api/comments/", reply_payload, format="json")
        self.assertEqual(res_c2.status_code, status.HTTP_201_CREATED)
        c2_data = res_c2.json()
        c2_id = c2_data["id"]
        self.assertEqual(c2_data["parent_id"], c1_id)
        self.assertEqual(c2_data["user"]["username"], self.peer_researcher.username)

        # =========================================================================
        # 4. REACTIONS: Peer reacts to Lead, Lead reacts to Peer via API
        # =========================================================================
        # Peer reacts bulb to Lead's question
        res_react_c1 = self.client.post(
            f"/api/comments/{c1_id}/reactions/",
            {"reaction_type": "bulb"},
            format="json"
        )
        self.assertEqual(res_react_c1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_react_c1.json()["action"], "added")

        # Lead reacts rocket to Peer's answer
        self.client.force_authenticate(user=self.lead_researcher)
        res_react_c2 = self.client.post(
            f"/api/comments/{c2_id}/reactions/",
            {"reaction_type": "rocket"},
            format="json"
        )
        self.assertEqual(res_react_c2.status_code, status.HTTP_200_OK)
        reactions_c2 = res_react_c2.json()["reactions"]
        self.assertEqual(len(reactions_c2), 1)
        self.assertEqual(reactions_c2[0]["reaction_type"], "rocket")
        self.assertEqual(reactions_c2[0]["count"], 1)
        self.assertTrue(reactions_c2[0]["has_reacted"])

        # =========================================================================
        # 5. EDITING: Peer Researcher revises their answer via API
        # =========================================================================
        self.client.force_authenticate(user=self.peer_researcher)
        edit_payload = {
            "content": "Rechecked table 3: throughput improves by ~18% and GPU memory usage drops by 12% across distributed nodes."
        }
        res_edit = self.client.patch(f"/api/comments/{c2_id}/", edit_payload, format="json")
        self.assertEqual(res_edit.status_code, status.HTTP_200_OK)
        self.assertEqual(res_edit.json()["content"], edit_payload["content"])
        self.assertTrue(res_edit.json()["is_edited"])

        # =========================================================================
        # 6. READ VERIFICATION: Retrieve Paper, Scorecard, and Comments stream
        # =========================================================================
        # A. Via Paper comments action endpoint
        res_paper_comments = self.client.get(f"/api/papers/{self.paper.id}/comments/?pipeline_run={self.run.id}")
        self.assertEqual(res_paper_comments.status_code, status.HTTP_200_OK)
        paper_messages = res_paper_comments.json()
        self.assertEqual(len(paper_messages), 2)

        # Strictly chronological (oldest on top, newest at bottom, chat-style)
        self.assertEqual(paper_messages[0]["id"], c1_id)
        self.assertEqual(paper_messages[0]["user"]["username"], self.lead_researcher.username)
        self.assertIsNone(paper_messages[0]["parent_id"])

        self.assertEqual(paper_messages[1]["id"], c2_id)
        self.assertEqual(paper_messages[1]["user"]["username"], self.peer_researcher.username)
        self.assertEqual(paper_messages[1]["parent_id"], c1_id)
        self.assertTrue(paper_messages[1]["is_edited"])

        # B. Via Scorecard endpoint
        res_scorecard = self.client.get(f"/api/papers/{self.paper.id}/scorecard/?pipeline_run={self.run.id}")
        self.assertEqual(res_scorecard.status_code, status.HTTP_200_OK)
        scorecard_json = res_scorecard.json()
        self.assertEqual(len(scorecard_json["messages"]), 2)
        self.assertEqual(len(scorecard_json["paper"]["messages"]), 2)

        # C. Via Dedicated Comments endpoint
        res_comments_list = self.client.get(f"/api/comments/?paper={self.paper.id}")
        self.assertEqual(res_comments_list.status_code, status.HTTP_200_OK)
        c_list_data = res_comments_list.json()
        c_items = c_list_data if isinstance(c_list_data, list) else c_list_data.get("results", [])
        self.assertEqual(len(c_items), 2)

        # =========================================================================
        # 7. RESOLUTION LIFECYCLE: Lead resolves the question thread
        # =========================================================================
        self.client.force_authenticate(user=self.lead_researcher)
        res_resolve = self.client.post(f"/api/comments/{c1_id}/resolve/", {"action": "resolve"}, format="json")
        self.assertEqual(res_resolve.status_code, status.HTTP_200_OK)
        self.assertTrue(res_resolve.json()["is_resolved"])
        self.assertEqual(res_resolve.json()["status"], "resolved")
        self.assertEqual(res_resolve.json()["resolved_by"]["username"], self.lead_researcher.username)

        # =========================================================================
        # 8. CROSS-TENANT ISOLATION: Competitor User attempts unauthorized access
        # =========================================================================
        self.client.force_authenticate(user=self.external_user)

        # Competitor cannot view comments (404 zero data leakage)
        res_comp_detail = self.client.get(f"/api/comments/{c1_id}/")
        self.assertEqual(res_comp_detail.status_code, status.HTTP_404_NOT_FOUND)

        # Competitor gets empty list
        res_comp_list = self.client.get(f"/api/comments/?paper={self.paper.id}")
        comp_data = res_comp_list.json()
        comp_items = comp_data if isinstance(comp_data, list) else comp_data.get("results", [])
        self.assertEqual(len(comp_items), 0)

        # Competitor cannot post comment to lab's paper (403 Forbidden)
        res_comp_post = self.client.post(
            "/api/comments/",
            {"paper": str(self.paper.id), "content": "Spy remark."},
            format="json"
        )
        self.assertEqual(res_comp_post.status_code, status.HTTP_403_FORBIDDEN)

        # Competitor cannot delete lab's comment (404 Not Found)
        res_comp_del = self.client.delete(f"/api/comments/{c1_id}/")
        self.assertEqual(res_comp_del.status_code, status.HTTP_404_NOT_FOUND)

        # =========================================================================
        # 9. DELETION & CLEANUP LIFECYCLE: Delete comments via API
        # =========================================================================
        # A. Peer soft-deletes their reply
        self.client.force_authenticate(user=self.peer_researcher)
        res_del_reply = self.client.delete(f"/api/comments/{c2_id}/")
        self.assertEqual(res_del_reply.status_code, status.HTTP_204_NO_CONTENT)

        # Verify soft-deleted comment is hidden from standard active list
        res_active_list = self.client.get(f"/api/comments/?paper={self.paper.id}")
        active_data = res_active_list.json()
        active_items = active_data if isinstance(active_data, list) else active_data.get("results", [])
        self.assertEqual(len(active_items), 1)  # Only c1 active

        # But still available when include_deleted=true
        res_with_deleted = self.client.get(f"/api/comments/?paper={self.paper.id}&include_deleted=true")
        with_del_data = res_with_deleted.json()
        with_del_items = with_del_data if isinstance(with_del_data, list) else with_del_data.get("results", [])
        self.assertEqual(len(with_del_items), 2)

        # B. Workspace Admin hard-deletes both comments
        self.client.force_authenticate(user=self.workspace_admin)
        res_hard_c2 = self.client.delete(f"/api/comments/{c2_id}/?hard=true")
        self.assertEqual(res_hard_c2.status_code, status.HTTP_204_NO_CONTENT)

        res_hard_c1 = self.client.delete(f"/api/comments/{c1_id}/?hard=true")
        self.assertEqual(res_hard_c1.status_code, status.HTTP_204_NO_CONTENT)

        # =========================================================================
        # 10. POST-CLEANUP VERIFICATION: Paper and API return clean slate
        # =========================================================================
        res_empty_comments = self.client.get(f"/api/comments/?paper={self.paper.id}&include_deleted=true")
        empty_data = res_empty_comments.json()
        empty_items = empty_data if isinstance(empty_data, list) else empty_data.get("results", [])
        self.assertEqual(len(empty_items), 0)

        # Comments endpoint falls back cleanly to placeholder structure
        res_comments_after = self.client.get(f"/api/papers/{self.paper.id}/comments/")
        self.assertEqual(res_comments_after.status_code, status.HTTP_200_OK)
        self.assertTrue(res_comments_after.json()[0]["id"].startswith("00000000-0000"))
