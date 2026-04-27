from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="infonih")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    database_url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://infonih:infonih@localhost:5432/infonih"),
        description="Async SQLAlchemy DSN. Use the +asyncpg driver.",
    )

    test_database_url: SecretStr = Field(
        default=SecretStr(
            "postgresql+asyncpg://infonih:infonih@localhost:5432/infonih_test"
        ),
        description="DSN for the isolated test database. Created on first test run.",
    )

    default_poll_interval_minutes: int = Field(default=60, ge=1)

    # LLM
    anthropic_api_key: SecretStr = Field(default=SecretStr(""))
    score_model: str = Field(default="claude-haiku-4-5")
    summarize_model: str = Field(default="claude-haiku-4-5")
    score_batch_size: int = Field(default=20, ge=1)
    score_interval_minutes: int = Field(default=5, ge=1)

    # Digest
    digest_max_items: int = Field(default=7, ge=1)
    score_threshold: int = Field(default=50, ge=0, le=100)
    digest_window_hours: int = Field(default=24, ge=1)
    digest_time_local: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")
    digest_timezone: str = Field(default="Asia/Jakarta")

    # Telegram
    telegram_bot_token: SecretStr = Field(default=SecretStr(""))
    telegram_chat_id: str = Field(default="")


settings = Settings()
