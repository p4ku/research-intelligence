from __future__ import annotations

import math
import re
from typing import Any, Optional, Tuple, Union

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


def _parse_dict_or_json(val):
    """
    Parses val if it is a dictionary, or a string representing a dict (JSON or Python repr).
    Returns dict if parsed, or None.
    """
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        s = val.strip()
        if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except Exception:
                pass
            try:
                import ast
                parsed = ast.literal_eval(s)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except Exception:
                pass
    return None


def _base_metric_key(key: str) -> str:
    """Normalizes a metric key by stripping suffix variations to detect duplicate metrics."""
    if not key:
        return ""
    clean = key.strip().lower().replace(" ", "_").replace("-", "_")
    return re.sub(r'(_postprocessed|_computed|_score|_assessment|_metric|_level|_band)$', '', clean)


def unpack_flag_value(raw_val, flag_name=""):
    """
    Unpacks a flag value that might be:
      - dict or stringified dict like:
        {'status': 'YES', 'matched_institutions': ['TUM']}
        {'status': 'NO', 'matches': None}
        {'status': 'YES', 'matches': ['OpenAI', 'Anthropic']}
      - boolean (True/False)
      - plain string ('YES', 'NO', 'None', etc.)
    Returns:
      (display_str, is_positive_match, items_list, is_dict, parsed_dict)
    """
    if raw_val is None:
        return None, False, [], False, None

    parsed = _parse_dict_or_json(raw_val)
    if isinstance(parsed, dict):
        status = parsed.get("status")
        if status is None:
            status = parsed.get("value") or parsed.get("risk") or parsed.get("level") or parsed.get("flag")

        matches = (
            parsed.get("matched_institutions")
            or parsed.get("matched_competitors")
            or parsed.get("matches")
            or parsed.get("institutions")
            or parsed.get("competitors")
            or parsed.get("details")
            or parsed.get("concerns")
            or parsed.get("reasons")
        )
        items = []
        if isinstance(matches, list):
            items = [str(x).strip() for x in matches if x is not None and str(x).strip() not in ("None", "null", "", "none")]
        elif isinstance(matches, str) and matches.strip() not in ("None", "null", "", "none"):
            items = [matches.strip()]

        stat_str = str(status).strip() if status is not None else ""
        is_pos = bool(re.search(r'^(yes|true|affiliated|high|present)\b', stat_str, re.I)) or (bool(items) and not re.search(r'^(no|false|none|low|safe)\b', stat_str, re.I))
        is_neg = bool(re.search(r'^(no|none|false|low|safe)\b', stat_str, re.I))

        if is_pos:
            display_val = f"YES ({', '.join(items)})" if items else "YES"
            return display_val, True, items, True, parsed
        elif is_neg:
            display_val = "None" if flag_name == "competitor" else "NO"
            return display_val, False, items, True, parsed
        else:
            if items:
                display_val = f"{stat_str} ({', '.join(items)})" if stat_str else ", ".join(items)
                return display_val, bool(items), items, True, parsed
            return stat_str or "—", False, items, True, parsed

    # String / scalar handling
    val_str = str(raw_val).strip()
    is_pos = bool(re.search(r'^(yes|true|affiliated|high|present)\b', val_str, re.I))
    if val_str.lower() in ("no", "none", "false") and flag_name == "competitor":
        val_str = "None"
    return val_str, is_pos, [], False, None


