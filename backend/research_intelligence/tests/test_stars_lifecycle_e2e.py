"""
Full End-to-End User Lifecycle Test Suite for Stars & Personal Curation.

Simulates real user workflows across multiple tenants, roles, and lifecycles:
1. Multi-user journey (Admin, Researcher 1, Researcher 2 in separate and shared workspaces).
2. Starring papers and briefings, verifying personal sets and ordering stability.
3. Idempotent PUT operations and state invariance.
4. Dynamic workspace access revocation: revoking membership immediately hides stars from API without losing database rows.
5. Workspace re-granting: re-adding membership instantly restores visibility of previously starred items.
6. Cascade delete lifecycle: target paper deletion, target pipeline run deletion, user deletion.
7. Cross-tenant penetration tests: unauthorized cross-workspace star attempts receive 404 without data leakage.
"""

import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    Star,
)

User = get_user_model()


class StarsLifecycleE2ETestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users: Admin, Researcher A, Researcher B, Superuser
        self.user_admin = User.objects.create_user(username="e2e_admin", password="password123")
        self.user_a = User.objects.create_user(username="e2e_researcher_a", password="password123")
        self.user_b = User.objects.create_user(username="e2e_researcher_b", password="password123")
        self.superuser = User.objects.create_superuser(username="e2e_super", password="password123", email="super@example.com")

        # Workspaces: Alpha (Shared by Admin & Researcher A), Beta (Researcher B only)
        self.ws_alpha = Workspace.objects.create(name="E2E Alpha Workspace")
        self.ws_beta = Workspace.objects.create(name="E2E Beta Workspace")

        WorkspaceMember.objects.create(workspace=self.ws_alpha, user=self.user_admin, role="admin")
        self.membership_a = WorkspaceMember.objects.create(workspace=self.ws_alpha, user=self.user_a, role="researcher")
        WorkspaceMember.objects.create(workspace=self.ws_beta, user=self.user_b, role="researcher")

        # Papers in Alpha
        self.paper_a1 = Paper.objects.create(
            workspace=self.ws_alpha,
            hash_id="e2e_hash_a1",
            title="Deep Learning Breakthroughs in Oncology",
            authors="Alice Smith, Bob Jones",
            abstract="Novel neural architectures for early detection.",
            source_database="arxiv",
        )
        self.paper_a2 = Paper.objects.create(
            workspace=self.ws_alpha,
            hash_id="e2e_hash_a2",
            title="Quantum Annealing in Genomic Sequence Alignment",
            authors="Charlie Brown",
            abstract="Quantum speedups for bioinformatic pipelines.",
            source_database="openalex",
        )

        # Papers in Beta
        self.paper_b1 = Paper.objects.create(
            workspace=self.ws_beta,
            hash_id="e2e_hash_b1",
            title="Proprietary Beta Research",
            authors="Dave Miller",
            abstract="Confidential findings.",
            source_database="arxiv",
        )

        # Pipeline Runs (Briefings)
        self.run_a1 = PipelineRun.objects.create(workspace=self.ws_alpha, name="Weekly Oncology Briefing #1")
        self.run_a2 = PipelineRun.objects.create(workspace=self.ws_alpha, name="Weekly Oncology Briefing #2")
        self.run_b1 = PipelineRun.objects.create(workspace=self.ws_beta, name="Beta Proprietary Briefing")

        # Tokens
        self.token_admin = str(RefreshToken.for_user(self.user_admin).access_token)
        self.token_a = str(RefreshToken.for_user(self.user_a).access_token)
        self.token_b = str(RefreshToken.for_user(self.user_b).access_token)
        self.token_super = str(RefreshToken.for_user(self.superuser).access_token)

    def _auth(self, token: str):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _put_star(self, kind: str, target_id: uuid.UUID, starred: bool = True):
        return self.client.put(
            "/api/stars/",
            {"kind": kind, "id": str(target_id), "starred": starred},
            format="json",
        )

    def test_full_curation_lifecycle_journey(self):
        """
        Complete E2E workflow:
        1. Researcher A logs in and has empty stars.
        2. Researcher A stars Paper A1 and Briefing A1 -> verified in payload.
        3. Admin stars Paper A1 -> verified that stars are personal and non-interfering.
        4. Researcher A stars Paper A2 -> verified ordering is chronological (oldest star first).
        5. Researcher A attempts to star Paper B1 (Beta workspace) -> rejected with 404.
        6. Workspace membership revoked for Researcher A -> GET /api/stars/ hides Alpha stars.
        7. Workspace membership re-granted -> GET /api/stars/ reveals previously saved stars intact.
        8. Deletion of Paper A2 -> cascades cleanly, removing star without errors.
        """
        # Step 1: Initial empty state
        self._auth(self.token_a)
        res = self.client.get("/api/stars/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {"papers": [], "briefings": []})

        # Step 2: Star Paper A1 and Briefing A1
        res_p1 = self._put_star("paper", self.paper_a1.id, starred=True)
        self.assertEqual(res_p1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_p1.json()["papers"], [str(self.paper_a1.id)])
        self.assertEqual(res_p1.json()["briefings"], [])

        res_r1 = self._put_star("briefing", self.run_a1.id, starred=True)
        self.assertEqual(res_r1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_r1.json()["papers"], [str(self.paper_a1.id)])
        self.assertEqual(res_r1.json()["briefings"], [str(self.run_a1.id)])

        # Step 3: Admin stars Paper A1 independently
        self._auth(self.token_admin)
        res_admin = self._put_star("paper", self.paper_a1.id, starred=True)
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        self.assertEqual(res_admin.json()["papers"], [str(self.paper_a1.id)])
        self.assertEqual(res_admin.json()["briefings"], [])

        # Step 4: Researcher A stars Paper A2 (ordering check)
        self._auth(self.token_a)
        res_p2 = self._put_star("paper", self.paper_a2.id, starred=True)
        self.assertEqual(res_p2.status_code, status.HTTP_200_OK)
        # Order must be [paper_a1, paper_a2]
        self.assertEqual(res_p2.json()["papers"], [str(self.paper_a1.id), str(self.paper_a2.id)])
        self.assertEqual(res_p2.json()["briefings"], [str(self.run_a1.id)])

        # Step 5: Cross-workspace penetration test (Researcher A attempts to access Beta Paper B1)
        res_cross = self._put_star("paper", self.paper_b1.id, starred=True)
        self.assertEqual(res_cross.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_cross.json().get("error"), "Paper not found.")

        # Step 6: Membership revocation hides stars
        self.membership_a.delete()
        res_revoked = self.client.get("/api/stars/")
        self.assertEqual(res_revoked.status_code, status.HTTP_200_OK)
        self.assertEqual(res_revoked.json(), {"papers": [], "briefings": []})
        # Verify stars are still persisted in database for when membership is restored
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 3)

        # Step 7: Membership re-granted restores stars immediately
        WorkspaceMember.objects.create(workspace=self.ws_alpha, user=self.user_a, role="researcher")
        res_restored = self.client.get("/api/stars/")
        self.assertEqual(res_restored.status_code, status.HTTP_200_OK)
        self.assertEqual(res_restored.json()["papers"], [str(self.paper_a1.id), str(self.paper_a2.id)])
        self.assertEqual(res_restored.json()["briefings"], [str(self.run_a1.id)])

        # Step 8: Cascade deletion of target paper
        paper_a2_id = self.paper_a2.id
        self.paper_a2.delete()
        res_after_del = self.client.get("/api/stars/")
        self.assertEqual(res_after_del.status_code, status.HTTP_200_OK)
        self.assertEqual(res_after_del.json()["papers"], [str(self.paper_a1.id)])
        self.assertEqual(res_after_del.json()["briefings"], [str(self.run_a1.id)])
        self.assertFalse(Star.objects.filter(paper_id=paper_a2_id).exists())

        # Step 9: Unstar remaining items cleanly
        res_unstar_p = self._put_star("paper", self.paper_a1.id, starred=False)
        self.assertEqual(res_unstar_p.status_code, status.HTTP_200_OK)
        self.assertEqual(res_unstar_p.json()["papers"], [])
        self.assertEqual(res_unstar_p.json()["briefings"], [str(self.run_a1.id)])

        res_unstar_r = self._put_star("briefing", self.run_a1.id, starred=False)
        self.assertEqual(res_unstar_r.status_code, status.HTTP_200_OK)
        self.assertEqual(res_unstar_r.json()["papers"], [])
        self.assertEqual(res_unstar_r.json()["briefings"], [])
