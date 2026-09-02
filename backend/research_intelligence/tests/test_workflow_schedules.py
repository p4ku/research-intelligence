"""
Comprehensive test suite for Workflow Scheduling, Periodic Dispatching,
Concurrency Controls, Signals/Observability, Admin UI, and REST API.

Organized into modular test cases by architectural responsibility:
1. WorkflowScheduleRecurrenceTests (cron generation, descriptions, validation, ZoneInfo DST)
2. WorkflowScheduleDispatcherAndConcurrencyTests (beat periodic task, overlap guard, jitter)
3. WorkflowScheduleExecutionAndTransactionsTests (triggering, atomic blocks, on_commit, history)
4. WorkflowScheduleObservabilityAndSignalsTests (signals observer, early halt, failure auto-pause)
5. WorkflowScheduleAdminAndAPITests (Admin changelist/actions, REST API endpoints, serializers)
"""

import datetime
from zoneinfo import ZoneInfo

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.serializers.schedules import WorkflowScheduleSerializer
from research_intelligence.admin import WorkflowScheduleAdmin
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    WorkflowSchedule,
    PipelineRun,
    ResearchAgentProcess,
)
from research_intelligence.tasks.auxiliary.schedule_dispatcher import (
    dispatch_due_workflow_schedules,
    dispatch_scheduled_workflow_runs_task,
)
from research_intelligence.tasks.orchestrator.runner import ResearchAgentRunner

User = get_user_model()


class WorkflowScheduleBaseTestCase(TestCase):
    """
    Shared base fixture for workflow schedule tests.
    Provides standard test superuser, workspace, member, and factory helpers.
    """

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="scheduler_admin",
            email="scheduler@example.com",
            password="Password123!"
        )
        self.workspace = Workspace.objects.create(
            name="Quantum Computing Intelligence",
            abstract_acceptance_criteria="Quantum qubit error correction",
        )
        self.member = WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.force_login(self.user)

    def create_schedule(self, **kwargs) -> WorkflowSchedule:
        """Helper factory with sensible defaults for creating schedules in tests."""
        defaults = {
            "workspace": self.workspace,
            "name": "Test Workflow Schedule",
            "frequency": "daily",
            "time_of_day": datetime.time(2, 0),
            "timezone_name": "UTC",
            "is_active": True,
            "created_by": self.user,
        }
        defaults.update(kwargs)
        return WorkflowSchedule.objects.create(**defaults)


# ==============================================================================
# 1. RECURRENCE, CRON PATTERNS & DST CALCULATIONS
# ==============================================================================

