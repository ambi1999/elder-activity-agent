"""Contract tests: every example in the vendored protocol, through the real endpoint (ADR 0023).

examples/manifest.json says what a conforming receiver must do with each file:
accept it (HTTP 200) or reject it (HTTP 422, as Problem Details).

Verifies: EA-NFR-CMP-001
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import devices, main

EXAMPLES = Path(__file__).resolve().parents[1] / "protocol" / "phone-sensor-logger-v1" / "examples"
MANIFEST = json.loads((EXAMPLES / "manifest.json").read_text())
client = TestClient(main.app)


@pytest.mark.parametrize("case", MANIFEST["batch"], ids=lambda c: c["file"])
def test_receiver_follows_the_manifest(migrated_db, case):
    with migrated_db.begin() as conn:
        _, token = devices.create_device(conn, "Contract test phone", "UTC")
    body = (EXAMPLES / case["file"]).read_bytes()

    response = client.post(
        "/v1/readings", content=body, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )

    if case["receiver"] == "accept":
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ok"
    else:
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
