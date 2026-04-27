from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from infonih.adapters.postgres.models import UserSettingsModel
from infonih.adapters.postgres.postgres_adapter import PostgresAdapter
from infonih.domain.user_settings import UserSettings


class PostgresUserSettingsRepository:
    """Postgres implementation of `UserSettingsRepository`."""

    def __init__(self, adapter: PostgresAdapter) -> None:
        self._adapter = adapter

    async def get(self, *, user_id: UUID | None = None) -> UserSettings | None:
        stmt = select(UserSettingsModel).where(UserSettingsModel.user_id.is_(user_id))
        async with self._adapter.session() as session:
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return _to_domain(model) if model is not None else None

    async def set_interests(
        self, interests_text: str, *, user_id: UUID | None = None
    ) -> UserSettings:
        # Upsert: insert with version=1, or bump version on conflict.
        # The unique constraint is `(user_id) NULLS NOT DISTINCT`, so a
        # second NULL collides with the first and updates instead.
        stmt = pg_insert(UserSettingsModel).values(
            user_id=user_id,
            interests_text=interests_text,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_settings_user",
            set_={
                "interests_text": stmt.excluded.interests_text,
                "interests_version": UserSettingsModel.interests_version + 1,
            },
        ).returning(UserSettingsModel)
        async with self._adapter.session() as session:
            result = await session.execute(stmt)
            row = result.scalar_one()
            await session.refresh(row)
            return _to_domain(row)


def _to_domain(model: UserSettingsModel) -> UserSettings:
    return UserSettings(
        id=model.id,
        user_id=model.user_id,
        interests_text=model.interests_text,
        interests_version=model.interests_version,
        digest_time_local=model.digest_time_local,
        digest_timezone=model.digest_timezone,
        score_threshold=model.score_threshold,
        digest_max_items=model.digest_max_items,
        category_caps=model.category_caps,
        paused_until=model.paused_until,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