def _unpack_nested_metric_object(parsed_dict: dict, fallback_numeric: Optional[Union[int, float]] = None) -> Tuple[
    Optional[Union[int, float]], Optional[str], Optional[str], list
]:
    """
    Unpacks a structured nested metric object ({score, band, insight, evidence})
    into (item_score, item_band, item_insight, item_evidence).
    """
    if not isinstance(parsed_dict, dict) or not parsed_dict:
        return fallback_numeric, None, None, []

    item_score = None
    s_raw = parsed_dict.get("score") if "score" in parsed_dict else parsed_dict.get("value")
    if s_raw is not None:
        try:
            f_s = float(s_raw)
            if math.isfinite(f_s):
                item_score = int(f_s) if f_s.is_integer() else round(f_s, 2)
        except (ValueError, TypeError):
            pass
    if item_score is None and fallback_numeric is not None:
        item_score = fallback_numeric

    b_raw = parsed_dict.get("band") or parsed_dict.get("label") or parsed_dict.get("level")
    item_band = str(b_raw).strip() if b_raw is not None and str(b_raw).strip() not in ("None", "") else None

    i_raw = (
        parsed_dict.get("insight")
        or parsed_dict.get("rationale")
        or parsed_dict.get("reasoning")
        or parsed_dict.get("explanation")
        or parsed_dict.get("description")
        or parsed_dict.get("text")
        or parsed_dict.get("summary")
    )
    item_insight = str(i_raw).strip() if i_raw is not None and str(i_raw).strip() not in ("None", "") else None

    e_raw = parsed_dict.get("evidence") or parsed_dict.get("quotes") or parsed_dict.get("snippets")
    item_evidence = []
    if isinstance(e_raw, list):
        item_evidence = [str(q.get("quote") if isinstance(q, dict) else q).strip() for q in e_raw if q and str(q).strip() not in ("None", "")]
    elif isinstance(e_raw, str) and e_raw.strip() not in ("None", ""):
        item_evidence = [e_raw.strip()]

    return item_score, item_band, item_insight, item_evidence



def humanise_field_label(key: str, title_case: bool = False) -> str:
    """
    Formats a field or metric key into a human-readable label.
    Preserves common acronyms (TRL, GDPR, LLM, API, NLP, AI, RTL).
    If title_case=True: capitalizes all words (e.g. 'Research Quality Insight').
    If title_case=False: capitalizes first word (e.g. 'Research quality insight').
    """
    if not key:
        return ""
    acronyms = {"trl": "TRL", "gdpr": "GDPR", "llm": "LLM", "api": "API", "nlp": "NLP", "ai": "AI", "rtl": "RTL"}
    clean_key = re.sub(r'(_postprocessed|_score|_assessment|_metric)$', '', key, flags=re.IGNORECASE)
    words = [w for w in clean_key.replace("-", "_").split("_") if w]
    if not words:
        return ""
    res = []
    for i, w in enumerate(words):
        wl = w.lower()
        if wl in acronyms:
            res.append(acronyms[wl])
        elif title_case or i == 0:
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

    parsed_sub = _parse_dict_or_json(actual_val)
    if isinstance(parsed_sub, dict):
        num_val = None
        is_num = False
        s_cand = parsed_sub.get("score") if "score" in parsed_sub else parsed_sub.get("numeric_value")
        if s_cand is None and "value" in parsed_sub:
            s_cand = parsed_sub.get("value")
        if s_cand is not None:
            try:
                f_cand = float(s_cand)
                if math.isfinite(f_cand):
                    num_val = int(f_cand) if f_cand.is_integer() else round(f_cand, 2)
                    is_num = True
            except (ValueError, TypeError):
                pass

        # Derive clean raw_str for dictionary - NEVER return str(actual_val) which leaks Python repr!
        if is_num:
            raw_str = str(num_val)
        else:
            if "status" in parsed_sub or any(k in parsed_sub for k in ("matched_institutions", "matched_competitors", "matches")):
                flag_disp = unpack_flag_value(parsed_sub)[0]
                raw_str = flag_disp or "—"
            elif parsed_sub.get("band"):
                raw_str = str(parsed_sub["band"]).strip()
            elif parsed_sub.get("label"):
                raw_str = str(parsed_sub["label"]).strip()
            elif parsed_sub.get("level"):
                raw_str = str(parsed_sub["level"]).strip()
            elif parsed_sub.get("insight"):
                raw_str = str(parsed_sub["insight"]).strip()
            elif parsed_sub.get("rationale"):
                raw_str = str(parsed_sub["rationale"]).strip()
            elif parsed_sub.get("reasoning"):
                raw_str = str(parsed_sub["reasoning"]).strip()
            elif parsed_sub.get("explanation"):
                raw_str = str(parsed_sub["explanation"]).strip()
            elif parsed_sub.get("text"):
                raw_str = str(parsed_sub["text"]).strip()
            elif parsed_sub.get("summary"):
                raw_str = str(parsed_sub["summary"]).strip()
            else:
                raw_str = "—"

        return actual_val, raw_str, num_val, is_num, True

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
    return humanise_field_label(key, title_case=True)


