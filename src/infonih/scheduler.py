"""Background scheduler that polls each enabled source on its own interval.

Architecture: a separate worker process from the FastAPI web app. Both share
the database, neither imports the other. Standard "web + worker" split — keeps
test isolation clean and lets you scale or restart them independently.

Reconciliation loop: every `RECONCILE_INTERVAL_SECONDS`, the scheduler diffs
its in-memory job list against the `sources` table:

* Source enabled in DB but no job scheduled → add a job at its `poll_interval_minutes`.
* Source disabled / removed in DB but job still scheduled → drop the job.
* Source's `poll_interval_minutes` changed → reschedule the job at the new cadence.

This is what makes `/pause-source` and `/add-source` (Telegram, later) take
effect without restarting the worker.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from infonih.agents.pipelines.ingest_source import IngestSourcePipeline
from infonih.domain.repositories.source_repository import SourceRepository

RECONCILE_INTERVAL_SECONDS = 60
RECONCILE_JOB_ID = "_reconcile"


class IngestionScheduler:
    """Owns one APScheduler instance and reconciles its job set with the DB."""

    def __init__(
        self,
        *,
        source_repo: SourceRepository,
        pipeline: IngestSourcePipeline,
        reconcile_interval_seconds: int = RECONCILE_INTERVAL_SECONDS,
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        self._source_repo = source_repo
        self._pipeline = pipeline
        self._reconcile_interval_seconds = reconcile_interval_seconds
        self._scheduler = scheduler or AsyncIOScheduler(timezone="UTC")
        self._tracked: dict[UUID, int] = {}  # source_id → poll_interval_minutes

    async def start(self) -> None:
        await self.reconcile()
        self._scheduler.add_job(
            self.reconcile,
            IntervalTrigger(seconds=self._reconcile_interval_seconds),
            id=RECONCILE_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        self._scheduler.start()
        logger.info("ingestion scheduler started")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("ingestion scheduler stopped")

    async def reconcile(self) -> None:
        """Sync the scheduled job list with what the database currently says.

        Public so tests can drive it deterministically without waiting for
        the interval trigger.
        """
        sources = await self._source_repo.list_enabled()
        wanted: dict[UUID, int] = {s.id: s.poll_interval_minutes for s in sources}

        for source_id in list(self._tracked):
            if source_id not in wanted:
                self._scheduler.remove_job(_job_id_for(source_id))
                self._tracked.pop(source_id)
                logger.info("scheduler: removed job for source {id}", id=source_id)

        for source_id, minutes in wanted.items():
            current = self._tracked.get(source_id)
            job_id = _job_id_for(source_id)
            if current is None:
                self._scheduler.add_job(
                    self._make_job(source_id),
                    IntervalTrigger(minutes=minutes),
                    id=job_id,
                    replace_existing=True,
                    max_instances=1,
                )
                self._tracked[source_id] = minutes
                logger.info(
                    "scheduler: added job for source {id} every {m} min",
                    id=source_id,
                    m=minutes,
                )
            elif current != minutes:
                self._scheduler.reschedule_job(
                    job_id, trigger=IntervalTrigger(minutes=minutes)
                )
                self._tracked[source_id] = minutes
                logger.info(
                    "scheduler: rescheduled source {id} from {old} to {new} min",
                    id=source_id,
                    old=current,
                    new=minutes,
                )

    def _make_job(self, source_id: UUID) -> Callable[[], Awaitable[None]]:
        """Bind a source-specific runner. Refetches the source per tick so
        URL / weight / enabled changes from Telegram take effect immediately
        on the *next* poll, not after the next reconcile."""

        async def _run() -> None:
            source = await self._source_repo.get_by_id(source_id)
            if source is None or not source.enabled:
                logger.info(
                    "scheduler: skipping tick for source {id} (gone or paused)",
                    id=source_id,
                )
                return
            await self._pipeline.run(source)

        return _run


def _job_id_for(source_id: UUID) -> str:
    return f"ingest-{source_id}"
