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


def normalize_title(title: str) -> str:
    """Converts to lowercase and retains only alphanumeric characters."""
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r'[^a-z0-9]', '', title)
    return title