def build_metric_entry(key: str, fields_data: dict, source: str = "exit_metric", label_override: str = None) -> dict:
    """Builds a structured metric dictionary with type inspection and numeric parsing."""
    actual_val, raw_str, num_val, is_num, found = resolve_field_val(fields_data, key)
    label = label_override or format_metric_label(key)

    if is_num:
        val_entry = num_val
    elif found and raw_str != "—":
        val_entry = raw_str
    elif not isinstance(actual_val, dict) and actual_val is not None:
        val_entry = actual_val
    else:
        val_entry = None

    return {
        "key": key,
        "name": label,
        "label": label,
        "value": val_entry,
        "numeric_value": num_val,
        "raw": raw_str if found else "—",
        "is_numeric": is_num,
        "source": source,
        "dict_value": actual_val if isinstance(actual_val, dict) else None,
    }


def _extract_legacy_postprocessing(
    definition: ExtractionDefinition, fields_data: dict, data_fields: dict, def_slug: str, exit_keys: list
) -> Tuple[dict, list]:
    """
    Helper for legacy definitions with postprocessing code and no explicit frontend metrics.
    Rule 2: Handles 1 key unpacked as primary vs >1 keys as secondary metrics.
    """
    exit_keys_norm = {ek.strip().lower().replace(" ", "_").replace("-", "_") for ek in exit_keys}
    ignored_keys = {
        "confidence_score", "reasoning", "explanation", "validation_status", "error",
        "validation_errors", "postprocessing_error", "fields",
    }
    alias_suffixes = ("_computed",)
    primary_exit = definition.get_primary_exit_metric() if definition else None
    primary_cand = f"{def_slug}_postprocessed"

    # Find candidate postprocessed key in data_fields
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
            inner_k, inner_v = next(iter(raw_post_val.items()))
            target_k = inner_k if (inner_k.endswith("_postprocessed") or not found_post_key) else found_post_key
            primary_metric = build_metric_entry(
                key=target_k,
                fields_data={target_k: inner_v},
                source="postprocessing",
                label_override=format_metric_label(target_k),
            )
        else:
            has_main = any(sub_k.strip().lower().replace(" ", "_").replace("-", "_") == primary_cand for sub_k in raw_post_val.keys())
            if has_main:
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
        post_non_exit = [
            k for k in (data_fields.keys() if isinstance(data_fields, dict) else [])
            if k.strip().lower().replace(" ", "_").replace("-", "_") not in exit_keys_norm
            and k.strip().lower().replace(" ", "_").replace("-", "_") not in ignored_keys
            and not any(k.strip().lower().endswith(sfx) for sfx in alias_suffixes)
        ]
        if len(post_non_exit) == 1:
            single_k = post_non_exit[0]
            primary_metric = build_metric_entry(
                key=single_k,
                fields_data=fields_data,
                source="postprocessing",
                label_override=format_metric_label(single_k),
            )
        elif len(post_non_exit) > 1:
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

    # Collect extra keys from postprocessing and combine with exit metrics
    if isinstance(data_fields, dict):
        already_included = {
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
            if k_norm not in already_included and k_norm not in alias_keys:
                post_extra_metrics.append(build_metric_entry(key=k, fields_data=fields_data, source="postprocessing"))

    seen_sec_bases = {_base_metric_key(primary_metric.get("key") or "")}
    for pm_entry in post_extra_metrics:
        b = _base_metric_key(pm_entry.get("key") or "")
        if b:
            seen_sec_bases.add(b)

    exit_secondary = []
    for ek in exit_keys:
        base_ek = _base_metric_key(ek)
        if base_ek not in seen_sec_bases:
            seen_sec_bases.add(base_ek)
            exit_secondary.append(build_metric_entry(key=ek, fields_data=fields_data, source="exit_metric"))

    return primary_metric, post_extra_metrics + exit_secondary


def extract_metrics_for_extraction(e: Extraction, d: ExtractionDefinition = None) -> Tuple[dict, list, bool]:
    """
    Extracts primary_metric (headline) and secondary_metrics (facets/submeasures).
    1. Explicit Frontend Metrics: Single source of truth if configured on definition.
    2. Legacy Postprocessing (Rule 2): Isolated fallback helper.
    3. Legacy Exit Metrics (Rule 1): First exit metric is primary, rest are secondary.
    4. Ad-hoc fallback: For ad-hoc extractions without definition.
    """
    definition = d or (e.extraction_definition if e else None)
    fields_data = e.fields_data if (e and isinstance(e.fields_data, dict)) else {}
    data_fields = fields_data.get("fields") if isinstance(fields_data.get("fields"), dict) else fields_data

    has_postprocessing = bool(
        definition
        and definition.postprocessing_code
        and definition.postprocessing_code.strip()
    )

    # Dynamic on-the-fly postprocessing evaluation if configured on definition and missing from fields_data
    if has_postprocessing and isinstance(data_fields, dict):
        needs_eval = False
        if definition and definition.has_explicit_frontend_metrics():
            prim_k = definition.get_primary_frontend_metric()
            sec_keys = definition.get_secondary_frontend_metrics_list()
            needed_keys = ([prim_k] if prim_k else []) + sec_keys
            norm_keys = {k.strip().lower().replace(" ", "_").replace("-", "_") for k in data_fields.keys()}
            if any(nk and nk.strip().lower().replace(" ", "_").replace("-", "_") not in norm_keys for nk in needed_keys):
                needs_eval = True
        else:
            def_slug = (
                definition.name.lower().replace(" ", "_").replace("-", "_")
                if definition
                else ((e.category or "extraction").lower().replace(" ", "_").replace("-", "_") if e else "extraction")
            )
            norm_keys = {k.strip().lower().replace(" ", "_").replace("-", "_") for k in data_fields.keys()}
            if f"{def_slug}_postprocessed" not in norm_keys and not any(k.endswith("_postprocessed") for k in norm_keys):
                needs_eval = True

        if needs_eval:
            try:
                from ..utils.sandbox import execute_sandboxed_postprocessing
                post_res = execute_sandboxed_postprocessing(
                    code_snippet=definition.postprocessing_code,
                    fields_data=data_fields,
                    timeout_seconds=2.0,
                )
                if isinstance(post_res, dict):
                    if isinstance(fields_data, dict) and "fields" in fields_data and isinstance(fields_data["fields"], dict):
                        fields_data = dict(fields_data)
                        fields_data["fields"] = dict(fields_data["fields"])
                        fields_data["fields"].update(post_res)
                        data_fields = fields_data["fields"]
                    else:
                        fields_data = dict(fields_data) if isinstance(fields_data, dict) else {}
                        fields_data.update(post_res)
                        data_fields = fields_data
                    if e:
                        e.fields_data = fields_data
                elif post_res is not None:
                    def_slug = (
                        definition.name.lower().replace(" ", "_").replace("-", "_")
                        if definition
                        else "extraction"
                    )
                    cand_k = f"{def_slug}_postprocessed"
                    if isinstance(fields_data, dict) and "fields" in fields_data and isinstance(fields_data["fields"], dict):
                        fields_data = dict(fields_data)
                        fields_data["fields"] = dict(fields_data["fields"])
                        fields_data["fields"][cand_k] = post_res
                        data_fields = fields_data["fields"]
                    else:
                        fields_data = dict(fields_data) if isinstance(fields_data, dict) else {}
                        fields_data[cand_k] = post_res
                        data_fields = fields_data
                    if e:
                        e.fields_data = fields_data
            except Exception:
                pass

    # 1. New Explicit Architecture: Single source of truth if configured
    if definition and definition.has_explicit_frontend_metrics():
        explicit_prim_key = definition.get_primary_frontend_metric()
        primary_metric = (
            build_metric_entry(
                key=explicit_prim_key,
                fields_data=fields_data,
                source="frontend_metric",
                label_override=format_metric_label(explicit_prim_key),
            )
            if explicit_prim_key
            else None
        )

        explicit_sec_keys = definition.get_secondary_frontend_metrics_list()
        secondary_metrics = []
        for sk in explicit_sec_keys:
            if explicit_prim_key and sk.strip().lower() == explicit_prim_key.strip().lower():
                continue
            secondary_metrics.append(
                build_metric_entry(key=sk, fields_data=fields_data, source="frontend_metric")
            )
        return primary_metric, secondary_metrics, has_postprocessing

    exit_keys = definition.get_exit_metrics_list() if definition else []
    def_slug = (
        definition.name.lower().replace(" ", "_").replace("-", "_")
        if definition
        else ((e.category or "extraction").lower().replace(" ", "_").replace("-", "_") if e else "extraction")
    )

    # 2. Legacy Postprocessing (Rule 2)
    if has_postprocessing:
        primary_metric, secondary_metrics = _extract_legacy_postprocessing(
            definition, fields_data, data_fields, def_slug, exit_keys
        )
        return primary_metric, secondary_metrics, True

    # 3. Legacy Exit Metrics (Rule 1)
    if exit_keys:
        primary_key = exit_keys[0]
        primary_metric = build_metric_entry(
            key=primary_key,
            fields_data=fields_data,
            source="exit_metric",
            label_override=format_metric_label(primary_key),
        )
        seen_sec_bases = {_base_metric_key(primary_key)}
        secondary_metrics = []
        for ek in exit_keys[1:]:
            base_ek = _base_metric_key(ek)
            if base_ek in seen_sec_bases:
                continue
            seen_sec_bases.add(base_ek)
            secondary_metrics.append(
                build_metric_entry(key=ek, fields_data=fields_data, source="exit_metric")
            )
        return primary_metric, secondary_metrics, False

    # 4. Ad-hoc fallback: No exit metrics configured and no postprocessing
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
    return primary_metric, [], False


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
    Extracts structured Risk & Affiliation data to display directly under authors.
    Delegates to `adapt_risk_and_affiliation` (Option A Tolerant Adapter).
    See `affiliation_adapter.py` for comprehensive architecture notes and Option B roadmap.
    """
    from .affiliation_adapter import adapt_affiliation_data
    return adapt_affiliation_data(fields_data)


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

    # 1. Rationale, Evidence & Band from primary metric / fields
    rationale = None
    evidence = []
    band = None

    matched_obj = data.get(primary_k)
    if not isinstance(matched_obj, dict):
        for k, v in data.items():
            if k.strip().lower().replace(" ", "_").replace("-", "_") == primary_k.replace(" ", "_").replace("-", "_"):
                if isinstance(v, dict):
                    matched_obj = v
                    break

    if isinstance(matched_obj, dict):
        if "band" in matched_obj and matched_obj["band"]:
            band = str(matched_obj["band"]).strip()
        elif "label" in matched_obj and matched_obj["label"]:
            band = str(matched_obj["label"]).strip()
        elif "level" in matched_obj and matched_obj["level"]:
            band = str(matched_obj["level"]).strip()

        if "rationale" in matched_obj and isinstance(matched_obj["rationale"], str):
            rationale = matched_obj["rationale"].strip()
        elif "insight" in matched_obj and isinstance(matched_obj["insight"], str):
            rationale = matched_obj["insight"].strip()

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

    # 2. Band label (e.g. 'TRL 4 — Technology validated in lab') if not yet found
    if not band:
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
    seen_facet_bases = set()
    primary_base = _base_metric_key(primary_metric.get("key") or "")
    if primary_base:
        seen_facet_bases.add(primary_base)
    facet_order = [k.strip().lower() for k in (order or [])]

    # Include secondary metrics
    for m in secondary_metrics:
        mk = m.get("key")
        mk_norm = mk.strip().lower() if mk else ""
        mk_base = _base_metric_key(mk_norm)
        if mk_base and mk_base in seen_facet_bases:
            continue

        raw_entry = data.get(mk) if mk in data else None
        if raw_entry is None:
            for dk, dv in data.items():
                if dk.strip().lower().replace(" ", "_").replace("-", "_") == mk_norm.replace(" ", "_").replace("-", "_"):
                    raw_entry = dv
                    break

        parsed_dict = _parse_dict_or_json(raw_entry)
        if isinstance(parsed_dict, dict) and parsed_dict:
            fb_num = m.get("numeric_value") if m.get("is_numeric") else None
            item_score, item_band, item_insight, item_evidence = _unpack_nested_metric_object(parsed_dict, fallback_numeric=fb_num)

            f_max = max_val
            if item_score is not None and 0.0 <= float(item_score) <= 1.0 and any(kw in mk_norm for kw in ("confidence", "probability", "prob", "ratio", "rate")):
                f_max = 1

            facets.append({
                "key": mk,
                "name": humanise_field_label(mk),
                "value": item_score,
                "max": f_max,
                "text": item_insight,
                "band": item_band,
                "evidence": item_evidence,
            })
            if item_insight or item_band or item_evidence or parsed_dict:
                texts.append({
                    "key": mk,
                    "name": humanise_field_label(mk),
                    "type": "dict",
                    "is_dict": True,
                    "value": item_insight or (f"{item_band}" if item_band else "—"),
                    "dict_value": parsed_dict,
                    "band": item_band,
                    "insight": item_insight,
                    "evidence": item_evidence,
                    "score": item_score,
                })
            seen_facet_keys.add(mk_norm)
            if mk_base:
                seen_facet_bases.add(mk_base)
            used.add(mk_norm)
            if item_evidence:
                evidence.extend(item_evidence)
            continue

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
            if mk_base:
                seen_facet_bases.add(mk_base)
            used.add(mk_norm)
        elif mk_norm and not m.get("is_numeric"):
            raw_v = m.get("raw") or m.get("value")
            if raw_v and str(raw_v) != "—":
                s_raw = str(raw_v).strip()
                if not (s_raw.startswith("{") or s_raw.startswith("[")):
                    facts.append({
                        "key": mk,
                        "name": humanise_field_label(mk),
                        "value": s_raw,
                    })
                    used.add(mk_norm)

    # Scan data for any other _score fields ONLY if secondary_metrics were not provided (legacy fallback)
    if not secondary_metrics:
        for k, v in data.items():
            k_norm = k.strip().lower()
            k_base = _base_metric_key(k_norm)
            if k_norm in used or k_norm in seen_facet_keys or (k_base and k_base in seen_facet_bases):
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
                    if k_base:
                        seen_facet_bases.add(k_base)
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

    DUPLICATE_KEY_RE = re.compile(r'_(computed|postprocessed)$', re.I)
    rich_unpacked_keys = set()

    for k, v in data.items():
        k_norm = k.strip().lower()
        if k_norm in ignored_keys or DUPLICATE_KEY_RE.search(k_norm) or k_norm in used:
            continue
        val = _unwrap_val(v)
        label = humanise_field_label(k)

        # Remaining dictionary fields (e.g. structured notes or extra sub-metrics not declared in secondary_metrics)
        parsed_dict = _parse_dict_or_json(val)
        if isinstance(parsed_dict, dict) and parsed_dict:
            item_score, item_band, item_insight, item_evidence = _unpack_nested_metric_object(parsed_dict)

            texts.append({
                "key": k,
                "name": label,
                "type": "dict",
                "is_dict": True,
                "value": item_insight or (f"{item_band}" if item_band else "—"),
                "dict_value": parsed_dict,
                "band": item_band,
                "insight": item_insight,
                "evidence": item_evidence,
                "score": item_score,
            })
            if item_evidence:
                evidence.extend(item_evidence)
            used.add(k_norm)
            continue

        # Lists
        if isinstance(val, list):
            items = [str(i).strip() for i in val if str(i).strip()]
            if items:
                lists.append({"key": k, "name": label, "items": items})
                used.add(k_norm)
            continue

        # Booleans -> Facts
        if isinstance(val, bool):
            facts.append({"key": k, "name": label, "value": val, "type": "boolean", "is_dict": False})
            used.add(k_norm)
            continue

        # Strings
        if isinstance(val, str):
            s = val.strip()
            if not s or s.startswith("{") or s.startswith("["):
                continue
            if SENTENCE_RE.search(s) or len(s) > 80:
                texts.append({"key": k, "name": label, "value": s, "type": "text", "is_dict": False})
            else:
                facts.append({"key": k, "name": label, "value": s, "type": "fact", "is_dict": False})
            used.add(k_norm)
            continue

        # Numbers
        if isinstance(val, (int, float)) and math.isfinite(val):
            if LEVEL_KEY_RE.search(k_norm) and primary_metric.get("numeric_value") == val:
                continue
            num_display = int(val) if float(val).is_integer() else round(float(val), 2)
            facts.append({"key": k, "name": label, "value": str(num_display), "type": "number", "is_dict": False})
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
