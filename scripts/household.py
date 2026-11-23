"""Set up households and add their phones from the command line (ADR 0024, story A-2).

Until the family web app exists (step D), this is how a household is created
and a phone connected. Run from the project folder; it uses DATABASE_URL from
.env, so it works on Neon:

  uv run --env-file .env python scripts/household.py create --name "Family 1" --person Mum --timezone Australia/Brisbane
  uv run --env-file .env python scripts/household.py add-phone --person PERSON_ID --name "Mum's phone"
  uv run --env-file .env python scripts/household.py list
  uv run --env-file .env python scripts/household.py revoke DEVICE_ID
  uv run --env-file .env python scripts/household.py delete HOUSEHOLD_ID

Replace PERSON_ID, DEVICE_ID and HOUSEHOLD_ID with the IDs that 'create' and
'list' print.

add-phone prints the setup QR code in the terminal, once. Scan it with the
logger app (Settings > Connection > Scan setup QR code); the phone's owner then
agrees on the consent screen. The code contains the device token, so don't
screenshot, print or share it; if it expires, run add-phone again.
"""

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import segno

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "app" can be imported

from app import db, devices, households  # noqa: E402
from app.settings import get_settings  # noqa: E402


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        sys.exit(f"That doesn't look like a {what} ID. Run 'list' to see them.")


def _create(args: argparse.Namespace) -> None:
    try:
        households.check_timezone(args.timezone)
    except ValueError as err:
        sys.exit(str(err))
    with db.get_engine().begin() as conn:
        household = households.create_household(conn, args.name)
        person = households.add_person(conn, household.id, args.person, args.timezone)
    print(f"Household {household.name!r}: {household.id}")
    print(f"Person    {person.display_name!r} ({person.timezone}): {person.id}\n")
    print(f'Next: add their phone with\n  add-phone --person {person.id} --name "{person.display_name}\'s phone"')


def _add_phone(args: argparse.Namespace) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    with db.get_engine().begin() as conn:
        person = households.find_person(conn, _uuid(args.person, "person"))
        if person is None:
            sys.exit("No person with that ID. Run 'list' to see them.")
        try:
            phone = households.add_phone(conn, person, args.name, now, settings)
        except ValueError as err:
            sys.exit(str(err))

    # Compact JSON keeps the QR code small enough to scan easily from a screen.
    contents = json.dumps(phone.provisioning, separators=(",", ":"))
    print(f"Phone {phone.device.name!r} added for {person.display_name} (device {phone.device.id}).\n")
    if not args.no_qr:
        segno.make(contents, error="m").terminal(compact=True)
    expires = phone.expires_at.astimezone().strftime("%H:%M on %d %b")
    minutes = settings.pairing.pending_token_expiry_minutes
    print(f"\nThis code works for {minutes} minutes (until {expires}) and is shown only once.")
    print("Scan it in the logger app: Settings > Connection > Scan setup QR code.")
    print("Can't scan? Type these instead:")
    print(f"  Endpoint: {phone.provisioning['endpoint']}")
    print(f"  Token:    {phone.provisioning['token']}")
    print("\nThen run 'list': the phone shows as active once its first data arrives.")


def _list(_: argparse.Namespace) -> None:
    with db.get_engine().connect() as conn:
        rows = households.list_households(conn)
    if not rows:
        print("No households yet. Create one with 'create'.")
    current = None
    for row in rows:
        if row["household_id"] != current:
            current = row["household_id"]
            print(f"\n{row['household']!r}  household {row['household_id']}")
        if row["person_id"] is None:
            continue
        if row["device_id"] is None:
            print(f"  {row['person']!r} ({row['timezone']})  person {row['person_id']}  - no phone yet")
            continue
        seen = row["last_seen_at"] or "never"
        note = f"  expires {row['pending_expires_at']}" if row["status"] == "pending" else ""
        print(
            f"  {row['person']!r}  person {row['person_id']}\n"
            f"    {row['device']!r}  device {row['device_id']}  {row['status']}  last seen: {seen}{note}"
        )


def _revoke(args: argparse.Namespace) -> None:
    with db.get_engine().begin() as conn:
        revoked = devices.revoke_device(conn, _uuid(args.device_id, "device"))
    print("Revoked: the phone's token no longer works." if revoked else "No pending or active device with that ID.")


def _delete(args: argparse.Namespace) -> None:
    household_id = _uuid(args.household_id, "household")
    with db.get_engine().begin() as conn:
        household = households.find_household(conn, household_id)
        if household is None:
            sys.exit("No household with that ID. Run 'list' to see them.")
        counts = households.count_household_data(conn, household_id)
        print(
            f"This permanently deletes {household.name!r}: {counts['people']} person(s), "
            f"{counts['phones']} phone(s) and {counts['data_rows']} stored data row(s)."
        )
        if not args.yes and input(f"Type the household name ({household.name}) to confirm: ") != household.name:
            sys.exit("Not deleted.")
        households.delete_household(conn, household_id)
    print("Deleted.")


def main() -> None:
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(description="Manage households and connect their phones.")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create a household and the person being looked after")
    create.add_argument("--name", required=True, help='household name, e.g. "Family 1" (avoid surnames)')
    create.add_argument("--person", required=True, help='nickname of the person, e.g. "Mum" (not a full name)')
    create.add_argument("--timezone", required=True, help="their IANA timezone, e.g. Australia/Brisbane")
    create.set_defaults(run=_create)

    add_phone = commands.add_parser("add-phone", help="add a phone and print its setup QR code once")
    add_phone.add_argument("--person", required=True, help="the person ID shown by 'create' or 'list'")
    add_phone.add_argument("--name", required=True, help='nickname for the phone, e.g. "Mum\'s phone"')
    add_phone.add_argument("--no-qr", action="store_true", help="print only the endpoint and token, no QR code")
    add_phone.set_defaults(run=_add_phone)

    commands.add_parser("list", help="list households, people and phones").set_defaults(run=_list)

    revoke = commands.add_parser("revoke", help="stop a phone's token from working")
    revoke.add_argument("device_id", help="the device ID shown by 'list'")
    revoke.set_defaults(run=_revoke)

    delete = commands.add_parser("delete", help="delete a household and everything about it")
    delete.add_argument("household_id", help="the household ID shown by 'list'")
    delete.add_argument("--yes", action="store_true", help="don't ask for confirmation (for scripts)")
    delete.set_defaults(run=_delete)

    args = parser.parse_args()
    print(f"Database: {db.describe(db.get_engine())}")
    args.run(args)


if __name__ == "__main__":
    main()
