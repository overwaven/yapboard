# syntax=docker/dockerfile:1
FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

# Install dependencies first (cached layer).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code + migrations.
COPY src ./src
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "yapboard"]
