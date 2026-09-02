from django.db import connection, transaction
from research_intelligence.tasks.orchestrator.runner import ResearchAgentRunner
import datetime
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

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

User = get_user_model()


class WorkflowScheduleModelAndDispatcherTests(TestCase):
    """
    Test suite for WorkflowSchedule model, cron expressions, next_run calculations,
    dispatcher periodic tasks, admin integration, and REST API.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="scheduler_admin",
            email="scheduler@example.com",
            password="Password123!"
        )
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        self.workspace = Workspace.objects.create(
            name="Quantum Computing Intelligence",
            abstract_acceptance_criteria="Quantum qubit error correction",
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.force_login(self.user)

    def test_daily_schedule_cron_and_description(self):
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Daily Afternoon Ingestion",
            frequency="daily",
            time_of_day=datetime.time(15, 0),
            timezone_name="UTC",
            is_active=True
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 15 * * *")
        self.assertEqual(schedule.schedule_description, "Every day at 15:00 UTC")
        self.assertIsNotNone(schedule.next_run_at)
        self.assertGreater(schedule.next_run_at, timezone.now())

    def test_weekdays_schedule_cron_and_description(self):
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Weekdays 3pm Run",
            frequency="weekdays",
            time_of_day=datetime.time(15, 0),
            timezone_name="UTC",
            is_active=True
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 15 * * 1-5")
        self.assertEqual(schedule.schedule_description, "Every weekday (Mon - Fri) at 15:00 UTC")
        self.assertIsNotNone(schedule.next_run_at)
        self.assertGreater(schedule.next_run_at, timezone.now())

    def test_weekly_schedule_cron_and_description(self):
        # 0=Mon, 2=Wed, 4=Fri
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Mon Wed Fri 2am Review",
            frequency="weekly",
            time_of_day=datetime.time(2, 0),
            days_of_week=[0, 2, 4],
            timezone_name="UTC",
            is_active=True
        )
        # Croniter maps Mon=1, Wed=3, Fri=5
        self.assertEqual(schedule.get_effective_cron_expression(), "0 2 * * 1,3,5")
        self.assertIn("Weekly on Mon, Wed, Fri at 02:00 UTC", schedule.schedule_description)

    def test_monthly_schedule_cron_and_description(self):
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Monthly Executive Sync",
            frequency="monthly",
            day_of_month=15,
            time_of_day=datetime.time(2, 0),
            timezone_name="UTC",
            is_active=True
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 2 15 * *")
        self.assertEqual(schedule.schedule_description, "Monthly on the 15th at 02:00 UTC")

    def test_custom_cron_expression(self):
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Custom 4am Saturday",
            frequency="custom_cron",
            cron_expression="0 4 * * 6",
            timezone_name="UTC",
            is_active=True
        )
        self.assertEqual(schedule.get_effective_cron_expression(), "0 4 * * 6")
        self.assertEqual(schedule.schedule_description, "Cron: 0 4 * * 6 UTC")

    def test_one_off_schedule_creation_and_auto_deactivation(self):
        future_dt = timezone.now() + datetime.timedelta(hours=5)
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="One-Off Late Night Run",
            frequency="one_off",
            one_off_datetime=future_dt,
            is_active=True
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

    def test_trigger_run_creates_pipeline_and_agent(self):
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Test Trigger Run",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            reprocess_existing=True,
            created_by=self.user,
            is_active=True
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

    def test_dispatcher_finds_and_triggers_due_schedules(self):
        past_time = timezone.now() - datetime.timedelta(minutes=10)
        due_schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Due Schedule",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            is_active=True
        )
        # Force next_run_at to past
        WorkflowSchedule.objects.filter(id=due_schedule.id).update(next_run_at=past_time)

        # Inactive schedule should not run even if past
        inactive_schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Paused Schedule",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            is_active=False
        )
        WorkflowSchedule.objects.filter(id=inactive_schedule.id).update(next_run_at=past_time)

        res = dispatch_due_workflow_schedules()
        self.assertEqual(res["dispatched_count"], 1)
        self.assertEqual(res["dispatched"][0]["schedule_id"], str(due_schedule.id))

        due_schedule.refresh_from_db()
        self.assertEqual(due_schedule.total_runs_count, 1)
        self.assertGreater(due_schedule.next_run_at, timezone.now())

        inactive_schedule.refresh_from_db()
        self.assertEqual(inactive_schedule.total_runs_count, 0)

    def test_admin_schedule_changelist_and_trigger_view(self):
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Admin Test Schedule",
            frequency="weekdays",
            time_of_day=datetime.time(15, 0),
            is_active=True
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
        # 1. Create schedule via API
        create_resp = self.client.post('/api/schedules/', {
            "workspace": str(self.workspace.id),
            "name": "API Created Schedule",
            "frequency": "weekdays",
            "time_of_day": "15:00:00",
            "timezone_name": "UTC",
            "is_active": True,
            "reprocess_existing": False
        }, format='json')
        self.assertEqual(create_resp.status_code, 201)
        schedule_id = create_resp.data["id"]
        self.assertEqual(create_resp.data["schedule_description"], "Every weekday (Mon - Fri) at 15:00 UTC")

        # 2. Trigger schedule via API
        trigger_resp = self.client.post(f'/api/schedules/{schedule_id}/trigger/')
        self.assertEqual(trigger_resp.status_code, 200)
        self.assertIn("Successfully triggered", trigger_resp.data["message"])

        # 3. Toggle pause/resume via API
        toggle_resp = self.client.post(f'/api/schedules/{schedule_id}/toggle/')
        self.assertEqual(toggle_resp.status_code, 200)
        self.assertFalse(toggle_resp.data["is_active"])
        self.assertIsNone(toggle_resp.data["next_run_at"])

    def test_trigger_run_atomic_transaction_resilience_and_on_commit(self):
        """
        Regression test: Verifies that trigger_run() executed inside an active transaction.atomic()
        does not close the connection and executes on_commit callbacks cleanly.
        """
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Transaction Resilience Schedule",
            frequency="daily",
            time_of_day=datetime.time(3, 0),
            is_active=True
        )

        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                agent = schedule.trigger_run(triggered_by_user=self.user)
                self.assertIsNotNone(agent)
                # Verify DB connection is still active and queries work in same transaction
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
        must NOT close the database connection (guard: if not connection.in_atomic_block).
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
            # Verify that connection was not closed and subsequent queries succeed
            self.assertTrue(connection.is_usable())
            agent.refresh_from_db()
            self.assertIsNotNone(agent.status)

    def test_observer_updates_schedule_status_on_pipeline_run_completion(self):
        """
        Observer test: When a PipelineRun transitions status (e.g. running -> completed),
        the post_save signal observer updates the associated WorkflowSchedule.last_status.
        """
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Observer Test Schedule",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            is_active=True
        )
        agent = schedule.trigger_run(triggered_by_user=self.user)
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, "running")

        # Simulate PipelineRun finishing (e.g. completed)
        pipeline_run = schedule.last_pipeline_run
        pipeline_run.status = "completed"
        pipeline_run.save(update_fields=["status"])

        # Observer should have automatically updated schedule.last_status
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, "completed")
        self.assertEqual(schedule.current_execution_status, "completed")

    def test_observer_updates_schedule_status_on_agent_process_update(self):
        """
        Observer test: When a ResearchAgentProcess updates status, the post_save
        observer reflects the status onto observing WorkflowSchedule.
        """
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Agent Observer Schedule",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            is_active=True
        )
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
        from django.contrib.admin.sites import AdminSite
        from research_intelligence.admin import WorkflowScheduleAdmin

        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Halt Schedule",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            is_active=True
        )
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

        # Test admin last_run_display
        admin_site = AdminSite()
        model_admin = WorkflowScheduleAdmin(WorkflowSchedule, admin_site)
        display_html = model_admin.last_run_display(schedule)

        self.assertIn("HALTED (SEARCH)", display_html)
        self.assertNotIn("RUNNING", display_html)

    def test_serializer_observable_last_status(self):
        """
        Tests that WorkflowScheduleSerializer exposes current_execution_status as last_status.
        """
        from api.serializers.schedules import WorkflowScheduleSerializer

        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Serializer Test Schedule",
            frequency="daily",
            time_of_day=datetime.time(2, 0),
            is_active=True
        )
        agent = schedule.trigger_run(triggered_by_user=self.user)

        # Force DB last_status to stale 'running', but pipeline run to 'completed'
        p_run = schedule.last_pipeline_run
        p_run.status = "completed"
        # Use bulk update to bypass signals to test fallback observable property
        PipelineRun.objects.filter(id=p_run.id).update(status="completed")

        schedule.refresh_from_db()
        serializer = WorkflowScheduleSerializer(schedule)
        self.assertEqual(serializer.data["last_status"], "completed")
