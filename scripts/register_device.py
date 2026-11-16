"""Register, list or revoke phones (ADR 0011).

Run from the project folder. Uses DATABASE_URL from .env, so it works on Neon:

  uv run --env-file .env python scripts/register_device.py add --name "Test phone" --timezone Europe/London
  uv run --env-file .env python scripts/register_device.py list
  uv run --env-file .env python scripts/register_device.py revoke DEVICE_ID
"""
import argparse
import sys
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "app" can be imported

from app import db, devices  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage phones that send data to /ingest.")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="register a phone and print its token once")
    add.add_argument("--name", required=True, help='a nickname, e.g. "Test phone" (avoid full names)')
    add.add_argument("--timezone", required=True, help="IANA timezone, e.g. Europe/London")

    commands.add_parser("list", help="list registered phones")

    revoke = commands.add_parser("revoke", help="stop a phone's token from working")
    revoke.add_argument("device_id", help="the device ID shown by 'list'")

    args = parser.parse_args()
    engine = db.get_engine()
    print(f"Database: {engine.url.host}/{engine.url.database}\n")

    if args.command == "add":
        try:
            ZoneInfo(args.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            sys.exit(f"Unknown timezone {args.timezone!r}. Use an IANA name such as Europe/London.")
        with engine.begin() as conn:
            device, token = devices.create_device(conn, args.name, args.timezone)
        print(f"Registered {device.name!r} ({device.timezone})")
        print(f"Device ID: {device.id}\n")
        print("Token (shown ONLY ONCE - paste it into the phone's Auth Header now):\n")
        print(f"    {token}\n")
        print("If you lose it, revoke this device and register the phone again.")

    elif args.command == "list":
        with engine.connect() as conn:
            rows = devices.list_devices(conn)
        if not rows:
            print("No devices registered.")
        for row in rows:
            status = "REVOKED" if row["revoked_at"] else "active"
            last_seen = row["last_seen_at"] or "never"
            print(f"{row['id']}  {status:7}  {row['name']!r} ({row['timezone']})  last seen: {last_seen}")

    elif args.command == "revoke":
        try:
            device_id = uuid.UUID(args.device_id)
        except ValueError:
            sys.exit("That doesn't look like a device ID. Run 'list' to see them.")
        with engine.begin() as conn:
            revoked = devices.revoke_device(conn, device_id)
        print("Revoked." if revoked else "No active device with that ID.")


if __name__ == "__main__":
    main()
