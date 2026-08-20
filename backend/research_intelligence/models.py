import uuid
import secrets
import hashlib
import logging
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

class Workspace(models.Model):
    """
    Represents a specific research project (e.g., 'Agentic AI Research Scanner').
    Top-level model holding prompt parameters, criteria settings, and API quotas.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    # Specific criteria for Step 4 Abstract Screening and Full-Text Screening
    abstract_acceptance_criteria = models.TextField(default="", blank=True, help_text="Specific inclusion criteria for Step 4 Abstract Screening")
    abstract_rejection_criteria = models.TextField(default="", blank=True, help_text="Specific exclusion criteria for Step 4 Abstract Screening")
    full_text_acceptance_criteria = models.TextField(default="", blank=True, help_text="Specific inclusion criteria for Step 4 Full-Text Screening")
    full_text_rejection_criteria = models.TextField(default="", blank=True, help_text="Specific exclusion criteria for Step 4 Full-Text Screening")

    def get_abstract_acceptance_criteria(self) -> str:
        return self.abstract_acceptance_criteria.strip()

    def get_abstract_rejection_criteria(self) -> str:
        return self.abstract_rejection_criteria.strip()

    def get_full_text_acceptance_criteria(self) -> str:
        return self.full_text_acceptance_criteria.strip()

    def get_full_text_rejection_criteria(self) -> str:
        return self.full_text_rejection_criteria.strip()
    
    # Digest distribution schedule
    digest_schedule = models.CharField(max_length=100, default="0 9 * * 5", help_text="Cron expression for weekly digest execution (e.g. every Friday at 9am)")
    ocr_provider = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        default=None,
        choices=[
            ("pypdf", "PyPDF (Fast Local Baseline)"),
            ("mistral", "Mistral OCR API"),
            ("gemini", "Gemini OCR (Google Gemini Flash Baseline)"),
            ("none", "None (Skip OCR Step)")
        ],
        help_text="OCR provider used for PDF layout extraction. Set to None or 'none' to skip Step 3 OCR."
    )
    screening_llm_model = models.CharField(max_length=100, default="google/gemini-3.7-flash", help_text="LLM model used for screening papers")
    llm_provider = models.CharField(
        max_length=50,
        default="google",
        choices=[("google", "Google Agent API"), ("openrouter", "OpenRouter")],
        help_text="LLM provider used for pipeline execution steps"
    )

    # Token & Budget quotas defined directly on the project/workspace level
    monthly_token_limit = models.BigIntegerField(default=10000000)
    tokens_in_consumed_this_month = models.BigIntegerField(default=0, help_text="Input/prompt tokens consumed this month")
    tokens_out_consumed_this_month = models.BigIntegerField(default=0, help_text="Output/completion tokens consumed this month")
    tokens_consumed_this_month = models.BigIntegerField(default=0, help_text="Total tokens consumed this month (in + out)")
    monthly_usd_limit = models.DecimalField(max_digits=10, decimal_places=2, default=100.00)
    usd_spent_this_month = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    
    # Agent & Pipeline Configuration
    skip_abstract_screening = models.BooleanField(default=False, help_text="If True, skips Step 4 Abstract Screening and performs direct Full-Text Screening")
    notification_email = models.EmailField(blank=True, null=True, help_text="Email address notified upon agent completion or failure")
    signal_score_code = models.TextField(
        blank=True, 
        null=True, 
        help_text="Custom Python snippet / function to compute paper signal score from extracted parameters in Step 6"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def record_token_usage(self, tokens_in: int, tokens_out: int, model_name: str = None):
        """
        Increments workspace monthly token and USD usage counters atomically.
        """
        from django.db.models import F
        from .llm_providers.pricing import calculate_llm_cost

        cost = calculate_llm_cost(model_name or self.screening_llm_model, tokens_in or 0, tokens_out or 0)
        total_tokens = (tokens_in or 0) + (tokens_out or 0)

        Workspace.objects.filter(pk=self.pk).update(
            tokens_in_consumed_this_month=F('tokens_in_consumed_this_month') + (tokens_in or 0),
            tokens_out_consumed_this_month=F('tokens_out_consumed_this_month') + (tokens_out or 0),
            tokens_consumed_this_month=F('tokens_consumed_this_month') + total_tokens,
            usd_spent_this_month=F('usd_spent_this_month') + cost
        )
        self.refresh_from_db(fields=[
            'tokens_in_consumed_this_month',
            'tokens_out_consumed_this_month',
            'tokens_consumed_this_month',
            'usd_spent_this_month'
        ])
        return cost

    def __str__(self):
        return self.name

class Subscriber(models.Model):
    """
    Represents a recipient of the weekly narrative reports and digests.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="subscribers")
    email = models.EmailField()
    name = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.email} ({self.workspace.name})"

