# infonih — Product Document

## What infonih is

infonih is a personal AI-powered news digest delivered through Telegram. It reads from a curated set of sources, scores articles against the user's interests using Claude, and sends a focused daily digest of the few items that actually matter — instead of letting the user spend hours scrolling.

The name is a play on the casual Indonesian phrase "info nih" — "got info for you." The product is built to feel as conversational and low-pressure as that phrase suggests.

## Who it's for

**Primary user: the author (Soultan).** This is a personal-use tool first. It's optimized for one person — someone who is professionally interested in AI engineering, follows AI policy and broader political news (with Indonesian and global coverage), and wants signal extracted from the noise without committing to yet another product subscription.

**Secondary users (open-source forks):** Other developers and knowledge workers who would self-host their own version with their own sources, interests, and Telegram bot. infonih is published open source so others can fork it, configure it for themselves, and run it on their own infrastructure.

**Explicitly not for:** General consumer audiences. Non-technical users. Users who want a polished SaaS experience. People who want a one-click setup with no configuration. Those audiences are well-served by funded competitors (notably Noscroll); infonih makes no attempt to compete there.

## The problem

Knowledge workers — especially those professionally engaged with AI and policy — face a structural information problem in 2026:

1. **The volume of relevant content has exploded.** AI labs publish daily, AI policy is a fast-moving domain, political news is 24/7, and Indonesian tech/policy coverage adds another stream. No human can read it all.

2. **Existing aggregators are noisy.** Hacker News, Reddit, and Twitter/X surface things, but they also surface enormous amounts of junk, ragebait, and content tangential to one's actual interests.

3. **Existing AI digest tools are general-purpose or paid.** Tools like Noscroll target broad audiences with subscription pricing. Specialized digest tools for AI + policy + Indonesian context don't exist.

4. **DIY RSS readers don't filter.** Tools like Feedly require the user to read everything; they don't help prioritize.

