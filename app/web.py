"""The family and care web app's pages (ADR 0025, ADR 0028; step D1).

Server-rendered HTML (Jinja2 templates in app/templates/), plain forms, and one
small script (app/static/app.js) for the account menu and for refreshing the
care overview. Everything works without JavaScript too.

Pages:
    GET  /                      where to start: sign in, the overview, or the only person's day
    GET  /signin                email address form;  POST /signin  emails a one-time link
    GET  /signin/link/{token}   "Sign in" button;    POST          uses the link, sets the session cookie
    POST /signout               ends the session
    GET  /people                care overview: everyone, needs attention first (story D-5)
    GET  /people/list           just the overview's list, for refreshing it in place
    GET  /people/{id}           a person's day (story D-1)
    GET  /alerts                open and recent alerts
    GET  /alerts/{id}           one alert;           POST /alerts/{id}/ack  "I'm checking" (story E-3)
    GET  /settings, /help, /about
    GET  /manifest.webmanifest, /brand/tokens.css   installable app and brand colours (story D-4)

Security, in short (ADR 0025): pages about a person or alert are found only
through the user's memberships (app/access.py), so anything else is 404; the
session cookie is ``__Host-``, Secure, HttpOnly and SameSite=Lax; every form
sends a CSRF token and must come from this site; pages have a strict Content
Security Policy and are never cached.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import access, alerts, auth, db, messages, overview, rate_limit, rules
from app.alert_routes import get_notifiers
from app.brand import get_brand, tokens_css
from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
# Words for times, available in every template: when(moment, timezone, now) and ago(moment, now).
TEMPLATES.env.globals.update(when=overview.when, ago=overview.ago)
COOKIE = "__Host-session"  # __Host-: only this exact site, only over HTTPS, path "/"
RECENT = timedelta(days=7)  # closed alerts shown under "Recent"
VERSION = "0.6.0"

# Only this site's own files may load; no inline scripts or styles, no framing.
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
    "manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """The current time, in UTC."""
    return datetime.now(UTC)


def session_for(request: Request) -> auth.Session | None:
    """The signed-in user for this request's cookie, or None."""
    session_id = request.cookies.get(COOKIE, "")
    if not session_id:
        return None
    with db.get_engine().connect() as conn:
        return auth.find_session(conn, session_id, utc_now())


def same_site(request: Request) -> bool:
    """Whether a form was submitted from this site (the Origin header, when the browser sends one)."""
    origin = request.headers.get("origin")
    if origin is None:
        return True  # older browsers; the CSRF token still protects signed-in forms
    return urlsplit(origin).netloc == request.headers.get("host", "")


def client_ip(request: Request) -> str:
    """The visitor's network address, for rate limits.

    Render's proxy adds the real address as the last entry of X-Forwarded-For;
    earlier entries could be made up by the visitor, so they are ignored.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def parse_id(value: str) -> uuid.UUID | None:
    """An id from a URL, or None if it isn't one (the page then answers 404)."""
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def render(
    request: Request,
    template: str,
    context: dict[str, Any],
    session: auth.Session | None = None,
    status: int = 200,
) -> HTMLResponse:
    """Render a page with what every page needs, and the security headers.

    Args:
        request: The request (templates need it for URLs).
        template: File in app/templates/.
        context: The page's own values, e.g. its ``title``, ``tab`` and ``up`` (the Back link).
        session: The signed-in user; None for sign-in pages, which have no menus.
        status: HTTP status code.
    """
    open_alerts = 0
    if session is not None:
        with db.get_engine().connect() as conn:
            open_alerts = access.open_alert_count(conn, session.user.id)
    values = {
        "brand": get_brand(),
        "session": session,
        "me": session.user if session else None,
        "csrf": session.csrf_token if session else "",
        "open_alerts": open_alerts,
        "tab": None,
        "up": None,
        **context,
    }
    response = TEMPLATES.TemplateResponse(request, template, values, status_code=status)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    # Browsers remember to use HTTPS for a year (ignored on http://localhost).
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    # Pages show private information: never keep a copy in caches or the browser's history cache.
    response.headers["Cache-Control"] = "no-store"
    return response


