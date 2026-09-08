import math
import re
import uuid
from rest_framework.response import Response
from research_intelligence.models import (
    Paper,
    Extraction,
    ExtractionDefinition,
    PipelineRun,
    NarrativeReport,
)
from ..serializers.papers import PaperSerializer


def resolve_field_val(fields_data: dict, key: str):
    """
    Looks up key in fields_data (or fields_data['fields']) with normalized matching.
    If the value is a dictionary:
      - If 1 key-value pair: unpacks it directly (e.g. {"schwarz_fit_postprocessed": 85} -> 85).
      - If >1 key-value pairs: returns the dictionary itself.
    Returns: (actual_val, raw_str, num_val, is_num, found)
    """
    if not isinstance(fields_data, dict) or not key:
        return None, "—", None, False, False

    data = fields_data.get("fields") if isinstance(fields_data.get("fields"), dict) else fields_data
    if not isinstance(data, dict):
        return None, "—", None, False, False

    norm_target = key.strip().lower().replace(" ", "_").replace("-", "_")

    val = data.get(key)
    if val is None:
        for k, v in data.items():
            if k.strip().lower().replace(" ", "_").replace("-", "_") == norm_target:
                val = v
                break

    if val is None:
        return None, "—", None, False, False

    actual_val = val
    # If actual_val is a dictionary:
    # 1. Standard {"value": ...} pattern
    # 2. 1 key-value dict -> unpack!
    if isinstance(actual_val, dict):
        if "value" in actual_val and len(actual_val) <= 2:
            actual_val = actual_val["value"]
        elif len(actual_val) == 1:
            inner_k, inner_v = next(iter(actual_val.items()))
            if isinstance(inner_v, dict) and "value" in inner_v:
                actual_val = inner_v["value"]
            elif isinstance(inner_v, dict) and len(inner_v) == 1:
                actual_val = next(iter(inner_v.values()))
            else:
                actual_val = inner_v

    if actual_val is None:
        return None, "—", None, False, True

    # If it is still a dictionary (meaning >1 key-values)
    if isinstance(actual_val, dict):
        return actual_val, str(actual_val), None, False, True

    raw_str = str(actual_val)
    num_val = None
    is_num = False
    if not isinstance(actual_val, (dict, list)):
        try:
            f_val = float(actual_val)
            if math.isfinite(f_val):
                num_val = int(f_val) if f_val.is_integer() else round(f_val, 2)
                is_num = True
        except (ValueError, TypeError):
            pass

    return actual_val, raw_str, num_val, is_num, True


def format_metric_label(key: str) -> str:
    """
    Converts a snake_case or slug key into a clean, human-readable label.
    Preserves common acronyms.
    """
    if not key:
        return ""
    acronyms = {"trl": "TRL", "gdpr": "GDPR", "llm": "LLM", "api": "API", "nlp": "NLP", "ai": "AI"}
    words = key.replace("-", "_").split("_")
    formatted = []
    for w in words:
        wl = w.lower()
        if wl in acronyms:
            formatted.append(acronyms[wl])
        else:
            formatted.append(w.capitalize())
    return " ".join(formatted)


def build_metric_entry(key: str, fields_data: dict, source: str = "exit_metric", label_override: str = None) -> dict:
    actual_val, raw_str, num_val, is_num, found = resolve_field_val(fields_data, key)
    label = label_override or format_metric_label(key)
    return {
        "key": key,
        "name": label,
        "label": label,
        "value": num_val if is_num else (actual_val if found else None),
        "numeric_value": num_val,
        "raw": raw_str if found else "—",
        "is_numeric": is_num,
        "source": source,
    }


# =====================================================================================
# [SECTION: PRIMARY VS SECONDARY METRICS CLASSIFICATION LOGIC]
# =====================================================================================
# LOCATION: extract_metrics_for_extraction()
#
# OVERVIEW OF CURRENT METRIC CLASSIFICATION LOGIC:
#
# Goal: Resolve a single primary metric (primary_metric / main_metric)
#       and a list of auxiliary metrics (secondary_metrics / auxiliary_metrics).
#
# RULE 1 (Postprocessing Code Configured):
#   When the definition has postprocessing code (definition.postprocessing_code):
#   - The postprocessing result (e.g. <def_slug>_postprocessed) is the primary metric candidate.
#   - Case A) If postprocessing returns a dict with EXACTLY 1 key-value pair (or a scalar value):
#        -> Unpack it directly as PRIMARY METRIC (e.g., {"schwarz_fit_postprocessed": 85} -> 85).
#        -> All configured 'exit_metrics' on the definition become SECONDARY METRICS.
#   - Case B) If postprocessing returns a dict with >1 key-value pairs (e.g., {"fit": 80, "risk": 20}):
#        -> If one of the keys explicitly matches the primary postprocessed candidate pattern,
#           it becomes the PRIMARY METRIC, and all remaining keys become SECONDARY METRICS.
#        -> If none of the keys match the primary candidate pattern, ALL returned keys become
#           SECONDARY METRICS (alongside the configured exit_metrics).
#
# RULE 2 (Exit Metrics Only):
#   When the definition has NO postprocessing code, but declares a list of Exit Metrics:
#   - The first metric in the list (exit_keys[0]) becomes the PRIMARY METRIC.
#   - All remaining metrics (exit_keys[1:]) become SECONDARY METRICS.
#
# RULE 3 (Fallback):
#   When neither postprocessing code nor exit metrics are configured:
#   - Inspect fields_data and pick the first business field (ignoring technical fields
#     such as reasoning, confidence, etc.) as the PRIMARY METRIC. secondary_metrics is empty.
#
# FUTURE REFINEMENT NOTES FOR THE TEAM:
#   - Consider adding an explicit 'primary_metric_key' field to the ExtractionDefinition model
#     rather than relying on naming conventions (suffixes/prefixes) or exit metric order.
#   - Consider supporting metric weights, bands, or category grouping for secondary_metrics.
# =====================================================================================


