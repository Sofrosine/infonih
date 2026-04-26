# infonih - Claude Code Project Instructions

## Project Documentation

When working on this project, read these companion documents alongside this one:
- `PRODUCT.md` — what infonih is, who it's for, product principles
- `FLOWS.md` — user journeys and system flows

Reference these when making product decisions; reference `CLAUDE.md` (this file) for technical standards.

## Project Context

- **Tech**: Python 3.12+, FastAPI, LangGraph, Pydantic v2
- **Package manager**: `uv`
- **Style**: Ruff (line length 100), async-first
- **Type checker**: mypy strict mode
- **Testing**: Pytest + pytest-asyncio, AAA pattern, minimum 60% coverage
- **Architecture**: Hexagonal (Application ↔ Adapters ↔ Agents ↔ Domain)

## Tooling Commands

Always use `uv`:

| Task | Command |
|------|---------|
| Install deps | `uv sync` |
| Add a runtime dep | `uv add <package>` |
| Add a dev dep | `uv add --dev <package>` |
| Run a script | `uv run python -m myapp` |
| Run tests | `uv run pytest` |
| Run linter | `uv run ruff check . --fix` |
| Run formatter | `uv run ruff format .` |
| Run type check | `uv run mypy src` |
| Lock deps | `uv lock` |

## Project Structure

```
src/myapp/
├── main.py                 # FastAPI app factory
├── config.py               # pydantic-settings (single Settings class)
├── api/                    # HTTP shell — thin, no business logic
│   ├── deps.py
│   └── routes/
├── adapters/               # external service wrappers (singletons)
├── agents/                 # LLM workflows — the brain
│   ├── workflows/          # LangGraph state machines (pure wiring)
│   ├── state/              # Pydantic state models
│   ├── chains/             # LLM call units (one file per node)
│   ├── prompts/            # .md templates + Python loader
│   │   └── templates/
│   ├── tools/              # agent-callable functions
│   ├── retrievers/         # search strategies
│   ├── vectorstores/       # vector DB wrappers
│   ├── pipelines/          # deterministic multi-step processing
│   ├── schemas/            # Pydantic models for LLM outputs
│   ├── parsers/            # output repair / extraction
│   ├── middleware/         # cross-cutting concerns
│   ├── callbacks/          # observability hooks
│   ├── usecases/           # orchestrator facades — the entry point
│   └── utils/              # shared helpers (descriptive long names)
├── domain/                 # pure business logic, no I/O
└── common/                 # exceptions, types, helpers
```

### What Each Folder Does (Brief)

- **`api/`** — FastAPI routers. Parse, validate, delegate to a usecase. No LLM logic here.
- **`adapters/`** — One folder or file per external service (S3, Postgres, Redis, vector DB). Singleton instances. Simple adapters (single file): `adapters/<service>_adapter.py`. Adapters with supporting modules (ORM models, query helpers): `adapters/<service>/` folder containing `<service>_adapter.py` plus the helpers.
- **`agents/workflows/`** — LangGraph `StateGraph` definitions. Just nodes + edges, no logic.
- **`agents/state/`** — Two Pydantic classes per workflow: `XxxInputState` (API-facing) + `XxxState` (full).
- **`agents/chains/`** — Each LangGraph node lives in its own file. Takes state, returns partial dict.
- **`agents/prompts/`** — Templates as `.md` files. Python wrapper declares `input_variables`.
- **`agents/tools/`** — Tool-call functions for agents. Pydantic args schema, stateless.
- **`agents/retrievers/`** — Search strategies (vector, hybrid, rerank). Swappable.
- **`agents/vectorstores/`** — Thin DB wrappers (insert, delete, similarity search).
- **`agents/pipelines/`** — Deterministic multi-step flows (e.g. ingestion: extract → chunk → embed).
- **`agents/schemas/`** — Pydantic models for structured LLM outputs (`with_structured_output`).
- **`agents/middleware/`** — LangGraph middleware (tool limits, context formatting, citations).
- **`agents/usecases/`** — Singleton facades. The ONLY thing `api/` imports from `agents/`.
- **`agents/utils/`** — DRY helpers, organized by domain (`utils/document/`, `utils/llm/`, `utils/text/`).

### Architectural Rules — Never Violate

1. `api/` imports from `agents/usecases/` only — never from `chains/`, `workflows/`, or `adapters/` directly
2. `agents/` must NEVER import from `api/`
3. `chains/` must NEVER import from other `chains/` (compose at workflow level)
4. External I/O ONLY through `adapters/`
5. LangGraph nodes return **partial dicts** — never mutate state

### Minimum Viable Scaffold (Day 1)

Don't create empty folders. Start small, split when you grow:
- `state.py` (single file) — split into `state/` when you have 2+ workflows
- `chains/` — one file per node from the start
- `utils.py` — split into `utils/<domain>/` when past 200 lines or 2 domains
- `pipelines/`, `middleware/`, `parsers/` — only when you actually need them

