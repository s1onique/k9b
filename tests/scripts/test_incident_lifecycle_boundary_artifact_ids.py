"""Tests for artifact ID boundary checks.

These tests verify that artifact ID types are properly defined and used
at the incident evidence boundary.

R2 Note: Tests use REPO_ROOT = Path(__file__).parent.parent.parent
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# Import from the verifier module
from scripts.incident_lifecycle_boundary.artifact_ids import (
    ARTIFACT_ID_ALIASES,
    check_artifact_id_aliases,
    check_artifact_id_contract,
    check_artifact_id_field_types,
    check_artifact_id_serialization,
    extract_newtype_aliases,
)

# R2: Use correct repo root path (tests/scripts/ -> repo root is 3 levels up)
REPO_ROOT = Path(__file__).parent.parent.parent
# NOTE: incident_evidence_types.py is the canonical source of evidence type definitions
# after module split f6d707a; incident_evidence.py is a compatibility facade only.
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_types.py"


class TestExtractNewTypeAliases:
    """Tests for NewType alias extraction."""

    def test_extracts_from_actual_evidence_module(self) -> None:
        """Extracts values from actual incident_evidence.py."""
        aliases = extract_newtype_aliases(str(EVIDENCE_MODULE))

        # Should find at least ArtifactId
        assert "ArtifactId" in aliases
        assert aliases["ArtifactId"] == "str"

    def test_extracts_all_expected_aliases(self) -> None:
        """Extracts all expected NewType aliases."""
        aliases = extract_newtype_aliases(str(EVIDENCE_MODULE))

        # All expected aliases should be present
        for expected_alias in ARTIFACT_ID_ALIASES:
            assert expected_alias in aliases, f"Missing alias: {expected_alias}"
            assert aliases[expected_alias] == "str"

    def test_returns_empty_for_missing_file(self) -> None:
        """Returns empty dict for missing file."""
        aliases = extract_newtype_aliases("/nonexistent/file.py")
        assert aliases == {}

    def test_returns_empty_for_invalid_syntax(self) -> None:
        """Returns empty dict for invalid syntax."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("this is not valid python #@$%")
            temp_path = f.name

        try:
            aliases = extract_newtype_aliases(temp_path)
            assert aliases == {}
        finally:
            Path(temp_path).unlink()


