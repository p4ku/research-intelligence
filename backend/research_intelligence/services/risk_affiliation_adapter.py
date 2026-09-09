"""
risk_affiliation_adapter.py - Tolerant Adapter & Normalizer for Risk and Affiliation Data.

========================================================================================
ARCHITECTURAL OVERVIEW & FUTURE ROADMAP: OPTION A vs OPTION B
========================================================================================

1. CURRENT ARCHITECTURE: OPTION A (Tolerant Adapter Pattern / Postel's Law)
----------------------------------------------------------------------------------------
Why this adapter exists:
- The frontend Paper page displays a fixed, dedicated masthead component
  (<RiskAffiliationFlagging /> in `affiliation-flags.tsx`) with a strict OpenAPI contract:
    * affiliations: list[str]
    * author_contacts: list[str]
    * funding_entities: list[str]
    * codebase_artifact_link: str | null
    * flags: list[dict] (GDPR Sovereignty, Schwarz Ecosystem, Competitor Involvement)
- In production (e.g. 8 Sep live workspaces: Chip Design, Hybrid Computing, Physical AI),
  LLM responses generated from live ExtractionDefinitions nest metadata under sub-dictionaries:
    * `metadata.institutional_affiliations`
    * `metadata.author_contacts` (list of dicts: {"author_name": ..., "email": ...})
    * `metadata.funding_entities`
    * `metadata.codebase_links` (array of links)
    * `metadata.dataset_links`
    * `gdpr_concern` (singular) with {"status": "...", "concerns": [...]}
- Option A follows Postel's Law ("Be conservative in what you send, be liberal in what
  you accept"). This adapter bridges variation in LLM output schemas by:
    a) Resolving fields from top-level keys or nested sub-dictionaries (`metadata`, `details`).
    b) Safely normalizing array-of-links to a single primary URL without str([list]) artifacts.
    c) Unpacking contact dicts so emails yield clean mailto: links without "Name <None>".
    d) Unpacking flag rationale items from `concerns`, `reasons`, or `matches`.

2. FUTURE ROADMAP: OPTION B (Data-Driven Schema & Postprocessing Standardization)
----------------------------------------------------------------------------------------
How Option B can be adopted to make this 100% data-driven:
- In Option B, instead of runtime Python heuristics in this adapter:
    a) The `ExtractionDefinition.response_schema` for Risk and Affiliation in each workspace
       is updated via a migration or management command to produce the canonical flat keys directly:
       `author_affiliation`, `author_contacts`, `funding_entities`, `codebase_artifact_link`, `gdpr_concerns`.
    b) Alternatively, a standard `postprocessing_code` snippet is attached to the
       Risk and Affiliation ExtractionDefinition in Django Admin, e.g.:
         ```python
         meta = metadata if isinstance(metadata, dict) else {}
         return {
             "author_affiliation": meta.get("institutional_affiliations") or author_affiliation,
             "author_contacts": [c.get("email") or c.get("author_name") for c in meta.get("author_contacts", []) if isinstance(c, dict)],
             "codebase_artifact_link": (meta.get("codebase_links") or [None])[0],
             "gdpr_concerns": gdpr_concern,
         }
         ```
- Once all production workspaces have been migrated to the standardized schema or postprocessing,
  this adapter can be simplified to a direct passthrough.
========================================================================================
"""

import re
from typing import Any, List, Optional, Tuple, Dict
from .scorecard_extractors import _unwrap_val, unpack_flag_value, _parse_dict_or_json


def _resolve_candidate_field(data: Dict[str, Any], candidates: List[str]) -> Any:
    """
    Tolerantly looks up any of the candidate keys in `data` (top-level),
    and if missing or empty, descends into nested sub-dictionaries
    (`metadata`, `paper_metadata`, `details`, `meta`).
    """
    if not isinstance(data, dict):
        return None

    # 1. Check top-level candidates
    for key in candidates:
        val = data.get(key)
        if val is not None and val != "" and val != []:
            return _unwrap_val(val)

    # 2. Check nested containers (e.g. metadata, paper_metadata, details)
    sub_containers = ("metadata", "paper_metadata", "details", "meta", "paper_info")
    for sub_k in sub_containers:
        sub_dict = data.get(sub_k)
        if isinstance(sub_dict, dict):
            for key in candidates:
                val = sub_dict.get(key)
                if val is not None and val != "" and val != []:
                    return _unwrap_val(val)

    return None


