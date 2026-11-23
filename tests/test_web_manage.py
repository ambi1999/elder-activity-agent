"""Managing a person in the web app: past days, phones, alert times, contacts, members, adding a person (step D2).

Owners can change things; viewers can look but get 403 on every change; anything
outside the user's households is 404.
"""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from alert_helpers import fakes
from sqlalchemy import text
from web_helpers import LINK, make_person, make_user, new_client, sign_in

from app import auth, contacts, web


@pytest.fixture
def notifiers(monkeypatch):
    fake = fakes()
    monkeypatch.setattr(web, "get_notifiers", lambda: fake)
    return fake


@pytest.fixture
def family(migrated_db):
    """Mum's household with Daughter (owner) and Son (viewer); Dad's household that neither can see."""
    household, mum, device = make_person(migrated_db, "Mum")
    _, dad, dad_device = make_person(migrated_db, "Dad")
    daughter = make_user(migrated_db, "daughter@example.com", "Daughter", [(household, "owner")])
    son = make_user(migrated_db, "son@example.com", "Son", [(household, "viewer")])
    return {
        "household": household,
        "mum": mum,
        "device": device,
        "dad": dad,
        "dad_device": dad_device,
        "daughter": daughter,
        "son": son,
    }


def signed_in(migrated_db, user):
    client = new_client()
    return client, sign_in(client, migrated_db, user)


# ---------- every page renders for members, and is 404 for others ----------


def test_every_page_renders_for_a_member(migrated_db, family):
    client, _ = signed_in(migrated_db, family["son"])
    mum = family["mum"]
    today = datetime.now(UTC).astimezone(ZoneInfo("Australia/Brisbane")).date()
    for path in [
        f"/people/{mum}/days",
        f"/people/{mum}/days/{today.isoformat()}",
        f"/people/{mum}/phones",
        f"/people/{mum}/alert-times",
        f"/people/{mum}/contacts",
        f"/people/{mum}/members",
        "/people/add",
        "/profile",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "no-store", path


def test_another_households_pages_are_not_found(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["daughter"])
    dad = family["dad"]
    for path in ["days", "phones", "alert-times", "contacts", "members", "phones/add"]:
        assert client.get(f"/people/{dad}/{path}").status_code == 404, path
    removed = client.post(f"/people/{dad}/phones/{family['dad_device']}/remove", data={"csrf": csrf})
    assert removed.status_code == 404
    # A phone of another household can't be reached through one's own person either.
    assert (
        client.post(f"/people/{family['mum']}/phones/{family['dad_device']}/remove", data={"csrf": csrf}).status_code
        == 404
    )
    with migrated_db.connect() as conn:
        assert (
            conn.execute(text("SELECT status FROM devices WHERE id = :id"), {"id": family["dad_device"]}).scalar()
            == "active"
        )


def test_only_the_days_kept_can_be_opened(migrated_db, family):
    client, _ = signed_in(migrated_db, family["daughter"])
    mum = family["mum"]
    long_ago = (datetime.now(UTC) - timedelta(days=30)).date().isoformat()
    assert client.get(f"/people/{mum}/days/{long_ago}").status_code == 404
    assert client.get(f"/people/{mum}/days/not-a-date").status_code == 404
    days = client.get(f"/people/{mum}/days").text
    assert days.count(f"/people/{mum}/days/") == 7
    assert "Today" in days and "Yesterday" in days


# ---------- viewers can't change anything ----------


def test_viewers_get_403_on_every_change(migrated_db, family, notifiers):
    client, csrf = signed_in(migrated_db, family["son"])
    mum = family["mum"]
    changes = {
        f"/people/{mum}/phones/add": {"name": "Spare phone"},
        f"/people/{mum}/phones/{family['device']}/remove": {},
        f"/people/{mum}/alert-times": {
            "waking_from": "07:00",
            "waking_to": "22:00",
            "inactive_hours": "3",
            "silent_hours": "6",
        },
        f"/people/{mum}/contacts/add": {"name": "Neighbour", "channel": "email", "email": "n@example.com"},
        f"/people/{mum}/members/invite": {"email": "x@example.com", "name": "X", "role": "owner"},
        f"/people/{mum}/members/{family['daughter'].id}/remove": {},
    }
    for path, data in changes.items():
        response = client.post(path, data={"csrf": csrf, **data})
        assert response.status_code == 403, path
        assert "Only an owner" in response.text
    assert client.get(f"/people/{mum}/phones/add").status_code == 403
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM devices WHERE person_id = :p"), {"p": mum}).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM alert_contacts")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM alert_settings")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM members")).scalar() == 2
    assert notifiers["email"].sent == []
    # Pages show viewers no forms.
    assert "/phones/add" not in client.get(f"/people/{mum}/phones").text
    assert '<form method="post" action="/people/' not in client.get(f"/people/{mum}/members").text