class WorkflowScheduleRecurrenceTests(WorkflowScheduleBaseTestCase):
    """Tests for cron expression auto-generation, human descriptions, and ZoneInfo DST handling."""

    def test_daily_schedule_cron_and_description(self):
        schedule = self.create_schedule(
            name="Daily Afternoon Ingestion",
            frequency="daily",
            time_of_day=datetime.time(15, 0),
            timezone_name="UTC"
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 15 * * *")
        self.assertEqual(schedule.schedule_description, "Every day at 15:00 UTC")
        self.assertIsNotNone(schedule.next_run_at)
        self.assertGreater(schedule.next_run_at, timezone.now())

    def test_weekdays_schedule_cron_and_description(self):
        schedule = self.create_schedule(
            name="Weekdays 3pm Run",
            frequency="weekdays",
            time_of_day=datetime.time(15, 0),
            timezone_name="UTC"
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 15 * * 1-5")
        self.assertEqual(schedule.schedule_description, "Every weekday (Mon - Fri) at 15:00 UTC")
        self.assertIsNotNone(schedule.next_run_at)
        self.assertGreater(schedule.next_run_at, timezone.now())

    def test_weekly_schedule_cron_and_description(self):
        # 0=Mon, 2=Wed, 4=Fri in Python
        schedule = self.create_schedule(
            name="Mon Wed Fri 2am Review",
            frequency="weekly",
            time_of_day=datetime.time(2, 0),
            days_of_week=[0, 2, 4],
            timezone_name="UTC"
        )
        # Croniter maps Mon=1, Wed=3, Fri=5
        self.assertEqual(schedule.get_effective_cron_expression(), "0 2 * * 1,3,5")
        self.assertIn("Weekly on Mon, Wed, Fri at 02:00 UTC", schedule.schedule_description)

    def test_monthly_schedule_cron_and_description(self):
        schedule = self.create_schedule(
            name="Monthly Executive Sync",
            frequency="monthly",
            day_of_month=15,
            time_of_day=datetime.time(2, 0),
            timezone_name="UTC"
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 2 15 * *")
        self.assertEqual(schedule.schedule_description, "Monthly on the 15th at 02:00 UTC")

    def test_interval_hours_schedule_cron_and_description(self):
        schedule = self.create_schedule(
            name="Interval 6h Run",
            frequency="interval_hours",
            interval_hours=6,
            time_of_day=datetime.time(0, 0),
            timezone_name="UTC"
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 */6 * * *")
        self.assertEqual(schedule.schedule_description, "Every 6 hours")

    def test_custom_cron_expression_and_validation(self):
        schedule = self.create_schedule(
            name="Custom 4am Saturday",
            frequency="custom_cron",
            cron_expression="0 4 * * 6",
            timezone_name="UTC"
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 4 * * 6")
        self.assertEqual(schedule.schedule_description, "Cron: 0 4 * * 6 UTC")

        # Invalid cron should raise ValidationError on clean
        invalid_schedule = WorkflowSchedule(
            workspace=self.workspace,
            name="Invalid Cron",
            frequency="custom_cron",
            cron_expression="invalid-cron-string",
            timezone_name="UTC"
        )
        with self.assertRaises(ValidationError):
            invalid_schedule.clean()

    def test_one_off_schedule_creation_and_auto_deactivation(self):
        future_dt = timezone.now() + datetime.timedelta(hours=5)
        schedule = self.create_schedule(
            name="One-Off Late Night Run",
            frequency="one_off",
            one_off_datetime=future_dt
        )
        self.assertEqual(schedule.next_run_at, future_dt)
        self.assertIn("One-off run at", schedule.schedule_description)

        # Trigger run
        agent = schedule.trigger_run(triggered_by_user=self.user)
        self.assertIsNotNone(agent)

        # Verify auto-deactivation after run
        schedule.refresh_from_db()
        self.assertEqual(schedule.total_runs_count, 1)
        self.assertFalse(schedule.is_active)
        self.assertIsNone(schedule.next_run_at)
        self.assertIn("One-off (Executed at", schedule.schedule_description)

    def test_zoneinfo_dst_aware_next_run_calculation(self):
        """
        Tests that compute_next_run correctly handles Daylight Saving Time (DST) with ZoneInfo.
        """
        schedule = self.create_schedule(
            name="Berlin Schedule",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            timezone_name="Europe/Berlin"
        )

        # In Winter (CET = UTC+1): 02:00 Berlin is 01:00 UTC
        winter_base = datetime.datetime(2026, 1, 15, 12, 0, tzinfo=datetime.timezone.utc)
        next_winter = schedule.compute_next_run(base_time=winter_base)
        self.assertEqual(next_winter.hour, 1)  # 01:00 UTC = 02:00 CET

        # In Summer (CEST = UTC+2): 02:00 Berlin is 00:00 UTC
        summer_base = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)
        next_summer = schedule.compute_next_run(base_time=summer_base)
        self.assertEqual(next_summer.hour, 0)  # 00:00 UTC = 02:00 CEST

    def test_invalid_timezone_raises_validation_error(self):
        schedule = WorkflowSchedule(
            workspace=self.workspace,
            name="Invalid TZ Schedule",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            timezone_name="Invalid/Fake_Zone"
        )
        with self.assertRaises(ValidationError):
            schedule.clean()


# ==============================================================================
# 2. DISPATCHER & CONCURRENCY / OVERLAP CONTROLS
# ==============================================================================

class WorkflowScheduleDispatcherAndConcurrencyTests(WorkflowScheduleBaseTestCase):
    """Tests for dispatcher periodic execution, race condition locks, and overlap prevention."""

    def test_dispatcher_finds_and_triggers_due_schedules(self):
        past_time = timezone.now() - datetime.timedelta(minutes=10)
        due_schedule = self.create_schedule(name="Due Schedule")
        WorkflowSchedule.objects.filter(id=due_schedule.id).update(next_run_at=past_time)

        inactive_schedule = self.create_schedule(name="Paused Schedule", is_active=False)
        WorkflowSchedule.objects.filter(id=inactive_schedule.id).update(next_run_at=past_time)

        res = dispatch_due_workflow_schedules()
        self.assertEqual(res["dispatched_count"], 1)
        self.assertEqual(res["dispatched"][0]["schedule_id"], str(due_schedule.id))

        due_schedule.refresh_from_db()
        self.assertEqual(due_schedule.total_runs_count, 1)
        self.assertGreater(due_schedule.next_run_at, timezone.now())

        inactive_schedule.refresh_from_db()
        self.assertEqual(inactive_schedule.total_runs_count, 0)

    def test_prevent_overlap_skips_when_previous_run_active(self):
        """
        Tests that prevent_overlap=True prevents triggering a new run when previous run is still active.
        """
        schedule = self.create_schedule(
            name="Overlap Test Schedule",
            prevent_overlap=True
        )
        agent1 = schedule.trigger_run(triggered_by_user=self.user)
        self.assertIsNotNone(agent1)
        self.assertEqual(schedule.total_runs_count, 1)

        # Attempt to trigger again while first run is in 'running' status
        agent2 = schedule.trigger_run(triggered_by_user=self.user, force=False)
        self.assertIsNone(agent2)
        self.assertEqual(schedule.total_runs_count, 1)

        # Force run overrides overlap guard
        agent3 = schedule.trigger_run(triggered_by_user=self.user, force=True)
        self.assertIsNotNone(agent3)
        self.assertEqual(schedule.total_runs_count, 2)

    def test_dispatcher_skips_overlap_and_advances_next_run(self):
        """
        Tests that dispatch_due_workflow_schedules skips overlapping active runs and advances next_run_at.
        """
        past_time = timezone.now() - datetime.timedelta(minutes=5)
        schedule = self.create_schedule(
            name="Dispatcher Overlap Test",
            prevent_overlap=True
        )
        p_run = PipelineRun.objects.create(
            workspace=self.workspace,
            schedule=schedule,
            status='running'
        )
        schedule.last_pipeline_run = p_run
        schedule.last_status = 'running'
        schedule.next_run_at = past_time
        schedule.save()

        summary = dispatch_due_workflow_schedules(dry_run=False)
        self.assertEqual(summary["dispatched_count"], 0)
        self.assertEqual(summary["skipped_overlap_count"], 1)

        schedule.refresh_from_db()
        # next_run_at should be advanced into the future
        self.assertGreater(schedule.next_run_at, timezone.now())

    def test_celery_periodic_task_wrapper(self):
        """Tests that dispatch_scheduled_workflow_runs_task runs without exceptions."""
        result = dispatch_scheduled_workflow_runs_task()
        self.assertIn("dispatched_count", result)
        self.assertIn("skipped_overlap_count", result)
        self.assertIn("errors_count", result)


# ==============================================================================
# 3. EXECUTION, TRANSACTIONS & RUN HISTORY
# ==============================================================================

class WorkflowScheduleExecutionAndTransactionsTests(WorkflowScheduleBaseTestCase):
    """Tests for trigger_run behavior, atomic blocks, on_commit resilience, and history linkage."""

    def test_trigger_run_creates_pipeline_and_agent(self):
        schedule = self.create_schedule(
            name="Test Trigger Run",
            reprocess_existing=True
        )
        agent = schedule.trigger_run(triggered_by_user=self.user)

        self.assertIsNotNone(agent)
        self.assertEqual(agent.workspace, self.workspace)
        self.assertEqual(agent.name, "Scheduled Run - Test Trigger Run")
        self.assertTrue(agent.configuration_override.get("reprocess_existing"))

        schedule.refresh_from_db()
        self.assertEqual(schedule.total_runs_count, 1)
        self.assertIsNotNone(schedule.last_run_at)
        self.assertIsNotNone(schedule.last_pipeline_run)
        self.assertEqual(schedule.last_status, "running")
        self.assertGreater(schedule.next_run_at, timezone.now())

    def test_trigger_run_atomic_transaction_resilience_and_on_commit(self):
        """
        Regression test: Verifies that trigger_run() executed inside an active transaction.atomic()
        does not close the connection and executes on_commit callbacks cleanly.
        """
        schedule = self.create_schedule(name="Transaction Resilience Schedule")

        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                agent = schedule.trigger_run(triggered_by_user=self.user)
                self.assertIsNotNone(agent)
                self.assertTrue(connection.is_usable())
                agent_count = ResearchAgentProcess.objects.filter(id=agent.id).count()
                self.assertEqual(agent_count, 1)

        schedule.refresh_from_db()
        self.assertEqual(schedule.total_runs_count, 1)
        self.assertEqual(schedule.last_status, "running")
        self.assertTrue(connection.is_usable())

    def test_runner_tick_inside_active_atomic_transaction_preserves_connection(self):
        """
        Regression test: Directly calling ResearchAgentRunner.tick inside an active transaction.atomic()
        must NOT close the database connection.
        """
        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status='running',
            current_stage='search'
        )
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            name="Atomic Tick Test Agent",
            status='running',
            current_step='initialized'
        )

        with transaction.atomic():
            self.assertTrue(connection.in_atomic_block)
            tick_result = ResearchAgentRunner.tick(str(agent.id))
            self.assertTrue(tick_result.get("success", False))
            self.assertTrue(connection.is_usable())
            agent.refresh_from_db()
            self.assertIsNotNone(agent.status)

    def test_pipelinerun_schedule_link_and_history(self):
        """
        Tests that PipelineRun is explicitly linked to WorkflowSchedule and history properties work.
        """
        schedule = self.create_schedule(name="History Link Schedule")
        agent = schedule.trigger_run(triggered_by_user=self.user, force=True)
        run = schedule.last_pipeline_run

        self.assertEqual(run.schedule, schedule)
        self.assertEqual(schedule.pipeline_runs.count(), 1)
        self.assertIn(run, schedule.runs_history)

        # Mark run as completed
        run.status = 'completed'
        run.save()

        schedule.refresh_from_db()
        self.assertEqual(schedule.successful_runs_count, 1)
        self.assertEqual(schedule.failed_runs_count, 0)
        self.assertEqual(schedule.success_rate_percent, 100.0)


# ==============================================================================
# 4. OBSERVABILITY, SIGNALS & FAILURE GUARDRAILS
# ==============================================================================

class WorkflowScheduleObservabilityAndSignalsTests(WorkflowScheduleBaseTestCase):
    """Tests for Django signals observer, early halt detection, and consecutive failure auto-pause."""

    def test_observer_updates_schedule_status_on_pipeline_run_completion(self):
        schedule = self.create_schedule(name="Observer Test Schedule")
        agent = schedule.trigger_run(triggered_by_user=self.user)
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, "running")

        # Simulate PipelineRun finishing (completed)
        pipeline_run = schedule.last_pipeline_run
        pipeline_run.status = "completed"
        pipeline_run.save(update_fields=["status"])

        # Observer should have automatically updated schedule.last_status
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, "completed")
        self.assertEqual(schedule.current_execution_status, "completed")

    def test_observer_updates_schedule_status_on_agent_process_update(self):
        schedule = self.create_schedule(name="Agent Observer Schedule")
        agent = schedule.trigger_run(triggered_by_user=self.user)
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, "running")

        # Simulate AgentProcess failing
        agent.status = "failed"
        agent.save(update_fields=["status"])

        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, "failed")
        self.assertEqual(schedule.current_execution_status, "failed")

    def test_schedule_observable_early_halt_and_admin_display(self):
        """
        Tests that when an agent process halts early (e.g. search stage with 0 new papers due to duplicates),
        is_last_execution_halted_early is True and admin last_run_display renders the HALTED badge.
        """
        schedule = self.create_schedule(name="Halt Schedule")
        agent = schedule.trigger_run(triggered_by_user=self.user)
        p_run = schedule.last_pipeline_run

        # Mark pipeline run and agent as halted early at search
        p_run.status = "completed"
        p_run.save(update_fields=["status"])

        agent.status = "completed"
        agent.stopped_at_step = "search"
        agent.stop_reason = "⚠️ Search: 0 papers were found matching criteria (0 new papers ingested - duplicates)"
        agent.save(update_fields=["status", "stopped_at_step", "stop_reason"])

        schedule.refresh_from_db()
        is_halted, halt_step = schedule.is_last_execution_halted_early
        self.assertTrue(is_halted)
        self.assertEqual(halt_step, "search")

        # Test admin last_run_display renders HALTED badge
        admin_site = AdminSite()
        model_admin = WorkflowScheduleAdmin(WorkflowSchedule, admin_site)
        display_html = model_admin.last_run_display(schedule)

        self.assertIn("HALTED (SEARCH)", display_html)
        self.assertNotIn("RUNNING", display_html)

    def test_consecutive_failures_tracking_and_auto_pause(self):
        """
        Tests that consecutive execution failures are tracked and schedule auto-pauses when reaching threshold.
        """
        schedule = self.create_schedule(
            name="Failure Tracking Schedule",
            max_consecutive_failures=2
        )
        agent1 = schedule.trigger_run(triggered_by_user=self.user, force=True)
        run1 = schedule.last_pipeline_run
        run1.status = 'failed'
        run1.save()

        schedule.refresh_from_db()
        self.assertEqual(schedule.consecutive_failures_count, 1)
        self.assertTrue(schedule.is_active)

        # Second failure triggers auto-pause
        agent2 = schedule.trigger_run(triggered_by_user=self.user, force=True)
        run2 = schedule.last_pipeline_run
        run2.status = 'failed'
        run2.save()

        schedule.refresh_from_db()
        self.assertEqual(schedule.consecutive_failures_count, 2)
        self.assertFalse(schedule.is_active)
        self.assertIsNone(schedule.next_run_at)


