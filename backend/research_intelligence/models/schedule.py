import uuid
import logging
import datetime
from typing import Optional, List, Dict, Any
from django.db import models, transaction
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
        ('one_off', 'One-Off (Run Once at Specific Date & Time)'),
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
        help_text="Human-readable schedule name (e.g. 'Daily 3pm Intelligence Ingestion', 'Weekly Deep Review', 'One-Off Ingestion Run')"
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
    one_off_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Specific execution date and time for 'one_off' frequency"
    )
    time_of_day = models.TimeField(
        default=datetime.time(2, 0),
        help_text="Execution time of day for recurring frequencies (e.g. 02:00, 15:00)"
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
    prevent_overlap = models.BooleanField(
        default=True,
        help_text="Prevent concurrent execution if a previous PipelineRun for this schedule is still running"
    )
    configuration_override = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional pipeline configuration overrides (e.g. limit, n_last_days, skip_abstract_screening)"
    )

    # Reliability, Telemetry & Failure Guardrails
    consecutive_failures_count = models.IntegerField(
        default=0,
        help_text="Number of consecutive execution failures"
    )
    max_consecutive_failures = models.IntegerField(
        default=5,
        help_text="Auto-pause schedule if consecutive failures reach this limit"
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

    @property
    def current_execution_status(self) -> str:
        """
        Observable property: dynamically derives the live status from the linked PipelineRun
        (and ResearchAgentProcess), ensuring real-time consistency without desynchronization.
        """
        if self.last_pipeline_run:
            p_status = self.last_pipeline_run.status
            if p_status in ('completed', 'failed', 'aborted'):
                return p_status
            agent = self.last_pipeline_run.agent_processes.first()
            if agent and agent.status in ('completed', 'failed', 'aborted'):
                return agent.status
            return p_status or self.last_status or 'running'
        return self.last_status or ''

    @property
    def is_last_execution_halted_early(self) -> tuple[bool, str]:
        """
        Returns (True, halt_step_name) if the last execution completed early / halted
        (e.g. 0 new papers found due to duplicates, or 0 papers passed screening).
        """
        if not self.last_pipeline_run:
            return False, ""
        agent = self.last_pipeline_run.agent_processes.first()
        if agent:
            step = agent.stopped_at_step
            if agent.status == 'completed' and step and step not in ('completed', 'reporting'):
                return True, step
        return False, ""

    @property
    def last_execution_stop_reason(self) -> str:
        """
        Returns the stop reason or status message of the last execution if available.
        """
        if not self.last_pipeline_run:
            return ""
        agent = self.last_pipeline_run.agent_processes.first()
        if agent and agent.stop_reason:
            return agent.stop_reason
        if self.last_pipeline_run.status_message:
            return self.last_pipeline_run.status_message
        return ""

    @property
    def runs_history(self):
        """Returns QuerySet of all PipelineRun records dispatched by this schedule, newest first."""
        return self.pipeline_runs.all().order_by('-started_at')

    @property
    def successful_runs_count(self) -> int:
        """Returns total number of completed pipeline runs."""
        return self.pipeline_runs.filter(status='completed').count()

    @property
    def failed_runs_count(self) -> int:
        """Returns total number of failed pipeline runs."""
        return self.pipeline_runs.filter(status='failed').count()

    @property
    def success_rate_percent(self) -> Optional[float]:
        """Returns overall success rate percentage (0.0-100.0) or None if no runs recorded."""
        total = self.total_runs_count or self.pipeline_runs.count()
        if total == 0:
            return None
        return round((self.successful_runs_count / total) * 100.0, 1)

    def __str__(self):
        return f"{self.name} [{self.workspace.name}] ({self.schedule_description})"

    def clean(self):
        """Validates schedule frequency parameters, cron expressions, and timezone."""
        if self.timezone_name:
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(self.timezone_name)
            except Exception as e:
                raise ValidationError({"timezone_name": f"Invalid timezone '{self.timezone_name}': {e}"})

        if self.frequency == 'one_off':
            if not self.one_off_datetime:
                raise ValidationError({"one_off_datetime": "An execution date & time is required for 'one_off' frequency."})
        elif self.frequency == 'custom_cron':
            if not self.cron_expression:
                raise ValidationError({"cron_expression": "A cron expression is required for 'custom_cron' frequency."})
            try:
                from croniter import croniter
                croniter(self.cron_expression)
            except ImportError:
                pass
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
        if self.frequency == 'one_off':
            if self.one_off_datetime:
                return f"{self.one_off_datetime.minute} {self.one_off_datetime.hour} {self.one_off_datetime.day} {self.one_off_datetime.month} *"
            return ""

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

        if self.frequency == 'one_off':
            if self.total_runs_count > 0:
                exec_time = self.last_run_at.strftime('%Y-%m-%d %H:%M') if self.last_run_at else ''
                return f"One-off (Executed at {exec_time}{tz_suffix})"
            elif self.one_off_datetime:
                return f"One-off run at {self.one_off_datetime.strftime('%Y-%m-%d %H:%M')}{tz_suffix}"
            return f"One-off run"
        elif self.frequency == 'daily':
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

    def get_timezone_obj(self):
        """Returns standard python zoneinfo.ZoneInfo object based on timezone_name."""
        if self.timezone_name:
            try:
                from zoneinfo import ZoneInfo
                return ZoneInfo(self.timezone_name)
            except Exception:
                pass
        return datetime.timezone.utc

    def compute_next_run(self, base_time: Optional[datetime.datetime] = None) -> Optional[datetime.datetime]:
        """
        Calculates and returns the next upcoming execution datetime using croniter.
        Accurately respects local time and Daylight Saving Time (DST) clock changes
        based on self.timezone_name.
        For one-off schedules, returns one_off_datetime (if not already executed).
        """
        if self.frequency == 'one_off':
            if self.total_runs_count > 0 or not self.is_active:
                return None
            return self.one_off_datetime

        now_dt = base_time or timezone.now()
        cron_expr = self.get_effective_cron_expression()
        tz = self.get_timezone_obj()

        try:
            from croniter import croniter
            # Convert base datetime to target timezone so croniter matches local wall-clock time
            local_dt = now_dt.astimezone(tz)
            itr = croniter(cron_expr, local_dt)
            next_local = itr.get_next(datetime.datetime)
            if next_local.tzinfo is None:
                next_local = next_local.replace(tzinfo=tz)
            # Store in database as UTC
            return next_local.astimezone(datetime.timezone.utc)
        except Exception as e:
            logger.warning(f"Error computing next run for schedule '{self.id}' with expr '{cron_expr}': {e}")
            return now_dt + datetime.timedelta(days=1)

    def trigger_run(self, triggered_by_user=None, force: bool = False, jitter_seconds: int = 0) -> Any:
        """
        Dispatches an autonomous pipeline run for this schedule:
        1. Checks concurrency / overlap policy (skips if prevent_overlap=True and previous run is active, unless force=True)
        2. Creates a PipelineRun (linked to self) & ResearchAgentProcess
        3. Ticks the orchestrator runner asynchronously (with optional jitter delay)
        4. Updates last_run_at, next_run_at, total_runs_count, and last_pipeline_run
        For One-Off schedules, automatically marks is_active=False and next_run_at=None.
        """
        from research_intelligence.models import PipelineRun, ResearchAgentProcess
        from research_intelligence.tasks.orchestrator.agent_engine import run_agent_process_tick, tick_agent_process

        now = timezone.now()

        # Concurrency / Overlap Guard
        if not force and self.prevent_overlap and self.last_pipeline_run:
            current_status = self.current_execution_status
            if current_status in ('running', 'pending'):
                logger.warning(
                    f"⚠️ [SCHEDULE OVERLAP PREVENTED] Schedule '{self.name}' ({self.id}) skipped "
                    f"because previous PipelineRun '{self.last_pipeline_run.id}' is still in status '{current_status}'."
                )
                return None

        config_override = dict(self.configuration_override or {})
        config_override["reprocess_existing"] = self.reprocess_existing

        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name=f"Scheduled Run - {self.name}",
            schedule=self,
            status='running',
            current_stage='search',
            reprocess_existing=self.reprocess_existing,
            triggered_by=triggered_by_user or self.created_by,
            configuration_override=config_override
        )
        agent = ResearchAgentProcess.objects.get(pk=pipeline_run.pk)

        self.last_run_at = now
        self.last_pipeline_run = pipeline_run
        self.last_status = 'running'
        self.total_runs_count += 1
        
        if self.frequency == 'one_off':
            self.is_active = False
            self.next_run_at = None
            self.save(update_fields=['last_run_at', 'last_pipeline_run', 'last_status', 'total_runs_count', 'next_run_at', 'is_active', 'updated_at'])
        else:
            self.next_run_at = self.compute_next_run(base_time=now)
            self.save(update_fields=['last_run_at', 'last_pipeline_run', 'last_status', 'total_runs_count', 'next_run_at', 'updated_at'])

        logger.info(f"⏰ [SCHEDULE DISPATCHED] Triggered scheduled workflow '{self.name}' (Agent: {agent.id}, PipelineRun: {pipeline_run.id}, Jitter: {jitter_seconds}s)")
        
        # Start execution asynchronously via Celery after transaction commit (with optional jitter)
        agent_id_str = str(agent.id)

        def _dispatch_execution():
            try:
                if jitter_seconds > 0:
                    run_agent_process_tick.apply_async(args=[agent_id_str], countdown=jitter_seconds)
                else:
                    run_agent_process_tick.delay(agent_id_str)
            except Exception as e_celery:
                logger.warning(f"⚠️ Celery dispatch failed, falling back to direct execution: {e_celery}")
                tick_agent_process(agent_id_str)

        transaction.on_commit(_dispatch_execution)
        return agent

    def save(self, *args, **kwargs):
        """Auto-computes cron_expression and next_run_at before saving."""
        if not self.cron_expression or self.frequency != 'custom_cron':
            self.cron_expression = self.get_effective_cron_expression()

        if self.frequency == 'one_off':
            if self.total_runs_count > 0:
                self.is_active = False
                self.next_run_at = None
            elif self.is_active and self.one_off_datetime:
                self.next_run_at = self.one_off_datetime
        else:
            if self.is_active and (not self.next_run_at or self.next_run_at <= timezone.now() - datetime.timedelta(hours=24)):
                self.next_run_at = self.compute_next_run()
            elif not self.is_active:
                self.next_run_at = None

        super().save(*args, **kwargs)
