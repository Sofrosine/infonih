"""Telegram bot worker entrypoint.

Runs the long-poll loop for `/add-source`, `/list-sources`, `/set-interests`,
etc. Separate process from the scheduler — they share the database, neither
imports the other.

    uv run python -m infonih.scripts.run_telegram_bot
"""

from loguru import logger

from infonih.adapters.postgres import source_repository, user_settings_repository
from infonih.adapters.telegram_adapter import TelegramBot


def main() -> None:
    bot = TelegramBot(
        source_repo=source_repository,
        user_settings_repo=user_settings_repository,
    )
    app = bot.build_application()
    logger.info("telegram bot starting (long-poll)")
    app.run_polling()


if __name__ == "__main__":
    main()
