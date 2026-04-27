from decimal import Decimal

import pytest

from infonih.adapters.postgres.source_repository import PostgresSourceRepository
from infonih.domain.category import Category
from infonih.domain.source import PollStatus, SourceType


async def _add_default_source(repo: PostgresSourceRepository, **overrides):
    defaults = {
        "name": "Simon Willison",
        "type": SourceType.RSS,
        "url": "https://simonwillison.net/atom/everything/",
        "category": Category.AI_ENGINEERING,
        "weight": Decimal("1.5"),
        "poll_interval_minutes": 60,
    }
    defaults.update(overrides)
    return await repo.add(**defaults)


async def test_add_returns_persisted_source(source_repo: PostgresSourceRepository) -> None:
    source = await _add_default_source(source_repo)

    assert source.id is not None
    assert source.name == "Simon Willison"
    assert source.category is Category.AI_ENGINEERING
    assert source.weight == Decimal("1.5")
    assert source.enabled is True
    assert source.consecutive_failures == 0


async def test_add_duplicate_url_raises(source_repo: PostgresSourceRepository) -> None:
    await _add_default_source(source_repo)

    with pytest.raises(Exception):  # IntegrityError surfaces from asyncpg
        await _add_default_source(source_repo, name="Different Name")


async def test_list_enabled_orders_unpolled_first(
    source_repo: PostgresSourceRepository,
) -> None:
    a = await _add_default_source(source_repo, name="A", url="https://a.example/feed")
    await _add_default_source(source_repo, name="B", url="https://b.example/feed")
    await source_repo.mark_polled(a.id, status=PollStatus.OK)

    enabled = await source_repo.list_enabled()

    # B has never been polled (NULL last_polled_at) → comes first.
    assert [s.name for s in enabled] == ["B", "A"]


async def test_list_enabled_excludes_paused(
    source_repo: PostgresSourceRepository,
) -> None:
    a = await _add_default_source(source_repo, name="A", url="https://a.example/feed")
    await _add_default_source(source_repo, name="B", url="https://b.example/feed")
    await source_repo.pause(a.id)

    enabled = await source_repo.list_enabled()

    assert [s.name for s in enabled] == ["B"]


async def test_get_by_name_is_case_insensitive(
    source_repo: PostgresSourceRepository,
) -> None:
    await _add_default_source(source_repo, name="Simon Willison")

    found = await source_repo.get_by_name("simon willison")

    assert found is not None
    assert found.name == "Simon Willison"


async def test_get_by_name_returns_none_when_missing(
    source_repo: PostgresSourceRepository,
) -> None:
    found = await source_repo.get_by_name("does-not-exist")

    assert found is None


async def test_pause_then_resume_round_trip(
    source_repo: PostgresSourceRepository,
) -> None:
    source = await _add_default_source(source_repo)

    await source_repo.pause(source.id)
    after_pause = await source_repo.get_by_name(source.name)
    await source_repo.resume(source.id)
    after_resume = await source_repo.get_by_name(source.name)

    assert after_pause is not None and after_pause.enabled is False
    assert after_resume is not None and after_resume.enabled is True


async def test_remove_deletes_row(source_repo: PostgresSourceRepository) -> None:
    source = await _add_default_source(source_repo)

    await source_repo.remove(source.id)

    assert await source_repo.get_by_name(source.name) is None


async def test_mark_polled_ok_resets_failures(
    source_repo: PostgresSourceRepository,
) -> None:
    source = await _add_default_source(source_repo)
    await source_repo.mark_polled(source.id, status=PollStatus.FAILED, error="boom")
    await source_repo.mark_polled(source.id, status=PollStatus.FAILED, error="boom")

    await source_repo.mark_polled(source.id, status=PollStatus.OK)

    refreshed = await source_repo.get_by_name(source.name)
    assert refreshed is not None
    assert refreshed.last_poll_status is PollStatus.OK
    assert refreshed.consecutive_failures == 0
    assert refreshed.last_poll_error is None


async def test_mark_polled_failed_increments_failures(
    source_repo: PostgresSourceRepository,
) -> None:
    source = await _add_default_source(source_repo)

    await source_repo.mark_polled(source.id, status=PollStatus.FAILED, error="timeout")
    await source_repo.mark_polled(source.id, status=PollStatus.FAILED, error="timeout")
    await source_repo.mark_polled(source.id, status=PollStatus.FAILED, error="timeout")

    refreshed = await source_repo.get_by_name(source.name)
    assert refreshed is not None
    assert refreshed.last_poll_status is PollStatus.FAILED
    assert refreshed.consecutive_failures == 3
    assert refreshed.last_poll_error == "timeout"
