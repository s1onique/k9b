"""Tests for artifact path constructor extraction and verification.

ACT-K9B-HULK-ARTIFACT-PATH-TYPES01.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary.artifact_paths import (
    REQUIRED_CONSTRUCTORS,
    check_artifact_path_constructors,
    extract_constructor_functions,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"


class TestExtractConstructorFunctions:
    """Tests for constructor function extraction."""

    def test_extracts_from_actual_evidence_module(self) -> None:
        """Extracts constructor functions from actual incident_evidence.py."""
        constructors = extract_constructor_functions(str(EVIDENCE_MODULE))
        assert "make_safe_relative_artifact_path" in constructors

    def test_extracts_all_expected_constructors(self) -> None:
        """Extracts all expected constructor functions."""
        constructors = extract_constructor_functions(str(EVIDENCE_MODULE))
        for expected_constructor in REQUIRED_CONSTRUCTORS:
            assert expected_constructor in constructors, f"Missing constructor: {expected_constructor}"

    def test_returns_empty_set_for_missing_file(self) -> None:
        """Returns empty set for missing file."""
        constructors = extract_constructor_functions("/nonexistent/file.py")
        assert constructors == set()


class TestCheckArtifactPathConstructors:
    """Tests for artifact path constructor verification."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py passes constructor checks."""
        errors = check_artifact_path_constructors(str(EVIDENCE_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_constructor_missing(self) -> None:
        """Fails if required constructor is missing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n\n')
            f.write("def make_safe_relative_artifact_path(value: str):\n")
            f.write('    """Missing other constructors."""\n')
            f.write("    pass\n")
            temp_path = f.name
        try:
            errors = check_artifact_path_constructors(temp_path)
            assert len(errors) > 0
            assert any("make_local_artifact_path" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_passes_with_all_constructors(self) -> None:
        """Passes with all required constructors defined."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n\n')
            for constructor in sorted(REQUIRED_CONSTRUCTORS):
                f.write(f"def {constructor}(value: str):\n")
                f.write(f'    """{constructor}."""\n')
                f.write("    pass\n\n")
            temp_path = f.name
        try:
            errors = check_artifact_path_constructors(temp_path)
            assert errors == [], f"Unexpected errors: {errors}"
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
