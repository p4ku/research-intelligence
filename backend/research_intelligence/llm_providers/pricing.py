from decimal import Decimal

# Cost in USD per 1 Million tokens
# Gemini 3.7 Flash: $0.075 / 1M prompt tokens (<128k context), $0.30 / 1M completion tokens
# Gemini 1.5/2.5/3.5 Flash: $0.075 / 1M in, $0.30 / 1M out
# Gemini Pro: $1.25 / 1M in, $5.00 / 1M out
MODEL_PRICING = {
    "gemini-3.7-flash": {"in": Decimal("0.075"), "out": Decimal("0.30")},
    "gemini-3.5-flash": {"in": Decimal("0.075"), "out": Decimal("0.30")},
    "gemini-2.5-flash": {"in": Decimal("0.075"), "out": Decimal("0.30")},
    "gemini-1.5-flash": {"in": Decimal("0.075"), "out": Decimal("0.30")},
    "gemini-1.5-pro": {"in": Decimal("1.25"), "out": Decimal("5.00")},
    "default": {"in": Decimal("0.075"), "out": Decimal("0.30")},
}


def calculate_llm_cost(model_name: str | None, tokens_in: int = 0, tokens_out: int = 0) -> Decimal:
    """
    Calculates estimated USD cost for a given LLM model and token counts.
    """
    if not model_name:
        pricing = MODEL_PRICING["default"]
    else:
        clean_name = str(model_name).lower().replace("google/", "").replace("google-agent/", "")
        pricing = MODEL_PRICING.get(clean_name, MODEL_PRICING["default"])

    cost_in = (Decimal(tokens_in or 0) / Decimal("1000000")) * pricing["in"]
    cost_out = (Decimal(tokens_out or 0) / Decimal("1000000")) * pricing["out"]
    return (cost_in + cost_out).quantize(Decimal("0.0001"))
