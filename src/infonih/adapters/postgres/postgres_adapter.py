from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from infonih.config import settings


class PostgresAdapter:
    """Singleton wrapper around the async SQLAlchemy engine and session factory.

    Hold a single instance per process (`postgres`). Every call site gets a
    fresh `AsyncSession` via `session()`; the adapter never leaks raw engines
    or sessionmakers outside this module.
    """

    def __init__(self, dsn: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            dsn,
            echo=settings.debug,
            pool_pre_ping=True,
        )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an `AsyncSession` and commit on success, rollback on error."""
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        logger.info("disposing postgres engine")
        await self._engine.dispose()


postgres = PostgresAdapter(settings.database_url.get_secret_value())
