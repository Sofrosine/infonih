<div align="center">

# 📰 infonih

**A personal AI news digest, delivered as a Telegram message every morning.**

*"info nih" — Indonesian for "got info for you."*

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-de5ff7)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Personal use first](https://img.shields.io/badge/audience-personal%20use%20first-orange.svg)](#who-this-is-for)

<!-- HERO SCREENSHOT: replace with a real digest from your bot.
     Suggested size: 800px wide. Place at docs/img/digest-hero.png -->
<img src="docs/img/digest-hero.png" alt="infonih daily digest in Telegram" width="600" />

</div>

---

## What it is

infonih reads articles from sources **you** configure (RSS feeds today; HN/ArXiv later), scores each one against **your** interests using Claude, and ships a focused daily digest to **your** Telegram chat. No web dashboard, no mobile app, no email. Telegram is the only interface.

It exists to replace doomscrolling for one specific person — the author — and is published openly so other developers can fork it and run their own.

> **This is shared, not offered as a service.** No SLA, no support, no roadmap promises. Fork it, configure it for yourself, run it on your own infrastructure.

## Who this is for

- **You** — the author or a fellow self-hoster who wants signal extracted from AI / policy / news without committing to another SaaS subscription.
- **You're comfortable** with Python, Postgres, Docker, and a cheap VPS.
- **You want one focused user**, not a multi-tenant product.

If you want a polished, zero-config consumer experience, look elsewhere — [Noscroll](https://noscroll.com/) is one option. infonih makes no attempt to compete there.

---

## Screenshots

<!-- Replace each placeholder image with a real screenshot from your bot. -->

<table>
  <tr>
    <td align="center" width="33%">
      <img src="docs/img/digest-example.png" alt="A real daily digest" /><br/>
      <sub><b>Daily digest at 07:00</b></sub>
    </td>
    <td align="center" width="33%">
      <img src="docs/img/bot-commands.png" alt="Bot commands in action" /><br/>
      <sub><b>Source management via Telegram</b></sub>
    </td>
    <td align="center" width="33%">
      <img src="docs/img/list-sources.png" alt="/list_sources output" /><br/>
      <sub><b>/list_sources output</b></sub>
    </td>
  </tr>
</table>

---

## How it works

```
                 ┌──────────────────────┐
                 │   Postgres (pgvector)│
                 │  sources / articles  │
                 │   user_settings      │
                 └────────┬─────────────┘
                          │
       ┌──────────────────┼──────────────────┐
       │                  │                  │
       ▼                  ▼                  ▼
 ┌──────────┐      ┌────────────┐      ┌──────────────┐
 │ Scheduler│      │  Telegram  │      │ Manual CLIs  │
 │  worker  │      │ bot worker │      │  (seed,      │
 │          │      │            │      │ ingest_once) │
 │  • RSS   │      │ /list_…    │      └──────────────┘
 │    poll  │      │ /add_…     │
 │  • Score │      │ /set_…     │
 │  • Daily │      │ /pause_…   │
 │   digest │      │ /resume_…  │
 │  cron    │      │ /remove_…  │
 └─────┬────┘      └─────┬──────┘
       │                 │
       │                 ▼
       │           ┌──────────┐
       └──────────►│ Telegram │
                   │   chat   │
                   └──────────┘
```

Three concurrent processes, all sharing Postgres and otherwise isolated:

1. **Scheduler worker** runs three jobs: per-source RSS polling, batch article scoring, and the daily digest cron.
2. **Telegram bot worker** long-polls for `/add_source`, `/set_interests`, etc.
3. **Postgres** is the single source of truth — sources, articles, scores, and user settings all live here.

A typical article's lifecycle:

```
RSS feed ──poll──► insert (status=unscored, is_backfill=true|false)
                       │
                       │ every 5 min
                       ▼
                ┌─────────────────┐
                │ Claude scores   │
                │ → status=scored │
                └────────┬────────┘
                         │
                         │ at 07:00 daily
                         ▼
                ┌─────────────────────┐
                │ Top N by score      │
                │ summarised by Claude│
                │ → Telegram message  │
                │ → sent_in_digest_at │
                └─────────────────────┘
```

---

## Features

- ✅ **RSS / Atom ingestion** with race-safe URL dedup (multiple sources surfacing the same article merge cleanly).
- ✅ **Per-source polling** at configurable intervals; first poll backfills the last 7 days but excludes that backfill from the digest.
- ✅ **LLM scoring** (Claude Haiku 4.5 by default) using your interests text — versioned, so re-grading after a profile update is trivial.
- ✅ **Daily digest** at your local time, capped at N items, with conservative AI-written 2-3 sentence summaries.
- ✅ **Telegram-first management**: add, pause, resume, remove sources without editing config files.
- ✅ **Failure-visible**: source poll errors stamp the row, scoring failures are retryable, low-signal days produce a "nothing met the threshold" message rather than silence.
- ✅ **Self-hostable for ~$10–15/month** including LLM costs.
- ✅ **Docker Compose deploy** in three commands.
- 🚧 **Topic deduplication via embeddings** — schema is pgvector-ready; pipeline change deferred.
- 🚧 **Reactions feedback loop** (👍/👎 refines scoring) — schema is hooked, pipeline not implemented yet.
- 🚧 **Cost cap & per-day token budget** — manual SQL for now.

---

## Quick start (local development)

**Prerequisites:** Docker, Python 3.12, [uv](https://github.com/astral-sh/uv), an Anthropic API key, a Telegram bot token + chat ID.

```bash
# 1. Clone and install
git clone https://github.com/Sofrosine/infonih.git
cd infonih
uv sync

# 2. Bring up Postgres
docker compose up -d postgres

# 3. Configure
cp .env.example .env
$EDITOR .env                          # paste your Anthropic + Telegram secrets

# 4. Apply migrations
uv run alembic upgrade head

# 5. Optional — seed initial sources from the example file
cp seeds/sources.example.yaml seeds/sources.yaml
cp seeds/interests.example.md seeds/interests.md
$EDITOR seeds/sources.yaml seeds/interests.md
uv run python -m infonih.scripts.seed

# 6. Run both workers (two terminals, or use tmux)
uv run python -m infonih.scripts.run_scheduler        # terminal A
uv run python -m infonih.scripts.run_telegram_bot     # terminal B
```

Send `/start` to your bot in Telegram. It should reply.

> **First time?** Set `DIGEST_WINDOW_HOURS=168` in `.env` while bootstrapping. RSS feeds typically expose only the last few days, so on a fresh install most of your scored articles will be 2–9 days old. Drop it back to `24` once fresh content fills in (~1 week of polling).

---

## Configuration

All configuration is in `.env`. Sensible defaults are baked into `src/infonih/config.py`; the only required values are the three secrets.

| Variable | Required | Default | What it does |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | — | Used for scoring and digest summaries |
| `TELEGRAM_BOT_TOKEN` | ✅ | — | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | ✅ | — | Your private chat ID; ask [@userinfobot](https://t.me/userinfobot) |
| `DATABASE_URL` | ✅ | localhost | `postgres:5432` host inside Docker Compose, `localhost:5432` for local dev |
| `SCORE_MODEL` | | `claude-haiku-4-5` | Model used for per-article scoring (cost-sensitive) |
| `SUMMARIZE_MODEL` | | `claude-haiku-4-5` | Model used to write digest summaries |
| `SCORE_INTERVAL_MINUTES` | | `5` | How often the scorer runs |
| `SCORE_BATCH_SIZE` | | `20` | Articles scored per tick |
| `SCORE_THRESHOLD` | | `50` | Minimum score (0-100) for digest inclusion |
| `DIGEST_MAX_ITEMS` | | `7` | Cap on digest length |
| `DIGEST_WINDOW_HOURS` | | `24` | Article publish-time window for the digest |
| `DIGEST_TIME_LOCAL` | | `07:00` | When the digest fires (HH:MM) |
| `DIGEST_TIMEZONE` | | `Asia/Jakarta` | IANA timezone name |
| `DEFAULT_POLL_INTERVAL_MINUTES` | | `60` | Default for new sources |

See `.env.example` for the full template.

---

## Telegram bot commands

| Command | What it does |
|---|---|
| `/start` | Welcome message |
| `/list_sources` | Show all enabled sources with category, weight, poll interval |
| `/add_source <url> <category> [weight] [poll_minutes]` | Add a new RSS source. Categories: `ai_engineering`, `ai_policy`, `politics` |
| `/pause_source <name>` | Stop polling a source without deleting its history |
| `/resume_source <name>` | Re-enable a paused source |
| `/remove_source <name>` | Delete a source row (existing articles are preserved) |
| `/set_interests <text>` | Update the interests description used for scoring |
| `/show_interests` | Display the current interests + version |

> **Tip:** configure the slash-command dropdown in @BotFather → `/setcommands` so users see autocomplete. The list to paste is in [docs/botfather-commands.txt](#) (or copy from the table above with `_` separators).

<!-- BOT COMMAND SCREENSHOT: a short Telegram conversation showing
     /add_source → bot reply → /list_sources → bot reply.
     Place at docs/img/bot-commands.png -->

---

## Deployment to a VPS

infonih runs comfortably on a tiny VPS (1 vCPU / 1 GB RAM, ~$4/month — Hetzner CX22, Vultr 1GB, DigitalOcean Basic Droplet). No domain or TLS cert needed; Telegram uses outbound long-poll.

```bash
# On a fresh Debian/Ubuntu VPS, as a non-root user with Docker installed:
git clone git@github.com:Sofrosine/infonih.git
cd infonih
$EDITOR .env                                                # paste prod secrets

# First-time database setup
docker compose up -d postgres
docker compose --profile migrate run --rm migrate
docker compose run --rm scheduler python -m infonih.scripts.seed   # optional

# Start the long-running services
docker compose up -d --build
docker compose ps                                            # 3 services: postgres, scheduler, bot
docker compose logs -f                                       # tail to verify activity
```

**Update to a new commit:**

```bash
git pull
docker compose --profile migrate run --rm migrate           # if migrations changed
docker compose up -d --build
```

**Daily Postgres backup** (cron, keep 7 days):

```bash
crontab -e
# Add:
0 4 * * * cd ~/infonih && docker compose exec -T postgres pg_dump -U infonih infonih | gzip > ~/backups/infonih-$(date +\%F).sql.gz && find ~/backups -name 'infonih-*.sql.gz' -mtime +7 -delete
```

**Firewall** (UFW; only allow SSH inbound):

```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow OpenSSH && sudo ufw enable
```

For a longer treatment of operational concerns (logs, secrets rotation, disaster recovery), see [`FLOWS.md`](FLOWS.md).

---

## Cost

Approximate monthly cost for a single user with ~5 sources, ~100 articles ingested per day:

| Item | Cost |
|---|---|
| VPS (Hetzner CX22 or equivalent) | ~$4 |
| Anthropic API (Haiku 4.5, ~$0.002/article) | ~$5–10 |
| Telegram | $0 |
| Off-site backups (Backblaze B2) | <$1 |
| **Total** | **~$10–15/month** |

LLM cost scales with article volume, not the scoring tick interval — adding more sources is what moves the needle. See `.env` for cost knobs (`SCORE_THRESHOLD`, `SCORE_BATCH_SIZE`, `SCORE_INTERVAL_MINUTES`).

---

## Project structure

```
src/infonih/
├── adapters/             # external services — Postgres, Anthropic, Telegram, RSS
│   ├── postgres/         # engine + ORM models + repository implementations
│   ├── anthropic_adapter.py
│   ├── rss_adapter.py
│   └── telegram_adapter.py
├── agents/               # the LLM half
│   ├── pipelines/        # ingest_source, score_articles, build_daily_digest
│   ├── prompts/          # .md templates + loader
│   ├── schemas/          # Pydantic models for structured Claude outputs
│   └── utils/            # URL normalisation, digest formatting
├── domain/               # pure Pydantic + Protocols, no I/O
│   ├── repositories/     # storage contracts (interfaces)
│   ├── article.py
│   ├── source.py
│   └── user_settings.py
├── scripts/              # entrypoints
│   ├── run_scheduler.py
│   ├── run_telegram_bot.py
│   ├── seed.py
│   └── ingest_once.py    # manual smoke-test helper
├── config.py             # pydantic-settings; single Settings class
└── scheduler.py          # APScheduler with DB-driven reconcile loop

alembic/versions/         # database migrations
seeds/                    # *.example.{yaml,md} committed; real ones gitignored
tests/                    # 71 tests, ~71% coverage
```

Architecture style: **hexagonal**. The domain layer (Pydantic models + repository Protocols) has no I/O. Concrete repositories live under `adapters/postgres/` and implement the Protocols. Scripts and pipelines depend on the Protocols, not the implementations — so swapping storage or LLM providers is a contained change.

For the full conventions, see [`CLAUDE.md`](CLAUDE.md).

---

## Development

```bash
uv sync                                  # install deps
uv run pytest                            # run tests (uses an isolated infonih_test database)
uv run ruff check . --fix                # lint
uv run ruff format .                     # format
uv run mypy src                          # type check
uv run alembic revision --autogenerate -m "..."   # generate a migration
```

The test suite spins up an isolated `infonih_test` database alongside `infonih` automatically on first run. Tests truncate tables between runs for isolation.

---

## Roadmap

The following are deliberately deferred per the [PRODUCT.md](PRODUCT.md) "Open product questions" section:

- **Topic deduplication** via embedding cosine similarity (~0.85 threshold). Schema and Postgres image (`pgvector`) are already in place; needs an OpenAI embeddings adapter and one Alembic migration to enable.
- **Reactions feedback loop**: 👍/👎 from the digest message refines the interest profile over time.
- **Cost ceiling**: hard cap on daily LLM spend, with the digest pausing when the budget is exhausted.
- **Source-health Telegram alerts**: notify after 3 consecutive poll failures.
- **`/poll_now`, `/status`, `/digest_now`** Telegram commands.
- **Hosted multi-user mode**: schema is `user_id`-ready (currently null in single-user mode); no infrastructure decided.

PRs that align with these are welcome but not promised any review timeline.

---

## Forking and customising

infonih is built to be forked. The bits most likely to need per-fork customisation:

- **`seeds/sources.example.yaml`** — your fork's default starter sources. The real `seeds/sources.yaml` is gitignored so each user keeps their own private list.
- **`seeds/interests.example.md`** — same idea for the interests text.
- **`src/infonih/domain/category.py`** — categories are an enum; add or rename to match your fork's focus (e.g. tech vs business vs sports).
- **`src/infonih/agents/prompts/templates/*.md`** — tune scoring strictness or summary tone here.

The hexagonal architecture means swapping out a piece (e.g. replacing the Anthropic adapter with a local model) is contained to its adapter file.

---

## Acknowledgments

- Built with [Claude Code](https://claude.ai/code) as the primary pair-programmer; the conversation log is the engineering history of the project.
- Architecture follows the [Hexagonal](https://alistair.cockburn.us/hexagonal-architecture/) / Ports-and-Adapters pattern.
- RSS parsing via [feedparser](https://feedparser.readthedocs.io/), HTTP via [httpx](https://www.python-httpx.org/), Telegram via [python-telegram-bot](https://python-telegram-bot.org/), scheduling via [APScheduler](https://apscheduler.readthedocs.io/).

## License

[MIT](LICENSE) — do whatever you want, but no warranty.

---

<div align="center">
<sub>Built for one. Shared with anyone who finds it useful.</sub>
</div>
