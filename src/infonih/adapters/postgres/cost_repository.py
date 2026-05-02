from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from infonih.adapters.postgres.models import CostEventModel
from infonih.adapters.postgres.postgres_adapter import PostgresAdapter
from infonih.domain.cost_event import CostSummary


class PostgresCostRepository:
    """Postgres implementation of `CostRepository`."""

    def __init__(self, adapter: PostgresAdapter) -> None:
        self._adapter = adapter

    async def record(
        self,
        *,
        flow: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        article_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        async with self._adapter.session() as session:
            session.add(
                CostEventModel(
                    user_id=user_id,
                    flow=flow,
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_creation_input_tokens=cache_creation_input_tokens,
                    cache_read_input_tokens=cache_read_input_tokens,
                    cost_usd=cost_usd,
                    article_id=article_id,
                )
            )

    async def summarize_since(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        user_id: UUID | None = None,
    ) -> CostSummary:
        stmt = select(
            func.count().label("call_count"),
            func.coalesce(func.sum(CostEventModel.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(CostEventModel.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(CostEventModel.cost_usd), Decimal("0")).label("cost_usd"),
        ).where(
            CostEventModel.user_id.is_(user_id),
            CostEventModel.created_at >= since,
        )
        if until is not None:
            stmt = stmt.where(CostEventModel.created_at < until)
        async with self._adapter.session() as session:
            result = await session.execute(stmt)
            row = result.one()
        return CostSummary(
            call_count=int(row.call_count or 0),
            input_tokens=int(row.input_tokens),
            output_tokens=int(row.output_tokens),
            cost_usd=Decimal(row.cost_usd),
        )

    async def summarize_by_flow_since(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        user_id: UUID | None = None,
    ) -> list[CostSummary]:
        stmt = (
            select(
                CostEventModel.flow,
                func.count().label("call_count"),
                func.coalesce(func.sum(CostEventModel.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(CostEventModel.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(CostEventModel.cost_usd), Decimal("0")).label("cost_usd"),
            )
            .where(
                CostEventModel.user_id.is_(user_id),
                CostEventModel.created_at >= since,
            )
            .group_by(CostEventModel.flow)
            .order_by(func.sum(CostEventModel.cost_usd).desc())
        )
        if until is not None:
            stmt = stmt.where(CostEventModel.created_at < until)
        async with self._adapter.session() as session:
            result = await session.execute(stmt)
            rows = result.all()
        return [
            CostSummary(
                flow=row.flow,
                call_count=int(row.call_count),
                input_tokens=int(row.input_tokens),
                output_tokens=int(row.output_tokens),
                cost_usd=Decimal(row.cost_usd),
            )
            for row in rows
        ]
