"""Protocol v1 adapter, without a database: envelope checks and item tolerance (ADR 0023)."""

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from app import households
from app.protocol_v1 import BatchEnvelope, to_batch
from app.readings import Event, MinuteSummary, Reading

PROTOCOL = Path(__file__).resolve().parents[1] / "protocol" / "phone-sensor-logger-v1"
EXAMPLES = PROTOCOL / "examples"
MANIFEST = json.loads((EXAMPLES / "manifest.json").read_text())
ALL = ("steps_total", "light_lux", "battery", "screen", "activity", "motion")
T = 1_794_800_820_000  # a whole minute, in ms


def envelope(readings=(), summaries=(), **overrides):
    body = {
        "protocol": "phone-sensor-logger/v1",
        "session_id": "s-1",
        "batch_seq": 0,
        "sent_at": T,
        "timezone": "Australia/Brisbane",
        "readings": list(readings),
        "summaries": list(summaries),
    }
    body.update(overrides)
    return body


def example(name):
    return json.loads((EXAMPLES / name).read_text())


@pytest.mark.parametrize("case", MANIFEST["batch"], ids=lambda c: c["file"])
def test_adapter_follows_the_manifest(case):
    body = json.loads((EXAMPLES / case["file"]).read_text())
    if case["receiver"] == "accept":
        to_batch(BatchEnvelope.model_validate(body), ALL)
    else:
        with pytest.raises(ValidationError):
            BatchEnvelope.model_validate(body)


@pytest.mark.parametrize("case", MANIFEST["batch"], ids=lambda c: c["file"])
def test_vendored_examples_match_the_vendored_schema(case):
    # Guards against a partial or edited copy of the protocol.
    schema = json.loads((PROTOCOL / "v1.schema.json").read_text())
    valid = jsonschema.Draft202012Validator(schema).is_valid(json.loads((EXAMPLES / case["file"]).read_text()))
    assert valid is case["schema_valid"]


def test_every_accepted_sensor_is_converted():
    batch = to_batch(BatchEnvelope.model_validate(example("batch/valid-03-all-sensors.json")), ALL)
    assert {r.sensor for r in batch.readings} == {"steps_total", "light_lux", "battery", "motion"}
    assert [(e.sensor, e.value, e.confidence) for e in batch.events] == [
        ("screen", "on", None),
        ("activity", "walking", 87),
        ("activity", "still", None),
    ]
    assert batch.ignored == 1  # location


def test_location_is_ignored_even_if_configured_by_mistake():
    item = {"sensor": "location", "t": T, "lat": 1.0, "lon": 2.0, "accuracy_m": 1000}
    batch = to_batch(BatchEnvelope.model_validate(envelope([item])), (*ALL, "location"))
    assert batch.readings == [] and batch.events == []
    assert batch.ignored == 1


def test_sensors_not_accepted_are_ignored():
    items = [{"sensor": "light_lux", "t": T, "value": 5}, {"sensor": "screen", "t": T, "on": True}]
    batch = to_batch(BatchEnvelope.model_validate(envelope(items)), ("screen",))
    assert [e.sensor for e in batch.events] == ["screen"]
    assert batch.readings == []
    assert batch.ignored == 1


def test_bad_items_are_ignored_and_the_rest_kept():
    batch = to_batch(BatchEnvelope.model_validate(example("batch/tolerated-01-bad-items.json")), ALL)
    assert [r.sensor for r in batch.readings] == ["light_lux"]
    assert batch.summaries == []
    assert batch.ignored == 4
    assert batch.received == 5


@pytest.mark.parametrize(
    "item",
    [
        {"sensor": "battery", "t": T, "level": 0.5},  # charging missing
        {"sensor": "screen", "t": T, "on": "yes"},
        {"sensor": "activity", "t": T, "type": "dancing"},
        {"sensor": "activity", "t": T, "type": "still", "confidence": 101},
        {"sensor": "steps_total", "t": T, "value": 1.5},
        {"sensor": "steps_total", "t": True, "value": 1},
        {"sensor": "light_lux", "t": T, "value": float("nan")},
        "not an object",
    ],
)
def test_malformed_readings_are_ignored(item):
    batch = to_batch(BatchEnvelope.model_validate(envelope([item])), ALL)
    assert batch.readings == [] and batch.events == []
    assert batch.ignored == 1


def test_summaries_become_minute_summaries():
    items = [
        {"sensor": "light_lux", "minute": T, "count": 60, "sum": 600.0, "min": 5, "max": 20},
        {"sensor": "motion", "minute": T, "count": 30, "sum": 3.0, "min": 0, "max": 0.4},
    ]
    batch = to_batch(BatchEnvelope.model_validate(envelope(summaries=items)), ALL)
    assert batch.summaries == [
        MinuteSummary("light_lux", batch.summaries[0].minute, 60, 600.0, 20.0),
        MinuteSummary("motion", batch.summaries[1].minute, 30, 3.0, 0.4),
    ]
    assert batch.summaries[0].minute.second == 0


def test_unknown_fields_and_sensors_are_ignored_not_rejected():
    body = envelope([{"sensor": "heart_rate", "t": T, "bpm": 70}], extra_field={"x": 1})
    batch = to_batch(BatchEnvelope.model_validate(body), ALL)
    assert batch.ignored == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"sent_at": str(T)},
        {"batch_seq": True},
        {"batch_seq": -1},
        {"session_id": "has spaces"},
        {"timezone": ""},
        {"readings": {}},
        {"protocol": "phone-sensor-logger/v2"},
    ],
)
def test_bad_envelopes_are_rejected(overrides):
    body = envelope() | overrides
    with pytest.raises(ValidationError):
        BatchEnvelope.model_validate(body)


def test_internal_types_are_used():
    items = [{"sensor": "steps_total", "t": T, "value": 3}, {"sensor": "screen", "t": T, "on": False}]
    batch = to_batch(BatchEnvelope.model_validate(envelope(items)), ALL)
    assert isinstance(batch.readings[0], Reading)
    assert isinstance(batch.events[0], Event)
    assert batch.events[0].value == "off"


def test_setup_qr_contents_match_the_provisioning_schema():
    schema = json.loads((PROTOCOL / "provisioning-v1.schema.json").read_text())
    token = "x" * 43  # same length as the real tokens (secrets.token_urlsafe(32))
    payload = households.provisioning_payload("https://example.com/v1/readings", token, "Mum's phone", "activity")
    jsonschema.validate(payload, schema)
