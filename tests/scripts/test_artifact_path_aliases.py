"""Tests for artifact path alias extraction and verification.

ACT-K9B-HULK-ARTIFACT-PATH-TYPES01.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary.artifact_paths import (
    PATH_ALIASES,
    check_artifact_path_aliases,
    extract_path_newtype_aliases,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"


class TestExtractPathNewTypeAliases:
    """Tests for path NewType alias extraction."""

    def test_extracts_from_actual_evidence_module(self) -> None:
        """Extracts values from actual incident_evidence.py."""
        aliases = extract_path_newtype_aliases(str(EVIDENCE_MODULE))
        assert "SafeRelativeArtifactPath" in aliases
        assert aliases["SafeRelativeArtifactPath"] == "str"

    def test_extracts_all_expected_aliases(self) -> None:
        """Extracts all expected NewType aliases."""
        aliases = extract_path_newtype_aliases(str(EVIDENCE_MODULE))
        for expected_alias in PATH_ALIASES:
            assert expected_alias in aliases, f"Missing alias: {expected_alias}"
            assert aliases[expected_alias] == "str"

    def test_returns_empty_for_missing_file(self) -> None:
        """Returns empty dict for missing file."""
        aliases = extract_path_newtype_aliases("/nonexistent/file.py")
        assert aliases == {}

    def test_returns_empty_for_invalid_syntax(self) -> None:
        """Returns empty dict for invalid syntax."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("this is not valid python #@$%")
            temp_path = f.name
        try:
            aliases = extract_path_newtype_aliases(temp_path)
            assert aliases == {}
        finally:
            Path(temp_path).unlink()


class TestCheckArtifactPathAliases:
    """Tests for artifact path alias verification."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py passes alias checks."""
        errors = check_artifact_path_aliases(str(EVIDENCE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_safe_relative_path_alias_missing(self) -> None:
        """Fails if SafeRelativeArtifactPath alias is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("LocalArtifactPath = NewType('LocalArtifactPath', str)\n")
            temp_path = f.name
        try:
            errors = check_artifact_path_aliases(temp_path)
            assert len(errors) > 0
            assert any("SafeRelativeArtifactPath" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_alias_not_based_on_str(self) -> None:
        """Fails if alias is not based on str."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("SafeRelativeArtifactPath = NewType('SafeRelativeArtifactPath', int)\n")
            temp_path = f.name
        try:
            errors = check_artifact_path_aliases(temp_path)
            assert len(errors) > 0
        finally:
            Path(temp_path).unlink()

    def test_passes_with_all_aliases(self) -> None:
        """Passes with all required aliases defined correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            for alias in sorted(PATH_ALIASES):
                f.write(f"{alias} = NewType('{alias}', str)\n")
            temp_path = f.name
        try:
            errors = check_artifact_path_aliases(temp_path)
            assert errors == [], f"Unexpected errors: {errors}"
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
