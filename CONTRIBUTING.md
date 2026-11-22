# Contributing

How code in this repository is written, so anyone can pick it up and understand it quickly. Pull requests are checked against this list; the parts marked **(checked)** fail the build if missed once Stage C2a's tooling is in place.

## Workflow

- Every change goes through a pull request to `main`; CI must pass ([ADR 0008](docs/adr/0008-protected-main-pull-requests.md)).
- A change that makes a decision adds or updates an [ADR](docs/adr/README.md) in the same pull request.
- A change to what is stored, who can reach it or how it is deployed updates the [threat model](docs/security/threat-model.md).
- Never commit secrets: `.env` is ignored; use `XXX` in examples, screenshots and logs.

## Comments and docstrings

The aim: a reader who doesn't know the code can tell **what each part is for and why it works that way** without asking.

- **Module docstring (checked).** Every Python module starts with a docstring: what it is responsible for, and the ADR or user story it implements.
  ```python
  """Pairing new phones with a household (ADR 0024, story C3-3).

  An owner's "Add phone" creates a pending device and shows its setup QR code
  once. The device becomes active when its first batch arrives, or its token
  expires after `pairing.pending_token_expiry_minutes`.
  """
  ```
- **Docstrings on public functions and classes (checked)**, in Google style: a one-line summary, then `Args:`, `Returns:` and `Raises:` where they apply. Say what the caller needs to know (units, time zones, side effects such as database writes), not how the body works.
  ```python
  def create_pending_device(session: Session, person_id: UUID, now: datetime) -> NewDevice:
      """Create a pending device and its one-time token for a setup QR code.

      Args:
          session: Open database session; the caller commits.
          person_id: The person who will carry the phone. Must belong to the
              signed-in member's household (checked by the caller's scope).
          now: Current time in UTC, passed in so tests control the clock.

      Returns:
          The new device and its token. The token is returned only here and
          never stored: the database keeps its SHA-256 hash.
      """
  ```
- **Inline comments explain why, not what.** Write them where the reason isn't obvious: a security choice, a workaround, a limit, an edge case.
  ```python
  # Compare hashes, not tokens: a leaked database must not be usable to upload.
  ```
  Don't restate the code (`# increment i`).
- **Settings are documented where they are defined.** Every entry in `config/settings.toml` has a comment with its meaning, unit (also in its name, such as `_minutes`) and allowed range, and the typed settings class enforces that range at startup.
- **Tests** don't need docstrings; their names describe the behaviour (`test_pending_device_expires_after_configured_minutes`). Add a comment when the setup is unusual.
- **Templates** (Jinja2) get a comment at the top saying which page or fragment they render and which route uses them.
- **TODOs** name an issue: `# TODO(#42): ...`.

## Style (checked)

- Type hints on every function; mypy must pass.
- ruff for formatting and linting, including its docstring rules (`D`, Google convention).
- Names say what things are, with units: `inactive_hours`, `expires_at` (always UTC).
- Small functions that do one thing; side effects (database, network, clock) passed in or kept at the edges so the logic is testable.
