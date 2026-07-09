"""Tests for artifact ID type contracts at the domain/store boundary.

These tests verify that artifact ID types are properly typed and serialized,
and that snapshot bundle and review packet evidence use the correct branded IDs.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from k8s_diag_agent.collect.incident_evidence import (
    ArtifactId,
    DiagnosisLoopPassId,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceLink,
    EvidenceRole,
    ExternalAnalysisArtifactId,
    ReviewPacketId,
    SnapshotBundleId,
    make_artifact_id,
    make_diagnosis_loop_pass_id,
    make_external_analysis_artifact_id,
    make_review_packet_id,
    make_snapshot_bundle_id,
)


class TestArtifactIdTypeContract:
    """Tests for ArtifactId type contract."""

    def test_artifact_id_preserves_runtime_string_value(self) -> None:
        """ArtifactId preserves runtime string value."""
        artifact_id = ArtifactId("bundle-123")
        # At runtime, NewType is just the identity function
        assert artifact_id == "bundle-123"
        assert str(artifact_id) == "bundle-123"

    def test_make_artifact_id_converts_string(self) -> None:
        """make_artifact_id converts a string to ArtifactId."""
        result = make_artifact_id("bundle-456")
        assert result == "bundle-456"
        assert isinstance(result, str)


class TestSnapshotBundleIdTypeContract:
    """Tests for SnapshotBundleId type contract."""

    def test_snapshot_bundle_id_preserves_runtime_string_value(self) -> None:
        """SnapshotBundleId preserves runtime string value."""
        bundle_id = SnapshotBundleId("snapshot-bundle-789")
        assert bundle_id == "snapshot-bundle-789"
        assert str(bundle_id) == "snapshot-bundle-789"

    def test_make_snapshot_bundle_id_converts_string(self) -> None:
        """make_snapshot_bundle_id converts a string to SnapshotBundleId."""
        result = make_snapshot_bundle_id("snapshot-bundle-123")
        assert result == "snapshot-bundle-123"


class TestReviewPacketIdTypeContract:
    """Tests for ReviewPacketId type contract."""

    def test_review_packet_id_preserves_runtime_string_value(self) -> None:
        """ReviewPacketId preserves runtime string value."""
        packet_id = ReviewPacketId("review-packet-123")
        assert packet_id == "review-packet-123"
        assert str(packet_id) == "review-packet-123"

    def test_make_review_packet_id_converts_string(self) -> None:
        """make_review_packet_id converts a string to ReviewPacketId."""
        result = make_review_packet_id("review-packet-456")
        assert result == "review-packet-456"


class TestDiagnosisLoopPassIdTypeContract:
    """Tests for DiagnosisLoopPassId type contract."""

    def test_diagnosis_loop_pass_id_preserves_runtime_string_value(self) -> None:
        """DiagnosisLoopPassId preserves runtime string value."""
        pass_id = DiagnosisLoopPassId("loop-pass-123")
        assert pass_id == "loop-pass-123"
        assert str(pass_id) == "loop-pass-123"

    def test_make_diagnosis_loop_pass_id_converts_string(self) -> None:
        """make_diagnosis_loop_pass_id converts a string to DiagnosisLoopPassId."""
        result = make_diagnosis_loop_pass_id("loop-pass-456")
        assert result == "loop-pass-456"


class TestExternalAnalysisArtifactIdTypeContract:
    """Tests for ExternalAnalysisArtifactId type contract."""

    def test_external_analysis_artifact_id_preserves_runtime_string_value(self) -> None:
        """ExternalAnalysisArtifactId preserves runtime string value."""
        ext_id = ExternalAnalysisArtifactId("external-123")
        assert ext_id == "external-123"
        assert str(ext_id) == "external-123"

    def test_make_external_analysis_artifact_id_converts_string(self) -> None:
        """make_external_analysis_artifact_id converts a string."""
        result = make_external_analysis_artifact_id("external-456")
        assert result == "external-456"


class TestEvidenceArtifactBrandedId:
    """Tests for EvidenceArtifact with branded ArtifactId."""

    def test_evidence_artifact_accepts_artifact_id(self) -> None:
        """EvidenceArtifact accepts ArtifactId."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("bundle-456"),
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/incidents/inc-123/bundles/bundle-456",
        )
        assert artifact.artifact_id == "bundle-456"

    def test_evidence_artifact_accepts_make_artifact_id(self) -> None:
        """EvidenceArtifact accepts make_artifact_id() result."""
        artifact = EvidenceArtifact(
            artifact_id=make_artifact_id("bundle-789"),
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/bundle-789",
        )
        assert artifact.artifact_id == "bundle-789"

    def test_evidence_artifact_to_dict_emits_plain_string(self) -> None:
        """EvidenceArtifact.to_dict() emits plain string artifact_id."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("bundle-123"),
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/bundle-123",
        )
        data = artifact.to_dict()
        assert data["artifact_id"] == "bundle-123"
        # Must be a plain string, not wrapped
        assert isinstance(data["artifact_id"], str)

    def test_snapshot_bundle_evidence_serializes_same_id(self) -> None:
        """Snapshot bundle evidence serializes the same ID as stored."""
        bundle_id = make_snapshot_bundle_id("snapshot-123")
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId(bundle_id),
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/snapshot-123",
        )
        data = artifact.to_dict()
        assert data["artifact_id"] == "snapshot-123"

    def test_review_packet_evidence_serializes_same_id(self) -> None:
        """Review packet evidence serializes the same ID as stored."""
        packet_id = make_review_packet_id("review-456")
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId(packet_id),
            kind=EvidenceKind.REVIEW_PACKET,
            storage_ref="s3://bucket/review-456",
        )
        data = artifact.to_dict()
        assert data["artifact_id"] == "review-456"


class TestEvidenceLinkBrandedId:
    """Tests for EvidenceLink with branded ArtifactId."""

    def test_evidence_link_accepts_artifact_id(self) -> None:
        """EvidenceLink accepts ArtifactId."""
        now = datetime.now(UTC)
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id=ArtifactId("bundle-456"),
            role=EvidenceRole.SNAPSHOT,
            attached_at=now,
        )
        assert link.artifact_id == "bundle-456"

    def test_evidence_link_accepts_make_artifact_id(self) -> None:
        """EvidenceLink accepts make_artifact_id() result."""
        now = datetime.now(UTC)
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id=make_artifact_id("bundle-789"),
            role=EvidenceRole.SNAPSHOT,
            attached_at=now,
        )
        assert link.artifact_id == "bundle-789"

    def test_evidence_link_to_dict_emits_plain_string(self) -> None:
        """EvidenceLink.to_dict() emits plain string artifact_id."""
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id=ArtifactId("bundle-123"),
            role=EvidenceRole.SNAPSHOT,
        )
        data = link.to_dict()
        assert data["artifact_id"] == "bundle-123"
        # Must be a plain string, not wrapped
        assert isinstance(data["artifact_id"], str)

    def test_evidence_link_serialization_preserves_snapshot_bundle_id(self) -> None:
        """EvidenceLink for snapshot bundle preserves ID on serialization."""
        bundle_id = make_snapshot_bundle_id("snapshot-bundle-123")
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id=make_artifact_id(bundle_id),
            role=EvidenceRole.SNAPSHOT,
        )
        data = link.to_dict()
        assert data["artifact_id"] == "snapshot-bundle-123"

    def test_evidence_link_serialization_preserves_review_packet_id(self) -> None:
        """EvidenceLink for review packet preserves ID on serialization."""
        packet_id = make_review_packet_id("review-packet-456")
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id=make_artifact_id(packet_id),
            role=EvidenceRole.REVIEW_PACKET,
        )
        data = link.to_dict()
        assert data["artifact_id"] == "review-packet-456"


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing code."""

    def test_plain_string_can_be_used_for_artifact_id(self) -> None:
        """Plain strings can still be used (compatibility)."""
        # This works because NewType is identity at runtime
        artifact = EvidenceArtifact(
            artifact_id="bundle-456",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/bundle-456",
        )
        assert artifact.artifact_id == "bundle-456"

    def test_evidence_link_with_plain_string_artifact_id(self) -> None:
        """EvidenceLink with plain string artifact_id works."""
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id="bundle-456",
            role=EvidenceRole.SNAPSHOT,
        )
        assert link.artifact_id == "bundle-456"

    def test_id_comparison_works(self) -> None:
        """ID comparison still works with branded IDs."""
        id1 = ArtifactId("bundle-123")
        id2 = ArtifactId("bundle-123")
        id3 = ArtifactId("bundle-456")

        # Values are equal
        assert id1 == id2
        # Different values are not equal
        assert id1 != id3


