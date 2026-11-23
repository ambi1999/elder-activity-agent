"""HTTP API around the agent and the phones' uploads. Render runs this.

Routes:
    GET  /health          liveness, without touching the database
    GET  /health/db       database check (needs APP_API_KEY)
    POST /chat            ask the agent (needs APP_API_KEY)
    POST /v1/readings     phone-sensor-logger protocol v1 uploads (ADR 0023)
    POST /ingest          Sensor Logger uploads, until no test phone uses it (ADR 0014)
    Alert routes (check job, Telegram webhook, email links): see app/alert_routes.py
    The family and care web app (sign-in, people, alerts): see app/web.py
    GET  /static/...      the web app's stylesheet, script and icons
"""

import hmac
import json
import logging
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app import agent, alert_routes, db, devices, protocol_v1, rate_limit, sensor_logger, storage, web
from app.brand import STATIC, contrast_problems, get_brand
from app.limits import BodyTooLarge, MaxBodySizeMiddleware
from app.problems import Problem, handle_problem
from app.settings import Settings, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

# Loaded here so a wrong setting stops the app at startup, naming the setting (story A-1).
settings = get_settings()
# The brand too (story D-4): a wrong value in config/brand.toml stops the app, naming it.
brand = get_brand()
for problem in contrast_problems(brand.colours):
    # CI fails on these (tests/test_brand.py); here a warning, so a deploy isn't stopped by a colour.
    log.warning("Brand colour contrast too low: %s", problem)