def extract_metrics_for_extraction(e: Extraction, d: ExtractionDefinition = None) -> tuple:
    """
    Extracts primary_metric (main_metric) and secondary_metrics (auxiliary_metrics).
    See the header comment above for the full architectural logic and rule breakdown.
    Returns: (primary_metric_dict, secondary_metrics_list, has_postprocessing)
    """
    definition = d or (e.extraction_definition if e else None)
    fields_data = e.fields_data if (e and isinstance(e.fields_data, dict)) else {}
    data_fields = fields_data.get("fields") if isinstance(fields_data.get("fields"), dict) else fields_data

    has_postprocessing = bool(
        definition
        and definition.postprocessing_code
        and definition.postprocessing_code.strip()
    )

    exit_keys = definition.get_exit_metrics_list() if definition else []
    primary_exit = definition.get_primary_exit_metric() if definition else None
    def_slug = (
        definition.name.lower().replace(" ", "_").replace("-", "_")
        if definition
        else ((e.category or "extraction").lower().replace(" ", "_").replace("-", "_") if e else "extraction")
    )

    if has_postprocessing:
        # Rule 2: Postprocessing code is present
        exit_keys_norm = {ek.strip().lower().replace(" ", "_").replace("-", "_") for ek in exit_keys}
        ignored_keys = {
            "confidence_score", "reasoning", "explanation", "validation_status", "error",
            "validation_errors", "postprocessing_error", "fields",
        }
        alias_suffixes = ("_computed",)

        primary_cand = f"{def_slug}_postprocessed"
        found_post_key = None

        if isinstance(data_fields, dict):
            for k in data_fields.keys():
                k_norm = k.strip().lower().replace(" ", "_").replace("-", "_")
                if k_norm == primary_cand:
                    found_post_key = k
                    break
            if not found_post_key and primary_exit:
                pe_norm = primary_exit.strip().lower().replace(" ", "_").replace("-", "_")
                for k in data_fields.keys():
                    k_norm = k.strip().lower().replace(" ", "_").replace("-", "_")
                    if k_norm == f"{pe_norm}_postprocessed":
                        found_post_key = k
                        break
            if not found_post_key:
                for k in data_fields.keys():
                    k_norm = k.strip().lower().replace(" ", "_").replace("-", "_")
                    if k_norm.endswith("_postprocessed"):
                        found_post_key = k
                        break

        raw_post_val = data_fields.get(found_post_key) if (found_post_key and isinstance(data_fields, dict)) else None
        post_extra_metrics = []

        if isinstance(raw_post_val, dict):
            if len(raw_post_val) == 1:
                # 1 key-value dict: "poprostu rozpakuj"
                inner_k, inner_v = next(iter(raw_post_val.items()))
                target_k = inner_k if (inner_k.endswith("_postprocessed") or not found_post_key) else found_post_key
                primary_metric = build_metric_entry(
                    key=target_k,
                    fields_data={target_k: inner_v},
                    source="postprocessing",
                    label_override=format_metric_label(target_k),
                )
            else:
                # >1 key-values: "jak jest wiecej to wszystkie są secondary metrics"
                has_main_in_dict = False
                for sub_k in raw_post_val.keys():
                    if sub_k.strip().lower().replace(" ", "_").replace("-", "_") == primary_cand:
                        has_main_in_dict = True
                        break
                if has_main_in_dict:
                    primary_metric = build_metric_entry(
                        key=primary_cand,
                        fields_data=raw_post_val,
                        source="postprocessing",
                        label_override=format_metric_label(primary_cand),
                    )
                    for sub_k in raw_post_val.keys():
                        if sub_k.strip().lower().replace(" ", "_").replace("-", "_") != primary_cand:
                            post_extra_metrics.append(build_metric_entry(key=sub_k, fields_data=raw_post_val, source="postprocessing"))
                else:
                    # All keys in this dict are secondary metrics!
                    primary_metric = {
                        "key": primary_cand,
                        "name": f"{definition.name} (Postprocessed)" if definition else format_metric_label(primary_cand),
                        "label": f"{definition.name} (Postprocessed)" if definition else format_metric_label(primary_cand),
                        "value": None,
                        "numeric_value": None,
                        "raw": "—",
                        "is_numeric": False,
                        "source": "postprocessing",
                    }
                    for sub_k in raw_post_val.keys():
                        post_extra_metrics.append(build_metric_entry(key=sub_k, fields_data=raw_post_val, source="postprocessing"))
        elif found_post_key:
            primary_metric = build_metric_entry(
                key=found_post_key,
                fields_data=fields_data,
                source="postprocessing",
                label_override=f"{definition.name} (Postprocessed)" if definition else None,
            )
        else:
            # No _postprocessed key found in data_fields. Check for other non-exit keys from postprocessing
            post_non_exit = []
            if isinstance(data_fields, dict):
                for k in data_fields.keys():
                    k_norm = k.strip().lower().replace(" ", "_").replace("-", "_")
                    if (
                        k_norm not in exit_keys_norm
                        and k_norm not in ignored_keys
                        and not any(k_norm.endswith(sfx) for sfx in alias_suffixes)
                    ):
                        post_non_exit.append(k)

            if len(post_non_exit) == 1:
                # 1 key-value: "poprostu rozpakuj" -> that single key is the primary metric!
                single_k = post_non_exit[0]
                primary_metric = build_metric_entry(
                    key=single_k,
                    fields_data=fields_data,
                    source="postprocessing",
                    label_override=format_metric_label(single_k),
                )
            elif len(post_non_exit) > 1:
                # >1 key-values: "jak jest wiecej to wszystkie są secondary metrics"!
                primary_metric = {
                    "key": primary_cand,
                    "name": f"{definition.name} (Postprocessed)" if definition else format_metric_label(primary_cand),
                    "label": f"{definition.name} (Postprocessed)" if definition else format_metric_label(primary_cand),
                    "value": None,
                    "numeric_value": None,
                    "raw": "—",
                    "is_numeric": False,
                    "source": "postprocessing",
                }
                for k in post_non_exit:
                    post_extra_metrics.append(build_metric_entry(key=k, fields_data=fields_data, source="postprocessing"))
            else:
                primary_metric = build_metric_entry(
                    key=primary_cand,
                    fields_data=fields_data,
                    source="postprocessing",
                    label_override=f"{definition.name} (Postprocessed)" if definition else None,
                )

        # Collect any other top-level keys in data_fields that came from postprocessing (>1 keys returned)
        if isinstance(data_fields, dict):
            already_included_keys = {
                (primary_metric["key"] or "").strip().lower().replace(" ", "_").replace("-", "_"),
                *(m["key"].strip().lower().replace(" ", "_").replace("-", "_") for m in post_extra_metrics),
                *exit_keys_norm,
                *ignored_keys,
            }
            alias_keys = {
                f"{def_slug}_computed",
                f"{primary_exit.strip().lower().replace(' ', '_').replace('-', '_')}_computed" if primary_exit else "",
                f"{primary_exit.strip().lower().replace(' ', '_').replace('-', '_')}_postprocessed" if primary_exit else "",
            }
            for k in data_fields.keys():
                k_norm = k.strip().lower().replace(" ", "_").replace("-", "_")
                if k_norm not in already_included_keys and k_norm not in alias_keys:
                    post_extra_metrics.append(build_metric_entry(key=k, fields_data=fields_data, source="postprocessing"))

        # Secondary metrics: all additional postprocessing metrics + all exit metrics
        exit_secondary = [
            build_metric_entry(key=ek, fields_data=fields_data, source="exit_metric")
            for ek in exit_keys
        ]
        secondary_metrics = post_extra_metrics + exit_secondary

    elif exit_keys:
        # Rule 1: Only exit metrics list -> first is primary, rest are secondary
        primary_key = exit_keys[0]
        primary_metric = build_metric_entry(
            key=primary_key,
            fields_data=fields_data,
            source="exit_metric",
            label_override=format_metric_label(primary_key),
        )
        secondary_metrics = [
            build_metric_entry(key=ek, fields_data=fields_data, source="exit_metric")
            for ek in exit_keys[1:]
        ]

    else:
        # Fallback: No exit metrics configured and no postprocessing
        cand_key = def_slug
        if isinstance(data_fields, dict) and data_fields:
            for k in data_fields.keys():
                if k not in ("confidence_score", "reasoning", "explanation"):
                    cand_key = k
                    break
        primary_metric = build_metric_entry(
            key=cand_key,
            fields_data=fields_data,
            source="custom",
            label_override=definition.name if definition else format_metric_label(cand_key),
        )
        secondary_metrics = []

    return primary_metric, secondary_metrics, has_postprocessing


