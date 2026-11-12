FROM python:3.12-slim

# uv binary from Astral's official image.
# For fully reproducible builds, replace "latest" with the version from `uv --version`.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Install dependencies first (cached layer), exactly as pinned in uv.lock, without dev tools.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
ENV PATH="/srv/.venv/bin:$PATH"

# Don't run as root inside the container.
RUN useradd --create-home appuser
USER appuser

# Cloud Run tells the app which port to use via $PORT.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
