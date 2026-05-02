from decimal import Decimal

from infonih.agents.utils.llm.pricing import cost_usd


def test_cost_usd_haiku_4_5() -> None:
    # 1M input @ $1 + 1M output @ $5 = $6
    actual = cost_usd(
        model="claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000
    )
    assert actual == Decimal("6.000000")


def test_cost_usd_sonnet_4_6() -> None:
    # 100K input @ $3/M + 50K output @ $15/M = 0.30 + 0.75 = $1.05
    actual = cost_usd(
        model="claude-sonnet-4-6", input_tokens=100_000, output_tokens=50_000
    )
    assert actual == Decimal("1.050000")


def test_cost_usd_unknown_model_falls_back_to_sonnet_pricing() -> None:
    expected = cost_usd(model="claude-sonnet-4-6", input_tokens=1000, output_tokens=500)
    actual = cost_usd(model="claude-mystery-99", input_tokens=1000, output_tokens=500)
    assert actual == expected


def test_cost_usd_zero_tokens_is_zero() -> None:
    actual = cost_usd(model="claude-haiku-4-5", input_tokens=0, output_tokens=0)
    assert actual == Decimal("0.000000")


def test_cost_usd_quantizes_to_six_decimals() -> None:
    # 1 token @ $1/M = $0.000001
    result = cost_usd(model="claude-haiku-4-5", input_tokens=1, output_tokens=0)
    assert result == Decimal("0.000001")
    # exponent matches Numeric(10, 6) column shape
    assert result.as_tuple().exponent == -6
