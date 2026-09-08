import math
import re
from typing import Tuple

from research_intelligence.models import Extraction, ExtractionDefinition

RATIONALE_RE = re.compile(r'(reason|rationale|justif)', re.IGNORECASE)
EVIDENCE_RE = re.compile(r'(quote|^evidence$|_evidence$)', re.IGNORECASE)
BAND_RE = re.compile(r'(_band$|_label$|^band$|^label$)', re.IGNORECASE)
FACET_KEY_RE = re.compile(r'_score$', re.IGNORECASE)
ASSESSMENT_KEY_RE = re.compile(r'_assessment$', re.IGNORECASE)
LEVEL_KEY_RE = re.compile(r'_level$', re.IGNORECASE)
SENTENCE_RE = re.compile(r'[.!?](\s|$)')


def _unwrap_val(v):
    """
    Unwraps values that might be nested as {'value': ...} from extraction DTOs or LLM outputs.
    Handles recursive nesting safely.
    """
    if isinstance(v, dict) and 'value' in v:
        return _unwrap_val(v['value'])
    return v


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
    """Formats a metric key into a human-readable title label."""
    if not key:
        return ""
    clean = re.sub(r'(_postprocessed|_score|_metric)$', '', key, flags=re.IGNORECASE)
    words = clean.replace("-", "_").split("_")
    acronyms = {"trl": "TRL", "gdpr": "GDPR", "llm": "LLM", "api": "API", "nlp": "NLP", "ai": "AI"}
    formatted = []
    for w in words:
        wl = w.lower()
        if wl in acronyms:
            formatted.append(acronyms[wl])
        else:
            formatted.append(w.capitalize())
    return " ".join(formatted)


def build_metric_entry(key: str, fields_data: dict, source: str = "exit_metric", label_override: str = None) -> dict:
    """Builds a structured metric dictionary with type inspection and numeric parsing."""
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


