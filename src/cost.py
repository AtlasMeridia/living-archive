"""Cost estimation for photo and document pipelines.

Provides token estimates and dollar costs for --dry-run output.
The photo pipeline runs via Max Plan OAuth (zero marginal cost) but
we still surface an equivalent API cost for awareness.
"""

from . import config

# Pricing per million tokens (input, output) — as of 2025-05
PRICING: dict[str, tuple[float, float]] = {
    "opus":   (15.00, 75.00),
    "sonnet": (3.00,  15.00),
    "haiku":  (0.80,   4.00),
}

# Estimation constants
PHOTO_INPUT_TOKENS = 1_600   # ~1 image + prompt
PHOTO_OUTPUT_TOKENS = 800    # structured analysis response
DOC_CHARS_PER_TOKEN = 4      # rough char→token ratio
DOC_OUTPUT_TOKENS = 1_200    # analysis response per doc


def estimate_photo_cost(num_photos: int, model: str = "") -> dict:
    """Estimate tokens and cost for a photo batch.

    Returns dict with input_tokens, output_tokens, total_tokens,
    cost_dollars, model, is_max_plan.
    """
    model = model or config.OAUTH_MODEL
    pricing_key = _resolve_pricing_key(model)

    input_tokens = num_photos * PHOTO_INPUT_TOKENS
    output_tokens = num_photos * PHOTO_OUTPUT_TOKENS
    total_tokens = input_tokens + output_tokens

    inp_rate, out_rate = PRICING.get(pricing_key, PRICING["sonnet"])
    cost = (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_dollars": cost,
        "model": model,
        "is_max_plan": True,
    }


def estimate_doc_cost(total_chars: int, num_docs: int, model: str = "") -> dict:
    """Estimate tokens and cost for a document batch.

    Returns dict with input_tokens, output_tokens, total_tokens,
    cost_dollars, model, is_max_plan.
    """
    model = model or (config.DOC_CLI_MODEL if config.DOC_PROVIDER == "claude-cli" else config.MODEL)
    pricing_key = _resolve_pricing_key(model)

    input_tokens = total_chars // DOC_CHARS_PER_TOKEN
    output_tokens = num_docs * DOC_OUTPUT_TOKENS
    total_tokens = input_tokens + output_tokens

    inp_rate, out_rate = PRICING.get(pricing_key, PRICING["sonnet"])
    cost = (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_dollars": cost,
        "model": model,
        "is_max_plan": config.DOC_PROVIDER in ("claude-cli", "oauth"),
    }


def format_cost_summary(estimate: dict) -> str:
    """Format a cost estimate as a human-readable string."""
    lines = []
    lines.append(
        f"  Estimated tokens: ~{estimate['input_tokens']:,} input + "
        f"~{estimate['output_tokens']:,} output = ~{estimate['total_tokens']:,} total"
    )
    if estimate.get("is_max_plan"):
        lines.append(
            f"  Cost: $0.00 (Max Plan) — equivalent API cost: ${estimate['cost_dollars']:.2f} "
            f"({estimate['model']})"
        )
    else:
        lines.append(
            f"  Estimated cost: ${estimate['cost_dollars']:.2f} ({estimate['model']})"
        )
    return "\n".join(lines)


def _resolve_pricing_key(model: str) -> str:
    """Map a model name/ID to a pricing key."""
    m = model.lower()
    if "opus" in m:
        return "opus"
    if "haiku" in m:
        return "haiku"
    return "sonnet"
