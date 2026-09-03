import uuid
import logging
from django.db import models
from django.conf import settings

logger = logging.getLogger(__name__)


class PipelineRunQuerySet(models.QuerySet):
    def prefetch_related(self, *lookups):
        cleaned = [l for l in lookups if l != 'agent_processes']
        if cleaned:
            return super().prefetch_related(*cleaned)
        return self


class PipelineRun(models.Model):
    """
    Represents a specific scheduled execution run (e.g., weekly batch run).
    Groups papers, extractions, and digests generated for a new weekly dataset.
    """
    objects = models.Manager.from_queryset(PipelineRunQuerySet)()

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
    error_message = models.TextField(
        blank=True,
        null=True,
        default="",
        help_text="Detailed error message if run failed."
    )
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    @property
    def pipeline_run(self):
        return self

    def save(self, *args, **kwargs):
        if 'update_fields' in kwargs and kwargs['update_fields']:
            mapped_fields = []
            for f in kwargs['update_fields']:
                if f == 'pipeline_run':
                    mapped_fields.append('configuration_override')
                elif f == 'current_step':
                    mapped_fields.append('current_stage')
                elif f == 'stopped_at_step':
                    mapped_fields.append('stopped_at_stage')
                elif f == 'stop_reason':
                    mapped_fields.append('status_message')
                elif f == 'error_message':
                    mapped_fields.append('error_message')
                else:
                    mapped_fields.append(f)
            kwargs['update_fields'] = mapped_fields
        super().save(*args, **kwargs)

    @property
    def agent_processes(self):
        """Logical proxy reverse-relation for backward compatibility."""
        return PipelineRunAgentProcessProxy(self)

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


class PipelineRunAgentProcessProxy:
    """
    Simulates reverse relation pipeline_run.agent_processes for backward compatibility.
    """
    def __init__(self, pipeline_run, items=None):
        self.pipeline_run = pipeline_run
        self._items = items

    def _get_items(self):
        if self._items is not None:
            return self._items
        cfg = self.pipeline_run.configuration_override or {}
        if not cfg and hasattr(self.pipeline_run, 'pk') and self.pipeline_run.pk:
            db_cfg = PipelineRun.objects.filter(pk=self.pipeline_run.pk).values_list('configuration_override', flat=True).first()
            if db_cfg:
                cfg = db_cfg
        if cfg.get('_detached', False):
            return []
        if not (cfg.get('_is_agent', False) or cfg.get('autonomous', False) or self.pipeline_run.schedule_id is not None):
            return []
        try:
            return [ResearchAgentProcess.objects.get(pk=self.pipeline_run.pk)]
        except Exception:
            return []

    def filter(self, *args, **kwargs):
        status = kwargs.get('status')
        status_in = kwargs.get('status__in')
        items = self._get_items()
        filtered = []
        for item in items:
            if status and item.status != status:
                continue
            if status_in and item.status not in status_in:
                continue
            filtered.append(item)
        return PipelineRunAgentProcessProxy(self.pipeline_run, items=filtered)

    def exclude(self, *args, **kwargs):
        status = kwargs.get('status')
        status_in = kwargs.get('status__in')
        items = self._get_items()
        filtered = []
        for item in items:
            if status and item.status == status:
                continue
            if status_in and item.status in status_in:
                continue
            filtered.append(item)
        return PipelineRunAgentProcessProxy(self.pipeline_run, items=filtered)

    def exists(self):
        return len(self._get_items()) > 0

    def first(self):
        items = self._get_items()
        return items[0] if items else None

    def last(self):
        items = self._get_items()
        return items[-1] if items else None

    def all(self):
        return self

    def count(self):
        return len(self._get_items())

    def __iter__(self):
        return iter(self._get_items())

    def __len__(self):
        return len(self._get_items())

    def __getitem__(self, idx):
        return self._get_items()[idx]

    def __bool__(self):
        return self.exists()


class ResearchAgentProcessQuerySet(models.QuerySet):
    def filter(self, *args, **kwargs):
        if 'current_step' in kwargs:
            kwargs['current_stage'] = kwargs.pop('current_step')
        if 'current_step__in' in kwargs:
            kwargs['current_stage__in'] = kwargs.pop('current_step__in')
        if 'stopped_at_step' in kwargs:
            kwargs['stopped_at_stage'] = kwargs.pop('stopped_at_step')
        if 'stop_reason' in kwargs:
            kwargs['status_message'] = kwargs.pop('stop_reason')
        if 'pipeline_run' in kwargs:
            pr_val = kwargs.pop('pipeline_run')
            if pr_val is not None:
                kwargs['pk'] = pr_val.pk if hasattr(pr_val, 'pk') else pr_val
        if 'pipeline_run__isnull' in kwargs:
            kwargs.pop('pipeline_run__isnull')
        return super().filter(*args, **kwargs)

    def select_related(self, *fields):
        cleaned = [f for f in fields if f != 'pipeline_run']
        if cleaned:
            return super().select_related(*cleaned)
        return self


