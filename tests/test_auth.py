"""Users, members, one-time sign-in links and sessions (story C3-1), below the web pages."""

from datetime import UTC, datetime, timedelta

import pytest

from app import auth, households
from app.settings import load_settings

SETTINGS = load_settings(environ={})
NOW = datetime(2026, 11, 24, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        (" Daughter@Example.COM ", "daughter@example.com"),
        ("nurse.one+care@example.com.au", "nurse.one+care@example.com.au"),
    ],
)
def test_addresses_are_stored_trimmed_and_lower_case(given, stored):
    assert auth.normalize_email(given) == stored


@pytest.mark.parametrize("bad", ["", "daughter", "daughter@", "@example.com", "two words@example.com", "a@b"])
def test_wrong_addresses_are_refused(bad):
    with pytest.raises(ValueError, match="email address"):
        auth.normalize_email(bad)


def test_csrf_tokens_are_compared_exactly():
    session = auth.Session(auth.User(None, "a@example.com", "A"), "token-123")  # type: ignore[arg-type]
    assert auth.csrf_matches(session, "token-123")
    assert not auth.csrf_matches(session, "token-12")
    assert not auth.csrf_matches(session, "")


# ---------- with a database ----------


def test_adding_a_user_twice_keeps_one_user_and_their_name(migrated_db):
    with migrated_db.begin() as conn:
        first = auth.add_user(conn, "daughter@example.com", "Daughter")
        again = auth.add_user(conn, "DAUGHTER@example.com", "Someone else")
    assert again.id == first.id
    assert again.display_name == "Daughter"


def test_members_and_roles(migrated_db):
    with migrated_db.begin() as conn:
        household = households.create_household(conn, "Family 1")
        user = auth.add_user(conn, "son@example.com", "Son")
        auth.add_member(conn, user.id, household.id, "viewer")
        auth.add_member(conn, user.id, household.id, "owner")  # changes the role, no second row
        members = auth.list_members(conn, household.id)
        assert [(m.user.display_name, m.role) for m in members] == [("Son", "owner")]
        with pytest.raises(ValueError, match="role"):
            auth.add_member(conn, user.id, household.id, "admin")
        assert auth.remove_member(conn, user.id, household.id)
        assert not auth.remove_member(conn, user.id, household.id)


def test_a_link_works_once_and_only_until_it_expires(migrated_db):
    with migrated_db.begin() as conn:
        user = auth.add_user(conn, "daughter@example.com", "Daughter")
        link = auth.create_signin_link(conn, user, NOW, SETTINGS)
        old = auth.create_signin_link(conn, user, NOW - timedelta(minutes=16), SETTINGS)
    token, old_token = link.rsplit("/", 1)[1], old.rsplit("/", 1)[1]
    assert link.startswith(f"{SETTINGS.server.public_url}/signin/link/")
    with migrated_db.begin() as conn:
        assert auth.signin_link_is_valid(conn, token, NOW)
        assert auth.use_signin_link(conn, token, NOW) == user
        assert auth.use_signin_link(conn, token, NOW) is None  # used
        assert not auth.signin_link_is_valid(conn, token, NOW)
        assert auth.use_signin_link(conn, old_token, NOW) is None  # expired after 15 minutes
        assert auth.use_signin_link(conn, "made-up", NOW) is None


def test_sessions_last_until_they_expire_or_end(migrated_db):
    with migrated_db.begin() as conn:
        user = auth.add_user(conn, "nurse@example.com", "Nurse")
        session_id = auth.create_session(conn, user.id, NOW, SETTINGS)
        found = auth.find_session(conn, session_id, NOW + timedelta(days=29))
        assert found is not None and found.user == user and found.csrf_token
        assert auth.find_session(conn, session_id, NOW + timedelta(days=31)) is None
        assert auth.find_session(conn, "made-up", NOW) is None
        assert auth.find_session(conn, "", NOW) is None
        auth.end_session(conn, session_id)
        assert auth.find_session(conn, session_id, NOW) is None


def test_only_hashes_are_stored(migrated_db):
    from sqlalchemy import text

    with migrated_db.begin() as conn:
        user = auth.add_user(conn, "nurse@example.com", "Nurse")
        token = auth.create_signin_link(conn, user, NOW, SETTINGS).rsplit("/", 1)[1]
        session_id = auth.create_session(conn, user.id, NOW, SETTINGS)
        stored = conn.execute(text("SELECT token_hash FROM signin_links")).scalars().all()
        sessions = conn.execute(text("SELECT id_hash FROM sessions")).scalars().all()
    assert token not in stored and session_id not in sessions


def test_a_users_households_and_people(migrated_db):
    from app import access

    with migrated_db.begin() as conn:
        mum = households.create_household(conn, "Household of Mum")
        households.add_person(conn, mum.id, "Mum", "Australia/Brisbane")
        empty = households.create_household(conn, "Empty")
        user = auth.add_user(conn, "nurse@example.com", "Nurse")
        auth.add_member(conn, user.id, mum.id, "owner")
        auth.add_member(conn, user.id, empty.id, "viewer")
        assert access.user_summary(conn, user.id) == [("Empty", "viewer", []), ("Household of Mum", "owner", ["Mum"])]
        assert [h.name for h in access.households_owned(conn, user.id)] == ["Household of Mum"]
        assert auth.owner_count(conn, mum.id) == 1


def test_invitation_links_last_longer(migrated_db):
    with migrated_db.begin() as conn:
        user = auth.add_user(conn, "son@example.com", "Son")
        link = auth.create_signin_link(conn, user, NOW, SETTINGS, lifetime=SETTINGS.web.invite_link_expiry)
        token = link.rsplit("/", 1)[1]
        assert auth.signin_link_is_valid(conn, token, NOW + timedelta(hours=71))
        assert not auth.signin_link_is_valid(conn, token, NOW + timedelta(hours=73))
