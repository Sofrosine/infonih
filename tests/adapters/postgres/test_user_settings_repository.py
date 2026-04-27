from infonih.adapters.postgres.user_settings_repository import (
    PostgresUserSettingsRepository,
)


async def test_get_returns_none_before_first_set(
    user_settings_repo: PostgresUserSettingsRepository,
) -> None:
    assert await user_settings_repo.get() is None


async def test_set_interests_creates_row_with_version_one(
    user_settings_repo: PostgresUserSettingsRepository,
) -> None:
    settings = await user_settings_repo.set_interests("AI engineering, AI policy")

    assert settings.interests_text == "AI engineering, AI policy"
    assert settings.interests_version == 1


async def test_set_interests_bumps_version_on_subsequent_calls(
    user_settings_repo: PostgresUserSettingsRepository,
) -> None:
    await user_settings_repo.set_interests("v1")
    await user_settings_repo.set_interests("v2")
    third = await user_settings_repo.set_interests("v3")

    assert third.interests_text == "v3"
    assert third.interests_version == 3


async def test_get_returns_latest_after_set(
    user_settings_repo: PostgresUserSettingsRepository,
) -> None:
    await user_settings_repo.set_interests("first")
    await user_settings_repo.set_interests("second")

    found = await user_settings_repo.get()

    assert found is not None
    assert found.interests_text == "second"
    assert found.interests_version == 2
