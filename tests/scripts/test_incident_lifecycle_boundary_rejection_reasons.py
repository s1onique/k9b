"""Tests for the rejection reasons checks in the incident lifecycle boundary verifier."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Import the verifier package
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from incident_lifecycle_boundary.rejection_reasons import (
    check_reason_allowlist,
    check_rejection_reason_type_alias,
    extract_transition_rejection_reasons,
)


class TestLiteralSubscriptExtraction:
    """Tests for Literal subscript extraction."""

    def test_extracts_reasons_from_simple_literal(self) -> None:
        """Extracts reasons from TransitionRejectionReason = Literal["a", "b"]."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
TransitionRejectionReason = Literal[
    "terminal_incident",
    "invalid_transition",
]
''')
            temp_path = f.name

        try:
            reasons = extract_transition_rejection_reasons(temp_path)
            assert reasons == {"terminal_incident", "invalid_transition"}
        finally:
            Path(temp_path).unlink()

    def test_extracts_reasons_from_multiline_literal(self) -> None:
        """Extracts reasons from multiline Literal alias."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
TransitionRejectionReason = Literal[
    "terminal_incident",
    "invalid_transition",
    "missing_review_packet",
    "missing_snapshot_bundle",
    "duplicate_self_reference",
]
''')
            temp_path = f.name

        try:
            reasons = extract_transition_rejection_reasons(temp_path)
            assert reasons == {
                "terminal_incident",
                "invalid_transition",
                "missing_review_packet",
                "missing_snapshot_bundle",
                "duplicate_self_reference",
            }
        finally:
            Path(temp_path).unlink()

    def test_only_accepts_literal_subscript(self) -> None:
        """Only Literal[...] subscripts should be accepted, not other types."""
        # Test with NotLiteral (should return empty set)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

class NotLiteral:
    pass

# This should NOT be extracted - NotLiteral is not Literal
TransitionRejectionReason = NotLiteral["terminal_incident", "invalid_transition"]
''')
            temp_path = f.name

        try:
            reasons = extract_transition_rejection_reasons(temp_path)
            assert reasons == set(), f"Should return empty for NotLiteral: {reasons}"
        finally:
            Path(temp_path).unlink()

    def test_only_accepts_sequence_subscript(self) -> None:
        """Sequence[...] subscripts should be rejected."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Sequence

# This should NOT be extracted - Sequence is too wide
TransitionRejectionReason = Sequence[str]
''')
            temp_path = f.name

        try:
            reasons = extract_transition_rejection_reasons(temp_path)
            assert reasons == set(), f"Should return empty for Sequence: {reasons}"
        finally:
            Path(temp_path).unlink()

    def test_fails_if_alias_missing(self) -> None:
        """Fails if TransitionRejectionReason alias is missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
# No TransitionRejectionReason defined
OtherReason = Literal["a", "b"]
''')
            temp_path = f.name

        try:
            reasons = extract_transition_rejection_reasons(temp_path)
            assert reasons == set()
        finally:
            Path(temp_path).unlink()

    def test_fails_if_alias_empty(self) -> None:
        """Fails if alias is empty Literal."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
