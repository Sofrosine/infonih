"""One-time bootstrap: seed sources and interests into the database.

Reads `seeds/sources.yaml` and `seeds/interests.md` if present. Idempotent
on repeated runs:

* Sources whose URL or name already exists are skipped (logged and counted).
* Interests are written only if no `user_settings` row exists yet — re-running
  does not bump the interests version.

After the initial seed, all source and interest changes go through Telegram
commands (the runtime path); this script is for fresh deployments and forks.

Run via:
    uv run python -m infonih.scripts.seed
"""

import asyncio
from decimal import Decimal
from pathlib import Path

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from infonih.domain.category import Category
from infonih.domain.repositories.source_repository import SourceRepository
from infonih.domain.repositories.user_settings_repository import (
    UserSettingsRepository,
)
from infonih.domain.source import SourceType

DEFAULT_SEEDS_DIR = Path("seeds")
SOURCES_FILENAME = "sources.yaml"
INTERESTS_FILENAME = "interests.md"


class SeedSource(BaseModel):
    """Schema for one entry in `seeds/sources.yaml`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    type: SourceType
    url: HttpUrl
    category: Category
    weight: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0.1"), le=Decimal("10.0"))
    poll_interval_minutes: int = Field(default=60, ge=1)


class SeedSourcesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[SeedSource]


class SeedReport(BaseModel):
    """Counts returned from `seed()` for logging and tests."""

    model_config = ConfigDict(frozen=True)

    sources_added: int = 0
    sources_skipped: int = 0
    interests_set: bool = False
    interests_skipped: bool = False


async def seed(
    *,
    source_repo: SourceRepository,
    user_settings_repo: UserSettingsRepository,
    seeds_dir: Path = DEFAULT_SEEDS_DIR,
) -> SeedReport:
    """Run both source and interests seeding. Repos are passed in so tests
    can substitute the test-database-bound singletons."""
    sources_added, sources_skipped = await _seed_sources(
        source_repo, seeds_dir / SOURCES_FILENAME
    )
    interests_set, interests_skipped = await _seed_interests(
        user_settings_repo, seeds_dir / INTERESTS_FILENAME
    )
    return SeedReport(
        sources_added=sources_added,
        sources_skipped=sources_skipped,
        interests_set=interests_set,
        interests_skipped=interests_skipped,
    )


async def _seed_sources(
    repo: SourceRepository, sources_path: Path
) -> tuple[int, int]:
    # Blocking file I/O is fine here: this is a one-shot startup script,
    # not a request hot path.
    if not sources_path.exists():  # noqa: ASYNC240
        logger.info("{path} not found; skipping source seed", path=sources_path)
        return 0, 0

    raw = yaml.safe_load(sources_path.read_text()) or {"sources": []}  # noqa: ASYNC240
    parsed = SeedSourcesFile.model_validate(raw)

    added = 0
    skipped = 0
    for src in parsed.sources:
        existing = await repo.get_by_name(src.name)
        if existing is not None:
            logger.info("source '{name}' already exists; skipping", name=src.name)
            skipped += 1
            continue
        await repo.add(
            name=src.name,
            type=src.type,
            url=str(src.url),
            category=src.category,
            weight=src.weight,
            poll_interval_minutes=src.poll_interval_minutes,
        )
        logger.info("seeded source: {name}", name=src.name)
        added += 1
    return added, skipped


async def _seed_interests(
    repo: UserSettingsRepository, interests_path: Path
) -> tuple[bool, bool]:
    if not interests_path.exists():  # noqa: ASYNC240
        logger.info("{path} not found; skipping interests seed", path=interests_path)
        return False, False

    text = interests_path.read_text().strip()  # noqa: ASYNC240
    if not text:
        logger.warning("{path} is empty; skipping interests seed", path=interests_path)
        return False, True

    existing = await repo.get()
    if existing is not None:
        logger.info("user settings already exist; skipping interests seed")
        return False, True

    await repo.set_interests(text)
    logger.info("seeded interests ({chars} chars)", chars=len(text))
    return True, False


async def _main() -> None:
    """Entry point that wires the production singletons."""
    from infonih.adapters.postgres import (
        source_repository,
        user_settings_repository,
    )

    report = await seed(
        source_repo=source_repository,
        user_settings_repo=user_settings_repository,
    )
    logger.info(
        "seed complete: sources_added={a} sources_skipped={s} "
        "interests_set={i} interests_skipped={k}",
        a=report.sources_added,
        s=report.sources_skipped,
        i=report.interests_set,
        k=report.interests_skipped,
    )


if __name__ == "__main__":
    asyncio.run(_main())
