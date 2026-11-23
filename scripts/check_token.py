"""Check that an old token is rejected and a current device token works.

Put the current device token in .env as DEVICE_TOKEN, then:
    uv run --env-file .env python scripts/check_token.py https://your-url.onrender.com OLD_TOKEN
"""

import os
import sys
from typing import Any

import httpx

# Accept the URL with or without /ingest on the end.
base, old = sys.argv[1].rstrip("/").removesuffix("/ingest"), sys.argv[2]
url = f"{base}/ingest"
body = {"messageId": 1, "sessionId": "token-check", "deviceId": "check", "payload": []}


def status(**kwargs: Any) -> int:
    """POST a test batch with the given httpx options; return the HTTP status."""
    return httpx.post(url, json=body, timeout=60, **kwargs).status_code


print("old token in header:", status(headers={"Authorization": old}))
print("old token in URL:   ", status(params={"token": old}))
print("current token:      ", status(headers={"Authorization": os.environ["DEVICE_TOKEN"]}))
