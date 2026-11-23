# Protocol changelog

Versions follow the rules in [v1.md, section 7](v1.md#7-compatibility-rules). Each version is tagged in Git as `protocol-vX.Y.Z`.

## 1.0.0 (2026-11-17)

First stable version.

- Upload batch: `phone-sensor-logger/v1`, with batch identity, readings and per-minute summaries.
- Sensors: `steps_total`, `light_lux`, `battery`, `screen`, `activity`, `motion`, `location`.
- Compatibility, privacy, response, error and retry rules.
- Provisioning QR code format, version 1.
- JSON Schemas and contract-test examples with a manifest.
