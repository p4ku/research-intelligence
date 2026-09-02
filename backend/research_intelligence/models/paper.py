import uuid
import logging
from django.db import models
from django.utils import timezone

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


class PaperQuerySet(models.QuerySet):
    """
    QuerySet that transparently maps legacy filter parameters (pipeline_run, reprocessed_runs,
    screening_status) to the PaperMetric association table.
    """
    def _filter_or_exclude(self, negate, args, kwargs):
        new_kwargs = {}
        for k, v in kwargs.items():
            if k == 'pipeline_run':
                new_kwargs['metrics__pipeline_run'] = v
            elif k == 'pipeline_run_id':
                new_kwargs['metrics__pipeline_run_id'] = v
            elif k.startswith('pipeline_run__'):
                new_kwargs['metrics__' + k] = v
            elif k in ('reprocessed_runs', 'reprocessed_runs__id'):
                new_kwargs['metrics__pipeline_run_id'] = getattr(v, 'id', v)
            elif k.startswith('reprocessed_runs__'):
                new_kwargs['metrics__pipeline_run__' + k[len('reprocessed_runs__'):]] = v
            elif k == 'screening_status':
                new_kwargs['metrics__screening_status'] = v
            elif k == 'screening_status__in':
                new_kwargs['metrics__screening_status__in'] = v
            elif k == 'screening_reasoning':
                new_kwargs['metrics__screening_reasoning'] = v
            elif k == 'abstract_screening_reasoning':
                new_kwargs['metrics__abstract_screening_reasoning'] = v
            elif k == 'full_text_screening_reasoning':
                new_kwargs['metrics__full_text_screening_reasoning'] = v
            elif k == 'signal_score':
                new_kwargs['metrics__signal_score'] = v
            elif k == 'signal_score__isnull':
                new_kwargs['metrics__signal_score__isnull'] = v
            else:
                new_kwargs[k] = v
        return super()._filter_or_exclude(negate, args, new_kwargs)


class PaperManager(models.Manager.from_queryset(PaperQuerySet)):
    """
    Paper manager supporting graceful creation with optional pipeline_run
    and screening parameters, automatically maintaining PaperMetric.
    """
    def create(self, **kwargs):
        pipeline_run = kwargs.pop('pipeline_run', None) or kwargs.pop('pipeline_run_id', None)
        reprocessed_runs = kwargs.pop('reprocessed_runs', None)
        screening_status = kwargs.pop('screening_status', None)
        screening_reasoning = kwargs.pop('screening_reasoning', None)
        abstract_screening_reasoning = kwargs.pop('abstract_screening_reasoning', None)
        full_text_screening_reasoning = kwargs.pop('full_text_screening_reasoning', None)
        signal_score = kwargs.pop('signal_score', None)
        signal_score_details = kwargs.pop('signal_score_details', None)
        is_evaluation_benchmark = kwargs.pop('is_evaluation_benchmark', None)
        evaluation_label = kwargs.pop('evaluation_label', None)
        metrics_data = kwargs.pop('metrics_data', None)

        paper = super().create(**kwargs)

        if pipeline_run is not None:
            pr_id = getattr(pipeline_run, 'id', pipeline_run)
            defaults = {
                'workspace': paper.workspace,
                'screening_status': screening_status or 'pending',
                'screening_reasoning': screening_reasoning,
                'abstract_screening_reasoning': abstract_screening_reasoning,
                'full_text_screening_reasoning': full_text_screening_reasoning,
                'signal_score': signal_score,
                'signal_score_details': signal_score_details or {},
                'is_evaluation_benchmark': bool(is_evaluation_benchmark) if is_evaluation_benchmark is not None else False,
                'evaluation_label': evaluation_label,
                'metrics_data': metrics_data or {}
            }
            PaperMetric.objects.update_or_create(
                paper=paper,
                pipeline_run_id=pr_id,
                defaults=defaults
            )

        if reprocessed_runs:
            for r_run in reprocessed_runs:
                r_id = getattr(r_run, 'id', r_run)
                PaperMetric.objects.get_or_create(
                    paper=paper,
                    pipeline_run_id=r_id,
                    defaults={'workspace': paper.workspace, 'screening_status': 'pending'}
                )

        return paper


