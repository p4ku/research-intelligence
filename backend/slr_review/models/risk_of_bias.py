import uuid
from django.db import models
from django.conf import settings


class RiskOfBiasAssessment(models.Model):
    """
    Stores methodological quality and Risk of Bias (RoB) assessments
    evaluated per study using Cochrane RoB 2 (RCTs) or ROBINS-I.
    Generates publication-ready Traffic Light Plots.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(
        'research_intelligence.Paper',
        on_delete=models.CASCADE,
        related_name='slr_rob_assessments',
        help_text="Study evaluated for Risk of Bias."
    )
    pipeline_run = models.ForeignKey(
        'research_intelligence.PipelineRun',
        on_delete=models.CASCADE,
        related_name='slr_rob_assessments',
        help_text="Pipeline execution run during which RoB was evaluated."
    )

    FRAMEWORKS = [
        ('rob2', 'Cochrane Risk of Bias Tool 2 (RCTs)'),
        ('robins_i', 'ROBINS-I (Non-Randomized Studies of Interventions)'),
        ('nos', 'Newcastle-Ottawa Scale (Cohort / Case-Control)'),
    ]
    framework = models.CharField(max_length=30, choices=FRAMEWORKS, default='rob2')

    # Domain Ratings: low_risk, some_concerns, high_risk, critical_risk
    # Example for RoB 2: D1_randomization, D2_deviations, D3_missing_data, D4_measurement, D5_selection
    domain_scores = models.JSONField(
        default=dict,
        help_text="""
        Dictionary of domain scores:
        {
            "D1_randomization": {"rating": "low_risk", "quote": "...", "page": 4},
            "D2_deviations": {"rating": "low_risk", "quote": "...", "page": 5},
            "D3_missing_data": {"rating": "some_concerns", "quote": "...", "page": 7},
            "D4_measurement": {"rating": "low_risk", "quote": "...", "page": 6},
            "D5_selection": {"rating": "low_risk", "quote": "...", "page": 9}
        }
        """
    )

    OVERALL_BIAS_CHOICES = [
        ('low_risk', 'Low Risk of Bias'),
        ('some_concerns', 'Some Concerns'),
        ('high_risk', 'High Risk of Bias'),
        ('critical_risk', 'Critical Risk of Bias'),
    ]
    overall_bias = models.CharField(
        max_length=30,
        choices=OVERALL_BIAS_CHOICES,
        default='some_concerns',
        db_index=True
    )

    # Traffic Light Color Code for Visual Plots
    TRAFFIC_LIGHT_CHOICES = [
        ('green', 'Green (Low Risk)'),
        ('yellow', 'Yellow (Some Concerns)'),
        ('red', 'Red (High Risk)'),
    ]
    traffic_light_color = models.CharField(max_length=10, choices=TRAFFIC_LIGHT_CHOICES, default='yellow')

    # Human-in-the-Loop Validation
    is_human_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='slr_rob_verifications',
        help_text="Human reviewer who signed off on the RoB assessment."
    )
    human_override_scores = models.JSONField(
        null=True,
        blank=True,
        help_text="Adjusted domain scores if human expert modified AI findings."
    )
    human_notes = models.TextField(blank=True, null=True, help_text="Expert commentary on methodological quality.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('paper', 'pipeline_run')
        indexes = [
            models.Index(fields=['pipeline_run', 'overall_bias']),
            models.Index(fields=['framework', 'overall_bias']),
        ]
        verbose_name = "Risk of Bias Assessment"
        verbose_name_plural = "Risk of Bias Assessments"

    def __str__(self):
        paper_title = getattr(self.paper, 'title', str(self.paper_id))
        return f"RoB ({self.framework}) - {paper_title[:30]} [{self.overall_bias.upper()}]"