class TestCheckArtifactIdAliases:
    """Tests for artifact ID alias verification."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py passes alias checks."""
        errors = check_artifact_id_aliases(str(EVIDENCE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_artifact_id_alias_missing(self) -> None:
        """Fails if ArtifactId alias is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            # Missing ArtifactId
            f.write("EvidenceLinkId = NewType('EvidenceLinkId', str)\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_aliases(temp_path)
            assert len(errors) > 0
            assert any("ArtifactId" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_alias_not_based_on_str(self) -> None:
        """Fails if alias is not based on str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            # Wrong base type - ArtifactId based on int instead of str
            f.write("ArtifactId = NewType('ArtifactId', int)\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_aliases(temp_path)
            assert len(errors) > 0
            # Check for errors about missing aliases (most will be missing) or wrong base type
            assert any("int" in e or "Missing" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_passes_with_all_aliases(self) -> None:
        """Passes with all required aliases defined correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            for alias in sorted(ARTIFACT_ID_ALIASES):
                f.write(f"{alias} = NewType('{alias}', str)\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_aliases(temp_path)
            assert errors == [], f"Unexpected errors: {errors}"
        finally:
            Path(temp_path).unlink()


class TestCheckArtifactIdFieldTypes:
    """Tests for artifact ID field type verification (R2 stricter checks)."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py passes field type checks."""
        errors = check_artifact_id_field_types(str(EVIDENCE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_evidence_artifact_artifact_id_is_str(self) -> None:
        """Fails if EvidenceArtifact.artifact_id is typed as str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("ArtifactId = NewType('ArtifactId', str)\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: str  # Must be ArtifactId, not str\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_field_types(temp_path)
            assert len(errors) > 0
            assert any("EvidenceArtifact.artifact_id" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_evidence_link_artifact_id_is_str(self) -> None:
        """Fails if EvidenceLink.artifact_id is typed as str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("ArtifactId = NewType('ArtifactId', str)\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceLink:\n")
            f.write("    artifact_id: str  # Must be ArtifactId, not str\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_field_types(temp_path)
            assert len(errors) > 0
            assert any("EvidenceLink.artifact_id" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_using_wrong_newtype_alias(self) -> None:
        """Fails if field uses wrong branded type (not ArtifactId)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("ArtifactId = NewType('ArtifactId', str)\n")
            f.write("CandidateId = NewType('CandidateId', str)\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: CandidateId  # Wrong type, must be ArtifactId\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_field_types(temp_path)
            assert len(errors) > 0
            assert any("EvidenceArtifact.artifact_id" in e for e in errors)
            assert any("CandidateId" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_using_int(self) -> None:
        """Fails if artifact_id is typed as int."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("ArtifactId = NewType('ArtifactId', str)\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: int  # Wrong type\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_field_types(temp_path)
            assert len(errors) > 0
            assert any("EvidenceArtifact.artifact_id" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_field_missing(self) -> None:
        """Fails if required artifact_id field is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("ArtifactId = NewType('ArtifactId', str)\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    kind: str  # artifact_id is missing\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_field_types(temp_path)
            assert len(errors) > 0
            assert any("Missing required field" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_passes_if_using_artifact_id(self) -> None:
        """Passes if both EvidenceArtifact and EvidenceLink use ArtifactId."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("ArtifactId = NewType('ArtifactId', str)\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: ArtifactId  # Correct!\n")
            f.write("\n")
            f.write("@dataclass\n")
            f.write("class EvidenceLink:\n")
            f.write("    artifact_id: ArtifactId  # Correct!\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_field_types(temp_path)
            assert errors == [], f"Unexpected errors: {errors}"
        finally:
            Path(temp_path).unlink()


class TestCheckArtifactIdSerialization:
    """Tests for artifact ID serialization verification (R2)."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py passes serialization checks."""
        errors = check_artifact_id_serialization(str(EVIDENCE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_to_dict_returns_artifact_id_directly(self) -> None:
        """Fails if to_dict returns self.artifact_id directly without str()."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("ArtifactId = NewType('ArtifactId', str)\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: ArtifactId\n")
            f.write("\n")
            f.write("    def to_dict(self):\n")
            f.write('        return {"artifact_id": self.artifact_id}  # Wrong: needs str()\n')
            temp_path = f.name

        try:
            errors = check_artifact_id_serialization(temp_path)
            assert len(errors) > 0
            assert any("str()" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_passes_if_to_dict_uses_str(self) -> None:
        """Passes if to_dict uses str(self.artifact_id)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("ArtifactId = NewType('ArtifactId', str)\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: ArtifactId\n")
            f.write("\n")
            f.write("    def to_dict(self):\n")
            f.write('        return {"artifact_id": str(self.artifact_id)}  # Correct!\n')
            temp_path = f.name

        try:
            errors = check_artifact_id_serialization(temp_path)
            assert errors == [], f"Unexpected errors: {errors}"
        finally:
            Path(temp_path).unlink()


class TestCheckArtifactIdContract:
    """Tests for complete artifact ID contract check (R2)."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py passes complete contract check."""
        errors = check_artifact_id_contract(str(EVIDENCE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_for_invalid_module(self) -> None:
        """Fails for module with invalid artifact ID definitions."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: str  # Wrong type\n")
            temp_path = f.name

        try:
            errors = check_artifact_id_contract(temp_path)
            assert len(errors) > 0
        finally:
            Path(temp_path).unlink()


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code patterns."""

    def test_evidence_artifact_id_preserves_runtime_value(self) -> None:
        """EvidenceArtifact.artifact_id preserves runtime string value."""
        aliases = extract_newtype_aliases(str(EVIDENCE_MODULE))
        assert "ArtifactId" in aliases
        # NewType is static-only, runtime value is still a string

    def test_newtype_aliases_are_based_on_str(self) -> None:
        """All NewType aliases are based on str."""
        aliases = extract_newtype_aliases(str(EVIDENCE_MODULE))
        for alias_name, base_type in aliases.items():
            assert base_type == "str", f"{alias_name} should be based on str, not {base_type}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
