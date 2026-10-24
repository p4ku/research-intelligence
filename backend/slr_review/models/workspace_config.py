import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


def get_default_exclusion_reasons():
    """Returns canonical default exclusion reasons for SLR PRISMA reporting."""
    return [
        "Wrong Study Population",
        "No Control / Comparator Group",
        "Off-Target Intervention / Method",
        "Animal / In-Vitro Model (Non-Human)",
        "Non-English Publication",
        "Duplicate / Retracted Article",
        "Insufficient Quantitative Data Reported",
    ]


class SLRWorkspaceConfig(models.Model):
    """
    Per-workspace Systematic Literature Review (SLR) policy engine.
    Controls checkpoint gate placement, quorum sizes, sampling strategies,
    Cochrane Risk of Bias appraisal, and evidence grounding requirements.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(
        'research_intelligence.Workspace',
        on_delete=models.CASCADE,
        related_name='slr_config',
        help_text="Workspace this SLR policy governs."
    )

    # 1. Checkpoint Gate Placement
    GATE_MODES = [
        ('two_stage_split', 'Two-Stage Split (Abstract Gate + Full-Text Gate)'),
        ('single_combined_post_fulltext', 'Single Combined Gate (Post Full-Text Screening)'),
        ('abstract_only_gate', 'Abstract Gate Only (Scoping Review Mode)'),
        ('autonomous_benchmark', 'Autonomous Benchmark (No Gates / Pure AI)'),
    ]
    checkpoint_gate_mode = models.CharField(
        max_length=40,
        choices=GATE_MODES,
        default='two_stage_split',
        help_text="Determines where the Celery DAG halts execution for human audit."
    )
    enable_extraction_gate = models.BooleanField(
        default=True,
        help_text="Halt pipeline for audit after AI 30-parameter extraction."
    )

    # 2. Quorum & Blind Dual-Review
    screening_quorum_size = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="Required independent reviews per sampled paper before consensus evaluation (1-6)."
    )
    extraction_quorum_size = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text="Required human validators per sampled extraction."
    )
    require_blind_review = models.BooleanField(
        default=True,
        help_text="Enforces blind evaluation: reviewers cannot see peer votes or AI reasoning until they vote."
    )

    # 3. Sampling Engine Policies (0.0% to 100.0%)
    SAMPLING_MODES = [
        ('uncertainty_stratified', 'Uncertainty-Stratified (100% Borderline + Random Controls)'),
        ('pure_random', 'Pure Uniform Random Sampling'),
        ('full_audit', '100% Full Manual Audit'),
    ]
    sampling_mode = models.CharField(
        max_length=30,
        choices=SAMPLING_MODES,
        default='uncertainty_stratified'
    )
    abstract_sample_percentage = models.FloatField(
        default=10.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Percentage of papers to sample at Abstract Screening gate."
    )
    full_text_sample_percentage = models.FloatField(
        default=20.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Percentage of candidates to sample at Full-Text Screening gate."
    )
    extraction_sample_percentage = models.FloatField(
        default=10.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Percentage of parameter extractions to sample for audit."
    )
    negative_control_percentage = models.FloatField(
        default=5.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(50.0)],
        help_text="Percentage of AI-rejected papers to audit to detect False Negatives."
    )

    # 4. Methodological Quality Appraisal (Risk of Bias)
    enable_rob_assessment = models.BooleanField(
        default=True,
        help_text="Executes Cochrane RoB 2 / ROBINS-I methodological appraisal during full-text review."
    )
    ROB_FRAMEWORKS = [
        ('auto_detect', 'Auto-detect Study Design (RCT vs Non-Randomized)'),
        ('rob2', 'Cochrane RoB 2 (Randomized Controlled Trials)'),
        ('robins_i', 'ROBINS-I (Non-Randomized Studies of Interventions)'),
        ('nos', 'Newcastle-Ottawa Scale (Cohort & Case-Control)'),
    ]
    rob_framework = models.CharField(
        max_length=30,
        choices=ROB_FRAMEWORKS,
        default='auto_detect'
    )
    require_human_rob_validation = models.BooleanField(
        default=True,
        help_text="Requires human sign-off on studies flagged with High Risk of Bias."
    )

    # 5. Dispute Resolution & Adjudication Rules
    designated_arbiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='slr_arbiter_configs',
        help_text="Designated Senior Arbiter (Principal Investigator / Supervisor) for tie-breaking."
    )
    TIE_STRATEGIES = [
        ('arbiter_ruling', 'Senior Arbiter Ruling (Binding Decision)'),
        ('conservative_include', 'Conservative Include (When in doubt, pass to next stage)'),
        ('discussion_meeting', 'Mark for In-Person Consensus Discussion'),
    ]
    tie_breaker_strategy = models.CharField(
        max_length=30,
        choices=TIE_STRATEGIES,
        default='arbiter_ruling'
    )

    # 6. Exclusion Reasons Taxonomy (Checklist for Reviewers & PRISMA Flow)
    exclusion_reasons = models.JSONField(
        default=get_default_exclusion_reasons,
        blank=True,
        help_text="Predefined checklist of exclusion reasons (e.g. ['Animal Study', 'Wrong Population'])."
    )

    # 7. Evidence Grounding Requirements
    require_evidence_on_exclusion = models.BooleanField(
        default=True,
        help_text="Mandates verbatim quote and page citation when reviewer selects an exclusion reason."
    )
    require_evidence_on_override = models.BooleanField(
        default=True,
        help_text="Mandates evidence quote when human overturns an AI recommendation."
    )

    # 8. Alerting & Governance
    notify_reviewers_on_pause = models.BooleanField(
        default=True,
        help_text="Dispatches email / webhook notification when DAG pauses at an audit gate."
    )
    stale_queue_reminder_days = models.PositiveIntegerField(
        default=3,
        help_text="Days of inactivity before dispatching review reminder."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SLR Workspace Config"
        verbose_name_plural = "SLR Workspace Configs"

    def __str__(self):
        ws_name = getattr(self.workspace, 'name', str(self.workspace_id))
        return f"SLR Config ({ws_name}) - Gate: {self.checkpoint_gate_mode}"
