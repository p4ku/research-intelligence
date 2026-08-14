from decimal import Decimal

# Cost in USD per 1 Million tokens (Gemini Developer API pricing from https://ai.google.dev/gemini-api/docs/pricing)
MODEL_PRICING = {
    # Gemini 3.x Flash Family
    "gemini-3.7-flash": {"in": Decimal("0.75"), "out": Decimal("3.75")},
    "gemini-3.6-flash": {"in": Decimal("0.75"), "out": Decimal("3.75")},
    "gemini-3.5-flash": {"in": Decimal("0.75"), "out": Decimal("3.75")},
    "gemini-3.1-flash-lite": {"in": Decimal("0.25"), "out": Decimal("1.50")},
    "gemini-omni-flash-preview": {"in": Decimal("1.50"), "out": Decimal("9.00")},

    # Gemini 2.5 Family
    "gemini-2.5-pro": {"in": Decimal("1.25"), "out": Decimal("10.00")},
    "gemini-2.5-flash": {"in": Decimal("0.30"), "out": Decimal("2.50")},
    "gemini-2.5-flash-lite": {"in": Decimal("0.10"), "out": Decimal("0.40")},

    # Gemini 2.0 Family
    "gemini-2.0-flash": {"in": Decimal("0.10"), "out": Decimal("0.40")},
    "gemini-2.0-flash-lite": {"in": Decimal("0.075"), "out": Decimal("0.30")},

    # Gemini 1.5 Family (Legacy)
    "gemini-1.5-flash": {"in": Decimal("0.075"), "out": Decimal("0.30")},
    "gemini-1.5-pro": {"in": Decimal("1.25"), "out": Decimal("5.00")},

    # Fallback default: Gemini 3.7 Flash Standard Tier
    "default": {"in": Decimal("0.75"), "out": Decimal("3.75")},
}


def calculate_llm_cost(model_name: str | None, tokens_in: int = 0, tokens_out: int = 0) -> Decimal:
    """
    Calculates estimated USD cost for a given LLM model and token counts based on official Gemini API pricing.
    """
    if not model_name:
        pricing = MODEL_PRICING["default"]
    else:
        clean_name = str(model_name).lower().replace("google/", "").replace("google-agent/", "").strip()
        pricing = MODEL_PRICING.get(clean_name, MODEL_PRICING["default"])

    cost_in = (Decimal(tokens_in or 0) / Decimal("1000000")) * pricing["in"]
    cost_out = (Decimal(tokens_out or 0) / Decimal("1000000")) * pricing["out"]
    return (cost_in + cost_out).quantize(Decimal("0.0001"))
