"""HTTP API around the agent. Render runs this."""
import hmac
import logging
import os
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import agent, db, devices, sensor_logger, storage
from app.limits import MaxBodySizeMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Elder Activity Agent", version="0.4.0")
app.add_middleware(MaxBodySizeMiddleware)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[dict]


def _matches(given: str | None, expected: str) -> bool:
    # Constant-time comparison, so attackers can't guess the secret by timing responses.
    return hmac.compare_digest((given or "").encode(), expected.encode())


def _require_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("APP_API_KEY")
    if expected and not _matches(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health")
def health() -> dict:
    # Deliberately does NOT touch the database: Render calls this every few seconds,
    # and querying Neon each time would stop it from ever sleeping (ADR 0016).
    return {"status": "ok", "commit": os.getenv("RENDER_GIT_COMMIT", "dev")}


@app.get("/health/db")
def health_db(x_api_key: str | None = Header(default=None)) -> dict:
    # Protected, so strangers can't keep the database awake by calling it.
    _require_api_key(x_api_key)
    try:
        with db.get_engine().connect() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        log.exception("Database check failed")
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"database": "ok", "schema_revision": revision}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, x_api_key: str | None = Header(default=None)) -> dict:
    # The URL is public, so require a key; otherwise anyone could use up your Gemini quota.
    _require_api_key(x_api_key)
    try:
        return agent.run_agent(request.message)
    except Exception:
        log.exception("Agent failed")
        raise HTTPException(status_code=502, detail="The AI model is unavailable right now. Try again shortly.")


@app.post("/ingest")
def ingest(
    batch: sensor_logger.SensorLoggerBatch,
    authorization: str | None = Header(default=None),
) -> dict:
    # Each phone has its own token, sent in the Authorization header (ADR 0011).
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    try:
        engine = db.get_engine()
        with engine.connect() as conn:
            device = devices.find_device(conn, token)
        if device is None:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        result = storage.save_batch(engine, device.id, sensor_logger.to_batch(batch), now=datetime.now(UTC))
    except SQLAlchemyError:
        # Nothing was saved (the transaction rolled back); the phone can safely retry.
        log.exception("Saving batch failed")
        raise HTTPException(status_code=503, detail="Storage unavailable, please retry")

    # One line per batch: counts only, never sensor values or tokens.
    log.info(
        "ingest device=%s session=%s batch=%s status=%s stored=%s ignored=%s dropped=%s",
        str(device.id)[:8], batch.sessionId[:8], batch.messageId,
        result.status, result.stored, result.ignored, result.dropped,
    )
    return asdict(result)
