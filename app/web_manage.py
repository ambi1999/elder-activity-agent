"""The family and care web app, second half: managing a person and their household (step D2).

Every page here is about one person, found through the signed-in user's
memberships (app/access.py), so anyone else's pages answer 404. Members of the
household can look; only owners can change things. A viewer who submits a form
anyway gets 403, and pages hide the forms from viewers.

Pages (``{id}`` is the person):
    GET  /people/{id}/days                  today and the six days before it (story D-2)
    GET  /people/{id}/days/{yyyy-mm-dd}     one day by hour
    GET  /people/{id}/phones                phones, connected or waiting (stories C3-3, D-3)
    GET  /people/{id}/phones/add            name the phone;  POST  shows the setup QR code once
    GET  /people/{id}/phones/{phone}/status the page with the QR code asks whether the phone has connected
    POST /people/{id}/phones/{phone}/remove the phone's token stops working
    GET  /people/{id}/alert-times           waking hours and how long before alerting;  POST saves (story E-5)
    GET  /people/{id}/contacts              who gets alerts;  POST .../contacts/add, .../contacts/{c}/remove
    GET  /people/{id}/members               who can see the household;  POST .../members/invite,
                                            .../members/{user}/remove (story C3-4)
    GET  /people/add                        add a person (in a new household, or one you own);  POST
    GET  /profile                           your name as others see it;  POST saves
"""

import json
from datetime import date, time
from typing import Any

import segno
from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app import access, alerts, auth, contacts, db, devices, households, messages, overview, rules
from app.access import VisiblePerson
from app.brand import get_brand
from app.settings import get_settings
from app.web import go, not_found, parse_id, refused, render, same_site, session_for, utc_now

router = APIRouter()