def normalize_affiliations(raw_val: Any) -> List[str]:
    """
    Normalizes affiliations into a clean list of institution names.
    Handles list of strings, comma/semicolon-delimited strings, or objects.
    """
    if raw_val is None:
        return []

    unwrapped = _unwrap_val(raw_val)
    if isinstance(unwrapped, list):
        items = []
        for a in unwrapped:
            if isinstance(a, dict):
                inst = a.get("institution") or a.get("name") or a.get("affiliation")
                if inst and str(inst).strip():
                    items.append(str(inst).strip())
            elif a is not None and str(a).strip():
                items.append(str(a).strip())
        return items
    elif isinstance(unwrapped, str) and unwrapped.strip():
        return [a.strip() for a in re.split(r'[,;]\s*', unwrapped) if a.strip()]

    return []


def normalize_author_contacts(raw_val: Any) -> List[str]:
    """
    Normalizes author contacts into clean email/name strings.
    Handles:
      - List of strings: ['author@example.com']
      - List of dicts: [{'author_name': 'Alice', 'email': 'alice@example.com'}, {'author_name': 'Bob', 'email': None}]
      - Delimited string: "author@example.com; second@example.com"
    Guarantees:
      - If email is present and valid, returns the clean email (or email string).
      - If email is None, returns the clean author name without '@', so the frontend
        renders plain text without broken mailto: or 'Name <None>'.
    """
    if raw_val is None:
        return []

    unwrapped = _unwrap_val(raw_val)
    contacts: List[str] = []

    if isinstance(unwrapped, list):
        for c in unwrapped:
            if isinstance(c, dict):
                email = c.get("email")
                name = c.get("author_name") or c.get("name")
                email_str = str(email).strip() if email is not None else ""
                name_str = str(name).strip() if name is not None else ""

                if email_str and email_str.lower() not in ("none", "null", ""):
                    # Clean valid email
                    contacts.append(email_str)
                elif name_str and name_str.lower() not in ("none", "null", ""):
                    # Name only (no email) - no '@', frontend renders as plain contact text
                    contacts.append(name_str)
            elif c is not None and str(c).strip():
                c_str = str(c).strip()
                if c_str.lower() not in ("none", "null", ""):
                    contacts.append(c_str)
    elif isinstance(unwrapped, str) and unwrapped.strip():
        contacts = [c.strip() for c in re.split(r'[,;]\s*', unwrapped) if c.strip()]

    return contacts


def normalize_codebase_link(raw_val: Any) -> Optional[str]:
    """
    Normalizes codebase / artifact repository link.
    Handles:
      - Direct string URL: "https://github.com/..."
      - Array of links: ["https://github.com/...", "https://zenodo.org/..."] -> picks the first
    Avoids stringifying list reprs (e.g. "['https://...']").
    """
    if raw_val is None:
        return None

    unwrapped = _unwrap_val(raw_val)
    if isinstance(unwrapped, (list, tuple)):
        # Take the first non-empty string URL
        for item in unwrapped:
            if item and isinstance(item, str) and item.strip():
                return item.strip()
            elif item and isinstance(item, dict):
                url = item.get("url") or item.get("link")
                if url and str(url).strip():
                    return str(url).strip()
        return None
    elif isinstance(unwrapped, str) and unwrapped.strip():
        return unwrapped.strip()

    return None


def normalize_funding_entities(raw_val: Any) -> List[str]:
    """
    Normalizes funding entities and grants into a clean list of strings.
    """
    if raw_val is None:
        return []

    unwrapped = _unwrap_val(raw_val)
    if isinstance(unwrapped, list):
        return [str(f).strip() for f in unwrapped if f is not None and str(f).strip()]
    elif isinstance(unwrapped, str) and unwrapped.strip():
        return [f.strip() for f in re.split(r'[,;]\s*', unwrapped) if f.strip()]

    return []


