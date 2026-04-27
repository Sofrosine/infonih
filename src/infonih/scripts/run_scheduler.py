"""Long-running scheduler entrypoint.

Runs three recurring jobs in one process, on one event loop:

1. Source ingestion — per-source, interval driven by each source's
   `poll_interval_minutes`. Reconciled against the DB every minute.
2. Scoring — every `SCORE_INTERVAL_MINUTES`, batches `SCORE_BATCH_SIZE`
   articles through Claude.
3. Daily digest — at the configured `DIGEST_TIME_LOCAL` in `DIGEST_TIMEZONE`.

Run as its own process — separate from the Telegram bot and the FastAPI
web app:

    uv run python -m infonih.scripts.run_scheduler
"""

import asyncio
import signal

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from infonih.adapters.anthropic_adapter import anthropic_adapter
from infonih.adapters.postgres import (
    article_repository,
    source_repository,
    user_settings_repository,
)
from infonih.adapters.rss_adapter import rss
from infonih.adapters.telegram_adapter import telegram
from infonih.agents.pipelines.build_daily_digest import BuildDailyDigestPipeline
from infonih.agents.pipelines.ingest_source import IngestSourcePipeline
from infonih.agents.pipelines.score_articles import ScoreArticlesPipeline
from infonih.config import settings
from infonih.scheduler import IngestionScheduler


async def _main() -> None:
    ingest_pipeline = IngestSourcePipeline(
        rss=rss,
        article_repo=article_repository,
        source_repo=source_repository,
    )
    score_pipeline = ScoreArticlesPipeline(
        anthropic=anthropic_adapter,
        article_repo=article_repository,
        user_settings_repo=user_settings_repository,
    )
    digest_pipeline = BuildDailyDigestPipeline(
        anthropic=anthropic_adapter,
        article_repo=article_repository,
        telegram=telegram,
    )

    scheduler = IngestionScheduler(
        source_repo=source_repository,
        pipeline=ingest_pipeline,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await scheduler.start()

    # Scoring tick — every SCORE_INTERVAL_MINUTES.
    scheduler.aps.add_job(
        score_pipeline.run,
        IntervalTrigger(minutes=settings.score_interval_minutes),
        id="score-articles",
        replace_existing=True,
        max_instances=1,
    )

    # Daily digest — at DIGEST_TIME_LOCAL in DIGEST_TIMEZONE.
    hh, mm = settings.digest_time_local.split(":")
    scheduler.aps.add_job(
        digest_pipeline.run,
        CronTrigger(hour=int(hh), minute=int(mm), timezone=settings.digest_timezone),
        id="daily-digest",
        replace_existing=True,
        max_instances=1,
    )

    logger.info(
        "worker running: ingest reconcile + scoring every {s}m + digest at {t} {tz}",
        s=settings.score_interval_minutes,
        t=settings.digest_time_local,
        tz=settings.digest_timezone,
    )
    try:
        await stop_event.wait()
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(_main())
