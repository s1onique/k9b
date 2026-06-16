"""Pytest configuration for tests/unit.

Adds tests/unit to sys.path so that fixture modules (like incident_store_fixtures)
can be imported by sibling test modules.
"""

import sys
from pathlib import Path

# Add this directory to sys.path so fixtures can be imported
_tests_unit = Path(__file__).parent
if str(_tests_unit) not in sys.path:
    sys.path.insert(0, str(_tests_unit))
