"""
risk_affiliation_adapter.py - Re-export wrapper for affiliation_adapter.py.

All core adapter logic and architecture documentation live in `affiliation_adapter.py`.
This module is maintained for 100% backwards compatibility with existing imports.
"""

from .affiliation_adapter import (
    adapt_affiliation_data,
    adapt_risk_and_affiliation,
    normalize_affiliations,
    normalize_author_contacts,
    normalize_funding_entities,
    normalize_codebase_link,
    unpack_flag_value,
    _resolve_candidate_field,
    _unwrap_val,
)

__all__ = [
    "adapt_affiliation_data",
    "adapt_risk_and_affiliation",
    "normalize_affiliations",
    "normalize_author_contacts",
    "normalize_funding_entities",
    "normalize_codebase_link",
    "unpack_flag_value",
    "_resolve_candidate_field",
    "_unwrap_val",
]
