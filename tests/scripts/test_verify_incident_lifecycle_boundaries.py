"""Tests for the incident lifecycle boundary verifier."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Import the verifier module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
import verify_incident_lifecycle_boundaries as verifier


class TestBoundaryVerifier:
    """Tests for the boundary verification logic."""

    def test_domain_module_has_no_forbidden_imports(self) -> None:
        """Domain module should not import forbidden dependencies."""
        domain_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "domain"
            / "incident_lifecycle.py"
        )
        errors = verifier.check_forbidden_imports(str(domain_module))
        assert errors == [], f"Domain module has forbidden imports: {errors}"

    def test_reason_allowlist_enforced(self) -> None:
        """Rejection reasons must be in the allowlist."""
        domain_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "domain"
            / "incident_lifecycle.py"
        )
        errors = verifier.check_reason_allowlist(str(domain_module))
        assert errors == [], f"Unknown rejection reasons found: {errors}"

    def test_verifier_passes_for_clean_module(self) -> None:
        """Verifier should pass when domain module is clean."""
        with patch.object(verifier, "check_forbidden_imports", return_value=[]):
            with patch.object(verifier, "check_reason_allowlist", return_value=[]):
                with patch.object(verifier, "check_status_assignments", return_value=[]):
                    with patch.object(verifier, "check_transition_adapter_uses_lifecycle_core", return_value=[]):
                        exit_code = verifier.main(["verify_incident_lifecycle_boundaries.py"])
                        assert exit_code == 0

    def test_verifier_fails_for_forbidden_import(self) -> None:
        """Verifier should detect forbidden imports."""
        errors = [
            "src/k8s_diag_agent/domain/incident_lifecycle.py:5: "
            "Forbidden import 'subprocess'"
        ]
        with patch.object(verifier, "check_forbidden_imports", return_value=errors):
            with patch.object(verifier, "check_reason_allowlist", return_value=[]):
                with patch.object(verifier, "check_status_assignments", return_value=[]):
                    with patch.object(verifier, "check_transition_adapter_uses_lifecycle_core", return_value=[]):
                        exit_code = verifier.main(["verify_incident_lifecycle_boundaries.py"])
                        assert exit_code == 1

    def test_verifier_fails_for_unknown_reason(self) -> None:
        """Verifier should detect unknown rejection reasons."""
        errors = [
            "src/k8s_diag_agent/domain/incident_lifecycle.py:10: "
            "Unknown rejection reason 'unknown_code'"
        ]
        with patch.object(verifier, "check_forbidden_imports", return_value=[]):
            with patch.object(verifier, "check_reason_allowlist", return_value=errors):
                with patch.object(verifier, "check_status_assignments", return_value=[]):
                    with patch.object(verifier, "check_transition_adapter_uses_lifecycle_core", return_value=[]):
                        exit_code = verifier.main(["verify_incident_lifecycle_boundaries.py"])
                        assert exit_code == 1

    def test_verifier_fails_for_missing_domain_module(self) -> None:
        """Verifier should fail gracefully when domain module is missing."""
        with patch.object(Path, "exists", return_value=False):
            exit_code = verifier.main(["verify_incident_lifecycle_boundaries.py"])
            assert exit_code == 2

    def test_is_forbidden_module_exact_match(self) -> None:
        """_is_forbidden_module should detect exact matches."""
        assert verifier._is_forbidden_module("subprocess") is True
        assert verifier._is_forbidden_module("logging") is True
        assert verifier._is_forbidden_module("random") is True

    def test_is_forbidden_module_dotted_match(self) -> None:
        """_is_forbidden_module should detect dotted module matches."""
        assert (
            verifier._is_forbidden_module("k8s_diag_agent.collect.incident_store")
            is True
        )
        assert (
            verifier._is_forbidden_module(
                "k8s_diag_agent.collect.incident_store_provider"
            )
            is True
        )

    def test_is_forbidden_module_prefix_match(self) -> None:
        """_is_forbidden_module should detect submodule matches."""
        assert verifier._is_forbidden_module("kubernetes.client") is True
        assert (
            verifier._is_forbidden_module("k8s_diag_agent.collect.incident_store.foo")
            is True
        )

    def test_is_forbidden_module_no_match(self) -> None:
        """_is_forbidden_module should return False for allowed modules."""
        assert verifier._is_forbidden_module("datetime") is False
        assert verifier._is_forbidden_module("typing") is False
        assert verifier._is_forbidden_module("k8s_diag_agent.domain") is False


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
            errors = verifier.check_status_assignments(temp_path)
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
            errors = verifier.check_status_assignments(temp_path)
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
            errors = verifier.check_status_assignments(temp_path)
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
            errors = verifier.check_status_assignments(temp_path)
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
        original = verifier._ALLOWED_STATUS_PROJECTION_FUNCTIONS.copy()
        try:
            verifier._ALLOWED_STATUS_PROJECTION_FUNCTIONS = frozenset({
                (str(temp_adapter), "_apply_lifecycle_transition"),
            })
            errors = verifier.check_status_assignments(str(temp_adapter))
            assert errors == [], f"Expected no errors for allowed adapter: {errors}"
        finally:
            verifier._ALLOWED_STATUS_PROJECTION_FUNCTIONS = original

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
            errors = verifier.check_status_assignments(temp_path)
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
            errors = verifier.check_status_assignments(temp_path)
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
            errors = verifier.check_status_assignments(temp_path)
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
            errors = verifier.check_status_assignments(temp_path)
            # Should not raise, should return empty (skip file with syntax errors)
            assert errors == [], f"Expected no errors for syntax error file: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_actual_adapter_module_passes(self) -> None:
        """Actual incident_lifecycle_domain_adapter.py should pass."""
        # Use relative path to match the allowed functions set in the verifier
        adapter_module = Path("src/k8s_diag_agent/collect/incident_lifecycle_domain_adapter.py")

        if adapter_module.exists():
            errors = verifier.check_status_assignments(str(adapter_module))
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
            errors = verifier.check_status_assignments(str(transitions_module))
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
            errors = verifier.check_status_assignments(str(store_module))
            assert errors == [], f"Expected no errors for actual store: {errors}"


class TestLegacyExclusionChecks:
    """Tests proving no legacy file exclusions remain."""

    def test_no_status_projection_exclusions_remain(self) -> None:
        """After ACT-K9B-HULK-LEGACY-INCIDENT-TRANSITIONS-RETIRE01, no exclusions remain.
        
        The only allowed status projection is in:
            incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition
        """
        assert verifier._EXCLUDED_FROM_STATUS_CHECKS == frozenset()

    def test_exclusion_constant_is_empty_frozenset(self) -> None:
        """Verify the exclusion constant is an empty frozenset."""
        assert isinstance(verifier._EXCLUDED_FROM_STATUS_CHECKS, frozenset)
        assert len(verifier._EXCLUDED_FROM_STATUS_CHECKS) == 0

    def test_legacy_transitions_file_checked_if_present(self) -> None:
        """If incident_transitions.py is present, it should be checked for status projections.
        
        This verifies the exclusion was truly removed.
        """
        # The exclusion set should be empty
        assert "incident_transitions.py" not in verifier._EXCLUDED_FROM_STATUS_CHECKS
        assert "src/k8s_diag_agent/collect/incident_transitions.py" not in verifier._EXCLUDED_FROM_STATUS_CHECKS


class TestTransitionAdapterUsesLifecycleCoreChecks:
    """Tests for transition adapter lifecycle core CALL checking via AST."""

    def test_transitions_with_all_required_calls_passes(self) -> None:
        """Transitions module with all required AST calls should pass."""
        # Create a temp file with all required CALLS (not just imports)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("""
