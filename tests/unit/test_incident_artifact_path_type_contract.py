"""Tests for artifact path/reference type contracts.

These tests verify that the branded path/reference types in incident_evidence.py
behave correctly according to the ACT-K9B-HULK-ARTIFACT-PATH-TYPES01 contract.

Design:
- SafeRelativeArtifactPath: relative paths safe for review/LLM boundaries
- LocalArtifactPath: local filesystem paths (implementation only)
- ExternalStorageRef: external storage references (s3://, gs://, etc.)
- ReviewPacketStorageRef: storage refs for review packet boundaries
- LLMSafeArtifactRef: artifact refs safe for LLM-facing outputs
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_evidence import (
    EvidenceArtifact,
    EvidenceKind,
    make_external_storage_ref,
    make_llm_safe_artifact_ref,
    make_llm_safe_artifact_ref_from_safe_path,
    make_local_artifact_path,
    make_review_packet_storage_ref,
    make_safe_relative_artifact_path,
)


class TestSafeRelativeArtifactPath:
    """Tests for SafeRelativeArtifactPath constructor validation."""

    def test_accepts_simple_relative_path(self) -> None:
        """Accepts simple relative artifact paths."""
        result = make_safe_relative_artifact_path("incidents/inc-123/snapshot.json")
        assert result == "incidents/inc-123/snapshot.json"
        assert isinstance(result, str)  # NewType is str at runtime

    def test_accepts_nested_relative_path(self) -> None:
        """Accepts nested relative artifact paths."""
        result = make_safe_relative_artifact_path("artifacts/bundle/2024/01/snapshot.tar.gz")
        assert result == "artifacts/bundle/2024/01/snapshot.tar.gz"

    def test_rejects_empty_string(self) -> None:
        """Rejects empty strings."""
        with pytest.raises(ValueError, match="empty or has whitespace"):
            make_safe_relative_artifact_path("")

    def test_rejects_whitespace_only(self) -> None:
        """Rejects whitespace-only strings."""
        with pytest.raises(ValueError, match="empty or has whitespace"):
            make_safe_relative_artifact_path("   ")

    def test_rejects_leading_whitespace(self) -> None:
        """Rejects strings with leading whitespace."""
        with pytest.raises(ValueError, match="empty or has whitespace"):
            make_safe_relative_artifact_path(" incidents/inc-123")

    def test_rejects_trailing_whitespace(self) -> None:
        """Rejects strings with trailing whitespace."""
        with pytest.raises(ValueError, match="empty or has whitespace"):
            make_safe_relative_artifact_path("incidents/inc-123 ")

    def test_rejects_absolute_path(self) -> None:
        """Rejects absolute paths."""
        with pytest.raises(ValueError, match="absolute"):
            make_safe_relative_artifact_path("/var/lib/k9b/artifacts/snapshot.json")

    def test_rejects_root_absolute_path(self) -> None:
        """Rejects root-level absolute paths."""
        with pytest.raises(ValueError, match="absolute"):
            make_safe_relative_artifact_path("/snapshot.json")

    def test_rejects_traversal_path(self) -> None:
        """Rejects path traversal patterns."""
        with pytest.raises(ValueError, match="traversal"):
            make_safe_relative_artifact_path("../secret")

    def test_rejects_nested_traversal(self) -> None:
        """Rejects nested path traversal patterns."""
        with pytest.raises(ValueError, match="traversal"):
            make_safe_relative_artifact_path("incidents/../../etc/passwd")

    def test_rejects_home_directory(self) -> None:
        """Rejects home directory references."""
        with pytest.raises(ValueError, match="home-relative"):
            make_safe_relative_artifact_path("~/artifacts/snapshot.json")

    def test_rejects_s3_scheme(self) -> None:
        """Rejects S3 URL scheme."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_safe_relative_artifact_path("s3://bucket/incidents/inc-123")

    def test_rejects_gs_scheme(self) -> None:
        """Rejects GCS URL scheme."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_safe_relative_artifact_path("gs://bucket/incidents/inc-123")

    def test_rejects_https_scheme(self) -> None:
        """Rejects HTTPS URL scheme."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_safe_relative_artifact_path("https://example.com/artifacts")

    def test_rejects_http_scheme(self) -> None:
        """Rejects HTTP URL scheme."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_safe_relative_artifact_path("http://example.com/artifacts")

    def test_rejects_file_scheme(self) -> None:
        """Rejects file:// URL scheme."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_safe_relative_artifact_path("file:///var/lib/k9b/snapshot.json")

    def test_rejects_windows_backslashes(self) -> None:
        """Rejects Windows-style paths with backslashes."""
        with pytest.raises(ValueError, match="Windows backslashes"):
            make_safe_relative_artifact_path("incidents\\inc-123\\snapshot.json")

    def test_rejects_windows_absolute_path(self) -> None:
        """Rejects Windows absolute paths."""
        with pytest.raises(ValueError, match="Windows backslashes"):
            make_safe_relative_artifact_path("C:\\Users\\admin\\artifacts\\snapshot.json")


