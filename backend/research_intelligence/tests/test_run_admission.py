"""
Run admission: at most MAX_CONCURRENT_RUNS_PER_WORKSPACE runs in flight per
workspace, and no second in-flight run for the same search window.

These tests run on SQLite, where select_for_update is a no-op: they prove the
counting and the HTTP mapping, not the race. The race is proven against a
real Postgres by `manage.py check_run_admission_race` (and end to end by
tests_e2e/scenarios/run_admission_guard.py).
"""
import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from research_intelligence.models import (
    PipelineRun,
    ResearchAgentProcess,
    WorkflowSchedule,
    Workspace,
    WorkspaceMember,
)
from research_intelligence.services.run_admission import (
    CODE_DUPLICATE_RUN,
    CODE_RUN_LIMIT_REACHED,
    RunAdmissionRefused,
    admit_run,
    search_window,
)
from research_intelligence.tasks.auxiliary.schedule_dispatcher import dispatch_due_workflow_schedules
from mcp_server.tools.agents.processes import start_research_agent_logic
from mcp_server.tools.pipeline_runs.triggers import start_pipeline_run_logic, trigger_search_job_logic
import json

User = get_user_model()

TICK = 'research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick'
AGENT_TICK = 'mcp_server.tools.agents.processes.tick_agent_process'


class SearchWindowTests(TestCase):
    def test_dates_are_cut_to_the_day_and_beat_lookback(self):
        self.assertEqual(
            search_window({"start_date": "2026-08-01T00:00:00Z", "end_date": "2026-08-15", "n_last_days": 7}),
            ("2026-08-01", "2026-08-15", None),
        )

    def test_lookback_counts_only_without_dates(self):
        self.assertEqual(search_window({"n_last_days": 7}), (None, None, 7))
        self.assertEqual(search_window({"n_last_days": "14", "start_date": None}), (None, None, 14))
        self.assertEqual(search_window({"start_date": "2026-08-01", "n_last_days": 7}), ("2026-08-01", None, None))

    def test_empty_and_garbage(self):
        self.assertEqual(search_window(None), (None, None, None))
        self.assertEqual(search_window({}), (None, None, None))
        self.assertEqual(search_window({"n_last_days": "soon"}), (None, None, None))


class AdmissionBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admit_admin', password='pw')
        self.workspace = Workspace.objects.create(name='Workspace Alpha')
        self.other = Workspace.objects.create(name='Workspace Beta')
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role='admin')
        WorkspaceMember.objects.create(workspace=self.other, user=self.user, role='admin')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def in_flight(self, workspace=None, n=1, status='running', **cfg):
        runs = []
        for i in range(n):
            override = {"n_last_days": 30 + i} if not cfg else dict(cfg)
            runs.append(PipelineRun.objects.create(
                workspace=workspace or self.workspace,
                status=status,
                configuration_override=override,
            ))
        return runs

    def start(self, **payload):
        body = {"workspace_id": str(self.workspace.id), "autonomous": True, **payload}
        return self.client.post('/api/pipeline-runs/start/', body, format='json')


class AdmitRunOutsideTransactionTests(TransactionTestCase):
    """TestCase wraps every test in a transaction, so this one needs the bare kind."""

    def test_requires_an_atomic_block(self):
        workspace = Workspace.objects.create(name='Bare')
        with self.assertRaises(RuntimeError):
            admit_run(workspace.id, {"n_last_days": 7})