RATIONALE_RE = re.compile(r'(reason|rationale|justif)', re.IGNORECASE)
EVIDENCE_RE = re.compile(r'(quote|^evidence$|_evidence$)', re.IGNORECASE)
BAND_RE = re.compile(r'(_band$|_label$|^band$|^label$)', re.IGNORECASE)
FACET_KEY_RE = re.compile(r'_score$', re.IGNORECASE)
ASSESSMENT_KEY_RE = re.compile(r'_assessment$', re.IGNORECASE)
LEVEL_KEY_RE = re.compile(r'_level$', re.IGNORECASE)
SENTENCE_RE = re.compile(r'[.!?](\s|$)')


def humanise_field_label(key: str) -> str:
    """
    Capitalizes first word, preserves common acronyms, e.g.
    'research_quality_insight' -> 'Research quality insight'
    'core_technology' -> 'Core technology'
    'confidence' -> 'Confidence'
    """
    if not key:
        return ""
    acronyms = {"trl": "TRL", "gdpr": "GDPR", "llm": "LLM", "api": "API", "nlp": "NLP", "ai": "AI", "rtl": "RTL"}
    clean_key = re.sub(r'(_score|_assessment)$', '', key, flags=re.IGNORECASE)
    words = [w for w in clean_key.replace("-", "_").split("_") if w]
    if not words:
        return ""
    res = []
    for i, w in enumerate(words):
        wl = w.lower()
        if wl in acronyms:
            res.append(acronyms[wl])
        elif i == 0:
            res.append(w.capitalize())
        else:
            res.append(w.lower())
    return " ".join(res)


def is_risk_dimension(name: str = "", key: str = "") -> bool:
    """
    Identifies whether a dimension or extraction represents Risk and Affiliation Flagging.
    """
    target = f"{name or ''} {key or ''}".lower().replace("-", "_")
    return bool(
        "affiliation" in target
        or "risk_and_affiliation" in target
        or ("risk" in target and "affiliation" in target)
    )


