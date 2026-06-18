"""Tests for incident diagnosis loop orchestrator schema version.

Tests:
1. Orchestrator returns schema version
"""

from __future__ import annotations

import unittest

# Module to test
from k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator import (
    ORCHESTRATOR_SCHEMA_VERSION,
)


class TestOrchestratorSchema(unittest.TestCase):
    """Schema version tests."""

    def test_schema_version_is_defined(self) -> None:
        """ORCHESTRATOR_SCHEMA_VERSION is defined."""
        self.assertEqual(ORCHESTRATOR_SCHEMA_VERSION, "1.0")
        self.assertIsInstance(ORCHESTRATOR_SCHEMA_VERSION, str)


if __name__ == "__main__":
    unittest.main()
