"""Test fixtures for the infonih test suite.

Tests run against a dedicated `infonih_test` database on the dev Postgres
instance — kept separate from `infonih` so test runs never touch real data.
The DB is created automatically on first run via an asyncpg admin connection;
schema is created from `Base.metadata.create_all` (not Alembic) for speed.
Tables are truncated between tests for isolation without per-test rollback
ceremony.
"""

from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import asyncpg
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from infonih.adapters.postgres.article_repository import PostgresArticleRepository
from infonih.adapters.postgres.models import Base
from infonih.adapters.postgres.postgres_adapter import PostgresAdapter
from infonih.adapters.postgres.source_repository import PostgresSourceRepository
from infonih.adapters.postgres.user_settings_repository import (
    PostgresUserSettingsRepository,
)
from infonih.config import settings


def _admin_dsn_for(test_dsn: str) -> tuple[str, str]:
    """Strip +asyncpg, swap target db for the maintenance `postgres` db.

    Returns (admin_dsn_for_asyncpg, target_db_name).
    """
    raw = test_dsn.replace("postgresql+asyncpg://", "postgresql://")
    parts = urlsplit(raw)
    target_db = parts.path.lstrip("/")
    admin = raw.rsplit("/", 1)[0] + "/postgres"
    return admin, target_db


async def _ensure_test_database_exists() -> None:
    admin_dsn, target_db = _admin_dsn_for(
        settings.test_database_url.get_secret_value()
    )
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", target_db
        )
        if not exists:
            # CREATE DATABASE cannot run inside a transaction; asyncpg
            # auto-commits each statement on a connection by default.
            await conn.execute(f'CREATE DATABASE "{target_db}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[None]:
    """Session-scoped: ensure the test DB exists and the schema is created.

    Yields the engine, drops all tables on teardown so the next session
    starts from a known state.
    """
    await _ensure_test_database_exists()
    engine = create_async_engine(settings.test_database_url.get_secret_value())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def test_adapter(test_engine) -> AsyncIterator[PostgresAdapter]:
    """Per-test PostgresAdapter wrapping the shared test engine.

    Truncates all tables before yielding so each test starts with empty data.
    """
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async with factory() as cleanup:
        await cleanup.execute(
            text("TRUNCATE sources, articles, user_settings RESTART IDENTITY CASCADE")
        )
        await cleanup.commit()

    adapter = PostgresAdapter.__new__(PostgresAdapter)
    adapter._engine = test_engine  # type: ignore[attr-defined]
    adapter._sessionmaker = factory  # type: ignore[attr-defined]
    yield adapter


@pytest_asyncio.fixture
async def source_repo(test_adapter: PostgresAdapter) -> PostgresSourceRepository:
    return PostgresSourceRepository(test_adapter)


@pytest_asyncio.fixture
async def article_repo(test_adapter: PostgresAdapter) -> PostgresArticleRepository:
    return PostgresArticleRepository(test_adapter)


@pytest_asyncio.fixture
async def user_settings_repo(
    test_adapter: PostgresAdapter,
) -> PostgresUserSettingsRepository:
    return PostgresUserSettingsRepository(test_adapter)


@pytest_asyncio.fixture
async def db_session(test_adapter: PostgresAdapter) -> AsyncIterator[AsyncSession]:
    """Raw session for tests that need to assert against the database directly."""
    async with test_adapter.session() as session:
        yield session
