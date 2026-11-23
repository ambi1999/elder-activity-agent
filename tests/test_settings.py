"""Settings: defaults load, wrong values stop the app with the setting's name (story A-1)."""

from datetime import timedelta
from pathlib import Path

import pytest

from app.settings import DEFAULT_PATH, SettingsError, load_settings


def test_default_settings_are_valid():
    settings = load_settings(environ={})
    assert settings.pairing.pending_token_expiry == timedelta(minutes=30)
    assert settings.pairing.device_profile == "activity"
    assert settings.server.readings_endpoint.endswith("/v1/readings")
    assert "location" not in settings.ingest.accepted_sensors
    assert settings.web.signin_link_expiry == timedelta(minutes=15)
    assert settings.web.session_length == timedelta(days=30)
    assert settings.web.invite_link_expiry == timedelta(hours=72)


def test_environment_overrides_the_file():
    settings = load_settings(environ={"PAIRING__PENDING_TOKEN_EXPIRY_MINUTES": "60"})
    assert settings.pairing.pending_token_expiry_minutes == 60


def test_sensor_list_can_come_from_the_environment():
    settings = load_settings(environ={"INGEST__ACCEPTED_SENSORS": "steps_total, screen"})
    assert settings.ingest.accepted_sensors == ("steps_total", "screen")


@pytest.mark.parametrize(
    ("env", "named"),
    [
        ({"PAIRING__PENDING_TOKEN_EXPIRY_MINUTES": "2"}, "pairing.pending_token_expiry_minutes"),
        ({"PAIRING__PENDING_TOKEN_EXPIRY_MINUTES": "1441"}, "pairing.pending_token_expiry_minutes"),
        ({"PAIRING__DEVICE_PROFILE": "everything"}, "pairing.device_profile"),
        ({"SERVER__PUBLIC_URL": "http://insecure.example.com"}, "server.public_url"),
        ({"INGEST__MAX_ITEMS_PER_BATCH": "100"}, "ingest.max_items_per_batch"),
        ({"INGEST__ACCEPTED_SENSORS": "steps_total,location"}, "ingest.accepted_sensors"),
        ({"INGEST__ACCEPTED_SENSORS": "heart_rate"}, "ingest.accepted_sensors"),
        ({"WEB__SIGNIN_LINK_MINUTES": "2"}, "web.signin_link_minutes"),
        ({"WEB__SESSION_DAYS": "365"}, "web.session_days"),
    ],
)
def test_invalid_values_stop_the_app_and_name_the_setting(env, named):
    with pytest.raises(SettingsError, match=named.replace(".", r"\.")):
        load_settings(environ=env)


def test_location_can_never_be_accepted():
    with pytest.raises(SettingsError, match="ADR 0022"):
        load_settings(environ={"INGEST__ACCEPTED_SENSORS": "location"})


def test_unknown_setting_is_an_error(tmp_path: Path):
    path = tmp_path / "settings.toml"
    path.write_text(DEFAULT_PATH.read_text() + "\n[pairing_extra]\ntypo = 1\n")
    with pytest.raises(SettingsError, match="pairing_extra"):
        load_settings(path, environ={})


def test_missing_file_is_a_clear_error(tmp_path: Path):
    with pytest.raises(SettingsError, match="Cannot read settings file"):
        load_settings(tmp_path / "missing.toml", environ={})
