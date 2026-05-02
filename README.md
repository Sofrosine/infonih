# 📰 infonih

**A personal AI news digest, delivered as a Telegram message every morning.**

*"info nih" — Indonesian for "got info for you."*

[Python 3.12+](https://www.python.org/downloads/)
[Built with uv](https://github.com/astral-sh/uv)
[License: MIT](LICENSE)
[Personal use first](#who-this-is-for)

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

### Daily digest

The actual product — one Telegram message per day, ranked by Claude.

<p align="center">
  <img src="docs/img/daily_digest.png" alt="Daily digest in Telegram" width="420" />
</p>

### Source management via Telegram

Add, pause, resume, or remove sources without editing config files.

<p align="center">
  <img src="docs/img/source_management.png" alt="Source management bot commands" width="420" />
</p>

### `/list_sources` output

Quick check of what's currently being polled.

<p align="center">
  <img src="docs/img/list_sources.png" alt="/list_sources output" width="420" />
</p>

---

## How it works

```
                 ┌──────────────────────┐
                 │   Postgres (pgvector)│
                 │  sources / articles  │
                 │   user_settings      │
                 │   cost_events        │
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
 │  cron    │      │ /cost      │
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
3. **Postgres** is the single source of truth — sources, articles, scores, user settings, and per-call LLM cost events all live here.

A typical article's lifecycle:

```
RSS feed ──poll──► insert (status=unscored, is_backfill=true|false)
                       │
                       │ every 5 min
                       ▼
                ┌─────────────────┐
                │ Claude scores   │
                │ → status=scored │
                │ → cost_events++ │
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
- ✅ **Daily digest** at your local time, capped at N items, with conservative AI-written 2–3 sentence summaries.
- ✅ **Telegram-first management**: add, pause, resume, remove sources without editing config files.
- ✅ **Per-call cost tracking** — every Anthropic call logs tokens + USD into `cost_events`. View today / week / month with `/cost`.
- ✅ **Failure-visible**: source poll errors stamp the row, scoring failures are retryable, low-signal days produce a "nothing met the threshold" message rather than silence.
- ✅ **Docker Compose deploy** in three commands.
- 🚧 **Topic deduplication via embeddings** — schema is pgvector-ready; pipeline change deferred.
- 🚧 **Reactions feedback loop** (👍/👎 refines scoring) — schema hook coming; pipeline not implemented.
- 🚧 **Hard cost cap** — `/cost` shows spend; an automatic cutoff is not wired yet.

---

## Getting started

This walks you from a clean machine to a working morning digest. **About 30 minutes.**

### Step 1 — Get the prerequisites you'll need credentials for

You can do these in any order; doing them first means you're not blocked later.

**Anthropic API key.** Sign up at [console.anthropic.com](https://console.anthropic.com), create an API key, save it. You'll paste it as `ANTHROPIC_API_KEY`.

**Telegram bot token.** In the Telegram app:

1. Search for [@BotFather](https://t.me/BotFather), open chat, send `/start`.
2. Send `/newbot`. Give it a display name (e.g. *infonih digest*) and a username ending in `bot` (e.g. `your_infonih_bot`).
3. BotFather replies with a token like `7891234567:AAH...xyz`. That's your `TELEGRAM_BOT_TOKEN`.
4. **(Optional but recommended)** While still in BotFather, send `/setcommands`, pick your bot, then paste:

   ```
   list_sources - List enabled sources
   add_source - Add a source: <url> <category>
   pause_source - Pause a source by name
   resume_source - Resume a paused source
   remove_source - Remove a source
   set_interests - Update your interests description
   show_interests - Show current interests
   cost - Today / week / month LLM spend
   ```

   This makes the slash-command dropdown appear when you type `/` in your bot chat.

**Telegram chat ID.** Easy way: message [@userinfobot](https://t.me/userinfobot) — it replies with your numeric chat ID. Save that as `TELEGRAM_CHAT_ID`.

> **Important:** open a chat with your new bot and send it any message (e.g. `hi`) before you start the bot worker. Telegram bots can only DM users who have initiated a conversation with them.

### Step 2 — Install the local toolchain

You need **Docker** + **Python 3.12** + **[uv](https://github.com/astral-sh/uv)**.

```bash
# macOS via Homebrew (one example — pick what fits your OS)
brew install --cask docker
brew install python@3.12
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Step 3 — Clone, install deps, configure

```bash
git clone https://github.com/Sofrosine/infonih.git
cd infonih
uv sync                              # creates .venv and installs deps
cp .env.example .env
$EDITOR .env                         # paste your three secrets, leave the rest as defaults
```

The minimum required values in `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=7891234567:AAH...
TELEGRAM_CHAT_ID=123456789
DATABASE_URL=postgresql+asyncpg://infonih:infonih@localhost:5432/infonih
```

> **Bootstrap tip.** Add `DIGEST_WINDOW_HOURS=168` (7 days) to your `.env` for the first 1–2 weeks. RSS feeds typically expose only the last few days; on a fresh install most of your scored articles will be 2–9 days old, and the default 24-hour window will be empty. Drop it back to `24` once fresh content fills in.

### Step 4 — Bring up Postgres and apply migrations

```bash
docker compose up -d postgres                      # starts Postgres on localhost:5432
uv run alembic upgrade head                        # creates the schema
```

Verify with:

```bash
docker exec infonih-postgres psql -U infonih -d infonih -c "\dt"
```

You should see five tables: `alembic_version`, `articles`, `cost_events`, `sources`, `user_settings`.

### Step 5 — Seed your starter sources and interests

```bash
cp seeds/sources.example.yaml seeds/sources.yaml
cp seeds/interests.example.md seeds/interests.md
$EDITOR seeds/sources.yaml seeds/interests.md      # edit to match what you actually care about
uv run python -m infonih.scripts.seed
```

The real `seeds/sources.yaml` and `seeds/interests.md` are gitignored — yours, never committed.

### Step 6 — Start the two workers

You need **two terminals** (or `tmux` / `screen`):

```bash
# Terminal A — runs ingestion + scoring + daily digest cron
uv run python -m infonih.scripts.run_scheduler

# Terminal B — runs the Telegram bot's long-poll loop
uv run python -m infonih.scripts.run_telegram_bot
```

Open Telegram, send `/start` to your bot. It should reply.

### Step 7 — Verify everything works

The first scheduler tick runs immediately. Within ~5 minutes:

```sql
-- In another terminal
docker exec infonih-postgres psql -U infonih -d infonih -c "
  SELECT status, count(*) FROM articles GROUP BY status;
"
```

You should see `unscored` counts dropping and `scored` counts growing.

In Telegram, try:

- `/list_sources` — should show what you seeded
- `/show_interests` — should echo your interests text
- `/cost` — should show today's LLM spend (small numbers — most calls are sub-cent)

### Step 8 — See your first digest

The digest fires at `DIGEST_TIME_LOCAL` in `DIGEST_TIMEZONE` (default `07:00 Asia/Jakarta`). To trigger one immediately for testing:

```bash
uv run python -c "
import asyncio
from infonih.adapters.anthropic_adapter import anthropic_adapter
from infonih.adapters.postgres import article_repository
from infonih.adapters.telegram_adapter import telegram
from infonih.agents.pipelines.build_daily_digest import BuildDailyDigestPipeline
asyncio.run(BuildDailyDigestPipeline(
    anthropic=anthropic_adapter,
    article_repo=article_repository,
    telegram=telegram,
).run())
"
```

If the message says *"Low-signal day"*, no scored article met the threshold within the digest window — see [Troubleshooting](#troubleshooting) below.

You're done. From now on, manage sources from inside Telegram.

---

## Configuration

All configuration is in `.env`. Sensible defaults are baked into `src/infonih/config.py`; only the three secrets are required.

| Variable                        | Required | Default            | What it does                                                               |
| ------------------------------- | -------- | ------------------ | -------------------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`             | ✅        | —                  | Used for scoring and digest summaries                                      |
| `TELEGRAM_BOT_TOKEN`            | ✅        | —                  | From [@BotFather](https://t.me/BotFather)                                  |
| `TELEGRAM_CHAT_ID`              | ✅        | —                  | Your private chat ID; ask [@userinfobot](https://t.me/userinfobot)         |
| `DATABASE_URL`                  | ✅        | localhost          | `postgres:5432` host inside Docker Compose, `localhost:5432` for local dev |
| `SCORE_MODEL`                   |          | `claude-haiku-4-5` | Model used for per-article scoring                                         |
| `SUMMARIZE_MODEL`               |          | `claude-haiku-4-5` | Model used to write digest summaries                                       |
| `SCORE_INTERVAL_MINUTES`        |          | `5`                | How often the scorer runs                                                  |
| `SCORE_BATCH_SIZE`              |          | `20`               | Articles scored per tick                                                   |
| `SCORE_THRESHOLD`               |          | `50`               | Minimum score (0–100) for digest inclusion                                 |
| `DIGEST_MAX_ITEMS`              |          | `7`                | Cap on digest length                                                       |
| `DIGEST_WINDOW_HOURS`           |          | `24`               | Article publish-time window for the digest (use `168` while bootstrapping) |
| `DIGEST_TIME_LOCAL`             |          | `07:00`            | When the digest fires (HH:MM)                                              |
| `DIGEST_TIMEZONE`               |          | `Asia/Jakarta`     | IANA timezone name                                                         |
| `DEFAULT_POLL_INTERVAL_MINUTES` |          | `60`               | Default for new sources                                                    |

See `.env.example` for the full template.

> **Restart workers after editing `.env`.** Both processes load env vars at startup. Changes take effect on the next start.

---

## Telegram bot commands

| Command                                                | What it does                                                                |
| ------------------------------------------------------ | --------------------------------------------------------------------------- |
| `/start`                                               | Welcome message                                                             |
| `/list_sources`                                        | Show all enabled sources with category, weight, poll interval               |
| `/add_source <url> <category> [weight] [poll_minutes]` | Add a new RSS source. Categories: `ai_engineering`, `ai_policy`, `politics` |
| `/pause_source <name>`                                 | Stop polling a source without deleting its history                          |
| `/resume_source <name>`                                | Re-enable a paused source                                                   |
| `/remove_source <name>`                                | Delete a source row (existing articles are preserved)                       |
| `/set_interests <text>`                                | Update the interests description used for scoring                           |
| `/show_interests`                                      | Display the current interests + version                                     |
| `/cost`                                                | Today / this week / this month LLM spend, plus today's per-flow breakdown   |

> Configure the slash-command dropdown via @BotFather → `/setcommands` (see Step 1 above) so users get autocomplete.

---

## Daily operations

### Trigger the digest manually (any time)

```bash
uv run python -c "
import asyncio
from infonih.adapters.anthropic_adapter import anthropic_adapter
from infonih.adapters.postgres import article_repository
from infonih.adapters.telegram_adapter import telegram
from infonih.agents.pipelines.build_daily_digest import BuildDailyDigestPipeline
asyncio.run(BuildDailyDigestPipeline(
    anthropic=anthropic_adapter,
    article_repo=article_repository,
    telegram=telegram,
).run())
"
```

### Re-score after changing interests

If you update interests via `/set_interests`, articles already in the DB keep their old scores until they age out of the digest window. To force a re-grade against the new interests:

```sql
docker exec infonih-postgres psql -U infonih -d infonih -c "
UPDATE articles
SET status = 'unscored',
    score = NULL,
    score_reasoning = NULL,
    scored_at = NULL,
    scored_with_interest_version = NULL
WHERE status = 'scored'
  AND scored_with_interest_version < (
    SELECT interests_version FROM user_settings LIMIT 1
  );
"
```

The next scoring tick (within `SCORE_INTERVAL_MINUTES`) re-grades them.

### Re-try articles that previously failed scoring

```sql
UPDATE articles
SET status = 'unscored', score_failure_reason = NULL
WHERE status = 'score_failed';
```

### Clean up old articles (manual housekeeping)

Articles accumulate forever by default. ~1 GB / year of growth at typical volume — cleanup is optional. Manual trim that preserves anything ever sent in a digest:

```sql
DELETE FROM articles
WHERE created_at < now() - interval '90 days'
  AND sent_in_digest_at IS NULL;
```

### View costs

`/cost` in Telegram is the easiest. Or directly:

```sql
SELECT flow,
       count(*)             AS calls,
       sum(input_tokens)    AS input_tokens,
       sum(output_tokens)   AS output_tokens,
       sum(cost_usd)        AS usd
FROM cost_events
WHERE created_at >= now() - interval '30 days'
GROUP BY flow
ORDER BY usd DESC;
```

---

## Deployment to a VPS

infonih runs comfortably on a tiny VPS (1 vCPU / 1 GB RAM, ~$4/month — Hetzner CX22, Vultr 1GB, DigitalOcean Basic Droplet). No domain or TLS cert needed; Telegram uses outbound long-poll.

### Initial setup

```bash
# As root, first time only
adduser infonih
usermod -aG sudo infonih
# Copy your local SSH public key to /home/infonih/.ssh/authorized_keys

# As `infonih` user
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker infonih
exit  # re-login so the docker group takes effect
```

### Deploy

```bash
ssh-keygen -t ed25519                                 # add the .pub to GitHub if private
git clone git@github.com:Sofrosine/infonih.git
cd infonih
$EDITOR .env                                          # paste prod secrets

# First-time database setup
docker compose up -d postgres
docker compose --profile migrate run --rm migrate
docker compose run --rm scheduler python -m infonih.scripts.seed   # optional

# Start the long-running services
docker compose up -d --build
docker compose ps                                     # 3 services: postgres, scheduler, bot
docker compose logs -f                                # tail to verify activity
```

> On the VPS, change `DATABASE_URL` to use the container name as host:
> `postgresql+asyncpg://infonih:infonih@postgres:5432/infonih`

### Update to a new commit

```bash
git pull
docker compose --profile migrate run --rm migrate    # if migrations changed
docker compose up -d --build
```

### Daily backup (cron, keeps 7 days)

```bash
crontab -e
```

```cron
0 4 * * * cd ~/infonih && docker compose exec -T postgres pg_dump -U infonih infonih | gzip > ~/backups/infonih-$(date +\%F).sql.gz && find ~/backups -name 'infonih-*.sql.gz' -mtime +7 -delete
```

### Firewall (UFW; only allow SSH inbound)

```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow OpenSSH && sudo ufw enable
```

For a longer treatment of operational concerns (logs, secrets rotation, disaster recovery), see [FLOWS.md](FLOWS.md).

---

## Troubleshooting

<details>
<summary><b>Digest message says "Low-signal day — nothing met the threshold."</b></summary>

The digest filter is `score >= SCORE_THRESHOLD AND published_at >= now() - DIGEST_WINDOW_HOURS AND NOT is_backfill AND sent_in_digest_at IS NULL`. Diagnose:

```sql
SELECT
    count(*) FILTER (WHERE score >= 50)                              AS above_threshold,
    count(*) FILTER (WHERE published_at >= now() - interval '24 h')  AS in_24h_window,
    count(*) FILTER (WHERE is_backfill = false)                      AS not_backfill,
    count(*) FILTER (WHERE sent_in_digest_at IS NULL)                AS not_sent
FROM articles WHERE status = 'scored';
```

If `above_threshold` is high but `in_24h_window` is low, your articles are too old for the window. Bump `DIGEST_WINDOW_HOURS=168` while bootstrapping.

If `above_threshold` is 0, your scoring is too strict for your sources — lower `SCORE_THRESHOLD`, or pick more relevant sources, or refine `/set_interests`.
</details>

<details>
<summary><b>Articles stuck in <code>unscored</code> status</b></summary>

Check, in order:

1. Is the scheduler worker running? Look for `scored batch: scored=N` in its logs.
2. Are interests set? `SELECT count(*) FROM user_settings;` — if 0, send `/set_interests <text>` first.
3. Are scores failing? `SELECT score_failure_reason, count(*) FROM articles WHERE status='score_failed' GROUP BY 1;` — most often missing/invalid `ANTHROPIC_API_KEY`.
</details>

<details>
<summary><b>Bot doesn't reply to commands</b></summary>

1. Is the bot worker running? Look for `telegram bot starting (long-poll)` in its logs.
2. Did you send the bot any message before? Bots can only DM chats they've received messages from.
3. Did you restart the worker after editing `.env`?
4. Check `TELEGRAM_BOT_TOKEN` is correct (no whitespace, full string from BotFather).
</details>

<details>
<summary><b>Telegram says "Low-signal day" but I see real digest content in <code>articles</code></b></summary>

Almost always the publish-time window. Articles in your DB might have `published_at` from days ago even if you ingested them today — feeds expose `published_at` as the source's timestamp, not yours. Use the diagnostic query above.
</details>

<details>
<summary><b>Pydantic validation error from Anthropic ("string too long")</b></summary>

Fixed in `f5d4a3a`-onwards — bumped `reasoning` max length and tightened the prompt. If you see a fresh occurrence, it's worth checking whether the model produced an unexpectedly long response; the article gets marked `score_failed` and will retry on the next tick.
</details>

<details>
<summary><b>Worker won't start: "another operation is in progress"</b></summary>

This is asyncpg's signal that a connection is being shared across event loops. Usually means you have a stale Python process. Kill any leftover `run_scheduler` / `run_telegram_bot` processes and restart.
</details>

<details>
<summary><b>Docker Compose says port 5432 is already allocated</b></summary>

Another Postgres is running on your host (system Postgres, another project's container, etc.). Either stop the conflicting one, or change the host port in `docker-compose.yml`:

```yaml
ports:
  - "127.0.0.1:5433:5432"
```

…and update `DATABASE_URL` to use port `5433`.
</details>

---

## Project structure

```
src/infonih/
├── adapters/             # external services — Postgres, Anthropic, Telegram, RSS
│   ├── postgres/         # engine + ORM models + repositories (source, article,
│   │                     #   user_settings, cost)
│   ├── anthropic_adapter.py
│   ├── rss_adapter.py
│   └── telegram_adapter.py
├── agents/               # the LLM half
│   ├── pipelines/        # ingest_source, score_articles, build_daily_digest
│   ├── prompts/          # .md templates + loader
│   ├── schemas/          # Pydantic models for structured Claude outputs
│   └── utils/            # URL normalisation, digest formatting, LLM pricing
├── domain/               # pure Pydantic + Protocols, no I/O
│   ├── repositories/     # storage contracts (interfaces)
│   ├── article.py
│   ├── cost_event.py
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
tests/                    # 81 tests, ~82% coverage
```

Architecture style: **hexagonal**. The domain layer (Pydantic models + repository Protocols) has no I/O. Concrete repositories live under `adapters/postgres/` and implement the Protocols. Scripts and pipelines depend on the Protocols, not the implementations — so swapping storage or LLM providers is a contained change.

For the full conventions, see [CLAUDE.md](CLAUDE.md).

---

## Development

```bash
uv sync                                            # install deps
uv run pytest                                      # run tests (uses an isolated infonih_test database)
uv run ruff check . --fix                          # lint
uv run ruff format .                               # format
uv run mypy src                                    # type check
uv run alembic revision --autogenerate -m "..."    # generate a migration
```

The test suite spins up an isolated `infonih_test` database alongside `infonih` automatically on first run. Tests truncate tables between runs for isolation.

---

## Cost

Approximate monthly cost for a single user with ~5 sources, ~100 articles ingested per day:

| Item                                            | Cost           |
| ----------------------------------------------- | -------------- |
| VPS (Hetzner CX22 or equivalent)                | ~$4            |
| Anthropic API (Haiku 4.5, ~$0.002/article)      | ~$5–10         |
| Telegram                                        | $0             |
| Off-site backups (Backblaze B2)                 | <$1            |
| **Total**                                       | **~$10–15/mo** |

LLM cost scales with article volume, not the scoring tick interval. The `/cost` Telegram command and the `cost_events` table give you per-flow visibility.

---

## Roadmap

The following are deliberately deferred per the [PRODUCT.md](PRODUCT.md) "Open product questions" section:

- **Topic deduplication** via embedding cosine similarity (~0.85 threshold). Schema and Postgres image (`pgvector`) are already in place; needs an OpenAI embeddings adapter and one Alembic migration to enable.
- **Reactions feedback loop**: 👍 / 👎 from the digest message refines the interest profile over time.
- **Hard cost ceiling**: `/cost` exposes spend; an automatic cutoff when a daily/monthly budget is reached is not wired yet.
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

Built for one. Shared with anyone who finds it useful.
