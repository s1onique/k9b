"""Tests for storage_ref field type enforcement.

ACT-K9B-HULK-ARTIFACT-PATH-TYPES01.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary.artifact_paths import (
    check_storage_ref_field_type,
    check_storage_ref_serialization,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"


class TestCheckStorageRefFieldType:
    """Tests for EvidenceArtifact.storage_ref field type enforcement."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py has properly typed storage_ref."""
        errors = check_storage_ref_field_type(str(EVIDENCE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_storage_ref_is_raw_str(self) -> None:
        """Fails if EvidenceArtifact.storage_ref is typed as raw str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: str\n")
            f.write("    storage_ref: str\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_field_type(temp_path)
            assert len(errors) > 0, "Should fail when storage_ref is raw str"
            assert any("str" in e for e in errors), f"Error should mention 'str': {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_if_storage_ref_is_any(self) -> None:
        """Fails if EvidenceArtifact.storage_ref is typed as Any."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import Any\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: str\n")
            f.write("    storage_ref: Any\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_field_type(temp_path)
            assert len(errors) > 0, "Should fail when storage_ref is Any"
            assert any("Any" in e for e in errors), f"Error should mention 'Any': {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_if_storage_ref_is_object(self) -> None:
        """Fails if EvidenceArtifact.storage_ref is typed as object."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: str\n")
            f.write("    storage_ref: object\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_field_type(temp_path)
            assert len(errors) > 0, "Should fail when storage_ref is object"
            assert any("object" in e for e in errors), f"Error should mention 'object': {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_if_storage_ref_is_int(self) -> None:
        """Fails if EvidenceArtifact.storage_ref is typed as int."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: str\n")
            f.write("    storage_ref: int\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_field_type(temp_path)
            assert len(errors) > 0, "Should fail when storage_ref is int"
            assert any("int" in e for e in errors), f"Error should mention 'int': {errors}"
        finally:
            Path(temp_path).unlink()

    def test_passes_if_storage_ref_is_artifact_storage_ref(self) -> None:
        """Passes if EvidenceArtifact.storage_ref is typed as ArtifactStorageRef."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("SafeRelativeArtifactPath = NewType('SafeRelativeArtifactPath', str)\n")
            f.write("LocalArtifactPath = NewType('LocalArtifactPath', str)\n")
            f.write("ExternalStorageRef = NewType('ExternalStorageRef', str)\n")
            f.write("ArtifactStorageRef = SafeRelativeArtifactPath | LocalArtifactPath | ExternalStorageRef\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: str\n")
            f.write("    storage_ref: ArtifactStorageRef\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_field_type(temp_path)
            assert errors == [], f"Should pass when storage_ref is ArtifactStorageRef: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_passes_if_storage_ref_is_valid_union(self) -> None:
        """Passes if EvidenceArtifact.storage_ref is typed as valid union."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n")
            f.write("from typing import NewType\n\n")
            f.write("SafeRelativeArtifactPath = NewType('SafeRelativeArtifactPath', str)\n")
            f.write("LocalArtifactPath = NewType('LocalArtifactPath', str)\n")
            f.write("ExternalStorageRef = NewType('ExternalStorageRef', str)\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    artifact_id: str\n")
            f.write("    storage_ref: SafeRelativeArtifactPath | LocalArtifactPath | ExternalStorageRef\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_field_type(temp_path)
            assert errors == [], f"Should pass with valid union type: {errors}"
        finally:
            Path(temp_path).unlink()

class TestCheckStorageRefSerialization:
    """Tests for EvidenceArtifact.to_dict() serialization enforcement."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py has proper serialization."""
        errors = check_storage_ref_serialization(str(EVIDENCE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_to_dict_returns_direct_self_storage_ref(self) -> None:
        """Fails if to_dict() returns {'storage_ref': self.storage_ref} directly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    storage_ref: str\n")
            f.write("    def to_dict(self):\n")
            f.write("        return {'storage_ref': self.storage_ref}\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_serialization(temp_path)
            assert len(errors) > 0, "Should fail when storage_ref is returned directly"
            assert any("str(self.storage_ref)" in e for e in errors), f"Error should mention str(self.storage_ref): {errors}"
        finally:
            Path(temp_path).unlink()

    def test_passes_if_to_dict_returns_str_self_storage_ref(self) -> None:
        """Passes if to_dict() returns {'storage_ref': str(self.storage_ref)}."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    storage_ref: str\n")
            f.write("    def to_dict(self):\n")
            f.write("        return {'storage_ref': str(self.storage_ref)}\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_serialization(temp_path)
            assert errors == [], f"Should pass with str(self.storage_ref): {errors}"
        finally:
            Path(temp_path).unlink()

    def test_passes_for_module_without_to_dict(self) -> None:
        """Passes for module without to_dict method."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from dataclasses import dataclass\n\n")
            f.write("@dataclass\n")
            f.write("class EvidenceArtifact:\n")
            f.write("    storage_ref: str\n")
            temp_path = f.name
        try:
            errors = check_storage_ref_serialization(temp_path)
            assert errors == [], f"Should pass without to_dict: {errors}"
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
