"""Requirements, stories and tests stay linked, and the matrix stays current (docs/requirements/).

Verifies: EA-NFR-MNT-002
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_traceability.py"


def load():
    spec = importlib.util.spec_from_file_location("check_traceability", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_requirements_stories_and_tests_are_linked():
    # If this fails, the message lists each problem; after editing the SRS or a
    # test's "Verifies:" line, run: uv run python scripts/check_traceability.py --write
    assert load().run() == []
