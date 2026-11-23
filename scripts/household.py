"""Set up households and add their phones from the command line (ADR 0024, story A-2).

Until the family web app exists (step D), this is how a household is created
and a phone connected. Run from the project folder; it uses DATABASE_URL from
.env, so it works on Neon:

  uv run --env-file .env python scripts/household.py create --name "Family 1" --person Mum --timezone Australia/Brisbane
  uv run --env-file .env python scripts/household.py add-phone --person PERSON_ID --name "Mum's phone"
  uv run --env-file .env python scripts/household.py list
  uv run --env-file .env python scripts/household.py revoke DEVICE_ID
  uv run --env-file .env python scripts/household.py delete HOUSEHOLD_ID

Alerts (step C, ADR 0026):

  ... household.py add-contact --household HOUSEHOLD_ID --name Daughter --telegram
  ... household.py add-contact --household HOUSEHOLD_ID --name Son --email son@example.com
  ... household.py contacts --household HOUSEHOLD_ID
  ... household.py quiet-hours CONTACT_ID --from 22:00 --to 07:00     (or --off)
  ... household.py remove-contact CONTACT_ID
  ... household.py alert-settings --person PERSON_ID --waking 08:00-21:00 --inactive-hours 4 --silent-hours 6
  ... household.py setup-telegram        (once, after creating the bot and setting its secrets)

Web app sign-in (step D1, ADR 0025). Accounts are invite only while testing:

  ... household.py add-member --household HOUSEHOLD_ID --email daughter@example.com --name Daughter --role owner
  ... household.py members --household HOUSEHOLD_ID
  ... household.py remove-member --household HOUSEHOLD_ID --email daughter@example.com
  ... household.py signin-link --email daughter@example.com
  ... household.py user --email nurse@example.com

signin-link prints a one-time sign-in link instead of emailing it: for testing
while the email service can only send to your own address. Anyone with the
link can sign in as that user until it is used or expires, so treat it like a
password: don't share, screenshot or paste it.

Replace PERSON_ID, DEVICE_ID, HOUSEHOLD_ID and CONTACT_ID with the IDs that
'create', 'list' and 'contacts' print.

add-phone prints the setup QR code in the terminal, once. Scan it with the
logger app (Settings > Connection > Scan setup QR code); the phone's owner then
agrees on the consent screen. The code contains the device token, so don't
screenshot, print or share it; if it expires, run add-phone again.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime, time
from pathlib import Path

import segno
from sqlalchemy.engine import Connection

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "app" can be imported

from app import access, alerts, auth, contacts, db, devices, households, rules  # noqa: E402
from app.messages import confirm_email  # noqa: E402
from app.notifiers import TelegramNotifier  # noqa: E402
from app.notifiers import build as build_notifiers  # noqa: E402
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


def _time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        sys.exit(f"{value!r} isn't a time like 07:30.")


def _household(conn: Connection, value: str) -> households.Household:
    household = households.find_household(conn, _uuid(value, "household"))
    if household is None:
        sys.exit("No household with that ID. Run 'list' to see them.")
    return household


def _add_contact(args: argparse.Namespace) -> None:
    settings = get_settings()
    channel = "telegram" if args.telegram else "email"
    with db.get_engine().begin() as conn:
        household = _household(conn, args.household)
        try:
            new = contacts.add_contact(
                conn, household.id, args.name, channel, datetime.now(UTC), settings, email=args.email
            )
        except ValueError as err:
            sys.exit(str(err))
    minutes = settings.alerts.link_expiry_minutes
    print(f"Contact {args.name!r} added to {household.name!r} (contact {new.contact.id}), not yet confirmed.")
    if channel == "telegram":
        print(f"\nSend {args.name} this link. They open it in Telegram and press Start (works for {minutes} minutes):")
        print(f"  {new.link}")
        return
    sent = build_notifiers(settings)["email"].send(
        new.contact.address or "", confirm_email(args.name, new.link, minutes)
    )
    print("A confirmation email has been sent." if sent else "The confirmation email could not be sent.")
    if not os.getenv("RESEND_API_KEY"):
        print(f"(Email isn't set up yet, so here is the link to open instead, valid {minutes} minutes:)\n  {new.link}")


def _contacts(args: argparse.Namespace) -> None:
    with db.get_engine().connect() as conn:
        household = _household(conn, args.household)
        found = contacts.list_contacts(conn, household.id)
    print(f"Contacts of {household.name!r}:")
    if not found:
        print("  none yet; add one with 'add-contact'")
    for c in found:
        state = "confirmed" if c.confirmed_at else "waiting for confirmation"
        quiet = f", quiet {c.quiet_from:%H:%M}-{c.quiet_to:%H:%M}" if c.quiet_from and c.quiet_to else ""
        print(f"  {c.display_name!r} ({c.channel}, {state}{quiet})  contact {c.id}")


def _quiet_hours(args: argparse.Namespace) -> None:
    start, end = (None, None) if args.off else (_time(args.start), _time(args.end))
    with db.get_engine().begin() as conn:
        try:
            done = contacts.set_quiet_hours(conn, _uuid(args.contact_id, "contact"), start, end)
        except ValueError as err:
            sys.exit(str(err))
    print("Saved." if done else "No contact with that ID.")


def _remove_contact(args: argparse.Namespace) -> None:
    with db.get_engine().begin() as conn:
        done = contacts.remove_contact(conn, _uuid(args.contact_id, "contact"))
    print("Removed: they get no more messages." if done else "No contact with that ID.")


def _alert_settings(args: argparse.Namespace) -> None:
    settings = get_settings()
    with db.get_engine().begin() as conn:
        person = households.find_person(conn, _uuid(args.person, "person"))
        if person is None:
            sys.exit("No person with that ID. Run 'list' to see them.")
        current = alerts.get_timing(conn, person.id, settings)
        start, end = current.waking_from, current.waking_to
        if args.waking:
            first, _, second = args.waking.partition("-")
            start, end = _time(first), _time(second)
        timing = rules.AlertTiming(
            start,
            end,
            args.inactive_hours or current.inactive_hours,
            args.silent_hours or current.silent_hours,
        )
        try:
            alerts.set_timing(conn, person.id, timing)
        except ValueError as err:
            sys.exit(str(err))
    print(
        f"{person.display_name}: waking {timing.waking_from:%H:%M}-{timing.waking_to:%H:%M}, alert after "
        f"{timing.inactive_hours} h without activity or {timing.silent_hours} h without data."
    )


def _add_member(args: argparse.Namespace) -> None:
    with db.get_engine().begin() as conn:
        household = _household(conn, args.household)
        try:
            user = auth.add_user(conn, args.email, args.name or args.email.split("@")[0])
            auth.add_member(conn, user.id, household.id, args.role)
        except ValueError as err:
            sys.exit(str(err))
    print(f"{user.display_name} ({user.email}) is now {args.role} of {household.name!r}.")
    print("They can sign in at /signin with that address.")


def _members(args: argparse.Namespace) -> None:
    with db.get_engine().connect() as conn:
        household = _household(conn, args.household)
        found = auth.list_members(conn, household.id)
    print(f"Members of {household.name!r}:")
    if not found:
        print("  none yet; add one with 'add-member'")
    for m in found:
        print(f"  {m.user.display_name} <{m.user.email}> {m.role}")


def _remove_member(args: argparse.Namespace) -> None:
    with db.get_engine().begin() as conn:
        household = _household(conn, args.household)
        try:
            user = auth.find_user(conn, auth.normalize_email(args.email))
        except ValueError as err:
            sys.exit(str(err))
        done = user is not None and auth.remove_member(conn, user.id, household.id)
    print("Removed: they can no longer see this household." if done else "They aren't a member of it.")


def _signin_link(args: argparse.Namespace) -> None:
    settings = get_settings()
    with db.get_engine().begin() as conn:
        try:
            user = auth.find_user(conn, auth.normalize_email(args.email))
        except ValueError as err:
            sys.exit(str(err))
        if user is None:
            sys.exit("No user with that email address. Add them with 'add-member' first.")
        link = auth.create_signin_link(conn, user, datetime.now(UTC), settings)
    print(f"Sign-in link for {user.display_name}, works once for {settings.web.signin_link_minutes} minutes:")
    print(f"  {link}")
    print("Treat it like a password: don't share, screenshot or paste it.")


def _user(args: argparse.Namespace) -> None:
    with db.get_engine().connect() as conn:
        try:
            user = auth.find_user(conn, auth.normalize_email(args.email))
        except ValueError as err:
            sys.exit(str(err))
        if user is None:
            sys.exit("No user with that email address.")
        summary = access.user_summary(conn, user.id)
    print(f"{user.display_name} <{user.email}>")
    if not summary:
        print("  not a member of any household yet")
    for household, role, people in summary:
        print(f"  {household!r} as {role}: {', '.join(people) or 'nobody yet'}")
    total = sum(len(people) for _, _, people in summary)
    print(f"Sees {total} {'person' if total == 1 else 'people'} in {len(summary)} household(s).")


def _setup_telegram(_: argparse.Namespace) -> None:
    settings = get_settings()
    token, secret = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if not (token and secret and settings.telegram.bot_username):
        sys.exit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET in .env, and telegram.bot_username, first.")
    url = f"{settings.server.public_url}/telegram/webhook"
    ok = TelegramNotifier(token).set_webhook(url, secret)
    print(f"Telegram will now send updates to {url}." if ok else "Telegram refused; check the token.")


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

    add_contact = commands.add_parser("add-contact", help="add an alert contact (email or Telegram)")
    add_contact.add_argument("--household", required=True, help="the household ID shown by 'list'")
    add_contact.add_argument("--name", required=True, help='how they are named in messages, e.g. "Daughter"')
    how = add_contact.add_mutually_exclusive_group(required=True)
    how.add_argument("--email", help="their email address")
    how.add_argument("--telegram", action="store_true", help="link their Telegram chat")
    add_contact.set_defaults(run=_add_contact)

    show_contacts = commands.add_parser("contacts", help="list a household's alert contacts")
    show_contacts.add_argument("--household", required=True, help="the household ID shown by 'list'")
    show_contacts.set_defaults(run=_contacts)

    quiet = commands.add_parser("quiet-hours", help="no messages to a contact between two times")
    quiet.add_argument("contact_id", help="the contact ID shown by 'contacts'")
    quiet.add_argument("--from", dest="start", help="start, e.g. 22:00")
    quiet.add_argument("--to", dest="end", help="end, e.g. 07:00")
    quiet.add_argument("--off", action="store_true", help="remove quiet hours")
    quiet.set_defaults(run=_quiet_hours)

    remove = commands.add_parser("remove-contact", help="stop sending alerts to a contact")
    remove.add_argument("contact_id", help="the contact ID shown by 'contacts'")
    remove.set_defaults(run=_remove_contact)

    timing = commands.add_parser("alert-settings", help="waking hours and alert thresholds for a person")
    timing.add_argument("--person", required=True, help="the person ID shown by 'list'")
    timing.add_argument("--waking", help="waking hours, e.g. 08:00-21:00")
    timing.add_argument("--inactive-hours", type=int, help="hours without activity before alerting (1-12)")
    timing.add_argument("--silent-hours", type=int, help="hours without data before alerting (1-48)")
    timing.set_defaults(run=_alert_settings)

    commands.add_parser("setup-telegram", help="connect the Telegram bot to this service").set_defaults(
        run=_setup_telegram
    )

    member = commands.add_parser("add-member", help="let someone sign in to the web app and see a household")
    member.add_argument("--household", required=True, help="the household ID shown by 'list'")
    member.add_argument("--email", required=True, help="the address they sign in with")
    member.add_argument("--name", help='how they are shown, e.g. "Daughter" (default: the start of the email)')
    member.add_argument(
        "--role", choices=auth.ROLES, default="viewer", help="owner can change settings (default: viewer)"
    )
    member.set_defaults(run=_add_member)

    show_members = commands.add_parser("members", help="list who can see a household")
    show_members.add_argument("--household", required=True, help="the household ID shown by 'list'")
    show_members.set_defaults(run=_members)

    remove_member = commands.add_parser("remove-member", help="stop someone seeing a household")
    remove_member.add_argument("--household", required=True, help="the household ID shown by 'list'")
    remove_member.add_argument("--email", required=True, help="their sign-in address")
    remove_member.set_defaults(run=_remove_member)

    who = commands.add_parser("user", help="show a user's households, roles and the people they see")
    who.add_argument("--email", required=True, help="the user's sign-in address")
    who.set_defaults(run=_user)

    link = commands.add_parser("signin-link", help="print a one-time sign-in link (for testing)")
    link.add_argument("--email", required=True, help="the user's sign-in address")
    link.set_defaults(run=_signin_link)

    args = parser.parse_args()
    if args.command == "quiet-hours" and not args.off and not (args.start and args.end):
        parser.error("quiet-hours needs --from and --to, or --off")
    print(f"Database: {db.describe(db.get_engine())}")
    args.run(args)


if __name__ == "__main__":
    main()