class Scraper(models.Model):
    """
    Represents a data source scraper configuration configured for a specific workspace.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="scrapers")
    
    PROVIDER_CHOICES = [
        ('arxiv', 'arXiv'),
        ('openalex', 'OpenAlex'),
        ('lens', 'Lens.org'),
    ]
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES, help_text="Target API/database provider")
    search_query = models.TextField(help_text="Search query string or structured term parameter specific to this provider")
    limit = models.IntegerField(default=50, help_text="Max results to fetch for this scraper")
    sort_by = models.CharField(max_length=50, default="relevance", choices=[('relevance', 'Relevance'), ('date', 'Date')], help_text="Sorting criteria")
    sort_order = models.CharField(max_length=10, default="desc", choices=[('desc', 'Descending'), ('asc', 'Ascending')], help_text="Sort order")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.workspace.name} - {self.get_provider_display()} ({self.search_query[:30]})"

class ExtractionDefinition(models.Model):
    """
    Defines a dynamic extraction target (e.g. 'ML Methods') with its own prompts and schema.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="extraction_definitions")
    name = models.CharField(max_length=255, help_text="e.g. 'ML Methods', 'Business Models'")
    system_prompt = models.TextField(help_text="System instructions enforcing extraction perspective")
    user_prompt_template = models.TextField(help_text="User prompt with placeholders like {paper_text}")
    response_schema = models.JSONField(help_text="JSON schema describing fields to extract")
    exit_metric = models.CharField(max_length=100, blank=True, null=True, help_text="Field key to unpack from extracted data as the exit metric (e.g. 'fit_score', 'trl_score')")
    llm_model = models.CharField(max_length=100, default="google/gemini-3.7-flash", help_text="LLM model used for this specific extraction")
    version = models.IntegerField(default=1, help_text="Tracks prompt/schema evolution")
    requires_consensus = models.BooleanField(default=False, help_text="Requires multi-sample self-consistency for difficult fields")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def exit_metrics(self):
        return self.exit_metric

    @exit_metrics.setter
    def exit_metrics(self, value):
        self.exit_metric = value

    @property
    def exit_metric_key(self):
        return self.exit_metric

    @exit_metric_key.setter
    def exit_metric_key(self, value):
        self.exit_metric = value

    def __str__(self):
        return f"{self.workspace.name} - {self.name}"

class PipelineRun(models.Model):
    """
    Represents a specific scheduled execution run (e.g., weekly batch run).
    Groups papers, extractions, and digests generated for a new weekly dataset.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="runs")
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
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('aborted', 'Aborted')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="agent_processes")
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_processes")
    name = models.CharField(max_length=255, help_text="e.g. 'ArXiv Monthly Agent Ingestion'")

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    current_step = models.CharField(max_length=50, choices=STEP_CHOICES, default='initialized')

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_processes",
        help_text="User who launched this agent process"
    )

    # Runtime configuration and dynamic query modifiers
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
        ordering = ['-started_at', '-id']

    def __str__(self):
        return f"Agent '{self.name}' [{self.workspace.name}] ({self.status} - step: {self.current_step})"


class ComponentRun(models.Model):
    """
    Generalized component execution model tracking any step/job execution within a PipelineRun.
    Supports step types: 'scraping', 'download', 'ocr', 'screening', 'extraction', 'metrics', 'deep_research', 'reporting'.
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
        ordering = ['-started_at', '-id']

    def __str__(self):
        return f"{self.step_type}:{self.component_name} - Run {self.pipeline_run.id} ({self.status})"