class TestTypeBranding:
    """Tests to verify type branding prevents mixing IDs."""

    def test_artifact_id_cannot_be_snapsh_bundle_id(self) -> None:
        """Type system prevents mixing ArtifactId and SnapshotBundleId at static time.

        Note: At runtime, NewType is just identity, so this is a static type check.
        The test documents the intended behavior.
        """
        # These are both just strings at runtime
        artifact_id = ArtifactId("bundle-123")
        bundle_id = SnapshotBundleId("bundle-123")

        # At runtime they are equal (both are "bundle-123")
        # The branding is enforced by the type system, not runtime
        assert str(artifact_id) == str(bundle_id)

    def test_evidence_artifact_kind_uses_enum(self) -> None:
        """EvidenceArtifact.kind uses EvidenceKind enum."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("bundle-123"),
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/bundle-123",
        )
        assert artifact.kind == EvidenceKind.SNAPSHOT_BUNDLE
        assert artifact.kind.value == "snapshot_bundle"

    def test_evidence_link_role_uses_enum(self) -> None:
        """EvidenceLink.role uses EvidenceRole enum."""
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id=ArtifactId("bundle-456"),
            role=EvidenceRole.SNAPSHOT,
        )
        assert link.role == EvidenceRole.SNAPSHOT
        assert link.role.value == "snapshot"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
