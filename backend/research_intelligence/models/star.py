import uuid
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.core.exceptions import ValidationError


class Star(models.Model):
    """
    A user's star on a single Paper or PipelineRun (a "briefing" edition).
    One row per (user, target); exactly one of paper / pipeline_run is set and kind names which.
    """
    KIND_PAPER = 'paper'
    KIND_PIPELINE_RUN = 'pipeline_run'
    KIND_CHOICES = [
        (KIND_PAPER, 'Paper'),
        (KIND_PIPELINE_RUN, 'Pipeline Run'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stars")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, help_text="Which target field is set")
    paper = models.ForeignKey('Paper', on_delete=models.CASCADE, null=True, blank=True, related_name="stars")
    pipeline_run = models.ForeignKey('PipelineRun', on_delete=models.CASCADE, null=True, blank=True, related_name="stars")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]
        constraints = [
            # Exactly one target, and kind names it. clean() is not run by get_or_create,
            # so the invariant lives in the database as well.
            models.CheckConstraint(
                condition=(
                    Q(kind='paper', paper__isnull=False, pipeline_run__isnull=True)
                    | Q(kind='pipeline_run', paper__isnull=True, pipeline_run__isnull=False)
                ),
                name='star_exactly_one_target',
            ),
            models.UniqueConstraint(
                fields=['user', 'paper'],
                name='unique_user_paper_star',
            ),
            models.UniqueConstraint(
                fields=['user', 'pipeline_run'],
                name='unique_user_pipeline_run_star',
            ),
        ]

    def clean(self):
        targets = {
            self.KIND_PAPER: self.paper_id,
            self.KIND_PIPELINE_RUN: self.pipeline_run_id,
        }
        set_kinds = [k for k, v in targets.items() if v]
        if len(set_kinds) != 1:
            raise ValidationError("Exactly one of paper or pipeline_run must be set.")
        if self.kind != set_kinds[0]:
            raise ValidationError({"kind": f"kind must be '{set_kinds[0]}' for the target that is set."})

    def __str__(self):
        return f"{self.user} - {self.kind}:{self.paper_id or self.pipeline_run_id}"
