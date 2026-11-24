"""Who sees what in the web app: the set of people, the overview, person pages and alerts (ADR 0028, C3-5, D-5, E-3).

Verifies: EA-FR-ACC-001, EA-FR-ACC-002, EA-FR-VIEW-001, EA-FR-VIEW-002, EA-FR-VIEW-003,
    EA-FR-VIEW-004, EA-FR-VIEW-005, EA-FR-VIEW-006, EA-FR-VIEW-007, EA-FR-VIEW-009, EA-FR-ALR-005,
    EA-FR-BRD-003, EA-NFR-SEC-003
"""

import pytest
from alert_helpers import fakes
from web_helpers import add_alert, alert_status, make_person, make_user, new_client, sign_in

from app import web


@pytest.fixture
def notifiers(monkeypatch):
    fake = fakes()
    monkeypatch.setattr(web, "get_notifiers", lambda: fake)
    return fake


@pytest.fixture
def two_families(migrated_db):
    """Mum's household (Daughter is a member) and Dad's household (Daughter isn't), each with an open alert."""
    mum_household, mum, _ = make_person(migrated_db, "Mum")
    dad_household, dad, _ = make_person(migrated_db, "Dad")
    daughter = make_user(migrated_db, "daughter@example.com", "Daughter", [(mum_household, "viewer")])
    return {
        "daughter": daughter,
        "mum": mum,
        "dad": dad,
        "mum_alert": add_alert(migrated_db, mum),
        "dad_alert": add_alert(migrated_db, dad),
        "households": (mum_household, dad_household),
    }


# ---------- isolation (story C3-5) ----------


def test_other_households_pages_are_not_found(migrated_db, two_families, notifiers):
    f = two_families
    client = new_client()
    csrf = sign_in(client, migrated_db, f["daughter"])
    for path in [f"/people/{f['dad']}", f"/alerts/{f['dad_alert']}"]:
        response = client.get(path)
        assert response.status_code == 404, path
        assert "Dad" not in response.text
    # Acknowledging someone else's alert is refused, and changes nothing.
    assert client.post(f"/alerts/{f['dad_alert']}/ack", data={"csrf": csrf}).status_code == 404
    assert alert_status(migrated_db, f["dad_alert"]) == ("open", None)
    assert notifiers["email"].sent == []


def test_lists_show_only_the_users_people(migrated_db, two_families):
    f = two_families
    client = new_client()
    sign_in(client, migrated_db, f["daughter"])
    for path in ["/alerts", "/settings", "/people/list"]:
        page = client.get(path)
        assert page.status_code == 200, path
        assert "Dad" not in page.text, path
    assert "Mum" in client.get("/alerts").text


def test_malformed_ids_are_not_found(migrated_db, two_families):
    client = new_client()
    sign_in(client, migrated_db, two_families["daughter"])
    assert client.get("/people/not-an-id").status_code == 404
    assert client.get("/alerts/123").status_code == 404


# ---------- one person or many (ADR 0028) ----------


def test_one_person_goes_straight_to_their_day(migrated_db, two_families):
    f = two_families
    client = new_client()
    sign_in(client, migrated_db, f["daughter"])
    assert client.get("/").headers["location"] == f"/people/{f['mum']}"
    assert client.get("/people").headers["location"] == f"/people/{f['mum']}"
    page = client.get(f"/people/{f['mum']}")
    assert page.status_code == 200
    assert 'aria-label="Back"' not in page.text  # nothing to go back to


def test_a_nurse_sees_everyone_needs_attention_first(migrated_db, notifiers):
    households, people = [], {}
    for name in ["Ahmed", "Rosa", "Margaret", "Tom"]:
        household, person, _ = make_person(migrated_db, name, phone=name != "Tom")
        households.append(household)
        people[name] = person
    add_alert(migrated_db, people["Margaret"], hours_ago=5)
    add_alert(migrated_db, people["Rosa"], rule="phone_silent", hours_ago=8)
    nurse = make_user(migrated_db, "nurse@example.com", "Nurse", [(h, "viewer") for h in households])
    client = new_client()
    sign_in(client, migrated_db, nurse)

    assert client.get("/").headers["location"] == "/people"
    page = client.get("/people").text
    assert "My people · 4" in page
    # Needs attention (red), then phone not sending (amber), then all OK, then no phone.
    order = [page.index(name) for name in ["Margaret", "Rosa", "Ahmed", "Tom"]]
    assert order == sorted(order)
    for words in ["1 need attention", "1 phone not sending", "1 all OK", "1 no phone yet"]:
        assert words in page
    assert 'data-refresh="' in page

    fragment = client.get("/people/list")
    assert fragment.status_code == 200
    assert "<html" not in fragment.text
    assert 'data-summary="1 need attention, 1 phone not sending, 1 all OK, 1 no phone yet"' in fragment.text


