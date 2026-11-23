"""HTTP routes for alerts (ADR 0026): the scheduled check, Telegram, and email links.

Routes:
    POST /jobs/check-alerts        run the alert check (needs JOBS_TOKEN; called every 5 minutes)
    POST /telegram/webhook         Telegram updates: /start links a chat, buttons acknowledge
    GET  /contacts/confirm/{token} page with a button to confirm an email contact
    POST /contacts/confirm/{token} confirms it
    GET  /a/{token}                page with an "I'm checking" button for an alert email
    POST /a/{token}                acknowledges the alert

Email links open a page with a button rather than acting straight away, because
email security scanners open links automatically; only a person presses the button.
"""

import hmac
import html
import logging
import os
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from app import alerts, contacts, db, messages, notifiers
from app.notifiers import Notifier, TelegramNotifier
from app.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_notifiers() -> dict[str, Notifier]:
    """The notifiers for this process, created once."""
    return notifiers.build(get_settings())


def _secret_matches(given: str | None, env_name: str) -> bool:
    """Constant-time check of a request's secret against an environment variable."""
    expected = os.getenv(env_name)
    if not expected:
        raise HTTPException(status_code=503, detail=f"{env_name} is not configured")
    return hmac.compare_digest((given or "").encode(), expected.encode())


# ---------------------------------------------------------------------------
# The scheduled check
# ---------------------------------------------------------------------------


@router.post("/jobs/check-alerts")
def check_alerts(authorization: str | None = Header(default=None)) -> dict[str, int]:
    """Run the alert rules for everyone. Safe to call repeatedly: open alerts aren't sent twice."""
    if not _secret_matches((authorization or "").removeprefix("Bearer ").strip(), "JOBS_TOKEN"):
        raise HTTPException(status_code=401, detail="Invalid or missing job token")
    totals = alerts.check_all(db.get_engine(), datetime.now(UTC), get_settings(), get_notifiers())
    log.info("check-alerts %s", totals)
    return totals


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)
) -> dict[str, bool]:
    """Handle an update from Telegram. Always 200 for genuine updates, so Telegram doesn't resend them."""
    if not _secret_matches(x_telegram_bot_api_secret_token, "TELEGRAM_WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Invalid secret")
    try:
        update = await request.json()
    except ValueError:
        return {"ok": True}
    if not isinstance(update, dict):
        return {"ok": True}
    await run_in_threadpool(_handle_update, update)
    return {"ok": True}


def _handle_update(update: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    telegram = get_notifiers()["telegram"]
    message = update.get("message") or {}
    callback = update.get("callback_query") or {}
    if isinstance(message, dict) and str(message.get("text", "")).startswith("/start"):
        chat_id = str((message.get("chat") or {}).get("id", ""))
        code = str(message.get("text", "")).removeprefix("/start").strip()
        with db.get_engine().begin() as conn:
            contact = contacts.confirm(conn, code, now, chat_id=chat_id) if code and chat_id else None
        reply = (
            messages.telegram_linked(contact.display_name)
            if contact
            else messages.Message("Link not valid", "This link has expired or was already used. Ask for a new one.")
        )
        if chat_id:
            telegram.send(chat_id, reply)
    elif isinstance(callback, dict) and str(callback.get("data", "")).startswith("ack:"):
        _acknowledge_from_button(callback, now, telegram)


def _acknowledge_from_button(callback: dict[str, Any], now: datetime, telegram: Notifier) -> None:
    """An "I'm checking" button: only a confirmed contact of the alert's household may press it."""
    chat_id = str(((callback.get("message") or {}).get("chat") or {}).get("id", ""))
    try:
        alert_id = uuid.UUID(str(callback["data"]).removeprefix("ack:"))
    except ValueError:
        return
    notice = "This alert can't be found."
    with db.get_engine().begin() as conn:
        found = alerts.find_alert(conn, alert_id)
        contact = contacts.find_telegram_contact(conn, found[1].household_id, chat_id) if found else None
        if found and contact:
            done = alerts.acknowledge(conn, alert_id, contact.display_name, now, get_settings(), get_notifiers())
            notice = "Thanks, the others have been told." if done else "Someone is already checking."
    if isinstance(telegram, TelegramNotifier) and callback.get("id"):
        telegram.answer_button(str(callback["id"]), notice)


# ---------------------------------------------------------------------------
# Email links: small pages with one button
# ---------------------------------------------------------------------------


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    """A minimal, accessible page (the full web app arrives in step D)."""
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem;line-height:1.5;
color:#1b2430}}
button{{font:inherit;font-weight:600;color:#fff;background:#0B1F3A;border:0;border-radius:12px;padding:.9rem 1.4rem;
min-height:48px;cursor:pointer}}button:focus-visible{{outline:3px solid #0A6B74;outline-offset:3px}}</style>
</head><body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>""",
        status_code=status,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


def _button(label: str) -> str:
    return f'<form method="post"><button type="submit">{html.escape(label)}</button></form>'


@router.get("/contacts/confirm/{token}", response_class=HTMLResponse)
def confirm_page(token: str) -> HTMLResponse:
    """Ask the person to press a button to confirm their email address."""
    return _page("Confirm your email", "<p>Press the button to start receiving alerts.</p>" + _button("Confirm"))


@router.post("/contacts/confirm/{token}", response_class=HTMLResponse)
def confirm_email(token: str) -> HTMLResponse:
    """Confirm an email contact from its one-time link."""
    with db.get_engine().begin() as conn:
        contact = contacts.confirm(conn, token, datetime.now(UTC))
    if contact is None:
        return _page("Link not valid", "<p>This link has expired or was already used. Ask for a new one.</p>", 404)
    return _page(
        "Email confirmed", f"<p>Thanks {html.escape(contact.display_name)}: alerts will now be emailed to you.</p>"
    )


@router.get("/a/{token}", response_class=HTMLResponse)
def acknowledge_page(token: str) -> HTMLResponse:
    """Show the alert and an "I'm checking" button."""
    with db.get_engine().connect() as conn:
        found = alerts.alert_for_ack_token(conn, token)
    if found is None:
        return _page("Link not valid", "<p>This link isn't valid.</p>", 404)
    alert, person, _ = found
    if alert.status != "open":
        state = "Someone is already checking." if alert.status == "acknowledged" else "This alert is closed."
        return _page(f"Alert about {person.display_name}", f"<p>{state}</p>")
    body = f"<p>{html.escape(alert.explanation)}</p>" + _button("I'm checking")
    return _page(f"Alert about {person.display_name}", body)


@router.post("/a/{token}", response_class=HTMLResponse)
def acknowledge_alert(token: str) -> HTMLResponse:
    """Acknowledge the alert behind an email's "I'm checking" link (story E-3)."""
    now = datetime.now(UTC)
    with db.get_engine().begin() as conn:
        found = alerts.alert_for_ack_token(conn, token)
        if found is None:
            return _page("Link not valid", "<p>This link isn't valid.</p>", 404)
        alert, _, name = found
        done = alerts.acknowledge(conn, alert.id, name, now, get_settings(), get_notifiers())
    if done:
        return _page("Thank you", "<p>The others have been told you're checking.</p>")
    return _page("Already in hand", "<p>Someone is already checking, or the alert has closed.</p>")
