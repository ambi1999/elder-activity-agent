"""Pretend to be a phone: send protocol v1 batches, to try alerts without the logger app.

Uses a real device token, so the data goes through the same endpoint, checks
and storage as a phone's. Get a token with 'household.py add-phone' (its
"Token:" line), put it in .env as PHONE_TOKEN, then:

  uv run --env-file .env python scripts/simulate_phone.py active
  uv run --env-file .env python scripts/simulate_phone.py quiet --hours 5
  uv run --env-file .env python scripts/simulate_phone.py heartbeat

Scenarios:
  active     steps and screen use now: all looks normal (clears an inactivity alert)
  quiet      activity N hours ago, then only battery readings every 15 minutes
             up to now: an inactivity alert at the next check, if it is
             waking hours and N >= the person's inactive hours
  heartbeat  a battery reading only: the phone is sending, nothing else

Sends to server.public_url from config/settings.toml, or --url (for example
http://localhost:8000 when running the app locally). The first batch from a
newly added phone makes it active.
"""

import argparse
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "app" can be imported

from app.settings import get_settings  # noqa: E402

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def ms(moment: datetime) -> int:
    """Milliseconds since 1970, as protocol v1 timestamps are."""
    return int((moment - EPOCH) / timedelta(milliseconds=1))


def batch(session: str, seq: int, readings: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """A protocol v1 batch."""
    return {
        "protocol": "phone-sensor-logger/v1",
        "session_id": session,
        "batch_seq": seq,
        "sent_at": ms(now),
        "timezone": "UTC",
        "app": {"name": "simulate_phone.py", "version": "1"},
        "readings": readings,
        "summaries": [],
    }


def active(now: datetime) -> list[list[dict[str, Any]]]:
    """Steps going up and the screen turning on, just now."""
    return [
        [
            {"sensor": "steps_total", "t": ms(now - timedelta(minutes=2)), "value": 100},
            {"sensor": "steps_total", "t": ms(now - timedelta(minutes=1)), "value": 160},
            {"sensor": "screen", "t": ms(now - timedelta(minutes=1)), "on": True},
            {"sensor": "battery", "t": ms(now), "level": 0.8, "charging": False},
        ]
    ]


def quiet(now: datetime, hours: float) -> list[list[dict[str, Any]]]:
    """Activity ``hours`` ago, then nothing but battery readings until now."""
    start = now - timedelta(hours=hours)
    first = [
        {"sensor": "steps_total", "t": ms(start - timedelta(minutes=1)), "value": 500},
        {"sensor": "steps_total", "t": ms(start), "value": 540},
    ]
    level, rest, moment = 0.9, [], start + timedelta(minutes=15)
    while moment <= now:
        rest.append({"sensor": "battery", "t": ms(moment), "level": round(level, 2), "charging": False})
        level = max(0.05, level - 0.01)
        moment += timedelta(minutes=15)
    return [first, rest]


def heartbeat(now: datetime) -> list[list[dict[str, Any]]]:
    """One battery reading."""
    return [[{"sensor": "battery", "t": ms(now), "level": 0.7, "charging": False}]]


def main() -> None:
    """Send the chosen scenario's batches and print the server's answers."""
    parser = argparse.ArgumentParser(description="Send simulated phone data.")
    parser.add_argument("scenario", choices=["active", "quiet", "heartbeat"])
    parser.add_argument("--hours", type=float, default=5, help="for 'quiet': hours since the last activity")
    parser.add_argument("--url", help="base URL of the service (default: server.public_url)")
    args = parser.parse_args()

    token = os.getenv("PHONE_TOKEN")
    if not token:
        sys.exit("Set PHONE_TOKEN in .env to a token from 'household.py add-phone'.")
    base = (args.url or get_settings().server.public_url).rstrip("/")
    now = datetime.now(UTC)
    plans = {"active": active(now), "quiet": quiet(now, args.hours), "heartbeat": heartbeat(now)}
    session = f"sim-{uuid.uuid4().hex[:12]}"

    # Render's free plan sleeps; the first request can take up to a minute to wake it.
    with httpx.Client(timeout=90) as client:
        for seq, readings in enumerate(plans[args.scenario]):
            response = client.post(
                f"{base}/v1/readings",
                json=batch(session, seq, readings, now),
                headers={"Authorization": f"Bearer {token}"},
            )
            print(f"batch {seq}: HTTP {response.status_code} {response.text[:200]}")
    print("Done. Alerts are checked every 5 minutes (or run the check now: see README, 'Alerts').")


if __name__ == "__main__":
    main()
