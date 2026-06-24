#!/usr/bin/env python3
"""Tests for promotion script and provenance verification."""
from __future__ import annotations

import sys
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from promote_diagnosis_golden_case_from_artifact import (
    compute_content_hash,
    validate_provenance_metadata,
    validate_raw_artifact_path,
)
from verify_provenance_golden_case import (
    verify_github_artifact_digest,
    verify_promotion_flag,
    verify_provenance_hash,
    verify_source_kind,
    verify_truthfulness,
)

# =============================================================================
# Tests for validate_raw_artifact_path
# =============================================================================

class TestValidateProvenanceMetadata:
    """Tests for provenance metadata truthfulness validation."""

    def test_rejects_placeholder_workflow_id(self) -> None:
        """Should reject placeholder workflow_run_id."""
        is_valid, error_msg = validate_provenance_metadata(
            "12345678",  # placeholder
            "a" * 40,
            "sha256:" + "a" * 64,
        )
        assert not is_valid
        assert "placeholder" in error_msg.lower()

    def test_rejects_short_sha(self) -> None:
        """Should reject workflow_sha that is not 40 hex chars."""
        is_valid, error_msg = validate_provenance_metadata(
            "987654321",
            "abc123def456789",  # only 15 chars
            "sha256:" + "a" * 64,
        )
        assert not is_valid
        assert "40 hex" in error_msg

    def test_rejects_truncated_digest(self) -> None:
        """Should reject truncated artifact digest."""
        is_valid, error_msg = validate_provenance_metadata(
            "987654321",
            "a" * 40,
            "sha256:abc123",  # too short
        )
        assert not is_valid
        assert "truncated" in error_msg.lower()

    def test_accepts_valid_provenance(self) -> None:
        """Should accept real GitHub provenance data."""
        is_valid, error_msg = validate_provenance_metadata(
            "987654321",
            "a" * 40,
            "sha256:" + "a" * 64,
        )
        assert is_valid
        assert error_msg == ""


class TestValidateRawArtifactPath:
    """Tests for raw artifact path validation."""

    def test_rejects_raw_live_path(self, tmp_path: Path) -> None:
        """Should reject paths containing lab-artifacts/live/ without sanitized."""
        artifact_dir = tmp_path / "lab-artifacts" / "live" / "pod-failure"
        artifact_dir.mkdir(parents=True)

        is_valid, error_msg = validate_raw_artifact_path(artifact_dir)
        assert not is_valid
        assert "lab-artifacts/live" in error_msg
        # Error message should indicate raw artifacts are forbidden
        assert "forbidden" in error_msg.lower() or "must use" in error_msg.lower()

    def test_accepts_sanitized_path(self, tmp_path: Path) -> None:
        """Should accept paths containing live-sanitized."""
        artifact_dir = tmp_path / "lab-artifacts" / "live-sanitized" / "pod-failure"
        artifact_dir.mkdir(parents=True)

        is_valid, error_msg = validate_raw_artifact_path(artifact_dir)
        assert is_valid
        assert error_msg == ""


# =============================================================================
# Tests for compute_content_hash (determinism)
# =============================================================================

