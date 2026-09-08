"""
Central Feature Flagging & Modular Capability Switching.

Provides a unified, configuration-driven mechanism to toggle features across
the backend (Django Admin, Celery Beat periodic dispatchers, Pipeline Runner,
outbound notifications, and API endpoints).

All flags default to `False` (safe opt-in).
"""

import os
import logging
from typing import Any, Dict, Callable, Optional, Union
from functools import wraps
from enum import StrEnum

from django.conf import settings

logger = logging.getLogger(__name__)


class Feature(StrEnum):
    """
    Standardized identifiers for togglable system features.
    Subclasses StrEnum so each member behaves as a native string.
    """
    SCHEDULING = "SCHEDULING"
    EMAIL_NOTIFICATIONS = "EMAIL_NOTIFICATIONS"


# All known feature flag members for iteration and inspection
ALL_FEATURES: list[Feature] = list(Feature)

# Registry of known feature flags with human-readable descriptions (EXPERIMENTAL: In testing phase, not production-ready)
KNOWN_FEATURES: Dict[Feature, str] = {
    Feature.SCHEDULING: "Periodic workflow task scheduling (Celery Beat dispatcher & WorkflowSchedule in Admin) [TESTING PHASE - NOT PROD READY]",
    Feature.EMAIL_NOTIFICATIONS: "Transactional email notifications and digests via Mailgun / Subscribers in Admin [TESTING PHASE - NOT PROD READY]",
}

_TRUTHY_VALUES = frozenset({"true", "1", "yes", "on", "t", "enabled"})
_FALSY_VALUES = frozenset({"false", "0", "no", "off", "f", "disabled", ""})


def _parse_bool(value: Any) -> Optional[bool]:
    """
    Normalizes diverse representations (bool, int, str) to a boolean.
    Returns None if value is None or cannot be decisively parsed.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUTHY_VALUES:
            return True
        if normalized in _FALSY_VALUES:
            return False
    return bool(value)


def is_feature_enabled(feature_name: Optional[Union[str, Feature]], default: bool = False) -> bool:
    """
    Evaluates whether a feature flag is enabled.

    Resolution order (all lookup keys are case-insensitive):
    1. `settings.FEATURES` dictionary (e.g. `{"SCHEDULING": True}`)
    2. Direct setting attribute (e.g. `settings.FEATURE_SCHEDULING = True`)
    3. Environment variable (e.g. `FEATURE_SCHEDULING="true"`)
    4. Fallback `default` argument (defaults to False)

    Args:
        feature_name: Feature member or string identifier (e.g. Feature.SCHEDULING or 'scheduling').
        default: Fallback boolean if feature is unconfigured (defaults to False).

    Returns:
        bool: True if feature is explicitly enabled, False otherwise.
    """
    if not feature_name:
        return default

    # Handles Feature enum members and raw strings alike
    raw_str = feature_name.value if isinstance(feature_name, Feature) else str(feature_name)
    normalized_key = raw_str.strip().upper()

    # 1. Check settings.FEATURES dictionary
    features_dict = getattr(settings, "FEATURES", None)
    if isinstance(features_dict, dict):
        for k, v in features_dict.items():
            key_str = k.value if isinstance(k, Feature) else str(k)
            if key_str.strip().upper() == normalized_key:
                parsed = _parse_bool(v)
                if parsed is not None:
                    return parsed

    # 2. Check direct settings attribute (e.g. FEATURE_SCHEDULING or SCHEDULING)
    candidate_attrs = [f"FEATURE_{normalized_key}", normalized_key]
    for attr in candidate_attrs:
        if hasattr(settings, attr):
            parsed = _parse_bool(getattr(settings, attr))
            if parsed is not None:
                return parsed

    # 3. Check environment variables
    candidate_env_vars = [f"FEATURE_{normalized_key}", normalized_key]
    for env_var in candidate_env_vars:
        if env_var in os.environ:
            parsed = _parse_bool(os.environ[env_var])
            if parsed is not None:
                return parsed

    return default


def get_all_features() -> Dict[str, bool]:
    """
    Returns a snapshot dictionary mapping all known and configured feature flag
    names to their active boolean states.
    """
    result: Dict[str, bool] = {}

    # Register known flags first
    for key in KNOWN_FEATURES:
        result[key] = is_feature_enabled(key, default=False)

    # Include any custom flags defined in settings.FEATURES
    features_dict = getattr(settings, "FEATURES", None)
    if isinstance(features_dict, dict):
        for k in features_dict:
            norm = (k.value if isinstance(k, Feature) else str(k)).strip().upper()
            if norm not in result:
                result[norm] = is_feature_enabled(norm, default=False)

    return result


def require_feature(feature_name: Union[str, Feature], fallback: Any = None) -> Callable:
    """
    Decorator that gates function or method execution behind a feature flag.

    If the feature is disabled:
    - If `fallback` is callable, calls and returns `fallback(*args, **kwargs)`.
    - Otherwise, returns `fallback` directly (defaults to None).
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not is_feature_enabled(feature_name):
                flag_str = feature_name.value if isinstance(feature_name, Feature) else str(feature_name)
                logger.debug(
                    f"Feature '{flag_str}' is disabled; skipping execution of '{func.__qualname__}'."
                )
                if callable(fallback):
                    return fallback(*args, **kwargs)
                return fallback
            return func(*args, **kwargs)
        return wrapper
    return decorator
