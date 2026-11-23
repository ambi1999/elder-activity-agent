"""Checking that text looks like an email address, without a regular expression.

A pattern that repeats "anything but @ or a space" on both sides of a dot can take a very long time on
crafted input (it backtracks over the dots), and these checks run on text typed
into the web app's forms. Splitting the string does the same check in a single
pass. It is a sanity check only: whether an address works is known when the
emailed link is used.
"""

MAX_LENGTH = 254  # the longest address SMTP allows


def looks_like_email(address: str) -> bool:
    """Whether ``address`` has the shape name@domain.tld, with no spaces.

    Examples:
        >>> looks_like_email("daughter@example.com")
        True
        >>> looks_like_email("daughter@example")
        False
    """
    if not address or len(address) > MAX_LENGTH or any(c.isspace() for c in address):
        return False
    local, at, domain = address.rpartition("@")
    if not at or not local or "@" in local or len(local) > 64:
        return False
    labels = domain.split(".")
    # At least two parts, none empty ("example..com", ".com" and "example." fail),
    # and a top-level part of two or more characters.
    return len(labels) >= 2 and all(labels) and len(labels[-1]) >= 2