def not_found(request: Request, session: auth.Session | None) -> HTMLResponse:
    """The same answer for "doesn't exist" and "not yours" (story C3-5)."""
    return render(request, "not_found.html", {"title": "Not found"}, session, status=404)


def refused(request: Request, session: auth.Session | None) -> HTMLResponse:
    """A form that didn't come from this site, or whose CSRF token is wrong or old."""
    body = {"title": "Please try again", "text": "This form had expired. Go back, reload the page and try again."}
    return render(request, "message.html", body, session, status=403)


def go(url: str) -> RedirectResponse:
    """Go to another page after a form (303, so the browser fetches it with GET)."""
    return RedirectResponse(url, status_code=303)


# ---------------------------------------------------------------------------
# Start and sign-in (story C3-1)
# ---------------------------------------------------------------------------


@router.get("/", include_in_schema=False)
def start(request: Request) -> Response:
    """Send the visitor to the right first page."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    with db.get_engine().connect() as conn:
        people = access.people_for(conn, session.user.id)
    # Someone looking after one person goes straight to that person's day (ADR 0028).
    return go(f"/people/{people[0].id}" if len(people) == 1 else "/people")


@router.get("/signin", response_class=HTMLResponse, include_in_schema=False)
def signin_page(request: Request, out: int = 0) -> Response:
    """The sign-in form."""
    if session_for(request) is not None:
        return go("/")
    notice = "You're signed out." if out else ""
    return render(request, "signin.html", {"title": "Sign in", "notice": notice, "email": "", "error": ""})


@router.post("/signin", response_class=HTMLResponse, include_in_schema=False)
def signin_submit(request: Request, background: BackgroundTasks, email: str = Form("")) -> Response:
    """Email a one-time link if the address has an account; the answer is the same either way."""
    if not same_site(request):
        return refused(request, None)
    try:
        address = auth.normalize_email(email)
    except ValueError as err:
        context = {"title": "Sign in", "notice": "", "email": email, "error": str(err)}
        return render(request, "signin.html", context, status=400)

    settings, now = get_settings(), utc_now()
    if rate_limit.signin_by_ip.check(client_ip(request), settings.web.signin_requests_per_hour_per_ip, now):
        body = {"title": "Too many tries", "text": "Too many sign-in requests from this network. Try again later."}
        return render(request, "message.html", body, status=429)

    # Over the per-address limit, the page looks the same but no email is sent,
    # so nobody can flood someone's inbox by typing their address.
    if rate_limit.signin_by_email.check(address, settings.web.signin_emails_per_hour, now) is None:
        with db.get_engine().begin() as conn:
            user = auth.find_user(conn, address)
            link = auth.create_signin_link(conn, user, now, settings) if user else None
        if link:
            # Sent after the response, so known and unknown addresses take the same time to answer.
            background.add_task(_send_signin_email, address, link)
    sent = {"title": "Check your email", "email": address, "minutes": settings.web.signin_link_minutes}
    return render(request, "signin_sent.html", sent)


def _send_signin_email(address: str, link: str) -> None:
    message = messages.signin_link(get_brand().product.name, link, get_settings().web.signin_link_minutes)
    if not get_notifiers()["email"].send(address, message):
        log.warning("Sign-in email could not be sent")


@router.get("/signin/link/{token}", response_class=HTMLResponse, include_in_schema=False)
def signin_link_page(request: Request, token: str) -> Response:
    """A page with a "Sign in" button: opening the link alone doesn't sign in (email scanners open links)."""
    with db.get_engine().connect() as conn:
        valid = auth.signin_link_is_valid(conn, token, utc_now())
    if not valid:
        return render(request, "signin_invalid.html", {"title": "Link not valid"}, status=404)
    return render(request, "signin_link.html", {"title": "Sign in"})


