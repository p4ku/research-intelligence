import uuid
from django.db import models


class SearchQueryRecord(models.Model):
    """
    Logs individual search queries executed against academic literature databases
    (PubMed, Embase, Scopus, OpenAlex, arXiv) for Cochrane/PRISMA Item 7 auditability.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    protocol = models.ForeignKey(
        'slr_review.SLRProtocol',
        on_delete=models.CASCADE,
        related_name='search_queries',
        help_text="SLR Protocol this search strategy belongs to."
    )
    database_name = models.CharField(
        max_length=50,
        help_text="Target academic database (e.g. 'PubMed', 'Embase', 'Scopus', 'OpenAlex', 'arXiv')."
    )
    raw_query_string = models.TextField(help_text="Exact query string dispatched with boolean tags.")
    filters_applied = models.JSONField(
        default=dict,
        blank=True,
        help_text="Filter limits applied (e.g. date range, language, study design)."
    )
    total_yield = models.PositiveIntegerField(default=0, help_text="Total raw candidate records returned before deduplication.")
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-executed_at']
        verbose_name = "Search Query Record"
        verbose_name_plural = "Search Query Records"

    def __str__(self):
        return f"{self.database_name} search ({self.total_yield} hits) at {self.executed_at.strftime('%Y-%m-%d') if self.executed_at else 'pending'}"
