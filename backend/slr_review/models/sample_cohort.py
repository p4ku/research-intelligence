import uuid
from django.db import models


class AuditSampleCohort(models.Model):
    """
    Represents a discrete batch of sampled papers generated when a pipeline run
    reaches an audit checkpoint gate (Abstract, Full-Text, or Extraction).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey(
        'slr_review.SLRWorkspaceConfig',
        on_delete=models.CASCADE,
        related_name='audit_cohorts',
        help_text="Workspace policy configuration governing this cohort."
    )
    pipeline_run = models.ForeignKey(
        'research_intelligence.PipelineRun',
        on_delete=models.CASCADE,
        related_name='slr_audit_cohorts',
        help_text="Pipeline execution run that generated this audit batch."
    )

    STAGE_CHOICES = [
        ('abstract_screening', 'Abstract Screening Gate'),
        ('full_text_screening', 'Full-Text Screening Gate'),
        ('parameter_extraction', 'Parameter Extraction Gate'),
    ]
    stage = models.CharField(max_length=30, choices=STAGE_CHOICES, db_index=True)

    total_pool_count = models.PositiveIntegerField(help_text="Total eligible papers at this stage.")
    sampled_count = models.PositiveIntegerField(help_text="Actual count of papers sampled for human audit.")
    sampling_strategy = models.JSONField(
        default=dict,
        help_text="Detailed sampling parameters (percentage, uncertainty cutoff, random seed)."
    )

    # M2M relationship to sampled papers
    sampled_papers = models.ManyToManyField(
        'research_intelligence.Paper',
        related_name='slr_audit_cohorts',
        blank=True
    )

    is_audit_complete = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Flips to True once all sampled papers satisfy quorum and dispute resolution."
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Audit Sample Cohort"
        verbose_name_plural = "Audit Sample Cohorts"

    def __str__(self):
        return f"Cohort {str(self.id)[:8]} ({self.stage}) - {self.sampled_count}/{self.total_pool_count} papers"
