FROM python:3.12-slim

# System deps: gcc for any wheel that needs compilation, libpq-dev for psycopg
# (used by Alembic migrations against Postgres), curl + ca-certs to install uv.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv into a stable PATH location.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Install Python deps first so Docker can cache this layer when only the
# app code changes. --no-dev skips the dev-only deps (pytest, ruff, mypy).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App code last — this layer rebuilds whenever the code changes, but the
# heavy dependency-install layer above stays cached.
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