# ==============================================================================
# 5. ADMIN UI & REST API ENDPOINTS
# ==============================================================================

class WorkflowScheduleAdminAndAPITests(WorkflowScheduleBaseTestCase):
    """Tests for Django Admin changelist/actions and REST API endpoints."""

    def test_admin_schedule_changelist_and_trigger_view(self):
        schedule = self.create_schedule(
            name="Admin Test Schedule",
            frequency="weekdays",
            time_of_day=datetime.time(15, 0)
        )

        # 1. Test changelist view renders and contains KPI banner stats
        changelist_url = reverse('admin:research_intelligence_workflowschedule_changelist')
        resp = self.client.get(changelist_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Admin Test Schedule")
        self.assertContains(resp, "Every weekday (Mon - Fri) at 15:00 UTC")
        self.assertContains(resp, "🚀 Run Now")
        self.assertContains(resp, "Active Schedules")
        self.assertContains(resp, "Next 24h Queue")
        self.assertContains(resp, "Total Runs Triggered")

        # 2. Test direct toggle view
        toggle_url = reverse('admin:research_intelligence_workflowschedule_toggle', args=[schedule.id])
        resp_toggle = self.client.get(toggle_url, follow=True)
        self.assertEqual(resp_toggle.status_code, 200)
        self.assertContains(resp_toggle, "Paused schedule")
        schedule.refresh_from_db()
        self.assertFalse(schedule.is_active)

        # Resume toggle
        resp_resume = self.client.get(toggle_url, follow=True)
        self.assertEqual(resp_resume.status_code, 200)
        self.assertContains(resp_resume, "Resumed schedule")
        schedule.refresh_from_db()
        self.assertTrue(schedule.is_active)

        # 3. Test direct Run Now view
        trigger_url = reverse('admin:research_intelligence_workflowschedule_trigger', args=[schedule.id])
        resp_trigger = self.client.get(trigger_url, follow=True)
        self.assertEqual(resp_trigger.status_code, 200)
        self.assertContains(resp_trigger, "Successfully triggered scheduled workflow")

        schedule.refresh_from_db()
        self.assertEqual(schedule.total_runs_count, 1)

    def test_rest_api_schedules_crud_and_trigger(self):
        # 1. Create schedule via API using reverse route
        list_url = reverse('schedule-list')
        create_resp = self.client.post(list_url, {
            "workspace": str(self.workspace.id),
            "name": "API Created Schedule",
            "frequency": "weekdays",
            "time_of_day": "15:00:00",
            "timezone_name": "UTC",
            "is_active": True,
            "reprocess_existing": False
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        schedule_id = create_resp.data["id"]
        self.assertEqual(create_resp.data["schedule_description"], "Every weekday (Mon - Fri) at 15:00 UTC")
        self.assertTrue(create_resp.data["prevent_overlap"])

        # 2. Trigger schedule via API
        trigger_url = reverse('schedule-trigger', args=[schedule_id])
        trigger_resp = self.client.post(trigger_url)
        self.assertEqual(trigger_resp.status_code, status.HTTP_200_OK)
        self.assertIn("Successfully triggered", trigger_resp.data["message"])

        # 3. Toggle pause/resume via API
        toggle_url = reverse('schedule-toggle', args=[schedule_id])
        toggle_resp = self.client.post(toggle_url)
        self.assertEqual(toggle_resp.status_code, status.HTTP_200_OK)
        self.assertFalse(toggle_resp.data["is_active"])
        self.assertIsNone(toggle_resp.data["next_run_at"])

    def test_serializer_observable_last_status(self):
        """
        Tests that WorkflowScheduleSerializer exposes current_execution_status as last_status.
        """
        schedule = self.create_schedule(name="Serializer Test Schedule")
        agent = schedule.trigger_run(triggered_by_user=self.user)

        # Force DB last_status to stale 'running', but pipeline run to 'completed'
        p_run = schedule.last_pipeline_run
        PipelineRun.objects.filter(id=p_run.id).update(status="completed")

        schedule.refresh_from_db()
        serializer = WorkflowScheduleSerializer(schedule)
        self.assertEqual(serializer.data["last_status"], "completed")
