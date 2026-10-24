import uuid
from django.db import models
from django.conf import settings


class ExtractionReview(models.Model):
    """
    Audits and validates AI-extracted parameters and evidence quotes
    during Gate 2 (Extraction Audit Gate).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample_cohort = models.ForeignKey(
        'slr_review.AuditSampleCohort',
        on_delete=models.CASCADE,
        related_name='extraction_reviews',
        help_text="Extraction audit cohort (e.g. 10 sampled papers out of 50)."
    )
    paper = models.ForeignKey(
        'research_intelligence.Paper',
        on_delete=models.CASCADE,
        related_name='slr_extraction_reviews'
    )
    extraction = models.ForeignKey(
        'research_intelligence.Extraction',
        on_delete=models.CASCADE,
        related_name='slr_audit_reviews'
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='slr_extractions_reviewed'
    )

    ACTION_CHOICES = [
        ('verify', 'Verify (Confirmed AI is 100% correct)'),
        ('modify', 'Modify (Corrected values or quotes)'),
        ('reject', 'Reject (Hallucinated / Not Reported in text)'),
    ]
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='verify', db_index=True)

    # Audited Data & Provenance
    original_fields = models.JSONField(help_text="Snapshot of raw AI extraction output.")
    corrected_fields = models.JSONField(
        blank=True,
        null=True,
        help_text="Human-corrected parameter values (if action == 'modify')."
    )
    verified_evidence_quotes = models.JSONField(
        default=list,
        blank=True,
        help_text="Human-verified or updated verbatim quotes and page numbers."
    )

    reviewer_notes = models.TextField(blank=True, null=True, help_text="Contextual notes explaining changes.")
    time_spent_seconds = models.PositiveIntegerField(null=True, blank=True, help_text="Audit duration in seconds.")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('sample_cohort', 'extraction', 'reviewer')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['sample_cohort', 'action']),
            models.Index(fields=['paper', 'reviewer']),
        ]
        verbose_name = "Extraction Review"
        verbose_name_plural = "Extraction Reviews"

    def __str__(self):
        cat = getattr(self.extraction, 'category', 'Extraction') if self.extraction else 'Extraction'
        return f"{self.reviewer} -> {cat} [{self.action.upper()}]"
