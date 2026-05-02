from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio

from infonih.adapters.postgres.cost_repository import PostgresCostRepository
from infonih.adapters.postgres.postgres_adapter import PostgresAdapter


@pytest_asyncio.fixture
async def cost_repo(test_adapter: PostgresAdapter) -> PostgresCostRepository:
    return PostgresCostRepository(test_adapter)


async def _record(
    repo: PostgresCostRepository,
    *,
    flow: str = "score_article",
    model: str = "claude-haiku-4-5",
    input_tokens: int = 1000,
    output_tokens: int = 100,
    cost_usd: Decimal = Decimal("0.0015"),
) -> None:
    await repo.record(
        flow=flow,
        provider="anthropic",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )


async def test_record_then_summarize_since_returns_aggregates(
    cost_repo: PostgresCostRepository,
) -> None:
    await _record(cost_repo, input_tokens=500, output_tokens=50, cost_usd=Decimal("0.0008"))
    await _record(cost_repo, input_tokens=300, output_tokens=20, cost_usd=Decimal("0.0004"))

    summary = await cost_repo.summarize_since(since=datetime.now(UTC) - timedelta(hours=1))

    assert summary.call_count == 2
    assert summary.input_tokens == 800
    assert summary.output_tokens == 70
    assert summary.cost_usd == Decimal("0.001200")


async def test_summarize_since_returns_zero_when_empty(
    cost_repo: PostgresCostRepository,
) -> None:
    summary = await cost_repo.summarize_since(since=datetime.now(UTC) - timedelta(hours=1))

    assert summary.call_count == 0
    assert summary.input_tokens == 0
    assert summary.output_tokens == 0
    assert summary.cost_usd == Decimal("0")


async def test_summarize_since_excludes_rows_before_window(
    cost_repo: PostgresCostRepository,
) -> None:
    # All recorded events are stamped server-side with now(); use a future
    # window start to confirm exclusion works.
    await _record(cost_repo)

    summary = await cost_repo.summarize_since(since=datetime.now(UTC) + timedelta(hours=1))

    assert summary.call_count == 0


async def test_summarize_by_flow_groups_and_orders_by_cost_desc(
    cost_repo: PostgresCostRepository,
) -> None:
    await _record(cost_repo, flow="score_article", cost_usd=Decimal("0.10"))
    await _record(cost_repo, flow="score_article", cost_usd=Decimal("0.10"))
    await _record(cost_repo, flow="summarize_for_digest", cost_usd=Decimal("0.50"))

    by_flow = await cost_repo.summarize_by_flow_since(
        since=datetime.now(UTC) - timedelta(hours=1)
    )

    assert [s.flow for s in by_flow] == ["summarize_for_digest", "score_article"]
    assert by_flow[0].cost_usd == Decimal("0.500000")
    assert by_flow[0].call_count == 1
    assert by_flow[1].cost_usd == Decimal("0.200000")
    assert by_flow[1].call_count == 2


async def test_record_optional_fields_persist(
    cost_repo: PostgresCostRepository,
) -> None:
    article_id = uuid4()
    await cost_repo.record(
        flow="score_article",
        provider="anthropic",
        model="claude-haiku-4-5",
        input_tokens=1500,
        output_tokens=80,
        cost_usd=Decimal("0.002"),
        cache_creation_input_tokens=500,
        cache_read_input_tokens=200,
        article_id=article_id,
    )

    summary = await cost_repo.summarize_since(since=datetime.now(UTC) - timedelta(hours=1))
    assert summary.call_count == 1
    # cache columns aren't in the summary today; we just verify the insert succeeded
