import uuid
import logging
from django.db import models

logger = logging.getLogger(__name__)


class NarrativeReport(models.Model):
    """
    Stores compiled weekly briefs, LaTeX bibliographies, and critique refinement iterations per run.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('Workspace', on_delete=models.CASCADE, related_name="reports")
    pipeline_run = models.ForeignKey('PipelineRun', on_delete=models.CASCADE, related_name="reports", help_text="The ingestion run summarized by this report")
    title = models.CharField(max_length=255)
    content_markdown = models.TextField()
    content_latex = models.TextField(blank=True, null=True)
    bibtex_content = models.TextField(blank=True, null=True, help_text="BibTeX bibliography compilation")
    compiled_pdf_path = models.CharField(max_length=512, blank=True, null=True, help_text="S3 key to final PDF report")
    refinement_depth = models.IntegerField(default=1, help_text="The value of K reached in self-refinement critique loops")
    critic_score_history = models.JSONField(default=list, help_text="Trace log of scores and critiques per iteration")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.title} (Run: {self.pipeline_run_id})"
