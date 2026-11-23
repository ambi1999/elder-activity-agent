"""Telegram and email notifiers, with HTTP replaced by a fake transport (nothing is really sent)."""

import json

import httpx

from app import notifiers
from app.messages import Message
from app.settings import load_settings

MESSAGE = Message("No activity for 4 hours: Mum", "Explanation.", ack_url=None, ack_alert_id="alert-1")


def recording_client(status: int = 200):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"ok": status == 200})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_telegram_sends_text_with_an_im_checking_button():
    client, calls = recording_client()
    assert notifiers.TelegramNotifier("bot-token-for-tests", client).send("4242", MESSAGE) is True
    [request] = calls
    assert request.url.path == "/botbot-token-for-tests/sendMessage"
    body = json.loads(request.content)
    assert body["chat_id"] == "4242"
    assert body["text"].startswith("No activity for 4 hours: Mum")
    assert body["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "ack:alert-1"


def test_telegram_failure_is_reported_and_logged_without_the_token(caplog):
    client, _ = recording_client(status=403)
    assert notifiers.TelegramNotifier("bot-token-for-tests", client).send("4242", MESSAGE) is False
    assert "bot-token-for-tests" not in caplog.text


def test_email_goes_through_resend():
    client, calls = recording_client()
    sender = notifiers.EmailNotifier("re_key_for_tests", "Elder Activity <alerts@example.com>", client)
    assert sender.send("son@example.com", MESSAGE) is True
    [request] = calls
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_key_for_tests"
    assert json.loads(request.content)["to"] == ["son@example.com"]


def test_without_secrets_messages_are_only_logged(monkeypatch, caplog):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    built = notifiers.build(load_settings(environ={}))
    assert isinstance(built["telegram"], notifiers.ConsoleNotifier)
    with caplog.at_level("INFO"):
        assert built["email"].send("son@example.com", MESSAGE) is True
    assert "son@example.com" not in caplog.text


def test_with_secrets_the_real_notifiers_are_used(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token-for-tests")
    monkeypatch.setenv("RESEND_API_KEY", "re_key_for_tests")
    built = notifiers.build(load_settings(environ={}))
    assert isinstance(built["telegram"], notifiers.TelegramNotifier)
    assert isinstance(built["email"], notifiers.EmailNotifier)
