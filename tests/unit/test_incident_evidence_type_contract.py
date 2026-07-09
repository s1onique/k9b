"""Tests for evidence type contracts at the domain/store boundary.

These tests verify that evidence role/kind values are properly typed
and that snapshot bundle and review packet evidence use the correct
typed role/kind values.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from k8s_diag_agent.collect.incident_evidence import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceKindCode,
    EvidenceLink,
    EvidenceRole,
    EvidenceRoleCode,
)


class TestEvidenceRoleTypeContract:
    """Tests for EvidenceRole type contract."""

    def test_evidence_role_enum_values_match_literal_alias_core_set(self) -> None:
        """EvidenceRole enum values must be a subset of EvidenceRoleCode literal values.

        Note: EvidenceRoleCode includes extended roles used across the codebase,
        but EvidenceRole only includes the core incident-boundary roles.
        """
        enum_values = {e.value for e in EvidenceRole}
        from typing import get_args

        literal_values = set(get_args(EvidenceRoleCode))
        # All enum values must be in the literal alias
        assert enum_values.issubset(literal_values), (
            f"EvidenceRole enum values {enum_values} must be a subset of "
            f"EvidenceRoleCode literal values {literal_values}"
        )

    def test_evidence_role_code_alias_is_closed(self) -> None:
        """EvidenceRoleCode must be a closed Literal alias with core and extended roles."""
        from typing import get_args

        role_values = set(get_args(EvidenceRoleCode))
        # Must include all core incident-boundary roles
        assert "primary" in role_values
        assert "supporting" in role_values
        assert "snapshot" in role_values
        assert "review_packet" in role_values
        assert "debug" in role_values
        # Alias must have at least the 5 core values (plus extended roles)
        assert len(role_values) >= 5


class TestEvidenceKindTypeContract:
    """Tests for EvidenceKind type contract."""

    def test_evidence_kind_enum_values_match_literal_alias_core_set(self) -> None:
        """EvidenceKind enum values must be a subset of EvidenceKindCode literal values.

        Note: EvidenceKindCode includes extended kinds used across the codebase,
        but EvidenceKind only includes the core incident-boundary kinds.
        """
        enum_values = {e.value for e in EvidenceKind}
        from typing import get_args

        literal_values = set(get_args(EvidenceKindCode))
        # All enum values must be in the literal alias
        assert enum_values.issubset(literal_values), (
            f"EvidenceKind enum values {enum_values} must be a subset of "
            f"EvidenceKindCode literal values {literal_values}"
        )

    def test_evidence_kind_code_alias_is_closed(self) -> None:
        """EvidenceKindCode must be a closed Literal alias with core and extended kinds."""
        from typing import get_args

        kind_values = set(get_args(EvidenceKindCode))
        # Must include all core incident-boundary kinds
        assert "snapshot_bundle" in kind_values
        assert "review_packet" in kind_values
        assert "log_excerpt" in kind_values
        assert "metric_window" in kind_values
        assert "trace" in kind_values
        assert "run_summary" in kind_values
        assert "external_analysis" in kind_values
        # Alias must have at least the 7 core values (plus extended kinds)
        assert len(kind_values) >= 7


class TestSnapshotBundleEvidenceRole:
    """Tests for snapshot bundle evidence role usage."""

    def test_snapshot_role_exists(self) -> None:
        """EvidenceRole.SNAPSHOT must exist and have correct value."""
        assert EvidenceRole.SNAPSHOT == EvidenceRole("snapshot")
        assert EvidenceRole.SNAPSHOT.value == "snapshot"

    def test_snapshot_role_in_literal_alias(self) -> None:
        """EvidenceRole.SNAPSHOT value must be in EvidenceRoleCode alias."""
        from typing import get_args

        role_values = set(get_args(EvidenceRoleCode))
        assert "snapshot" in role_values


class TestReviewPacketEvidenceRole:
    """Tests for review packet evidence role usage."""

    def test_review_packet_role_exists(self) -> None:
        """EvidenceRole.REVIEW_PACKET must exist and have correct value."""
        assert EvidenceRole.REVIEW_PACKET == EvidenceRole("review_packet")
        assert EvidenceRole.REVIEW_PACKET.value == "review_packet"

    def test_review_packet_role_in_literal_alias(self) -> None:
        """EvidenceRole.REVIEW_PACKET value must be in EvidenceRoleCode alias."""
        from typing import get_args

        role_values = set(get_args(EvidenceRoleCode))
        assert "review_packet" in role_values


class TestEvidenceLinkConstruction:
    """Tests for EvidenceLink construction with typed role values."""

    def test_evidence_link_with_snapshot_role(self) -> None:
        """EvidenceLink can be constructed with EvidenceRole.SNAPSHOT."""
        now = datetime.now(UTC)
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id="bundle-456",
            role=EvidenceRole.SNAPSHOT,
            attached_at=now,
        )
        assert link.incident_id == "inc-123"
        assert link.artifact_id == "bundle-456"
        assert link.role == EvidenceRole.SNAPSHOT
        assert link.attached_at == now

    def test_evidence_link_with_review_packet_role(self) -> None:
        """EvidenceLink can be constructed with EvidenceRole.REVIEW_PACKET."""
        now = datetime.now(UTC)
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id="packet-789",
            role=EvidenceRole.REVIEW_PACKET,
            attached_at=now,
        )
        assert link.incident_id == "inc-123"
        assert link.artifact_id == "packet-789"
        assert link.role == EvidenceRole.REVIEW_PACKET

    def test_evidence_link_serialization_preserves_role_value(self) -> None:
        """EvidenceLink.to_dict() must preserve role as string value."""
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id="bundle-456",
            role=EvidenceRole.SNAPSHOT,
        )
        data = link.to_dict()
        assert data["role"] == "snapshot"
        # Must be a string, not an enum
        assert isinstance(data["role"], str)

    def test_evidence_link_serialization_review_packet(self) -> None:
        """EvidenceLink.to_dict() for review packet preserves role as string."""
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id="packet-789",
            role=EvidenceRole.REVIEW_PACKET,
        )
        data = link.to_dict()
        assert data["role"] == "review_packet"
        assert isinstance(data["role"], str)


class TestEvidenceArtifactConstruction:
    """Tests for EvidenceArtifact construction with typed kind values."""

    def test_evidence_artifact_with_snapshot_bundle_kind(self) -> None:
        """EvidenceArtifact can be constructed with EvidenceKind.SNAPSHOT_BUNDLE."""
        artifact = EvidenceArtifact(
            artifact_id="bundle-456",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/incidents/inc-123/bundles/bundle-456",
        )
        assert artifact.artifact_id == "bundle-456"
        assert artifact.kind == EvidenceKind.SNAPSHOT_BUNDLE

    def test_evidence_artifact_with_review_packet_kind(self) -> None:
        """EvidenceArtifact can be constructed with EvidenceKind.REVIEW_PACKET."""
        artifact = EvidenceArtifact(
            artifact_id="packet-789",
            kind=EvidenceKind.REVIEW_PACKET,
            storage_ref="s3://bucket/incidents/inc-123/packets/packet-789",
        )
        assert artifact.artifact_id == "packet-789"
        assert artifact.kind == EvidenceKind.REVIEW_PACKET

    def test_evidence_artifact_serialization_preserves_kind_value(self) -> None:
        """EvidenceArtifact.to_dict() must preserve kind as string value."""
        artifact = EvidenceArtifact(
            artifact_id="bundle-456",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/bundle-456",
        )
        data = artifact.to_dict()
        assert data["kind"] == "snapshot_bundle"
        # Must be a string, not an enum
        assert isinstance(data["kind"], str)


class TestEvidenceRoleCodeValidation:
    """Tests for EvidenceRoleCode validation helpers."""

    def test_require_evidence_role_rejects_unknown(self) -> None:
        """Unknown evidence role values should be rejected."""
        # This tests a validation helper that should exist
        # if runtime validation is needed at construction seams
        from typing import get_args

        from k8s_diag_agent.collect.incident_evidence import EvidenceRoleCode

        allowed_roles = set(get_args(EvidenceRoleCode))
        unknown_role = "unknown_role"

        # Unknown role should not be in allowed set
        assert unknown_role not in allowed_roles

        # Construction should fail for unknown role
        with pytest.raises(ValueError):
            EvidenceRole(unknown_role)

    def test_require_evidence_role_accepts_enum_values(self) -> None:
        """EvidenceRole enum values should be accepted.

        Note: Not all EvidenceRoleCode values are valid EvidenceRole enum values.
        Extended roles (e.g., system, user) are only in the Literal alias,
        not in the EvidenceRole enum. This is intentional per the ACT design.
        """
        # Only test EvidenceRole enum values
        for role in EvidenceRole:
            # Should not raise ValueError
            parsed = EvidenceRole(role.value)
            assert parsed == role


class TestEvidenceKindCodeValidation:
    """Tests for EvidenceKindCode validation helpers."""

    def test_require_evidence_kind_rejects_unknown(self) -> None:
        """Unknown evidence kind values should be rejected."""
        from typing import get_args

        from k8s_diag_agent.collect.incident_evidence import EvidenceKindCode

        allowed_kinds = set(get_args(EvidenceKindCode))
        unknown_kind = "unknown_kind"

        # Unknown kind should not be in allowed set
        assert unknown_kind not in allowed_kinds

        # Construction should fail for unknown kind
        with pytest.raises(ValueError):
            EvidenceKind(unknown_kind)

    def test_require_evidence_kind_accepts_enum_values(self) -> None:
        """EvidenceKind enum values should be accepted.

        Note: Not all EvidenceKindCode values are valid EvidenceKind enum values.
        Extended kinds (e.g., read_only_kubernetes) are only in the Literal alias,
        not in the EvidenceKind enum. This is intentional per the ACT design.
        """
        # Only test EvidenceKind enum values
        for kind in EvidenceKind:
            # Should not raise ValueError
            parsed = EvidenceKind(kind.value)
            assert parsed == kind


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing code."""

    def test_evidence_link_role_can_use_enum_member(self) -> None:
        """Existing code using EvidenceRole.SNAPSHOT still works."""
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id="bundle-456",
            role=EvidenceRole.SNAPSHOT,
        )
        # Role comparison should work
        assert link.role == EvidenceRole.SNAPSHOT
        assert link.role.value == "snapshot"

    def test_evidence_artifact_kind_can_use_enum_member(self) -> None:
        """Existing code using EvidenceKind.SNAPSHOT_BUNDLE still works."""
        artifact = EvidenceArtifact(
            artifact_id="bundle-456",
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref="s3://bucket/bundle-456",
        )
        # Kind comparison should work
        assert artifact.kind == EvidenceKind.SNAPSHOT_BUNDLE
        assert artifact.kind.value == "snapshot_bundle"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
