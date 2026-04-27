from pathlib import Path

import pytest

from infonih.adapters.postgres.source_repository import PostgresSourceRepository
from infonih.adapters.postgres.user_settings_repository import (
    PostgresUserSettingsRepository,
)
from infonih.scripts.seed import seed


@pytest.fixture
def seeds_dir(tmp_path: Path) -> Path:
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        "sources:\n"
        "  - name: Simon Willison\n"
        "    type: rss\n"
        "    url: https://simonwillison.net/atom/everything/\n"
        "    category: ai_engineering\n"
        "    weight: 1.5\n"
        "    poll_interval_minutes: 60\n"
        "  - name: BBC World\n"
        "    type: rss\n"
        "    url: https://feeds.bbci.co.uk/news/world/rss.xml\n"
        "    category: politics\n"
        "    weight: 0.8\n"
        "    poll_interval_minutes: 60\n"
    )
    interests_md = tmp_path / "interests.md"
    interests_md.write_text("AI engineering, AI policy, Indonesian politics.")
    return tmp_path


async def test_seed_first_run_inserts_everything(
    seeds_dir: Path,
    source_repo: PostgresSourceRepository,
    user_settings_repo: PostgresUserSettingsRepository,
) -> None:
    report = await seed(
        source_repo=source_repo,
        user_settings_repo=user_settings_repo,
        seeds_dir=seeds_dir,
    )

    assert report.sources_added == 2
    assert report.sources_skipped == 0
    assert report.interests_set is True
    assert report.interests_skipped is False

    sources = await source_repo.list_enabled()
    assert {s.name for s in sources} == {"Simon Willison", "BBC World"}

    settings = await user_settings_repo.get()
    assert settings is not None
    assert settings.interests_text == "AI engineering, AI policy, Indonesian politics."
    assert settings.interests_version == 1


async def test_seed_second_run_is_idempotent(
    seeds_dir: Path,
    source_repo: PostgresSourceRepository,
    user_settings_repo: PostgresUserSettingsRepository,
) -> None:
    await seed(
        source_repo=source_repo,
        user_settings_repo=user_settings_repo,
        seeds_dir=seeds_dir,
    )

    second = await seed(
        source_repo=source_repo,
        user_settings_repo=user_settings_repo,
        seeds_dir=seeds_dir,
    )

    assert second.sources_added == 0
    assert second.sources_skipped == 2
    assert second.interests_set is False
    assert second.interests_skipped is True

    settings = await user_settings_repo.get()
    assert settings is not None
    assert settings.interests_version == 1  # NOT bumped


async def test_seed_no_files_is_noop(
    tmp_path: Path,
    source_repo: PostgresSourceRepository,
    user_settings_repo: PostgresUserSettingsRepository,
) -> None:
    report = await seed(
        source_repo=source_repo,
        user_settings_repo=user_settings_repo,
        seeds_dir=tmp_path,  # empty dir
    )

    assert report.sources_added == 0
    assert report.sources_skipped == 0
    assert report.interests_set is False
    assert report.interests_skipped is False
    assert await source_repo.list_enabled() == []
    assert await user_settings_repo.get() is None


async def test_seed_empty_interests_file_skips(
    tmp_path: Path,
    source_repo: PostgresSourceRepository,
    user_settings_repo: PostgresUserSettingsRepository,
) -> None:
    (tmp_path / "interests.md").write_text("   \n   ")

    report = await seed(
        source_repo=source_repo,
        user_settings_repo=user_settings_repo,
        seeds_dir=tmp_path,
    )

    assert report.interests_set is False
    assert report.interests_skipped is True
    assert await user_settings_repo.get() is None
