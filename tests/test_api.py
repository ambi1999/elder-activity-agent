from fastapi.testclient import TestClient

from app import agent, main

client = TestClient(main.app)


def fake_agent(message: str) -> dict:
    # Stand-in for Gemini so tests are free, fast and don't need an API key.
    return {"answer": f"echo: {message}", "tool_calls": []}


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "commit" in body

def test_chat(monkeypatch):
    monkeypatch.setattr(agent, "run_agent", fake_agent)
    monkeypatch.delenv("APP_API_KEY", raising=False)
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 200
    assert response.json()["answer"] == "echo: hi"


def test_chat_requires_key_when_set(monkeypatch):
    monkeypatch.setattr(agent, "run_agent", fake_agent)
    monkeypatch.setenv("APP_API_KEY", "secret")
    assert client.post("/chat", json={"message": "hi"}).status_code == 401
    ok = client.post("/chat", json={"message": "hi"}, headers={"X-API-Key": "secret"})
    assert ok.status_code == 200


def test_chat_model_failure(monkeypatch):
    def broken(message):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(agent, "run_agent", broken)
    monkeypatch.delenv("APP_API_KEY", raising=False)
    assert client.post("/chat", json={"message": "hi"}).status_code == 502