TransitionRejectionReason = Literal[()]
''')
            temp_path = f.name

        try:
            reasons = extract_transition_rejection_reasons(temp_path)
            assert reasons == set()
        finally:
            Path(temp_path).unlink()

    def test_returns_empty_for_syntax_error(self) -> None:
        """Returns empty set for files with syntax errors."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("def broken(\n")  # Syntax error
            temp_path = f.name

        try:
            reasons = extract_transition_rejection_reasons(temp_path)
            assert reasons == set()
        finally:
            Path(temp_path).unlink()

    def test_extracts_from_actual_domain_module(self) -> None:
        """Extracts reasons from actual incident_lifecycle.py."""
        domain_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "domain"
            / "incident_lifecycle.py"
        )
        if domain_module.exists():
            reasons = extract_transition_rejection_reasons(str(domain_module))
            assert "terminal_incident" in reasons
            assert "invalid_transition" in reasons
            assert "duplicate_self_reference" in reasons


class TestRejectionReasonTypeAliasCheck:
    """Tests for TransitionRejectionReason type alias verification."""

    def test_passes_for_correct_typed_alias(self) -> None:
        """Passes if TransitionRejected.reason is typed as TransitionRejectionReason."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

TransitionRejectionReason = Literal[
    "terminal_incident",
    "invalid_transition",
    "missing_review_packet",
    "missing_snapshot_bundle",
    "duplicate_self_reference",
]

@dataclass
class TransitionRejected:
    incident: str
    reason: TransitionRejectionReason
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert errors == [], f"Expected no errors: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_if_alias_missing(self) -> None:
        """Fails if TransitionRejectionReason alias is missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
@dataclass
class TransitionRejected:
    incident: str
    reason: str
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert len(errors) > 0
            assert "missing" in errors[0].lower() or "expected" in errors[0].lower()
        finally:
            Path(temp_path).unlink()

    def test_fails_if_reason_typed_as_str(self) -> None:
        """Fails if TransitionRejected.reason is typed as 'str'."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

TransitionRejectionReason = Literal["terminal_incident"]

@dataclass
class TransitionRejected:
    incident: str
    reason: str  # Should be TransitionRejectionReason
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert len(errors) > 0
            assert any("typed as 'str'" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_passes_for_actual_domain_module(self) -> None:
        """Actual incident_lifecycle.py passes type alias checks."""
        domain_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "domain"
            / "incident_lifecycle.py"
        )
        if domain_module.exists():
            errors = check_rejection_reason_type_alias(str(domain_module))
            assert errors == [], f"Expected no errors for actual module: {errors}"

    def test_alias_values_match_expected_contract(self) -> None:
        """Alias values must match the expected stable contract."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
# Missing "terminal_incident" - should fail
TransitionRejectionReason = Literal["invalid_transition"]
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert len(errors) > 0
            assert any("missing" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_transition_rejected_class_missing(self) -> None:
        """Fails if TransitionRejected class is missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

TransitionRejectionReason = Literal["terminal_incident", "invalid_transition"]

# No TransitionRejected class defined
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert len(errors) > 0
            assert any("missing" in e.lower() and "class" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_reason_field_missing(self) -> None:
        """Fails if TransitionRejected.reason field is missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

TransitionRejectionReason = Literal["terminal_incident", "invalid_transition"]

@dataclass
class TransitionRejected:
    incident: str
    # No reason field defined
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert len(errors) > 0
            assert any("reason" in e.lower() and "field" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_reason_typed_as_object(self) -> None:
        """Fails if TransitionRejected.reason is typed as 'object'."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

TransitionRejectionReason = Literal["terminal_incident"]

@dataclass
class TransitionRejected:
    incident: str
    reason: object  # Should be TransitionRejectionReason
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert len(errors) > 0
            assert any("too wide" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_reason_typed_as_any(self) -> None:
        """Fails if TransitionRejected.reason is typed as 'Any'."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal, Any

TransitionRejectionReason = Literal["terminal_incident"]

@dataclass
class TransitionRejected:
    incident: str
    reason: Any  # Should be TransitionRejectionReason
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert len(errors) > 0
            assert any("too wide" in e or "Any" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_reason_typed_as_sequence(self) -> None:
        """Fails if TransitionRejected.reason is typed as Sequence[...]."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal, Sequence

TransitionRejectionReason = Literal["terminal_incident"]

@dataclass
class TransitionRejected:
    incident: str
    reason: Sequence[str]  # Should be TransitionRejectionReason
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            assert len(errors) > 0
            assert any("too wide" in e or "Sequence" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_passes_only_for_transition_rejection_reason_type(self) -> None:
        """Passes only for reason: TransitionRejectionReason, not widened types."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Literal

TransitionRejectionReason = Literal[
    "terminal_incident",
    "invalid_transition",
    "missing_review_packet",
    "missing_snapshot_bundle",
    "duplicate_self_reference",
]

@dataclass
class TransitionRejected:
    incident: str
    reason: TransitionRejectionReason  # Exactly correct
''')
            temp_path = f.name

        try:
            errors = check_rejection_reason_type_alias(temp_path)
            # Should have no errors - this is the correct pattern
            assert errors == [], f"Expected no errors for correct type: {errors}"
        finally:
            Path(temp_path).unlink()


class TestReasonAllowlistCheck:
    """Tests for rejection reason allowlist enforcement."""

    def test_reason_allowlist_enforced(self) -> None:
        """Rejection reasons must be in the allowlist."""
        domain_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "domain"
            / "incident_lifecycle.py"
        )
        errors = check_reason_allowlist(str(domain_module))
        assert errors == [], f"Unknown rejection reasons found: {errors}"

    def test_detects_unknown_string_reason(self) -> None:
        """Should detect unknown rejection reason string values.
        
        Note: The actual domain module uses constants (reason=_REJECT_TERMINAL_INCIDENT),
        but this checks the fallback pattern for direct string literals.
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            # Use a simple file that might contain reason= patterns
            f.write('reason="unknown_code"\n')
            temp_path = f.name

        try:
            errors = check_reason_allowlist(temp_path)
            # When extraction fails (no TransitionRejectionReason), falls back to static allowlist
            # "unknown_code" is not in the fallback allowlist, so should error
            assert len(errors) > 0
            assert "unknown_code" in errors[0]
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    import unittest
    unittest.main()
