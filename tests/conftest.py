"""Shared pytest configuration for incident diagnosis service tests.

This module re-exports fixtures from test_incident_diagnosis_service_fixtures.py
so they can be discovered by sibling test modules via pytest's fixture discovery.
"""

from __future__ import annotations

import pytest

# Import kubectl guard to enforce unit test boundaries
# This must be imported before other fixtures to ensure it runs first
from tests.conftest_kubectl_guard import forbid_real_kubectl  # noqa: F401

# Re-export fixtures from the fixtures module so they're discoverable by sibling test files
# The fixtures module is not a conftest.py, so we re-export here for fixture discovery
from tests.test_incident_diagnosis_service_fixtures import (  # noqa: F401
    case_dir,  # noqa: F401
    cleanup_store,  # noqa: F401
    evidence_provider,  # noqa: F401
    expected,  # noqa: F401
    manifest,  # noqa: F401
)

# =============================================================================
# kubectl guard hooks (must be in conftest.py for pytest to discover)
# =============================================================================

def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "live_kubernetes: mark test as requiring real Kubernetes cluster (skips kubectl guard)",
    )
    config.addinivalue_line(
        "markers",
        "mock_kubectl: mark test as providing its own kubectl mock (auto-installs mock fixture)",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-add mock_kubectl_subprocess fixture to tests marked with mock_kubectl."""
    for item in items:
        if item.get_closest_marker("mock_kubectl"):
            # Ensure the mock_kubectl_subprocess fixture is available
            item.add_marker(pytest.mark.usefixtures("mock_kubectl_subprocess"))