class Paper(models.Model):
    """
    Holds metadata, file references, and canonical identifiers for articles ingested in a workspace.
    Pipeline-specific screening states, evaluations, and composite signal scores are maintained per-run in PaperMetric.
    """
    objects = PaperManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('Workspace', on_delete=models.CASCADE, related_name="papers")
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
    
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def pipeline_run(self):
        """Returns the initial / origin PipelineRun for this paper."""
        if hasattr(self, '_pipeline_run') and self._pipeline_run is not None:
            return self._pipeline_run
        if hasattr(self, '_prefetched_objects_cache') and 'metrics' in self._prefetched_objects_cache:
            m_list = list(self.metrics.all())
            if m_list:
                initial_metric = min(m_list, key=lambda m: (m.created_at or timezone.now(), str(m.id)))
                return initial_metric.pipeline_run
            return None
        initial_metric = self.metrics.order_by('created_at').first()
        return initial_metric.pipeline_run if initial_metric else None

    @pipeline_run.setter
    def pipeline_run(self, val):
        self._pipeline_run = val

    @property
    def latest_pipeline_run(self):
        """Returns the most recent PipelineRun that evaluated this paper."""
        if hasattr(self, '_prefetched_objects_cache') and 'metrics' in self._prefetched_objects_cache:
            m_list = list(self.metrics.all())
            if m_list:
                latest_metric = max(m_list, key=lambda m: (m.created_at or timezone.now(), str(m.id)))
                return latest_metric.pipeline_run
            return None
        latest_metric = self.metrics.order_by('-created_at').first()
        return latest_metric.pipeline_run if latest_metric else None

    @property
    def pipeline_run_id(self):
        if hasattr(self, 'annotated_pipeline_run_id') and self.annotated_pipeline_run_id is not None:
            return self.annotated_pipeline_run_id
        pr = self.pipeline_run
        return pr.id if pr else None

    @property
    def reprocessed_runs(self):
        class _ReprocessedRunsShim:
            def __init__(self, paper):
                self.paper = paper
            def all(self):
                from .pipeline import PipelineRun
                return PipelineRun.objects.filter(paper_metrics__paper=self.paper).distinct()
            def add(self, *runs):
                for run in runs:
                    r_id = getattr(run, 'id', run)
                    PaperMetric.objects.get_or_create(
                        paper=self.paper,
                        pipeline_run_id=r_id,
                        defaults={'workspace': self.paper.workspace, 'screening_status': 'pending'}
                    )
            def filter(self, *args, **kwargs):
                return self.all().filter(*args, **kwargs)
        return _ReprocessedRunsShim(self)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-created_at', '-id']
        unique_together = ('workspace', 'hash_id')
        indexes = [
            models.Index(fields=['workspace', '-created_at']),
            models.Index(fields=['workspace', 'hash_id']),
            models.Index(fields=['doi']),
            models.Index(fields=['arxiv_id']),
            models.Index(fields=['hash_id']),
        ]

    def __str__(self):
        return self.title


class PaperMetricManager(models.Manager):
    """
    Ensures that calls to PaperMetric.objects.create(paper=..., pipeline_run=...)
    safely update or create the metric record without violating the unique constraint,
    and automatically infers workspace from paper or pipeline_run if not provided.
    """
    def create(self, **kwargs):
        paper = kwargs.get('paper') or kwargs.get('paper_id')
        pipeline_run = kwargs.get('pipeline_run') or kwargs.get('pipeline_run_id')
        workspace = kwargs.get('workspace') or kwargs.get('workspace_id')
        if not workspace:
            if hasattr(paper, 'workspace'):
                workspace = paper.workspace
            elif hasattr(pipeline_run, 'workspace'):
                workspace = pipeline_run.workspace
            elif paper:
                from .paper import Paper
                ws_id = Paper.objects.filter(pk=getattr(paper, 'id', paper)).values_list('workspace_id', flat=True).first()
                if ws_id:
                    workspace = ws_id

        if paper and pipeline_run:
            paper_id = getattr(paper, 'id', paper)
            pipeline_run_id = getattr(pipeline_run, 'id', pipeline_run)
            clean_kwargs = {k: v for k, v in kwargs.items() if k not in ('paper', 'paper_id', 'pipeline_run', 'pipeline_run_id')}
            if 'workspace' not in clean_kwargs and 'workspace_id' not in clean_kwargs and workspace:
                clean_kwargs['workspace'] = workspace
            obj, _ = self.update_or_create(
                paper_id=paper_id,
                pipeline_run_id=pipeline_run_id,
                defaults=clean_kwargs
            )
            return obj

        if 'workspace' not in kwargs and 'workspace_id' not in kwargs and workspace:
            kwargs['workspace'] = workspace
        return super().create(**kwargs)


class PaperMetric(models.Model):
    """
    Stores paper-level evaluations, screening statuses, dynamic metric dictionaries,
    and composite signal scores evaluated per pipeline run.
    """
    objects = PaperMetricManager()

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
    
    # Screening and Review Decisions (Scoped strictly per pipeline_run)
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
        db_index=True,
        help_text="Review decision for this paper within this pipeline run"
    )
    screening_reasoning = models.TextField(blank=True, null=True, help_text="Agent justification for screening action in this run")
    abstract_screening_reasoning = models.TextField(blank=True, null=True, help_text="Agent justification for abstract screening decision in this run")
    full_text_screening_reasoning = models.TextField(blank=True, null=True, help_text="Agent justification for full-text screening decision in this run")
    is_evaluation_benchmark = models.BooleanField(default=False, help_text="Flags whether this paper evaluation is part of the benchmark set for this run")
    evaluation_label = models.CharField(
        max_length=50,
        choices=[('passed', 'Passed'), ('rejected', 'Rejected')],
        null=True,
        blank=True,
        help_text="Ground-truth review decision"
    )

    # Composite Signal Score
    signal_score = models.FloatField(blank=True, null=True, db_index=True, help_text="Calculated composite signal score")
    signal_score_details = models.JSONField(default=dict, blank=True, help_text="Calculation audit for signal score")
    metrics_data = models.JSONField(default=dict, blank=True, help_text="Dictionary of extracted and calculated variables used for scoring")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'research_intelligence'
        unique_together = ('paper', 'pipeline_run')
        indexes = [
            models.Index(fields=['pipeline_run', 'screening_status']),
            models.Index(fields=['workspace', 'screening_status']),
            models.Index(fields=['paper', '-created_at']),
            models.Index(fields=['pipeline_run', '-signal_score']),
            models.Index(fields=['workspace', '-signal_score']),
        ]
        ordering = ['-created_at', '-id']

    def __str__(self):
        score_str = f"{self.signal_score:.2f}" if self.signal_score is not None else "-"
        pr_str = str(self.pipeline_run_id)[:8] if self.pipeline_run_id else "global"
        return f"{self.paper.title[:30]}... (Run: {pr_str} | Score: {score_str})"