## Coding Standards

### Python Core
- Complete type hints on every function (return type included)
- Async-first for I/O (`async def`, `await`)
- Line length: 100 chars
- Use `loguru` for logging — never `print()`, never stdlib `logging`
- Pydantic v2 (`BaseModel`, `Field`, `field_validator`)
- f-strings for formatting

### DRY
- If used 2x → extract to `agents/utils/<domain>/<descriptive_name>.py`
- Use **descriptive long names**: `extract_citations_from_documents`, not `get_cites`
- Add Google-style docstrings

### Configuration
- Use `pydantic-settings` — single `Settings` class in `src/myapp/config.py`
- Never `os.getenv` outside `config.py`
- Secrets typed as `SecretStr`
- Keep `.env.example` up to date

### Database indexes
- Add an index ONLY when a query that runs frequently scans the column. UNIQUE constraints (which create implicit indexes) are functional and always allowed.
- Do NOT add indexes proactively for `/list-X` endpoints, low-cardinality enum filters on small tables, or "we might filter by this someday" columns.
- Prefer one wider composite index over multiple narrow indexes when queries always filter by the same prefix.
- Partial indexes are appropriate ONLY when (a) the predicate matches a real recurring query and (b) the predicate eliminates a large fraction of rows. Otherwise the planner won't use them.
- When adding an index, drop a comment in the model citing the query that justifies it.

### Testing
- AAA pattern (Arrange-Act-Assert)
- Mock the **adapter**, not the underlying lib
- `@pytest.mark.asyncio` for async tests
- Test naming: `test_<function>_<scenario>_<expected>`
- LLM evals live in `tests/evals/` — separate from unit tests

## Communication Style

### Agent Mode (Making Changes)

**Forbidden:**
- Summarizing file contents
- Copying code blocks into messages
- Narrating actions ("Now I will...", "Let me...")
- Listing completions at end
- Explaining what you're reading

**Required:**
- Reference files by path + line numbers
- Execute silently
- End with "Done"

**Format:**
```
[1 sentence: what's changing and why]
[Execute tools]
Done.
```

### Ask Mode (Questions Only)

- Direct answer (2-3 sentences)
- Bullet points for multi-part
- File references, not explanations
- No preamble

## Token Efficiency

- **Never summarize files** — reference by path
- **Never copy code blocks** — point to file + line numbers
- Use: "See: `path/to/file.py` (lines 10-20)"

## Anti-Patterns — Never Do

1. ❌ `pip install` or any non-`uv` dependency commands
2. ❌ `os.getenv` outside `config.py`
3. ❌ `from myapp.api...` inside `agents/`
4. ❌ Mutating state in LangGraph nodes (return partial dict instead)
5. ❌ Inline f-string prompts — extract to `.md`
6. ❌ Single `helpers.py` or `utils.py` dump — split by domain
7. ❌ Pre-emptive API versioning — version only when external consumers force it
8. ❌ Mixing API request/response models with LLM output schemas
9. ❌ Singleton tools holding mutable state — connections only
10. ❌ Calling boto3/asyncpg/redis-py outside `adapters/`

## Quick Reference — Where Code Goes

| Need | Location |
|------|----------|
| HTTP route | `src/myapp/api/routes/<resource>.py` |
| LLM workflow | `src/myapp/agents/workflows/<name>.py` |
| Workflow node | `src/myapp/agents/chains/<node_name>.py` |
| Prompt | `src/myapp/agents/prompts/templates/<name>.md` + register in `prompts.py` |
| Tool | `src/myapp/agents/tools/<tool_name>.py` |
| Structured LLM output | `src/myapp/agents/schemas/<name>_schema.py` |
| Vector store | `src/myapp/agents/vectorstores/<name>_store.py` |
| Retrieval strategy | `src/myapp/agents/retrievers/<name>_retriever.py` |
| External service | `src/myapp/adapters/<service>_adapter.py` |
| Config value | `src/myapp/config.py` (Settings class) + `.env.example` |
| Shared helper | `src/myapp/agents/utils/<domain>/<descriptive_name>.py` |

## Verification Checklist

Before responding, verify:
- [ ] Used `uv` for any dependency operations?
- [ ] Type hints complete on all new functions?
- [ ] Avoided code duplication (extracted to `utils/` if 2x)?
- [ ] Maintained architecture boundaries?
- [ ] LangGraph nodes return partial dicts?
- [ ] Prompts as `.md` files with declared `input_variables`?
- [ ] Tests written for new behavior?
- [ ] No file summaries / action narration in response?

## Remember

1. **Proactive, not reactive** — Read references automatically
2. **Reference, don't summarize** — Save tokens
3. **Execute, don't narrate** — Tools speak for themselves
4. **Hexagonal, not spaghetti** — Respect layer boundaries
5. **Done, don't celebrate** — End simply