def test_the_overview_list_needs_a_session(migrated_db):
    assert new_client().get("/people/list").status_code == 401


# ---------- a person's day (story D-1) ----------


def test_the_day_shows_the_alert_first_and_no_location(migrated_db, two_families):
    f = two_families
    client = new_client()
    sign_in(client, migrated_db, f["daughter"])
    page = client.get(f"/people/{f['mum']}").text
    assert "Needs attention" in page
    assert f"/alerts/{f['mum_alert']}" in page
    assert "Steps today" in page and "Phone last sent data" in page
    for word in ("latitude", "longitude", "location"):
        assert word not in page.lower()


def test_a_silent_phone_is_shown_apart_from_activity(migrated_db):
    household, mum, device = make_person(migrated_db, "Mum")
    from sqlalchemy import text

    with migrated_db.begin() as conn:
        conn.execute(
            text("UPDATE devices SET last_seen_at = now() - interval '3 hours' WHERE id = :id"), {"id": device}
        )
    daughter = make_user(migrated_db, "daughter@example.com", "Daughter", [(household, "owner")])
    client = new_client()
    sign_in(client, migrated_db, daughter)
    page = client.get(f"/people/{mum}").text
    assert "3 h ago" in page
    assert "hasn't sent anything for over an hour" in page


# ---------- alerts (story E-3) ----------


def test_a_viewer_can_say_they_are_checking(migrated_db, two_families, notifiers):
    from alert_helpers import NOW, SETTINGS, token_of

    from app import contacts

    f = two_families
    # Son is a confirmed email contact of Mum's household, so he hears who is checking.
    with migrated_db.begin() as conn:
        new = contacts.add_contact(conn, f["households"][0], "Son", "email", NOW, SETTINGS, email="son@example.com")
        contacts.confirm(conn, token_of(new.link), NOW)

    client = new_client()
    csrf = sign_in(client, migrated_db, f["daughter"])
    page = client.get(f"/alerts/{f['mum_alert']}").text
    assert "I&#39;m checking" in page or "I'm checking" in page

    response = client.post(f"/alerts/{f['mum_alert']}/ack", data={"csrf": csrf})
    assert response.status_code == 303
    assert response.headers["location"] == f"/alerts/{f['mum_alert']}?done=ack"
    assert alert_status(migrated_db, f["mum_alert"]) == ("acknowledged", "Daughter")
    assert notifiers["email"].subjects == ["Daughter is checking on Mum"]

    after = client.get(f"/alerts/{f['mum_alert']}?done=ack").text
    assert "You&#39;re checking" in after or "You're checking" in after
    assert 'action="/alerts/' not in after  # no second "I'm checking" button

    # Pressing it again changes nothing and tells nobody again.
    again = client.post(f"/alerts/{f['mum_alert']}/ack", data={"csrf": csrf})
    assert again.headers["location"].endswith("?done=already")
    assert len(notifiers["email"].sent) == 1


def test_the_alerts_page_lists_open_and_recent(migrated_db, two_families):
    f = two_families
    closed = add_alert(migrated_db, f["mum"], rule="phone_silent", status="resolved", hours_ago=30)
    client = new_client()
    sign_in(client, migrated_db, f["daughter"])
    page = client.get("/alerts").text
    assert page.index(f"/alerts/{f['mum_alert']}") < page.index("Recent") < page.index(f"/alerts/{closed}")
    assert "Alerts · 1" in page  # the tab shows how many are open


# ---------- every page renders, with its security headers ----------


def test_every_page_renders(migrated_db, two_families):
    f = two_families
    client = new_client()
    sign_in(client, migrated_db, f["daughter"])
    for path in [f"/people/{f['mum']}", "/alerts", f"/alerts/{f['mum_alert']}", "/settings", "/help", "/about"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-security-policy"].startswith("default-src 'self'"), path
        assert response.headers["cache-control"] == "no-store", path
        assert "Sign out" in response.text, path


def test_brand_manifest_and_static_files(migrated_db):
    client = new_client()
    manifest = client.get("/manifest.webmanifest").json()
    assert manifest["display"] == "standalone"
    assert manifest["name"]
    assert "--primary:" in client.get("/brand/tokens.css").text
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/icon-192.png").status_code == 200