class AdmitRunHelperTests(AdmissionBase):
    def test_returns_the_workspace_when_admitted(self):
        with transaction.atomic():
            ws = admit_run(self.workspace.id, {"n_last_days": 7})
        self.assertEqual(ws.id, self.workspace.id)

    @override_settings(MAX_CONCURRENT_RUNS_PER_WORKSPACE=2)
    def test_cap_reads_settings_and_counts_pending_running_paused(self):
        self.in_flight(status='pending', n_last_days=1)
        self.in_flight(status='paused', n_last_days=2)
        with self.assertRaises(RunAdmissionRefused) as ctx:
            with transaction.atomic():
                admit_run(self.workspace.id, {"n_last_days": 7})
        self.assertEqual(ctx.exception.code, CODE_RUN_LIMIT_REACHED)
        self.assertEqual(ctx.exception.payload["in_flight"], 2)
        self.assertEqual(ctx.exception.payload["limit"], 2)
        self.assertEqual(ctx.exception.payload["workspace_name"], 'Workspace Alpha')

    def test_finished_runs_do_not_count(self):
        for st in ('completed', 'failed', 'aborted'):
            self.in_flight(n=5, status=st)
        with transaction.atomic():
            admit_run(self.workspace.id, {"n_last_days": 7})

    def test_other_workspace_does_not_count(self):
        self.in_flight(workspace=self.other, n=5)
        with transaction.atomic():
            admit_run(self.workspace.id, {"n_last_days": 7})

    def test_duplicate_window_is_refused_with_the_conflicting_run(self):
        (existing,) = self.in_flight(start_date="2026-08-01", end_date="2026-08-15")
        with self.assertRaises(RunAdmissionRefused) as ctx:
            with transaction.atomic():
                admit_run(self.workspace.id, {"start_date": "2026-08-01T00:00:00Z", "end_date": "2026-08-15", "n_last_days": 7})
        self.assertEqual(ctx.exception.code, CODE_DUPLICATE_RUN)
        self.assertEqual(ctx.exception.payload["conflicting_run_id"], str(existing.id))
        self.assertEqual(ctx.exception.as_error_json()["status"], "error")

    def test_unknown_window_never_duplicates(self):
        self.in_flight(n=1, status='running')
        PipelineRun.objects.filter(workspace=self.workspace).update(configuration_override={})
        with transaction.atomic():
            admit_run(self.workspace.id, {})

    def test_check_window_false_skips_the_duplicate_rule(self):
        self.in_flight(n_last_days=7)
        with transaction.atomic():
            admit_run(self.workspace.id, {"n_last_days": 7}, check_window=False)


class StartEndpointAdmissionTests(AdmissionBase):
    @patch(TICK, return_value={"success": True})
    def test_sixth_start_is_409_run_limit_reached(self, _tick):
        self.in_flight(n=5)
        res = self.start(start_date="2026-08-01", end_date="2026-08-15")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], CODE_RUN_LIMIT_REACHED)
        self.assertEqual(res.data["in_flight"], 5)
        self.assertEqual(res.data["limit"], 5)
        self.assertEqual(res.data["error"], "5 of 5 runs in progress for Workspace Alpha. Wait for one to finish.")
        self.assertEqual(PipelineRun.objects.filter(workspace=self.workspace).count(), 5)

    @patch(TICK, return_value={"success": True})
    def test_fifth_start_is_admitted(self, _tick):
        self.in_flight(n=4)
        res = self.start(start_date="2026-08-01", end_date="2026-08-15")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

    @patch(TICK, return_value={"success": True})
    def test_same_window_is_409_duplicate_run(self, _tick):
        (existing,) = self.in_flight(start_date="2026-08-01", end_date="2026-08-15")
        res = self.start(start_date="2026-08-01", end_date="2026-08-15")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], CODE_DUPLICATE_RUN)
        self.assertEqual(res.data["conflicting_run_id"], str(existing.id))

    @patch(TICK, return_value={"success": True})
    def test_different_end_date_is_admitted(self, _tick):
        self.in_flight(start_date="2026-08-01", end_date="2026-08-15")
        res = self.start(start_date="2026-08-01", end_date="2026-08-16")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

    @patch(TICK, return_value={"success": True})
    def test_two_bare_starts_share_the_default_window(self, _tick):
        first = self.start()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        second = self.start()
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], CODE_DUPLICATE_RUN)
        third = self.start(n_last_days=14)
        self.assertEqual(third.status_code, status.HTTP_201_CREATED, third.data)

    @patch(TICK, return_value={"success": True})
    def test_workspace_run_pipeline_endpoint_is_409(self, _tick):
        self.in_flight(n=5)
        res = self.client.post(f'/api/workspaces/{self.workspace.id}/run-pipeline/', {"n_last_days": 3}, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], CODE_RUN_LIMIT_REACHED)

    @patch(AGENT_TICK, return_value={"success": True})
    def test_agents_endpoint_is_409(self, _tick):
        self.in_flight(n=5)
        res = self.client.post('/api/agents/', {"workspace_id": str(self.workspace.id), "n_last_days": 3}, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], CODE_RUN_LIMIT_REACHED)
        self.assertEqual(ResearchAgentProcess.objects.filter(workspace=self.workspace).count(), 5)

    def test_bare_create_is_409(self):
        self.in_flight(n=5)
        res = self.client.post('/api/pipeline-runs/', {"workspace_id": str(self.workspace.id), "n_last_days": 3}, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], CODE_RUN_LIMIT_REACHED)

    def test_bare_create_duplicate_window_is_409(self):
        self.in_flight(start_date="2026-08-01", end_date="2026-08-15")
        res = self.client.post(
            '/api/pipeline-runs/',
            {"workspace_id": str(self.workspace.id), "start_date": "2026-08-01", "end_date": "2026-08-15"},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], CODE_DUPLICATE_RUN)

    def test_role_refusal_is_still_403(self):
        outsider = User.objects.create_user(username='outsider', password='pw')
        self.client.force_authenticate(user=outsider)
        res = self.start()
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class MCPStartLogicAdmissionTests(AdmissionBase):
    @patch(TICK, return_value={"success": True})
    def test_start_pipeline_run_logic_returns_the_code(self, _tick):
        self.in_flight(n=5)
        res = json.loads(start_pipeline_run_logic(self.user, str(self.workspace.id)))
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["code"], CODE_RUN_LIMIT_REACHED)

    @patch(AGENT_TICK, return_value={"success": True})
    def test_start_research_agent_logic_returns_the_code(self, _tick):
        self.in_flight(n_last_days=7)
        res = json.loads(start_research_agent_logic(self.user, str(self.workspace.id)))
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["code"], CODE_DUPLICATE_RUN)

    def test_trigger_search_job_logic_new_run_is_admitted(self):
        from research_intelligence.models import Scraper
        Scraper.objects.create(workspace=self.workspace, provider='arxiv', search_query='cat:cs.AI', is_active=True)
        self.in_flight(n=5)
        res = json.loads(trigger_search_job_logic(self.user, str(self.workspace.id)))
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["code"], CODE_RUN_LIMIT_REACHED)


