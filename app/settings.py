"""Typed, validated settings from config/settings.toml (story A-1, CONTRIBUTING.md).

Settings are loaded once, the first time they are needed, from the TOML file
and then from environment variables named ``SECTION__KEY``, which win. Every
value is checked against its allowed range; a wrong value stops the app with a
message naming the setting, so a typo can't silently change behaviour.

Secrets are deliberately not settings: they stay in environment variables.
"""

import os
import tomllib
from collections.abc import Mapping
from datetime import time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.toml"

# Sensors this service knows how to store. Location is not among them, so it
# can never be accepted, whatever the configuration says (ADR 0022).
STORABLE_SENSORS = ("steps_total", "light_lux", "battery", "screen", "activity", "motion")


class SettingsError(RuntimeError):
    """A setting is missing, unknown or outside its allowed range."""


class _Section(BaseModel):
    # Unknown keys are errors, so a misspelt setting is noticed instead of ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)


class ServerSettings(_Section):
    """Where this service can be reached."""

    public_url: str = Field(pattern=r"^https://[^/\s]+(/[^\s]*[^/\s])?$")

    @property
    def readings_endpoint(self) -> str:
        """The protocol v1 upload URL given to phones in their setup QR code."""
        return f"{self.public_url}/v1/readings"


class PairingSettings(_Section):
    """How phones are added to a household (ADR 0024)."""

    pending_token_expiry_minutes: int = Field(ge=5, le=1440)
    device_profile: Literal["minimal", "activity", "full"]

    @property
    def pending_token_expiry(self) -> timedelta:
        """How long a new phone's token works before its first batch."""
        return timedelta(minutes=self.pending_token_expiry_minutes)


class IngestSettings(_Section):
    """Limits and rules for receiving data from phones (ADR 0020, ADR 0023)."""

    max_body_bytes: int = Field(ge=1_000_000, le=10_000_000)
    max_items_per_batch: int = Field(ge=10_000, le=50_000)
    max_future_minutes: int = Field(ge=0, le=60)
    max_reading_age_days: int = Field(ge=1, le=30)
    batches_per_minute_per_device: int = Field(ge=1, le=600)
    accepted_sensors: tuple[str, ...]

    @field_validator("accepted_sensors", mode="before")
    @classmethod
    def _split_text(cls, value: object) -> object:
        # An environment variable arrives as "a,b,c"; the TOML file gives a list.
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("accepted_sensors")
    @classmethod
    def _only_storable(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if "location" in value:
            raise ValueError("location is never stored (ADR 0022)")
        unknown = sorted(set(value) - set(STORABLE_SENSORS))
        if unknown:
            raise ValueError(f"unknown sensors {unknown}; allowed: {', '.join(STORABLE_SENSORS)}")
        return value


class AlertSettings(_Section):
    """Defaults and timing for alerts (ADR 0026)."""

    default_waking_from: time
    default_waking_to: time
    default_inactive_hours: int = Field(ge=1, le=12)
    default_silent_hours: int = Field(ge=1, le=48)
    resend_after_minutes: int = Field(ge=15, le=720)
    max_resends: int = Field(ge=0, le=10)
    link_expiry_minutes: int = Field(ge=5, le=1440)
    llm_timeout_seconds: int = Field(ge=2, le=30)

    @field_validator("default_waking_to")
    @classmethod
    def _after_waking_from(cls, value: time, info: ValidationInfo) -> time:
        start = info.data.get("default_waking_from")
        if start is not None and value <= start:
            raise ValueError("must be later than default_waking_from (waking hours can't cross midnight)")
        return value


class TelegramSettings(_Section):
    """The Telegram bot that sends alerts. Its token is the secret TELEGRAM_BOT_TOKEN."""

    bot_username: str = Field(pattern=r"^([A-Za-z][A-Za-z0-9_]{3,31}[Bb][Oo][Tt])?$")


class EmailSettings(_Section):
    """Who alert emails come from. The Resend API key is the secret RESEND_API_KEY."""

    from_address: str = Field(min_length=3, max_length=200, pattern=r"@")


class WebSettings(_Section):
    """The family and care web app: sign-in, sessions and refreshing (ADR 0025, ADR 0028)."""

    session_days: int = Field(ge=1, le=90)
    signin_link_minutes: int = Field(ge=5, le=60)
    signin_emails_per_hour: int = Field(ge=1, le=20)
    signin_requests_per_hour_per_ip: int = Field(ge=5, le=500)
    overview_refresh_seconds: int = Field(ge=15, le=600)
    invite_link_hours: int = Field(ge=1, le=168)

    @property
    def session_length(self) -> timedelta:
        """How long a browser stays signed in without signing in again."""
        return timedelta(days=self.session_days)

    @property
    def signin_link_expiry(self) -> timedelta:
        """How long an emailed sign-in link works."""
        return timedelta(minutes=self.signin_link_minutes)

    @property
    def invite_link_expiry(self) -> timedelta:
        """How long the sign-in link in an invitation email works."""
        return timedelta(hours=self.invite_link_hours)


class Settings(_Section):
    """All settings, one attribute per section of config/settings.toml."""

    server: ServerSettings
    pairing: PairingSettings
    ingest: IngestSettings
    alerts: AlertSettings
    telegram: TelegramSettings
    email: EmailSettings
    web: WebSettings


def load_settings(path: Path = DEFAULT_PATH, environ: Mapping[str, str] | None = None) -> Settings:
    """Read, override and validate settings.

    Args:
        path: The TOML settings file.
        environ: Environment variables to apply on top of the file; defaults
            to the process environment. Passed in so tests can control it.

    Returns:
        The validated settings.

    Raises:
        SettingsError: If the file is missing or any value is invalid. The
            message names each wrong setting as ``section.key``.
    """
    environ = os.environ if environ is None else environ
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise SettingsError(f"Cannot read settings file {path}: {err}") from err

    for section, values in raw.items():
        if not isinstance(values, dict):
            continue
        for key in list(values):
            env_name = f"{section}__{key}".upper()
            if env_name in environ:
                values[key] = environ[env_name]

    try:
        return Settings.model_validate(raw)
    except ValidationError as err:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in err.errors()
        )
        raise SettingsError(f"Invalid settings in {path.name} or environment: {problems}") from err


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The settings for this process, loaded on first use and then reused."""
    return load_settings()


def reset_settings() -> None:
    """Forget the loaded settings, so the next call reloads them (used by tests)."""
    get_settings.cache_clear()
