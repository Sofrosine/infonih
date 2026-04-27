from decimal import Decimal
from typing import Protocol
from uuid import UUID

from infonih.domain.category import Category
from infonih.domain.source import PollStatus, Source, SourceType


class SourceRepository(Protocol):
    """Storage contract for configured news sources.

    Implementations live under `adapters/<service>/`. The contract is
    storage-agnostic; callers depend on this Protocol, not on the
    concrete Postgres implementation.
    """

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
        """Insert a new enabled source. Raises if (user_id, url) or
        (user_id, name) collides with an existing row."""
        ...

    async def list_enabled(self, *, user_id: UUID | None = None) -> list[Source]:
        """Return all enabled sources for the user, scheduler-friendly order
        (oldest `last_polled_at` first; nulls first)."""
        ...

    async def get_by_name(
        self, name: str, *, user_id: UUID | None = None
    ) -> Source | None:
        """Case-insensitive exact-name lookup. Telegram /pause-source uses this."""
        ...

    async def get_by_id(self, source_id: UUID) -> Source | None:
        """Lookup by primary key. Scheduler refreshes source state per tick."""
        ...

    async def pause(self, source_id: UUID) -> None:
        """Set enabled=false. No-op if already paused."""
        ...

    async def resume(self, source_id: UUID) -> None:
        """Set enabled=true. No-op if already enabled."""
        ...

    async def remove(self, source_id: UUID) -> None:
        """Delete the source row. Articles previously ingested from this
        source are preserved; only the source registration goes away."""
        ...

    async def mark_polled(
        self,
        source_id: UUID,
        *,
        status: PollStatus,
        error: str | None = None,
    ) -> None:
        """Record the outcome of a poll attempt.

        On `ok`: stamps `last_polled_at = now()`, status `ok`, clears error,
        resets `consecutive_failures` to 0.
        On `failed`: stamps `last_polled_at = now()`, status `failed`,
        records the error message, increments `consecutive_failures`.
        """
        ...
