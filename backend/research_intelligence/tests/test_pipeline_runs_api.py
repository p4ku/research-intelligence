import json
import uuid
from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    Paper,
    Extraction,
    Scraper,
)


class PipelineRunsAPITestCase(APITestCase):
    def setUp(self):
        # Create users
        self.user_a = User.objects.create_user(username='user_alpha', password='password123')
        self.user_b = User.objects.create_user(username='user_beta', password='password123')
        self.superuser = User.objects.create_superuser(username='super_admin', password='password123', email='admin@example.com')

        # Create workspaces
        self.workspace_a = Workspace.objects.create(name='Workspace Alpha')
        self.workspace_b = Workspace.objects.create(name='Workspace Beta')

        # Assign memberships
        WorkspaceMember.objects.create(workspace=self.workspace_a, user=self.user_a, role='admin')
        WorkspaceMember.objects.create(workspace=self.workspace_b, user=self.user_b, role='admin')

        # Create pipeline runs
        self.run_a = PipelineRun.objects.create(
            workspace=self.workspace_a,
            status='running',
            current_stage='screening',
            triggered_by=self.user_a
        )
        self.run_b = PipelineRun.objects.create(
            workspace=self.workspace_b,
            status='running',
            current_stage='search',
            triggered_by=self.user_b
        )

        # Create component runs
        self.comp_run_a = ComponentRun.objects.create(
            pipeline_run=self.run_a,
            step_type='screening',
            component_name='gemini_screener',
            status='running'
        )
        self.comp_run_b = ComponentRun.objects.create(
            pipeline_run=self.run_b,
            step_type='search',
            component_name='arxiv_scraper',
            status='running'
        )

        # JWT tokens
        self.token_a = str(RefreshToken.for_user(self.user_a).access_token)
        self.token_b = str(RefreshToken.for_user(self.user_b).access_token)
        self.token_super = str(RefreshToken.for_user(self.superuser).access_token)

    def test_unauthenticated_requests_are_rejected(self):
        """Unauthenticated requests must return 401 Unauthorized."""
        res = self.client.get('/api/pipeline-runs/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res = self.client.get('/api/component-runs/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res = self.client.post('/api/pipeline-runs/', {'workspace_id': str(self.workspace_a.id)})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tenant_isolation_list_and_retrieve_pipeline_runs(self):
        """User A should only see Run A, and User B should only see Run B."""
        # User A list
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')
        res_a = self.client.get('/api/pipeline-runs/')
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        items_a = res_a.data if isinstance(res_a.data, list) else res_a.data.get('results', [])
        run_ids_a = [r['id'] for r in items_a]
        self.assertIn(str(self.run_a.id), run_ids_a)
        self.assertNotIn(str(self.run_b.id), run_ids_a)

        # User A retrieve Run A -> 200 OK with rich telemetry
        res_detail = self.client.get(f'/api/pipeline-runs/{self.run_a.id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['workspace'], self.workspace_a.id)
        self.assertIn('storage_stats', res_detail.data)
        self.assertIn('papers_count', res_detail.data)
        self.assertIn('extractions_count', res_detail.data)
        self.assertIn('component_runs', res_detail.data)
        self.assertIn('schedule', res_detail.data)
        self.assertIn('schedule_name', res_detail.data)
        self.assertIn('reprocess_existing', res_detail.data)

        # User A retrieve Run B -> 404 Not Found (tenant isolated)
        res_cross = self.client.get(f'/api/pipeline-runs/{self.run_b.id}/')
        self.assertEqual(res_cross.status_code, status.HTTP_404_NOT_FOUND)

        # User B list
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_b}')
        res_b = self.client.get('/api/pipeline-runs/')
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)
        items_b = res_b.data if isinstance(res_b.data, list) else res_b.data.get('results', [])
        run_ids_b = [r['id'] for r in items_b]
        self.assertIn(str(self.run_b.id), run_ids_b)
        self.assertNotIn(str(self.run_a.id), run_ids_b)

    def test_tenant_isolation_component_runs(self):
        """Component runs must also be strictly isolated by workspace membership."""
        # User A list component runs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')
        res_a = self.client.get('/api/component-runs/')
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        items_a = res_a.data if isinstance(res_a.data, list) else res_a.data.get('results', [])
        comp_ids_a = [c['id'] for c in items_a]
        self.assertIn(str(self.comp_run_a.id), comp_ids_a)
        self.assertNotIn(str(self.comp_run_b.id), comp_ids_a)

        # User A retrieve Comp Run B -> 404 Not Found
        res_cross = self.client.get(f'/api/component-runs/{self.comp_run_b.id}/')
        self.assertEqual(res_cross.status_code, status.HTTP_404_NOT_FOUND)

        # User A get components of Run A
        res_components = self.client.get(f'/api/pipeline-runs/{self.run_a.id}/components/')
        self.assertEqual(res_components.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_components.data), 1)
        self.assertEqual(res_components.data[0]['id'], str(self.comp_run_a.id))

    def test_create_pipeline_run_cross_workspace_forbidden(self):
        """User A cannot create a pipeline run in Workspace B."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')

        # Create in own workspace -> 201 Created
        res_own = self.client.post('/api/pipeline-runs/', {
            'workspace_id': str(self.workspace_a.id),
            'reprocess_existing': True,
        })
        self.assertEqual(res_own.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_own.data['status'], 'pending')
        self.assertTrue(res_own.data['reprocess_existing'])

        # Create in Workspace B -> 403 Forbidden
        res_foreign = self.client.post('/api/pipeline-runs/', {
            'workspace_id': str(self.workspace_b.id),
        })
        self.assertEqual(res_foreign.status_code, status.HTTP_403_FORBIDDEN)

    @patch('mcp_server.tools.pipeline_runs.triggers.execute_scraper_run_job')
    def test_trigger_step_tenant_isolation(self, mock_scraper_job):
        """User A can trigger steps on Run A, but gets 404 when attempting on Run B."""
        Scraper.objects.create(workspace=self.workspace_a, provider='arxiv', search_query='quantum', is_active=True)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')

        # Trigger search on own workspace run -> 200 OK
        res_own = self.client.post(f'/api/pipeline-runs/{self.run_a.id}/trigger-step/', {
            'step_type': 'search',
            'limit': 10,
        })
        self.assertEqual(res_own.status_code, status.HTTP_200_OK)

        # Trigger step on foreign run -> 404 Not Found
        res_foreign = self.client.post(f'/api/pipeline-runs/{self.run_b.id}/trigger-step/', {
            'step_type': 'search',
            'limit': 10,
        })
        self.assertEqual(res_foreign.status_code, status.HTTP_404_NOT_FOUND)

    def test_abort_and_delete_pipeline_run_tenant_isolation(self):
        """User A cannot abort or delete Run B."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')

        # Abort foreign run -> 404 Not Found
        res_abort_foreign = self.client.post(f'/api/pipeline-runs/{self.run_b.id}/abort/')
        self.assertEqual(res_abort_foreign.status_code, status.HTTP_404_NOT_FOUND)

        # Delete foreign run -> 404 Not Found
        res_delete_foreign = self.client.delete(f'/api/pipeline-runs/{self.run_b.id}/')
        self.assertEqual(res_delete_foreign.status_code, status.HTTP_404_NOT_FOUND)

        # Abort own run -> 200 OK
        res_abort_own = self.client.post(f'/api/pipeline-runs/{self.run_a.id}/abort/')
        self.assertEqual(res_abort_own.status_code, status.HTTP_200_OK)
        self.run_a.refresh_from_db()
        self.assertEqual(self.run_a.status, 'aborted')

        # Delete own run -> 200 OK
        res_delete_own = self.client.delete(f'/api/pipeline-runs/{self.run_a.id}/')
        self.assertEqual(res_delete_own.status_code, status.HTTP_200_OK)
        self.assertFalse(PipelineRun.objects.filter(id=self.run_a.id).exists())

    def test_superuser_without_membership_has_no_access_to_workspaces(self):
        """Superuser without membership in workspaces must NOT see any pipeline runs."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_super}')
        res = self.client.get('/api/pipeline-runs/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.data if isinstance(res.data, list) else res.data.get('results', [])
        self.assertEqual(len(items), 0)

    def test_pause_and_resume_pipeline_run(self):
        """User A can pause and resume Run A with full audit history tracking."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')

        # Pause own run -> 200 OK
        res_pause = self.client.post(f'/api/pipeline-runs/{self.run_a.id}/pause/', {'reason': 'Maintenance pause'})
        self.assertEqual(res_pause.status_code, status.HTTP_200_OK)
        self.run_a.refresh_from_db()
        self.assertEqual(self.run_a.status, 'paused')
        self.assertEqual(self.run_a.status_message, 'Maintenance pause')
        self.assertTrue(any(e.get('event') == 'paused' for e in self.run_a.step_history))

        # Pause foreign run -> 404 Not Found
        res_foreign = self.client.post(f'/api/pipeline-runs/{self.run_b.id}/pause/')
        self.assertEqual(res_foreign.status_code, status.HTTP_404_NOT_FOUND)

        # Resume own run -> 200 OK
        with patch('research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick') as mock_notify:
            res_resume = self.client.post(f'/api/pipeline-runs/{self.run_a.id}/resume/')
            self.assertEqual(res_resume.status_code, status.HTTP_200_OK)
            self.run_a.refresh_from_db()
            self.assertEqual(self.run_a.status, 'running')
            self.assertTrue(any(e.get('event') == 'resumed' for e in self.run_a.step_history))
            mock_notify.assert_called_once()

    def test_tick_pipeline_run(self):
        """User A can trigger a manual DAG tick on Run A."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')
        with patch('research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick') as mock_tick:
            mock_tick.return_value = {"success": True, "status": "running", "current_stage": "search"}
            res = self.client.post(f'/api/pipeline-runs/{self.run_a.id}/tick/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertTrue(res.data['success'])
            mock_tick.assert_called_once_with(self.run_a.id)

    @patch('research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick')
    def test_rerun_from_step_api(self, mock_notify):
        """User A can trigger rerun from a specific step or auto-resume via REST API."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')

        # Create paper and component runs
        from research_intelligence.models import Paper, ComponentRun
        Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="p_api_rerun",
            title="API Rerun Paper",
            authors="Author",
            abstract="Abstract",
            source_database="arxiv",
            screening_status="accepted"
        )
        ComponentRun.objects.create(pipeline_run=self.run_a, step_type="search", component_name="search", status="completed")
        ComponentRun.objects.create(pipeline_run=self.run_a, step_type="screening", component_name="abstract_screening", status="completed")
        ComponentRun.objects.create(pipeline_run=self.run_a, step_type="download", component_name="download", status="failed", error_message="Timeout")

        # Foreign user B cannot rerun run A -> 404
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_b}')
        res_foreign = self.client.post(f'/api/pipeline-runs/{self.run_a.id}/rerun-from-step/', {'step_name': 'download'})
        self.assertEqual(res_foreign.status_code, status.HTTP_404_NOT_FOUND)

        # User A triggers rerun with auto-detection -> 200 OK
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')
        res_own = self.client.post(f'/api/pipeline-runs/{self.run_a.id}/rerun-from-step/')
        self.assertEqual(res_own.status_code, status.HTTP_200_OK)
        self.assertEqual(res_own.data['status'], 'success')
        self.assertEqual(res_own.data['resumed_from_step'], 'download')

    @patch('research_intelligence.tasks.orchestrator.dag.DownloadNode.execute')
    def test_reexecute_component_run_api(self, mock_execute):
        """User A can re-execute an isolated failed component task via REST API."""
        from research_intelligence.models import ComponentRun
        cr = ComponentRun.objects.create(
            pipeline_run=self.run_a,
            step_type="download",
            component_name="download",
            status="failed",
            error_message="Worker died"
        )

        # Foreign user B cannot re-execute -> 404
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_b}')
        res_foreign = self.client.post(f'/api/component-runs/{cr.id}/reexecute/')
        self.assertEqual(res_foreign.status_code, status.HTTP_404_NOT_FOUND)

        # User A re-executes -> 200 OK
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')
        res_own = self.client.post(f'/api/component-runs/{cr.id}/reexecute/')
        self.assertEqual(res_own.status_code, status.HTTP_200_OK)
        self.assertEqual(res_own.data['status'], 'success')
        mock_execute.assert_called_once()

    @patch('research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick')
    def test_start_pipeline_run_endpoint_with_date_range(self, mock_tick):
        """User A starts an autonomous pipeline run with custom date range and n_last_days."""
        mock_tick.return_value = {"success": True, "status": "running"}
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')
        payload = {
            "workspace_id": str(self.workspace_a.id),
            "name": "Date Filtered Review",
            "start_date": "2026-08-01",
            "end_date": "2026-08-15",
            "n_last_days": 14,
            "autonomous": True
        }
        res = self.client.post('/api/pipeline-runs/start/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("pipeline_run_id", res.data)
        pr = PipelineRun.objects.get(id=res.data["pipeline_run_id"])
        self.assertEqual(pr.configuration_override.get("start_date"), "2026-08-01")
        self.assertEqual(pr.configuration_override.get("end_date"), "2026-08-15")
        self.assertEqual(pr.configuration_override.get("n_last_days"), 14)

    @patch('research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick')
    def test_workspace_run_pipeline_endpoint_with_date_range(self, mock_tick):
        """User A triggers an autonomous pipeline run via workspace action with date parameters."""
        mock_tick.return_value = {"success": True, "status": "running"}
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')
        payload = {
            "start_date": "2026-07-01",
            "end_date": "2026-07-20",
            "n_last_days": 10
        }
        res = self.client.post(f'/api/workspaces/{self.workspace_a.id}/run-pipeline/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("pipeline_run_id", res.data)
        pr = PipelineRun.objects.get(id=res.data["pipeline_run_id"])
        self.assertEqual(pr.configuration_override.get("start_date"), "2026-07-01")
        self.assertEqual(pr.configuration_override.get("end_date"), "2026-07-20")
        self.assertEqual(pr.configuration_override.get("n_last_days"), 10)

    @patch('research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay')
    def test_trigger_search_step_endpoint_with_date_range(self, mock_delay):
        """Triggering search step on an existing run forwards date parameters."""
        mock_delay.return_value = MagicMock(id="celery_123")
        Scraper.objects.get_or_create(
            workspace=self.workspace_a,
            provider="arxiv",
            defaults={"search_query": "deep learning", "is_active": True}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_a}')
        payload = {
            "step_type": "search",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "n_last_days": 5
        }
        res = self.client.post(f'/api/pipeline-runs/{self.run_a.id}/trigger-step/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        new_pr_id = res.data.get("pipeline_run_id")
        cr = ComponentRun.objects.filter(pipeline_run_id=new_pr_id, step_type="search").first()
        self.assertIsNotNone(cr)
        self.assertEqual(cr.input_params.get("start_date"), "2026-08-01")
        self.assertEqual(cr.input_params.get("end_date"), "2026-08-10")
        self.assertEqual(cr.input_params.get("n_last_days"), 5)


