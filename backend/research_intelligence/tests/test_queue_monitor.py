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
        url = f"{reverse('admin:queue-monitor')}?refresh=10"
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

        resp = self.client.get(reverse("admin:queue-monitor"))
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
        resp = self.client.get(reverse("admin:queue-monitor"))

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

        resp = self.client.get(reverse("admin:queue-monitor"))
        self.assertEqual(resp.status_code, 200)

        # Total active count must be 1, NOT 2!
        self.assertEqual(resp.context["total_active_tasks"], 1)
        self.assertIn("1 in DB &amp; active on worker", resp.content.decode("utf-8"))
        self.assertContains(resp, "celery@node-01")
        self.assertContains(resp, task_uuid)

