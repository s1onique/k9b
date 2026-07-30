"""Integration-test conftest.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01.

Adds ``tests/unit`` to ``sys.path`` so the integration tests can
import the shared scoped-selection support module without
extending the canonical ``pythonpath`` in :mod:`pytest.ini`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_INTEGRATION_TEST_DIR = Path(__file__).resolve().parent
_UNIT_DIR = _INTEGRATION_TEST_DIR.parent / "unit"
if str(_UNIT_DIR) not in sys.path:
    sys.path.insert(0, str(_UNIT_DIR))
del _INTEGRATION_TEST_DIR, _UNIT_DIR