class TestLocalArtifactPath:
    """Tests for LocalArtifactPath constructor."""

    def test_accepts_string_path(self) -> None:
        """Accepts string paths."""
        result = make_local_artifact_path("/var/lib/k9b/artifacts/snapshot.json")
        assert result == "/var/lib/k9b/artifacts/snapshot.json"
        assert isinstance(result, str)  # NewType is str at runtime

    def test_accepts_path_object(self) -> None:
        """Accepts Path objects."""
        path = Path("/var/lib/k9b/artifacts/snapshot.json")
        result = make_local_artifact_path(path)
        assert result == "/var/lib/k9b/artifacts/snapshot.json"
        assert isinstance(result, str)  # NewType is str at runtime

    def test_accepts_relative_path(self) -> None:
        """Accepts relative paths."""
        result = make_local_artifact_path("artifacts/snapshot.json")
        assert result == "artifacts/snapshot.json"

    def test_preserves_string_value(self) -> None:
        """Preserves the string value."""
        path_str = "/absolute/path/to/artifact.json"
        result = make_local_artifact_path(path_str)
        assert result == path_str
        assert str(result) == path_str


class TestExternalStorageRef:
    """Tests for ExternalStorageRef constructor."""

    def test_accepts_s3_ref(self) -> None:
        """Accepts S3 storage references."""
        result = make_external_storage_ref("s3://bucket/incidents/inc-123/snapshot.json")
        assert result == "s3://bucket/incidents/inc-123/snapshot.json"
        assert isinstance(result, str)  # NewType is str at runtime

    def test_accepts_gs_ref(self) -> None:
        """Accepts GCS storage references."""
        result = make_external_storage_ref("gs://bucket/incidents/inc-123/snapshot.json")
        assert result == "gs://bucket/incidents/inc-123/snapshot.json"

    def test_accepts_https_ref(self) -> None:
        """Accepts HTTPS storage references."""
        result = make_external_storage_ref("https://storage.example.com/bucket/snapshot.json")
        assert result == "https://storage.example.com/bucket/snapshot.json"

    def test_accepts_az_ref(self) -> None:
        """Accepts Azure Blob storage references."""
        result = make_external_storage_ref("az://storageaccount.blob.core.windows.net/container/snapshot.json")
        assert "az://" in result

    def test_rejects_relative_path(self) -> None:
        """Rejects relative paths without URL scheme."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_external_storage_ref("incidents/inc-123/snapshot.json")

    def test_rejects_absolute_path(self) -> None:
        """Rejects local absolute paths."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_external_storage_ref("/var/lib/k9b/snapshot.json")

    def test_rejects_file_scheme(self) -> None:
        """Rejects file:// URL scheme (local filesystem reference)."""
        with pytest.raises(ValueError, match="unsupported scheme"):
            make_external_storage_ref("file:///var/lib/k9b/snapshot.json")

    def test_rejects_http_scheme(self) -> None:
        """Rejects http:// URL scheme (not an allowed external storage scheme)."""
        with pytest.raises(ValueError, match="unsupported scheme"):
            make_external_storage_ref("http://example.com/artifacts/snapshot.json")

    def test_rejects_unknown_scheme(self) -> None:
        """Rejects unknown URL schemes."""
        with pytest.raises(ValueError, match="unsupported scheme"):
            make_external_storage_ref("ftp://example.com/artifacts/snapshot.json")
        with pytest.raises(ValueError, match="unsupported scheme"):
            make_external_storage_ref("sftp://example.com/artifacts/snapshot.json")