class DocumentRegistry(models.Model):
    """
    Global, deduplicated document registry holding canonical binary storage references,
    OCR layout artifacts, and cross-workspace access metrics.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sha256_hash = models.CharField(max_length=64, unique=True, db_index=True, help_text="Global SHA-256 hash of PDF binary")
    doi = models.CharField(max_length=255, blank=True, null=True, db_index=True, help_text="Digital Object Identifier (DOI)")
    arxiv_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="arXiv repository ID")
    title = models.CharField(max_length=512)
    primary_source = models.CharField(max_length=50, default="arxiv", help_text="arxiv, openalex, lens, or pubmed")

    # Canonical Storage References
    canonical_pdf_path = models.CharField(max_length=512, blank=True, null=True, help_text="Storage key of canonical PDF binary")
    pdf_file_size_bytes = models.BigIntegerField(default=0, help_text="Size of PDF in bytes")

    # OCR Layout Cache
    ocr_provider = models.CharField(max_length=50, blank=True, null=True, help_text="OCR provider used (e.g. pypdf, mistral, gemini)")
    canonical_ocr_md_path = models.CharField(max_length=512, blank=True, null=True, help_text="Storage key of layout Markdown")

    # Lifetime Metrics
    access_count = models.PositiveIntegerField(default=1, help_text="Total times this document was accessed/reused across workspaces")
    first_ingested_at = models.DateTimeField(auto_now_add=True)
    last_accessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_accessed_at', '-id']
        indexes = [
            models.Index(fields=['doi']),
            models.Index(fields=['arxiv_id']),
            models.Index(fields=['sha256_hash']),
        ]

    def __str__(self):
        return f"{self.title[:50]} (Hits: {self.access_count})"


class Paper(models.Model):
    """
    Holds metadata, file references, and screening states for articles ingested during a specific run.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="papers")
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="papers", help_text="Ingestion run that fetched this paper")
    document_registry = models.ForeignKey(
        DocumentRegistry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paper_instances",
        help_text="Reference to global canonical document registry entry"
    )
    
    # Deduplication Keys
    hash_id = models.CharField(max_length=64, unique=True, help_text="SHA-256 hash of PDF or fallback unique hash to prevent duplicates")
    doi = models.CharField(max_length=255, blank=True, null=True, help_text="Digital Object Identifier (DOI)")
    arxiv_id = models.CharField(max_length=100, blank=True, null=True, help_text="arXiv repository ID")
    
    title = models.CharField(max_length=512)
    authors = models.TextField()
    abstract = models.TextField()
    source_database = models.CharField(max_length=50, help_text="arxiv, openalex, or lens")
    original_pdf_path = models.CharField(max_length=512, blank=True, null=True, help_text="S3 key of original PDF")
    converted_md_path = models.CharField(max_length=512, blank=True, null=True, help_text="S3 key of layout Markdown")
    
    screening_status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('abstract_passed', 'Abstract Passed'),
            ('full_text_passed', 'Full Text Passed'),
            ('borderline', 'Borderline (Human Review)'),
            ('rejected', 'Rejected'),
            ('withdrawn', 'Withdrawn by Authors')
        ],
        default='pending'
    )
    screening_reasoning = models.TextField(blank=True, null=True, help_text="Agent justification for screening action")
    
    # Evaluation Bootstrap Benchmark
    is_evaluation_benchmark = models.BooleanField(default=False, help_text="Flags whether a paper is part of the frozen labelled benchmark set")
    evaluation_label = models.CharField(
        max_length=50,
        choices=[('passed', 'Passed'), ('rejected', 'Rejected')],
        null=True,
        blank=True,
        help_text="Stores the ground-truth review decision made by the human analyst lead"
    )

    # Step 6: Signal Score
    signal_score = models.FloatField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Computed composite signal score from extraction parameters in Step 6"
    )
    signal_score_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed variable values and calculation audit for the signal score"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.title