def test_changes_need_the_csrf_token(migrated_db, family):
    client, _ = signed_in(migrated_db, family["daughter"])
    response = client.post(f"/people/{family['mum']}/phones/add", data={"csrf": "wrong", "name": "Spare"})
    assert response.status_code == 403


# ---------- phones (stories C3-3, D-3) ----------


def test_adding_a_phone_shows_its_setup_code_once(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["daughter"])
    mum = family["mum"]
    page = client.post(f"/people/{mum}/phones/add", data={"csrf": csrf, "name": "Spare phone"})
    assert page.status_code == 200
    assert "data:image/svg+xml" in page.text
    assert page.headers["cache-control"] == "no-store"
    status_url = re.search(r'data-status="([^"]+)"', page.text).group(1)
    assert client.get(status_url).json() == {"status": "pending"}

    # Only a hash of the token is stored: the token on the page isn't in the database.
    token = re.search(r'<div class="label">Token</div><div class="mono">([^<]+)</div>', page.text).group(1)
    with migrated_db.connect() as conn:
        stored = conn.execute(text("SELECT token_hash FROM devices WHERE name = 'Spare phone'")).scalar()
    assert token not in stored

    phones = client.get(f"/people/{mum}/phones").text
    assert "Spare phone" in phones and "Waiting for the phone to connect" in phones
    assert "data:image/svg+xml" not in phones  # never shown again


def test_a_phone_name_is_required(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["daughter"])
    response = client.post(f"/people/{family['mum']}/phones/add", data={"csrf": csrf, "name": " "})
    assert response.status_code == 400
    assert 'aria-invalid="true"' in response.text


def test_the_setup_page_hears_when_the_code_expires(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["daughter"])
    page = client.post(f"/people/{family['mum']}/phones/add", data={"csrf": csrf, "name": "Spare phone"})
    status_url = re.search(r'data-status="([^"]+)"', page.text).group(1)
    with migrated_db.begin() as conn:
        conn.execute(
            text("UPDATE devices SET pending_expires_at = now() - interval '1 minute' WHERE name = 'Spare phone'")
        )
    assert client.get(status_url).json() == {"status": "expired"}


def test_removing_a_phone_stops_it(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["daughter"])
    mum, device = family["mum"], family["device"]
    response = client.post(f"/people/{mum}/phones/{device}/remove", data={"csrf": csrf})
    assert response.headers["location"] == f"/people/{mum}/phones?done=removed"
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT status FROM devices WHERE id = :id"), {"id": device}).scalar() == "revoked"
    assert client.get(f"/people/{mum}/phones/{device}/status").json() == {"status": "removed"}


# ---------- alert times (story E-5) ----------


def test_an_owner_changes_alert_times(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["daughter"])
    mum = family["mum"]
    data = {"csrf": csrf, "waking_from": "07:30", "waking_to": "21:30", "inactive_hours": "3", "silent_hours": "8"}
    response = client.post(f"/people/{mum}/alert-times", data=data)
    assert response.headers["location"] == f"/people/{mum}/alert-times?done=saved"
    with migrated_db.connect() as conn:
        row = conn.execute(
            text("SELECT waking_from, waking_to, inactive_hours, silent_hours FROM alert_settings")
        ).one()
    assert (row.waking_from.isoformat(), row.waking_to.isoformat(), row.inactive_hours, row.silent_hours) == (
        "07:30:00",
        "21:30:00",
        3,
        8,
    )
    page = client.get(f"/people/{mum}/alert-times?done=saved").text
    assert 'value="07:30"' in page and "Saved." in page


def test_wrong_alert_times_are_explained(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["daughter"])
    data = {"csrf": csrf, "waking_from": "22:00", "waking_to": "07:00", "inactive_hours": "3", "silent_hours": "8"}
    response = client.post(f"/people/{family['mum']}/alert-times", data=data)
    assert response.status_code == 400
    assert "must start before they end" in response.text
    bad_number = {**data, "waking_from": "07:00", "waking_to": "21:00", "inactive_hours": "lots"}
    assert client.post(f"/people/{family['mum']}/alert-times", data=bad_number).status_code == 400


# ---------- contacts ----------


def test_an_owner_adds_and_removes_a_contact(migrated_db, family, notifiers):
    client, csrf = signed_in(migrated_db, family["daughter"])
    mum = family["mum"]
    data = {"csrf": csrf, "name": "Neighbour", "channel": "email", "email": "Neighbour@Example.com"}
    response = client.post(f"/people/{mum}/contacts/add", data=data)
    assert response.headers["location"] == f"/people/{mum}/contacts?done=added"
    ((address, message),) = notifiers["email"].sent
    assert address == "neighbour@example.com"
    assert "/contacts/confirm/" in message.text
    page = client.get(f"/people/{mum}/contacts").text
    assert "Neighbour" in page and "waiting for them to confirm" in page

    with migrated_db.connect() as conn:
        (contact,) = contacts.list_contacts(conn, family["household"])
    assert client.post(f"/people/{mum}/contacts/{contact.id}/remove", data={"csrf": csrf}).status_code == 303
    with migrated_db.connect() as conn:
        assert contacts.list_contacts(conn, family["household"]) == []


