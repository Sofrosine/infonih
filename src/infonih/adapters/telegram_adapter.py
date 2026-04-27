"""Telegram adapter — message send + bot command handling.

Wraps `python-telegram-bot` v22 async API. Two responsibilities:

1. `send(text)` — push a digest message to the configured chat. Used by the
   digest pipeline.
2. `run_bot()` — long-poll for `/add-source`, `/list-sources`, etc. Used by
   the bot worker process.

These split because the digest sends from a one-shot scheduler tick (no
event loop owned by PTB), while bot commands need PTB's async polling
loop. They share an underlying `Bot` instance.
"""

from collections.abc import Awaitable, Callable
from decimal import Decimal

from loguru import logger
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from infonih.config import settings
from infonih.domain.category import Category
from infonih.domain.repositories.source_repository import SourceRepository
from infonih.domain.repositories.user_settings_repository import (
    UserSettingsRepository,
)
from infonih.domain.source import SourceType


class TelegramAdapter:
    """Singleton Telegram client. Send-only; bot polling lives in TelegramBot."""

    def __init__(self) -> None:
        token = settings.telegram_bot_token.get_secret_value()
        self._bot: Bot | None = Bot(token) if token else None
        self._chat_id = settings.telegram_chat_id

    async def send(self, text: str) -> int | None:
        """Send `text` to the configured chat. Returns the message_id, or
        None if Telegram is not configured (silent no-op for dev)."""
        if self._bot is None or not self._chat_id:
            logger.warning("telegram not configured; skipping send: {t}", t=text[:80])
            return None
        message = await self._bot.send_message(
            chat_id=self._chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
        return message.message_id


telegram = TelegramAdapter()


# ---------------------------------------------------------------------------
# Bot command handlers — separated so they can be unit-tested with fake repos.
# ---------------------------------------------------------------------------


class TelegramBot:
    """Bot worker. Wires command handlers to the source / settings repos."""

    def __init__(
        self,
        *,
        source_repo: SourceRepository,
        user_settings_repo: UserSettingsRepository,
    ) -> None:
        self._source_repo = source_repo
        self._user_settings_repo = user_settings_repo

    async def cmd_start(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "infonih bot ready. Try /list_sources, /add_source, /set_interests."
        )

    async def cmd_list_sources(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        sources = await self._source_repo.list_enabled()
        if not sources:
            await update.message.reply_text(
                "No sources yet. Use /add_source <url> <category> to add one."
            )
            return
        lines = [
            f"• <b>{s.name}</b> — {s.category.value} "
            f"(weight {s.weight}, every {s.poll_interval_minutes}m)"
            for s in sources
        ]
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_add_source(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args or []
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /add_source <url> <category> [weight] [poll_minutes]\n"
                "Categories: " + ", ".join(c.value for c in Category)
            )
            return
        url = args[0]
        try:
            category = Category(args[1])
        except ValueError:
            await update.message.reply_text(
                f"Unknown category. Valid: {', '.join(c.value for c in Category)}"
            )
            return
        weight = Decimal(args[2]) if len(args) > 2 else Decimal("1.0")
        poll_minutes = int(args[3]) if len(args) > 3 else settings.default_poll_interval_minutes
        # Derive a default name from the URL host until we probe-fetch the feed title.
        from urllib.parse import urlparse

        host = urlparse(url).hostname or url
        try:
            source = await self._source_repo.add(
                name=host,
                type=SourceType.RSS,
                url=url,
                category=category,
                weight=weight,
                poll_interval_minutes=poll_minutes,
            )
        except Exception as exc:
            await update.message.reply_text(f"Failed to add source: {exc}")
            return
        await update.message.reply_text(
            f"Added '{source.name}' ({category.value}, weight {weight}, every {poll_minutes}m). "
            "First poll within the interval."
        )

    async def cmd_pause_source(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._toggle(update, ctx, enable=False, verb="paused")

    async def cmd_resume_source(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._toggle(update, ctx, enable=True, verb="resumed")

    async def cmd_remove_source(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not ctx.args:
            await update.message.reply_text("Usage: /remove_source <name>")
            return
        name = " ".join(ctx.args)
        source = await self._source_repo.get_by_name(name)
        if source is None:
            await update.message.reply_text(f"No source named '{name}'.")
            return
        await self._source_repo.remove(source.id)
        await update.message.reply_text(f"Removed source '{source.name}'.")

    async def cmd_set_interests(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        text = " ".join(ctx.args).strip() if ctx.args else ""
        if not text:
            await update.message.reply_text(
                "Usage: /set_interests <description>\n"
                "Send a few sentences describing what you want in your digest."
            )
            return
        result = await self._user_settings_repo.set_interests(text)
        await update.message.reply_text(
            f"Interests updated (version {result.interests_version})."
        )

    async def cmd_show_interests(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        s = await self._user_settings_repo.get()
        if s is None:
            await update.message.reply_text("No interests set. Use /set_interests <text>.")
            return
        await update.message.reply_text(
            f"Interests (v{s.interests_version}):\n\n{s.interests_text}"
        )

    async def _toggle(
        self,
        update: Update,
        ctx: ContextTypes.DEFAULT_TYPE,
        *,
        enable: bool,
        verb: str,
    ) -> None:
        if not ctx.args:
            cmd = "resume_source" if enable else "pause_source"
            await update.message.reply_text(f"Usage: /{cmd} <name>")
            return
        name = " ".join(ctx.args)
        source = await self._source_repo.get_by_name(name)
        if source is None:
            await update.message.reply_text(f"No source named '{name}'.")
            return
        if enable:
            await self._source_repo.resume(source.id)
        else:
            await self._source_repo.pause(source.id)
        await update.message.reply_text(f"{verb.capitalize()} source '{source.name}'.")

    def build_application(self) -> Application:
        token = settings.telegram_bot_token.get_secret_value()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        app = Application.builder().token(token).build()
        for cmd, handler in self._handlers().items():
            app.add_handler(CommandHandler(cmd, handler))
        return app

    def _handlers(self) -> dict[str, Callable[..., Awaitable[None]]]:
        return {
            "start": self.cmd_start,
            "list_sources": self.cmd_list_sources,
            "add_source": self.cmd_add_source,
            "pause_source": self.cmd_pause_source,
            "resume_source": self.cmd_resume_source,
            "remove_source": self.cmd_remove_source,
            "set_interests": self.cmd_set_interests,
            "show_interests": self.cmd_show_interests,
        }