class Extraction(models.Model):
    """
    Stores schema-validated claims, research parameters, technical attributes, or patent details.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="extractions")
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="extractions")
    extraction_definition = models.ForeignKey(
        ExtractionDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extractions"
    )
    category = models.CharField(max_length=50, help_text="e.g. ml_method, performance_metric, patent_claim")
    fields_data = models.JSONField(help_text="Extracted data containing value, evidence array, rationale, and confidence per field")
    is_hitl_validated = models.BooleanField(default=False)
    
    version_info = models.JSONField(default=dict, help_text="Stores prompt_version, schema_version, llm_model, provider")
    validation_status = models.CharField(
        max_length=50, 
        choices=[('pending', 'Pending'), ('pass', 'Pass'), ('warn', 'Warn'), ('fail', 'Fail')],
        default='pending'
    )
    review_required = models.BooleanField(default=False)
    confidence_score = models.FloatField(blank=True, null=True, help_text="Aggregate confidence score")
    confidence_method = models.CharField(max_length=50, blank=True, null=True, help_text="e.g. self_consistency, single_pass")
    
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def exit_metric(self) -> str:
        """
        Dynamically unpacks the exit metric value from fields_data using extraction_definition.exit_metric key
        with smart fallbacks for key variants and scalar values.
        """
        if self.fields_data and isinstance(self.fields_data, dict):
            data = self.fields_data
            if "fields" in data and isinstance(data["fields"], dict):
                data = data["fields"]

            # 1. Exact match on configured extraction_definition.exit_metric
            if self.extraction_definition and self.extraction_definition.exit_metric:
                exit_key = self.extraction_definition.exit_metric
                val = data.get(exit_key)
                if isinstance(val, dict) and "value" in val:
                    return str(val["value"])
                if val is not None:
                    return str(val)
                # Case-insensitive / snake_case lookup for the configured exit_key
                for k, v in data.items():
                    if k.lower().replace(" ", "_") == exit_key.lower().replace(" ", "_"):
                        if isinstance(v, dict) and "value" in v:
                            return str(v["value"])
                        elif v is not None:
                            return str(v)
                return "-"

            # 2. Case-insensitive / snake_case candidate keys when exit_metric not set
            candidates = []
            if self.extraction_definition:
                cand_name = self.extraction_definition.name.lower().replace(" ", "_")
                candidates.extend([cand_name, cand_name.replace("_extraction", ""), cand_name.replace("_score", "")])
            if self.category:
                cat_name = self.category.lower().replace(" ", "_")
                candidates.extend([cat_name, cat_name.replace("_extraction", "")])

            for ck in candidates:
                for k, v in data.items():
                    if k.lower().replace(" ", "_") == ck:
                        if isinstance(v, dict) and "value" in v:
                            return str(v["value"])
                        elif v is not None:
                            return str(v)

            # 3. First non-empty scalar value in fields_data (excluding long text / urls)
            for k, v in data.items():
                if isinstance(v, dict) and "value" in v:
                    return str(v["value"])
                elif isinstance(v, (int, float, bool)):
                    return str(v)
                elif isinstance(v, str) and len(v) < 80 and not v.startswith("http"):
                    return v

        return "-"

    def get_exit_metric(self) -> str:
        return self.exit_metric

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.paper.title[:30]}... ({self.category}): {self.exit_metric}"

class PaperMetric(models.Model):
    """
    Stores paper-level evaluations (TRL levels, graph-based importance indices, and citation facts).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="metrics")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="metrics")
    trl_score = models.IntegerField(blank=True, null=True, help_text="TRL scale score (1-9)")
    trl_reasoning = models.TextField(blank=True, null=True)
    trl_evidence = models.JSONField(default=list, blank=True, help_text="List of exact quotes supporting the TRL score")
    importance_score = models.FloatField(default=0.0, help_text="PageRank centrality score in cross-citations graph")
    importance_reasoning = models.TextField(blank=True, null=True)
    citation_count = models.IntegerField(default=0)
    venue_impact_factor = models.FloatField(default=0.0)
    h_index = models.IntegerField(default=0)
    signal_score = models.FloatField(blank=True, null=True, help_text="Calculated composite signal score")
    signal_score_details = models.JSONField(default=dict, blank=True, help_text="Calculation audit for signal score")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

class NarrativeReport(models.Model):
    """
    Stores compiled weekly briefs, LaTeX bibliographies, and critique refinement iterations per run.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="reports")
    pipeline_run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="reports", help_text="The ingestion run summarized by this report")
    title = models.CharField(max_length=255)
    content_markdown = models.TextField()
    content_latex = models.TextField(blank=True, null=True)
    bibtex_content = models.TextField(blank=True, null=True, help_text="BibTeX bibliography compilation")
    compiled_pdf_path = models.CharField(max_length=512, blank=True, null=True, help_text="S3 key to final PDF report")
    refinement_depth = models.IntegerField(default=1, help_text="The value of K reached in self-refinement critique loops")
    critic_score_history = models.JSONField(default=list, help_text="Trace log of scores and critiques per iteration")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

class HITLCorrection(models.Model):
    """
    Audits manual corrections and validation overrides made by domain experts.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extraction = models.ForeignKey(Extraction, on_delete=models.CASCADE, related_name="corrections")
    action = models.CharField(max_length=50, help_text="verify, modify, or reject")
    human_operator = models.CharField(max_length=255, help_text="Email or identifier of the scientist")
    original_value = models.JSONField(help_text="Extracted data before correction")
    corrected_value = models.JSONField(blank=True, null=True, help_text="Updated data after correction")
    reason = models.TextField(blank=True, null=True, help_text="Reasoning for override")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp', '-id']