# Timezones offered when adding a person; any other IANA name can be typed.
TIMEZONES = [
    "Australia/Brisbane",
    "Australia/Sydney",
    "Australia/Melbourne",
    "Australia/Hobart",
    "Australia/Adelaide",
    "Australia/Darwin",
    "Australia/Perth",
    "Pacific/Auckland",
    "Asia/Kolkata",
    "Europe/London",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _person(request: Request, person_id: str) -> tuple[auth.Session, VisiblePerson] | Response:
    """The signed-in user and the person a page is about, or the response to send instead.

    Returns a redirect to sign in, or the 404 page if the id is wrong or the
    person is outside the user's households (the same answer for both).
    """
    session = session_for(request)
    if session is None:
        return go("/signin")
    pid = parse_id(person_id)
    with db.get_engine().connect() as conn:
        person = access.person_for(conn, session.user.id, pid) if pid else None
    if person is None:
        return not_found(request, session)
    return session, person


def _form_refused(request: Request, session: auth.Session, person: VisiblePerson | None, csrf: str) -> Response | None:
    """Why a form must be refused, or None if it may go ahead.

    A form must come from this site with this session's CSRF token, and changes
    to a household need its owner (``person`` given), checked here on the server.
    """
    if not (same_site(request) and auth.csrf_matches(session, csrf)):
        return refused(request, session)
    if person is not None and not person.is_owner:
        return _owners_only(request, session, person)
    return None


def _owners_only(request: Request, session: auth.Session, person: VisiblePerson) -> Response:
    """The answer to a viewer trying to change something (403)."""
    body = {
        "title": "Owners only",
        "text": f"Only an owner of {person.household_name} can change this. Ask an owner to do it, "
        "or to make you an owner.",
    }
    return render(request, "message.html", body, session, status=403)


def _base(person: VisiblePerson, title: str, /, **values: Any) -> dict[str, Any]:
    """What every page about a person has: the person, its title, the People tab, Back to the person's day."""
    return {
        "person": person,
        "title": f"{person.display_name} · {title}",
        "tab": "people",
        "up": f"/people/{person.id}",
        **values,
    }


DONE = {
    "removed": "Removed.",
    "saved": "Saved.",
    "added": "Added. They'll get an email to confirm before alerts reach them.",
    "invited": "Invited. They'll get an email with a sign-in link.",
}


# ---------------------------------------------------------------------------
# Past days (story D-2)
# ---------------------------------------------------------------------------


@router.get("/people/{person_id}/days", response_class=HTMLResponse, include_in_schema=False)
def days_page(request: Request, person_id: str) -> Response:
    """Today and the six days before it: steps and active hours each day."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    now = utc_now()
    with db.get_engine().connect() as conn:
        days = overview.recent_days(conn, person, now)
    labelled = [(overview.day_label(d.day, now, person.timezone), d) for d in days]
    return render(request, "days.html", _base(person, "Past days", days=labelled), session)


@router.get("/people/{person_id}/days/{day}", response_class=HTMLResponse, include_in_schema=False)
def day_page(request: Request, person_id: str, day: str) -> Response:
    """One day: steps by hour, as a chart and a table."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    now = utc_now()
    try:
        wanted = date.fromisoformat(day)
    except ValueError:
        return not_found(request, session)
    age = (overview.today(now, person.timezone) - wanted).days
    if not 0 <= age < overview.DAYS_SHOWN:
        return not_found(request, session)  # only the days the app keeps
    with db.get_engine().connect() as conn:
        activity = overview.day_activity(conn, person, wanted)
    label = overview.day_label(wanted, now, person.timezone)
    context = _base(person, label, day=activity, label=label)
    context["up"] = f"/people/{person.id}/days"
    return render(request, "day.html", context, session)


# ---------------------------------------------------------------------------
# Phones (stories C3-3, D-3)
# ---------------------------------------------------------------------------


@router.get("/people/{person_id}/phones", response_class=HTMLResponse, include_in_schema=False)
def phones_page(request: Request, person_id: str, done: str = "") -> Response:
    """The person's phones: connected, or waiting for their first data."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    with db.get_engine().connect() as conn:
        phones = access.phones_for(conn, person.id)
    context = _base(person, "Phones", phones=phones, now=utc_now(), notice=DONE.get(done, ""))
    return render(request, "phones.html", context, session)


@router.get("/people/{person_id}/phones/add", response_class=HTMLResponse, include_in_schema=False)
def phone_add_page(request: Request, person_id: str) -> Response:
    """Name the new phone (owners only)."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    if not person.is_owner:
        return _owners_only(request, session, person)
    default = f"{person.display_name}'s phone"[: households.MAX_DEVICE_NAME]
    context = _base(person, "Add a phone", name=default, error="")
    context["up"] = f"/people/{person.id}/phones"
    return render(request, "phone_add.html", context, session)


@router.post("/people/{person_id}/phones/add", response_class=HTMLResponse, include_in_schema=False)
def phone_add(request: Request, person_id: str, csrf: str = Form(""), name: str = Form("")) -> Response:
    """Add a waiting phone and show its setup QR code, once.

    The QR code holds the phone's token, a secret. It is shown only in this
    response (never stored, never cached), and stops working after
    ``pairing.pending_token_expiry_minutes`` unless the phone connects.
    """
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    if (problem := _form_refused(request, session, person, csrf)) is not None:
        return problem
    settings, now = get_settings(), utc_now()
    try:
        with db.get_engine().begin() as conn:
            who = households.Person(person.id, person.household_id, person.display_name, person.timezone)
            phone = households.add_phone(conn, who, name.strip(), now, settings)
    except ValueError as err:
        context = _base(person, "Add a phone", name=name, error=str(err))
        context["up"] = f"/people/{person.id}/phones"
        return render(request, "phone_add.html", context, session, status=400)
    # Compact JSON keeps the code small enough to scan easily from a screen.
    contents = json.dumps(phone.provisioning, separators=(",", ":"))
    qr = segno.make(contents, error="m").svg_data_uri(scale=5, border=4)
    context = _base(
        person,
        "Connect the phone",
        phone=phone,
        qr=qr,
        minutes=settings.pairing.pending_token_expiry_minutes,
        expires=overview.when(phone.expires_at, person.timezone, now),
    )
    context["up"] = f"/people/{person.id}/phones"
    return render(request, "phone_qr.html", context, session)


@router.get("/people/{person_id}/phones/{phone_id}/status", include_in_schema=False)
def phone_status(request: Request, person_id: str, phone_id: str) -> Response:
    """Whether a new phone has connected: "pending", "active", "expired" or "removed" (for the QR page)."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return JSONResponse({"status": "unknown"}, status_code=404)
    _, person = found
    did = parse_id(phone_id)
    with db.get_engine().connect() as conn:
        phone = access.phone_for(conn, person.id, did) if did else None
    if phone is None:
        return JSONResponse({"status": "unknown"}, status_code=404)
    status = {"revoked": "removed"}.get(phone.status, phone.status)
    if status == "pending" and phone.pending_expires_at and phone.pending_expires_at <= utc_now():
        status = "expired"
    return JSONResponse({"status": status}, headers={"Cache-Control": "no-store"})


@router.post("/people/{person_id}/phones/{phone_id}/remove", include_in_schema=False)
def phone_remove(request: Request, person_id: str, phone_id: str, csrf: str = Form("")) -> Response:
    """Remove a phone: its token stops working at once; the data it sent stays."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    if (problem := _form_refused(request, session, person, csrf)) is not None:
        return problem
    did = parse_id(phone_id)
    with db.get_engine().begin() as conn:
        phone = access.phone_for(conn, person.id, did) if did else None
        if phone is None:
            return not_found(request, session)
        devices.revoke_device(conn, phone.id)
    return go(f"/people/{person.id}/phones?done=removed")


# ---------------------------------------------------------------------------
# Alert times (story E-5)
# ---------------------------------------------------------------------------


def _hhmm(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as err:
        raise ValueError("Enter times like 08:00.") from err


@router.get("/people/{person_id}/alert-times", response_class=HTMLResponse, include_in_schema=False)
def alert_times_page(request: Request, person_id: str, done: str = "") -> Response:
    """Waking hours and how long before each kind of alert."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    with db.get_engine().connect() as conn:
        timing = alerts.get_timing(conn, person.id, get_settings())
    context = _base(person, "Alert times", timing=timing, error="", notice=DONE.get(done, ""))
    return render(request, "alert_times.html", context, session)


@router.post("/people/{person_id}/alert-times", response_class=HTMLResponse, include_in_schema=False)
def alert_times_save(
    request: Request,
    person_id: str,
    csrf: str = Form(""),
    waking_from: str = Form(""),
    waking_to: str = Form(""),
    inactive_hours: str = Form(""),
    silent_hours: str = Form(""),
) -> Response:
    """Save the alert times (owners only)."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    if (problem := _form_refused(request, session, person, csrf)) is not None:
        return problem
    try:
        timing = rules.AlertTiming(_hhmm(waking_from), _hhmm(waking_to), int(inactive_hours), int(silent_hours))
        with db.get_engine().begin() as conn:
            alerts.set_timing(conn, person.id, timing)
    except ValueError as err:
        with db.get_engine().connect() as conn:
            current = alerts.get_timing(conn, person.id, get_settings())
        message = str(err) if "invalid literal" not in str(err) else "Choose a number of hours."
        context = _base(person, "Alert times", timing=current, error=message, notice="")
        return render(request, "alert_times.html", context, session, status=400)
    return go(f"/people/{person.id}/alert-times?done=saved")


# ---------------------------------------------------------------------------
# Contacts: who gets alerts (household-wide)
# ---------------------------------------------------------------------------


@router.get("/people/{person_id}/contacts", response_class=HTMLResponse, include_in_schema=False)
def contacts_page(request: Request, person_id: str, done: str = "") -> Response:
    """The household's alert contacts, and (for owners) a form to add one."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    with db.get_engine().connect() as conn:
        found_contacts = contacts.list_contacts(conn, person.household_id)
    context = _base(
        person,
        "Contacts",
        contacts=found_contacts,
        telegram=bool(get_settings().telegram.bot_username),
        error="",
        form={"name": "", "email": ""},
        notice=DONE.get(done, ""),
    )
    return render(request, "contacts.html", context, session)


@router.post("/people/{person_id}/contacts/add", response_class=HTMLResponse, include_in_schema=False)
def contact_add(
    request: Request,
    background: BackgroundTasks,
    person_id: str,
    csrf: str = Form(""),
    name: str = Form(""),
    channel: str = Form("email"),
    email: str = Form(""),
) -> Response:
    """Add a contact; they confirm by email link (or by pressing Start in Telegram) before getting alerts."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    if (problem := _form_refused(request, session, person, csrf)) is not None:
        return problem
    settings = get_settings()
    try:
        if not 1 <= len(name.strip()) <= 60:
            raise ValueError("Enter a name, up to 60 characters.")
        with db.get_engine().begin() as conn:
            new = contacts.add_contact(
                conn, person.household_id, name.strip(), channel, utc_now(), settings, email=email
            )
    except ValueError as err:
        with db.get_engine().connect() as conn:
            found_contacts = contacts.list_contacts(conn, person.household_id)
        context = _base(
            person,
            "Contacts",
            contacts=found_contacts,
            telegram=bool(settings.telegram.bot_username),
            error=str(err),
            form={"name": name, "email": email},
            notice="",
        )
        return render(request, "contacts.html", context, session, status=400)
    minutes = settings.alerts.link_expiry_minutes
    if new.contact.channel == "telegram":
        # The Telegram link is shown once, for the owner to send to the contact.
        context = _base(person, "Contacts", link=new.link, contact=new.contact, minutes=minutes)
        context["up"] = f"/people/{person.id}/contacts"
        return render(request, "contact_telegram.html", context, session)
    background.add_task(
        _send, new.contact.address or "", messages.confirm_email(new.contact.display_name, new.link, minutes)
    )
    return go(f"/people/{person.id}/contacts?done=added")


@router.post("/people/{person_id}/contacts/{contact_id}/remove", include_in_schema=False)
def contact_remove(request: Request, person_id: str, contact_id: str, csrf: str = Form("")) -> Response:
    """Remove a contact: they get no more alerts."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    if (problem := _form_refused(request, session, person, csrf)) is not None:
        return problem
    cid = parse_id(contact_id)
    with db.get_engine().begin() as conn:
        # Only a contact of this person's household; anything else is 404.
        mine = {c.id for c in contacts.list_contacts(conn, person.household_id)}
        if cid is None or cid not in mine:
            return not_found(request, session)
        contacts.remove_contact(conn, cid)
    return go(f"/people/{person.id}/contacts?done=removed")


def _send(address: str, message: messages.Message) -> None:
    """Send an email after the response (so the page doesn't wait for the email service)."""
    from app.web import get_notifiers  # looked up at send time, so tests can replace it

    get_notifiers()["email"].send(address, message)


# ---------------------------------------------------------------------------
# Members: who can see the household (story C3-4)
# ---------------------------------------------------------------------------


@router.get("/people/{person_id}/members", response_class=HTMLResponse, include_in_schema=False)
def members_page(request: Request, person_id: str, done: str = "") -> Response:
    """Who can see this household, and (for owners) inviting and removing."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    with db.get_engine().connect() as conn:
        members = auth.list_members(conn, person.household_id)
    context = _base(
        person,
        "Members",
        members=members,
        error="",
        form={"email": "", "name": "", "role": "viewer"},
        notice=DONE.get(done, ""),
        hours=get_settings().web.invite_link_hours,
    )
    return render(request, "members.html", context, session)


@router.post("/people/{person_id}/members/invite", response_class=HTMLResponse, include_in_schema=False)
def member_invite(
    request: Request,
    background: BackgroundTasks,
    person_id: str,
    csrf: str = Form(""),
    email: str = Form(""),
    name: str = Form(""),
    role: str = Form("viewer"),
) -> Response:
    """Invite someone: they become a member at once and get an email with a sign-in link."""
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    if (problem := _form_refused(request, session, person, csrf)) is not None:
        return problem
    settings, now = get_settings(), utc_now()
    try:
        address = auth.normalize_email(email)
        with db.get_engine().begin() as conn:
            user = auth.add_user(conn, address, name.strip() or address.split("@")[0])
            auth.add_member(conn, user.id, person.household_id, role)
            link = auth.create_signin_link(conn, user, now, settings, lifetime=settings.web.invite_link_expiry)
            people = [
                p.display_name
                for p in access.people_for(conn, session.user.id)
                if p.household_id == person.household_id
            ]
    except ValueError as err:
        with db.get_engine().connect() as conn:
            members = auth.list_members(conn, person.household_id)
        context = _base(
            person,
            "Members",
            members=members,
            error=str(err),
            form={"email": email, "name": name, "role": role},
            notice="",
            hours=settings.web.invite_link_hours,
        )
        return render(request, "members.html", context, session, status=400)
    message = messages.invitation(
        get_brand().product.name, session.user.display_name, " and ".join(people), link, settings.web.invite_link_hours
    )
    background.add_task(_send, user.email, message)
    return go(f"/people/{person.id}/members?done=invited")


@router.post("/people/{person_id}/members/{user_id}/remove", include_in_schema=False)
def member_remove(request: Request, person_id: str, user_id: str, csrf: str = Form("")) -> Response:
    """Remove a member: from their next page they can no longer see the household.

    Access is checked on every request (app/access.py), so removal works at once
    without ending their sessions. A household always keeps at least one owner.
    """
    found = _person(request, person_id)
    if isinstance(found, Response):
        return found
    session, person = found
    if (problem := _form_refused(request, session, person, csrf)) is not None:
        return problem
    uid = parse_id(user_id)
    with db.get_engine().begin() as conn:
        members = {m.user.id: m for m in auth.list_members(conn, person.household_id)}
        member = members.get(uid) if uid else None
        if member is None:
            return not_found(request, session)
        if member.role == "owner" and auth.owner_count(conn, person.household_id) == 1:
            body = {
                "title": "Can't remove",
                "text": "A household needs at least one owner. Make someone else an owner first.",
            }
            return render(request, "message.html", body, session, status=400)
        auth.remove_member(conn, member.user.id, person.household_id)
    if member.user.id == session.user.id:
        return go("/")  # they left; this household's pages are no longer theirs
    return go(f"/people/{person.id}/members?done=removed")


# ---------------------------------------------------------------------------
# Adding a person, and your profile
# ---------------------------------------------------------------------------


@router.get("/people/add", response_class=HTMLResponse, include_in_schema=False)
def person_add_page(request: Request) -> Response:
    """Add someone to look after: in a new household (you become its owner) or one you own."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    with db.get_engine().connect() as conn:
        owned = access.households_owned(conn, session.user.id)
    context = {
        "title": "Add a person",
        "tab": "settings",
        "up": "/settings",
        "owned": owned,
        "zones": TIMEZONES,
        "form": {"name": "", "timezone": TIMEZONES[0], "household": "new"},
        "error": "",
    }
    return render(request, "person_add.html", context, session)


@router.post("/people/add", response_class=HTMLResponse, include_in_schema=False)
def person_add(
    request: Request,
    csrf: str = Form(""),
    name: str = Form(""),
    timezone: str = Form(""),
    household: str = Form("new"),
) -> Response:
    """Create the person, and a household for them unless one of yours was chosen."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    if (problem := _form_refused(request, session, None, csrf)) is not None:
        return problem
    try:
        display_name = name.strip()
        if not 1 <= len(display_name) <= 60:
            raise ValueError("Enter a name, up to 60 characters. A first name or nickname is enough.")
        households.check_timezone(timezone.strip())
        with db.get_engine().begin() as conn:
            owned = {h.id for h in access.households_owned(conn, session.user.id)}
            if household == "new":
                new_household = households.create_household(conn, f"Household of {display_name}")
                auth.add_member(conn, session.user.id, new_household.id, "owner")
                household_id = new_household.id
            else:
                chosen = parse_id(household)
                if chosen is None or chosen not in owned:
                    raise ValueError("Choose one of your households.")
                household_id = chosen
            person = households.add_person(conn, household_id, display_name, timezone.strip())
    except ValueError as err:
        with db.get_engine().connect() as conn:
            owned_list = access.households_owned(conn, session.user.id)
        context = {
            "title": "Add a person",
            "tab": "settings",
            "up": "/settings",
            "owned": owned_list,
            "zones": TIMEZONES,
            "form": {"name": name, "timezone": timezone, "household": household},
            "error": str(err),
        }
        return render(request, "person_add.html", context, session, status=400)
    return go(f"/people/{person.id}")


@router.get("/profile", response_class=HTMLResponse, include_in_schema=False)
def profile_page(request: Request, done: str = "") -> Response:
    """Your name as others see it, and your sign-in address."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    context = {
        "title": "Profile",
        "tab": "settings",
        "up": "/settings",
        "name": session.user.display_name,
        "error": "",
        "notice": DONE.get(done, ""),
    }
    return render(request, "profile.html", context, session)


@router.post("/profile", response_class=HTMLResponse, include_in_schema=False)
def profile_save(request: Request, csrf: str = Form(""), name: str = Form("")) -> Response:
    """Change your name."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    if (problem := _form_refused(request, session, None, csrf)) is not None:
        return problem
    try:
        with db.get_engine().begin() as conn:
            auth.rename_user(conn, session.user.id, name)
    except ValueError as err:
        context = {
            "title": "Profile",
            "tab": "settings",
            "up": "/settings",
            "name": name,
            "error": str(err),
            "notice": "",
        }
        return render(request, "profile.html", context, session, status=400)
    return go("/profile?done=saved")