class ResearchAgentProcessManager(models.Manager.from_queryset(ResearchAgentProcessQuerySet)):
    def create(self, **kwargs):
        if 'current_step' in kwargs:
            kwargs['current_stage'] = kwargs.pop('current_step')
        if 'stopped_at_step' in kwargs:
            kwargs['stopped_at_stage'] = kwargs.pop('stopped_at_step')
        if 'stop_reason' in kwargs:
            kwargs['status_message'] = kwargs.pop('stop_reason')
        if 'error_message' in kwargs:
            kwargs['error_message'] = kwargs.pop('error_message') or ""
        if 'reprocess_existing' not in kwargs:
            config = kwargs.get('configuration_override') or {}
            if 'reprocess_existing' in config:
                kwargs['reprocess_existing'] = bool(config['reprocess_existing'])
            elif 'workspace' in kwargs and hasattr(kwargs['workspace'], 'reprocess_existing'):
                kwargs['reprocess_existing'] = bool(kwargs['workspace'].reprocess_existing)
        config = dict(kwargs.get('configuration_override') or {})
        config['_is_agent'] = True
        kwargs['configuration_override'] = config
        if 'pipeline_run' in kwargs:
            p_val = kwargs.pop('pipeline_run')
            if p_val is None:
                config['_detached'] = True
                kwargs['configuration_override'] = config
            elif isinstance(p_val, models.Model):
                # Update existing PipelineRun to attach agent settings
                p_cfg = dict(p_val.configuration_override or {})
                p_cfg['_is_agent'] = True
                p_cfg.update(config)
                p_val.configuration_override = p_cfg
                for k, v in kwargs.items():
                    if k == 'triggered_by' and v is None and p_val.triggered_by is not None:
                        continue
                    if k == 'current_stage' and v == 'initialized' and p_val.current_stage and p_val.current_stage != 'initialized':
                        continue
                    if hasattr(p_val, k):
                        setattr(p_val, k, v)
                p_val.save()
                return ResearchAgentProcess.objects.get(pk=p_val.pk)
        return super().create(**kwargs)


class ResearchAgentProcess(PipelineRun):
    """
    Logical Proxy Model over PipelineRun for 100% backward compatibility.
    Operates directly on the PipelineRun table without maintaining a duplicate model.
    """
    objects = ResearchAgentProcessManager()

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

    class Meta:
        proxy = True
        app_label = 'research_intelligence'
        verbose_name = "Research Agent Process"
        verbose_name_plural = "Research Agent Processes"

    def __init__(self, *args, **kwargs):
        if 'current_step' in kwargs:
            kwargs['current_stage'] = kwargs.pop('current_step')
        if 'stopped_at_step' in kwargs:
            kwargs['stopped_at_stage'] = kwargs.pop('stopped_at_step')
        if 'stop_reason' in kwargs:
            kwargs['status_message'] = kwargs.pop('stop_reason')
        if 'error_message' in kwargs:
            kwargs['error_message'] = kwargs.pop('error_message') or ""
        if 'reprocess_existing' not in kwargs:
            config = kwargs.get('configuration_override') or {}
            if 'reprocess_existing' in config:
                kwargs['reprocess_existing'] = bool(config['reprocess_existing'])
        kwargs.pop('pipeline_run', None)
        super().__init__(*args, **kwargs)

    @property
    def pipeline_run(self):
        """Logical proxy self-reference or linked pipeline run."""
        cfg = self.configuration_override or {}
        if cfg.get('_detached', False):
            linked_id = cfg.get('_linked_pipeline_run_id')
            if linked_id:
                return PipelineRun.objects.filter(id=linked_id).first()
            return None
        return self

    @pipeline_run.setter
    def pipeline_run(self, value):
        if not self.configuration_override:
            self.configuration_override = {}
        if value is None:
            self.configuration_override['_detached'] = True
            self.configuration_override.pop('_linked_pipeline_run_id', None)
        else:
            if hasattr(value, 'id') and str(value.id) != str(self.id):
                self.configuration_override['_detached'] = True
                self.configuration_override['_linked_pipeline_run_id'] = str(value.id)
            else:
                self.configuration_override.pop('_detached', None)
                self.configuration_override.pop('_linked_pipeline_run_id', None)

    @property
    def pipeline_run_id(self):
        """Logical proxy self-reference ID or linked ID."""
        cfg = self.configuration_override or {}
        if cfg.get('_detached', False):
            return cfg.get('_linked_pipeline_run_id')
        return self.id

    @property
    def current_step(self):
        return self.current_stage

    @current_step.setter
    def current_step(self, value):
        self.current_stage = value

    @property
    def stopped_at_step(self):
        return self.stopped_at_stage

    @stopped_at_step.setter
    def stopped_at_step(self, value):
        self.stopped_at_stage = value

    @property
    def stop_reason(self):
        return self.status_message

    @stop_reason.setter
    def stop_reason(self, value):
        self.status_message = value or ""

    def save(self, *args, **kwargs):
        if 'update_fields' in kwargs and kwargs['update_fields']:
            mapped_fields = []
            for f in kwargs['update_fields']:
                if f == 'pipeline_run':
                    mapped_fields.append('configuration_override')
                elif f == 'current_step':
                    mapped_fields.append('current_stage')
                elif f == 'stopped_at_step':
                    mapped_fields.append('stopped_at_stage')
                elif f == 'stop_reason':
                    mapped_fields.append('status_message')
                elif f == 'error_message':
                    mapped_fields.append('error_message')
                else:
                    mapped_fields.append(f)
            kwargs['update_fields'] = mapped_fields
        super().save(*args, **kwargs)

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
