"""Check that an old ingest token is rejected and the current one works.

Usage:
    uv run --env-file .env python scripts/check_token.py https://your-url.onrender.com OLD_TOKEN
"""
import os
import sys

import httpx

base, old = sys.argv[1].rstrip("/"), sys.argv[2]
url = f"{base}/ingest"
body = {"messageId": 1, "sessionId": "check", "deviceId": "check", "payload": []}


def status(**kwargs) -> int:
    return httpx.post(url, json=body, timeout=60, **kwargs).status_code


print("old token in header:", status(headers={"Authorization": old}))
print("old token in URL:   ", status(params={"token": old}))
print("current token:      ", status(headers={"Authorization": os.environ["INGEST_TOKEN"]}))