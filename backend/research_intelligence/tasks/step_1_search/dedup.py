"""
Deduplication and Identifier Normalization utilities for scientific papers.
"""
import re

_WHITESPACE = re.compile(r'[ \t\r\n\f\v]+')
# A line wrap that took a JSON round-trip upstream: backslash + n as two
# characters (CRLF included). A doubled backslash is TeX's own '\\', left alone.
_ESCAPED_WRAP = re.compile(r'(?<!\\)(?:\\r)?\\n')
# An escaped wrap right before whitespace or the end of the field. No TeX
# control word looks like that (\nabla, \newline, \neq all continue), so one
# of these marks the whole field as escape-encoded.
_ESCAPED_FIELD_MARK = re.compile(r'(?<!\\)(?:\\r)?\\n(?=\s|$)')


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
    — and that wrap is a transport artefact, not part of the text. The arXiv XML
    parsers swap the newline for a space but keep the indent (three spaces where
    the wrap was); OpenAlex and Lens titles kept the newline itself. Either way it
    reached the UI.

    ASCII whitespace only, on purpose: a line wrap is never a no-break space, and
    NBSP inside a title ('10 kg', 'Fig. 1') is typography we must keep. It also
    keeps this identical to the frontend's oneLine() — '\\s' differs between the
    two engines on NEL and U+FEFF.

    The wrap can also arrive *escaped* — OpenAlex serves some works with the
    backslash and the letter as two characters — and is collapsed only in a
    field that is escape-encoded as a whole (_ESCAPED_FIELD_MARK). TeX starts
    the same way and abstracts carry it bare (\\nabla, \\textbf{..}), so
    nothing local tells 'of\\\\nquantum' from '\\\\nabla'; the mark does.
    """
    if not text:
        return ""
    if _ESCAPED_FIELD_MARK.search(text):
        text = _ESCAPED_WRAP.sub(' ', text)
    return _WHITESPACE.sub(' ', text).strip()


def normalize_title(title: str) -> str:
    """Converts to lowercase and retains only alphanumeric characters."""
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r'[^a-z0-9]', '', title)
    return title
