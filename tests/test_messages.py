"""Alert wording (docs/design.md "Tone") and contacts' quiet hours, without a database."""

import uuid
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from app import messages
from app.contacts import Contact, in_quiet_hours
from app.rules import INACTIVITY, PHONE_SILENT

TZ = "Australia/Brisbane"


def local(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 23, hour, minute, tzinfo=ZoneInfo(TZ)).astimezone(UTC)


def test_times_read_as_people_say_them():
    assert messages.clock(local(9, 5), TZ) == "9:05 am"
    assert messages.clock(local(21, 30), TZ) == "9:30 pm"


def test_inactivity_template_states_facts():
    text = messages.template_explanation(INACTIVITY, "Mum", local(9, 5), TZ, False, 0.58)
    assert text == (
        "Mum's phone is still sending data (battery 58%), but there have been no steps, "
        "screen use or walking since 9:05 am."
    )
    assert "start of waking hours" in messages.template_explanation(INACTIVITY, "Mum", local(8), TZ, True, None)


def test_phone_silent_is_worded_as_a_phone_problem():
    text = messages.template_explanation(PHONE_SILENT, "Mum", local(15, 10), TZ, False, None)
    assert "hasn't sent any data since 3:10 pm" in text
    assert "about the phone, not necessarily about Mum" in text
    assert messages.headline(PHONE_SILENT, "Mum", 6) == "Mum's phone has stopped sending"


def test_opened_message_labels_the_llm_and_carries_the_link():
    message = messages.opened(INACTIVITY, "Mum", 4, "They have not moved.", True, "https://x/a/t", "alert-1")
    assert message.subject == "No activity for 4 hours: Mum"
    assert "written by the agent" in message.text
    assert "https://x/a/t" in message.text
    assert messages.opened(INACTIVITY, "Mum", 4, "x", False, None, "a").text == "x"


def test_updates_name_who_is_checking_and_the_all_clear():
    assert messages.acknowledged(INACTIVITY, "Mum", 4, "Son", local(9, 21), TZ).subject == "Son is checking on Mum"
    assert messages.resolved(INACTIVITY, "Mum", local(9, 40), TZ).text == "Activity resumed at 9:40 am. Alert closed."


def contact(start, end):
    return Contact(uuid.uuid4(), uuid.uuid4(), "Son", "email", "son@example.com", local(8), start, end)


def test_quiet_hours_within_a_day_and_across_midnight():
    day = contact(time(12), time(14))
    assert in_quiet_hours(day, local(13), TZ) is True
    assert in_quiet_hours(day, local(14), TZ) is False
    night = contact(time(22), time(7))
    assert in_quiet_hours(night, local(23), TZ) is True
    assert in_quiet_hours(night, local(6, 59), TZ) is True
    assert in_quiet_hours(night, local(7), TZ) is False
    assert in_quiet_hours(contact(None, None), local(3), TZ) is False
