"""
affiliation_adapter.py - Tolerant Adapter & Normalizer for Affiliation and Risk Metadata.

========================================================================================
ARCHITECTURAL OVERVIEW & ROADMAP: OPTION A vs OPTION B
========================================================================================

CONTEXT:
Extractions on production (e.g. Chip Design, Hybrid Computing, Physical AI) output
metadata nested under top-level dictionaries:
  - `metadata.institutional_affiliations`: ["Technical University of Munich, Germany", ...]
  - `metadata.author_contacts`: [{"author_name": "L. Berent", "email": "lukas.berent@tum.de"}, ...]
  - `metadata.funding_entities`: ["European Research Council (ERC)", ...]
  - `metadata.codebase_links`: ["https://github.com/..."]
  - `gdpr_concern`: {"status": "NO", "concerns": null}
  - `competitor_involvement`: {"status": "NO", "matches": null}
  - `schwarz_ecosystem_affiliation`: {"status": "YES", "matched_institutions": ["TUM"]}

This adapter operates as **Option A (Tolerant Adapter & SOTA Normalizer)**:
1. Normalizes heterogeneously formatted extraction outputs (both flat and nested
   containers like `metadata.*`, `details.*`, `paper_info.*`) in real-time.
2. Formats all institutional affiliations, author contacts/emails, funding entities,
   codebase links, and sovereignty flags into the exact canonical shape expected
   by frontend `<RiskAffiliationFlagging />` in `paper-header.tsx` and `affiliation-flags.tsx`.
3. Preserves backwards compatibility with legacy extractions that store flat keys.

FUTURE ROADMAP - OPTION B (Data-Driven Extraction Definition Configuration):
In the future, ExtractionDefinition response schemas can specify explicit JSONPath or
mapping directives (e.g. `frontend_mapping: {"affiliations": "metadata.institutional_affiliations"}`).
Until all definitions are updated and migrated in prod, Option A provides resilient,
zero-downtime, non-breaking extraction parsing.
========================================================================================
"""

import ast
import json
import logging
import re
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _unwrap_val(val: Any) -> Any:
    """
    Unwraps wrapper dictionaries or serialized representations.
    Handles:
      - {"value": X} -> X
      - {"status": X} -> {"status": X} (kept intact for flag dictionaries)
      - Serialized JSON strings: '{"status": "YES"}' -> parsed dict
      - Python dict reprs: "{'status': 'YES'}" -> parsed dict
    """
    if val is None:
        return None

    if isinstance(val, dict):
        if "value" in val and len(val) == 1:
            return _unwrap_val(val["value"])
        return val

    if isinstance(val, str):
        trimmed = val.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (
            trimmed.startswith("[") and trimmed.endswith("]")
        ):
            try:
                return json.loads(trimmed)
            except Exception:
                try:
                    return ast.literal_eval(trimmed)
                except Exception:
                    pass

    return val


def _resolve_candidate_field(data: dict, candidates: List[str]) -> Any:
    """
    Resolves a candidate field from data dictionary by checking:
      1. Top-level keys
      2. Nested sub-containers (e.g. 'metadata', 'paper_metadata', 'details', 'meta', 'paper_info')
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
    Handles:
      - List of strings: ["Technical University of Munich, Germany", "Munich Quantum Valley, Germany"]
      - List of dicts: [{"name": "Technical University of Munich"}, {"institution": "..."}]
      - Semicolon or comma delimited strings: "TUM; Munich Quantum Valley"
    """
    if raw_val is None:
        return []

    unwrapped = _unwrap_val(raw_val)
    affiliations: List[str] = []
    if isinstance(unwrapped, list):
        for item in unwrapped:
            if isinstance(item, str) and item.strip():
                affiliations.append(item.strip())
            elif isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("institution")
                    or item.get("affiliation")
                    or item.get("institutional_affiliation")
                )
                if name and str(name).strip():
                    affiliations.append(str(name).strip())
            elif item is not None and str(item).strip():
                affiliations.append(str(item).strip())
    elif isinstance(unwrapped, str) and unwrapped.strip():
        if ";" in unwrapped:
            parts = [p.strip() for p in unwrapped.split(";") if p.strip()]
        else:
            parts = [p.strip() for p in unwrapped.split(",") if p.strip()]
        affiliations.extend(parts)

    return [a for a in affiliations if a and a.lower() not in ("none", "null", "n/a", "")]


