from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from infonih.domain.cost_event import CostSummary


class CostRepository(Protocol):
    """Storage contract for LLM cost events."""

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
        """Append a single cost event. Never raises a billing/data error
        all the way back to the caller — callers must not have their LLM
        call fail because the audit log write failed."""
        ...

    async def summarize_since(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        user_id: UUID | None = None,
    ) -> CostSummary:
        """Grand total over the window."""
        ...

    async def summarize_by_flow_since(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        user_id: UUID | None = None,
    ) -> list[CostSummary]:
        """One row per flow, sorted by cost descending."""
        ...
