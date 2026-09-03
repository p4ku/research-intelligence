import uuid
import logging
from django.db import models
from django.conf import settings

logger = logging.getLogger(__name__)


class PipelineRun(models.Model):
    """
    Represents a specific scheduled execution run (e.g., weekly batch run).
    Groups papers, extractions, and digests generated for a new weekly dataset.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('Workspace', on_delete=models.CASCADE, related_name="runs")
    run_date = models.DateField(auto_now_add=True, help_text="Date when this ingestion run was triggered")
    STAGE_CHOICES = [
        ('search', 'Search & Metadata Ingestion'),
        ('abstract_screening', 'Abstract Screening'),
        ('download', 'PDF Binary Download'),
        ('ocr', 'Layout OCR Extraction'),
        ('full_text_screening', 'Full-Text Screening'),
        ('screening', 'Dual-Stage Screening'),
        ('extraction', 'Parameter & Claim Extraction'),
        ('signal_score', 'Composite Signal Score'),
        ('metrics', 'TRL & Importance Metrics'),
        ('deep_research', 'Deep Research Iteration'),
        ('reporting', 'Narrative Report Generation'),
        ('completed', 'Completed'),
    ]

    name = models.CharField(max_length=255, blank=True, default="", help_text="Optional human-readable label for this pipeline run")
    status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('paused', 'Paused'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('aborted', 'Aborted')
        ],
        default='pending'
    )
    current_stage = models.CharField(
        max_length=50,
        choices=STAGE_CHOICES,
        default='search',
        help_text="Active processing stage of the overall pipeline"
    )
    stopped_at_stage = models.CharField(
        max_length=50,
        choices=STAGE_CHOICES,
        blank=True,
        null=True,
        help_text="Pipeline stage at which the pipeline run halted, completed, or failed"
    )
    configuration_override = models.JSONField(
        default=dict,
        blank=True,
        help_text="Overrides e.g. limit, date_range_days, query_prefix, skip_abstract_screening, notification_email, reprocess_existing"
    )
    step_history = models.JSONField(
        default=list,
        blank=True,
        help_text="Audit log of state transitions and lifecycle events"
    )
    stage_results = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured status, summary message, and metrics for each executed pipeline stage"
    )
    
    # Aggregated run metrics
    total_papers_fetched = models.IntegerField(default=0)
    total_papers_passed_screening = models.IntegerField(default=0)
    tokens_in = models.BigIntegerField(default=0, help_text="Total input/prompt tokens used in this run")
    tokens_out = models.BigIntegerField(default=0, help_text="Total output/completion tokens used in this run")
    tokens_consumed = models.BigIntegerField(default=0, help_text="Total tokens used in this run (in + out)")
    usd_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pipeline_runs",
        help_text="User who launched this pipeline run"
    )
    schedule = models.ForeignKey(
        'WorkflowSchedule',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pipeline_runs",
        help_text="The WorkflowSchedule that triggered this run (if automated)"
    )
    reprocess_existing = models.BooleanField(
        default=False,
        help_text="If True, re-evaluates and links existing workspace papers through screening, extraction, and signal scoring even if no new papers were scraped."
    )
    status_message = models.TextField(
        blank=True,
        default="",
        help_text="Detailed status, halting reason, or completion summary message."
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    @property
    def current_step(self):
        """Backward-compatible alias matching ResearchAgentProcess.current_step."""
        return self.current_stage

    @current_step.setter
    def current_step(self, value):
        self.current_stage = value

    @property
    def stopped_at_step(self):
        """Backward-compatible alias matching ResearchAgentProcess.stopped_at_step."""
        return self.stopped_at_stage

    @stopped_at_step.setter
    def stopped_at_step(self, value):
        self.stopped_at_stage = value

    @property
    def stop_reason(self):
        """Backward-compatible alias matching ResearchAgentProcess.stop_reason."""
        return self.status_message

    @stop_reason.setter
    def stop_reason(self, value):
        self.status_message = value

    def tick(self) -> dict:
        """Executes a single state transition tick for this PipelineRun via the DAG engine."""
        from research_intelligence.tasks.orchestrator.runner import PipelineRunner
        return PipelineRunner.tick(self.id)

    def pause(self, reason: str = "Paused by user") -> bool:
        """Pauses execution of the pipeline run."""
        from django.utils import timezone
        if self.status not in ['running', 'pending']:
            return False
        self.status = 'paused'
        self.status_message = reason
        history = list(self.step_history or [])
        history.append({
            "step": self.current_stage,
            "event": "paused",
            "message": reason,
            "timestamp": timezone.now().isoformat()
        })
        self.step_history = history
        self.save(update_fields=['status', 'status_message', 'step_history'])
        return True

    def resume(self) -> bool:
        """Resumes a paused pipeline run and dispatches an orchestrator tick."""
        from django.utils import timezone
        if self.status != 'paused':
            return False
        self.status = 'running'
        history = list(self.step_history or [])
        history.append({
            "step": self.current_stage,
            "event": "resumed",
            "timestamp": timezone.now().isoformat()
        })
        self.step_history = history
        self.save(update_fields=['status', 'step_history'])
        from research_intelligence.tasks.orchestrator.dag.base_node import safe_dispatch_on_commit
        from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
        safe_dispatch_on_commit(lambda: notify_pipeline_orchestrator_tick(self))
        return True

    def abort(self, reason: str = "Aborted by user") -> bool:
        """Aborts an active or paused pipeline run."""
        from django.utils import timezone
        if self.status in ['completed', 'failed', 'aborted']:
            return False
        self.status = 'aborted'
        self.status_message = reason
        self.stopped_at_stage = self.current_stage
        self.completed_at = timezone.now()
        history = list(self.step_history or [])
        history.append({
            "step": self.current_stage,
            "event": "aborted",
            "message": reason,
            "timestamp": timezone.now().isoformat()
        })
        self.step_history = history
        self.save(update_fields=['status', 'status_message', 'stopped_at_stage', 'step_history', 'completed_at'])
        return True

    def get_papers(self, screening_status=None, exclude_status=None):
        """
        Returns all papers associated with this run (both newly ingested and reprocessed)
        evaluated via PaperMetric.
        Filters evaluate metrics__pipeline_run and status in the same filter expression
        to guarantee evaluation against the single, run-specific PaperMetric row.
        """
        from .paper import Paper

        if screening_status is not None:
            if isinstance(screening_status, (list, tuple, set)):
                return Paper.objects.filter(
                    metrics__pipeline_run=self,
                    metrics__screening_status__in=screening_status
                ).distinct()
            return Paper.objects.filter(
                metrics__pipeline_run=self,
                metrics__screening_status=screening_status
            ).distinct()

        if exclude_status is not None:
            if isinstance(exclude_status, (list, tuple, set)):
                return Paper.objects.filter(metrics__pipeline_run=self).exclude(
                    metrics__pipeline_run=self,
                    metrics__screening_status__in=exclude_status
                ).distinct()
            return Paper.objects.filter(metrics__pipeline_run=self).exclude(
                metrics__pipeline_run=self,
                metrics__screening_status=exclude_status
            ).distinct()

        return Paper.objects.filter(metrics__pipeline_run=self).distinct()

    @property
    def papers(self):
        """Returns all papers associated with this run (both newly ingested and reprocessed)."""
        return self.get_papers()

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return max(0.0, (self.completed_at - self.started_at).total_seconds())
        if self.started_at and self.status == 'running':
            from django.utils import timezone
            return max(0.0, (timezone.now() - self.started_at).total_seconds())
        return None

    @property
    def execution_time_display(self) -> str:
        sec = self.duration_seconds
        if sec is None:
            return "-"
        if sec < 1.0:
            formatted = f"{sec:.2f}s"
        elif sec < 60:
            formatted = f"{sec:.1f}s"
        else:
            minutes, rem_sec = divmod(int(sec), 60)
            if minutes < 60:
                formatted = f"{minutes}m {rem_sec:02d}s"
            else:
                hours, mins = divmod(minutes, 60)
                formatted = f"{hours}h {mins:02d}m {rem_sec:02d}s"
        if self.status == 'running':
            return f"⏳ {formatted}"
        return formatted

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-started_at', '-id']

    def __str__(self):
        return f"{self.workspace.name} - Run {self.run_date} ({self.status})"


class ResearchAgentProcess(models.Model):
    """
    Autonomous State Machine Orchestrator running an ingestion & intelligence cycle for a Workspace.
    Manages state transitions: initialized -> search -> abstract_screening -> download -> ocr -> full_text_screening -> extraction -> signal_score -> reporting -> completed.
    Supports parallel runs, pause/resume/abort controls, dynamic search query modifiers (e.g. date_range_days),
    and sends completion/failure notifications.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('aborted', 'Aborted')
    ]

    STEP_CHOICES = [
        ('initialized', 'Initialized'),
        ('search', 'Search & Ingestion'),
        ('abstract_screening', 'Abstract Screening'),
        ('download', 'PDF Download'),
        ('ocr', 'OCR Conversion'),
        ('full_text_screening', 'Full-Text Screening'),
        ('screening', 'Dual-Stage Screening'),
        ('extraction', 'Parameter & Claim Extraction'),
        ('signal_score', 'Signal Score Evaluation'),
        ('reporting', 'Narrative Reporting'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('aborted', 'Aborted')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('Workspace', on_delete=models.CASCADE, related_name="agent_processes")
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_processes")
    name = models.CharField(max_length=255, help_text="e.g. 'ArXiv Monthly Agent Ingestion'")

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    current_step = models.CharField(max_length=50, choices=STEP_CHOICES, default='initialized')
    stopped_at_step = models.CharField(
        max_length=50,
        choices=STEP_CHOICES,
        blank=True,
        null=True,
        help_text="Pipeline step at which the agent process halted, completed, or failed"
    )
    stop_reason = models.TextField(
        blank=True,
        default="",
        help_text="Detailed explanation or status message describing why the pipeline completed, halted early, or failed"
    )
    stage_results = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured status, summary message, and metrics for each executed pipeline stage (search, download, ocr, screening, extraction, signal_score, reporting)."
    )

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_processes",
        help_text="User who launched this agent process"
    )

    configuration_override = models.JSONField(
        default=dict,
        blank=True,
        help_text="Overrides e.g. limit, date_range_days, query_prefix, skip_abstract_screening, notification_email"
    )
    step_history = models.JSONField(default=list, blank=True, help_text="Audit log of step transitions and metrics")
    error_message = models.TextField(blank=True, null=True)

    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return max(0.0, (self.completed_at - self.started_at).total_seconds())
        if self.started_at and self.status == 'running':
            from django.utils import timezone
            return max(0.0, (timezone.now() - self.started_at).total_seconds())
        return None

    @property
    def execution_time_display(self) -> str:
        sec = self.duration_seconds
        if sec is None:
            return "-"
        if sec < 1.0:
            formatted = f"{sec:.2f}s"
        elif sec < 60:
            formatted = f"{sec:.1f}s"
        else:
            minutes, rem_sec = divmod(int(sec), 60)
            if minutes < 60:
                formatted = f"{minutes}m {rem_sec:02d}s"
            else:
                hours, mins = divmod(minutes, 60)
                formatted = f"{hours}h {mins:02d}m {rem_sec:02d}s"
        if self.status == 'running':
            return f"⏳ {formatted}"
        return formatted

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-started_at', '-id']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['pipeline_run']),
            models.Index(fields=['workspace', '-started_at']),
        ]

    def __str__(self):
        return f"Agent '{self.name}' [{self.workspace.name}] ({self.status} - step: {self.current_step})"


