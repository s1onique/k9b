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
    """Tests for direct .status assignment detection."""

    def test_status_assignment_plain_detected_in_non_allowlisted_file(self) -> None:
        """Plain .status assignment (Assign) in non-allowlisted file should be detected."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            # Plain assignment (most common form)
            f.write("incident.status = 'resolved'\n")
            temp_path = f.name

        try:
            errors = verifier.check_status_assignments(temp_path)
            assert len(errors) == 1, f"Expected 1 error, got: {errors}"
            assert "'incident'" in errors[0]
            assert "outside allowed files" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_status_assignment_annotated_detected_in_non_allowlisted_file(self) -> None:
        """Annotated .status assignment (AnnAssign) in non-allowlisted file should be detected."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            # Annotated assignment
            f.write("incident.status: str = 'resolved'\n")
            temp_path = f.name

        try:
            errors = verifier.check_status_assignments(temp_path)
            assert len(errors) == 1, f"Expected 1 error, got: {errors}"
            assert "'incident'" in errors[0]
            assert "outside allowed files" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_status_assignment_passes_in_allowlisted_file(self) -> None:
        """Direct .status assignment in allowlisted file should pass."""
        # Create a temp file in the allowed directory with a predictable relative path
        temp_path = "src/k8s_diag_agent/collect/test_incident_store.py"
        with open(temp_path, "w") as f:
            f.write("incident.status = 'resolved'\n")

        try:
            # Check with the allowlisted path
            original = verifier._ALLOWED_STATUS_MUTATION_FILES.copy()
            verifier._ALLOWED_STATUS_MUTATION_FILES = {
                "src/k8s_diag_agent/collect/incident_store.py",
                "src/k8s_diag_agent/collect/test_incident_store.py",
            }
            try:
                errors = verifier.check_status_assignments(temp_path)
                assert errors == [], f"Expected no errors for allowlisted file: {errors}"
            finally:
                verifier._ALLOWED_STATUS_MUTATION_FILES = original
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
