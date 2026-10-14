import uuid
from datetime import datetime, timezone
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from research_intelligence.models import (
    Extraction,
    ExtractionDefinition,
    Paper,
    PaperMetric,
    PipelineRun,
    Star,
    Workspace,
    WorkspaceMember,
)

User = get_user_model()


class PapersScorecardAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='tester', password='password123')
        self.other_user = User.objects.create_user(username='other', password='password123')

        # Workspaces
        self.ws_1 = Workspace.objects.create(name='Workspace 1')
        self.ws_2 = Workspace.objects.create(name='Workspace 2')
        self.ws_unauthorized = Workspace.objects.create(name='Secret Workspace')

        # Memberships
        WorkspaceMember.objects.create(workspace=self.ws_1, user=self.user, role='owner')
        WorkspaceMember.objects.create(workspace=self.ws_2, user=self.user, role='viewer')
        WorkspaceMember.objects.create(workspace=self.ws_unauthorized, user=self.other_user, role='owner')

        # Active Definitions
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.ws_1,
            name='TRL Assessment',
            response_schema={"type": "object", "properties": {"trl_score": {"type": "number"}}},
            order=1,
            is_active=True,
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.ws_1,
            name='Schwarz Fit',
            response_schema={"type": "object", "properties": {"fit_score": {"type": "number"}}},
            order=2,
            is_active=True,
        )

        # Pipeline runs
        self.run_1 = PipelineRun.objects.create(workspace=self.ws_1, name='Run 1', status='completed')

        # Papers
        # Paper 1 in ws_1: passed, high score, starred
        self.paper_1 = Paper.objects.create(
            workspace=self.ws_1,
            hash_id='hash_paper_1',
            title='Autonomous Retail Robotics',
            authors='Alice Smith, Bob Jones',
            abstract='Deep reinforcement learning for autonomous store inventory management.',
            arxiv_id='2601.00001',
            doi='10.1000/182',
        )
        PaperMetric.objects.create(
            paper=self.paper_1,
            pipeline_run=self.run_1,
            workspace=self.ws_1,
            signal_score=92.5,
            screening_status='accepted',
        )
        Star.objects.create(user=self.user, paper=self.paper_1, kind='paper')

        # Paper 2 in ws_1: passed, lower score, not starred
        self.paper_2 = Paper.objects.create(
            workspace=self.ws_1,
            hash_id='hash_paper_2',
            title='Inventory Optimization with Transformers',
            authors='Charlie Brown',
            abstract='Transformers for supply chain demand forecasting.',
            arxiv_id='2601.00002',
        )
        PaperMetric.objects.create(
            paper=self.paper_2,
            pipeline_run=self.run_1,
            workspace=self.ws_1,
            signal_score=75.0,
            screening_status='abstract_passed',
        )

        # Paper 3 in ws_1: rejected, matching search term 'Autonomous'
        self.paper_3 = Paper.objects.create(
            workspace=self.ws_1,
            hash_id='hash_paper_3',
            title='Autonomous Drones in Outer Space',
            authors='Dave Astronaut',
            abstract='Off-world autonomous flight controls.',
            arxiv_id='2601.00003',
        )
        PaperMetric.objects.create(
            paper=self.paper_3,
            pipeline_run=self.run_1,
            workspace=self.ws_1,
            signal_score=40.0,
            screening_status='rejected',
        )

        # Paper 4 in ws_2: passed
        self.paper_4 = Paper.objects.create(
            workspace=self.ws_2,
            hash_id='hash_paper_4',
            title='Supply Chain Resiliency',
            authors='Eve Carter',
            abstract='Resilient logistics networks.',
        )
        PaperMetric.objects.create(
            paper=self.paper_4,
            workspace=self.ws_2,
            signal_score=81.0,
            screening_status='full_text_passed',
        )

        # Paper 5 in unauthorized workspace: should never be returned to self.user
        self.paper_hidden = Paper.objects.create(
            workspace=self.ws_unauthorized,
            hash_id='hash_paper_hidden',
            title='Confidential Strategy Paper',
            authors='Zack Secret',
            abstract='Top secret research.',
        )
        PaperMetric.objects.create(
            paper=self.paper_hidden,
            workspace=self.ws_unauthorized,
            signal_score=99.0,
            screening_status='accepted',
        )

    def test_unauthenticated_request_rejected(self):
        resp = self.client.get('/api/papers/scorecard/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_all_accessible_workspaces(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/papers/scorecard/?screening=all')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        # Total accessible papers = 4 (paper_1, paper_2, paper_3 in ws_1, paper_4 in ws_2)
        # paper_hidden must be excluded
        self.assertEqual(data['count'], 4)
        results = data['results']
        result_ids = [p['id'] for p in results]
        self.assertIn(str(self.paper_1.id), result_ids)
        self.assertIn(str(self.paper_2.id), result_ids)
        self.assertIn(str(self.paper_3.id), result_ids)
        self.assertIn(str(self.paper_4.id), result_ids)
        self.assertNotIn(str(self.paper_hidden.id), result_ids)

        # Facets verification
        facets = data['facets']
        self.assertEqual(facets['total'], 4)
        self.assertEqual(facets['score_ceiling'], 100)
        self.assertTrue(facets['has_trl'])
        self.assertEqual(facets['starred_count'], 1)
        self.assertIsNotNone(facets['newest'])
        self.assertTrue(any(d['key'] == 'schwarz_fit' for d in facets['dimension_sorts']))

    def test_workspace_scoping_and_forbidden_workspace(self):
        self.client.force_authenticate(user=self.user)

        # Filter by ws_1 only
        resp = self.client.get(f'/api/papers/scorecard/?workspace_id={self.ws_1.id}&screening=all')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['count'], 3)

        # Request unauthorized workspace
        resp = self.client.get(f'/api/papers/scorecard/?workspace_id={self.ws_unauthorized.id}')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_screening_passed_filter(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/papers/scorecard/?screening=passed')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        # Passed papers: paper_1 (accepted), paper_2 (abstract_passed), paper_4 (full_text_passed)
        # paper_3 (rejected) excluded
        self.assertEqual(data['count'], 3)
        result_ids = [p['id'] for p in data['results']]
        self.assertIn(str(self.paper_1.id), result_ids)
        self.assertIn(str(self.paper_2.id), result_ids)
        self.assertIn(str(self.paper_4.id), result_ids)
        self.assertNotIn(str(self.paper_3.id), result_ids)

    def test_search_and_hidden_by_screening(self):
        self.client.force_authenticate(user=self.user)

        # Search for 'Autonomous' with default screening=passed
        # paper_1 (passed) and paper_3 (rejected) have 'Autonomous'.
        # paper_1 is returned; paper_3 is hidden_by_screening.
        resp = self.client.get('/api/papers/scorecard/?search=Autonomous&screening=passed')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['id'], str(self.paper_1.id))
        self.assertEqual(data['facets']['hidden_by_screening'], 1)

    def test_starred_filter(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/papers/scorecard/?starred=1&screening=all')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['id'], str(self.paper_1.id))

    def test_min_score_filter(self):
        self.client.force_authenticate(user=self.user)
        # min_score=80 -> paper_1 (92.5) and paper_4 (81.0)
        resp = self.client.get('/api/papers/scorecard/?min_score=80&screening=all')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data['count'], 2)
        result_ids = [p['id'] for p in data['results']]
        self.assertIn(str(self.paper_1.id), result_ids)
        self.assertIn(str(self.paper_4.id), result_ids)

    def test_pagination_and_ordering(self):
        self.client.force_authenticate(user=self.user)
        # Page size 2, ordering -signal_score:
        # Expected order across all: paper_1 (92.5), paper_4 (81.0), paper_2 (75.0), paper_3 (40.0)
        resp = self.client.get('/api/papers/scorecard/?screening=all&ordering=-signal_score&page=1&page_size=2')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data['count'], 4)
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(data['results'][0]['id'], str(self.paper_1.id))
        self.assertEqual(data['results'][1]['id'], str(self.paper_4.id))
        self.assertIsNotNone(data['next'])
        self.assertIn('page=2', data['next'])

        # Page 2
        resp_p2 = self.client.get('/api/papers/scorecard/?screening=all&ordering=-signal_score&page=2&page_size=2')
        self.assertEqual(resp_p2.status_code, status.HTTP_200_OK)
        data_p2 = resp_p2.json()
        self.assertEqual(len(data_p2['results']), 2)
        self.assertEqual(data_p2['results'][0]['id'], str(self.paper_2.id))
        self.assertEqual(data_p2['results'][1]['id'], str(self.paper_3.id))
        self.assertIsNotNone(data_p2['previous'])
        self.assertIn('page=1', data_p2['previous'])