def adapt_risk_and_affiliation(fields_data: dict) -> Optional[dict]:
    """
    Main entrypoint: tolerantly extracts Risk & Affiliation data from extraction fields.
    Outputs the canonical contract matching frontend `<RiskAffiliationFlagging />`
    and OpenAPI specifications.
    """
    if not isinstance(fields_data, dict):
        return None

    data = fields_data.get("fields") if isinstance(fields_data.get("fields"), dict) else fields_data
    if not isinstance(data, dict):
        return None

    # 1. Affiliations
    raw_affil = _resolve_candidate_field(data, [
        "author_affiliation",
        "institutional_affiliations",
        "affiliations",
        "affiliation",
        "institutions",
        "institution",
    ])
    affiliations = normalize_affiliations(raw_affil)

    # 2. Author contacts / emails
    raw_contacts = _resolve_candidate_field(data, [
        "author_contacts",
        "contacts",
        "emails",
        "email",
        "author_emails",
        "correspondence",
    ])
    contacts = normalize_author_contacts(raw_contacts)

    # 3. Funding entities
    raw_funding = _resolve_candidate_field(data, [
        "funding_entities",
        "funding",
        "grants",
        "sponsors",
        "grant_agencies",
    ])
    funding = normalize_funding_entities(raw_funding)

    # 4. Codebase artifact link (primary repository)
    raw_code = _resolve_candidate_field(data, [
        "codebase_artifact_link",
        "codebase_links",
        "artifact_link",
        "code_repository",
        "repository",
        "code_url",
        "github_url",
        "zenodo_link",
        "dataset_links",
        "dataset_url",
        "repository_url",
    ])
    code_link = normalize_codebase_link(raw_code)

    # 5. Risk flags (handles singular and plural variations tolerantly)
    schwarz_ecosystem = _resolve_candidate_field(data, [
        "schwarz_ecosystem_affiliation",
        "schwarz_fit",
        "schwarz_affiliation",
    ])
    gdpr_concerns = _resolve_candidate_field(data, [
        "gdpr_concerns",
        "gdpr_concern",
        "gdpr_sovereignty",
        "gdpr",
        "data_privacy_concerns",
    ])
    competitor_involvement = _resolve_candidate_field(data, [
        "competitor_involvement",
        "competitor_risk",
        "competitor",
    ])

    risk_score = _resolve_candidate_field(data, ["risk_score"])
    risk_assessment = _resolve_candidate_field(data, ["risk_score_assessment", "risk_assessment"])

    # Format badges/flags for frontend
    flags = []
    if gdpr_concerns is not None:
        val_str, is_pos, _, is_d, p_dict = unpack_flag_value(gdpr_concerns, "gdpr")
        flags.append({
            "key": "gdpr",
            "label": "GDPR Sovereignty",
            "value": val_str,
            "status": "warn" if is_pos else "safe",
            "type": "dict" if is_d else "string",
            "is_dict": is_d,
            "dict_value": p_dict if is_d else None,
        })
    if schwarz_ecosystem is not None:
        val_str, is_pos, items, is_d, p_dict = unpack_flag_value(schwarz_ecosystem, "schwarz")
        flags.append({
            "key": "schwarz_ecosystem",
            "label": "Schwarz Ecosystem",
            "value": val_str,
            "status": "highlight" if is_pos else "neutral",
            "type": "dict" if is_d else "string",
            "is_dict": is_d,
            "dict_value": p_dict if is_d else None,
        })
        if not affiliations and items:
            affiliations.extend(items)
    if competitor_involvement is not None:
        val_str, is_pos, _, is_d, p_dict = unpack_flag_value(competitor_involvement, "competitor")
        flags.append({
            "key": "competitor",
            "label": "Competitor Involvement",
            "value": val_str,
            "status": "warn" if is_pos else "safe",
            "type": "dict" if is_d else "string",
            "is_dict": is_d,
            "dict_value": p_dict if is_d else None,
        })

    schwarz_clean = unpack_flag_value(schwarz_ecosystem, "schwarz")[0] if schwarz_ecosystem is not None else None
    gdpr_clean = unpack_flag_value(gdpr_concerns, "gdpr")[0] if gdpr_concerns is not None else None
    competitor_clean = unpack_flag_value(competitor_involvement, "competitor")[0] if competitor_involvement is not None else None

    return {
        "raw": data,
        "affiliations": affiliations,
        "author_contacts": contacts,
        "funding_entities": funding,
        "codebase_artifact_link": code_link,
        "schwarz_ecosystem_affiliation": schwarz_clean,
        "gdpr_concerns": gdpr_clean,
        "competitor_involvement": competitor_clean,
        "risk_score": float(risk_score) if isinstance(risk_score, (int, float)) else None,
        "risk_score_assessment": str(risk_assessment) if risk_assessment else None,
        "flags": flags,
    }