app = FastAPI(title="Elder Activity Agent", version=web.VERSION)
app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.ingest.max_body_bytes)
app.add_exception_handler(Problem, handle_problem)
app.include_router(alert_routes.router)
app.include_router(web.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class ChatRequest(BaseModel):
    """A question for the agent."""

    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    """The agent's answer, with the tools it called on the way."""

    answer: str
    tool_calls: list[dict[str, Any]]


def _matches(given: str | None, expected: str) -> bool:
    # Constant-time comparison, so attackers can't guess the secret by timing responses.
    return hmac.compare_digest((given or "").encode(), expected.encode())


def _require_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("APP_API_KEY")
    if expected and not _matches(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _bearer_token(authorization: str | None) -> str:
    """The token from an ``Authorization: Bearer <token>`` header, or ""."""
    return (authorization or "").removeprefix("Bearer ").strip()


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the app is running, and which commit is deployed."""
    # Deliberately does NOT touch the database: Render calls this every few seconds,
    # and querying Neon each time would stop it from ever sleeping (ADR 0016).
    return {"status": "ok", "commit": os.getenv("RENDER_GIT_COMMIT", "dev")}


@app.get("/health/db")
def health_db(x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Check the database and report its schema revision."""
    # Protected, so strangers can't keep the database awake by calling it.
    _require_api_key(x_api_key)
    try:
        with db.get_engine().connect() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as err:
        log.exception("Database check failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from err
    return {"database": "ok", "schema_revision": revision}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Answer a question with the agent."""
    # The URL is public, so require a key; otherwise anyone could use up your Gemini quota.
    _require_api_key(x_api_key)
    try:
        return agent.run_agent(request.message)
    except Exception as err:
        log.exception("Agent failed")
        raise HTTPException(
            status_code=502, detail="The AI model is unavailable right now. Try again shortly."
        ) from err


# ---------------------------------------------------------------------------
# Protocol v1 uploads (ADR 0023)
# ---------------------------------------------------------------------------


@app.post("/v1/readings")
async def readings_v1(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Receive one phone-sensor-logger protocol v1 batch.

    Responses follow protocol v1 section 9: 200 with counts (``status`` "ok" or
    "duplicate"), or Problem Details for 401, 413, 422, 429 and 503.
    """
    try:
        body = await request.body()
    except BodyTooLarge as err:
        raise Problem(413, f"Request body larger than {settings.ingest.max_body_bytes} bytes.") from err
    # Database work is blocking, so it runs in a worker thread, not the event loop.
    return await run_in_threadpool(_receive_v1, body, _bearer_token(authorization), settings)


def _receive_v1(body: bytes, token: str, settings: Settings) -> dict[str, Any]:
    """Authenticate, limit, validate and store a protocol v1 batch (blocking)."""
    now = datetime.now(UTC)
    try:
        engine = db.get_engine()
        with engine.connect() as conn:
            device = devices.find_device(conn, token, now)
    except SQLAlchemyError as err:
        log.exception("Device lookup failed")
        raise Problem(503, "Storage unavailable, please retry.") from err
    if device is None:
        # Same answer for missing, unknown, revoked and expired tokens: nothing to learn by guessing.
        raise Problem(401, "Missing, unknown, revoked or expired device token.", {"WWW-Authenticate": "Bearer"})

    wait = rate_limit.uploads.check(str(device.id), settings.ingest.batches_per_minute_per_device, now)
    if wait is not None:
        raise Problem(429, "Too many batches from this phone; retry later.", {"Retry-After": str(wait)})

    envelope = _parse_envelope(body)
    limit = settings.ingest.max_items_per_batch
    if len(envelope.readings) > limit or len(envelope.summaries) > limit:
        raise Problem(413, f"At most {limit} readings and {limit} summaries per batch; send smaller batches.")

    batch = protocol_v1.to_batch(envelope, settings.ingest.accepted_sensors)
    rules = storage.Plausibility(
        max_future=timedelta(minutes=settings.ingest.max_future_minutes),
        max_age=timedelta(days=settings.ingest.max_reading_age_days),
    )
    try:
        result = storage.save_batch(engine, device.id, batch, now=now, rules=rules)
    except SQLAlchemyError as err:
        # Nothing was saved (the transaction rolled back); the phone can safely retry.
        log.exception("Saving batch failed")
        raise Problem(503, "Storage unavailable, please retry.") from err

    # One line per batch: counts only, never sensor values or tokens.
    log.info(
        "v1 device=%s session=%s batch=%s status=%s stored=%s ignored=%s dropped=%s",
        str(device.id)[:8],
        envelope.session_id[:8],
        envelope.batch_seq,
        result.status,
        result.stored,
        result.ignored,
        result.dropped,
    )
    return asdict(result)


def _parse_envelope(body: bytes) -> protocol_v1.BatchEnvelope:
    """Decode and validate a batch's top level, or raise 422 naming the bad fields."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise Problem(422, "The body is not valid JSON.") from err
    try:
        return protocol_v1.BatchEnvelope.model_validate(data)
    except ValidationError as err:
        # Field names only: values could be sensor data.
        fields = sorted({".".join(str(p) for p in e["loc"]) or "(batch)" for e in err.errors()})
        raise Problem(422, f"Invalid batch; check these fields: {', '.join(fields)}.") from err


# ---------------------------------------------------------------------------
# Sensor Logger uploads (ADR 0014), kept until no test phone uses them
# ---------------------------------------------------------------------------


@app.post("/ingest")
def ingest(
    batch: sensor_logger.SensorLoggerBatch,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive one batch from the Sensor Logger app's HTTP push."""
    # Each phone has its own token, sent in the Authorization header (ADR 0011).
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    now = datetime.now(UTC)
    try:
        engine = db.get_engine()
        with engine.connect() as conn:
            device = devices.find_device(conn, token, now)
        if device is None:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        result = storage.save_batch(engine, device.id, sensor_logger.to_batch(batch), now=now)
    except SQLAlchemyError as err:
        # Nothing was saved (the transaction rolled back); the phone can safely retry.
        log.exception("Saving batch failed")
        raise HTTPException(status_code=503, detail="Storage unavailable, please retry") from err

    # One line per batch: counts only, never sensor values or tokens.
    log.info(
        "ingest device=%s session=%s batch=%s status=%s stored=%s ignored=%s dropped=%s",
        str(device.id)[:8],
        batch.sessionId[:8],
        batch.messageId,
        result.status,
        result.stored,
        result.ignored,
        result.dropped,
    )
    return asdict(result)
