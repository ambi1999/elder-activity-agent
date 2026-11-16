FROM python:3.12-slim

# uv binary from Astral's official image.

# uv binary from Astral's official image, pinned to an exact version (ADR 0021).
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Install dependencies first (cached layer), exactly as pinned in uv.lock, without dev tools.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/srv/.venv/bin:$PATH"

# Don't run as root inside the container.
RUN useradd --create-home appuser
USER appuser

# Apply database migrations, then start the app. If a migration fails, the app never
# starts, the health check fails, and Render keeps the previous version running (ADR 0015).
CMD alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
