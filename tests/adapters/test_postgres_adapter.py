"""Smoke test for the postgres adapter.

Skipped automatically when the local Postgres at $DATABASE_URL is unreachable
(e.g., CI without the docker-compose stack running). Adapters are tested
against a real database per CLAUDE.md — mocking SQLAlchemy is more pain than
value.
"""

import pytest
from sqlalchemy import text

from infonih.adapters.postgres import postgres


@pytest.mark.asyncio
async def test_session_executes_select_one() -> None:
    try:
        async with postgres.session() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar_one()
    except Exception as exc:
        pytest.skip(f"postgres unreachable: {exc}")

    assert value == 1
