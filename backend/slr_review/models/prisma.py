import uuid
from django.db import models


class SLRPRISMAMetrics(models.Model):
    """
    Maintains computed PRISMA 2020 statement counts and statistical inter-rater
    agreement metrics (Cohen's Kappa) for a specific systematic review run.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline_run = models.OneToOneField(
        'research_intelligence.PipelineRun',
        on_delete=models.CASCADE,
        related_name='slr_prisma_metrics'
    )

    # 1. PRISMA: Identification
    records_identified_total = models.PositiveIntegerField(default=0)
    records_by_source = models.JSONField(
        default=dict,
        help_text="Records identified per database (e.g. {'pubmed': 420, 'openalex': 610, 'arxiv': 150})"
    )
    duplicates_removed = models.PositiveIntegerField(default=0)

    # 2. PRISMA: Screening (Title / Abstract)
    records_screened_abstract = models.PositiveIntegerField(default=0)
    records_excluded_abstract = models.PositiveIntegerField(default=0)
    abstract_exclusion_reasons = models.JSONField(
        default=dict,
        help_text="Breakdown of rejection reasons at abstract stage (e.g. {'Non-English': 45, 'Wrong Topic': 320})"
    )

    # 3. PRISMA: Eligibility (Full-Text)
    full_text_assessed = models.PositiveIntegerField(default=0)
    full_text_excluded = models.PositiveIntegerField(default=0)
    full_text_exclusion_reasons = models.JSONField(
        default=dict,
        help_text="Detailed exclusion reasons for full-text candidates (e.g. {'No Control Group': 18})"
    )

    # 4. PRISMA: Included Studies
    studies_included_synthesis = models.PositiveIntegerField(default=0)
    studies_included_meta_analysis = models.PositiveIntegerField(default=0)

    # 5. Scientific Reliability Metrics
    human_inter_rater_kappa = models.FloatField(
        null=True,
        blank=True,
        help_text="Cohen's Kappa (κ) between Reviewer 1 and Reviewer 2 (0.0 to 1.0)."
    )
    ai_vs_human_kappa = models.FloatField(
        null=True,
        blank=True,
        help_text="Cohen's Kappa (κ) between AI agent decisions and Human Consensus ground-truth."
    )
    ai_sensitivity = models.FloatField(
        null=True,
        blank=True,
        help_text="AI Recall / Sensitivity (Proportion of truly eligible studies correctly included by AI)."
    )
    ai_specificity = models.FloatField(
        null=True,
        blank=True,
        help_text="AI Specificity (Proportion of irrelevant studies correctly rejected by AI)."
    )

    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "PRISMA 2020 Metrics"
        verbose_name_plural = "PRISMA 2020 Metrics"

    def __str__(self):
        pr_id = getattr(self.pipeline_run, 'id', self.pipeline_run_id)
        return f"PRISMA Run {str(pr_id)[:8]}: {self.studies_included_synthesis} Studies Included"
