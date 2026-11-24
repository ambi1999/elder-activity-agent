"""Signing in to the web app by email link, sessions, signing out and form protection (story C3-1, ADR 0025).

Verifies: EA-FR-AUTH-001, EA-FR-AUTH-002, EA-FR-AUTH-003, EA-FR-AUTH-004, EA-FR-AUTH-005,
    EA-FR-AUTH-006, EA-FR-AUTH-007, EA-FR-AUTH-008, EA-NFR-SEC-003
"""

from datetime import UTC, datetime, timedelta

import pytest
from alert_helpers import fakes
from sqlalchemy import text
from web_helpers import LINK, add_alert, make_person, make_user, new_client, sign_in

from app import auth, web
from app.settings import get_settings


@pytest.fixture
def notifiers(monkeypatch):
    fake = fakes()
    monkeypatch.setattr(web, "get_notifiers", lambda: fake)
    return fake


@pytest.fixture
def daughter(migrated_db):
    household_id, person_id, _ = make_person(migrated_db, "Mum")
    user = make_user(migrated_db, "Daughter@Example.com", "Daughter", [(household_id, "owner")])
    return user, person_id


def emailed_link(notifiers) -> str:
    """The path of the sign-in link in the last email sent."""
    _, message = notifiers["email"].sent[-1]
    match = LINK.search(message.text)
    assert match, message.text
    return f"/signin/link/{match.group(1)}"


# ---------- requesting a link ----------


def test_signed_out_visitors_go_to_sign_in(migrated_db):
    client = new_client()
    for path in ["/", "/people", "/alerts", "/settings", "/help", "/about"]:
        response = client.get(path)
        assert response.status_code == 303, path
        assert response.headers["location"] == "/signin"


def test_sign_in_page_has_a_form_and_security_headers(migrated_db):
    response = new_client().get("/signin")
    assert response.status_code == 200
    assert '<form method="post" action="/signin"' in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_known_address_gets_a_link_by_email(daughter, notifiers):
    response = new_client().post("/signin", data={"email": " daughter@example.COM "})
    assert response.status_code == 200
    assert "daughter@example.com" in response.text
    (address, message), *_ = notifiers["email"].sent
    assert address == "daughter@example.com"
    assert "works once" in message.text
    assert LINK.search(message.text)


def test_unknown_address_gets_the_same_page_and_no_email(daughter, notifiers):
    client = new_client()
    known = client.post("/signin", data={"email": "daughter@example.com"}).text
    unknown = client.post("/signin", data={"email": "stranger@example.com"}).text
    assert unknown == known.replace("daughter@example.com", "stranger@example.com")
    assert [a for a, _ in notifiers["email"].sent] == ["daughter@example.com"]


def test_a_wrong_address_is_explained(migrated_db, notifiers):
    response = new_client().post("/signin", data={"email": "daughter@"})
    assert response.status_code == 400
    assert "Enter an email address" in response.text
    assert 'aria-invalid="true"' in response.text


def test_one_address_gets_a_limited_number_of_emails(daughter, notifiers):
    client = new_client()
    limit = get_settings().web.signin_emails_per_hour
    for _ in range(limit + 2):
        assert client.post("/signin", data={"email": "daughter@example.com"}).status_code == 200
    assert len(notifiers["email"].sent) == limit


def test_one_network_gets_a_limited_number_of_requests(migrated_db, notifiers):
    client = new_client()
    limit = get_settings().web.signin_requests_per_hour_per_ip
    for i in range(limit):
        assert client.post("/signin", data={"email": f"person{i}@example.com"}).status_code == 200
    assert client.post("/signin", data={"email": "one-more@example.com"}).status_code == 429


def test_forms_from_other_sites_are_refused(daughter, notifiers):
    response = new_client().post(
        "/signin", data={"email": "daughter@example.com"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert notifiers["email"].sent == []


# ---------- using a link ----------


def test_a_link_signs_in_once(daughter, notifiers):
    user, person_id = daughter
    client = new_client()
    client.post("/signin", data={"email": "daughter@example.com"})
    path = emailed_link(notifiers)

    # Opening the link only shows a button (email scanners open links); it doesn't use the link.
    assert "Sign in" in client.get(path).text
    assert client.get(path).status_code == 200

    response = client.post(path)
    assert response.status_code == 303
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{web.COOKIE}=")
    for flag in ("Secure", "HttpOnly", "SameSite=lax", "Path=/"):
        assert flag.lower() in cookie.lower()

    # Signed in: the only person's day is the start page (ADR 0028).
    assert client.get("/").headers["location"] == f"/people/{person_id}"
    assert client.get(f"/people/{person_id}").status_code == 200

    # The same link can't be used again, even by someone else.
    again = new_client().post(path)
    assert again.status_code == 404
    assert "expired or was already used" in again.text
    assert new_client().get(path).status_code == 404


def test_an_expired_link_is_refused(daughter, migrated_db):
    user, _ = daughter
    with migrated_db.begin() as conn:
        link = auth.create_signin_link(conn, user, datetime.now(UTC) - timedelta(hours=1), get_settings())
    path = link[link.index("/signin/link/") :]
    assert new_client().get(path).status_code == 404
    assert new_client().post(path).status_code == 404


def test_an_unknown_link_is_refused(migrated_db):
    assert new_client().post("/signin/link/not-a-real-token").status_code == 404


# ---------- sessions ----------


def test_signing_out_ends_the_session(daughter, migrated_db):
    user, person_id = daughter
    client = new_client()
    csrf = sign_in(client, migrated_db, user)
    session_id = client.cookies.get(web.COOKIE)
    response = client.post("/signout", data={"csrf": csrf})
    assert response.status_code == 303
    assert response.headers["location"] == "/signin?out=1"
    # Even if someone replayed the old cookie, its session is gone.
    replay = new_client()
    replay.cookies.set(web.COOKIE, session_id)
    assert replay.get(f"/people/{person_id}").headers["location"] == "/signin"


def test_an_expired_session_signs_out(daughter, migrated_db):
    user, person_id = daughter
    client = new_client()
    sign_in(client, migrated_db, user)
    with migrated_db.begin() as conn:
        conn.execute(text("UPDATE sessions SET expires_at = now() - interval '1 minute'"))
    assert client.get(f"/people/{person_id}").headers["location"] == "/signin"


def test_sign_out_needs_the_csrf_token(daughter, migrated_db):
    user, person_id = daughter
    client = new_client()
    sign_in(client, migrated_db, user)
    assert client.post("/signout", data={"csrf": "wrong"}).status_code == 403
    assert client.get(f"/people/{person_id}").status_code == 200  # still signed in


def test_acknowledging_needs_the_csrf_token_and_this_site(daughter, notifiers, migrated_db):
    user, person_id = daughter
    alert_id = add_alert(migrated_db, person_id)
    client = new_client()
    csrf = sign_in(client, migrated_db, user)
    assert client.post(f"/alerts/{alert_id}/ack", data={"csrf": "wrong"}).status_code == 403
    other_site = client.post(f"/alerts/{alert_id}/ack", data={"csrf": csrf}, headers={"Origin": "https://evil.example"})
    assert other_site.status_code == 403
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT status FROM alerts WHERE id = :id"), {"id": alert_id}).scalar() == "open"
