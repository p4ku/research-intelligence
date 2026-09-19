import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PaperComment(models.Model):
    """
    Stores collaborative comments, evaluations, notes, and discussions on a Paper
    within a Workspace.
    
    Context & Scoping:
    - Scoped strictly to a Workspace for multi-tenant isolation.
    - Associated with a specific Paper.
    - If `pipeline_run` is None: The comment applies to the paper across all runs within the workspace.
    - If `pipeline_run` is set: The comment is tied to a specific execution / edition of the scanner.
    """

    # --- Comment Types ---
    TYPE_GENERAL = 'general'
    TYPE_EVALUATION = 'evaluation'
    TYPE_EXTRACTION_NOTE = 'extraction_note'
    TYPE_FINDING = 'finding'
    TYPE_QUESTION = 'question'

    COMMENT_TYPE_CHOICES = [
        (TYPE_GENERAL, 'General Comment'),
        (TYPE_EVALUATION, 'Paper Evaluation / Review'),
        (TYPE_EXTRACTION_NOTE, 'Extraction Feedback / Note'),
        (TYPE_FINDING, 'Research Finding / Insight'),
        (TYPE_QUESTION, 'Question / Inquiry'),
    ]

    # --- Status Choices ---
    STATUS_ACTIVE = 'active'
    STATUS_RESOLVED = 'resolved'
    STATUS_ARCHIVED = 'archived'
    STATUS_DELETED = 'deleted'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_ARCHIVED, 'Archived'),
        (STATUS_DELETED, 'Deleted'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Scoping relations
    workspace = models.ForeignKey(
        'Workspace',
        on_delete=models.CASCADE,
        related_name="paper_comments",
        help_text="Workspace context guaranteeing tenant isolation"
    )
    paper = models.ForeignKey(
        'Paper',
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="Target paper being commented on"
    )
    pipeline_run = models.ForeignKey(
        'PipelineRun',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="paper_comments",
        help_text="Nullable: if None, comment applies to this paper across all runs in the workspace"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="paper_comments",
        help_text="Researcher author of the comment"
    )

    # Threading (Parent-Child discussions)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        help_text="Parent comment for nested replies and threaded conversations"
    )

    # Content & Metadata
    content = models.TextField(
        help_text="Markdown formatted message content supporting math syntax, tables, and researcher @mentions"
    )
    comment_type = models.CharField(
        max_length=32,
        choices=COMMENT_TYPE_CHOICES,
        default=TYPE_GENERAL,
        db_index=True,
        help_text="Functional type of the comment"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        help_text="Lifecycle state of the comment"
    )

    # Researcher Mentions & Tagging
    mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="paper_comment_mentions",
        blank=True,
        help_text="Marked / tagged researchers in this comment"
    )

    # Anchoring & Domain Extraction Synergy
    extraction = models.ForeignKey(
        'Extraction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comments",
        help_text="Optional link to a specific paper extraction from the Domain Pool"
    )
    anchor_text = models.TextField(
        blank=True,
        null=True,
        help_text="Quoted text snippet from paper abstract or full-text layout"
    )
    anchor_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Deep linking location metadata (e.g. {'page': 3, 'section': 'Results', 'field_key': 'param1'})"
    )

    # Resolution & Workflow
    is_resolved = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if discussion thread or inquiry has been resolved"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_paper_comments"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Flags & Lifecycle
    is_pinned = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Pinned comment highlighted at the top of the paper scorecard/overview"
    )
    is_edited = models.BooleanField(
        default=False,
        help_text="Indicates whether markdown content was modified after creation"
    )
    is_deleted = models.BooleanField(
        default=False,
        help_text="Soft deletion flag to maintain thread reply integrity"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['workspace', 'paper', '-created_at']),
            models.Index(fields=['paper', 'pipeline_run', '-created_at']),
            models.Index(fields=['workspace', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['parent', 'created_at']),
            models.Index(fields=['comment_type', 'status']),
        ]

    def clean(self):
        super().clean()
        errors = {}

        # 1. Workspace isolation integrity with paper
        if self.paper_id and self.workspace_id:
            if self.paper.workspace_id != self.workspace_id:
                errors["workspace"] = "Comment workspace must match paper workspace."

        # 2. Workspace isolation integrity with pipeline_run
        if self.pipeline_run_id and self.workspace_id:
            if self.pipeline_run.workspace_id != self.workspace_id:
                errors["pipeline_run"] = "Comment pipeline_run must belong to the same workspace."

        # 3. Thread parent integrity
        if self.parent_id:
            if self.parent.paper_id != self.paper_id:
                errors["parent"] = "Reply must belong to the same paper as the parent comment."
            elif self.parent.workspace_id != self.workspace_id:
                errors["parent"] = "Reply must belong to the same workspace as the parent comment."

        # 4. Extraction integrity
        if self.extraction_id:
            if self.extraction.paper_id != self.paper_id:
                errors["extraction"] = "Extraction referenced must belong to the same paper."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Automatically infer workspace from paper or parent if missing
        if not self.workspace_id:
            if self.paper_id:
                self.workspace_id = self.paper.workspace_id
            elif self.parent_id:
                self.workspace_id = self.parent.workspace_id
            elif self.pipeline_run_id:
                self.workspace_id = self.pipeline_run.workspace_id

        self.clean()
        super().save(*args, **kwargs)

    def resolve(self, resolving_user=None):
        """Marks this comment / thread as resolved."""
        self.is_resolved = True
        self.status = self.STATUS_RESOLVED
        self.resolved_by = resolving_user
        self.resolved_at = timezone.now()
        self.save(update_fields=['is_resolved', 'status', 'resolved_by', 'resolved_at', 'updated_at'])

    def unresolve(self):
        """Re-opens a previously resolved comment."""
        self.is_resolved = False
        self.status = self.STATUS_ACTIVE
        self.resolved_by = None
        self.resolved_at = None
        self.save(update_fields=['is_resolved', 'status', 'resolved_by', 'resolved_at', 'updated_at'])

    def soft_delete(self):
        """Soft-deletes the comment preserving reply hierarchy."""
        self.is_deleted = True
        self.status = self.STATUS_DELETED
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'status', 'deleted_at', 'updated_at'])

    def __str__(self):
        target_run = f"Run:{str(self.pipeline_run_id)[:8]}" if self.pipeline_run_id else "Global"
        snippet = (self.content[:30] + '...') if len(self.content) > 30 else self.content
        return f"[{self.workspace.name} | {target_run}] {self.user}: {snippet}"


