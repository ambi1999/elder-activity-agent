# Vendored protocols

| Folder | Source | Version |
|---|---|---|
| `phone-sensor-logger-v1/` | phone-sensor-logger repository, `protocol/` at tag `protocol-v1.0.0` | Specification 1.0.0 |

These are exact copies, not edited here. `POST /v1/readings` implements them ([ADR 0023](../docs/adr/0023-phone-sensor-logger-as-data-source.md)), and `tests/test_protocol_v1_contract.py` runs every example in `examples/manifest.json` through the endpoint, so a change in the protocol shows up as a failing test.

To update: copy the logger's `protocol/` folder at a newer protocol tag over the folder here, update this table, and run the tests.
