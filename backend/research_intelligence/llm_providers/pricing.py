from decimal import Decimal

# Cost in USD per 1 Million tokens (Gemini Developer API pricing from https://ai.google.dev/gemini-api/docs/pricing)
# Context caching provides a 75% discount on cached input prompt tokens (cost is 25% of standard input rate)
MODEL_PRICING = {
    # Gemini 3.x Flash Family (Base rates: $0.75 / 1M prompt, $3.75 / 1M completion; Fusion tier: $0.825 / $4.125)
    "google/gemini-3.8-flash": {"in": Decimal("0.75"), "out": Decimal("3.75"), "cached_in": Decimal("0.1875")},
    "gemini-3.8-flash": {"in": Decimal("0.75"), "out": Decimal("3.75"), "cached_in": Decimal("0.1875")},
    "openrouter/fusion/google/gemini-3.8-flash": {"in": Decimal("0.825"), "out": Decimal("4.125"), "cached_in": Decimal("0.0825")},
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

    # OpenRouter Popular Models (rates per 1M tokens)
    "meta-llama/llama-3.3-70b-instruct": {"in": Decimal("0.13"), "out": Decimal("0.40")},
    "meta-llama/llama-3.1-8b-instruct": {"in": Decimal("0.02"), "out": Decimal("0.05")},
    "anthropic/claude-3.5-sonnet": {"in": Decimal("3.00"), "out": Decimal("15.00")},
    "anthropic/claude-3.7-sonnet": {"in": Decimal("3.00"), "out": Decimal("15.00")},
    "openai/gpt-4o": {"in": Decimal("2.50"), "out": Decimal("10.00")},
    "openai/gpt-4o-mini": {"in": Decimal("0.15"), "out": Decimal("0.60")},
    "deepseek/deepseek-chat": {"in": Decimal("0.14"), "out": Decimal("0.28")},
    "deepseek/deepseek-r1": {"in": Decimal("0.55"), "out": Decimal("2.19")},
    "qwen/qwen-2.5-72b-instruct": {"in": Decimal("0.35"), "out": Decimal("0.40")},
    "mistralai/mistral-large-2411": {"in": Decimal("2.00"), "out": Decimal("6.00")},

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
    Calculates estimated USD cost for a given LLM model and token counts based on official API pricing.
    Supports discounted context caching tokens.
    """
    if not model_name:
        pricing = MODEL_PRICING["default"]
    else:
        base_slug = str(model_name).lower().strip()
        raw_slug = base_slug.split(":")[0].strip()
        if base_slug in MODEL_PRICING:
            pricing = MODEL_PRICING[base_slug]
        elif raw_slug in MODEL_PRICING:
            pricing = MODEL_PRICING[raw_slug]
        else:
            clean_name = raw_slug.replace("openrouter/", "").replace("google/", "").replace("google-agent/", "").strip()
            pricing = MODEL_PRICING.get(clean_name, MODEL_PRICING.get(raw_slug, MODEL_PRICING["default"]))

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
