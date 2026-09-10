import base64
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from research_intelligence.admin_views.queue_monitor import (
    decode_celery_message,
    format_elapsed_time,
)
from research_intelligence.models import ComponentRun, PipelineRun, Workspace

User = get_user_model()


class QueueMonitorTestCase(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_superuser(
            username="queue_admin",
            email="queue_admin@example.com",
            password="adminpassword123",
        )
        self.regular_user = User.objects.create_user(
            username="regular_user",
            email="regular@example.com",
            password="userpassword123",
            is_staff=False,
        )
        self.workspace = Workspace.objects.create(
            name="Test Research WS",
        )

    def test_format_elapsed_time(self):
        self.assertEqual(format_elapsed_time(None), "0s")
        self.assertEqual(format_elapsed_time(-5), "0s")
        self.assertEqual(format_elapsed_time(0), "0s")
        self.assertEqual(format_elapsed_time(42), "42s")
        self.assertEqual(format_elapsed_time(125), "2m 05s")
        self.assertEqual(format_elapsed_time(3665), "1h 01m 05s")

    def test_decode_celery_message_with_headers(self):
        msg_payload = {
            "headers": {
                "task": "research_intelligence.tasks.step_1_search.search.execute_search_step",
                "id": "abc-123",
                "argsrepr": "('run-uuid',)",
                "kwargsrepr": "{'query': 'quantum'}",
                "retries": 0,
            }
        }
        decoded = decode_celery_message(json.dumps(msg_payload))
        self.assertEqual(decoded["task"], "research_intelligence.tasks.step_1_search.search.execute_search_step")
        self.assertEqual(decoded["id"], "abc-123")
        self.assertEqual(decoded["args"], "('run-uuid',)")
        self.assertEqual(decoded["kwargs"], "{'query': 'quantum'}")

    def test_decode_celery_message_with_base64_body(self):
        body_content = json.dumps([["arg1", "arg2"], {"limit": 100}])
        body_b64 = base64.b64encode(body_content.encode("utf-8")).decode("utf-8")
        msg_payload = {
            "task": "custom.task",
            "id": "task-xyz",
            "body": body_b64,
        }
        decoded = decode_celery_message(json.dumps(msg_payload))
        self.assertEqual(decoded["task"], "custom.task")
        self.assertEqual(decoded["id"], "task-xyz")
        self.assertIn("arg1", decoded["args"])
        self.assertIn("limit", decoded["kwargs"])

    def test_decode_celery_message_fallback(self):
        decoded = decode_celery_message("not-a-valid-json")
        self.assertEqual(decoded["task"], "Raw Message")
        self.assertEqual(decoded["args"], "not-a-valid-json")

    def test_access_requires_staff(self):
        url = reverse("admin:queue-monitor")

        # Anonymous user
        resp_anon = self.client.get(url)
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn("/admin/login", resp_anon.url)

        # Regular non-staff user
        self.client.force_login(self.regular_user)
        resp_user = self.client.get(url)
        self.assertEqual(resp_user.status_code, 302)
        self.assertIn("/admin/login", resp_user.url)

    def test_access_staff_success(self):
        self.client.force_login(self.staff_user)
        url = reverse("admin:queue-monitor")
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(resp, "Live Monitor")
        self.assertContains(resp, "Messages in Broker Queues (Redis)")
        self.assertContains(resp, "Active In-Progress Tasks")
        self.assertContains(resp, "Active SLR Pipeline Runs")
        self.assertContains(resp, "Celery Worker Nodes")

    def test_auto_refresh_meta(self):
        self.client.force_login(self.staff_user)
        url = f"{reverse('admin:queue-monitor')}?refresh=10&sync=1"
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '<meta http-equiv="refresh" content="10">')

    def test_renders_running_pipeline_and_components(self):
        self.client.force_login(self.staff_user)

        now = timezone.now()
        pipe = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Quantum Discovery Run",
            status="running",
            current_stage="search",
            total_papers_fetched=45,
        )
        PipelineRun.objects.filter(id=pipe.id).update(started_at=now - timedelta(minutes=15))

        comp = ComponentRun.objects.create(
            pipeline_run=pipe,
            component_name="arxiv_scraper",
            step_type="search",
            status="running",
            celery_task_id="celery-comp-999",
            input_params={"query": "quantum error correction"},
        )
        ComponentRun.objects.filter(id=comp.id).update(started_at=now - timedelta(minutes=12))

        resp = self.client.get(reverse("admin:queue-monitor") + "?sync=1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Quantum Discovery Run")
        self.assertContains(resp, "arxiv_scraper")
        self.assertContains(resp, "celery-comp-999")
        self.assertIn("12m ", resp.content.decode("utf-8"))

    @patch("research_intelligence.admin_views.queue_monitor.reap_zombie_tasks")
    def test_run_watchdog_action(self, mock_watchdog):
        mock_watchdog.return_value = {"reaped_components": 2, "reaped_pipelines": 1}
        self.client.force_login(self.staff_user)

        url = f"{reverse('admin:queue-monitor')}?action=run_watchdog"
        resp = self.client.get(url, follow=True)

        self.assertEqual(resp.status_code, 200)
        mock_watchdog.assert_called_once()
        self.assertContains(resp, "Reaped 2 stalled component(s) and 1 pipeline run(s)")

    @patch("research_intelligence.admin_views.queue_monitor.QueueMonitorView.get_redis_client")
    def test_mocked_redis_queues(self, mock_get_redis):
        mock_r = MagicMock()
        mock_r.scan_iter.return_value = []
        mock_r.llen.side_effect = lambda q: 3 if q == "celery" else 0
        mock_r.lrange.return_value = [
            json.dumps({
                "headers": {
                    "task": "research_intelligence.tasks.step_1_search.search.execute_search_step",
                    "id": "redis-task-001",
                    "argsrepr": "('pipeline-1',)",
                }
            }).encode("utf-8")
        ]
        mock_get_redis.return_value = mock_r

        self.client.force_login(self.staff_user)
        resp = self.client.get(reverse("admin:queue-monitor") + "?sync=1")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "celery")
        self.assertContains(resp, "redis-task-001")
        self.assertContains(resp, "execute_search_step")

    def test_check_task_liveness_active_worker(self):
        from research_intelligence.utils.celery_liveness import check_task_liveness
        active_map = {"task-123": {"worker": "celery@node-1", "time_start": 100}}
        res = check_task_liveness("task-123", "running", active_map=active_map)
        self.assertEqual(res["state"], "ACTIVE")
        self.assertTrue(res["is_alive"])
        self.assertFalse(res["is_ghost"])
        self.assertIn("node-1", res["badge_text"])

    def test_check_task_liveness_ghost_task(self):
        from research_intelligence.utils.celery_liveness import check_task_liveness
        res = check_task_liveness(
            "ghost-task-999",
            "running",
            active_map={},
            reserved_set=set(),
            inspector_ok=True,
            duration_seconds=300.0,
        )
        self.assertEqual(res["state"], "GHOST")
        self.assertFalse(res["is_alive"])
        self.assertTrue(res["is_ghost"])
        self.assertIn("NO WORKER / STALLED", res["badge_text"])

    def test_check_task_liveness_recent_progress(self):
        from research_intelligence.utils.celery_liveness import check_task_liveness
        res = check_task_liveness(
            "progress-task-111",
            "running",
            active_map={},
            reserved_set=set(),
            inspector_ok=True,
            duration_seconds=500.0,
            metrics={"last_progress_at": (timezone.now() - timedelta(seconds=15)).isoformat()},
        )
        self.assertEqual(res["state"], "ACTIVE")
        self.assertTrue(res["is_alive"])
        self.assertFalse(res["is_ghost"])
        self.assertIn("ACTIVE (PROGRESSING)", res["badge_text"])

    def test_check_task_liveness_starting_grace_period(self):
        from research_intelligence.utils.celery_liveness import check_task_liveness
        # Dispatched 20 seconds ago, not in worker map yet
        res = check_task_liveness(
            "starting-task-222",
            "running",
            active_map={},
            reserved_set=set(),
            inspector_ok=True,
            duration_seconds=20.7,
        )
        self.assertEqual(res["state"], "STARTING")
        self.assertTrue(res["is_alive"])
        self.assertFalse(res["is_ghost"])
        self.assertIn("QUEUED / STARTING", res["badge_text"])

    def test_component_run_changelist_ghost_detection(self):
        self.client.force_login(self.staff_user)
        now = timezone.now()
        pipe = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Ghost Test Pipeline",
            status="running",
        )
        comp = ComponentRun.objects.create(
            pipeline_run=pipe,
            component_name="abstract_screening",
            step_type="screening",
            status="running",
            celery_task_id="dead-worker-task-777",
        )
        ComponentRun.objects.filter(id=comp.id).update(started_at=now - timedelta(minutes=10))

        with patch("research_intelligence.utils.celery_liveness.get_active_celery_tasks_map") as mock_inspect:
            mock_inspect.return_value = ({}, set(), True)
            url = reverse("admin:research_intelligence_componentrun_changelist")
            resp = self.client.get(url)

            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "NO WORKER / STALLED")
            self.assertContains(resp, "RUNNING (💀 GHOST)")

    def test_mark_ghost_tasks_failed_action(self):
        self.client.force_login(self.staff_user)
        pipe = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Abort Ghost Pipeline",
            status="running",
        )
        comp = ComponentRun.objects.create(
            pipeline_run=pipe,
            component_name="abstract_screening",
            step_type="screening",
            status="running",
            celery_task_id="terminate-me-123",
        )
        url = reverse("admin:research_intelligence_componentrun_changelist")
        data = {
            "action": "mark_ghost_tasks_failed_action",
            "_selected_action": [str(comp.id)],
        }
        resp = self.client.post(url, data, follow=True)
        self.assertEqual(resp.status_code, 200)

        comp.refresh_from_db()
        self.assertEqual(comp.status, "failed")
        self.assertIn("Manually terminated by admin", comp.error_message)

    @patch("research_intelligence.admin_views.queue_monitor.QueueMonitorView.get_celery_worker_data")
    def test_active_tasks_deduplication(self, mock_get_worker_data):
        """
        Verify that a ComponentRun in DB and the corresponding active Celery task
        are counted as ONE task (not double-counted as 1+1=2).
        """
        self.client.force_login(self.staff_user)
        now = timezone.now()
        pipe = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Deduplication Test Pipeline",
            status="running",
        )
        task_uuid = "ab99f176-1958-466a-b75a-551ef579fa03"
        ComponentRun.objects.create(
            pipeline_run=pipe,
            component_name="abstract_screening",
            step_type="screening",
            status="running",
            celery_task_id=task_uuid,
            started_at=now - timedelta(minutes=5),
        )

        mock_get_worker_data.return_value = (
            [
                {
                    "worker": "celery@node-01",
                    "id": task_uuid,
                    "name": "abstract_screening",
                    "start_time": "17:42:53 UTC",
                    "elapsed_seconds": 307.0,
                    "elapsed_display": "5m 07s",
                    "args": "()",
                    "kwargs": "{}",
                }
            ],
            [
                {"name": "celery@node-01", "status": "Online", "concurrency": 2, "active_count": 1, "processed_count": 10}
            ],
            "",
        )

        resp = self.client.get(reverse("admin:queue-monitor") + "?sync=1")
        self.assertEqual(resp.status_code, 200)

        # Total active count must be 1, NOT 2!
        self.assertEqual(resp.context["total_active_tasks"], 1)
        self.assertIn("1 in DB &amp; active on worker", resp.content.decode("utf-8"))
        self.assertContains(resp, "celery@node-01")
        self.assertContains(resp, task_uuid)

    def test_ajax_json_endpoint(self):
        """Verify that GET ?format=json returns the complete real-time cluster state as JSON."""
        self.client.force_login(self.staff_user)

        now = timezone.now()
        pipe = PipelineRun.objects.create(
            workspace=self.workspace,
            name="JSON API Test Pipeline",
            status="running",
            current_stage="extraction",
        )
        comp = ComponentRun.objects.create(
            pipeline_run=pipe,
            component_name="deep_extractor",
            step_type="extraction",
            status="running",
            celery_task_id="json-test-celery-123",
            started_at=now - timedelta(minutes=3),
        )

        url = f"{reverse('admin:queue-monitor')}?format=json"
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/json")
        data = resp.json()

        self.assertTrue(data["success"])
        self.assertIn("last_updated_str", data)
        self.assertGreaterEqual(data["total_active_tasks"], 1)
        self.assertIsInstance(data["running_components"], list)
        self.assertIsInstance(data["running_pipelines"], list)
        self.assertIsInstance(data["queue_summaries"], list)

        # Ensure component details are serialized
        matched_comp = next((c for c in data["running_components"] if c["id"] == str(comp.id)), None)
        self.assertIsNotNone(matched_comp)
        self.assertEqual(matched_comp["component_name"], "deep_extractor")
        self.assertEqual(matched_comp["celery_task_id"], "json-test-celery-123")
        self.assertIn("admin_change_url", matched_comp)

    def test_ajax_json_unauthenticated_forbidden(self):
        """Verify that unauthorized requests are redirected to admin login, and direct dispatch returns 403."""
        url = f"{reverse('admin:queue-monitor')}?format=json"

        # Anonymous user via Django Admin is redirected to login
        resp_anon = self.client.get(url)
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn("/admin/login", resp_anon.url)

        # Non-staff user via Django Admin is redirected to login
        self.client.force_login(self.regular_user)
        resp_user = self.client.get(url)
        self.assertEqual(resp_user.status_code, 302)
        self.assertIn("/admin/login", resp_user.url)

        # Direct view dispatch returns 403 JSON for non-staff
        from django.test import RequestFactory
        from research_intelligence.admin_views.queue_monitor import QueueMonitorView
        factory = RequestFactory()
        req = factory.get(url)
        req.user = self.regular_user
        view_resp = QueueMonitorView.as_view()(req)
        self.assertEqual(view_resp.status_code, 403)
        self.assertFalse(json.loads(view_resp.content.decode("utf-8"))["success"])

    @patch("research_intelligence.tasks.orchestrator.dag.build_default_slr_dag")
    def test_post_restart_task_success(self, mock_build_dag):
        """Verify that POST action=restart_task resets status and dispatches on Celery."""
        mock_node = MagicMock()
        mock_dag = MagicMock()
        mock_node.step_type = "search"
        mock_dag.nodes = {"search_node": mock_node}
        mock_build_dag.return_value = mock_dag

        self.client.force_login(self.staff_user)
        pipe = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Restart Test Pipeline",
            status="running",
        )
        comp = ComponentRun.objects.create(
            pipeline_run=pipe,
            component_name="search_step",
            step_type="search",
            status="stalled",
            celery_task_id="old-celery-id-999",
        )

        url = reverse("admin:queue-monitor")
        payload = {
            "action": "restart_task",
            "component_id": str(comp.id),
        }
        resp = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("Restarted task 'search_step'", data["message"])

        comp.refresh_from_db()
        self.assertEqual(comp.status, "running")
        self.assertEqual(comp.error_message, "")
        self.assertIsNone(comp.celery_task_id)
        self.assertEqual(comp.metrics.get("reexecuted_by"), "queue_admin")
        mock_node.execute.assert_called_once_with(pipe, comp)

    def test_post_restart_task_not_found(self):
        """Verify error response when restarting a nonexistent component."""
        self.client.force_login(self.staff_user)
        url = reverse("admin:queue-monitor")
        payload = {
            "action": "restart_task",
            "component_id": "00000000-0000-0000-0000-000000000000",
        }
        resp = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("not found", data["message"])

    @patch("django_project.celery.app.control.revoke")
    def test_post_kill_task_component(self, mock_revoke):
        """Verify that POST action=kill_task revokes in Celery and marks aborted in DB."""
        self.client.force_login(self.staff_user)
        pipe = PipelineRun.objects.create(
            workspace=self.workspace,
            name="Kill Test Pipeline",
            status="running",
        )
        comp = ComponentRun.objects.create(
            pipeline_run=pipe,
            component_name="heavy_clustering",
            step_type="clustering",
            status="running",
            celery_task_id="kill-celery-id-444",
        )

        url = reverse("admin:queue-monitor")
        payload = {
            "action": "kill_task",
            "component_id": str(comp.id),
        }
        resp = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("Successfully killed task", data["message"])

        mock_revoke.assert_called_once_with("kill-celery-id-444", terminate=True, signal="SIGKILL")
        comp.refresh_from_db()
        self.assertEqual(comp.status, "aborted")
        self.assertIn("Manually terminated by administrator (queue_admin)", comp.error_message)

    @patch("django_project.celery.app.control.revoke")
    def test_post_kill_task_celery_id_only(self, mock_revoke):
        """Verify that killing an orphaned Celery task (without DB component) revokes it directly."""
        self.client.force_login(self.staff_user)
        url = reverse("admin:queue-monitor")
        payload = {
            "action": "kill_task",
            "celery_task_id": "orphaned-celery-task-888",
        }
        resp = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("SIGKILL revocation signal sent", data["message"])
        mock_revoke.assert_called_once_with("orphaned-celery-task-888", terminate=True, signal="SIGKILL")

    @patch("research_intelligence.admin_views.queue_monitor.reap_zombie_tasks")
    def test_post_run_watchdog(self, mock_watchdog):
        """Verify that POST action=run_watchdog executes watchdog and returns stats."""
        mock_watchdog.return_value = {"reaped_components": 3, "reaped_pipelines": 2}
        self.client.force_login(self.staff_user)

        url = reverse("admin:queue-monitor")
        payload = {"action": "run_watchdog"}
        resp = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("Reaped 3 stalled component(s) and 2 pipeline run(s)", data["message"])
        mock_watchdog.assert_called_once()