def extract_metrics_for_extraction(e: Extraction, d: ExtractionDefinition = None) -> Tuple[dict, list, bool]:
    """
    Extracts primary_metric (main_metric) and secondary_metrics (auxiliary_metrics).
    Handles:
      - Rule 1: No postprocessing -> first exit metric is primary, rest are secondary
      - Rule 2: Postprocessing code present -> handles 1 key unpacked vs >1 keys as secondary metrics
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


def is_risk_dimension(name: str = "", key: str = "") -> bool:
    """Identifies whether a dimension or extraction represents Risk and Affiliation Flagging."""
    target = f"{name} {key}".lower()
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

    # Affiliations (unwrapping nested value dicts)
    affiliations = []
    raw_affil = _unwrap_val(
        data.get("author_affiliation")
        or data.get("affiliations")
        or data.get("affiliation")
        or data.get("institutions")
        or data.get("institution")
    )
    if isinstance(raw_affil, list):
        affiliations = [str(a).strip() for a in raw_affil if str(a).strip()]
    elif isinstance(raw_affil, str) and raw_affil.strip():
        affiliations = [a.strip() for a in re.split(r'[,;]\s*', raw_affil) if a.strip()]

    # Author contacts / emails
    contacts = []
    raw_contacts = _unwrap_val(
        data.get("author_contacts")
        or data.get("contacts")
        or data.get("emails")
        or data.get("email")
        or data.get("author_emails")
        or data.get("correspondence")
    )
    if isinstance(raw_contacts, list):
        contacts = [str(c).strip() for c in raw_contacts if str(c).strip()]
    elif isinstance(raw_contacts, str) and raw_contacts.strip():
        contacts = [c.strip() for c in re.split(r'[,;]\s*', raw_contacts) if c.strip()]

    # Funding entities
    funding = []
    raw_funding = _unwrap_val(
        data.get("funding_entities")
        or data.get("funding")
        or data.get("grants")
        or data.get("sponsors")
        or data.get("grant_agencies")
    )
    if isinstance(raw_funding, list):
        funding = [str(f).strip() for f in raw_funding if str(f).strip()]
    elif isinstance(raw_funding, str) and raw_funding.strip():
        funding = [f.strip() for f in re.split(r'[,;]\s*', raw_funding) if f.strip()]

    # Codebase artifact link with extended aliases
    code_link = _unwrap_val(
        data.get("codebase_artifact_link")
        or data.get("artifact_link")
        or data.get("code_repository")
        or data.get("repository")
        or data.get("code_url")
        or data.get("github_url")
        or data.get("zenodo_link")
        or data.get("dataset_url")
        or data.get("repository_url")
    )
    if code_link and not isinstance(code_link, str):
        code_link = str(code_link)

    # Specific boolean/string risk flags
    schwarz_ecosystem = _unwrap_val(data.get("schwarz_ecosystem_affiliation") or data.get("schwarz_fit") or data.get("schwarz_affiliation"))
    gdpr_concerns = _unwrap_val(data.get("gdpr_concerns") or data.get("gdpr_sovereignty") or data.get("gdpr") or data.get("data_privacy_concerns"))
    competitor_involvement = _unwrap_val(data.get("competitor_involvement") or data.get("competitor_risk") or data.get("competitor"))
    risk_score = _unwrap_val(data.get("risk_score"))
    risk_assessment = _unwrap_val(data.get("risk_score_assessment") or data.get("risk_assessment"))

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

    for k, v in data.items():
        k_norm = k.strip().lower()
        if k_norm in used:
            continue
        val = _unwrap_val(v)

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
        val = _unwrap_val(v)
        if isinstance(val, str) and (BAND_RE.search(k_norm) or k_norm in ("band", "label", "trl_band", "trl_label")):
            s = val.strip()
            if s:
                band = s
                used.add(k_norm)
                break

    # 3. Facets, Texts, Lists, Facts
    facets = []
    texts = []
    lists = []
    facts = []
    seen_facet_keys = set()
    facet_order = [k.strip().lower() for k in (order or [])]

    # Include numeric secondary metrics first
    for m in secondary_metrics:
        mk = m.get("key")
        mk_norm = mk.strip().lower() if mk else ""
        if mk_norm and m.get("is_numeric") and m.get("numeric_value") is not None:
            num_v = m["numeric_value"]
            f_max = max_val
            # SOTA: support 0.0 to 1.0 scale
            if 0.0 <= float(num_v) <= 1.0 and any(kw in mk_norm for kw in ("confidence", "probability", "prob", "ratio", "rate")):
                f_max = 1

            # Look for assessment twin
            twin_text = None
            twin_candidates = [
                f"{mk_norm}_assessment",
                re.sub(r'_score$', '_assessment', mk_norm),
            ]
            for tc in twin_candidates:
                if tc in data:
                    t_val = _unwrap_val(data[tc])
                    if isinstance(t_val, str) and t_val.strip():
                        twin_text = t_val.strip()
                        used.add(tc)
                        break

            facets.append({
                "key": mk,
                "name": humanise_field_label(mk),
                "value": num_v,
                "max": f_max,
                "text": twin_text,
            })
            seen_facet_keys.add(mk_norm)
            used.add(mk_norm)
        elif mk_norm and not m.get("is_numeric"):
            raw_v = m.get("raw") or m.get("value")
            if raw_v and str(raw_v) != "—":
                facts.append({
                    "key": mk,
                    "name": humanise_field_label(mk),
                    "value": str(raw_v),
                })
                used.add(mk_norm)

    # Scan data for any other _score fields that weren't in secondary_metrics
    for k, v in data.items():
        k_norm = k.strip().lower()
        if k_norm in used or k_norm in seen_facet_keys:
            continue
        val = _unwrap_val(v)
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
                    t_val = _unwrap_val(data[twin_k])
                    if isinstance(t_val, str) and t_val.strip():
                        twin_text = t_val.strip()
                        used.add(twin_k)

                f_max = max_val
                if 0.0 <= float(num_v) <= 1.0 and any(kw in k_norm for kw in ("confidence", "probability", "prob", "ratio", "rate")):
                    f_max = 1

                facets.append({
                    "key": k,
                    "name": humanise_field_label(k),
                    "value": num_v,
                    "max": f_max,
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
    ignored_keys = {
        "confidence_score", "confidence_level", "confidence_method",
        "validation_status", "validation_errors", "error", "postprocessing_error",
        "fields",
    }

    for k, v in data.items():
        k_norm = k.strip().lower()
        if k_norm in used or k_norm in ignored_keys:
            continue
        val = _unwrap_val(v)
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
        "evidence": evidence if evidence else [],
        "band": band or None,
        "facets": facets if facets else [],
        "texts": texts if texts else [],
        "facts": facts if facts else [],
        "lists": lists if lists else [],
    }
