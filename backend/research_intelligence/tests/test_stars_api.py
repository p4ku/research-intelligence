import uuid
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    Paper,
    Star,
)


class StarsAPITestCase(APITestCase):
    """
    /api/stars/ — per-user stars on papers and briefings (pipeline runs).
    Two users in two workspaces; stars must stay personal and workspace-scoped.
    """

    def setUp(self):
        self.user_a = User.objects.create_user(username='star_alpha', password='password123')
        self.user_b = User.objects.create_user(username='star_beta', password='password123')
        self.superuser = User.objects.create_superuser(username='star_super', password='password123', email='super@example.com')

        self.workspace_a = Workspace.objects.create(name='Stars Workspace Alpha')
        self.workspace_b = Workspace.objects.create(name='Stars Workspace Beta')
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.user_a, role='researcher')
        WorkspaceMember.objects.create(workspace=self.workspace_b, user=self.user_b, role='researcher')

        self.run_a = PipelineRun.objects.create(workspace=self.workspace_a)
        self.run_b = PipelineRun.objects.create(workspace=self.workspace_b)

        self.paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            hash_id='hash_star_a',
            title='Paper A',
            authors='Author A',
            abstract='Abstract A',
            source_database='arxiv',
        )
        self.paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            hash_id='hash_star_b',
            title='Paper B',
            authors='Author B',
            abstract='Abstract B',
            source_database='arxiv',
        )

        self.token_a = str(RefreshToken.for_user(self.user_a).access_token)
        self.token_b = str(RefreshToken.for_user(self.user_b).access_token)
        self.token_super = str(RefreshToken.for_user(self.superuser).access_token)

    # --- helpers ---

    def _as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _put(self, kind, target_id, starred=True):
        return self.client.put(
            '/api/stars/',
            {'kind': kind, 'id': str(target_id), 'starred': starred},
            format='json',
        )

    # --- auth ---

    def test_unauthenticated_get_and_put_are_401(self):
        res = self.client.get('/api/stars/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res = self._put('paper', self.paper_a.id)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- read ---

    def test_get_empty_set(self):
        self._as(self.token_a)
        res = self.client.get('/api/stars/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {'papers': [], 'briefings': []})

    # --- write ---

    def test_put_star_paper_returns_full_set(self):
        self._as(self.token_a)
        res = self._put('paper', self.paper_a.id)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {'papers': [str(self.paper_a.id)], 'briefings': []})

        star = Star.objects.get(user=self.user_a)
        self.assertEqual(star.kind, Star.KIND_PAPER)
        self.assertEqual(star.paper_id, self.paper_a.id)
        self.assertIsNone(star.pipeline_run_id)

    def test_put_star_briefing_maps_to_pipeline_run(self):
        self._as(self.token_a)
        res = self._put('briefing', self.run_a.id)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {'papers': [], 'briefings': [str(self.run_a.id)]})

        star = Star.objects.get(user=self.user_a)
        self.assertEqual(star.kind, Star.KIND_PIPELINE_RUN)
        self.assertEqual(star.pipeline_run_id, self.run_a.id)
        self.assertIsNone(star.paper_id)

    def test_put_is_idempotent(self):
        self._as(self.token_a)
        first = self._put('paper', self.paper_a.id)
        second = self._put('paper', self.paper_a.id)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.json()['papers'], [str(self.paper_a.id)])
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 1)

    def test_put_unstar_then_unstar_again(self):
        self._as(self.token_a)
        self._put('paper', self.paper_a.id)
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 1)

        res = self._put('paper', self.paper_a.id, starred=False)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {'papers': [], 'briefings': []})
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 0)

        # Repeating unstar is a 200 no-op.
        res = self._put('paper', self.paper_a.id, starred=False)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {'papers': [], 'briefings': []})

    # --- isolation and 404s ---

    def test_put_cross_workspace_is_404_and_does_not_star(self):
        """User A cannot star Paper B or Run B, which live in Workspace B."""
        self._as(self.token_a)

        res = self._put('paper', self.paper_b.id)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', res.json())
        self.assertEqual(Star.objects.count(), 0)

        res = self._put('briefing', self.run_b.id)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', res.json())
        self.assertEqual(Star.objects.count(), 0)

    def test_put_unknown_uuid_is_404(self):
        self._as(self.token_a)
        res = self._put('paper', uuid.uuid4())
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.json()['error'], 'Paper not found.')
        self.assertEqual(Star.objects.count(), 0)

    def test_put_wrong_kind_for_target_is_404(self):
        """A run id under kind=paper (and the reverse) is not found, even though the object exists."""
        self._as(self.token_a)
        res = self._put('paper', self.run_a.id)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        res = self._put('briefing', self.paper_a.id)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.json()['error'], 'Briefing not found.')
        self.assertEqual(Star.objects.count(), 0)

    def test_put_unstar_cross_workspace_is_404(self):
        self._as(self.token_a)
        res = self._put('paper', self.paper_b.id, starred=False)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_methods_are_405(self):
        self._as(self.token_a)
        body = {'kind': 'paper', 'id': str(self.paper_a.id), 'starred': True}
        self.assertEqual(self.client.post('/api/stars/', body, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.patch('/api/stars/', body, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete('/api/stars/').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_put_invalid_body_is_400(self):
        self._as(self.token_a)

        res = self._put('report', self.paper_a.id)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        res = self.client.put('/api/stars/', {'kind': 'paper', 'id': 'not-a-uuid', 'starred': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        res = self.client.put('/api/stars/', {'kind': 'paper', 'id': str(self.paper_a.id)}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(Star.objects.count(), 0)

    def test_superuser_can_star_any_workspace(self):
        self._as(self.token_super)
        res = self._put('paper', self.paper_b.id)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self._put('briefing', self.run_a.id)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {'papers': [str(self.paper_b.id)], 'briefings': [str(self.run_a.id)]})

    # --- ordering and isolation ---

    def test_get_orders_oldest_first_and_restar_appends(self):
        paper_a2 = Paper.objects.create(
            workspace=self.workspace_a,
            hash_id='hash_star_a2',
            title='Paper A2',
            authors='Author A2',
            abstract='Abstract A2',
            source_database='arxiv',
        )
        self._as(self.token_a)
        self._put('paper', self.paper_a.id)
        self._put('briefing', self.run_a.id)
        self._put('paper', paper_a2.id)

        res = self.client.get('/api/stars/')
        self.assertEqual(res.json()['papers'], [str(self.paper_a.id), str(paper_a2.id)])
        self.assertEqual(res.json()['briefings'], [str(self.run_a.id)])

        self._put('paper', self.paper_a.id, starred=False)
        self._put('paper', self.paper_a.id, starred=True)
        res = self.client.get('/api/stars/')
        self.assertEqual(res.json()['papers'], [str(paper_a2.id), str(self.paper_a.id)])

    def test_get_hides_stars_after_membership_revoked(self):
        self._as(self.token_a)
        self._put('paper', self.paper_a.id)
        self._put('briefing', self.run_a.id)

        WorkspaceMember.objects.filter(workspace=self.workspace_a, user=self.user_a).delete()

        res = self.client.get('/api/stars/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {'papers': [], 'briefings': []})
        # Rows are kept: membership can be restored.
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 2)

    def test_deleting_target_cascades_star(self):
        self._as(self.token_a)
        self._put('paper', self.paper_a.id)
        self._put('briefing', self.run_a.id)
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 2)

        self.paper_a.delete()
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 1)
        self.run_a.delete()
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 0)

    def test_stars_are_per_user(self):
        self._as(self.token_a)
        self._put('paper', self.paper_a.id)

        self._as(self.token_b)
        res = self.client.get('/api/stars/')
        self.assertEqual(res.json(), {'papers': [], 'briefings': []})

        self._as(self.token_super)
        res = self.client.get('/api/stars/')
        self.assertEqual(res.json(), {'papers': [], 'briefings': []})

    def test_two_users_can_star_the_same_paper(self):
        """unique_together is per user, not global."""
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.user_b, role='researcher')
        self._as(self.token_a)
        self.assertEqual(self._put('paper', self.paper_a.id).status_code, status.HTTP_200_OK)
        self._as(self.token_b)
        res = self._put('paper', self.paper_a.id)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()['papers'], [str(self.paper_a.id)])
        self.assertEqual(Star.objects.filter(paper=self.paper_a).count(), 2)

    def test_deleting_user_cascades_stars(self):
        self._as(self.token_a)
        self._put('paper', self.paper_a.id)
        self.assertEqual(Star.objects.count(), 1)
        self.user_a.delete()
        self.assertEqual(Star.objects.count(), 0)

    # --- model invariants ---

    def test_unique_together_is_enforced(self):
        Star.objects.create(user=self.user_a, kind=Star.KIND_PAPER, paper=self.paper_a)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Star.objects.create(user=self.user_a, kind=Star.KIND_PAPER, paper=self.paper_a)
        # A paper star and a briefing star for the same user do not collide on the NULL column.
        Star.objects.create(user=self.user_a, kind=Star.KIND_PIPELINE_RUN, pipeline_run=self.run_a)
        Star.objects.create(user=self.user_a, kind=Star.KIND_PIPELINE_RUN, pipeline_run=self.run_b)
        self.assertEqual(Star.objects.filter(user=self.user_a).count(), 3)

    def test_db_rejects_wrong_or_missing_target(self):
        """The check constraint holds even when clean() is bypassed (bulk writes, shell, get_or_create)."""
        cases = [
            dict(kind=Star.KIND_PAPER),
            dict(kind=Star.KIND_PAPER, paper=self.paper_a, pipeline_run=self.run_a),
            dict(kind=Star.KIND_PAPER, pipeline_run=self.run_a),
            dict(kind=Star.KIND_PIPELINE_RUN, paper=self.paper_a),
        ]
        for fields in cases:
            with self.subTest(fields=fields):
                with transaction.atomic():
                    with self.assertRaises(IntegrityError):
                        Star.objects.create(user=self.user_a, **fields)
        self.assertEqual(Star.objects.count(), 0)

    def test_clean_rejects_two_targets_or_none(self):
        with self.assertRaises(ValidationError):
            Star(user=self.user_a, kind=Star.KIND_PAPER, paper=self.paper_a, pipeline_run=self.run_a).full_clean()
        with self.assertRaises(ValidationError):
            Star(user=self.user_a, kind=Star.KIND_PAPER).full_clean()
        with self.assertRaises(ValidationError):
            Star(user=self.user_a, kind=Star.KIND_PAPER, pipeline_run=self.run_a).full_clean()
        Star(user=self.user_a, kind=Star.KIND_PAPER, paper=self.paper_a).full_clean()
