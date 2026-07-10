"""Tests for complete evidence type contract."""

from __future__ import annotations

import sys
from pathlib import Path

# Import from the package using absolute imports from scripts root
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from incident_lifecycle_boundary.evidence_types_rules import (
    check_evidence_type_contract,
)


class TestEvidenceTypeContract:
    """Tests for the complete evidence type contract check."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence_types.py passes the complete contract check.

        NOTE: incident_evidence_types.py is the canonical source of evidence type definitions
        after module split f6d707a; incident_evidence.py is a compatibility facade only.
        """
        evidence_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "collect"
            / "incident_evidence_types.py"
        )
        if evidence_module.exists():
            errors = check_evidence_type_contract(
                evidence_filepath=str(evidence_module),
                repo_root=Path(__file__).parent.parent.parent / "src",
            )
            assert errors == [], f"Expected no errors for actual module: {errors}"


if __name__ == "__main__":
    import unittest
    unittest.main()
