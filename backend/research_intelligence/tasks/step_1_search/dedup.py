"""
Deduplication and Identifier Normalization utilities for scientific papers.
"""
import re


def normalize_doi(doi: str) -> str:
    """Strips protocol prefix, doi.org base URL, spaces and converts to lowercase."""
    if not doi:
        return ""
    doi = doi.lower().strip()
    for prefix in ["https://doi.org/", "http://doi.org/", "doi.org/", "doi:"]:
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def normalize_arxiv_id(arxiv_id: str) -> str:
    """Strips 'arxiv:' prefix and version suffix (e.g., 'v1', 'v2') and lowercases."""
    if not arxiv_id:
        return ""
    arxiv_id = arxiv_id.lower().strip()
    if arxiv_id.startswith("arxiv:"):
        arxiv_id = arxiv_id[6:]
    arxiv_id = re.sub(r'v\d+$', '', arxiv_id)
    return arxiv_id


def one_line(text: str) -> str:
    """
    Collapses a provider's line wrapping into single spaces.

    Sources wrap long fields across lines — arXiv's Atom feed breaks a title as
    'PennyLane: Automatic differentiation of hybrid quantum-classical\\n  computations'
    — and that wrap is a transport artefact, not part of the text. Only the arXiv
    XML parsers stripped it, so titles arriving via OpenAlex or Lens kept the
    newline all the way to the UI.
    """
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def normalize_title(title: str) -> str:
    """Converts to lowercase and retains only alphanumeric characters."""
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r'[^a-z0-9]', '', title)
    return title
