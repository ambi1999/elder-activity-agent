"""HTTP API around the agent. Cloud Run runs this."""
import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Elder Activity Agent", version="0.1.0")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[dict]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, x_api_key: str | None = Header(default=None)) -> dict:
    # The URL is public, so require a key; otherwise anyone could use up your Gemini quota.
    expected = os.getenv("APP_API_KEY")
    if expected and not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    try:
        return agent.run_agent(request.message)
    except Exception:
        log.exception("Agent failed")
        raise HTTPException(status_code=502, detail="The AI model is unavailable right now. Try again shortly.")
