"""Long-running scheduler entrypoint.

Starts the ingestion scheduler and idles until interrupted (Ctrl+C / SIGTERM).
Run as its own process — separate from the FastAPI web app:

    uv run python -m infonih.scripts.run_scheduler

The web app and the worker share the database; neither imports the other.
"""

import asyncio
import signal

from loguru import logger

from infonih.adapters.postgres import article_repository, source_repository
from infonih.adapters.rss_adapter import rss
from infonih.agents.pipelines.ingest_source import IngestSourcePipeline
from infonih.scheduler import IngestionScheduler


async def _main() -> None:
    pipeline = IngestSourcePipeline(
        rss=rss,
        article_repo=article_repository,
        source_repo=source_repository,
    )
    scheduler = IngestionScheduler(
        source_repo=source_repository,
        pipeline=pipeline,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await scheduler.start()
    logger.info("scheduler running; press Ctrl+C to stop")
    try:
        await stop_event.wait()
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(_main())