class WorkspaceMember(models.Model):
    """
    Represents user membership and role assignments within a specific Workspace.
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('researcher', 'Researcher'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_memberships")
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='researcher')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('workspace', 'user')

    def __str__(self):
        return f"{self.user} - {self.workspace.name} ({self.role})"


class APIKey(models.Model):
    """
    MCP and REST Integration API Keys associated with specific users and workspaces.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Friendly label for the API Key")
    key_id = models.CharField(max_length=32, unique=True, help_text="Public API Key identifier")
    hashed_secret = models.CharField(max_length=128, help_text="SHA-256 hash of the API key secret")
    is_active = models.BooleanField(default=True)
    scopes = models.JSONField(
        default=list, 
        blank=True, 
        help_text="Granted scopes, e.g. ['scrapers:read', 'scrapers:write', 'workspaces:read', 'workspaces:write', 'prompts:read', 'prompts:write']"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mcp_api_keys")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="mcp_api_keys", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def generate_key(self):
        self.key_id = secrets.token_hex(8)
        raw_secret = secrets.token_urlsafe(32)
        self.hashed_secret = hashlib.sha256(raw_secret.encode()).hexdigest()
        return raw_secret

    def set_secret(self, raw_secret: str):
        self.hashed_secret = hashlib.sha256(raw_secret.encode()).hexdigest()

    def check_secret(self, raw_secret: str) -> bool:
        return self.hashed_secret == hashlib.sha256(raw_secret.encode()).hexdigest()

    def update_last_used(self):
        from django.utils import timezone
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])

    def __str__(self):
        return f"{self.name} ({self.key_id})"


