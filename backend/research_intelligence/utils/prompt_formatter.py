"""
Safe and Resilient Prompt Template Formatter.

Replaces template variables (e.g. {title}, {abstract}, {acceptance_criteria}, {rejection_criteria})
without raising KeyError/ValueError when user templates include JSON schema examples,
regular expressions, mathematical notation (e.g. \\mathcal{O}(n)), or unmatched curly braces.
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def safe_format_prompt(template: str, context: Dict[str, Any]) -> str:
    """
    Safely substitutes named placeholder variables in prompt templates.

    Features:
    1. Normalizes double-curlies {{key}} into {key}.
    2. Identifies {variable_name} placeholders matching alphanumeric keys in context.
    3. Replaces matched variables with stringified context values.
    4. Ignores JSON structures (e.g. {"passed": true}) and unescaped braces without crashing.
    5. Leaves unmatched placeholders unchanged or substitutes None as empty string.

    Args:
        template: The raw prompt string template containing variables like {title} or {acceptance_criteria}.
        context: Mapping of variable names to replacement values.

    Returns:
        str: The safely formatted prompt string.
    """
    if not template or not isinstance(template, str):
        return ""

    # 1. Normalize double-curly {{var}} to {var} if user wrote escaped syntax
    normalized = re.sub(r'\{\{([a-zA-Z0-9_]+)\}\}', r'{\1}', template)

    # 2. Regex replacer matching {identifier}
    # Matches {key} where key is a valid Python-like identifier
    def _replacer(match):
        key = match.group(1)
        if key in context:
            val = context[key]
            return str(val) if val is not None else ""
        # If key is not in context, leave the original placeholder untouched
        return match.group(0)

    # Match single braces with a valid word identifier inside: {identifier}
    pattern = re.compile(r'\{([a-zA-Z0-9_]+)\}')
    return pattern.sub(_replacer, normalized)
