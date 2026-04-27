from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from infonih.domain.category import Category
from infonih.domain.source import PollStatus, Source, SourceType
from infonih.scheduler import IngestionScheduler

# ---------------------------------------------------------------------------
# Fakes — mock the *adapter* (per CLAUDE.md), use a real-ish APScheduler
# instance with no jobs running for free.
# ---------------------------------------------------------------------------


class FakeSourceRepository:
    def __init__(self, sources: list[Source] | None = None) -> None:
        self._sources = list(sources) if sources else []

    def replace(self, sources: list[Source]) -> None:
        self._sources = list(sources)

    async def list_enabled(self, *, user_id: UUID | None = None) -> list[Source]:
        return [s for s in self._sources if s.enabled]

    async def get_by_id(self, source_id: UUID) -> Source | None:
        return next((s for s in self._sources if s.id == source_id), None)

    # Stubs to satisfy the Protocol shape in case anything else asks.
    async def add(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def get_by_name(self, *_args, **_kwargs):  # pragma: no cover
        return None

    async def pause(self, *_args, **_kwargs):  # pragma: no cover
        pass

    async def resume(self, *_args, **_kwargs):  # pragma: no cover
        pass

    async def remove(self, *_args, **_kwargs):  # pragma: no cover
        pass

    async def mark_polled(self, *_args, **_kwargs):  # pragma: no cover
        pass


class FakePipeline:
    def __init__(self) -> None:
        self.runs: list[UUID] = []

    async def run(self, source: Source):
        self.runs.append(source.id)


def _make_source(
    *,
    id: UUID | None = None,
    name: str = "Source",
    poll_interval_minutes: int = 60,
    enabled: bool = True,
) -> Source:
    now = datetime(2026, 4, 27, 12, tzinfo=UTC)
    return Source(
        id=id or uuid4(),
        name=name,
        type=SourceType.RSS,
        url="https://example.com/feed.xml",
        category=Category.AI_ENGINEERING,
        weight=Decimal("1.0"),
        poll_interval_minutes=poll_interval_minutes,
        enabled=enabled,
        consecutive_failures=0,
        created_at=now,
        updated_at=now,
        last_polled_at=now,
        last_poll_status=PollStatus.OK,
    )


@pytest.fixture
def repo() -> FakeSourceRepository:
    return FakeSourceRepository()


@pytest.fixture
def pipeline() -> FakePipeline:
    return FakePipeline()


@pytest.fixture
def scheduler(
    repo: FakeSourceRepository, pipeline: FakePipeline
) -> IngestionScheduler:
    # IngestSourcePipeline contract is duck-typed in the scheduler; FakePipeline
    # passes muster at runtime even though the type hint expects the real class.
    return IngestionScheduler(
        source_repo=repo,
        pipeline=pipeline,  # type: ignore[arg-type]
        reconcile_interval_seconds=60,
    )


# ---------------------------------------------------------------------------
# Tests — drive `reconcile()` directly so we don't depend on APScheduler ticks.
# ---------------------------------------------------------------------------


async def test_reconcile_adds_jobs_for_new_enabled_sources(
    scheduler: IngestionScheduler,
    repo: FakeSourceRepository,
) -> None:
    a = _make_source(name="A", poll_interval_minutes=30)
    b = _make_source(name="B", poll_interval_minutes=60)
    repo.replace([a, b])

    await scheduler.reconcile()

    assert set(scheduler._tracked) == {a.id, b.id}
    assert scheduler._scheduler.get_job(f"ingest-{a.id}") is not None
    assert scheduler._scheduler.get_job(f"ingest-{b.id}") is not None


async def test_reconcile_removes_jobs_for_disabled_sources(
    scheduler: IngestionScheduler,
    repo: FakeSourceRepository,
) -> None:
    a = _make_source(name="A")
    repo.replace([a])
    await scheduler.reconcile()

    paused = a.model_copy(update={"enabled": False})
    repo.replace([paused])
    await scheduler.reconcile()

    assert a.id not in scheduler._tracked
    assert scheduler._scheduler.get_job(f"ingest-{a.id}") is None


async def test_reconcile_removes_jobs_for_deleted_sources(
    scheduler: IngestionScheduler,
    repo: FakeSourceRepository,
) -> None:
    a = _make_source(name="A")
    repo.replace([a])
    await scheduler.reconcile()

    repo.replace([])
    await scheduler.reconcile()

    assert a.id not in scheduler._tracked


async def test_reconcile_reschedules_when_interval_changes(
    scheduler: IngestionScheduler,
    repo: FakeSourceRepository,
) -> None:
    a = _make_source(name="A", poll_interval_minutes=60)
    repo.replace([a])
    await scheduler.reconcile()

    updated = a.model_copy(update={"poll_interval_minutes": 15})
    repo.replace([updated])
    await scheduler.reconcile()

    assert scheduler._tracked[a.id] == 15
    job = scheduler._scheduler.get_job(f"ingest-{a.id}")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 15 * 60


async def test_reconcile_is_idempotent_with_no_changes(
    scheduler: IngestionScheduler,
    repo: FakeSourceRepository,
) -> None:
    a = _make_source(name="A", poll_interval_minutes=60)
    repo.replace([a])
    await scheduler.reconcile()
    snapshot = dict(scheduler._tracked)

    await scheduler.reconcile()
    await scheduler.reconcile()

    assert scheduler._tracked == snapshot


async def test_per_source_job_runs_pipeline_with_refreshed_source(
    scheduler: IngestionScheduler,
    repo: FakeSourceRepository,
    pipeline: FakePipeline,
) -> None:
    a = _make_source(name="A")
    repo.replace([a])
    await scheduler.reconcile()

    runner = scheduler._make_job(a.id)
    await runner()

    assert pipeline.runs == [a.id]


async def test_per_source_job_skips_when_source_paused_between_ticks(
    scheduler: IngestionScheduler,
    repo: FakeSourceRepository,
    pipeline: FakePipeline,
) -> None:
    a = _make_source(name="A")
    repo.replace([a])
    runner = scheduler._make_job(a.id)

    # Source pauses after the job was scheduled but before it fires.
    repo.replace([a.model_copy(update={"enabled": False})])
    await runner()

    assert pipeline.runs == []


async def test_per_source_job_skips_when_source_deleted(
    scheduler: IngestionScheduler,
    pipeline: FakePipeline,
) -> None:
    runner = scheduler._make_job(uuid4())

    await runner()

    assert pipeline.runs == []
