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
        ('search', '1. Search & Metadata Ingestion'),
        ('download', '2. PDF Binary Download'),
        ('ocr', '3. Layout OCR Extraction'),
        ('screening', '4. Abstract & Full-Text Screening'),
        ('extraction', '5. Parameter & Claim Extraction'),
        ('signal_score', '6. Composite Signal Score'),
        ('metrics', '7. TRL & Importance Metrics'),
        ('deep_research', '8. Deep Research Iteration'),
        ('reporting', '9. Narrative Report Generation'),
        ('completed', 'Completed'),
    ]

    status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
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
    Manages state transitions: initialized -> search -> download -> ocr (if ocr_provider set) -> screening -> extraction -> completed.
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
        ('search', '1. Search & Ingestion'),
        ('download', '2. PDF Download'),
        ('ocr', '3. OCR Conversion'),
        ('screening', '4. Abstract & Full-Text Screening'),
        ('extraction', '5. Parameter & Claim Extraction'),
        ('signal_score', '6. Signal Score Evaluation'),
        ('reporting', '7. Narrative Reporting'),
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
