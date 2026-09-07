import hashlib
import logging
from dataclasses import dataclass

from django.core.cache import cache
from django.core.files.storage import default_storage

from research_intelligence.models import (
    Workspace,
    Paper,
    Extraction,
    PaperMetric,
)

logger = logging.getLogger(__name__)

# The OCR markdown is content-addressed (path carries the document hash), so a
# stale entry can only mean the file was deleted; one hour bounds that window.
DOCUMENT_CACHE_TIMEOUT = 60 * 60


@dataclass(frozen=True)
class PaperDocument:
    """
    The immutable part of a paper's chat context: metadata plus the full text
    (layout markdown) or, failing that, the raw PDF for multimodal reading.
    Sent first in every prompt so Gemini's implicit prefix cache can hit.
    """
    text: str
    pdf_bytes: bytes | None = None
    mime_type: str | None = None


class PaperContextBuilder:
    """
    Constructs a clean, dense, structured context block for academic paper and workspace Q&A.
    Only includes sections that contain actual verified data, omitting empty placeholders.

    The context is split in two so the prompt has a stable prefix:
      - document():     metadata + full text — immutable once OCR has run, memoised.
      - annotations():  screening, extractions, signal metrics — small and may change after rescoring.
    """

    def build(self, paper: Paper | None, workspace: Workspace | None = None) -> tuple[str, bytes | None, str | None]:
        """
        Composes document and annotations into one block, in prompt order.

        Returns:
            context_text (str): Structured textual context to inject into prompt.
            pdf_bytes (bytes | None): Raw PDF binary if layout markdown is absent and PDF exists.
            mime_type (str | None): 'application/pdf' if pdf_bytes is loaded, else None.
        """
        target_workspace = workspace or (paper.workspace if paper else None)

        if not paper:
            overview = self.workspace_overview(target_workspace) if target_workspace else ""
            return overview, None, None

        doc = self.document(paper)
        notes = self.annotations(paper, target_workspace)
        context_text = "\n\n".join(part for part in (doc.text, notes) if part)
        return context_text, doc.pdf_bytes, doc.mime_type

    def workspace_overview(self, workspace: Workspace) -> str:
        """Workspace-level chat (no single paper selected): name, description, top accepted papers."""
        ws_lines = [
            f"Workspace: {workspace.name}",
            f"Description: {getattr(workspace, 'description', '') or 'Systematic Literature Review Workspace'}"
        ]
        from django.db.models import Subquery, OuterRef, F
        metric_sub = PaperMetric.objects.filter(paper=OuterRef('pk')).order_by('-created_at')
        accepted_papers = Paper.objects.filter(
            workspace=workspace,
            metrics__screening_status__in=['full_text_passed', 'accepted']
        ).distinct().annotate(
            annotated_signal_score=Subquery(metric_sub.values('signal_score')[:1])
        ).order_by(F('annotated_signal_score').desc(nulls_last=True), '-created_at')[:10]
        if accepted_papers.exists():
            ws_lines.append("\nTop Accepted Papers:")
            for p in accepted_papers:
                score_val = getattr(p, 'annotated_signal_score', None)
                score_str = f" (Signal Score: {score_val})" if score_val is not None else ""
                ws_lines.append(f"- {p.title}{score_str}")
        return "### Workspace Overview\n" + "\n".join(ws_lines)

    def document(self, paper: Paper) -> PaperDocument:
        """Paper metadata and full text (layout markdown), or the PDF binary when no markdown exists."""
        context_parts = []
        pdf_bytes = None
        mime_type = None

        # 1. Paper Core Metadata
        meta_lines = [f"Title: {paper.title}"]
        if getattr(paper, 'authors', None):
            authors_val = paper.authors
            meta_lines.append(f"Authors: {', '.join(authors_val) if isinstance(authors_val, list) else authors_val}")
        if getattr(paper, 'year', None):
            meta_lines.append(f"Year: {paper.year}")
        if getattr(paper, 'venue', None):
            meta_lines.append(f"Venue/Journal: {paper.venue}")
        if getattr(paper, 'doi', None):
            meta_lines.append(f"DOI: {paper.doi}")
        if getattr(paper, 'arxiv_id', None):
            meta_lines.append(f"arXiv ID: {paper.arxiv_id}")
        if getattr(paper, 'abstract', None):
            meta_lines.append(f"\nAbstract:\n{paper.abstract.strip()}")

        context_parts.append("### Paper Metadata\n" + "\n".join(meta_lines))

        # 2. Document Content (Layout Markdown vs Multimodal PDF)
        md_text = self._read_markdown(paper.converted_md_path) if paper.converted_md_path else ""
        if md_text:
            context_parts.append("### Full Document Text (Layout OCR Markdown)\n" + md_text)
        elif paper.original_pdf_path:
            # Fallback to multimodal PDF binary if Markdown was not found
            if not paper.original_pdf_path.startswith(("http://", "https://")) and default_storage.exists(paper.original_pdf_path):
                try:
                    with default_storage.open(paper.original_pdf_path, 'rb') as f:
                        pdf_bytes = f.read()
                    mime_type = "application/pdf"
                    context_parts.append("### Full Document Binary: Attached as native multimodal PDF.")
                except Exception as e:
                    logger.warning(f"Failed to read original PDF from {paper.original_pdf_path}: {e}")

        return PaperDocument(text="\n\n".join(context_parts), pdf_bytes=pdf_bytes, mime_type=mime_type)

    def _read_markdown(self, path: str) -> str:
        """Reads the OCR markdown from storage, memoised so repeat turns skip the object-store round trip."""
        key = "chat:doc:" + hashlib.sha1(path.encode("utf-8")).hexdigest()
        md_text = cache.get(key)
        if md_text is not None:
            return md_text

        md_text = ""
        if default_storage.exists(path):
            try:
                with default_storage.open(path, 'rb') as f:
                    content = f.read()
                    md_text = content.decode('utf-8', errors='replace') if isinstance(content, bytes) else str(content)
                md_text = md_text.strip()
            except Exception as e:
                logger.warning(f"Failed to read OCR markdown from {path}: {e}")
                return ""

        if md_text:
            cache.set(key, md_text, DOCUMENT_CACHE_TIMEOUT)
        return md_text

    def annotations(self, paper: Paper, workspace: Workspace | None = None) -> str:
        """Screening rationale, extracted parameters and signal metrics — small, always read fresh."""
        target_workspace = workspace or paper.workspace
        context_parts = []

        # 3. Systematic Literature Review (SLR) Screening Rationale (from PaperMetric)
        metrics = list(PaperMetric.objects.filter(paper=paper).order_by('-created_at'))
        latest_metric = metrics[0] if metrics else None
        screening_lines = []
        if latest_metric:
            if latest_metric.screening_status and latest_metric.screening_status != 'pending':
                screening_lines.append(f"- Screening Status: {latest_metric.screening_status}")
            reasoning = latest_metric.screening_reasoning
            if reasoning:
                screening_lines.append(f"  Decision Rationale: {reasoning}")
            elif latest_metric.abstract_screening_reasoning:
                screening_lines.append(f"  Abstract Screening Reason: {latest_metric.abstract_screening_reasoning}")
            elif latest_metric.full_text_screening_reasoning:
                screening_lines.append(f"  Full-Text Screening Reason: {latest_metric.full_text_screening_reasoning}")

        if screening_lines:
            context_parts.append("### SLR Screening Evaluation\n" + "\n".join(screening_lines))

        # 4. Dynamic Parameter Extractions
        extractions = Extraction.objects.filter(paper=paper).select_related('extraction_definition')
        if extractions.exists():
            ext_lines = []
            for ext in extractions:
                def_name = ext.extraction_definition.name if ext.extraction_definition else (ext.category or "Custom Parameter")
                val = ext.fields_data
                ext_lines.append(f"- **{def_name}**: {val}")
                if ext.confidence_score is not None:
                    ext_lines.append(f"  Confidence: {ext.confidence_score:.2f}")
            context_parts.append("### Extracted Research Parameters\n" + "\n".join(ext_lines))

        # 5. Computed Quality & Signal Metrics (from PaperMetric)
        if metrics:
            metric_lines = []
            primary_metric = metrics[0]
            if primary_metric.signal_score is not None:
                metric_lines.append(f"- Composite Signal Score: {primary_metric.signal_score}")
                if primary_metric.signal_score_details:
                    metric_lines.append(f"  Score Computation Details: {primary_metric.signal_score_details}")
            for m in metrics:
                if m.metrics_data and isinstance(m.metrics_data, dict):
                    for k, v in m.metrics_data.items():
                        metric_lines.append(f"- {k}: {v}")

            if target_workspace and getattr(target_workspace, 'signal_score_code', None):
                metric_lines.append(f"\nSignal Score Formula (Python AST):\n```python\n{target_workspace.signal_score_code.strip()}\n```")

            if metric_lines:
                context_parts.append("### Computed Quality & Signal Metrics\n" + "\n".join(metric_lines))

        return "\n\n".join(context_parts)
