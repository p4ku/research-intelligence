"""
Shared constants for the research_intelligence task pipeline.
Centralises magic strings that were previously scattered across multiple files.
"""


class OcrProvider:
    """
    Canonical identifiers for OCR / document conversion providers stored in
    DocumentRegistry.ocr_provider and used for cache-key matching.
    """
    GOOGLE_PATENTS_HTML = "google_patents_html"
    PYPDF = "pypdf"
    MISTRAL = "mistral"
    GEMINI = "gemini"
    MARKDOWN = "markdown"


class SourceDatabase:
    """
    Canonical identifiers for external academic / patent databases.
    Used in Paper.source_database and DocumentRegistry.primary_source.
    """
    ARXIV = "arxiv"
    OPENALEX = "openalex"
    LENS = "lens"
    GOOGLE_PATENTS = "google_patents"
    PUBMED = "pubmed"

    ALL = {ARXIV, OPENALEX, LENS, GOOGLE_PATENTS, PUBMED}

    @classmethod
    def for_paper(cls, paper) -> str:
        """Returns the source_database value of a paper, defaulting to ARXIV."""
        return (getattr(paper, "source_database", None) or cls.ARXIV).lower()

    @classmethod
    def ocr_provider_for(cls, paper) -> str:
        """Returns the appropriate OcrProvider identifier for a paper's source."""
        src = cls.for_paper(paper)
        if src == cls.GOOGLE_PATENTS:
            return OcrProvider.GOOGLE_PATENTS_HTML
        return OcrProvider.MARKDOWN
