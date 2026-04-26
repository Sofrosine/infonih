# infonih — User Flows and System Flows

This document describes how infonih works in practice — what users do, what the system does in response, and what success and failure look like for each flow. It complements `PRODUCT.md` (what infonih is) and `CLAUDE.md` (how the code is organized).

When implementing any of these flows, this document is the source of truth for behavior. If something here is unclear or contradictory, surface the question rather than guessing.

## Flow taxonomy

infonih has three categories of flows:

1. **Setup flows** — done once or rarely; user-driven
2. **Continuous flows** — happen automatically on a schedule; system-driven
3. **Interaction flows** — happen when the user reacts to a digest; user-driven

This document covers all of them.

---

## Setup Flows

### Flow: First-time setup

**When this happens:** User has just cloned the repo or pulled a fresh deployment.

**User steps:**

1. User clones the repo
2. User copies `.env.example` to `.env` and fills in: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATABASE_URL`
3. User edits `config.yaml` to specify their sources, interests, and digest schedule
4. User runs `docker compose up -d` to start Postgres
5. User runs database migrations
6. User runs the application
7. User waits for the next scheduled digest, or triggers a manual digest to verify setup

**System behavior:**

- On startup, application validates `.env` and `config.yaml` against Pydantic schemas
- If config is invalid, application exits with a clear error message identifying the specific problem (missing field, wrong type, invalid URL, etc.)
- If config is valid, application initializes the scheduler and registers each source for polling
- Application logs each registered source with its polling interval and category
- Application sends a startup message to the configured Telegram chat: "infonih started. Watching N sources. Next digest at HH:MM."

**Success looks like:**

- User receives the startup message in Telegram
- Logs show all sources successfully registered
- First poll cycle begins on schedule

**Failure modes and handling:**

- **Missing required env var:** application exits with a message naming the missing variable and pointing to `.env.example`
- **Invalid config.yaml syntax:** application exits with the YAML parser error and the line number
- **Telegram bot token invalid:** application starts but startup message fails; user sees the error in logs and can fix the token
- **Database unreachable:** application retries 3 times with backoff, then exits with a clear connection error
- **At least one source URL is invalid:** application starts anyway, logs a warning for the bad source, marks it disabled in memory; other sources continue to work

### Flow: Adding a new source

**When this happens:** User wants to add Simon Willison's blog two weeks after starting with BBC sources.

**User steps:**

1. User edits `config.yaml`
2. User adds a new entry to the `sources` list with name, type, URL, category, weight, and poll interval
3. User saves the file
4. User restarts the application (`docker compose restart` or equivalent)

**System behavior:**

- On restart, the application re-validates the config
- New sources are registered with the scheduler alongside existing ones
- On the new source's first poll, articles published in the last 7 days are fetched and ingested as "backfill" — stored in the database but not eligible for the next digest
- Articles published after the source was added are eligible for the digest normally
- Application logs the new source registration

**Success looks like:**

- The next polling cycle for the new source successfully fetches articles
- Subsequent digests include articles from the new source where their score and category cap allow
- No flood of historical articles dominates the next digest

**Failure modes and handling:**

- **New source URL is unreachable:** logged as warning, source marked disabled, other sources unaffected
- **New source returns malformed feed:** specific parse error logged, source disabled, user sees it on next startup
- **New source duplicates URLs from existing sources:** dedup at insert time prevents double-storage; the new source's name is appended to the existing article's `sources` array

### Flow: Removing or pausing a source

**When this happens:** User decides BBC Business is too noisy and wants to stop ingesting from it.

**User steps:**

1. User edits `config.yaml`
2. User either deletes the source entry or sets `enabled: false`
3. User restarts the application

**System behavior:**

- On restart, the source is no longer registered with the scheduler
- Existing articles from that source remain in the database (history is preserved)
- Articles from that source can still appear in the database for retrospective queries; they simply stop being added to digests because no new ones arrive

**Success looks like:**

- No new articles from the disabled source appear in subsequent digests
- Existing data is preserved
- User can re-enable the source later by setting `enabled: true` and restarting

**Failure modes and handling:**

- None significant. This flow is intentionally simple.

### Flow: Updating interest description

**When this happens:** User's interests shift (e.g., they're now job-hunting and want more career-related content).

**User steps:**

1. User edits the `interests` field in `config.yaml`
2. User restarts the application

**System behavior:**

- Future article scoring uses the new interests description
- Articles already scored under the old description are not re-scored
- The next digest uses the new interests for any articles being scored fresh

**Success looks like:**

- New digests reflect the updated interests
- Historical scores are unchanged (auditable)

**Failure modes and handling:**

- **Interests description is empty:** application exits with a clear "interests is required" error on restart
- **Interests description is extremely long (>2000 chars):** application warns but proceeds; user is alerted that long descriptions may degrade Claude's scoring quality

---

## Continuous Flows

These run automatically on schedules. The user does not trigger them directly.

### Flow: Source polling

**When this happens:** Every N minutes per source, where N is configured per source (default 60).

**System behavior:**

For each scheduled source poll:

1. Fetcher (selected by source `type`) connects to the source URL or API
2. Response is parsed into a normalized list of `Article` candidates with: URL, title, raw content/summary, source name, published_at timestamp
3. For each candidate article:
   - Check if URL already exists in articles table
   - If new: insert into database with status `unscored`
   - If existing: append source name to the article's `sources` array if not already there; do not duplicate
4. Mark the source as successfully polled with current timestamp
5. Log: number of new articles found, number of duplicates skipped

**Success looks like:**

- Each source's last_polled_at timestamp updates regularly
- New articles flow into the database
- No duplicate URLs ever stored

**Failure modes and handling:**

- **Network timeout:** retry once after 30 seconds; if still failing, log warning, mark source as "failed last poll," continue to next scheduled poll. Do not crash the application.
- **HTTP 4xx/5xx errors:** logged with status code; behave as timeout case
- **Malformed feed content:** specific parse error logged; source marked as "failed last poll" but not disabled
- **Source URL changed (redirect to new URL):** follow redirect once; if URL has fundamentally changed, log a warning recommending user update config
- **Three consecutive failed polls for one source:** application sends a Telegram alert to the user: "Source X has failed 3 polls in a row. Last error: ___. Consider checking the URL or disabling the source."

### Flow: Article scoring

**When this happens:** After articles are ingested, before the next digest is built. May run on a schedule (e.g., every 30 minutes) or be triggered by the digest builder.

**System behavior:**

For each article with status `unscored`:

1. Build the scoring prompt: user's interest description, source name and category, article title, article summary or first N chars of content, user's recent reactions (last 50 👍/👎 with article titles)
2. Call Claude (default model: Haiku for cost; Sonnet if marked high-priority by source weight) with structured output schema: `{score: int 0-100, reasoning: str, suggested_category_match: str}`
3. Apply source weight multiplier to the raw score
4. Apply category-based adjustments (politics gets stricter scoring threshold; AI gets a small boost in source weight as defined in config)
5. Update article record with: `score`, `reasoning`, `scored_at`, status `scored`
6. Log token usage and cost

**Success looks like:**

- All `unscored` articles transition to `scored` within one polling cycle
- Token costs stay within reasonable range (roughly $0.01-0.05 per scored article)
- Reasoning text is stored and inspectable

**Failure modes and handling:**

- **Claude API error:** retry once with backoff; if still failing, mark article as `score_failed` with error reason. Article remains eligible for re-scoring on next cycle. Do not block other articles.
- **Structured output validation fails:** log raw response, mark article `score_failed`, retry once. If repeated, alert user.
- **Token budget exceeded for the day:** scoring pauses; remaining articles stay `unscored`; user is alerted via Telegram with current spend and option to extend budget by editing config.
- **Article content is very short or missing:** Claude is given what's available; score is computed but flagged with a `low_content_confidence: true` field.

### Flow: Daily digest delivery

**When this happens:** At the configured digest time (default 7 AM user-local time), every day.

**System behavior:**

1. Query articles where: `scored_at` is set, `score >= min_score_threshold`, `sent_in_digest_at` is null, `published_at` within configured window (default last 24 hours)
2. Group articles by category
3. For each category, sort by adjusted score descending and take top N where N is the category's `max_items_per_digest`
4. Combine across categories, deduplicate by topic similarity (using article embeddings, cosine similarity threshold ~0.85), preserving the highest-scored from each cluster
5. Sort final list by score descending, cap at global `digest_max_items`
6. For each selected article, generate a digest summary: 2-3 sentences via Claude (Haiku), conservative for political content, with explicit source attribution
7. Format the digest message: header with date, sections by category, each item with title, source, summary, link, and item number for reactions
8. Send via Telegram to configured chat
9. Mark all included articles with `sent_in_digest_at = now()`
10. Log: digest sent, item count, total tokens used

**Digest message format (illustrative):**

```
📨 infonih — Sunday, April 27, 2026

