"""Tests for evidence type scanning functions."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Import from the package using absolute imports from scripts root
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from incident_lifecycle_boundary.evidence_types_contract import (  # noqa: I001
    EXPECTED_EVIDENCE_KINDS,
    EXPECTED_EVIDENCE_ROLES,
)
from incident_lifecycle_boundary.evidence_types_scan import (  # noqa: I001
    check_evidence_dataclass_field_types,
    check_evidence_literal_usage,
    extract_evidence_kind_values,
    extract_evidence_role_values,
)


class TestLiteralSubscriptExtraction:
    """Tests for Literal subscript extraction for evidence types."""

    def test_extracts_role_values_from_literal(self) -> None:
        """Extracts role values from EvidenceRoleCode = Literal[...]."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
EvidenceRoleCode = Literal[
    "primary",
    "supporting",
    "snapshot",
]
''')
            temp_path = f.name

        try:
            roles = extract_evidence_role_values(temp_path)
            assert roles == {"primary", "supporting", "snapshot"}
        finally:
            Path(temp_path).unlink()

    def test_extracts_kind_values_from_literal(self) -> None:
        """Extracts kind values from EvidenceKindCode = Literal[...]."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
EvidenceKindCode = Literal[
    "snapshot_bundle",
    "review_packet",
    "log_excerpt",
]
''')
            temp_path = f.name

        try:
            kinds = extract_evidence_kind_values(temp_path)
            assert kinds == {"snapshot_bundle", "review_packet", "log_excerpt"}
        finally:
            Path(temp_path).unlink()

    def test_fails_if_role_alias_missing(self) -> None:
        """Fails if EvidenceRoleCode alias is missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
EvidenceKindCode = Literal["snapshot_bundle"]
''')
            temp_path = f.name

        try:
            roles = extract_evidence_role_values(temp_path)
            assert roles == set()
        finally:
            Path(temp_path).unlink()

    def test_fails_if_kind_alias_missing(self) -> None:
        """Fails if EvidenceKindCode alias is missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
EvidenceRoleCode = Literal["primary"]
''')
            temp_path = f.name

        try:
            kinds = extract_evidence_kind_values(temp_path)
            assert kinds == set()
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
            roles = extract_evidence_role_values(temp_path)
            assert roles == set()
        finally:
            Path(temp_path).unlink()

    def test_extracts_from_actual_evidence_module(self) -> None:
        """Extracts values from actual incident_evidence_types.py.

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
            roles = extract_evidence_role_values(str(evidence_module))
            assert "primary" in roles
            assert "supporting" in roles
            assert "snapshot" in roles
            kinds = extract_evidence_kind_values(str(evidence_module))
            assert "snapshot_bundle" in kinds
            assert "review_packet" in kinds


class TestEvidenceDataclassFieldTypes:
    """Tests for evidence dataclass field type checking."""

    def test_passes_for_enum_typed_fields(self) -> None:
        """Passes if fields use enum types (EvidenceRole, EvidenceKind)."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from enum import StrEnum

class EvidenceRole(StrEnum):
    PRIMARY = "primary"

class EvidenceKind(StrEnum):
    SNAPSHOT_BUNDLE = "snapshot_bundle"

class EvidenceLink:
    role: EvidenceRole  # OK - uses enum

class EvidenceArtifact:
    kind: EvidenceKind  # OK - uses enum
''')
            temp_path = f.name

        try:
            errors = check_evidence_dataclass_field_types(temp_path)
            assert errors == [], f"Expected no errors: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_if_role_typed_as_str(self) -> None:
        """Fails if EvidenceLink.role is typed as 'str'."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from enum import StrEnum

class EvidenceRole(StrEnum):
    SNAPSHOT = "snapshot"

class EvidenceLink:
    incident_id: str
    artifact_id: str
    role: str  # Too wide - should be EvidenceRole
''')
            temp_path = f.name

        try:
            errors = check_evidence_dataclass_field_types(temp_path)
            assert len(errors) > 0
            assert any("too wide" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_kind_typed_as_any(self) -> None:
        """Fails if EvidenceArtifact.kind is typed as 'Any'."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Any

