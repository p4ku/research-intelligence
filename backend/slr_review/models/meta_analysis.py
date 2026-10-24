import uuid
from django.db import models


class MetaAnalysisOutcomeData(models.Model):
    """
    Stores structured quantitative effect size data extracted for statistical meta-analyses
    (ready for R metafor, RevMan Web, or Python statsmodels / Forest Plots).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(
        'research_intelligence.Paper',
        on_delete=models.CASCADE,
        related_name='slr_meta_outcomes',
        help_text="Study reporting this numerical outcome."
    )
    outcome_name = models.CharField(
        max_length=255,
        help_text="e.g. 'Overall Survival', 'HbA1c Reduction', '28-Day Mortality'"
    )

    OUTCOME_TYPES = [
        ('dichotomous', 'Dichotomous (Binary Events: E1/N1, E2/N2)'),
        ('continuous', 'Continuous (Numerical: Mean, SD, N)'),
        ('time_to_event', 'Time-to-Event (Survival: Hazard Ratio, CI)'),
    ]
    outcome_type = models.CharField(max_length=20, choices=OUTCOME_TYPES, default='dichotomous')

    # Intervention / Treatment Group Data
    int_sample_size = models.PositiveIntegerField(null=True, blank=True, help_text="Intervention group sample size (N1)")
    int_events = models.PositiveIntegerField(null=True, blank=True, help_text="Intervention group event count (E1)")
    int_mean = models.FloatField(null=True, blank=True, help_text="Intervention group mean (x1)")
    int_sd = models.FloatField(null=True, blank=True, help_text="Intervention group standard deviation (SD1)")

    # Control / Comparator Group Data
    ctrl_sample_size = models.PositiveIntegerField(null=True, blank=True, help_text="Control group sample size (N2)")
    ctrl_events = models.PositiveIntegerField(null=True, blank=True, help_text="Control group event count (E2)")
    ctrl_mean = models.FloatField(null=True, blank=True, help_text="Control group mean (x2)")
    ctrl_sd = models.FloatField(null=True, blank=True, help_text="Control group standard deviation (SD2)")

    # Computed or Reported Effect Estimates
    effect_size_estimate = models.FloatField(null=True, blank=True, help_text="Point estimate (RR, OR, HR, MD, or SMD)")
    ci_lower = models.FloatField(null=True, blank=True, help_text="95% Confidence Interval lower bound")
    ci_upper = models.FloatField(null=True, blank=True, help_text="95% Confidence Interval upper bound")
    p_value = models.FloatField(null=True, blank=True, help_text="Statistical significance (p-value)")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['outcome_name', '-created_at']
        verbose_name = "Meta-Analysis Outcome Data"
        verbose_name_plural = "Meta-Analysis Outcome Data"

    def __str__(self):
        paper_title = getattr(self.paper, 'title', str(self.paper_id))
        return f"{self.outcome_name} ({self.outcome_type}) - {paper_title[:30]}"
