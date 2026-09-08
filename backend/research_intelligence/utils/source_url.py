import re
from typing import Any

# New-style "2401.12345(v2)" or old-style "cond-mat/0102536", "cs.CV/0101001".
# Anything else in `arxiv_id` is not an arXiv id and must never become a link:
# the arXiv scraper's OpenAlex fallback puts the work id in `hash_id`, and
# `step_1_search/search.py` copies that into `arxiv_id` when the row is
# labelled `arxiv`, so a `W2781738013` reaches here routinely.
# The subject class is not always two letters: `cond-mat.stat-mech/9910200`
# is a real old-style id. Kept identical to the frontend's `isArxivId`
# (`lib/papers/map.ts`) so a link and its chip never disagree.
ARXIV_ID_RE = re.compile(r'^(\d{4}\.\d{4,5}|[a-z-]+(\.[a-z-]+)?/\d{7})(v\d+)?$', re.IGNORECASE)

# A stored arXiv link, so one minted from an id that was never an arXiv id can
# be recognised and ignored (migration 0069 backfilled those without a check).
_ARXIV_URL_RE = re.compile(r'^https?://arxiv\.org/(?:abs|pdf)/(.+?)(?:\.pdf)?$', re.IGNORECASE)


def _clean_arxiv(value: Any) -> str:
    clean = str(value).strip()
    if clean.lower().startswith("arxiv:"):
        clean = clean[6:]
    return clean


def is_arxiv_id(value: Any) -> bool:
    """Whether `value` is shaped like an arXiv id, `arxiv:` prefix allowed."""
    return bool(value) and bool(ARXIV_ID_RE.match(_clean_arxiv(value)))


def _trusted_source_url(value: Any) -> bool:
    """
    A stored source_url is taken as given unless it is an arxiv.org link whose
    id is not arXiv-shaped — a 404 minted by the 0069 backfill, which had no
    shape check. Ignoring it here re-resolves the row on read, so the rows
    already written heal without a data migration.
    """
    match = _ARXIV_URL_RE.match(str(value).strip())
    return True if not match else bool(ARXIV_ID_RE.match(match.group(1)))


def resolve_paper_source_url(
    obj: Any = None,
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
    meta: dict | None = None,
    source_database: str | None = None,
    hash_id: str | None = None,
    source_url: str | None = None,
) -> str | None:
    """
    Resolves the canonical external web URL to the original paper landing page or publication.
    Can accept a Paper/DocumentRegistry model instance, a raw dictionary, or explicit keyword arguments.

    Resolution hierarchy:
    1. Existing source_url (if non-empty)
    2. DOI (works for OpenAlex, Lens, CrossRef, publishers, etc.) -> https://doi.org/{clean_doi}
    3. arXiv ID -> https://arxiv.org/abs/{clean_arxiv}
    4. Raw repository metadata payload (meta):
       - OpenAlex: meta['id'] (e.g. 'https://openalex.org/W2963403868')
       - OpenAlex / Publisher landing page: meta['primary_location']['landing_page_url']
       - Lens / generic URLs: meta['landing_page_url'], meta['other_url'], meta['url']
    5. Fallback for OpenAlex work identifier stored in hash_id.
    """
    if obj is not None:
        if isinstance(obj, dict):
            source_url = source_url or obj.get('source_url')
            doi = doi or obj.get('doi')
            arxiv_id = arxiv_id or obj.get('arxiv_id')
            meta = meta or obj.get('meta')
            source_database = source_database or obj.get('source_database') or obj.get('primary_source')
            hash_id = hash_id or obj.get('hash_id')
        else:
            source_url = source_url or getattr(obj, 'source_url', None)
            doi = doi or getattr(obj, 'doi', None)
            arxiv_id = arxiv_id or getattr(obj, 'arxiv_id', None)
            meta = meta or getattr(obj, 'meta', None)
            source_database = source_database or getattr(obj, 'source_database', None) or getattr(obj, 'primary_source', None)
            hash_id = hash_id or getattr(obj, 'hash_id', None)

    if source_url and _trusted_source_url(source_url):
        return str(source_url)

    # 1. DOI takes precedence if available
    if doi:
        clean_doi = str(doi).strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
            if clean_doi.lower().startswith(prefix):
                clean_doi = clean_doi[len(prefix):]
        if clean_doi:
            return f"https://doi.org/{clean_doi}"

    # 2. arXiv ID — only when it is actually shaped like one. A value that is
    #    not falls through to the metadata below, which is where an OpenAlex
    #    fallback record's real landing page lives.
    if arxiv_id:
        clean_arxiv = _clean_arxiv(arxiv_id)
        if clean_arxiv and ARXIV_ID_RE.match(clean_arxiv):
            return f"https://arxiv.org/abs/{clean_arxiv}"

    # 3. Raw metadata payload (OpenAlex, Lens, CrossRef, PubMed)
    if meta and isinstance(meta, dict):
        # OpenAlex canonical ID is a full URL e.g. "https://openalex.org/W2963403868"
        openalex_id = meta.get("id")
        if openalex_id and str(openalex_id).startswith("http"):
            return str(openalex_id)

        # OpenAlex publisher landing page
        prim_loc = meta.get("primary_location")
        if isinstance(prim_loc, dict) and prim_loc.get("landing_page_url"):
            landing = prim_loc.get("landing_page_url")
            if landing and str(landing).startswith("http"):
                return str(landing)

        # Lens or custom scraper URL
        other_url = meta.get("landing_page_url") or meta.get("other_url") or meta.get("url")
        if other_url and str(other_url).startswith("http"):
            return str(other_url)

    # 4. Fallback for OpenAlex work ID stored in hash_id
    if source_database == "openalex" and hash_id:
        raw_hash = str(hash_id).strip()
        if raw_hash.startswith("W") and raw_hash[1:].isdigit():
            return f"https://openalex.org/{raw_hash}"

    return None