def extract_risk_and_affiliation(fields_data: dict) -> dict:
    """
    Extracts structured Risk & Affiliation data to display directly under authors:
      - Affiliations (institutions/labs)
      - Author contacts (emails, names)
      - Funding entities
      - Codebase artifact link (Zenodo, GitHub, etc.)
      - Key risk flags (GDPR Sovereignty, Schwarz Ecosystem, Competitor Involvement)
    """
    if not isinstance(fields_data, dict):
        return None
    data = fields_data.get("fields") if isinstance(fields_data.get("fields"), dict) else fields_data
    if not isinstance(data, dict):
        return None

    # Affiliations
    affiliations = []
    raw_affil = (
        data.get("author_affiliation")
        or data.get("affiliations")
        or data.get("affiliation")
        or data.get("institutions")
    )
    if isinstance(raw_affil, list):
        affiliations = [str(a).strip() for a in raw_affil if str(a).strip()]
    elif isinstance(raw_affil, str) and raw_affil.strip():
        affiliations = [a.strip() for a in re.split(r'[,;]\s*', raw_affil) if a.strip()]

    # Author contacts / emails
    contacts = []
    raw_contacts = (
        data.get("author_contacts")
        or data.get("contacts")
        or data.get("emails")
        or data.get("email")
        or data.get("author_emails")
    )
    if isinstance(raw_contacts, list):
        contacts = [str(c).strip() for c in raw_contacts if str(c).strip()]
    elif isinstance(raw_contacts, str) and raw_contacts.strip():
        contacts = [c.strip() for c in re.split(r'[,;]\s*', raw_contacts) if c.strip()]

    # Funding entities
    funding = []
    raw_funding = (
        data.get("funding_entities")
        or data.get("funding")
        or data.get("grants")
        or data.get("sponsors")
    )
    if isinstance(raw_funding, list):
        funding = [str(f).strip() for f in raw_funding if str(f).strip()]
    elif isinstance(raw_funding, str) and raw_funding.strip():
        funding = [f.strip() for f in re.split(r'[,;]\s*', raw_funding) if f.strip()]

    # Codebase artifact link
    code_link = (
        data.get("codebase_artifact_link")
        or data.get("artifact_link")
        or data.get("code_repository")
        or data.get("repository")
        or data.get("code_url")
        or data.get("zenodo_link")
    )
    if code_link and not isinstance(code_link, str):
        code_link = str(code_link)

    # Specific boolean/string risk flags
    schwarz_ecosystem = data.get("schwarz_ecosystem_affiliation") or data.get("schwarz_fit")
    gdpr_concerns = data.get("gdpr_concerns") or data.get("gdpr_sovereignty") or data.get("gdpr")
    competitor_involvement = data.get("competitor_involvement") or data.get("competitor_risk")
    risk_score = data.get("risk_score")
    risk_assessment = data.get("risk_score_assessment") or data.get("risk_assessment")

    # Format badges/flags
    flags = []
    if gdpr_concerns is not None:
        val_str = str(gdpr_concerns).strip()
        is_safe = bool(re.search(r'^(no|none|false|low)\b', val_str, re.I))
        flags.append({
            "key": "gdpr",
            "label": "GDPR Sovereignty",
            "value": val_str,
            "status": "safe" if is_safe else "warn",
        })
    if schwarz_ecosystem is not None:
        val_str = str(schwarz_ecosystem).strip()
        has_affil = bool(re.search(r'^(yes|true|affiliated)\b', val_str, re.I))
        flags.append({
            "key": "schwarz_ecosystem",
            "label": "Schwarz Ecosystem",
            "value": val_str,
            "status": "highlight" if has_affil else "neutral",
        })
    if competitor_involvement is not None:
        val_str = str(competitor_involvement).strip()
        has_comp = bool(re.search(r'^(yes|true|high|present)\b', val_str, re.I))
        flags.append({
            "key": "competitor",
            "label": "Competitor Involvement",
            "value": val_str,
            "status": "warn" if has_comp else "safe",
        })

    return {
        "raw": data,
        "affiliations": affiliations,
        "author_contacts": contacts,
        "funding_entities": funding,
        "codebase_artifact_link": code_link,
        "schwarz_ecosystem_affiliation": str(schwarz_ecosystem) if schwarz_ecosystem is not None else None,
        "gdpr_concerns": str(gdpr_concerns) if gdpr_concerns is not None else None,
        "competitor_involvement": str(competitor_involvement) if competitor_involvement is not None else None,
        "risk_score": float(risk_score) if isinstance(risk_score, (int, float)) else None,
        "risk_score_assessment": str(risk_assessment) if risk_assessment else None,
        "flags": flags,
    }


