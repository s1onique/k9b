"""Unit tests for AlertmanagerSource model and contracts.

Tests cover:
- Source identity and endpoint normalization
- Serialization/deserialization roundtrips
- Enum values and validation
"""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceMode,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    DiscoveryResult,
    VerificationResult,
)


class TestAlertmanagerSourceIdentity:
    """Tests for AlertmanagerSource identity."""

    def test_source_identity_key(self) -> None:
        """Test that source_id is used as identity key."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
        )
        assert source.identity_key == "crd:monitoring/main"

    def test_source_endpoint_normalization(self) -> None:
        """Test that endpoint trailing slashes are removed."""
        source = AlertmanagerSource(
            source_id="test",
            endpoint="http://alertmanager:9093/",
        )
        assert source.endpoint == "http://alertmanager:9093"

    def test_source_with_special_characters_in_id(self) -> None:
        """Test source handling special characters in source_id."""
        source = AlertmanagerSource(
            source_id="crd:my-namespace/my-alertmanager-instance",
            endpoint="http://alertmanager:9093",
            namespace="my-namespace",
            name="my-alertmanager-instance",
        )
        assert source.identity_key == "crd:my-namespace/my-alertmanager-instance"

        serialized = source.to_dict()
        restored = AlertmanagerSource.from_dict(serialized)
        assert restored.source_id == source.source_id


class TestAlertmanagerSourceSerialization:
    """Tests for AlertmanagerSource serialization."""

    def test_source_to_dict_roundtrip(self) -> None:
        """Test source serialization and deserialization."""
        original = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            verified_version="0.25.0",
            confidence_hints=("from-crd", "namespace=monitoring"),
        )

        serialized = original.to_dict()
        restored = AlertmanagerSource.from_dict(serialized)

        assert restored.source_id == original.source_id
        assert restored.endpoint == original.endpoint
        assert restored.namespace == original.namespace
        assert restored.name == original.name
        assert restored.origin == original.origin
        assert restored.state == original.state
        assert restored.verified_version == original.verified_version
        assert restored.confidence_hints == original.confidence_hints

    def test_source_without_aliases_serialization(self) -> None:
        """Test that AlertmanagerSource without aliases doesn't include aliases in dict."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        serialized = source.to_dict()
        # Aliases should not be present when empty (backward compatibility)
        assert "aliases" not in serialized

        # But roundtrip should still work
        restored = AlertmanagerSource.from_dict(serialized)
        assert len(restored.aliases) == 0


class TestEnums:
    """Tests for enum values."""

    def test_source_origin_enum_values(self) -> None:
        """Verify all expected origin values exist."""
        expected = {"manual", "alertmanager-crd", "prometheus-crd-config", "service-heuristic"}
        actual = {s.value for s in AlertmanagerSourceOrigin}
        assert actual == expected

    def test_source_state_enum_values(self) -> None:
        """Verify all expected state values exist."""
        expected = {"discovered", "auto-tracked", "degraded", "missing", "manual"}
        actual = {s.value for s in AlertmanagerSourceState}
        assert actual == expected

    def test_manual_source_mode_enum_values(self) -> None:
        """Verify all expected manual_source_mode values exist."""
        expected = {"not-manual", "operator-configured", "operator-promoted"}
        actual = {s.value for s in AlertmanagerSourceMode}
        assert actual == expected


class TestDiscoveryResult:
    """Tests for DiscoveryResult."""

    def test_discovery_result_creation(self) -> None:
        """Test DiscoveryResult creation with sources and errors."""
        result = DiscoveryResult(
            sources=(
                AlertmanagerSource(
                    source_id="test:source",
                    endpoint="http://test:9093",
                ),
            ),
            errors=("Error 1", "Error 2"),
            strategy="test-strategy",
        )

        assert len(result.sources) == 1
        assert len(result.errors) == 2
        assert result.strategy == "test-strategy"


class TestVerificationResult:
    """Tests for VerificationResult."""

    def test_verification_result_all_fields(self) -> None:
        """Test VerificationResult with all fields populated."""
        result = VerificationResult(
            healthy=True,
            ready=True,
            version="0.25.0",
            error=None,
            checked_at=datetime.now(UTC),
        )

        assert result.healthy is True
        assert result.ready is True
        assert result.version == "0.25.0"
        assert result.error is None

    def test_verification_result_with_error(self) -> None:
        """Test VerificationResult with error and no version."""
        result = VerificationResult(
            healthy=False,
            ready=False,
            version=None,
            error="Connection refused: Error 111",
        )

        assert result.healthy is False
        assert result.ready is False
        assert result.version is None
        assert result.error is not None
        assert "Connection refused" in result.error
