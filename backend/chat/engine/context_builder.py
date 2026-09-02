import logging
from django.core.files.storage import default_storage

from research_intelligence.models import (
    Workspace,
    Paper,
    Extraction,
    PaperMetric,
)

logger = logging.getLogger(__name__)


class PaperContextBuilder:
    """
    Constructs a clean, dense, structured context block for academic paper and workspace Q&A.
    Only includes sections that contain actual verified data, omitting empty placeholders.
    """

    def build(self, paper: Paper | None, workspace: Workspace | None = None) -> tuple[str, bytes | None, str | None]:
        """
        Gathers paper metadata (or workspace overview), layout markdown / PDF binary,
        screening evaluations, dynamic extractions, and signal scores.

        Returns:
            context_text (str): Structured textual context to inject into prompt.
            pdf_bytes (bytes | None): Raw PDF binary if layout markdown is absent and PDF exists.
            mime_type (str | None): 'application/pdf' if pdf_bytes is loaded, else None.
        """
        context_parts = []
        pdf_bytes = None
        mime_type = None

        target_workspace = workspace or (paper.workspace if paper else None)

        # Handle Workspace-Level Chat (when no single paper is selected)
        if not paper and target_workspace:
            ws_lines = [
                f"Workspace: {target_workspace.name}",
                f"Description: {getattr(target_workspace, 'description', '') or 'Systematic Literature Review Workspace'}"
            ]
            from django.db.models import Subquery, OuterRef, F
            metric_sub = PaperMetric.objects.filter(paper=OuterRef('pk')).order_by('-created_at')
            accepted_papers = Paper.objects.filter(
                workspace=target_workspace,
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
            context_parts.append("### Workspace Overview\n" + "\n".join(ws_lines))
            return "\n\n".join(context_parts), None, None

        if not paper:
            return "", None, None

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
        if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
            try:
                with default_storage.open(paper.converted_md_path, 'rb') as f:
                    content = f.read()
                    md_text = content.decode('utf-8', errors='replace') if isinstance(content, bytes) else str(content)
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

        # 3. Systematic Literature Review (SLR) Screening Rationale (from PaperMetric)
        latest_metric = PaperMetric.objects.filter(paper=paper).order_by('-created_at').first()
        screening_lines = []
        if latest_metric:
            if latest_metric.screening_status and latest_metric.screening_status != 'pending':
                screening_lines.append(f"- Screening Status: {latest_metric.screening_status}")
            if latest_metric.abstract_screening_reasoning:
                screening_lines.append(f"  Abstract Screening Reason: {latest_metric.abstract_screening_reasoning}")
            if latest_metric.full_text_screening_reasoning:
                screening_lines.append(f"  Full-Text Screening Reason: {latest_metric.full_text_screening_reasoning}")
            elif latest_metric.screening_reasoning:
                screening_lines.append(f"  Screening Reason: {latest_metric.screening_reasoning}")

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
        metrics = list(PaperMetric.objects.filter(paper=paper).order_by('-created_at'))
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

        context_text = "\n\n".join(context_parts)
        return context_text, pdf_bytes, mime_type