@override_settings(FEATURES={"SCHEDULING": True, "EMAIL_NOTIFICATIONS": False})
class ScheduleAdmissionTests(AdmissionBase):
    def make_schedule(self, **kwargs):
        defaults = dict(
            workspace=self.workspace,
            name="Nightly",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            created_by=self.user,
            is_active=True,
            prevent_overlap=False,
        )
        defaults.update(kwargs)
        return WorkflowSchedule.objects.create(**defaults)

    def test_trigger_run_raises_at_the_cap_even_when_forced(self):
        schedule = self.make_schedule()
        self.in_flight(n=5)
        with self.assertRaises(RunAdmissionRefused) as ctx:
            schedule.trigger_run(triggered_by_user=self.user, force=True)
        self.assertEqual(ctx.exception.code, CODE_RUN_LIMIT_REACHED)
        schedule.refresh_from_db()
        self.assertEqual(schedule.total_runs_count, 0)
        self.assertEqual(PipelineRun.objects.filter(workspace=self.workspace).count(), 5)

    def test_trigger_run_ignores_the_duplicate_window_rule(self):
        schedule = self.make_schedule(n_last_days=7)
        self.in_flight(n_last_days=7)
        with patch('research_intelligence.tasks.orchestrator.agent_engine.run_agent_process_tick'):
            self.assertIsNotNone(schedule.trigger_run(triggered_by_user=self.user))

    def test_dispatcher_advances_next_run_at_and_reports_the_refusal(self):
        schedule = self.make_schedule()
        past = timezone.now() - datetime.timedelta(minutes=5)
        WorkflowSchedule.objects.filter(id=schedule.id).update(next_run_at=past)
        self.in_flight(n=5)
        summary = dispatch_due_workflow_schedules()
        self.assertEqual(summary["dispatched_count"], 0)
        self.assertEqual(summary["skipped_overlap_count"], 1)
        self.assertEqual(summary["skipped_overlap"][0]["reason"], CODE_RUN_LIMIT_REACHED)
        schedule.refresh_from_db()
        self.assertGreater(schedule.next_run_at, timezone.now())
        self.assertEqual(schedule.total_runs_count, 0)

    def test_trigger_endpoint_is_409_instead_of_500(self):
        schedule = self.make_schedule()
        self.in_flight(n=5)
        res = self.client.post(f'/api/schedules/{schedule.id}/trigger/')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], CODE_RUN_LIMIT_REACHED)

    def test_trigger_endpoint_overlap_is_409(self):
        schedule = self.make_schedule(prevent_overlap=True)
        run = PipelineRun.objects.create(workspace=self.workspace, schedule=schedule, status='running')
        schedule.last_pipeline_run = run
        schedule.save()
        res = self.client.post(f'/api/schedules/{schedule.id}/trigger/')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], "schedule_overlap")