def normalize_author_contacts(raw_val: Any) -> List[str]:
    """
    Normalizes author contacts into a clean list of strings for display.
    If items are dicts with {'author_name': '...', 'email': '...'}, extracts
    clean email strings (which frontend renders as mailto: links) or author names.
    """
    if raw_val is None:
        return []

    unwrapped = _unwrap_val(raw_val)
    contacts: List[str] = []
    if isinstance(unwrapped, list):
        for c in unwrapped:
            if isinstance(c, dict):
                email_str = str(c.get("email") or "").strip()
                name_str = str(c.get("author_name") or c.get("name") or "").strip()
                if email_str and email_str.lower() not in ("none", "null", "n/a", ""):
                    contacts.append(email_str)
                elif name_str and name_str.lower() not in ("none", "null", "n/a", ""):
                    contacts.append(name_str)
            elif c is not None and str(c).strip():
                c_str = str(c).strip()
                if c_str.lower() not in ("none", "null", "n/a", ""):
                    contacts.append(c_str)
    elif isinstance(unwrapped, str) and unwrapped.strip():
        contacts = [c.strip() for c in re.split(r'[,;]\s*', unwrapped) if c.strip()]

    return [c for c in contacts if c and c.lower() not in ("none", "null", "n/a", "")]


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
        for item in unwrapped:
            if item and isinstance(item, str) and item.strip() and item.strip().lower() not in ("none", "null", "n/a", ""):
                return item.strip()
            elif item and isinstance(item, dict):
                url = item.get("url") or item.get("link")
                if url and str(url).strip() and str(url).strip().lower() not in ("none", "null", "n/a", ""):
                    return str(url).strip()
        return None
    elif isinstance(unwrapped, str) and unwrapped.strip():
        u = unwrapped.strip()
        return u if u.lower() not in ("none", "null", "n/a", "") else None

    return None


def normalize_funding_entities(raw_val: Any) -> List[str]:
    """
    Normalizes funding entities and grants into a clean list of strings.
    Handles:
      - List of strings: ["European Research Council (ERC)", ...]
      - List of dicts: [{"name": "ERC", "grant_id": "123"}, ...]
      - Semicolon or comma delimited strings
    """
    if raw_val is None:
        return []

    unwrapped = _unwrap_val(raw_val)
    if isinstance(unwrapped, list):
        funding: List[str] = []
        for f in unwrapped:
            if isinstance(f, str) and f.strip():
                funding.append(f.strip())
            elif isinstance(f, dict):
                name = (
                    f.get("name")
                    or f.get("entity")
                    or f.get("agency")
                    or f.get("funder")
                    or f.get("funding_agency")
                )
                if name and str(name).strip():
                    funding.append(str(name).strip())
            elif f is not None and str(f).strip():
                funding.append(str(f).strip())
        return [item for item in funding if item and item.lower() not in ("none", "null", "n/a", "")]
    elif isinstance(unwrapped, str) and unwrapped.strip():
        return [f.strip() for f in re.split(r'[,;]\s*', unwrapped) if f.strip() and f.strip().lower() not in ("none", "null", "n/a", "")]

    return []


