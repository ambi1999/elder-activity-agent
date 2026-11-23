"""Sending messages by Telegram and email (ADR 0026).

Each channel has a ``Notifier``: ``send(address, message)`` returns True if
the message was accepted for delivery. Which notifier is used depends on
whether the channel's secret is set:

- ``TELEGRAM_BOT_TOKEN`` set: real Telegram messages; otherwise logged only.
- ``RESEND_API_KEY`` set: real emails through Resend; otherwise logged only.

"Logged only" (``ConsoleNotifier``) lets everything be developed and tested
without accounts. Logs never contain addresses, chat ids or tokens.
"""

import logging
import os
from typing import Protocol

import httpx

from app.messages import Message
from app.settings import Settings

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0)


class Notifier(Protocol):
    """Sends a message on one channel."""

    channel: str

    def send(self, address: str, message: Message) -> bool:
        """Send a message. Returns True if the service accepted it."""
        ...


class ConsoleNotifier:
    """Writes messages to the log instead of sending them (no account configured).

    Args:
        channel: "email" or "telegram".
    """

    def __init__(self, channel: str) -> None:
        self.channel = channel

    def send(self, address: str, message: Message) -> bool:
        """Log the message's subject (not its address) and report it as sent."""
        log.info("[%s not configured, logged only] %s", self.channel, message.subject)
        return True


class TelegramNotifier:
    """Sends Telegram messages through the Bot API.

    Args:
        token: The bot's token (secret).
        client: HTTP client, passed in so tests can replace it.
    """

    channel = "telegram"

    def __init__(self, token: str, client: httpx.Client | None = None) -> None:
        self._url = f"https://api.telegram.org/bot{token}"
        self._client = client or httpx.Client(timeout=TIMEOUT)

    def _call(self, method: str, payload: dict[str, object]) -> bool:
        try:
            response = self._client.post(f"{self._url}/{method}", json=payload)
        except httpx.HTTPError as err:
            # The URL contains the bot token, so log only the error type.
            log.warning("Telegram %s failed: %s", method, type(err).__name__)
            return False
        if response.status_code != 200:
            log.warning("Telegram %s returned %s", method, response.status_code)
            return False
        return True

    def send(self, address: str, message: Message) -> bool:
        """Send to a chat id, with an "I'm checking" button for open alerts."""
        payload: dict[str, object] = {"chat_id": address, "text": f"{message.subject}\n\n{message.text}"}
        if message.ack_alert_id:
            button = {"text": "I'm checking", "callback_data": f"ack:{message.ack_alert_id}"}
            payload["reply_markup"] = {"inline_keyboard": [[button]]}
        return self._call("sendMessage", payload)

    def answer_button(self, callback_query_id: str, text: str) -> bool:
        """Show a short notice after someone presses a button."""
        return self._call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})

    def set_webhook(self, url: str, secret: str) -> bool:
        """Tell Telegram where to send updates (button presses, /start), with a secret header."""
        return self._call(
            "setWebhook",
            {"url": url, "secret_token": secret, "allowed_updates": ["message", "callback_query"]},
        )


class EmailNotifier:
    """Sends email through Resend's HTTP API.

    Args:
        api_key: Resend API key (secret).
        from_address: Sender, e.g. "Elder Activity <alerts@example.com>".
        client: HTTP client, passed in so tests can replace it.
    """

    channel = "email"

    def __init__(self, api_key: str, from_address: str, client: httpx.Client | None = None) -> None:
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._from = from_address
        self._client = client or httpx.Client(timeout=TIMEOUT)

    def send(self, address: str, message: Message) -> bool:
        """Send a plain-text email."""
        payload = {"from": self._from, "to": [address], "subject": message.subject, "text": message.text}
        try:
            response = self._client.post("https://api.resend.com/emails", json=payload, headers=self._headers)
        except httpx.HTTPError as err:
            log.warning("Email failed: %s", type(err).__name__)
            return False
        if response.status_code not in (200, 201, 202):
            log.warning("Email service returned %s", response.status_code)
            return False
        return True


def build(settings: Settings) -> dict[str, Notifier]:
    """The notifier for each channel, real if its secret is set, logged-only otherwise."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_key = os.getenv("RESEND_API_KEY")
    return {
        "telegram": TelegramNotifier(token) if token else ConsoleNotifier("telegram"),
        "email": EmailNotifier(api_key, settings.email.from_address) if api_key else ConsoleNotifier("email"),
    }
