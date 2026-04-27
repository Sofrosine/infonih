"""Manual end-to-end ingestion smoke test.

Resolves a source by name, runs the ingestion pipeline against it once,
prints the result. Exists as a sanity check before the scheduler is wired
in — useful for verifying that the entire ingest spine (fetch → normalize
→ dedup-insert → mark polled) works against a real source and a real
Postgres.

Usage:
    uv run python -m infonih.scripts.ingest_once "<source name>"

Examples:
    uv run python -m infonih.scripts.ingest_once "Simon Willison"
    uv run python -m infonih.scripts.ingest_once "BBC World"
"""

import asyncio
import sys

from loguru import logger

from infonih.adapters.postgres import article_repository, source_repository
from infonih.adapters.rss_adapter import rss
from infonih.agents.pipelines.ingest_source import IngestSourcePipeline


async def _main(source_name: str) -> int:
    source = await source_repository.get_by_name(source_name)
    if source is None:
        logger.error(
            "no source named '{name}' (try `psql` SELECT name FROM sources)",
            name=source_name,
        )
        return 1

    pipeline = IngestSourcePipeline(
        rss=rss,
        article_repo=article_repository,
        source_repo=source_repository,
    )
    result = await pipeline.run(source)

    logger.info("result: {r}", r=result.model_dump_json(indent=2))
    return 0 if result.succeeded else 2


if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error('usage: python -m infonih.scripts.ingest_once "<source name>"')
        sys.exit(1)
    sys.exit(asyncio.run(_main(sys.argv[1])))
