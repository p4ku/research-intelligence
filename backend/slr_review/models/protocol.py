import uuid
from django.db import models
from django.conf import settings


class SLRProtocol(models.Model):
    """
    Formal Systematic Review Protocol.
    Captures research questions, PICO criteria, inclusion/exclusion rules,
    and PROSPERO trial registry identifiers with immutable version locking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'research_intelligence.Workspace',
        on_delete=models.CASCADE,
        related_name='slr_protocols'
    )
    title = models.CharField(max_length=512, help_text="Formal systematic review title.")
    review_question = models.TextField(help_text="Primary research question / hypothesis.")

    # Structured PICO / PECO Criteria
    pico_population = models.TextField(help_text="Target population / clinical condition.")
    pico_intervention = models.TextField(help_text="Intervention or exposure under review.")
    pico_comparison = models.TextField(help_text="Control / comparator group (placebo, standard of care).")
    pico_outcome = models.TextField(help_text="Primary and secondary endpoints / measurements.")
    study_design_criteria = models.TextField(
        blank=True,
        help_text="Eligible study types (e.g. 'RCTs, prospective cohorts; exclude case reports')."
    )

    # Registry & Immutability Governance
    prospero_registration_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="e.g. CRD42026123456 (PROSPERO registration token)."
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="When True, criteria are read-only. Changes require a formal amendment."
    )
    version = models.PositiveIntegerField(default=1)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='slr_protocols_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-version', '-created_at']
        verbose_name = "SLR Protocol"
        verbose_name_plural = "SLR Protocols"

    def __str__(self):
        return f"{self.title} (v{self.version}) - {'LOCKED' if self.is_locked else 'DRAFT'}"


class ProtocolAmendment(models.Model):
    """
    Tracks post-registration protocol revisions for PROSPERO / OSF compliance.
    Created whenever a locked protocol undergoes formal methodological modifications.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    protocol = models.ForeignKey(
        SLRProtocol,
        on_delete=models.CASCADE,
        related_name='amendments'
    )
    amendment_number = models.PositiveIntegerField(help_text="Sequential amendment index (1, 2, ...)")
    rationale = models.TextField(help_text="Detailed scientific justification for amending criteria.")
    changes_diff = models.JSONField(
        default=dict,
        help_text="Structured before/after diff of modified PICO fields or eligibility criteria."
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='slr_protocol_amendments',
        help_text="Senior researcher or PI approving this formal amendment."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['amendment_number', 'created_at']
        unique_together = ('protocol', 'amendment_number')
        verbose_name = "Protocol Amendment"
        verbose_name_plural = "Protocol Amendments"

    def __str__(self):
        return f"Amendment #{self.amendment_number} for {self.protocol.title[:30]}"
