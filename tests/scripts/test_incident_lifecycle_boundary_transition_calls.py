"""Tests for the transition adapter calls checks in the incident lifecycle boundary verifier."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

# Import the verifier package
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from incident_lifecycle_boundary.transition_adapter_calls import (
    REQUIRED_LIFECYCLE_CALLS,
    _get_called_names,
    check_transition_adapter_uses_lifecycle_core,
)


class TestTransitionAdapterUsesLifecycleCore:
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
            errors = check_transition_adapter_uses_lifecycle_core(temp_path)
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

            errors = check_transition_adapter_uses_lifecycle_core(str(temp_path))
            # Should have errors for missing calls
            assert len(errors) > 0, "Expected errors for missing calls"
            # All missing calls should be reported
            assert any("domain_mark_investigating" in e for e in errors)
            assert any("domain_suppress_incident" in e for e in errors)
            assert any("domain_mark_duplicate" in e for e in errors)
            assert any("domain_resolve_incident" in e for e in errors)
        finally:
            shutil.rmtree(temp_dir)

    def test_imports_without_calls_fail(self) -> None:
        """Transitions module with only imports but no calls should fail."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("""
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_collecting_evidence as domain_mark_collecting_evidence,
)

# No actual function calls
""")
            temp_path = f.name

        try:
            errors = check_transition_adapter_uses_lifecycle_core(temp_path)
            assert len(errors) > 0, "Expected errors for missing calls"
        finally:
            Path(temp_path).unlink()

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
            errors = check_transition_adapter_uses_lifecycle_core(str(transitions_module))
            # Should have no errors (all calls present)
            assert errors == [], f"Expected no errors for transitions module: {errors}"

    def test_handles_missing_file(self) -> None:
        """Should handle missing files gracefully."""
        errors = check_transition_adapter_uses_lifecycle_core("/nonexistent/file.py")
        assert len(errors) == 1
        assert "Cannot read" in errors[0]

    def test_handles_syntax_error(self) -> None:
        """Should handle syntax errors gracefully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("def broken(\n")  # Syntax error
            temp_path = f.name

        try:
            errors = check_transition_adapter_uses_lifecycle_core(temp_path)
            assert len(errors) == 1
            assert "Syntax error" in errors[0]
        finally:
            Path(temp_path).unlink()


class TestGetCalledNames:
    """Tests for the _get_called_names helper function."""

    def test_extracts_simple_call(self) -> None:
        """Should extract simple function call names."""
        import ast
        tree = ast.parse("foo()")
        names = _get_called_names(tree)
        assert names == {"foo"}

    def test_extracts_multiple_calls(self) -> None:
        """Should extract multiple function call names."""
        import ast
        tree = ast.parse("foo(); bar(); baz()")
        names = _get_called_names(tree)
        assert names == {"foo", "bar", "baz"}

    def test_ignores_attribute_calls(self) -> None:
        """Should ignore method calls (attribute access)."""
        import ast
        tree = ast.parse("obj.method()")
        names = _get_called_names(tree)
        assert names == set()

    def test_ignores_non_call_nodes(self) -> None:
        """Should ignore non-call nodes."""
        import ast
        tree = ast.parse("x = 1")
        names = _get_called_names(tree)
        assert names == set()


class TestRequiredLifecycleCalls:
    """Tests for the REQUIRED_LIFECYCLE_CALLS constant."""

    def test_has_all_expected_calls(self) -> None:
        """Should have all expected lifecycle calls."""
        expected = {
            "domain_mark_collecting_evidence",
            "domain_mark_ready_for_review",
            "domain_mark_investigating",
            "domain_suppress_incident",
            "domain_mark_duplicate",
            "domain_resolve_incident",
        }
        assert REQUIRED_LIFECYCLE_CALLS == expected

    def test_is_frozenset(self) -> None:
        """Should be a frozenset (immutable)."""
        assert isinstance(REQUIRED_LIFECYCLE_CALLS, frozenset)


if __name__ == "__main__":
    import unittest
    unittest.main()