from datetime import datetime
from k8s_diag_agent.domain.incident_lifecycle import (
    IncidentLifecycle,
    mark_collecting_evidence as domain_mark_collecting_evidence,
    mark_ready_for_review as domain_mark_ready_for_review,
    mark_investigating as domain_mark_investigating,
    suppress_incident as domain_suppress_incident,
    mark_duplicate as domain_mark_duplicate,
    resolve_incident as domain_resolve_incident,
)

def transition_all(lifecycle, now):
    # All required AST calls
    domain_mark_collecting_evidence(lifecycle, bundle_id="b", actor="system", now=now)
    domain_mark_ready_for_review(lifecycle, review_packet_id="r", actor="diag", now=now)
    domain_mark_investigating(lifecycle, actor="diag", now=now)
    domain_suppress_incident(lifecycle, reason="x", actor="user", now=now)
    domain_mark_duplicate(lifecycle, duplicate_of="o", actor="user", now=now)
    domain_resolve_incident(lifecycle, actor="user", now=now)
""")
            temp_path = f.name

        try:
            errors = verifier.check_transition_adapter_uses_lifecycle_core(temp_path)
            assert errors == [], f"Expected no errors for complete calls: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_transitions_missing_required_calls_fails(self) -> None:
        """Transitions module missing required calls should fail."""
        temp_dir = tempfile.mkdtemp()
        temp_path = Path(temp_dir) / "test_incident_lifecycle_transitions.py"
        try:
            # Only include some calls (missing several required ones)
            temp_path.write_text("""
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_collecting_evidence as domain_mark_collecting_evidence,
    mark_ready_for_review as domain_mark_ready_for_review,
)

def partial_transition(lifecycle, now):
    # Missing: mark_investigating, suppress_incident, mark_duplicate, resolve_incident
    domain_mark_collecting_evidence(lifecycle, bundle_id="b", actor="system", now=now)
    domain_mark_ready_for_review(lifecycle, review_packet_id="r", actor="diag", now=now)
""")

            errors = verifier.check_transition_adapter_uses_lifecycle_core(str(temp_path))
            # Should have errors for missing calls
            assert len(errors) > 0, "Expected errors for missing calls"
            # All missing calls should be reported
            assert any("domain_mark_investigating" in e for e in errors)
            assert any("domain_suppress_incident" in e for e in errors)
            assert any("domain_mark_duplicate" in e for e in errors)
            assert any("domain_resolve_incident" in e for e in errors)
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_verifier_passes_for_actual_transitions_module(self) -> None:
        """Verifier should pass for the actual transitions module."""
        transitions_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "collect"
            / "incident_lifecycle_transitions.py"
        )

        # This test checks if the transitions file exists and has required calls
        if transitions_module.exists():
            errors = verifier.check_transition_adapter_uses_lifecycle_core(str(transitions_module))
            # Should have no errors (all calls present)
            assert errors == [], f"Expected no errors for transitions module: {errors}"


if __name__ == "__main__":
    import unittest
    unittest.main()