🤖 AI (3)

1. Anthropic ships persistent agent memory
   anthropic.com · 2 min read
   Anthropic released a new feature for Claude that allows agents to maintain memory across sessions. Documentation includes an opinionated default architecture for memory storage.

2. [next AI item]
...

🏛️ AI Policy (1)

4. EU AI Act enforcement begins for foundation models
   lawfaremedia.org · 8 min read
   The EU AI Act's foundation model provisions took effect this week. Lawfare summarizes obligations for major model providers including transparency reports and red-team disclosures.

🌍 Global Politics (2)

5. [next item]
...

Reply with 👍 or 👎 followed by the item number to react.
Reply with 🔍 followed by an item number to ask follow-up questions.
```

**Success looks like:**

- User receives a digest at the scheduled time
- Digest contains 5-7 well-distributed items across categories
- All summaries are 2-3 sentences and accurately reflect their source
- Reactions are easy to send (numbered items, simple syntax)

**Failure modes and handling:**

- **No articles meet threshold:** send a "low-signal day" message: "No articles met your interest threshold today. N candidates were scored, top score was X. Consider reviewing your sources or interest description if this happens often."
- **Telegram delivery fails:** retry 3 times with backoff; if still failing, log full digest content to a file and alert user via any other configured notification channel (or just log).
- **Summary generation fails for one article:** that article is included with title and link only, marked with "(summary unavailable)" — other articles still go in the digest.
- **Total token cost for digest exceeds budget:** digest is still built and sent (delivery is more important than budget), but a warning is included at the end of the message: "Today's digest used $X, above your configured budget of $Y."

### Flow: Source health monitoring

**When this happens:** Continuously, as a side effect of polling.

**System behavior:**

- Each source tracks: `last_polled_at`, `last_successful_poll_at`, `consecutive_failures`, `total_articles_ingested_30d`, `total_articles_in_digest_30d`
- When `consecutive_failures` reaches 3: alert user
- When a source has ingested >50 articles in 30 days but had 0 in any digest: surface as "low-signal source" in next weekly summary

**Success looks like:**

- User receives early warning when sources break
- Low-value sources are identifiable by data, not by guessing

**Failure modes and handling:**

- This is itself a monitoring flow; it shouldn't fail loudly. If health metrics don't update for some reason, the next polling cycle restores them.

---

## Interaction Flows

These happen when the user reacts to a digest message.

### Flow: Reacting to an article (👍 or 👎)

**When this happens:** After receiving a digest, user replies with `👍 3` or `👎 5` (number is the item index in the digest).

**System behavior:**

1. Telegram message handler receives the reply
2. Parse the message: identify reaction type (positive/negative) and target item number
3. Resolve item number to article ID using the most recent digest for that user
4. Store reaction: `{article_id, reaction_type, reacted_at}`
5. Optionally: send a brief confirmation reaction back ("Got it" or just an emoji)
6. Reactions are used in future scoring as described in Flow: Article scoring

**Success looks like:**

- Reactions are stored persistently
- Future digests reflect reaction history through scoring

**Failure modes and handling:**

- **Item number doesn't match recent digest:** reply with "I couldn't find item N in the most recent digest. Reactions only apply to the latest digest items."
- **Multiple reactions to same item:** latest reaction overwrites previous (user changed their mind)
- **Reaction message is malformed:** ignore silently; do not error-spam the user

### Flow: Asking a follow-up question on a digest item

**When this happens:** User replies with `🔍 3` followed by a question, e.g., "🔍 3 what does this mean for self-hosted models?"

**System behavior:**

1. Parse the message: identify item number and question text
2. Resolve item number to article ID
3. Fetch full article content (if not already stored, fetch from URL with respectful rate limiting)
4. Build context: article title, full content, user's question, user's interest profile
5. Call Claude (Sonnet for quality) with the context and a "answer the user's question grounded in the article" prompt
6. Send response as a Telegram message, threaded as reply to original digest

**Success looks like:**

- User gets a useful, article-grounded answer to their question
- Response cites the article and only the article, not external knowledge
- Response respects the same conservative tone as summaries (no editorializing on political content)

**Failure modes and handling:**

- **Article full content cannot be fetched:** Claude is given only the summary; response includes "Based on the summary I have access to..."
- **Question is ambiguous:** Claude asks one clarifying question instead of guessing
- **Question is unrelated to the article:** Claude responds: "That question doesn't seem related to the article. I can only answer questions grounded in the digest items."

### Flow: Manual digest trigger

**When this happens:** User sends `/digest_now` to the bot, e.g., to test setup or get a digest at an unusual time.

**System behavior:**

- Same as Flow: Daily digest delivery, but on-demand
- Articles included are still subject to the same `sent_in_digest_at IS NULL` filter, so this doesn't repeat content
- If no fresh articles are available, returns the "low-signal day" message

**Success looks like:**

- User receives a digest on demand
- Already-sent articles are not re-included

### Flow: Pause and resume

**When this happens:** User sends `/pause` (e.g., going on vacation) or `/resume`.

**System behavior:**

- `/pause`: digest scheduling is suspended; polling continues so articles are still ingested and scored, but no digests are sent
- `/resume`: digest scheduling resumes; the next scheduled digest sends a "Welcome back" message + the digest

**Success looks like:**

- No unwanted digests during pause
- On resume, user gets a properly formatted digest, not a flood of accumulated content

### Flow: Status check

**When this happens:** User sends `/status` to verify the system is working.

**System behavior:**

- Response includes: number of active sources, articles ingested in last 24 hours, articles scored, articles waiting to be sent, total tokens used today, next scheduled digest time, any source failures

**Success looks like:**

- User has visibility into system state without checking logs

---

## Cross-cutting concerns

### Logging

Every flow logs structured events to JSONL files in a `logs/` directory. Each event includes timestamp, flow name, action, status, and relevant context (article IDs, source names, token counts, etc.). Logs are not part of the user-facing product but are essential for debugging and for future analysis (e.g., the eventual blog post about infonih).

### Cost tracking

Every Claude and OpenAI call is logged with model, input tokens, output tokens, and computed cost. Daily and per-flow cost rollups are accessible via `/status`. Budget overruns trigger alerts but never silently degrade service.

### Database persistence

All state — articles, scores, reactions, digests sent, source health — lives in Postgres. The system can be restarted at any time without losing context. Configuration in `config.yaml` is read at startup; runtime state is in the database.

### Secrets and config

API keys live in `.env`, sources and interests in `config.yaml`. These are separate concerns: `.env` contains credentials (private, not in version control), `config.yaml` contains preferences (semi-private, may be shared in obfuscated form for blog posts or open-source examples).