def unpack_flag_value(raw: Any, flag_type: str = "") -> Tuple[str, bool, List[str], bool, Optional[dict]]:
    """
    Parses flag fields into (display_value, is_positive, matched_items, is_dict, parsed_dict).
    Handles both direct values and rich objects:
      - {"status": "YES", "matched_institutions": ["TUM"]} -> ("YES (TUM)", True, ["TUM"], True, {...})
      - {"status": "NO", "concerns": null} -> ("NO", False, [], True, {...})
      - {"status": "FLAGGED", "concerns": ["Personal data"]} -> ("FLAGGED (Personal data)", True, [...], True, {...})
    """
    if raw is None:
        return "None" if "competitor" in flag_type else "NO", False, [], False, None

    parsed = _unwrap_val(raw)
    if isinstance(parsed, dict):
        raw_status = (
            parsed.get("status")
            or parsed.get("value")
            or parsed.get("risk")
            or parsed.get("level")
        )
        status_str = str(raw_status).strip() if raw_status is not None else ""

        matches = (
            parsed.get("matched_institutions")
            or parsed.get("matched_competitors")
            or parsed.get("matches")
            or parsed.get("institutions")
            or parsed.get("competitors")
            or parsed.get("concerns")
            or parsed.get("details")
            or parsed.get("reasons")
        )
        items: List[str] = []
        if isinstance(matches, list):
            items = [str(m).strip() for m in matches if m is not None and str(m).strip() and str(m).strip().lower() not in ("none", "null")]
        elif matches and str(matches).strip() and str(matches).strip().lower() not in ("none", "null"):
            items = [str(matches).strip()]

        stat_lower = status_str.lower()
        is_pos = (
            stat_lower in ("yes", "true", "affiliated", "high", "present", "flagged")
            or (bool(items) and stat_lower not in ("no", "false", "none", "low", "safe"))
        )
        is_neg = stat_lower in ("no", "false", "none", "safe", "low")

        if is_pos:
            val_str = f"YES ({', '.join(items)})" if items else (status_str if status_str else "YES")
        elif is_neg:
            val_str = "None" if "competitor" in flag_type else (status_str if status_str else "NO")
        else:
            val_str = f"{status_str} ({', '.join(items)})" if (status_str and items) else (status_str or "—")

        return val_str, is_pos, items, True, parsed

    # String or primitive flag
    val_str = str(parsed).strip()
    stat_lower = val_str.lower()
    is_pos = (
        stat_lower.startswith("yes")
        or stat_lower.startswith("true")
        or stat_lower in ("affiliated", "high", "present", "flagged")
        or bool(re.match(r'^(yes|true|affiliated|high|present|flagged)\b', stat_lower))
    )
    return val_str, is_pos, [], False, None


def adapt_affiliation_data(fields_data: dict) -> Optional[dict]:
    """
    Main entrypoint: tolerantly extracts Affiliation, Funding, Contacts, Artifact Links,
    and Sovereignty/Risk data from extraction fields.
    Outputs the canonical contract matching frontend `<RiskAffiliationFlagging />`
    in `paper-header.tsx` and OpenAPI specifications.
    """
    if not isinstance(fields_data, dict):
        return None

    data = fields_data.get("fields") if isinstance(fields_data.get("fields"), dict) else fields_data
    if not isinstance(data, dict):
        return None

    # 1. Institutional Affiliations
    raw_affil = _resolve_candidate_field(data, [
        "author_affiliation",
        "institutional_affiliations",
        "institutional_affiliation",
        "affiliations",
        "affiliation",
        "institutions",
        "institution",
        "organizations",
        "organization",
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
        "funding_entity",
        "funding",
        "grants",
        "grant_agencies",
        "sponsors",
        "sponsor",
        "funders",
        "funder",
        "financial_support",
    ])
    funding = normalize_funding_entities(raw_funding)

    # 4. Codebase & dataset artifact link (primary repository)
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

    # 5. Risk & Sovereignty flags (handles singular and plural variations tolerantly)
    schwarz_ecosystem = _resolve_candidate_field(data, [
        "schwarz_ecosystem_affiliation",
        "schwarz_fit",
        "schwarz_affiliation",
    ])
    gdpr_concerns = _resolve_candidate_field(data, [
        "compliance_risks",
        "compliance_risk",
        "compliance",
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
    # Ordered per UX requirements:
    # 1. Schwarz Ecosystem
    # 2. Competitor Involvement
    # 3. Compliance Risks
    flags = []
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
    if gdpr_concerns is not None:
        val_str, is_pos, _, is_d, p_dict = unpack_flag_value(gdpr_concerns, "gdpr")
        flags.append({
            "key": "gdpr",
            "label": "Compliance Risks",
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


# Canonical alias matching existing callers
adapt_risk_and_affiliation = adapt_affiliation_data
