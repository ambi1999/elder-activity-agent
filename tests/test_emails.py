"""The email address check used by sign-in, invitations and contacts."""

import time

import pytest

from app.emails import looks_like_email


@pytest.mark.parametrize("ok", ["daughter@example.com", "nurse.one+care@example.com.au", "a@b.co"])
def test_good_addresses(ok):
    assert looks_like_email(ok)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "daughter",
        "daughter@",
        "@example.com",
        "a@b",
        "a@b.c",
        "two words@example.com",
        "a@@b.com",
        "a@example..com",
        "a@.com",
        "a@example.",
        "a@b@c.com",
        "x" * 65 + "@example.com",
    ],
)
def test_bad_addresses(bad):
    assert not looks_like_email(bad)


def test_crafted_input_is_quick():
    # The kind of input that made the old regular expression slow (CodeQL py/polynomial-redos).
    start = time.perf_counter()
    assert not looks_like_email("!@!." + "!." * 50_000)
    assert time.perf_counter() - start < 0.5
