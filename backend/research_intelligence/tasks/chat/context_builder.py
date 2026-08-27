import json
import logging
from django.core.files.storage import default_storage

from research_intelligence.models import Paper, Extraction, PaperMetric

logger = logging.getLogger(__name__)


class PaperContextBuilder:
    """
    Constructs a clean, dynamic context text and multimodal binary payload
    for paper interrogation without noise or empty placeholder fields.
    """

    def build(self, paper: Paper) -> tuple[str, bytes | None, str | None]:
        """
        Builds structured, concise paper context for LLM prompt:
        1. Metadata: Only present, non-empty attributes.
        2. Full document text: OCR Markdown if available, or raw PDF bytes for multimodal Gemini, or abstract.
        3. Screening evaluation: Only if evaluated or criteria defined.
        4. Extracted parameters: Only included if extractions exist.
        5. Quality metrics & signal scores: Only included if metrics or score exist.
        
        Returns (context_text, pdf_bytes, mime_type).
        """
        context_sections = []

        # 1. Metadata
        meta_section = self._build_metadata(paper)
        if meta_section:
            context_sections.append(meta_section)

        # 2. Document Content (OCR Markdown / PDF binary / Abstract)
        content_section, pdf_bytes, mime_type = self._build_content(paper)
        if content_section:
            context_sections.append(content_section)

        # 3. Screening Evaluation
        screening_section = self._build_screening(paper)
        if screening_section:
            context_sections.append(screening_section)

        # 4. Extracted Parameters & Evidence
        extractions_section = self._build_extractions(paper)
        if extractions_section:
            context_sections.append(extractions_section)

        # 5. Composite Metrics & Signal Score
        metrics_section = self._build_metrics(paper)
        if metrics_section:
            context_sections.append(metrics_section)

        full_context_text = "\n\n".join(context_sections)
        return full_context_text, pdf_bytes, mime_type

    def _build_metadata(self, paper: Paper) -> str:
        lines = ["### Paper Metadata", f"- Title: {paper.title}"]
        if paper.authors and paper.authors.strip():
            lines.append(f"- Authors: {paper.authors.strip()}")
        if paper.doi and paper.doi.strip():
            lines.append(f"- DOI: {paper.doi.strip()}")
        if paper.arxiv_id and paper.arxiv_id.strip():
            lines.append(f"- arXiv ID: {paper.arxiv_id.strip()}")
        if paper.source_database and paper.source_database.strip():
            lines.append(f"- Source: {paper.source_database.strip()}")
        if paper.pipeline_run_id:
            lines.append(f"- Ingestion Run: {paper.pipeline_run_id}")
        return "\n".join(lines)

    def _build_content(self, paper: Paper) -> tuple[str | None, bytes | None, str | None]:
        pdf_bytes = None
        mime_type = None
        has_md = False

        # Try Layout OCR Markdown first
        if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
            try:
                with default_storage.open(paper.converted_md_path, 'r') as f:
                    md_text = f.read()
                    if isinstance(md_text, bytes):
                        md_text = md_text.decode('utf-8', errors='replace')
                    if md_text and len(md_text.strip()) > 50:
                        return f"### Full Document Text (Layout OCR Markdown):\n{md_text.strip()}", None, None
            except Exception as e:
                logger.warning(f"Could not read OCR Markdown at '{paper.converted_md_path}': {e}")

        # Try raw multimodal PDF binary
        if paper.original_pdf_path and default_storage.exists(paper.original_pdf_path):
            try:
                with default_storage.open(paper.original_pdf_path, 'rb') as f:
                    pdf_bytes = f.read()
                    mime_type = "application/pdf"
                return "### Full Document Binary: Attached as native multimodal PDF.", pdf_bytes, mime_type
            except Exception as e:
                logger.warning(f"Could not read PDF binary at '{paper.original_pdf_path}': {e}")

        # Fallback to Abstract
        if paper.abstract and paper.abstract.strip():
            return f"### Abstract:\n{paper.abstract.strip()}", None, None

        return None, None, None

    def _build_screening(self, paper: Paper) -> str | None:
        workspace = paper.workspace
        lines = []
        if paper.screening_status and paper.screening_status != 'pending':
            lines.append(f"- Status: {paper.screening_status}")
        if paper.screening_reasoning and paper.screening_reasoning.strip():
            lines.append(f"- Reasoning: {paper.screening_reasoning.strip()}")

        crit_acc = workspace.get_full_text_acceptance_criteria() or workspace.get_abstract_acceptance_criteria()
        if crit_acc and crit_acc.strip():
            lines.append(f"- Workspace Acceptance Criteria: {crit_acc.strip()}")

        crit_rej = workspace.get_full_text_rejection_criteria() or workspace.get_abstract_rejection_criteria()
        if crit_rej and crit_rej.strip():
            lines.append(f"- Workspace Rejection Criteria: {crit_rej.strip()}")

        if lines:
            return "### SLR Screening Evaluation\n" + "\n".join(lines)
        return None

    def _build_extractions(self, paper: Paper) -> str | None:
        extractions = Extraction.objects.filter(paper=paper).select_related('extraction_definition')
        if not extractions.exists():
            return None

        lines = ["### Extracted Research Parameters & Evidence:"]
        for ext in extractions:
            def_name = ext.extraction_definition.name if ext.extraction_definition else ext.category
            lines.append(f"#### Definition: {def_name}")
            lines.append(f"- Fields Data: {json.dumps(ext.fields_data, indent=2)}")
            if ext.validation_status and ext.validation_status != 'pending':
                lines.append(f"- Validation Status: {ext.validation_status} (HITL Validated: {ext.is_hitl_validated})")
        return "\n".join(lines)

    def _build_metrics(self, paper: Paper) -> str | None:
        workspace = paper.workspace
        metrics = PaperMetric.objects.filter(paper=paper)
        lines = []
        if paper.signal_score is not None:
            lines.append(f"- Composite Signal Score: {paper.signal_score}")
        if paper.signal_score_details:
            lines.append(f"- Signal Score Calculation Details: {json.dumps(paper.signal_score_details, indent=2)}")
        if workspace.signal_score_code and (paper.signal_score is not None or metrics.exists()):
            lines.append(f"- Workspace Signal Score Formula:\n```python\n{workspace.signal_score_code}\n```")
        for m in metrics:
            if m.metrics_data:
                lines.append(f"- Run Metrics: {json.dumps(m.metrics_data, indent=2)}")

        if lines:
            return "### Computed Quality & Signal Metrics:\n" + "\n".join(lines)
        return None
