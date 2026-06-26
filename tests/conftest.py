"""Shared pytest configuration for incident diagnosis service tests.

This module re-exports fixtures from test_incident_diagnosis_service_fixtures.py
so they can be discovered by sibling test modules via pytest's fixture discovery.
"""

from __future__ import annotations

# Re-export fixtures from the fixtures module so they're discoverable by sibling test files
# The fixtures module is not a conftest.py, so we re-export here for fixture discovery
from tests.test_incident_diagnosis_service_fixtures import (  # noqa: F401
    case_dir,  # noqa: F401
    cleanup_store,  # noqa: F401
    evidence_provider,  # noqa: F401
    expected,  # noqa: F401
    manifest,  # noqa: F401
)