def test_a_wrong_contact_address_is_explained(migrated_db, family, notifiers):
    client, csrf = signed_in(migrated_db, family["daughter"])
    data = {"csrf": csrf, "name": "Neighbour", "channel": "email", "email": "neighbour@"}
    response = client.post(f"/people/{family['mum']}/contacts/add", data=data)
    assert response.status_code == 400
    assert (
        "doesn&#39;t look like an email address" in response.text
        or "doesn't look like an email address" in response.text
    )
    assert notifiers["email"].sent == []


def test_another_households_contact_cant_be_removed(migrated_db, family):
    from alert_helpers import NOW, SETTINGS

    with migrated_db.begin() as conn:
        dad_household = conn.execute(
            text("SELECT household_id FROM people WHERE id = :id"), {"id": family["dad"]}
        ).scalar()
        other = contacts.add_contact(conn, dad_household, "Dad's friend", "email", NOW, SETTINGS, email="f@example.com")
    client, csrf = signed_in(migrated_db, family["daughter"])
    response = client.post(f"/people/{family['mum']}/contacts/{other.contact.id}/remove", data={"csrf": csrf})
    assert response.status_code == 404
    with migrated_db.connect() as conn:
        assert len(contacts.list_contacts(conn, dad_household)) == 1


# ---------- members (story C3-4) ----------


def test_an_owner_invites_someone_who_can_then_sign_in(migrated_db, family, notifiers):
    client, csrf = signed_in(migrated_db, family["daughter"])
    mum = family["mum"]
    data = {"csrf": csrf, "email": "Nurse@Example.com", "name": "Nurse", "role": "viewer"}
    response = client.post(f"/people/{mum}/members/invite", data=data)
    assert response.headers["location"] == f"/people/{mum}/members?done=invited"
    ((address, message),) = notifiers["email"].sent
    assert address == "nurse@example.com"
    assert message.subject.startswith("Daughter invited you")
    assert "72 hours" in message.text

    # The invitation's link signs the nurse in, and she sees Mum.
    path = f"/signin/link/{LINK.search(message.text).group(1)}"
    nurse_browser = new_client()
    assert nurse_browser.post(path).status_code == 303
    assert nurse_browser.get("/").headers["location"] == f"/people/{mum}"


def test_removing_a_member_ends_their_access_at_once(migrated_db, family):
    son_browser, _ = signed_in(migrated_db, family["son"])
    mum = family["mum"]
    assert son_browser.get(f"/people/{mum}").status_code == 200
    client, csrf = signed_in(migrated_db, family["daughter"])
    response = client.post(f"/people/{mum}/members/{family['son'].id}/remove", data={"csrf": csrf})
    assert response.headers["location"] == f"/people/{mum}/members?done=removed"
    assert son_browser.get(f"/people/{mum}").status_code == 404


def test_the_last_owner_cant_be_removed(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["daughter"])
    response = client.post(f"/people/{family['mum']}/members/{family['daughter'].id}/remove", data={"csrf": csrf})
    assert response.status_code == 400
    assert "at least one owner" in response.text


# ---------- adding a person, and the profile ----------


def test_adding_a_person_makes_a_household_you_own(migrated_db, family):
    nurse = make_user(migrated_db, "nurse@example.com", "Nurse", [])
    client, csrf = signed_in(migrated_db, nurse)
    response = client.post(
        "/people/add", data={"csrf": csrf, "name": "Grace", "timezone": "Australia/Sydney", "household": "new"}
    )
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert page.status_code == 200 and "Grace" in page.text
    with migrated_db.connect() as conn:
        role = conn.execute(
            text("""
            SELECT m.role FROM members m JOIN people p ON p.household_id = m.household_id
            WHERE p.display_name = 'Grace' AND m.user_id = :u
        """),
            {"u": nurse.id},
        ).scalar()
    assert role == "owner"


def test_a_person_can_only_be_added_to_a_household_you_own(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["son"])  # a viewer of Mum's household
    data = {"csrf": csrf, "name": "Uncle", "timezone": "Australia/Brisbane", "household": str(family["household"])}
    response = client.post("/people/add", data=data)
    assert response.status_code == 400
    assert "Choose one of your households" in response.text
    bad_zone = {**data, "household": "new", "timezone": "Mars/Olympus"}
    assert client.post("/people/add", data=bad_zone).status_code == 400


def test_changing_your_name(migrated_db, family):
    client, csrf = signed_in(migrated_db, family["son"])
    assert client.post("/profile", data={"csrf": csrf, "name": "  Sam "}).headers["location"] == "/profile?done=saved"
    with migrated_db.connect() as conn:
        assert auth.find_user(conn, "son@example.com").display_name == "Sam"
    assert client.post("/profile", data={"csrf": csrf, "name": ""}).status_code == 400
