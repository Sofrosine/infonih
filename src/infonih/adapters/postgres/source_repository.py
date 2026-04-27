from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update

from infonih.adapters.postgres.models import SourceModel
from infonih.adapters.postgres.postgres_adapter import PostgresAdapter
from infonih.domain.category import Category
from infonih.domain.source import PollStatus, Source, SourceType


class PostgresSourceRepository:
    """Postgres implementation of `SourceRepository`."""

    def __init__(self, adapter: PostgresAdapter) -> None:
        self._adapter = adapter

    async def add(
        self,
        *,
        name: str,
        type: SourceType,
        url: str,
        category: Category,
        weight: Decimal = Decimal("1.0"),
        poll_interval_minutes: int = 60,
        user_id: UUID | None = None,
    ) -> Source:
        async with self._adapter.session() as session:
            model = SourceModel(
                user_id=user_id,
                name=name,
                type=type,
                url=url,
                category=category,
                weight=weight,
                poll_interval_minutes=poll_interval_minutes,
            )
            session.add(model)
            await session.flush()
            await session.refresh(model)
            return _to_domain(model)

    async def list_enabled(self, *, user_id: UUID | None = None) -> list[Source]:
        stmt = (
            select(SourceModel)
            .where(SourceModel.user_id.is_(user_id), SourceModel.enabled.is_(True))
            .order_by(SourceModel.last_polled_at.asc().nullsfirst())
        )
        async with self._adapter.session() as session:
            result = await session.execute(stmt)
            return [_to_domain(m) for m in result.scalars()]

    async def get_by_name(
        self, name: str, *, user_id: UUID | None = None
    ) -> Source | None:
        stmt = select(SourceModel).where(
            SourceModel.user_id.is_(user_id),
            func.lower(SourceModel.name) == name.lower(),
        )
        async with self._adapter.session() as session:
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return _to_domain(model) if model is not None else None

    async def get_by_id(self, source_id: UUID) -> Source | None:
        async with self._adapter.session() as session:
            model = await session.get(SourceModel, source_id)
            return _to_domain(model) if model is not None else None

    async def pause(self, source_id: UUID) -> None:
        await self._set_enabled(source_id, enabled=False)

    async def resume(self, source_id: UUID) -> None:
        await self._set_enabled(source_id, enabled=True)

    async def remove(self, source_id: UUID) -> None:
        async with self._adapter.session() as session:
            model = await session.get(SourceModel, source_id)
            if model is not None:
                await session.delete(model)

    async def mark_polled(
        self,
        source_id: UUID,
        *,
        status: PollStatus,
        error: str | None = None,
    ) -> None:
        if status is PollStatus.OK:
            values = {
                "last_polled_at": datetime.now(UTC),
                "last_poll_status": PollStatus.OK,
                "last_poll_error": None,
                "consecutive_failures": 0,
            }
        else:
            values = {
                "last_polled_at": datetime.now(UTC),
                "last_poll_status": PollStatus.FAILED,
                "last_poll_error": error,
                "consecutive_failures": SourceModel.consecutive_failures + 1,
            }
        stmt = update(SourceModel).where(SourceModel.id == source_id).values(**values)
        async with self._adapter.session() as session:
            await session.execute(stmt)

    async def _set_enabled(self, source_id: UUID, *, enabled: bool) -> None:
        stmt = update(SourceModel).where(SourceModel.id == source_id).values(enabled=enabled)
        async with self._adapter.session() as session:
            await session.execute(stmt)


def _to_domain(model: SourceModel) -> Source:
    return Source(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        type=model.type,
        url=model.url,
        category=model.category,
        weight=model.weight,
        poll_interval_minutes=model.poll_interval_minutes,
        enabled=model.enabled,
        last_polled_at=model.last_polled_at,
        last_poll_status=model.last_poll_status,
        last_poll_error=model.last_poll_error,
        consecutive_failures=model.consecutive_failures,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
