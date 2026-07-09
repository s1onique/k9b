"""Tests for the status projection checks in the incident lifecycle boundary verifier."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Import the verifier package
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from incident_lifecycle_boundary.status_projection import (
    ALLOWED_STATUS_PROJECTION_FUNCTIONS,
    EXCLUDED_FROM_STATUS_CHECKS,
    check_status_assignments,
)


class TestStatusAssignmentChecks:
    """Tests for direct .status assignment detection with function-level allowlist."""

    def test_status_assignment_plain_detected_outside_adapter(self) -> None:
        """Plain .status assignment (Assign) outside adapter function should be detected."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            # Plain assignment (most common form)
            f.write("incident.status = 'resolved'\n")
            temp_path = f.name

        try:
            errors = check_status_assignments(temp_path)
            assert len(errors) == 1, f"Expected 1 error, got: {errors}"
            assert "status projection" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_status_assignment_annotated_detected_outside_adapter(self) -> None:
        """Annotated .status assignment (AnnAssign) outside adapter function should be detected."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            # Annotated assignment
            f.write("incident.status: str = 'resolved'\n")
            temp_path = f.name

        try:
            errors = check_status_assignments(temp_path)
            assert len(errors) == 1, f"Expected 1 error, got: {errors}"
            assert "status projection" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_status_assignment_augmented_detected_outside_adapter(self) -> None:
        """Augmented .status assignment (AugAssign) outside adapter function should be detected."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            # Augmented assignment
            f.write("incident.status += 1\n")
            temp_path = f.name

        try:
            errors = check_status_assignments(temp_path)
            assert len(errors) == 1, f"Expected 1 error, got: {errors}"
            assert "status projection" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_replace_status_detected_outside_adapter(self) -> None:
        """replace(incident, status=...) outside adapter function should be detected."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("""
from dataclasses import replace

def helper(incident):
    return replace(incident, status='resolved')
""")
            temp_path = f.name

        try:
            errors = check_status_assignments(temp_path)
            assert len(errors) == 1, f"Expected 1 error, got: {errors}"
            assert "status projection" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_replace_status_passes_inside_adapter(self, tmp_path: Path) -> None:
        """replace(incident, status=...) inside _apply_lifecycle_transition should pass."""
        # Create a temp file with the adapter function
        temp_adapter = tmp_path / "incident_lifecycle_domain_adapter.py"
        temp_adapter.write_text("""
from dataclasses import replace

def _apply_lifecycle_transition(incident, transition_result):
    return replace(incident, status='resolved')
""")

        # Save original and patch the allowed functions set
        original = ALLOWED_STATUS_PROJECTION_FUNCTIONS.copy()
        try:
            # Patch the module-level constant for the test
            import incident_lifecycle_boundary.status_projection as status_proj
            status_proj.ALLOWED_STATUS_PROJECTION_FUNCTIONS = frozenset({
                (str(temp_adapter), "_apply_lifecycle_transition"),
            })
            errors = check_status_assignments(str(temp_adapter))
            assert errors == [], f"Expected no errors for allowed adapter: {errors}"
        finally:
            import incident_lifecycle_boundary.status_projection as status_proj
            status_proj.ALLOWED_STATUS_PROJECTION_FUNCTIONS = original

    def test_status_read_outside_adapter_passes(self) -> None:
        """Status reads and comparisons outside adapter function should pass."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("""
def check_status(incident):
    if incident.status == 'resolved':
        return True
    status = incident.status
    return status
""")
            temp_path = f.name

        try:
            errors = check_status_assignments(temp_path)
            assert errors == [], f"Expected no errors for status reads: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_replace_other_field_outside_adapter_passes(self) -> None:
        """replace(..., other_field=...) outside adapter function should pass."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("""
from dataclasses import replace

def helper(incident):
    return replace(incident, last_observed_at=123)
""")
            temp_path = f.name

        try:
            errors = check_status_assignments(temp_path)
            assert errors == [], f"Expected no errors for other fields: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_status_assignment_not_detected_for_other_attributes(self) -> None:
        """Assignments to other attributes should not be flagged."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("incident.name = 'test'\n")
            f.write("incident.count = 42\n")
            temp_path = f.name

        try:
            errors = check_status_assignments(temp_path)
            assert errors == [], f"Expected no errors for other attributes: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_status_assignment_handles_syntax_error_gracefully(self) -> None:
        """Syntax errors should be skipped gracefully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("def broken(\n")  # Syntax error
            temp_path = f.name

        try:
            errors = check_status_assignments(temp_path)
            # Should not raise, should return empty (skip file with syntax errors)
            assert errors == [], f"Expected no errors for syntax error file: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_actual_adapter_module_passes(self) -> None:
        """Actual incident_lifecycle_domain_adapter.py should pass."""
        # Use relative path to match the allowed functions set in the verifier
        adapter_module = Path("src/k8s_diag_agent/collect/incident_lifecycle_domain_adapter.py")

        if adapter_module.exists():
            errors = check_status_assignments(str(adapter_module))
            assert errors == [], f"Expected no errors for actual adapter: {errors}"

    def test_actual_transitions_module_passes(self) -> None:
        """Actual incident_lifecycle_transitions.py should pass."""
        transitions_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "collect"
            / "incident_lifecycle_transitions.py"
        )

        if transitions_module.exists():
            errors = check_status_assignments(str(transitions_module))
            assert errors == [], f"Expected no errors for actual transitions: {errors}"

    def test_actual_store_module_passes(self) -> None:
        """Actual incident_store.py should pass."""
        store_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "collect"
            / "incident_store.py"
        )

        if store_module.exists():
            errors = check_status_assignments(str(store_module))
            assert errors == [], f"Expected no errors for actual store: {errors}"


class TestLegacyExclusionChecks:
    """Tests proving no legacy file exclusions remain."""

    def test_no_status_projection_exclusions_remain(self) -> None:
        """After ACT-K9B-HULK-LEGACY-INCIDENT-TRANSITIONS-RETIRE01, no exclusions remain.

        The only allowed status projection is in:
            incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition
        """
        assert EXCLUDED_FROM_STATUS_CHECKS == frozenset()

    def test_exclusion_constant_is_empty_frozenset(self) -> None:
        """Verify the exclusion constant is an empty frozenset."""
        assert isinstance(EXCLUDED_FROM_STATUS_CHECKS, frozenset)
        assert len(EXCLUDED_FROM_STATUS_CHECKS) == 0

    def test_legacy_transitions_file_checked_if_present(self) -> None:
        """If incident_transitions.py is present, it should be checked for status projections.

        This verifies the exclusion was truly removed.
        """
        # The exclusion set should be empty
        assert "incident_transitions.py" not in EXCLUDED_FROM_STATUS_CHECKS
        assert "src/k8s_diag_agent/collect/incident_transitions.py" not in EXCLUDED_FROM_STATUS_CHECKS


if __name__ == "__main__":
    import unittest
    unittest.main()
