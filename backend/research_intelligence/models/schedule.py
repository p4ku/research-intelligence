import uuid
import logging
import datetime
from typing import Optional, List, Dict, Any
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class WorkflowSchedule(models.Model):
    """
    Automated Cron / Periodic Execution Schedule for Workspace Workflows.
    Allows defining recurring runs (Daily, Weekdays Mon-Fri, Weekly, Monthly, or Custom Cron)
    to autonomously dispatch Systematic Literature Review (SLR) ingestion and analysis pipelines.
    """

    FREQUENCY_CHOICES = [
        ('daily', 'Daily (Every Day)'),
        ('weekdays', 'Weekdays (Mon - Fri, excluding Sat & Sun)'),
        ('weekly', 'Weekly (Specific Days of Week)'),
        ('monthly', 'Monthly (Specific Day of Month)'),
        ('interval_hours', 'Interval (Every N Hours)'),
        ('custom_cron', 'Custom Cron Expression'),
    ]

    WEEKDAY_MAP = {
        0: 'Mon',
        1: 'Tue',
        2: 'Wed',
        3: 'Thu',
        4: 'Fri',
        5: 'Sat',
        6: 'Sun',
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'Workspace',
        on_delete=models.CASCADE,
        related_name='schedules',
        help_text="Workspace/Workflow target to execute on schedule"
    )
    name = models.CharField(
        max_length=255,
        help_text="Human-readable schedule name (e.g. 'Daily 3pm Intelligence Ingestion', 'Weekly Deep Review')"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Enable or pause this recurring workflow schedule"
    )

    # Recurrence configuration
    frequency = models.CharField(
        max_length=32,
        choices=FREQUENCY_CHOICES,
        default='daily',
        help_text="Recurrence frequency pattern"
    )
    time_of_day = models.TimeField(
        default=datetime.time(2, 0),
        help_text="Execution time of day (e.g. 02:00, 15:00)"
    )
    days_of_week = models.JSONField(
        default=list,
        blank=True,
        help_text="List of weekday integers [0=Monday, 1=Tuesday, ... 6=Sunday] for weekly frequency"
    )
    day_of_month = models.IntegerField(
        default=1,
        blank=True,
        null=True,
        help_text="Day of month (1-31) for monthly frequency"
    )
    interval_hours = models.IntegerField(
        default=24,
        blank=True,
        null=True,
        help_text="Interval in hours for 'interval_hours' frequency"
    )
    cron_expression = models.CharField(
        max_length=100,
        blank=True,
        help_text="Standard 5-part cron expression (e.g. '0 2 * * 1', '0 15 * * 1-5'). Auto-computed or custom."
    )
    timezone_name = models.CharField(
        max_length=64,
        default='UTC',
        help_text="Timezone for schedule execution (e.g. 'UTC', 'Europe/Berlin', 'Europe/Warsaw')"
    )

    # Execution overrides & options
    reprocess_existing = models.BooleanField(
        default=False,
        help_text="If True, re-screen and re-extract all workspace papers instead of skipping existing papers"
    )
    configuration_override = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional pipeline configuration overrides (e.g. limit, date_range_days, skip_abstract_screening)"
    )

    # Execution tracking & telemetry
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent scheduled execution"
    )
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Calculated timestamp of the next upcoming execution"
    )
    last_pipeline_run = models.ForeignKey(
        'PipelineRun',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_by_schedules',
        help_text="Reference to the most recent PipelineRun triggered by this schedule"
    )
    last_status = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Status of the last triggered pipeline (e.g. 'completed', 'failed', 'running')"
    )
    total_runs_count = models.IntegerField(
        default=0,
        help_text="Total number of pipeline runs dispatched by this schedule"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_schedules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-is_active', 'next_run_at', '-created_at']
        indexes = [
            models.Index(fields=['is_active', 'next_run_at']),
            models.Index(fields=['workspace', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} [{self.workspace.name}] ({self.schedule_description})"

    def clean(self):
        """Validates schedule frequency parameters and cron expressions."""
        if self.frequency == 'custom_cron':
            if not self.cron_expression:
                raise ValidationError({"cron_expression": "A cron expression is required for 'custom_cron' frequency."})
            try:
                from croniter import croniter
                croniter(self.cron_expression)
            except Exception as e:
                raise ValidationError({"cron_expression": f"Invalid cron expression '{self.cron_expression}': {e}"})
        elif self.frequency == 'monthly':
            if not self.day_of_month or self.day_of_month < 1 or self.day_of_month > 31:
                raise ValidationError({"day_of_month": "Day of month must be between 1 and 31."})
        elif self.frequency == 'interval_hours':
            if not self.interval_hours or self.interval_hours < 1:
                raise ValidationError({"interval_hours": "Interval hours must be at least 1."})

    def get_effective_cron_expression(self) -> str:
        """
        Returns the canonical 5-part cron expression representing this schedule.
        Auto-generates from frequency settings if frequency is not custom_cron.
        """
        if self.frequency == 'custom_cron' and self.cron_expression:
            return self.cron_expression.strip()

        minute = self.time_of_day.minute if self.time_of_day else 0
        hour = self.time_of_day.hour if self.time_of_day else 2

        if self.frequency == 'daily':
            return f"{minute} {hour} * * *"

        elif self.frequency == 'weekdays':
            # Mon-Fri: 1,2,3,4,5 in croniter (1=Monday, 5=Friday)
            return f"{minute} {hour} * * 1-5"

        elif self.frequency == 'weekly':
            if self.days_of_week and isinstance(self.days_of_week, list):
                # Convert python weekdays (0=Mon...6=Sun) to cron weekdays (1=Mon...7=Sun or 0=Sun)
                cron_days = []
                for d in self.days_of_week:
                    try:
                        d_int = int(d)
                        cron_d = 7 if d_int == 6 else (d_int + 1)
                        cron_days.append(str(cron_d))
                    except (ValueError, TypeError):
                        pass
                if cron_days:
                    return f"{minute} {hour} * * {','.join(sorted(set(cron_days)))}"
            # Default to Monday if no days specified
            return f"{minute} {hour} * * 1"

        elif self.frequency == 'monthly':
            dom = self.day_of_month or 1
            return f"{minute} {hour} {dom} * *"

        elif self.frequency == 'interval_hours':
            hrs = self.interval_hours or 24
            if hrs < 24 and 24 % hrs == 0:
                return f"{minute} */{hrs} * * *"
            return f"{minute} {hour} * * *"

        return f"{minute} {hour} * * *"

    @property
    def schedule_description(self) -> str:
        """Returns a human-readable English summary of the schedule pattern."""
        t_str = self.time_of_day.strftime("%H:%M") if self.time_of_day else "02:00"
        tz_suffix = f" {self.timezone_name}" if self.timezone_name else ""

        if self.frequency == 'daily':
            return f"Every day at {t_str}{tz_suffix}"
        elif self.frequency == 'weekdays':
            return f"Every weekday (Mon - Fri) at {t_str}{tz_suffix}"
        elif self.frequency == 'weekly':
            if self.days_of_week and isinstance(self.days_of_week, list):
                day_names = [self.WEEKDAY_MAP.get(int(d), str(d)) for d in self.days_of_week if str(d).isdigit() and int(d) in self.WEEKDAY_MAP]
                if day_names:
                    return f"Weekly on {', '.join(day_names)} at {t_str}{tz_suffix}"
            return f"Every Monday at {t_str}{tz_suffix}"
        elif self.frequency == 'monthly':
            dom = self.day_of_month or 1
            suffix = "th" if 11 <= dom <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(dom % 10, "th")
            return f"Monthly on the {dom}{suffix} at {t_str}{tz_suffix}"
        elif self.frequency == 'interval_hours':
            return f"Every {self.interval_hours or 24} hours"
        elif self.frequency == 'custom_cron':
            return f"Cron: {self.cron_expression}{tz_suffix}"
        return f"At {t_str}{tz_suffix}"

    def compute_next_run(self, base_time: Optional[datetime.datetime] = None) -> datetime.datetime:
        """
        Calculates and returns the next upcoming execution datetime using croniter.
        """
        from croniter import croniter
        now_dt = base_time or timezone.now()
        cron_expr = self.get_effective_cron_expression()
        
        try:
            itr = croniter(cron_expr, now_dt)
            next_ts = itr.get_next(float)
            return datetime.datetime.fromtimestamp(next_ts, tz=datetime.timezone.utc)
        except Exception as e:
            logger.warning(f"Error computing next run for schedule '{self.id}' with expr '{cron_expr}': {e}")
            return now_dt + datetime.timedelta(days=1)

    def trigger_run(self, triggered_by_user=None) -> Any:
        """
        Dispatches an autonomous pipeline run for this schedule:
        1. Creates a PipelineRun & ResearchAgentProcess
        2. Ticks the orchestrator runner
        3. Updates last_run_at, next_run_at, total_runs_count, and last_pipeline_run
        """
        from research_intelligence.models import PipelineRun, ResearchAgentProcess
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process

        now = timezone.now()
        config_override = dict(self.configuration_override or {})
        config_override["reprocess_existing"] = self.reprocess_existing

        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status='running',
            current_stage='search',
            reprocess_existing=self.reprocess_existing,
            triggered_by=triggered_by_user or self.created_by,
        )

        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            name=f"Scheduled Run - {self.name}",
            status='running',
            current_step='initialized',
            configuration_override=config_override
        )

        self.last_run_at = now
        self.last_pipeline_run = pipeline_run
        self.last_status = 'running'
        self.total_runs_count += 1
        self.next_run_at = self.compute_next_run(base_time=now)
        self.save(update_fields=['last_run_at', 'last_pipeline_run', 'last_status', 'total_runs_count', 'next_run_at', 'updated_at'])

        logger.info(f"⏰ [SCHEDULE DISPATCHED] Triggered scheduled workflow '{self.name}' (Agent: {agent.id}, PipelineRun: {pipeline_run.id})")
        
        # Start execution
        tick_agent_process(str(agent.id))
        return agent

    def save(self, *args, **kwargs):
        """Auto-computes cron_expression and next_run_at before saving."""
        if not self.cron_expression or self.frequency != 'custom_cron':
            self.cron_expression = self.get_effective_cron_expression()

        if self.is_active and (not self.next_run_at or self.next_run_at <= timezone.now() - datetime.timedelta(hours=24)):
            self.next_run_at = self.compute_next_run()
        elif not self.is_active:
            self.next_run_at = None

        super().save(*args, **kwargs)
