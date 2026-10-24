import uuid
from django.db import models
from django.conf import settings


class ScreeningReview(models.Model):
    """
    Single blind evaluation by a human reviewer for a sampled paper.
    Under blind dual-review, annotators cannot inspect peer votes or AI reasoning
    prior to submitting their assessment.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample_cohort = models.ForeignKey(
        'slr_review.AuditSampleCohort',
        on_delete=models.CASCADE,
        related_name='screening_reviews'
    )
    paper = models.ForeignKey(
        'research_intelligence.Paper',
        on_delete=models.CASCADE,
        related_name='slr_screening_reviews'
    )
    pipeline_run = models.ForeignKey(
        'research_intelligence.PipelineRun',
        on_delete=models.CASCADE,
        related_name='slr_screening_reviews'
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='slr_reviews_submitted'
    )

    STAGE_CHOICES = [
        ('abstract', 'Abstract Screening'),
        ('full_text', 'Full-Text Screening'),
    ]
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, db_index=True)

    DECISION_CHOICES = [
        ('include', 'Include (Eligible)'),
        ('exclude', 'Exclude (Ineligible)'),
        ('uncertain', 'Uncertain (Flag for Second Opinion)'),
    ]
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, db_index=True)

    exclusion_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Standardized rejection category selected from workspace taxonomy."
    )

    # Verbatim Evidence Provenance
    evidence_quotes = models.JSONField(
        default=list,
        blank=True,
        help_text="Structured quotes supporting the decision (quote, page_number, section, annotation_type)."
    )

    reviewer_notes = models.TextField(blank=True, null=True, help_text="Qualitative notes or remarks.")
    time_spent_seconds = models.PositiveIntegerField(null=True, blank=True, help_text="Audit duration in seconds.")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('sample_cohort', 'paper', 'reviewer', 'stage')
        indexes = [
            models.Index(fields=['sample_cohort', 'stage', 'decision']),
            models.Index(fields=['paper', 'reviewer']),
        ]
        verbose_name = "Screening Review"
        verbose_name_plural = "Screening Reviews"

    def __str__(self):
        paper_title = getattr(self.paper, 'title', str(self.paper_id))
        return f"{self.reviewer} -> {paper_title[:30]} [{self.decision.upper()}] ({self.stage})"
