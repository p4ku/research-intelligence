import uuid
import logging
from django.db import models

logger = logging.getLogger(__name__)


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
        app_label = 'research_intelligence'
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
    workspace = models.ForeignKey('Workspace', on_delete=models.CASCADE, related_name="papers")
    pipeline_run = models.ForeignKey('PipelineRun', on_delete=models.CASCADE, related_name="papers", help_text="Ingestion run that fetched this paper")
    document_registry = models.ForeignKey(
        DocumentRegistry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paper_instances",
        help_text="Reference to global canonical document registry entry"
    )
    
    # Deduplication Keys (scoped per workspace)
    hash_id = models.CharField(max_length=64, db_index=True, help_text="SHA-256 hash of PDF or fallback unique hash to prevent duplicates within a workspace")
    doi = models.CharField(max_length=255, blank=True, null=True, db_index=True, help_text="Digital Object Identifier (DOI)")
    arxiv_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="arXiv repository ID")
    
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
            ('accepted', 'Accepted'),
            ('borderline', 'Borderline (Human Review)'),
            ('rejected', 'Rejected'),
            ('withdrawn', 'Withdrawn by Authors')
        ],
        default='pending',
        db_index=True
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
        app_label = 'research_intelligence'
        ordering = ['-created_at', '-id']
        unique_together = ('workspace', 'hash_id')
        indexes = [
            models.Index(fields=['workspace', 'screening_status']),
            models.Index(fields=['pipeline_run', 'screening_status']),
            models.Index(fields=['workspace', '-created_at']),
            models.Index(fields=['pipeline_run', '-created_at']),
            models.Index(fields=['workspace', 'hash_id']),
            models.Index(fields=['doi']),
            models.Index(fields=['arxiv_id']),
            models.Index(fields=['hash_id']),
        ]

    def __str__(self):
        return self.title


class PaperMetric(models.Model):
    """
    Stores paper-level evaluations, dynamic metric dictionaries, and composite signal scores
    evaluated per pipeline run.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="metrics")
    pipeline_run = models.ForeignKey(
        'PipelineRun',
        on_delete=models.CASCADE,
        related_name="paper_metrics",
        blank=True,
        null=True,
        help_text="PipelineRun during which these metrics were evaluated"
    )
    workspace = models.ForeignKey('Workspace', on_delete=models.CASCADE, related_name="metrics")
    
    # Composite Signal Score
    signal_score = models.FloatField(blank=True, null=True, db_index=True, help_text="Calculated composite signal score")
    signal_score_details = models.JSONField(default=dict, blank=True, help_text="Calculation audit for signal score")
    
    # Dynamic Metrics Payload (all extracted parameters e.g. trl, fit_score, novelty, custom criteria)
    metrics_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dynamic dictionary of computed metrics, extracted parameters, and evaluation attributes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-created_at', '-id']
        unique_together = ('paper', 'pipeline_run')
        indexes = [
            models.Index(fields=['workspace', '-signal_score']),
            models.Index(fields=['pipeline_run', '-signal_score']),
            models.Index(fields=['paper', '-created_at']),
        ]

    def __str__(self):
        score_str = f"{self.signal_score:.2f}" if self.signal_score is not None else "-"
        pr_str = str(self.pipeline_run_id)[:8] if self.pipeline_run_id else "global"
        return f"{self.paper.title[:30]}... (Run: {pr_str} | Score: {score_str})"