class EvidenceArtifact:
    artifact_id: str
    kind: Any  # Too wide - should be EvidenceKind
''')
            temp_path = f.name

        try:
            errors = check_evidence_dataclass_field_types(temp_path)
            assert len(errors) > 0
            assert any("too wide" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_role_typed_as_sequence(self) -> None:
        """Fails if EvidenceLink.role is typed as Sequence[...]."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write('''
from typing import Sequence

class EvidenceLink:
    incident_id: str
    artifact_id: str
    role: Sequence[str]  # Too wide - should be EvidenceRole
''')
            temp_path = f.name

        try:
            errors = check_evidence_dataclass_field_types(temp_path)
            assert len(errors) > 0
            assert any("too wide" in e for e in errors)
        finally:
            Path(temp_path).unlink()


class TestEvidenceLiteralUsage:
    """Tests for evidence literal usage checking (context-aware)."""

    def test_detects_unknown_role_in_evidence_constructor(self) -> None:
        """Detects unknown evidence role in EvidenceLink(...) call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create an evidence module with unknown role in constructor
            prod_file = tmppath / "test_module.py"
            prod_file.write_text('EvidenceLink(role="unknown_role", incident_id="inc-1", artifact_id="art-1")\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                frozenset({"primary", "supporting", "snapshot", "review_packet", "debug"}),
                EXPECTED_EVIDENCE_KINDS,
            )
            assert len(errors) > 0
            assert "unknown_role" in errors[0]

    def test_detects_unknown_kind_in_evidence_constructor(self) -> None:
        """Detects unknown evidence kind in EvidenceArtifact(...) call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create an evidence module with unknown kind in constructor
            prod_file = tmppath / "test_module.py"
            prod_file.write_text('EvidenceArtifact(kind="unknown_kind", artifact_id="art-1", storage_ref="s3://x")\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                EXPECTED_EVIDENCE_ROLES,
                frozenset({"snapshot_bundle", "review_packet", "log_excerpt"}),
            )
            assert len(errors) > 0
            assert "unknown_kind" in errors[0]

    def test_allows_known_role_in_evidence_constructor(self) -> None:
        """Allows known evidence role values in EvidenceLink(...)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create an evidence module with valid role
            prod_file = tmppath / "test_module.py"
            prod_file.write_text('EvidenceLink(role="snapshot", incident_id="inc-1", artifact_id="art-1")\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                frozenset({"primary", "supporting", "snapshot", "review_packet", "debug"}),
                EXPECTED_EVIDENCE_KINDS,
            )
            assert errors == [], f"Expected no errors for known values: {errors}"

    def test_ignores_llm_chat_roles_without_evidence_context(self) -> None:
        """Ignores LLM/chat roles (system, user) without evidence context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a file with LLM/chat roles - no evidence context
            prod_file = tmppath / "llm_provider.py"
            prod_file.write_text('role="system"\ncontent="Hello"\nrole="user"\ncontent="Hi"\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                frozenset({"primary", "supporting", "snapshot", "review_packet", "debug"}),
                EXPECTED_EVIDENCE_KINDS,
            )
            # Should not flag LLM roles without evidence context
            assert not any("system" in e for e in errors)
            assert not any("user" in e for e in errors)

    def test_ignores_kubernetes_object_kinds_without_evidence_context(self) -> None:
        """Ignores Kubernetes object kinds (Pod, etc.) without evidence context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a file with K8s object kinds - no evidence context
            prod_file = tmppath / "k8s_resource.py"
            prod_file.write_text('{"kind": "Pod", "metadata": {"name": "test"}}\n{"kind": "Deployment"}\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                EXPECTED_EVIDENCE_ROLES,
                frozenset({"snapshot_bundle", "review_packet", "log_excerpt"}),
            )
            # Should not flag K8s kinds without evidence context
            assert not any("Pod" in e for e in errors)
            assert not any("Deployment" in e for e in errors)

    def test_detects_unknown_role_in_dict_with_evidence_keys(self) -> None:
        """Detects unknown role in dict with evidence-adjacent keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a file with dict containing evidence keys + unknown role
            prod_file = tmppath / "test_module.py"
            prod_file.write_text('{"role": "unknown_role", "artifact_id": "art-1"}\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                frozenset({"primary", "supporting", "snapshot", "review_packet", "debug"}),
                EXPECTED_EVIDENCE_KINDS,
            )
            assert len(errors) > 0
            assert "unknown_role" in errors[0]

    def test_detects_unknown_kind_in_dict_with_evidence_keys(self) -> None:
        """Detects unknown kind in dict with evidence-adjacent keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a file with dict containing evidence keys + unknown kind
            prod_file = tmppath / "test_module.py"
            prod_file.write_text('{"kind": "unknown_kind", "storage_ref": "s3://x"}\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                EXPECTED_EVIDENCE_ROLES,
                frozenset({"snapshot_bundle", "review_packet", "log_excerpt"}),
            )
            assert len(errors) > 0
            assert "unknown_kind" in errors[0]

    def test_allows_known_role_in_dict_with_evidence_keys(self) -> None:
        """Allows known role in dict with evidence-adjacent keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a file with valid evidence dict
            prod_file = tmppath / "test_module.py"
            prod_file.write_text('{"role": "snapshot", "artifact_id": "art-1"}\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                frozenset({"primary", "supporting", "snapshot", "review_packet", "debug"}),
                EXPECTED_EVIDENCE_KINDS,
            )
            assert errors == [], f"Expected no errors for known values: {errors}"

    def test_allows_enum_member_access(self) -> None:
        """Allows EvidenceRole.SNAPSHOT style enum member access."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a file using enum member access
            prod_file = tmppath / "test_module.py"
            prod_file.write_text('EvidenceLink(role=EvidenceRole.SNAPSHOT, incident_id="x", artifact_id="y")\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                frozenset({"primary", "supporting", "snapshot", "review_packet", "debug"}),
                EXPECTED_EVIDENCE_KINDS,
            )
            # Should not flag enum member access
            assert not any("EvidenceRole.SNAPSHOT" in e for e in errors)

    def test_skips_test_files(self) -> None:
        """Skips files in tests/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a test file that would have unknown literals in evidence context
            tests_dir = tmppath / "tests" / "unit"
            tests_dir.mkdir(parents=True)
            test_file = tests_dir / "test_module.py"
            test_file.write_text('EvidenceLink(role="unknown_in_test", incident_id="x", artifact_id="y")\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                frozenset({"primary", "supporting", "snapshot", "review_packet", "debug"}),
                EXPECTED_EVIDENCE_KINDS,
            )
            # Should not flag unknown literals in tests/
            assert not any("unknown_in_test" in e for e in errors)

    def test_skips_scripts_directory(self) -> None:
        """Skips files in scripts/ directory (verifier package)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a script file that would have unknown literals
            scripts_dir = tmppath / "scripts"
            scripts_dir.mkdir(parents=True)
            script_file = scripts_dir / "verify.py"
            script_file.write_text('EvidenceLink(role="unknown_in_script", incident_id="x", artifact_id="y")\n')

            errors = check_evidence_literal_usage(
                str(tmppath / "dummy.py"),
                tmppath,
                frozenset({"primary", "supporting", "snapshot", "review_packet", "debug"}),
                EXPECTED_EVIDENCE_KINDS,
            )
            # Should not flag unknown literals in scripts/
            assert not any("unknown_in_script" in e for e in errors)


if __name__ == "__main__":
    import unittest
    unittest.main()