class UserActivityLog(models.Model):
    """
    Immutable audit log capturing user actions across FastMCP tools and REST API endpoints.
    Preserves historical traceability even after User or Workspace deletion via denormalized fields.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Foreign keys (SET_NULL on deletion to maintain audit record)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    workspace = models.ForeignKey(Workspace, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    
    # Denormalized historical strings (Preserved even if user/workspace row is deleted!)
    user_username = models.CharField(max_length=255, blank=True, help_text="Historical username at action execution")
    user_email = models.CharField(max_length=255, blank=True, help_text="Historical email at action execution")
    workspace_name = models.CharField(max_length=255, blank=True, help_text="Historical workspace name at action execution")
    
    # Action Metadata
    interface = models.CharField(max_length=50, help_text="'mcp' or 'rest_api'")
    action_name = models.CharField(max_length=255, help_text="e.g. 'start_research_agent', 'POST /api/agents/'")
    status = models.CharField(max_length=50, default="success", help_text="'success', 'failed', 'unauthorized'")
    
    # Payloads & Execution Trace
    input_params = models.JSONField(blank=True, null=True, help_text="Parameters / request body sent by user")
    output_summary = models.JSONField(blank=True, null=True, help_text="Response payload or summary returned")
    error_message = models.TextField(blank=True, null=True, help_text="Error traceback or failure reason if status != success")
    execution_time_ms = models.FloatField(default=0.0, help_text="Duration of operation in milliseconds")
    
    # Client Context
    api_key_id = models.CharField(max_length=255, blank=True, null=True, help_text="MCP API Key ID used")
    ip_address = models.CharField(max_length=100, blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True, null=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['interface', 'action_name']),
            models.Index(fields=['status']),
        ]

    @classmethod
    def log_action(
        cls,
        user=None,
        workspace=None,
        interface: str = "mcp",
        action_name: str = "",
        status: str = "success",
        input_params: dict = None,
        output_summary: dict = None,
        error_message: str = None,
        execution_time_ms: float = 0.0,
        api_key_id: str = None,
        ip_address: str = None,
        user_agent: str = None
    ):
        """Helper factory creating UserActivityLog entries with automatic workspace resolution and denormalization."""
        # 1. Resolve Workspace if passed directly as Workspace instance or UUID/str
        ws_obj = None
        if isinstance(workspace, Workspace):
            ws_obj = workspace
        elif isinstance(workspace, (str, uuid.UUID)):
            try:
                ws_obj = Workspace.objects.filter(id=workspace).first()
            except Exception:
                ws_obj = None

        # 2. Intelligent workspace resolution from input_params / kwargs
        if not ws_obj and isinstance(input_params, dict):
            try:
                ws_val = input_params.get('workspace_id') or input_params.get('workspace')
                if ws_val:
                    if isinstance(ws_val, Workspace):
                        ws_obj = ws_val
                    else:
                        ws_obj = Workspace.objects.filter(id=ws_val).first()

                if not ws_obj and input_params.get('pipeline_run_id'):
                    pr = PipelineRun.objects.filter(id=input_params['pipeline_run_id']).select_related('workspace').first()
                    if pr:
                        ws_obj = pr.workspace

                if not ws_obj and (input_params.get('process_id') or input_params.get('agent_process_id')):
                    p_id = input_params.get('process_id') or input_params.get('agent_process_id')
                    proc = ResearchAgentProcess.objects.filter(id=p_id).select_related('workspace').first()
                    if proc:
                        ws_obj = proc.workspace

                if not ws_obj and input_params.get('paper_id'):
                    paper = Paper.objects.filter(id=input_params['paper_id']).select_related('workspace').first()
                    if paper:
                        ws_obj = paper.workspace

                if not ws_obj and input_params.get('scraper_id'):
                    scraper = Scraper.objects.filter(id=input_params['scraper_id']).select_related('workspace').first()
                    if scraper:
                        ws_obj = scraper.workspace

                if not ws_obj and input_params.get('definition_id'):
                    ext_def = ExtractionDefinition.objects.filter(id=input_params['definition_id']).select_related('workspace').first()
                    if ext_def:
                        ws_obj = ext_def.workspace

                if not ws_obj and input_params.get('extraction_id'):
                    ext = Extraction.objects.filter(id=input_params['extraction_id']).select_related('workspace').first()
                    if ext:
                        ws_obj = ext.workspace

                if not ws_obj and input_params.get('component_run_id'):
                    cr = ComponentRun.objects.filter(id=input_params['component_run_id']).select_related('pipeline_run__workspace').first()
                    if cr and cr.pipeline_run:
                        ws_obj = cr.pipeline_run.workspace
            except Exception:
                pass

        # 3. Intelligent workspace resolution from output_summary (e.g. create_workspace returns workspace_id)
        if not ws_obj and isinstance(output_summary, dict):
            try:
                out_ws = output_summary.get('workspace_id') or output_summary.get('workspace')
                if not out_ws and action_name in ('create_workspace', 'POST /api/workspaces/'):
                    out_ws = output_summary.get('id')
                if out_ws:
                    ws_obj = Workspace.objects.filter(id=out_ws).first()
            except Exception:
                pass

        # 4. Intelligent workspace resolution from REST API URL path (e.g. /api/workspaces/<uuid>/)
        if not ws_obj and action_name:
            try:
                import re
                uuid_match = re.search(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', action_name)
                if uuid_match:
                    matched_id = uuid_match.group(0)
                    if '/workspaces/' in action_name:
                        ws_obj = Workspace.objects.filter(id=matched_id).first()
                    elif '/agents/' in action_name:
                        proc = ResearchAgentProcess.objects.filter(id=matched_id).select_related('workspace').first()
                        if proc:
                            ws_obj = proc.workspace
                    elif '/pipeline-runs/' in action_name:
                        pr = PipelineRun.objects.filter(id=matched_id).select_related('workspace').first()
                        if pr:
                            ws_obj = pr.workspace
                    elif '/extractions/' in action_name:
                        ext = Extraction.objects.filter(id=matched_id).select_related('workspace').first()
                        if ext:
                            ws_obj = ext.workspace
            except Exception:
                pass

        username = getattr(user, 'username', '') if user else ''
        email = getattr(user, 'email', '') if user else ''
        ws_name = getattr(ws_obj, 'name', '') if ws_obj else ''

        logger.info(
            f"📝 [USER ACTIVITY LOG] [{interface.upper()}] {action_name} | "
            f"User: '{username or 'Anonymous'}' ({email or 'N/A'}) | "
            f"Workspace: '{ws_name or 'N/A'}' | "
            f"Status: {status.upper()} ({execution_time_ms:.1f}ms)"
        )

        return cls.objects.create(
            user=user,
            workspace=ws_obj,
            user_username=username,
            user_email=email,
            workspace_name=ws_name,
            interface=interface,
            action_name=action_name,
            status=status,
            input_params=input_params,
            output_summary=output_summary,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            api_key_id=api_key_id,
            ip_address=ip_address,
            user_agent=user_agent
        )

    def __str__(self):
        user_str = self.user_username or (str(self.user) if self.user else "Anonymous")
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {user_str} executed {self.action_name} ({self.status})"



