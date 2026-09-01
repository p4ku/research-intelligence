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
