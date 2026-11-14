"""HTTP API around the agent. Render runs this."""
import hmac
import logging
import os
from collections import Counter

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Elder Activity Agent", version="0.2.0")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[dict]


class SensorBatch(BaseModel):
    """One message from Sensor Logger's HTTP push."""
    messageId: int
    sessionId: str
    deviceId: str
    payload: list[dict] = Field(default_factory=list)


def _matches(given: str | None, expected: str) -> bool:
    # Constant-time comparison, so attackers can't guess the secret by timing responses.
    return hmac.compare_digest((given or "").encode(), expected.encode())


@app.get("/health")
def health() -> dict:
    # Render sets RENDER_GIT_COMMIT to the deployed commit; "dev" when running locally.
    return {"status": "ok", "commit": os.getenv("RENDER_GIT_COMMIT", "dev")}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, x_api_key: str | None = Header(default=None)) -> dict:
    # The URL is public, so require a key; otherwise anyone could use up your Gemini quota.
    expected = os.getenv("APP_API_KEY")
    if expected and not _matches(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    try:
        return agent.run_agent(request.message)
    except Exception:
        log.exception("Agent failed")
        raise HTTPException(status_code=502, detail="The AI model is unavailable right now. Try again shortly.")

@app.post("/ingest")
def ingest(batch: SensorBatch, authorization: str | None = Header(default=None)) -> dict:
    # The token must come in the Authorization header; tokens in URLs leak into logs.
    supplied = (authorization or "").removeprefix("Bearer ").strip()

    # Fail closed: if no token is configured on the server, reject everything.
    expected = os.getenv("INGEST_TOKEN")
    if not expected or not _matches(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    counts = Counter(reading.get("name", "unknown") for reading in batch.payload)
    log.info(
        "ingest device=%s session=%s message=%s readings=%s",
        batch.deviceId[:8], batch.sessionId[:8], batch.messageId, dict(counts),
    )

    # TEMPORARY: log one example reading per sensor so we can see the real format.
    seen = set()
    for reading in batch.payload:
        name = reading.get("name")
        if name not in seen:
            seen.add(name)
            log.info("sample %s", reading)

    return {"status": "ok", "received": len(batch.payload)}