class TestReviewPacketStorageRef:
    """Tests for ReviewPacketStorageRef constructor."""

    def test_accepts_safe_relative_path(self) -> None:
        """Accepts safe relative artifact paths."""
        result = make_review_packet_storage_ref("incidents/inc-123/snapshot.json")
        assert result == "incidents/inc-123/snapshot.json"
        assert isinstance(result, str)  # NewType is str at runtime

    def test_rejects_absolute_path(self) -> None:
        """Rejects absolute paths."""
        with pytest.raises(ValueError, match="absolute"):
            make_review_packet_storage_ref("/var/lib/k9b/snapshot.json")

    def test_rejects_traversal(self) -> None:
        """Rejects path traversal."""
        with pytest.raises(ValueError, match="traversal"):
            make_review_packet_storage_ref("../secret")

    def test_rejects_url_scheme(self) -> None:
        """Rejects URL schemes."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_review_packet_storage_ref("s3://bucket/incidents")


class TestLLMSafeArtifactRef:
    """Tests for LLMSafeArtifactRef constructor."""

    def test_accepts_safe_relative_path(self) -> None:
        """Accepts safe relative artifact paths."""
        result = make_llm_safe_artifact_ref("incidents/inc-123/snapshot.json")
        assert result == "incidents/inc-123/snapshot.json"
        assert isinstance(result, str)  # NewType is str at runtime

    def test_rejects_absolute_path(self) -> None:
        """Rejects absolute paths."""
        with pytest.raises(ValueError, match="absolute"):
            make_llm_safe_artifact_ref("/var/lib/k9b/snapshot.json")

    def test_rejects_traversal(self) -> None:
        """Rejects path traversal."""
        with pytest.raises(ValueError, match="traversal"):
            make_llm_safe_artifact_ref("../secret")

    def test_rejects_url_scheme(self) -> None:
        """Rejects URL schemes."""
        with pytest.raises(ValueError, match="URL scheme"):
            make_llm_safe_artifact_ref("s3://bucket/incidents")


class TestLLMSafeArtifactRefFromSafePath:
    """Tests for make_llm_safe_artifact_ref_from_safe_path conversion."""

    def test_converts_safe_relative_path_to_llm_ref(self) -> None:
        """Converts SafeRelativeArtifactPath to LLMSafeArtifactRef."""
        safe_path = make_safe_relative_artifact_path("incidents/inc-123/snapshot.json")
        result = make_llm_safe_artifact_ref_from_safe_path(safe_path)
        assert result == "incidents/inc-123/snapshot.json"
        assert isinstance(result, str)  # NewType is str at runtime

    def test_preserves_path_value(self) -> None:
        """Preserves the path value through conversion."""
        safe_path = make_safe_relative_artifact_path("artifacts/bundle/snapshot.tar.gz")
        result = make_llm_safe_artifact_ref_from_safe_path(safe_path)
        assert str(result) == str(safe_path)


class TestEvidenceArtifactStorageRef:
    """Tests for EvidenceArtifact.storage_ref handling."""

    def test_evidence_artifact_to_dict_emits_storage_ref(self) -> None:
        """EvidenceArtifact.to_dict() emits storage_ref as string."""
        artifact = EvidenceArtifact(
            artifact_id="bundle-123",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="incidents/inc-123/snapshot.json",
        )
        result = artifact.to_dict()
        assert result["storage_ref"] == "incidents/inc-123/snapshot.json"
        assert isinstance(result["storage_ref"], str)

    def test_evidence_artifact_to_dict_preserves_external_ref(self) -> None:
        """EvidenceArtifact.to_dict() preserves external storage refs."""
        artifact = EvidenceArtifact(
            artifact_id="bundle-456",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/incidents/inc-123/snapshot.json",
        )
        result = artifact.to_dict()
        assert result["storage_ref"] == "s3://bucket/incidents/inc-123/snapshot.json"
        assert isinstance(result["storage_ref"], str)

    def test_storage_ref_preserves_type_value(self) -> None:
        """storage_ref field preserves the typed string value."""
        ref = make_external_storage_ref("s3://bucket/artifacts/bundle-123")
        artifact = EvidenceArtifact(
            artifact_id="bundle-123",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref=ref,
        )
        # At runtime, NewType is identity, so this works
        assert artifact.storage_ref == "s3://bucket/artifacts/bundle-123"


class TestTypeSeparation:
    """Tests for type separation guarantees."""

    def test_safe_relative_and_local_are_different_types(self) -> None:
        """SafeRelativeArtifactPath and LocalArtifactPath are distinct types."""
        safe = make_safe_relative_artifact_path("relative/path")
        local = make_local_artifact_path("/absolute/path")
        # At runtime, both are str, but static type checker enforces distinction
        assert safe != local
        assert safe == "relative/path"
        assert local == "/absolute/path"

    def test_safe_relative_rejects_local_absolute(self) -> None:
        """SafeRelativeArtifactPath rejects absolute paths that LocalArtifactPath accepts."""
        # This should work - absolute path to LocalArtifactPath
        local = make_local_artifact_path("/var/lib/k9b/artifacts")
        assert local == "/var/lib/k9b/artifacts"

        # This should fail - absolute path to SafeRelativeArtifactPath
        with pytest.raises(ValueError, match="absolute"):
            make_safe_relative_artifact_path("/var/lib/k9b/artifacts")

    def test_safe_relative_rejects_external_ref(self) -> None:
        """SafeRelativeArtifactPath rejects external refs that ExternalStorageRef accepts."""
        # This should work - s3:// to ExternalStorageRef
        external = make_external_storage_ref("s3://bucket/path")
        assert external == "s3://bucket/path"

        # This should fail - s3:// to SafeRelativeArtifactPath
        with pytest.raises(ValueError, match="URL scheme"):
            make_safe_relative_artifact_path("s3://bucket/path")


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing patterns."""

    def test_plain_string_still_works(self) -> None:
        """Plain strings still work for storage_ref (backward compatibility)."""
        artifact = EvidenceArtifact(
            artifact_id="bundle-789",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="incidents/inc-456/snapshot.json",
        )
        assert artifact.storage_ref == "incidents/inc-456/snapshot.json"

    def test_to_dict_still_emits_string(self) -> None:
        """to_dict() still emits plain strings (backward compatibility)."""
        artifact = EvidenceArtifact(
            artifact_id="bundle-123",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="artifacts/snapshot.json",
        )
        result = artifact.to_dict()
        # Ensure it's a plain string, not a branded type wrapper
        assert isinstance(result["storage_ref"], str)
        assert not hasattr(result["storage_ref"], "__class__") or result["storage_ref"].__class__ is str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
