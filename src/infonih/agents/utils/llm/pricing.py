"""Per-model token pricing for cost tracking.

Prices in USD per 1 million tokens, sourced from anthropic.com/pricing
(cached 2026-04-15). Update when Anthropic changes pricing.

Unknown models fall back to Sonnet 4.6 pricing — pessimistic enough that
we never zero-out a cost row, conservative enough that an unknown model
isn't dramatically over-priced.
"""

from decimal import Decimal

# (input_per_million, output_per_million)
_PRICING_USD_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
    "claude-sonnet-4-6": (Decimal("3.00"), Decimal("15.00")),
    "claude-opus-4-6": (Decimal("5.00"), Decimal("25.00")),
    "claude-opus-4-7": (Decimal("5.00"), Decimal("25.00")),
}

_FALLBACK = (Decimal("3.00"), Decimal("15.00"))


def cost_usd(*, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Compute the USD cost of an Anthropic call.

    Returns a Decimal quantized to 6 decimal places (sub-cent precision —
    matches the `cost_events.cost_usd` column shape).
    """
    in_price, out_price = _PRICING_USD_PER_MILLION.get(model, _FALLBACK)
    raw = (
        Decimal(input_tokens) * in_price
        + Decimal(output_tokens) * out_price
    ) / Decimal("1000000")
    return raw.quantize(Decimal("0.000001"))
