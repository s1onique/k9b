"""Tests for evidence type alias verification rules."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Import from the package using absolute imports from scripts root
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from incident_lifecycle_boundary.evidence_types_rules import (
    check_evidence_type_aliases,
)


class TestEvidenceTypeAliasCheck:
    """Tests for EvidenceRoleCode and EvidenceKindCode type alias verification."""

    def test_passes_for_correct_typed_aliases(self) -> None:
        """Passes if both aliases exist with correct values."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

EvidenceRoleCode = Literal[
    "primary",
    "supporting",
    "snapshot",
    "review_packet",
    "debug",
]

EvidenceKindCode = Literal[
    "snapshot_bundle",
    "review_packet",
    "log_excerpt",
    "metric_window",
    "trace",
    "run_summary",
    "external_analysis",
]
''')
            temp_path = f.name

        try:
            errors = check_evidence_type_aliases(temp_path)
            assert errors == [], f"Expected no errors: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_if_role_alias_missing(self) -> None:
        """Fails if EvidenceRoleCode alias is missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

EvidenceKindCode = Literal["snapshot_bundle"]
''')
            temp_path = f.name

        try:
            errors = check_evidence_type_aliases(temp_path)
            assert len(errors) > 0
            assert any("EvidenceRoleCode" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_kind_alias_missing(self) -> None:
        """Fails if EvidenceKindCode alias is missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

EvidenceRoleCode = Literal["primary"]
''')
            temp_path = f.name

        try:
            errors = check_evidence_type_aliases(temp_path)
            assert len(errors) > 0
            assert any("EvidenceKindCode" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_role_values_mismatch(self) -> None:
        """Fails if role values don't match expected contract."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

# Missing "user", has unexpected "unknown_role"
EvidenceRoleCode = Literal[
    "primary",
    "supporting",
    "snapshot",
    "review_packet",
    "debug",
    "system",
    "unknown_role",
]

EvidenceKindCode = Literal["snapshot_bundle"]
''')
            temp_path = f.name

        try:
            errors = check_evidence_type_aliases(temp_path)
            assert len(errors) > 0
            assert any("missing" in e.lower() or "unexpected" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_kind_values_mismatch(self) -> None:
        """Fails if kind values don't match expected contract."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

EvidenceRoleCode = Literal["primary", "supporting", "snapshot", "review_packet", "debug", "system", "user"]

# Missing "log_excerpt", has unexpected "unknown_kind"
EvidenceKindCode = Literal[
    "snapshot_bundle",
    "review_packet",
    "unknown_kind",
]
''')
            temp_path = f.name

        try:
            errors = check_evidence_type_aliases(temp_path)
            assert len(errors) > 0
            assert any("missing" in e.lower() or "unexpected" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence_types.py passes type alias checks.

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
            errors = check_evidence_type_aliases(str(evidence_module))
            assert errors == [], f"Expected no errors for actual module: {errors}"


if __name__ == "__main__":
    import unittest
    unittest.main()