@router.post("/signin/link/{token}", response_class=HTMLResponse, include_in_schema=False)
def signin_link_use(request: Request, token: str) -> Response:
    """Use the link, start a session and set its cookie."""
    if not same_site(request):
        return refused(request, None)
    settings, now = get_settings(), utc_now()
    with db.get_engine().begin() as conn:
        user = auth.use_signin_link(conn, token, now)
        session_id = auth.create_session(conn, user.id, now, settings) if user else None
    if session_id is None:
        return render(request, "signin_invalid.html", {"title": "Link not valid"}, status=404)
    response = go("/")
    response.set_cookie(
        COOKIE,
        session_id,
        max_age=int(settings.web.session_length.total_seconds()),
        path="/",
        secure=True,
        httponly=True,  # scripts can't read it
        samesite="lax",  # not sent with forms posted from other sites
    )
    return response


@router.post("/signout", include_in_schema=False)
def signout(request: Request, csrf: str = Form("")) -> Response:
    """Sign this browser out."""
    session = session_for(request)
    if session is not None:
        if not (same_site(request) and auth.csrf_matches(session, csrf)):
            return refused(request, session)
        with db.get_engine().begin() as conn:
            auth.end_session(conn, request.cookies.get(COOKIE, ""))
    response = go("/signin?out=1")
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# People (stories D-5 and D-1)
# ---------------------------------------------------------------------------


def _statuses(session: auth.Session) -> list[overview.Status]:
    now = utc_now()
    with db.get_engine().connect() as conn:
        people = access.people_for(conn, session.user.id)
        all_alerts = access.alerts_for(conn, session.user.id, now - RECENT)
        return overview.overview(conn, people, all_alerts, now, get_settings(), session.user.display_name)


@router.get("/people", response_class=HTMLResponse, include_in_schema=False)
def people_page(request: Request) -> Response:
    """The care overview: who needs attention first."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    statuses = _statuses(session)
    if len(statuses) == 1:
        return go(f"/people/{statuses[0].person.id}")
    context = {
        "title": f"My people · {len(statuses)}" if statuses else "My people",
        "tab": "people",
        "statuses": statuses,
        "counts": overview.counts(statuses),
        "refresh": get_settings().web.overview_refresh_seconds,
    }
    return render(request, "overview.html", context, session)


@router.get("/people/list", response_class=HTMLResponse, include_in_schema=False)
def people_list(request: Request) -> Response:
    """Just the overview's list, which the page's script swaps in to refresh it."""
    session = session_for(request)
    if session is None:
        return Response(status_code=401)
    statuses = _statuses(session)
    context = {"statuses": statuses, "counts": overview.counts(statuses)}
    return render(request, "_overview_list.html", context, session)


@router.get("/people/{person_id}", response_class=HTMLResponse, include_in_schema=False)
def person_page(request: Request, person_id: str) -> Response:
    """A person's day: their status, today's numbers, activity by hour, the phone (story D-1)."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    pid, now = parse_id(person_id), utc_now()
    with db.get_engine().connect() as conn:
        person = access.person_for(conn, session.user.id, pid) if pid else None
        if person is None:
            return not_found(request, session)
        unresolved = [a for a in access.alerts_for(conn, session.user.id, now, person.id) if a.status != "resolved"]
        status = overview.person_status(conn, person, unresolved, now, get_settings(), session.user.display_name)
        day = overview.day_activity(conn, person, overview.today(now, person.timezone))
        only_one = len(access.people_for(conn, session.user.id)) == 1
    data_age = now - status.last_data_at if status.last_data_at else None
    context = {
        "title": f"{person.display_name} · Today",
        "tab": "people",
        "up": None if only_one else "/people",
        "person": person,
        "status": status,
        "day": day,
        "last_active": (
            overview.when(status.last_activity_at, person.timezone, now) if status.last_activity_at else None
        ),
        "last_data": overview.ago(status.last_data_at, now) if status.last_data_at else None,
        "data_stale": data_age is not None and data_age > overview.STALE_DATA,
    }
    return render(request, "person.html", context, session)


# ---------------------------------------------------------------------------
# Alerts (story E-3)
# ---------------------------------------------------------------------------


