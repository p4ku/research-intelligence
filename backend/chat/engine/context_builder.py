import logging
from django.core.files.storage import default_storage

from research_intelligence.models import (
    Paper,
    Extraction,
    PaperMetric,
)

logger = logging.getLogger(__name__)


class PaperContextBuilder:
    """
    Constructs a clean, dense, structured context block for academic paper Q&A.
    Only includes sections that contain actual verified data, omitting empty placeholders.
    """

    def build(self, paper: Paper) -> tuple[str, bytes | None, str | None]:
        """
        Gathers paper metadata, layout markdown (or raw PDF bytes), screening evaluations,
        dynamic extractions, and calculated mathematical signal scores.

        Returns:
            context_text (str): Structured textual context to inject into prompt.
            pdf_bytes (bytes | None): Raw PDF binary if layout markdown is absent and PDF exists.
            mime_type (str | None): 'application/pdf' if pdf_bytes is loaded, else None.
        """
        workspace = paper.workspace
        context_parts = []

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
        pdf_bytes = None
        mime_type = None

        if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
            try:
                with default_storage.open(paper.converted_md_path, 'r') as f:
                    md_text = f.read()
                if md_text and md_text.strip():
                    context_parts.append("### Full Document Text (Layout OCR Markdown)\n" + md_text.strip())
            except Exception as e:
                logger.warning(f"Failed to read OCR markdown from {paper.converted_md_path}: {e}")

        # Fallback to multimodal PDF binary if Markdown was not found
        if not any("Full Document Text" in p for p in context_parts) and paper.original_pdf_path:
            if default_storage.exists(paper.original_pdf_path):
                try:
                    with default_storage.open(paper.original_pdf_path, 'rb') as f:
                        pdf_bytes = f.read()
                    mime_type = "application/pdf"
                    context_parts.append("### Full Document Binary: Attached as native multimodal PDF.")
                except Exception as e:
                    logger.warning(f"Failed to read original PDF from {paper.original_pdf_path}: {e}")

        # 3. Systematic Literature Review (SLR) Screening Rationale
        screening_lines = []
        status_val = getattr(paper, 'screening_status', None)
        reason_val = getattr(paper, 'screening_reasoning', None)
        if status_val and status_val != 'pending':
            screening_lines.append(f"- Screening Status: {status_val}")
        if reason_val:
            screening_lines.append(f"  Reason: {reason_val}")

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

        # 5. Computed Quality & Signal Metrics
        metrics = PaperMetric.objects.filter(paper=paper)
        has_signal_score = paper.signal_score is not None
        if metrics.exists() or has_signal_score:
            metric_lines = []
            if has_signal_score:
                metric_lines.append(f"- Composite Signal Score: {paper.signal_score}")
                if paper.signal_score_details:
                    metric_lines.append(f"  Score Computation Details: {paper.signal_score_details}")
            for m in metrics:
                if m.signal_score is not None and not has_signal_score:
                    metric_lines.append(f"- Signal Score: {m.signal_score}")
                if m.metrics_data and isinstance(m.metrics_data, dict):
                    for k, v in m.metrics_data.items():
                        metric_lines.append(f"- {k}: {v}")

            if getattr(workspace, 'signal_score_code', None):
                metric_lines.append(f"\nSignal Score Formula (Python AST):\n```python\n{workspace.signal_score_code.strip()}\n```")

            context_parts.append("### Computed Quality & Signal Metrics\n" + "\n".join(metric_lines))

        context_text = "\n\n".join(context_parts)
        return context_text, pdf_bytes, mime_type