def extract_rich_dimension_details(
    fields_data: dict,
    primary_metric: dict,
    secondary_metrics: list,
    max_val: int = 100,
    is_trl: bool = False,
    order: list = None,
) -> dict:
    """
    Extracts structured visual elements matching the UI design specs:
      - rationale: main markdown explanation / justification
      - evidence: list of quoted text snippets
      - band: band pill badge (e.g. 'TRL 4 — Technology validated in lab')
      - facets: list of sub-scores with progress bars (e.g. Novelty 68, Significance 72)
      - texts: titled prose insight sections (e.g. 'Research quality insight')
      - facts: key-value definition list entries (e.g. 'Confidence': 'HIGH', 'Core technology': '...')
      - lists: lists of strings (e.g. 'Key contributions': [...])
    """
    if not isinstance(fields_data, dict):
        return {
            'rationale': None,
            'evidence': [],
            'band': None,
            'facets': [],
            'texts': [],
            'facts': [],
            'lists': [],
        }

    data = fields_data.get("fields") if isinstance(fields_data.get("fields"), dict) else fields_data
    if not isinstance(data, dict):
        data = {}

    used = set()
    primary_k = (primary_metric.get("key") or "").strip().lower()
    if primary_k:
        used.add(primary_k)

    # 1. Rationale & Evidence
    rationale = None
    evidence = []
    # Check if matched primary field was a dict containing evidence / rationale
    matched_obj = data.get(primary_k)
    if isinstance(matched_obj, dict):
        if "rationale" in matched_obj and isinstance(matched_obj["rationale"], str):
            rationale = matched_obj["rationale"].strip()
        if "evidence" in matched_obj:
            ev_val = matched_obj["evidence"]
            if isinstance(ev_val, list):
                evidence.extend([str(q.get("quote") if isinstance(q, dict) else q).strip() for q in ev_val if q])
            elif isinstance(ev_val, str) and ev_val.strip():
                evidence.append(ev_val.strip())

    # Scan data for rationale and evidence
    for k, v in data.items():
        k_norm = k.strip().lower()
        if k_norm in used:
            continue
        val = v.get("value") if (isinstance(v, dict) and "value" in v) else v

        if RATIONALE_RE.search(k_norm) and isinstance(val, str) and val.strip():
            if not rationale:
                rationale = val.strip()
                used.add(k_norm)
        elif EVIDENCE_RE.search(k_norm):
            if isinstance(val, list):
                quotes = [str(q.get("quote") if isinstance(q, dict) else q).strip() for q in val if q]
                evidence.extend([q for q in quotes if q])
                used.add(k_norm)
            elif isinstance(val, str) and val.strip():
                evidence.append(val.strip())
                used.add(k_norm)

    # 2. Band label (e.g. 'TRL 4 — Technology validated in lab')
    band = None
    for k, v in data.items():
        k_norm = k.strip().lower()
        if k_norm in used:
            continue
        val = v.get("value") if (isinstance(v, dict) and "value" in v) else v
        if isinstance(val, str) and (BAND_RE.search(k_norm) or k_norm in ("band", "label", "trl_band", "trl_label")):
            s = val.strip()
            if s:
                band = s
                used.add(k_norm)
                break

    # 3. Facets (sub-scores with progress bars)
    facets = []
    seen_facet_keys = set()
    facet_order = [k.strip().lower() for k in (order or [])]

    # Include numeric secondary metrics first
    for m in secondary_metrics:
        mk = m.get("key")
        mk_norm = mk.strip().lower() if mk else ""
        if mk_norm and m.get("is_numeric") and m.get("numeric_value") is not None:
            # Look for assessment twin
            twin_text = None
            twin_candidates = [
                f"{mk_norm}_assessment",
                re.sub(r'_score$', '_assessment', mk_norm),
            ]
            for tc in twin_candidates:
                if tc in data:
                    t_val = data[tc]
                    t_val_str = t_val.get("value") if isinstance(t_val, dict) else t_val
                    if isinstance(t_val_str, str) and t_val_str.strip():
                        twin_text = t_val_str.strip()
                        used.add(tc)
                        break

            facets.append({
                "key": mk,
                "name": humanise_field_label(mk),
                "value": m["numeric_value"],
                "max": max_val,
                "text": twin_text,
            })
            seen_facet_keys.add(mk_norm)
            used.add(mk_norm)

    # Also scan data for any other _score fields that weren't in secondary_metrics
    for k, v in data.items():
        k_norm = k.strip().lower()
        if k_norm in used or k_norm in seen_facet_keys:
            continue
        val = v.get("value") if (isinstance(v, dict) and "value" in v) else v
        if FACET_KEY_RE.search(k_norm):
            num_v = None
            try:
                f_v = float(val)
                if math.isfinite(f_v):
                    num_v = int(f_v) if f_v.is_integer() else round(f_v, 2)
            except (ValueError, TypeError):
                pass

            if num_v is not None:
                twin_text = None
                twin_k = re.sub(r'_score$', '_assessment', k_norm)
                if twin_k in data:
                    t_val = data[twin_k]
                    t_val_str = t_val.get("value") if isinstance(t_val, dict) else t_val
                    if isinstance(t_val_str, str) and t_val_str.strip():
                        twin_text = t_val_str.strip()
                        used.add(twin_k)

                facets.append({
                    "key": k,
                    "name": humanise_field_label(k),
                    "value": num_v,
                    "max": max_val,
                    "text": twin_text,
                })
                seen_facet_keys.add(k_norm)
                used.add(k_norm)

    # Sort facets by definition order if given
    if facet_order:
        def facet_sort_key(f):
            k = f["key"].strip().lower()
            try:
                return facet_order.index(k)
            except ValueError:
                return len(facet_order)
        facets.sort(key=facet_sort_key)

    # 4. Texts, Lists, Facts
    texts = []
    lists = []
    facts = []

    ignored_keys = {
        "confidence_score", "confidence_level", "confidence_method",
        "validation_status", "validation_errors", "error", "postprocessing_error",
        "fields",
    }

    for k, v in data.items():
        k_norm = k.strip().lower()
        if k_norm in used or k_norm in ignored_keys:
            continue
        val = v.get("value") if (isinstance(v, dict) and "value" in v) else v
        label = humanise_field_label(k)

        # Lists
        if isinstance(val, list):
            items = [str(i).strip() for i in val if str(i).strip()]
            if items:
                lists.append({"key": k, "name": label, "items": items})
                used.add(k_norm)
            continue

        # Booleans -> Facts
        if isinstance(val, bool):
            facts.append({"key": k, "name": label, "value": val})
            used.add(k_norm)
            continue

        # Strings
        if isinstance(val, str):
            s = val.strip()
            if not s:
                continue
            if SENTENCE_RE.search(s) or len(s) > 80:
                texts.append({"key": k, "name": label, "value": s})
            else:
                facts.append({"key": k, "name": label, "value": s})
            used.add(k_norm)
            continue

        # Numbers
        if isinstance(val, (int, float)) and math.isfinite(val):
            if LEVEL_KEY_RE.search(k_norm) and primary_metric.get("numeric_value") == val:
                continue
            num_display = int(val) if float(val).is_integer() else round(float(val), 2)
            facts.append({"key": k, "name": label, "value": str(num_display)})
            used.add(k_norm)

    return {
        "rationale": rationale,
        "evidence": evidence if evidence else None,
        "band": band,
        "facets": facets if facets else None,
        "texts": texts if texts else None,
        "lists": lists if lists else None,
        "facts": facts if facts else None,
    }


