from infonih.adapters.postgres.article_repository import PostgresArticleRepository
from infonih.adapters.postgres.postgres_adapter import postgres
from infonih.adapters.postgres.source_repository import PostgresSourceRepository
from infonih.adapters.postgres.user_settings_repository import PostgresUserSettingsRepository
from infonih.domain.repositories.article_repository import ArticleRepository
from infonih.domain.repositories.source_repository import SourceRepository
from infonih.domain.repositories.user_settings_repository import UserSettingsRepository

# Singletons exposed via Protocol types so callers depend on the contract,
# not the concrete Postgres implementation.
source_repository: SourceRepository = PostgresSourceRepository(postgres)
article_repository: ArticleRepository = PostgresArticleRepository(postgres)
user_settings_repository: UserSettingsRepository = PostgresUserSettingsRepository(postgres)

__all__ = [
    "article_repository",
    "postgres",
    "source_repository",
    "user_settings_repository",
]
