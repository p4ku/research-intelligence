from decimal import Decimal

# Cost in USD per 1 Million tokens (Gemini Developer API pricing from https://ai.google.dev/gemini-api/docs/pricing)
# Context caching provides a 75% discount on cached input prompt tokens (cost is 25% of standard input rate)
MODEL_PRICING = {
    # Gemini 3.x Flash Family
    "gemini-3.8-flash": {"in": Decimal("0.75"), "out": Decimal("3.75"), "cached_in": Decimal("0.1875")},
    "gemini-3.7-flash": {"in": Decimal("0.75"), "out": Decimal("3.75"), "cached_in": Decimal("0.1875")},
    "gemini-3.6-flash": {"in": Decimal("0.75"), "out": Decimal("3.75"), "cached_in": Decimal("0.1875")},
    "gemini-3.5-flash": {"in": Decimal("0.75"), "out": Decimal("3.75"), "cached_in": Decimal("0.1875")},
    "gemini-3.1-flash-lite": {"in": Decimal("0.25"), "out": Decimal("1.50"), "cached_in": Decimal("0.0625")},
    "gemini-omni-flash-preview": {"in": Decimal("1.50"), "out": Decimal("9.00"), "cached_in": Decimal("0.375")},

    # Gemini 2.5 Family
    "gemini-2.5-pro": {"in": Decimal("1.25"), "out": Decimal("10.00"), "cached_in": Decimal("0.3125")},
    "gemini-2.5-flash": {"in": Decimal("0.30"), "out": Decimal("2.50"), "cached_in": Decimal("0.075")},
    "gemini-2.5-flash-lite": {"in": Decimal("0.10"), "out": Decimal("0.40"), "cached_in": Decimal("0.025")},

    # Gemini 2.0 Family
    "gemini-2.0-flash": {"in": Decimal("0.10"), "out": Decimal("0.40"), "cached_in": Decimal("0.025")},
    "gemini-2.0-flash-lite": {"in": Decimal("0.075"), "out": Decimal("0.30"), "cached_in": Decimal("0.01875")},

    # Gemini 1.5 Family (Legacy)
    "gemini-1.5-flash": {"in": Decimal("0.075"), "out": Decimal("0.30"), "cached_in": Decimal("0.01875")},
    "gemini-1.5-pro": {"in": Decimal("1.25"), "out": Decimal("5.00"), "cached_in": Decimal("0.3125")},

    # Fallback default: Gemini 3.8 Flash Standard Tier
    "default": {"in": Decimal("0.75"), "out": Decimal("3.75"), "cached_in": Decimal("0.1875")},
}


def calculate_llm_cost(
    model_name: str | None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    tokens_cached: int = 0
) -> Decimal:
    """
    Calculates estimated USD cost for a given LLM model and token counts based on official Gemini API pricing.
    Supports discounted context caching tokens (75% discount on prompt tokens according to official Gemini pricing).
    
    Robustness guarantees:
    - If Google API omits or returns 0/None for cached tokens, standard input pricing is applied.
    - If Google API returns prompt_token_count as total prompt tokens (which includes cached_content_token_count),
      the uncached portion is computed as max(0, tokens_in - tokens_cached) so cached tokens are never double-billed.
    - If tokens_in is already supplied as net uncached tokens, both are billed at their respective rates.
    """
    if not model_name:
        pricing = MODEL_PRICING["default"]
    else:
        clean_name = str(model_name).lower().replace("google/", "").replace("google-agent/", "").strip()
        pricing = MODEL_PRICING.get(clean_name, MODEL_PRICING["default"])

    cached_rate = pricing.get("cached_in", pricing["in"] * Decimal("0.25"))

    tokens_in_val = Decimal(tokens_in or 0)
    tokens_cached_val = Decimal(tokens_cached or 0)
    tokens_out_val = Decimal(tokens_out or 0)

    # In Google Gemini API, prompt_token_count includes cached_content_token_count.
    # If tokens_in >= tokens_cached > 0, tokens_in is the total prompt tokens from usage_metadata,
    # so the uncached portion is (tokens_in - tokens_cached).
    # If tokens_in < tokens_cached, tokens_in was already supplied as net uncached.
    if tokens_in_val >= tokens_cached_val > 0:
        uncached_in = tokens_in_val - tokens_cached_val
    else:
        uncached_in = tokens_in_val

    cost_in = (uncached_in / Decimal("1000000")) * pricing["in"]
    cost_cached = (tokens_cached_val / Decimal("1000000")) * cached_rate
    cost_out = (tokens_out_val / Decimal("1000000")) * pricing["out"]
    raw_cost = cost_in + cost_cached + cost_out
    if raw_cost > 0 and raw_cost < Decimal("0.0001"):
        return Decimal("0.0001")
    return raw_cost.quantize(Decimal("0.0001"))