def build_paper_scorecard_data(paper: Paper, pipeline_run_id=None, request=None) -> dict:
    """
    Builds the dynamic, schema-driven Paper Scorecard data dictionary.
    Usable by both REST API (GET /api/papers/{id}/scorecard/) and MCP tools.

    Relying on:
      - JSON Schemas (ExtractionDefinition.response_schema)
      - Exit metrics configuration (ExtractionDefinition.exit_metrics)
      - Postprocessing code (ExtractionDefinition.postprocessing_code)
      - Unflattened extracted payload (Extraction.fields_data)
      - Primary & Secondary (main & auxiliary) metrics structured according to extraction rules
      - Document metadata, run-scoped PaperMetric, and NarrativeReport
    """
    # 1. Resolve target pipeline run
    pr_param = pipeline_run_id
    target_pr = None
    target_pr_id = None

    if pr_param and str(pr_param).lower() not in ('undefined', 'null', ''):
        if str(pr_param).lower() == 'latest':
            target_pr = (
                PipelineRun.objects.filter(workspace=paper.workspace)
                .exclude(status__in=['failed', 'aborted'])
                .order_by('-started_at', '-id')
                .first()
            )
            if not target_pr:
                target_pr = (
                    PipelineRun.objects.filter(workspace=paper.workspace)
                    .order_by('-started_at', '-id')
                    .first()
                )
            if target_pr:
                target_pr_id = target_pr.id
        else:
            try:
                pr_uuid = uuid.UUID(str(pr_param))
                target_pr = PipelineRun.objects.filter(id=pr_uuid, workspace=paper.workspace).first()
                if target_pr:
                    target_pr_id = target_pr.id
                else:
                    target_pr_id = pr_uuid
            except (ValueError, TypeError):
                target_pr_id = None

    # Fallback to paper's newest run if not specified
    if not target_pr_id:
        latest_m = paper.metrics.order_by('-created_at').first()
        if latest_m and latest_m.pipeline_run_id:
            target_pr_id = latest_m.pipeline_run_id
            target_pr = latest_m.pipeline_run

    target_metric = None
    if target_pr_id:
        target_metric = paper.metrics.filter(pipeline_run_id=target_pr_id).first()
    if not target_metric:
        target_metric = paper.metrics.order_by('-created_at').first()

    paper_serializer = PaperSerializer(paper, context={'request': request, 'pipeline_run': target_pr_id})
    paper_data = paper_serializer.data

    extractions = list(
        Extraction.objects.filter(paper=paper)
        .select_related('extraction_definition')
        .order_by('-created_at')
    )
    definitions = list(
        ExtractionDefinition.objects.filter(workspace=paper.workspace, is_active=True)
        .order_by('created_at')
    )

    raw_authors = paper.authors or ''
    authors_list = [a.strip() for a in raw_authors.split(',') if a.strip()] if raw_authors else []

    # Format signal_score_details
    ssd = (
        target_metric.signal_score_details
        if (target_metric and target_metric.signal_score_details)
        else paper_data.get('signal_score_details')
    )
    formatted_ssd = None
    if isinstance(ssd, dict) and ssd:
        formatted_ssd = {
            'variables': ssd.get('variables') if isinstance(ssd.get('variables'), dict) else {},
            'code_snippet': ssd.get('code_snippet') or None,
            'calculated_at': ssd.get('calculated_at') or None,
            'error': ssd.get('error') or None,
        }

    # 2. Dynamic Schemas & Extraction Definitions
    definitions_data = []
    for d in definitions:
        has_post = bool(d.postprocessing_code and d.postprocessing_code.strip())
        exit_list = d.get_exit_metrics_list()
        prim_exit = d.get_primary_exit_metric()
        d_slug = d.name.lower().replace(' ', '_').replace('-', '_')

        if has_post:
            main_key = f"{d_slug}_postprocessed"
            aux_keys = exit_list
        else:
            main_key = exit_list[0] if exit_list else prim_exit
            aux_keys = exit_list[1:] if len(exit_list) > 1 else []

        definitions_data.append({
            'id': str(d.id),
            'name': d.name,
            'key': d_slug,
            'system_prompt': d.system_prompt,
            'user_prompt_template': d.user_prompt_template,
            'response_schema': d.response_schema,
            'exit_metrics': exit_list,
            'primary_exit_metric': prim_exit,
            'has_postprocessing': has_post,
            'postprocessing_code': d.postprocessing_code or None,
            'primary_metric_key': main_key,
            'main_metric_key': main_key,
            'secondary_metric_keys': aux_keys,
            'auxiliary_metric_keys': aux_keys,
            'llm_model': d.llm_model,
            'is_active': d.is_active,
            'version': d.version,
        })

    # 3. Dynamic Extractions (raw unflattened fields_data, structured primary & secondary metrics, definition schema)
    extractions_data = []
    risk_and_affiliation_info = None

    for e in extractions:
        d_obj = e.extraction_definition
        primary_metric, secondary_metrics, has_post = extract_metrics_for_extraction(e, d_obj)
        is_risk = is_risk_dimension(d_obj.name if d_obj else e.category, (d_obj.name if d_obj else e.category or '').lower().replace(' ', '_'))
        if is_risk and e.fields_data and not risk_and_affiliation_info:
            risk_and_affiliation_info = extract_risk_and_affiliation(e.fields_data)

        def_dict = None
        if d_obj:
            exit_list = d_obj.get_exit_metrics_list()
            prim_exit = d_obj.get_primary_exit_metric()
            d_slug = d_obj.name.lower().replace(' ', '_').replace('-', '_')
            if has_post:
                main_key = f"{d_slug}_postprocessed"
                aux_keys = exit_list
            else:
                main_key = exit_list[0] if exit_list else prim_exit
                aux_keys = exit_list[1:] if len(exit_list) > 1 else []

            def_dict = {
                'id': str(d_obj.id),
                'name': d_obj.name,
                'key': d_slug,
                'response_schema': d_obj.response_schema,
                'exit_metrics': exit_list,
                'primary_exit_metric': prim_exit,
                'has_postprocessing': has_post,
                'postprocessing_code': d_obj.postprocessing_code or None,
                'primary_metric_key': main_key,
                'main_metric_key': main_key,
                'secondary_metric_keys': aux_keys,
                'auxiliary_metric_keys': aux_keys,
                'llm_model': d_obj.llm_model,
                'is_active': d_obj.is_active,
            }

        extractions_data.append({
            'id': str(e.id),
            'workspace_id': str(e.workspace_id),
            'paper_id': str(e.paper_id),
            'extraction_definition_id': str(e.extraction_definition_id) if e.extraction_definition_id else None,
            'category': e.category,
            'is_risk_and_affiliation': is_risk,
            'fields_data': e.fields_data,
            'exit_metric': e.exit_metric,
            'has_postprocessing': has_post,
            'primary_metric': primary_metric,
            'secondary_metrics': secondary_metrics,
            'main_metric': primary_metric,
            'auxiliary_metrics': secondary_metrics,
            'confidence_score': float(e.confidence_score) if e.confidence_score is not None else None,
            'confidence_method': e.confidence_method,
            'validation_status': e.validation_status,
            'review_required': bool(e.review_required),
            'is_hitl_validated': bool(e.is_hitl_validated),
            'model': (
                e.version_info.get('llm_model')
                if isinstance(e.version_info, dict)
                else (d_obj.llm_model if d_obj else None)
            ),
            'version_info': e.version_info,
            'created_at': e.created_at.isoformat(),
            'definition': def_dict,
        })

    # 4. Workspace summary
    ws_summary = {
        'id': str(paper.workspace.id),
        'name': paper.workspace.name,
        'definitions': definitions_data,
        'scrapers_count': paper.workspace.scrapers.count(),
    }

    # 5. Associated NarrativeReport
    report = None
    if target_pr_id:
        report = NarrativeReport.objects.filter(pipeline_run_id=target_pr_id).first()
    if not report:
        report = NarrativeReport.objects.filter(workspace=paper.workspace).order_by('-created_at').first()

    narrative_report_data = None
    if report:
        narrative_report_data = {
            'id': str(report.id),
            'pipeline_run_id': str(report.pipeline_run_id) if report.pipeline_run_id else None,
            'workspace_id': str(report.workspace_id),
            'title': report.title,
            'content_markdown': report.content_markdown,
            'content_latex': report.content_latex or None,
            'bibtex_content': report.bibtex_content or None,
            'compiled_pdf_path': report.compiled_pdf_path or None,
            'refinement_depth': report.refinement_depth,
            'created_at': report.created_at.isoformat(),
        }

    # 6. Run-scoped PaperMetric
    metric_data = None
    if target_metric:
        metric_data = {
            'id': str(target_metric.id),
            'paper_id': str(target_metric.paper_id),
            'pipeline_run_id': str(target_metric.pipeline_run_id) if target_metric.pipeline_run_id else None,
            'workspace_id': str(target_metric.workspace_id),
            'screening_status': target_metric.screening_status,
            'screening_reasoning': target_metric.latest_screening_reasoning,
            'abstract_screening_reasoning': target_metric.abstract_screening_reasoning,
            'full_text_screening_reasoning': target_metric.full_text_screening_reasoning,
            'signal_score': float(target_metric.signal_score) if target_metric.signal_score is not None else None,
            'signal_score_details': formatted_ssd,
            'metrics_data': target_metric.metrics_data or {},
            'is_evaluation_benchmark': bool(target_metric.is_evaluation_benchmark),
            'evaluation_label': target_metric.evaluation_label,
            'created_at': target_metric.created_at.isoformat(),
        }

    # 7. Dynamic dimensions with rich layout details (facets, texts, facts, lists, rationale, evidence)
    ext_by_def = {}
    for e in extractions:
        if e.extraction_definition_id and e.extraction_definition_id not in ext_by_def:
            ext_by_def[e.extraction_definition_id] = e

    dimensions = []
    for d in definitions:
        e = ext_by_def.get(d.id)
        if not d.is_active and not e:
            continue

        is_trl = bool(re.search(r'\btrl\b', d.name, re.IGNORECASE))
        if is_trl:
            max_val = 9
        elif re.search(r'\(1-10\)', d.name):
            max_val = 10
        else:
            max_val = 100

        primary_metric, secondary_metrics, has_post = extract_metrics_for_extraction(e, d)
        dim_key = d.name.lower().replace(' ', '_')
        is_risk = is_risk_dimension(d.name, dim_key)

        num_val = primary_metric.get('numeric_value')
        raw = primary_metric.get('raw') or '—'
        if num_val is not None and is_trl:
            num_val = max(1.0, min(9.0, float(num_val)))
            num_val = int(num_val) if float(num_val).is_integer() else round(float(num_val), 2)

        model_name = (
            (e.version_info.get('llm_model') if (e and isinstance(e.version_info, dict)) else None)
            or d.llm_model
        )

        rich_details = extract_rich_dimension_details(
            fields_data=e.fields_data if e else {},
            primary_metric=primary_metric,
            secondary_metrics=secondary_metrics,
            max_val=max_val,
            is_trl=is_trl,
            order=d.get_exit_metrics_list(),
        )

        dim_item = {
            'key': dim_key,
            'label': d.name,
            'name': d.name,
            'definition_id': str(d.id),
            'value': num_val,
            'raw': raw,
            'max': max_val,
            'is_trl': is_trl,
            'is_risk_and_affiliation': is_risk,
            'has_postprocessing': has_post,
            'primary_metric': primary_metric,
            'secondary_metrics': secondary_metrics,
            'main_metric': primary_metric,
            'auxiliary_metrics': secondary_metrics,
            'confidence': float(e.confidence_score) if (e and e.confidence_score is not None) else None,
            'validation_status': e.validation_status if e else 'pending',
            'review_required': bool(e.review_required) if e else False,
            'is_hitl': bool(e.is_hitl_validated) if e else False,
            'extraction_id': str(e.id) if e else None,
            'model': model_name,
            'fields_data': e.fields_data if e else None,
            'response_schema': d.response_schema,
            'exit_metrics': d.get_exit_metrics_list(),
            'rationale': rich_details['rationale'],
            'evidence': rich_details['evidence'],
            'band': rich_details['band'],
            'facets': rich_details['facets'],
            'texts': rich_details['texts'],
            'facts': rich_details['facts'],
            'lists': rich_details['lists'],
        }
        dimensions.append(dim_item)

    matched_ext_ids = {e.id for e in ext_by_def.values() if e}
    for e in extractions:
        if e.id not in matched_ext_ids:
            cat_name = e.category or 'Custom Extraction'
            is_trl = bool(re.search(r'\btrl\b', cat_name, re.IGNORECASE))
            max_val = 9 if is_trl else 100
            dim_key = cat_name.lower().replace(' ', '_')
            is_risk = is_risk_dimension(cat_name, dim_key)

            primary_metric, secondary_metrics, has_post = extract_metrics_for_extraction(e, None)
            num_val = primary_metric.get('numeric_value')
            raw = primary_metric.get('raw') or '—'
            if num_val is not None and is_trl:
                num_val = max(1.0, min(9.0, float(num_val)))
                num_val = int(num_val) if float(num_val).is_integer() else round(float(num_val), 2)

            rich_details = extract_rich_dimension_details(
                fields_data=e.fields_data,
                primary_metric=primary_metric,
                secondary_metrics=secondary_metrics,
                max_val=max_val,
                is_trl=is_trl,
                order=[],
            )

            dim_item = {
                'key': dim_key,
                'label': cat_name,
                'name': cat_name,
                'definition_id': str(e.extraction_definition_id) if e.extraction_definition_id else None,
                'value': num_val,
                'raw': raw,
                'max': max_val,
                'is_trl': is_trl,
                'is_risk_and_affiliation': is_risk,
                'has_postprocessing': has_post,
                'primary_metric': primary_metric,
                'secondary_metrics': secondary_metrics,
                'main_metric': primary_metric,
                'auxiliary_metrics': secondary_metrics,
                'confidence': float(e.confidence_score) if e.confidence_score is not None else None,
                'validation_status': e.validation_status,
                'review_required': bool(e.review_required),
                'is_hitl': bool(e.is_hitl_validated),
                'extraction_id': str(e.id),
                'model': e.version_info.get('llm_model') if isinstance(e.version_info, dict) else None,
                'fields_data': e.fields_data,
                'response_schema': None,
                'exit_metrics': [],
                'rationale': rich_details['rationale'],
                'evidence': rich_details['evidence'],
                'band': rich_details['band'],
                'facets': rich_details['facets'],
                'texts': rich_details['texts'],
                'facts': rich_details['facts'],
                'lists': rich_details['lists'],
            }
            dimensions.append(dim_item)

    # 8. Paper representation
    scored_paper = {
        'id': str(paper.id),
        'workspace_id': str(paper.workspace_id),
        'pipeline_run_id': str(target_pr_id) if target_pr_id else (paper_data.get('pipeline_run') or ''),
        'pipeline_run_name': target_pr.name if (target_pr and hasattr(target_pr, 'name')) else paper_data.get('pipeline_run_name'),
        'title': paper.title,
        'authors': authors_list,
        'authors_raw': raw_authors,
        'abstract': paper.abstract or '',
        'doi': paper.doi or None,
        'arxiv_id': paper.arxiv_id or None,
        'source': paper.source_database or '',
        'screening_status': target_metric.screening_status if target_metric else (paper_data.get('screening_status') or 'pending'),
        'screening_reasoning': (target_metric.latest_screening_reasoning if target_metric else None) or paper_data.get('screening_reasoning') or None,
        'abstract_screening_reasoning': target_metric.abstract_screening_reasoning if target_metric else paper_data.get('abstract_screening_reasoning'),
        'full_text_screening_reasoning': target_metric.full_text_screening_reasoning if target_metric else paper_data.get('full_text_screening_reasoning'),
        'signal_score': float(target_metric.signal_score) if (target_metric and target_metric.signal_score is not None) else paper_data.get('signal_score'),
        'signal_score_details': formatted_ssd,
        'pdf_key': paper.original_pdf_path or None,
        'markdown_key': paper.converted_md_path or None,
        'pdf_url': paper.source_url,
        'source_url': paper.source_url,
        'is_benchmark': bool(target_metric.is_evaluation_benchmark if target_metric else paper_data.get('is_evaluation_benchmark', False)),
        'evaluation_label': (target_metric.evaluation_label if target_metric else None) or paper_data.get('evaluation_label'),
        'published_date': paper_data.get('published_date'),
        'created_at': paper.created_at.isoformat(),
        'dimensions': dimensions,
        'risk_and_affiliation': risk_and_affiliation_info,
    }

    return {
        'workspace': ws_summary,
        'paper': scored_paper,
        'definitions': definitions_data,
        'extractions': extractions_data,
        'metric': metric_data,
        'narrative_report': narrative_report_data,
    }


def build_paper_scorecard_response(paper: Paper, request) -> Response:
    """
    Builds the dynamic, schema-driven Paper Scorecard DRF Response for GET /api/papers/{id}/scorecard/.
    """
    pr_param = (
        request.query_params.get('pipeline_run')
        or request.query_params.get('pipeline_run_id')
        or request.query_params.get('run')
        or request.query_params.get('run_id')
    )
    data = build_paper_scorecard_data(paper, pipeline_run_id=pr_param, request=request)
    return Response(data)