The result: most thoughtful professionals end up either over-consuming (hours of scrolling) or under-consuming (missing things they'd genuinely have wanted to know about).

## The solution

infonih fetches articles from a user-configured set of sources (RSS feeds, with an architecture that supports adding API-based sources like Hacker News later). Each article is scored by Claude against a description of the user's interests and the user's reaction history. Once a day, the highest-scoring articles — capped per category to maintain diversity — are delivered as a Telegram message with short summaries and source links.

The key insight: the user configures *what they care about* once, in plain language and source weights, and then receives a focused daily digest indefinitely without further work. Reactions (👍/👎) refine the system over time but aren't required for it to be useful from day one.

## Product principles

These principles guide product decisions when tradeoffs arise. They're more important than any specific feature.

### 1. Personal-use first

infonih is designed for one user (the author) with optional multi-user support as a secondary path. When in doubt, prefer simplicity that serves a single power user over flexibility that serves many casual ones. Multi-tenancy, if added, must not compromise the core single-user experience.

### 2. Open-source from day one

The code is published openly under MIT license. The README explicitly disclaims any maintenance, support, or feature obligations. Users are expected to fork and configure for themselves. infonih is a tool shared, not a service offered.

### 3. Sources are configured, not algorithmic

The user explicitly chooses their sources. infonih does not auto-discover sources, recommend new sources, or scrape uncited content. This keeps the system legible, legally simple, and aligned with the user's deliberate intent.

### 4. AI scores; humans curate

Claude evaluates articles for relevance, but the source list, interest description, and category structure are entirely human-defined. AI is a filter, not a curator. infonih should never feel like it's "deciding" what the user should care about.

### 5. Summaries are conservative, especially for politics

Article summaries are 2-3 sentences maximum. For political articles, summaries quote the source's framing rather than synthesizing across viewpoints, and never editorialize. The user reads the original article for substance; the summary is just enough to decide whether to click through.

### 6. Diversity is enforced architecturally

Per-category caps in the digest prevent any single category (or single source) from dominating, regardless of article-level scores. A digest with 7 BBC articles and 0 AI articles is a failure mode the system actively prevents.

### 7. Volume control respects the user's attention

The default digest is small — 5-7 items per day. infonih is built to *replace* doomscrolling, not to be a more efficient form of it. If the user finds themselves wanting "more articles," that's a signal to refine sources, not to expand digest size.

### 8. Failure modes are visible, not silent

If a source fails to fetch, the user sees it. If Claude scoring fails for an article, the user sees it. If today's digest is empty because nothing met the threshold, the user sees that too — with a clear "low-signal day" message rather than no message at all.

### 9. Privacy by structural design

All user data — sources, interests, history, reactions — lives on the user's own infrastructure when self-hosted. There is no telemetry, no analytics, no phone-home behavior. The optional hosted version (if built) honors the same principle: per-user data isolation, no cross-user analysis.

### 10. The digest is the interface

infonih's primary UI is the Telegram message itself. There is no web dashboard, no mobile app, no email digest. Reactions and commands happen through Telegram. This keeps the product radically simple and the user's attention in one place.

## Focus areas

infonih is opinionated about what content matters. The three focus areas are:

### AI engineering and research

Tracking developments in LLMs, AI tooling, agentic systems, embeddings, and applied AI. Sources include: AI labs (Anthropic, OpenAI, DeepMind), independent commentators (Simon Willison, Ethan Mollick, Jack Clark), research aggregators (ArXiv, Papers With Code), and high-signal communities (Hacker News, r/LocalLLaMA).

### AI policy

The intersection of AI and governance, regulation, and societal impact. Sources include: Lawfare, AI Snake Oil, Don't Worry About the Vase, Stanford HAI, and AI-focused policy writing from think tanks. This is the area where infonih is most uniquely positioned — no other digest tool focuses here specifically.

### Politics — Indonesian and global

Indonesian political and policy coverage from sources like Tempo, Tirto, and Katadata. Global political coverage from wire services (Reuters, BBC) and a small set of analysis sources spanning ideological perspectives. Politics is the highest-noise category and is most strictly capped in digest output.

## Explicit non-goals

These are deliberate decisions about what infonih is not. They prevent scope creep and keep the product coherent.

- **Not a general-audience product.** No effort is made to serve users outside the focus areas above.
- **Not a competitor to Noscroll.** Different distribution channel (Telegram vs SMS), different audience (technical users vs general), different business model (open-source self-hosted vs paid subscription).
- **Not a content discovery tool.** infonih does not surface sources the user hasn't explicitly added.
- **Not a content scraper.** RSS and authorized APIs only. No HTML scraping, no paywall bypass.
- **Not a chat companion.** infonih sends digests and accepts reactions; it is not a conversational AI for general questions.
- **Not multi-language for v1.** English-language sources and English summaries only. Indonesian-language sources may be added later, but Bahasa Indonesia summarization is not a v1 feature.
- **Not a replacement for direct reading.** Summaries are decision aids, not substitutes. Users are expected to click through to read sources they care about.
- **Not a real-time alerter.** Daily digest only. No "breaking news" pushes. The whole point is to *reduce* attention demands, not add new urgency channels.
- **Not a social platform.** No sharing, no public digests, no commentary feeds. Every user's digest is private to them.

## Success criteria

How to know infonih is working:

**For the author specifically:**
- The author reads infonih daily and finds 60%+ of items either useful or interesting
- The author has not opened Hacker News, Twitter/X, or news sites manually for general news consumption (only for follow-up on specific items)
- Time spent on news consumption has decreased while perceived information value has stayed the same or increased
- The author has not had to reactively expand the source list more than 1-2 times per quarter

**For the open-source project:**
- The README is clear enough that a competent developer can fork, configure, and run infonih within an hour
- A blog post about building infonih is published and well-received
- Code on GitHub serves as a portfolio artifact for AI engineering interviews

Conspicuously absent: user count, MRR, retention, or any SaaS-style metrics. infonih is not a business and is not measured as one.

## Open product questions

These are decisions that have not yet been made and may evolve as the project develops.

- **Hosted multi-user mode:** whether to ever build a hosted version that runs infonih as a service for users who don't self-host. Architectural decisions are made to keep this option open without committing to it.
- **Indonesian-language source handling:** whether to support sources that publish primarily in Bahasa Indonesia, and how summaries would work (translate then summarize? summarize in Bahasa? both?).
- **Reaction model:** whether 👍/👎 directly modifies a stored interest profile, or whether it accumulates reactions and Claude periodically re-derives the profile. Both are reasonable; the choice depends on personalization quality observed in practice.
- **Topic clustering:** whether infonih should detect when multiple sources cover the same story and consolidate them in the digest. Architecturally desirable but adds complexity. Likely deferred to v2.
- **Source quality auto-monitoring:** whether to track per-source acceptance rates and surface "this source has produced 0 useful articles in 30 days" warnings to the user. Useful but not v1.

These questions are tracked as decisions are made in `DECISIONS.md`.