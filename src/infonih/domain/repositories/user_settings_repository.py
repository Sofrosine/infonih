from typing import Protocol
from uuid import UUID

from infonih.domain.user_settings import UserSettings


class UserSettingsRepository(Protocol):
    """Storage contract for per-user preferences (interests, schedule)."""

    async def get(self, *, user_id: UUID | None = None) -> UserSettings | None:
        """Return the user's settings row, or None if it has not been seeded yet."""
        ...

    async def set_interests(
        self, interests_text: str, *, user_id: UUID | None = None
    ) -> UserSettings:
        """Upsert the interests description and bump `interests_version`.

        On first call, creates the row with `version=1`. On subsequent calls,
        increments the version atomically — articles record which version
        scored them via `articles.scored_with_interest_version`.
        """
        ...
