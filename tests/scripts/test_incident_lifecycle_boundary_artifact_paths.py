"""Tests for artifact path/reference boundary checks.

ACT-K9B-HULK-ARTIFACT-PATH-TYPES01.

Note: Tests are split across multiple modules:
- test_artifact_path_aliases.py: alias extraction and verification
- test_artifact_path_constructors.py: constructor extraction and verification
- test_artifact_path_storage_ref.py: storage_ref field type enforcement
- test_incident_lifecycle_boundary_artifact_paths.py: contract, boundary, and integration tests
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary.artifact_paths import (
    check_artifact_path_contract,
    check_llm_review_path_boundaries,
    check_unsafe_literal_constructor_calls,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"


class TestCheckUnsafeLiteralConstructorCalls:
    """Tests for detecting unsafe constructor usage patterns."""

    def test_detects_absolute_path_in_safe_relative(self) -> None:
        """Detects make_safe_relative_artifact_path('/absolute/path')."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n\n')
            f.write('make_safe_relative_artifact_path("/var/lib/secret")\n')
            temp_path = f.name
        try:
            errors = check_unsafe_literal_constructor_calls(temp_path)
            assert len(errors) > 0
            assert any("absolute path" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_detects_traversal_path_in_safe_relative(self) -> None:
        """Detects make_safe_relative_artifact_path('../secret')."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n\n')
            f.write('make_safe_relative_artifact_path("../secret")\n')
            temp_path = f.name
        try:
            errors = check_unsafe_literal_constructor_calls(temp_path)
            assert len(errors) > 0
            assert any("traversal path" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_detects_s3_url_in_safe_relative(self) -> None:
        """Detects make_safe_relative_artifact_path('s3://bucket/key')."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n\n')
            f.write('make_safe_relative_artifact_path("s3://bucket/secret")\n')
            temp_path = f.name
        try:
            errors = check_unsafe_literal_constructor_calls(temp_path)
            assert len(errors) > 0
            assert any("s3://" in e or "URL scheme" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_ignores_safe_constructor_usages(self) -> None:
        """Does not flag safe relative path constructors with valid paths."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n\n')
            f.write('make_safe_relative_artifact_path("incidents/inc-123/snapshot.json")\n')
            f.write('make_external_storage_ref("s3://bucket/incidents/inc-123/snapshot.json")\n')
            temp_path = f.name
        try:
            errors = check_unsafe_literal_constructor_calls(temp_path)
            assert not any("s3://" in e and "safe_relative" in e.lower() for e in errors)
        finally:
            Path(temp_path).unlink()


class TestCheckLlmReviewPathBoundaries:
    """Tests for LLM/review path boundary violations."""

    def test_detects_local_artifact_path_in_llm_module(self) -> None:
        """Detects LocalArtifactPath usage in LLM/review modules."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            fake_llm_path = tmp_root / "src" / "k8s_diag_agent" / "collect" / "incident_llm_diagnosis.py"
            fake_llm_path.parent.mkdir(parents=True, exist_ok=True)
            fake_llm_path.write_text(
                '"""Fake LLM diagnosis module."""\n\n'
                'from typing import NewType\n'
                "LocalArtifactPath = NewType('LocalArtifactPath', str)\n"
                "path: LocalArtifactPath = '/var/lib/k9b/secret'\n"
            )
            errors = check_llm_review_path_boundaries(tmp_root)
            assert len(errors) >= 1, "Should detect LocalArtifactPath in LLM/review modules"
            assert any("incident_llm_diagnosis.py" in e for e in errors)

    def test_no_violation_when_llm_modules_are_clean(self) -> None:
        """No violations when LLM modules don't use LocalArtifactPath."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            fake_llm_path = tmp_root / "src" / "k8s_diag_agent" / "collect" / "incident_llm_diagnosis.py"
            fake_llm_path.parent.mkdir(parents=True, exist_ok=True)
            fake_llm_path.write_text(
                '"""Fake LLM diagnosis module."""\n\n'
                "SafeRelativeArtifactPath = 'relative/path'\n"
            )
            errors = check_llm_review_path_boundaries(tmp_root)
            assert not any("LocalArtifactPath" in e for e in errors)


class TestCheckArtifactPathContract:
    """Tests for complete artifact path contract check."""

    def test_passes_for_actual_evidence_module(self) -> None:
        """Actual incident_evidence.py passes complete contract check."""
        errors = check_artifact_path_contract(
            evidence_filepath=str(EVIDENCE_MODULE),
            repo_root=REPO_ROOT,
        )
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_for_invalid_module(self) -> None:
        """Fails for module with missing path type definitions."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("# Missing all path aliases and constructors\n")
            temp_path = f.name
        try:
            errors = check_artifact_path_contract(
                evidence_filepath=temp_path,
                repo_root=REPO_ROOT,
            )
            assert len(errors) > 0
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
