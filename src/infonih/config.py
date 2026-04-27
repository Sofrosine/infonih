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


settings = Settings()