class TestComputeContentHash:
    """Tests for deterministic content hash."""

    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Hash should be stable across repeated runs."""
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        # Create test files
        (artifact_dir / "file1.txt").write_text("content1")
        (artifact_dir / "file2.json").write_text('{"key": "value"}')

        # Compute hash twice
        hash1 = compute_content_hash(artifact_dir)
        hash2 = compute_content_hash(artifact_dir)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_hash_changes_with_content(self, tmp_path: Path) -> None:
        """Hash should change when content changes."""
        artifact_dir1 = tmp_path / "artifacts1"
        artifact_dir2 = tmp_path / "artifacts2"
        artifact_dir1.mkdir()
        artifact_dir2.mkdir()

        (artifact_dir1 / "file.txt").write_text("original")
        (artifact_dir2 / "file.txt").write_text("modified")

        hash1 = compute_content_hash(artifact_dir1)
        hash2 = compute_content_hash(artifact_dir2)

        assert hash1 != hash2

    def test_hash_excludes_findings_marker(self, tmp_path: Path) -> None:
        """Hash should exclude _findings.json marker file."""
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        (artifact_dir / "file.txt").write_text("content")
        (artifact_dir / "_findings.json").write_text('{"success": true}')

        hash1 = compute_content_hash(artifact_dir)

        # Remove findings and verify hash is same
        (artifact_dir / "_findings.json").unlink()
        hash2 = compute_content_hash(artifact_dir)

        assert hash1 == hash2


# =============================================================================
# Tests for provenance verifier functions
# =============================================================================

class TestVerifySourceKind:
    """Tests for source_kind verification."""

    def test_representative_fixture_is_not_promoted(self) -> None:
        """Should return is_promoted=False when source_kind is representative_fixture."""
        manifest: dict[str, object] = {"source_kind": "representative_fixture"}
        is_promoted, failures = verify_source_kind(manifest)
        assert not is_promoted
        assert len(failures) == 0  # Not a failure, just not promoted

    def test_passes_on_live_sanitized_artifact(self) -> None:
        """Should return is_promoted=True when source_kind is live_sanitized_artifact."""
        manifest: dict[str, object] = {"source_kind": "live_sanitized_artifact"}
        is_promoted, failures = verify_source_kind(manifest)
        assert is_promoted
        assert len(failures) == 0

    def test_fails_on_unknown_kind(self) -> None:
        """Should fail when source_kind is unknown."""
        manifest: dict[str, object] = {"source_kind": "unknown_kind"}
        is_promoted, failures = verify_source_kind(manifest)
        assert not is_promoted
        assert len(failures) == 1
        assert "unknown_kind" in failures[0]


class TestVerifyProvenanceHash:
    """Tests for provenance hash verification."""

    def test_fails_on_null_hash(self) -> None:
        """Should fail when artifacts_hash is null."""
        manifest = {"provenance": {"artifacts_hash": None}}
        failures = verify_provenance_hash(manifest)
        assert len(failures) == 1
        assert "null" in failures[0].lower()

    def test_fails_on_missing_hash(self) -> None:
        """Should fail when artifacts_hash is missing."""
        manifest: dict[str, object] = {"provenance": {}}
        failures = verify_provenance_hash(manifest)
        assert len(failures) == 1

    def test_passes_on_valid_hash(self) -> None:
        """Should pass when artifacts_hash is a valid hex string."""
        manifest: dict[str, object] = {"provenance": {"artifacts_hash": "abc123def456"}}
        failures = verify_provenance_hash(manifest)
        assert len(failures) == 0


class TestVerifyGithubArtifactDigest:
    """Tests for GitHub artifact digest verification."""

    def test_fails_on_missing_digest(self) -> None:
        """Should fail when github_artifact_digest is missing."""
        manifest: dict[str, object] = {"provenance": {}}
        failures = verify_github_artifact_digest(manifest)
        assert len(failures) == 1

    def test_fails_on_invalid_format(self) -> None:
        """Should fail when digest doesn't start with sha256:."""
        manifest = {"provenance": {"github_artifact_digest": "invalid-format"}}
        failures = verify_github_artifact_digest(manifest)
        assert len(failures) == 1
        assert "sha256" in failures[0]

    def test_passes_on_valid_digest(self) -> None:
        """Should pass when digest has valid sha256: format."""
        manifest: dict[str, object] = {"provenance": {"github_artifact_digest": "sha256:abc123"}}
        failures = verify_github_artifact_digest(manifest)
        assert len(failures) == 0


class TestVerifyPromotionFlag:
    """Tests for real_live_artifact_required_for_promotion flag."""

    def test_fails_when_true(self) -> None:
        """Should fail when flag is true."""
        manifest: dict[str, object] = {"provenance": {"real_live_artifact_required_for_promotion": True}}
        failures = verify_promotion_flag(manifest)
        assert len(failures) == 1
        assert "true" in failures[0].lower()

    def test_passes_when_false(self) -> None:
        """Should pass when flag is false."""
        manifest: dict[str, object] = {"provenance": {"real_live_artifact_required_for_promotion": False}}
        failures = verify_promotion_flag(manifest)
        assert len(failures) == 0


class TestVerifyTruthfulness:
    """Tests for truthfulness checks (no placeholder/mock data)."""

    def test_fails_on_placeholder_workflow_id(self) -> None:
        """Should fail when workflow_run_id is placeholder."""
        manifest: dict[str, object] = {"provenance": {"workflow_run_id": "12345678"}}
        failures = verify_truthfulness(manifest)
        assert len(failures) >= 1
        assert any("placeholder" in f.lower() for f in failures)

    def test_fails_on_short_sha(self) -> None:
        """Should fail when workflow_sha is not 40 hex chars."""
        manifest: dict[str, object] = {"provenance": {"workflow_sha": "abc123def456789"}}
        failures = verify_truthfulness(manifest)
        assert len(failures) >= 1
        assert any("placeholder" in f.lower() or "40 hex" in f.lower() for f in failures)

    def test_fails_on_truncated_digest(self) -> None:
        """Should fail when digest is truncated."""
        manifest: dict[str, object] = {"provenance": {"github_artifact_digest": "sha256:a1b2c3d4e5f6789"}}
        failures = verify_truthfulness(manifest)
        assert len(failures) >= 1
        assert any("truncated" in f.lower() for f in failures)

    def test_passes_on_valid_full_sha(self) -> None:
        """Should pass when workflow_sha is valid 40 hex chars."""
        manifest: dict[str, object] = {"provenance": {"workflow_sha": "a" * 40}}
        failures = verify_truthfulness(manifest)
        assert len(failures) == 0

    def test_passes_on_valid_digest(self) -> None:
        """Should pass when digest is valid sha256: + 64 hex chars."""
        manifest: dict[str, object] = {"provenance": {"github_artifact_digest": "sha256:" + "a" * 64}}
        failures = verify_truthfulness(manifest)
        assert len(failures) == 0
