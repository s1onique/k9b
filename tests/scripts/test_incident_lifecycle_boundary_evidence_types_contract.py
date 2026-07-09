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
        """Actual incident_evidence.py passes the complete contract check."""
        evidence_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "collect"
            / "incident_evidence.py"
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
