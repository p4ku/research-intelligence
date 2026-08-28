import uuid
from django.db import models
from django.conf import settings


class PaperChatSession(models.Model):
    """
    Represents an interactive multi-turn Q&A session over a specific paper in a workspace.
    Supports hierarchical session summarization and cumulative token & USD cost tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'research_intelligence.Workspace',
        on_delete=models.CASCADE,
        related_name="paper_chat_sessions"
    )
    paper = models.ForeignKey(
        'research_intelligence.Paper',
        on_delete=models.CASCADE,
        related_name="chat_sessions",
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="paper_chat_sessions",
        null=True,
        blank=True
    )
    title = models.CharField(max_length=255, default="Paper Discussion")
    summary = models.TextField(blank=True, default="", help_text="Hierarchical scientific summary of past conversation turns")
    cached_content_name = models.CharField(max_length=255, blank=True, default="", help_text="Reference key for Gemini server-side CachedContent")
    
    # Cumulative Session Token & Cost Metrics
    total_tokens_in = models.BigIntegerField(default=0, help_text="Cumulative input/prompt tokens across session")
    total_tokens_out = models.BigIntegerField(default=0, help_text="Cumulative output/candidate tokens across session")
    total_tokens = models.BigIntegerField(default=0, help_text="Cumulative total tokens (in + out) across session")
    total_usd_cost = models.DecimalField(max_digits=10, decimal_places=5, default=0.0, help_text="Cumulative USD cost of the session")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'chat'
        ordering = ['-updated_at', '-created_at']
        indexes = [
            models.Index(fields=['workspace', '-updated_at']),
            models.Index(fields=['paper', '-updated_at']),
            models.Index(fields=['user', '-updated_at']),
        ]

    def record_message_cost(self, tokens_in: int, tokens_out: int, cost):
        """Atomically increments session token and USD counters."""
        from django.db.models import F
        tot = (tokens_in or 0) + (tokens_out or 0)
        PaperChatSession.objects.filter(pk=self.pk).update(
            total_tokens_in=F('total_tokens_in') + (tokens_in or 0),
            total_tokens_out=F('total_tokens_out') + (tokens_out or 0),
            total_tokens=F('total_tokens') + tot,
            total_usd_cost=F('total_usd_cost') + cost
        )
        self.refresh_from_db(fields=['total_tokens_in', 'total_tokens_out', 'total_tokens', 'total_usd_cost'])

    def __str__(self):
        paper_title = getattr(self.paper, 'title', str(self.paper_id)) if hasattr(self, 'paper') else str(self.paper_id)
        return f"Chat Session: {self.title} (Paper: {paper_title[:30]}...)"