class ComponentRun(models.Model):
    """
    Generalized component execution model tracking any step/job execution within a PipelineRun.
    Supports step types: 'search', 'download', 'ocr', 'screening', 'extraction', 'signal_score', 'metrics', 'deep_research', 'reporting'.
    Monitors lifecycle (pending, running, completed, failed, aborted), Celery task ID, storage paths, metrics, and logs.
    """
    STEP_TYPE_CHOICES = [
        ('search', 'Search & Metadata Ingestion'),
        ('download', 'PDF Binary Download'),
        ('ocr', 'Layout OCR Extraction'),
        ('screening', 'Abstract & Full-Text Screening'),
        ('extraction', 'Parameter & Claim Extraction'),
        ('signal_score', 'Signal Score Evaluation'),
        ('metrics', 'TRL & Graph Metrics'),
        ('deep_research', 'Deep Research Iteration'),
        ('reporting', 'Narrative Report Generation'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('aborted', 'Aborted')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="component_runs")
    step_type = models.CharField(max_length=50, choices=STEP_TYPE_CHOICES, help_text="Type of pipeline step/task")
    component_name = models.CharField(max_length=100, help_text="Specific component identifier (e.g. 'arxiv_scraper', 'gemini_screener', 'docling_ocr')")
    
    # Optional foreign key references for specific step types
    scraper = models.ForeignKey('Scraper', on_delete=models.SET_NULL, null=True, blank=True, related_name="component_runs")
    
    celery_task_id = models.CharField(max_length=255, blank=True, null=True, help_text="Celery Task ID executing this job")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    
    # Storage, Payload & Metrics
    raw_storage_path = models.CharField(max_length=512, blank=True, null=True, help_text="Orthogonal path in Django default_storage for raw output/payload")
    input_params = models.JSONField(default=dict, blank=True, help_text="Input arguments passed to this component execution")
    metrics = models.JSONField(default=dict, blank=True, help_text="Execution metrics (e.g. total_fetched, total_created, tokens_consumed, etc.)")
    output_data = models.JSONField(default=dict, blank=True, help_text="Structured summary / outputs produced by this step execution")
    error_message = models.TextField(blank=True, null=True)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    @property
    def meta(self):
        """Returns consolidated metadata dictionary stored in metrics."""
        return self.metrics or {}

    @property
    def duration_seconds(self):
        """Returns duration in seconds extracted from metrics or calculated from timestamps."""
        if self.metrics and isinstance(self.metrics, dict):
            if "total_duration_seconds" in self.metrics and self.metrics["total_duration_seconds"] is not None:
                try:
                    return float(self.metrics["total_duration_seconds"])
                except (ValueError, TypeError):
                    pass
            if "duration_seconds" in self.metrics and self.metrics["duration_seconds"] is not None:
                try:
                    return float(self.metrics["duration_seconds"])
                except (ValueError, TypeError):
                    pass
        if self.started_at and self.completed_at:
            return max(0.0, (self.completed_at - self.started_at).total_seconds())
        if self.started_at and self.status == 'running':
            from django.utils import timezone
            return max(0.0, (timezone.now() - self.started_at).total_seconds())
        return None

    @property
    def execution_time_display(self) -> str:
        sec = self.duration_seconds
        if sec is None:
            return "-"
        if sec < 1.0:
            formatted = f"{sec:.2f}s"
        elif sec < 60:
            formatted = f"{sec:.1f}s"
        else:
            minutes, rem_sec = divmod(int(sec), 60)
            if minutes < 60:
                formatted = f"{minutes}m {rem_sec:02d}s"
            else:
                hours, mins = divmod(minutes, 60)
                formatted = f"{hours}h {mins:02d}m {rem_sec:02d}s"
        if self.status == 'running':
            return f"⏳ {formatted}"
        return formatted

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-started_at', '-id']
        indexes = [
            models.Index(fields=['pipeline_run', 'step_type']),
            models.Index(fields=['pipeline_run', 'status']),
            models.Index(fields=['pipeline_run', '-started_at']),
        ]

    def __str__(self):
        return f"{self.step_type}:{self.component_name} - Run {self.pipeline_run.id} ({self.status})"
