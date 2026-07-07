"""Tests for compact artifact contract and truncation/bounding behavior.

Part of ACT-K9B-ALERTMANAGER-SNAPSHOT-SPLIT01 split.
Tests sensitive key redaction and compact serialization.
"""

from __future__ import annotations

from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    _is_sensitive_key,
)


class TestIsSensitiveKey:
    """Tests for _is_sensitive_key function."""

    def test_detects_password_pattern(self) -> None:
        """Password in key is detected as sensitive."""
        assert _is_sensitive_key("password") is True
        assert _is_sensitive_key("user_password") is True
        assert _is_sensitive_key("dbPassword") is True

    def test_detects_secret_pattern(self) -> None:
        """Secret in key is detected as sensitive."""
        assert _is_sensitive_key("secret") is True
        assert _is_sensitive_key("api_secret") is True

    def test_detects_token_pattern(self) -> None:
        """Token in key is detected as sensitive."""
        assert _is_sensitive_key("token") is True
        assert _is_sensitive_key("bearer_token") is True

    def test_detects_auth_pattern(self) -> None:
        """Auth in key is detected as sensitive."""
        assert _is_sensitive_key("auth") is True
        assert _is_sensitive_key("basic_auth") is True

    def test_detects_credential_pattern(self) -> None:
        """Credential in key is detected as sensitive."""
        assert _is_sensitive_key("credential") is True
        assert _is_sensitive_key("credentials") is True

    def test_detects_private_key_pattern(self) -> None:
        """Private in key is detected as sensitive."""
        assert _is_sensitive_key("private") is True
        assert _is_sensitive_key("private_key") is True

    def test_detects_api_key_patterns(self) -> None:
        """API key patterns are detected as sensitive."""
        assert _is_sensitive_key("api_key") is True
        assert _is_sensitive_key("apikey") is True
        assert _is_sensitive_key("apiKey") is True

    def test_safe_keys_pass(self) -> None:
        """Safe keys are not flagged as sensitive."""
        assert _is_sensitive_key("summary") is False
        assert _is_sensitive_key("description") is False
        assert _is_sensitive_key("runbook_url") is False
        assert _is_sensitive_key("dashboard_url") is False


class TestSensitiveAnnotationRedaction:
    """Tests for sensitive annotation redaction in normalization."""

    def test_redacts_sensitive_annotation_keys(self) -> None:
        """Sensitive annotation keys are redacted."""
        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            normalize_alertmanager_payload,
        )
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "annotations": {
                    "summary": "Safe annotation",
                    "password": "secret123",
                    "api_key": "key123",
                },
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        ann_dict = dict(snapshot.alerts[0].annotations)
        assert ann_dict["summary"] == "Safe annotation"
        assert ann_dict["password"] == "[REDACTED]"
        assert ann_dict["api_key"] == "[REDACTED]"


class TestCompactArtifactContract:
    """Tests for AlertmanagerCompact artifact contract."""

    def test_compact_roundtrip_serialization(self) -> None:
        """Compact serializes and deserializes correctly."""
        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            normalize_alertmanager_payload,
            snapshot_to_compact,
        )
        raw = [
            {
                "labels": {"alertname": "TestAlert", "severity": "warning"},
                "annotations": {"summary": "Test alert"},
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        
        # Verify compact has expected structure
        data = compact.to_dict()
        assert "status" in data
        assert "alert_count" in data
        assert "severity_counts" in data
        assert "top_alert_names" in data
        
        # Verify JSON bytes are deterministic
        json_bytes = compact.to_json_bytes()
        assert isinstance(json_bytes, bytes)
        
        # Verify same compact produces same bytes
        json_bytes2 = compact.to_json_bytes()
        assert json_bytes == json_bytes2

    def test_compact_includes_artifact_id(self) -> None:
        """Compact includes artifact_id for new artifacts."""
        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            normalize_alertmanager_payload,
            snapshot_to_compact,
        )
        raw = [{"labels": {"alertname": "TestAlert"}}]
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        
        # Compact gets its own artifact_id
        assert compact.artifact_id is not None
        assert isinstance(compact.artifact_id, str)

    def test_new_snapshot_gets_artifact_id_by_default(self) -> None:
        """Regression: AlertmanagerSnapshot auto-generates artifact_id via default_factory."""
        from datetime import UTC, datetime

        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            AlertmanagerSnapshot,
            AlertmanagerStatus,
        )

        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        assert snapshot.artifact_id is not None
        assert isinstance(snapshot.artifact_id, str)