class PaperCommentReaction(models.Model):
    """
    Lightweight reactions (e.g. thumbs up, bulb, rocket) left by researchers on a PaperComment.
    """
    REACTION_THUMBS_UP = 'thumbs_up'
    REACTION_THUMBS_DOWN = 'thumbs_down'
    REACTION_BULB = 'bulb'
    REACTION_ROCKET = 'rocket'
    REACTION_QUESTION = 'question'
    REACTION_HEART = 'heart'

    REACTION_CHOICES = [
        (REACTION_THUMBS_UP, '👍 Useful / Agree'),
        (REACTION_THUMBS_DOWN, '👎 Disagree'),
        (REACTION_BULB, '💡 Insightful'),
        (REACTION_ROCKET, '🚀 Breakthrough / High Priority'),
        (REACTION_QUESTION, '❓ Clarification Needed'),
        (REACTION_HEART, '❤️ Appreciated'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comment = models.ForeignKey(
        PaperComment,
        on_delete=models.CASCADE,
        related_name="reactions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="paper_comment_reactions"
    )
    reaction_type = models.CharField(
        max_length=32,
        choices=REACTION_CHOICES,
        help_text="Type of reaction emoji/badge"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['comment', 'user', 'reaction_type'],
                name='unique_user_comment_reaction'
            )
        ]
        indexes = [
            models.Index(fields=['comment', 'reaction_type']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user} reacted {self.reaction_type} on comment {self.comment_id}"
