import uuid
from django.db import models
from django.conf import settings


class AdjudicationDispute(models.Model):
    """
    Formed automatically when independent human reviews split on a paper
    (e.g. Reviewer 1 voted 'Include', Reviewer 2 voted 'Exclude').
    Escalates to the Senior Arbiter with side-by-side evidence quotes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample_cohort = models.ForeignKey(
        'slr_review.AuditSampleCohort',
        on_delete=models.CASCADE,
        related_name='disputes',
        help_text="Audit cohort where the split review occurred."
    )
    paper = models.ForeignKey(
        'research_intelligence.Paper',
        on_delete=models.CASCADE,
        related_name='slr_disputes',
        help_text="Contested research paper."
    )
    stage = models.CharField(
        max_length=20,
        choices=[('abstract', 'Abstract'), ('full_text', 'Full-Text')],
        help_text="Screening stage where the conflict arose."
    )

    STATUS_CHOICES = [
        ('pending', 'Pending Senior Adjudication'),
        ('resolved', 'Resolved by Arbiter'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)

    # Arbiter Rulings
    arbiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='slr_disputes_resolved',
        help_text="Designated Senior Arbiter who issued the ruling."
    )
    final_decision = models.CharField(
        max_length=20,
        choices=[('include', 'Include'), ('exclude', 'Exclude')],
        null=True,
        blank=True,
        help_text="Binding final decision on eligibility."
    )
    final_exclusion_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Exclusion reason applied if paper is ruled Exclude."
    )
    resolution_rationale = models.TextField(
        blank=True,
        null=True,
        help_text="Detailed explanation of the arbiter's binding ruling."
    )

    # Aggregated Side-by-Side Evidence Comparison Matrix
    evidence_synthesis = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Structured side-by-side evidence comparison:
        {
            "reviewer_1": {"decision": "include", "quotes": [...]},
            "reviewer_2": {"decision": "exclude", "reason": "Animal Model", "quotes": [...]},
            "ai_agent": {"decision": "rejected", "confidence": 0.88, "reasoning": "..."}
        }
        """
    )

    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['status', '-created_at']
        verbose_name = "Adjudication Dispute"
        verbose_name_plural = "Adjudication Disputes"

    def __str__(self):
        paper_title = getattr(self.paper, 'title', str(self.paper_id))
        return f"Dispute on {paper_title[:30]} - Status: {self.status.upper()}"