@router.get("/alerts", response_class=HTMLResponse, include_in_schema=False)
def alerts_page(request: Request) -> Response:
    """Open alerts, then those closed in the last week."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    now = utc_now()
    with db.get_engine().connect() as conn:
        found = access.alerts_for(conn, session.user.id, now - RECENT)
    context = {
        "title": "Alerts",
        "tab": "alerts",
        "open": [a for a in found if a.status != "resolved"],
        "closed": [a for a in found if a.status == "resolved"],
        "now": now,
    }
    return render(request, "alerts.html", context, session)


@router.get("/alerts/{alert_id}", response_class=HTMLResponse, include_in_schema=False)
def alert_page(request: Request, alert_id: str, done: str = "") -> Response:
    """One alert: what the rule saw, the explanation, and "I'm checking"."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    aid, now = parse_id(alert_id), utc_now()
    with db.get_engine().connect() as conn:
        alert = access.alert_for(conn, session.user.id, aid) if aid else None
        if alert is None:
            return not_found(request, session)
        timing = alerts.get_timing(conn, alert.person.id, get_settings())
    hours = timing.inactive_hours if alert.rule == rules.INACTIVITY else timing.silent_hours
    notices = {"ack": "Thanks. Everyone has been told you're checking.", "already": "Someone is already checking."}
    context = {
        "title": "Alert",
        "tab": "alerts",
        "up": "/alerts",
        "alert": alert,
        "headline": messages.headline(alert.rule, alert.person.display_name, hours),
        "now": now,
        "notice": notices.get(done, ""),
    }
    return render(request, "alert.html", context, session)


@router.post("/alerts/{alert_id}/ack", include_in_schema=False)
def acknowledge(request: Request, alert_id: str, csrf: str = Form("")) -> Response:
    """Say "I'm checking": tell every contact who is checking, and stop the repeats."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    if not (same_site(request) and auth.csrf_matches(session, csrf)):
        return refused(request, session)
    aid = parse_id(alert_id)
    with db.get_engine().begin() as conn:
        alert = access.alert_for(conn, session.user.id, aid) if aid else None
        if alert is None:
            return not_found(request, session)
        done = alerts.acknowledge(conn, alert.id, session.user.display_name, utc_now(), get_settings(), get_notifiers())
    return go(f"/alerts/{alert.id}?done={'ack' if done else 'already'}")


# ---------------------------------------------------------------------------
# Settings, help, about (more settings arrive in step D2)
# ---------------------------------------------------------------------------


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request) -> Response:
    """The signed-in user, the people they look after, help, and Sign out."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    with db.get_engine().connect() as conn:
        people = access.people_for(conn, session.user.id)
    return render(request, "settings.html", {"title": "Settings", "tab": "settings", "people": people}, session)


@router.get("/help", response_class=HTMLResponse, include_in_schema=False)
def help_page(request: Request) -> Response:
    """What the colours mean, and what this app is not."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    return render(request, "help.html", {"title": "Help", "tab": "settings", "up": "/settings"}, session)


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def about_page(request: Request) -> Response:
    """The app, its version, who makes it, and what the phone shares."""
    session = session_for(request)
    if session is None:
        return go("/signin")
    context = {"title": "About", "tab": "settings", "up": "/settings", "version": VERSION}
    return render(request, "about.html", context, session)


# ---------------------------------------------------------------------------
# Installable app and brand colours (stories C3-6, D-4)
# ---------------------------------------------------------------------------


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> JSONResponse:
    """The Web App Manifest, from the brand, so the app can be added to a phone's home screen."""
    brand = get_brand()
    body = {
        "name": brand.product.name,
        "short_name": brand.product.name,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#F6F8FB",
        "theme_color": brand.colours.primary,
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    return JSONResponse(body, media_type="application/manifest+json")


@router.get("/brand/tokens.css", include_in_schema=False)
def brand_tokens() -> Response:
    """The brand's colours as CSS custom properties (generated from config/brand.toml)."""
    return Response(tokens_css(get_brand()), media_type="text/css", headers={"Cache-Control": "public, max-age=3600"})
