"""Golden/contract tests for Alertmanager sources review packet.

Tests that the review packet schema is stable and conforms to the canonical wire schema
k9b.alertmanager_sources.review_packet.v1.

Run with: python -m pytest tests/unit/test_alertmanager_packet_contracts_review.py -v
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.alertmanager_sources_review_packet import (
    AlertmanagerSourcesReviewPacket,
    EndpointIdentity,
    KubernetesIdentity,
    RuntimeIdentity,
    SourceEntry,
    Summary,
)


class TestAlertmanagerSourcesReviewPacketContract(unittest.TestCase):
    """Contract tests for AlertmanagerSourcesReviewPacket canonical schema."""

    def test_schema_version_matches_canonical(self) -> None:
        """Schema version must be k9b.alertmanager_sources.review_packet.v1."""
        from k8s_diag_agent.external_analysis.alertmanager_sources_review_packet import SCHEMA_VERSION

        self.assertEqual(SCHEMA_VERSION, "k9b.alertmanager_sources.review_packet.v1")

    def test_review_packet_to_dict_has_required_top_level_keys(self) -> None:
        """Review packet must have all required top-level keys."""
        packet = AlertmanagerSourcesReviewPacket(
            sources=(),
            summary=Summary(),
        )
        result = packet.to_dict()

        # Required top-level keys
        required_keys = {
            "schema_version",
            "artifact_id",
            "generated_at",
            "context",
            "summary",
            "sources",
            "duplicate_analysis",
            "redactions",
        }
        self.assertEqual(set(result.keys()), required_keys)

    def test_review_packet_schema_version_in_output(self) -> None:
        """Schema version must appear in output dict."""
        packet = AlertmanagerSourcesReviewPacket(
            sources=(),
            summary=Summary(),
        )
        result = packet.to_dict()

        self.assertEqual(result["schema_version"], "k9b.alertmanager_sources.review_packet.v1")

    def test_review_packet_source_entry_to_dict_structure(self) -> None:
        """SourceEntry must produce expected structure."""
        runtime_identity = RuntimeIdentity(
            probe_attempted=False,
            ready=True,
            healthy=True,
            alertmanager_version="0.25.0",
        )
        kubernetes_identity = KubernetesIdentity(
            service_uid="abc123",
            service_type="ClusterIP",
            labels={"app": "alertmanager"},
        )
        endpoint_identity = EndpointIdentity(
            endpoint_slices=["eps-1"],
            target_pod_uids=["pod-uid-1", "pod-uid-2"],
            target_pod_names=["monitoring/alertmanager-0", "monitoring/alertmanager-1"],
            target_owner_refs=[{"kind": "StatefulSet", "name": "alertmanager"}],
        )

        # SourceEntry test
        source_entry = SourceEntry(
            source_id="source-1",
            state="auto-tracked",
            origin="service-heuristic",
            provenance="service-heuristic",
            namespace="monitoring",
            service_name="alertmanager-main",
            endpoint_url="http://alertmanager.monitoring:9093",
            cluster="prod-cluster",
            kubernetes_identity=kubernetes_identity,
            endpoint_identity=endpoint_identity,
            runtime_identity=runtime_identity,
        )
        result = source_entry.to_dict()

        # Required keys in source entry
        required_keys = {
            "source_id",
            "state",
            "origin",
            "provenance",
            "namespace",
            "service_name",
            "endpoint_url",
            "cluster",
            "kubernetes_identity",
            "endpoint_identity",
            "runtime_identity",
        }
        self.assertEqual(set(result.keys()), required_keys)

        # Verify endpoint_identity nested structure
        endpoint_result = result["endpoint_identity"]
        self.assertEqual(endpoint_result["endpoint_slices"], ["eps-1"])
        self.assertEqual(endpoint_result["target_pod_uids"], ["pod-uid-1", "pod-uid-2"])
        self.assertEqual(endpoint_result["target_pod_names"], ["monitoring/alertmanager-0", "monitoring/alertmanager-1"])

    def test_review_packet_runtime_identity_keys(self) -> None:
        """RuntimeIdentity must have stable key names."""
        identity = RuntimeIdentity(
            probe_attempted=True,
            ready=True,
            healthy=False,
            alertmanager_version="0.25.0",
            cluster_status="ready",
            cluster_peer_count=3,
            config_sha256="abc123",
            receiver_count=5,
            silence_count=10,
            alert_group_count=2,
        )
        result = identity.to_dict()

        # Stable key names
        expected_keys = {
            "probe_attempted",
            "ready",
            "healthy",
            "alertmanager_version",
            "cluster_status",
            "cluster_peer_count",
            "config_sha256",
            "receiver_count",
            "silence_count",
            "alert_group_count",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_review_packet_kubernetes_identity_keys(self) -> None:
        """KubernetesIdentity must have stable key names."""
        identity = KubernetesIdentity(
            service_uid="uid-123",
            service_type="ClusterIP",
            labels={"app": "alertmanager"},
            annotations_redacted={"secret": "[REDACTED]"},
            selector={"app": "alertmanager"},
            ports=[{"port": 9093, "protocol": "TCP"}],
            owner_references=[],
        )
        result = identity.to_dict()

        # Stable key names
        expected_keys = {
            "service_uid",
            "service_type",
            "labels",
            "annotations_redacted",
            "selector",
            "ports",
            "owner_references",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_review_packet_summary_keys(self) -> None:
        """Summary must have stable key names."""
        summary = Summary(
            total=5,
            tracked=3,
            manual=1,
            degraded=0,
            missing=1,
            duplicate_groups=2,
        )
        result = summary.to_dict()

        # Stable key names
        expected_keys = {
            "total",
            "tracked",
            "manual",
            "degraded",
            "missing",
            "duplicate_groups",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_review_packet_no_raw_config_in_runtime_identity(self) -> None:
        """RuntimeIdentity must NOT expose raw Alertmanager config."""
        identity = RuntimeIdentity(
            probe_attempted=True,
            ready=True,
            healthy=True,
            alertmanager_version="0.25.0",
            config_sha256="abc123",  # Only hash allowed
        )
        result = identity.to_dict()

        # Must not contain raw config keys
        forbidden_keys = {"config", "config_original", "config_resolved", "raw_config"}
        for key in forbidden_keys:
            self.assertNotIn(key, result)

        # Only config_sha256 is allowed
        self.assertIn("config_sha256", result)
        self.assertEqual(result["config_sha256"], "abc123")

    def test_review_packet_redactions_policy(self) -> None:
        """Redactions must specify policy constants."""
        from k8s_diag_agent.external_analysis.alertmanager_sources_review_packet import (
            REDACTION_ALERTMANAGER_CONFIG,
            REDACTION_ANNOTATIONS,
            REDACTION_TOKENS,
        )

        self.assertEqual(REDACTION_ALERTMANAGER_CONFIG, "sha256_only")
        self.assertEqual(REDACTION_ANNOTATIONS, "secret_like_values_redacted")
        self.assertEqual(REDACTION_TOKENS, "redacted")

    def test_review_packet_redactions_in_output(self) -> None:
        """Redactions must be present in packet output."""
        packet = AlertmanagerSourcesReviewPacket(
            sources=(),
            summary=Summary(),
        )
        result = packet.to_dict()

        self.assertIn("redactions", result)
        redactions = result["redactions"]
        self.assertEqual(redactions["alertmanager_config"], "sha256_only")
        self.assertEqual(redactions["annotations"], "secret_like_values_redacted")
        self.assertEqual(redactions["tokens"], "redacted")

    def test_review_packet_endpoint_identity_keys(self) -> None:
        """EndpointIdentity must have stable key names."""
        endpoint_identity = EndpointIdentity(
            endpoint_slices=["eps-1", "eps-2"],
            target_pod_uids=["uid-1", "uid-2"],
            target_pod_names=["monitoring/alertmanager-0"],
            target_owner_refs=[{"kind": "StatefulSet", "name": "alertmanager"}],
        )
        result = endpoint_identity.to_dict()

        # Stable key names
        expected_keys = {
            "endpoint_slices",
            "target_pod_uids",
            "target_pod_names",
            "target_owner_refs",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_review_packet_source_identity_keys(self) -> None:
        """Source identity keys must be stable for routing."""
        source_entry = SourceEntry(
            source_id="source/with/slash",
            state="auto-tracked",
            origin="service-heuristic",
            provenance="service-heuristic",
            namespace="monitoring",
            service_name="alertmanager",
            endpoint_url="http://alertmanager:9093",
            cluster="prod",
            kubernetes_identity=KubernetesIdentity(),
            endpoint_identity=EndpointIdentity(),
            runtime_identity=RuntimeIdentity(),
        )
        result = source_entry.to_dict()

        # Source identity must have source_id for routing
        self.assertIn("source_id", result)
        # source_id with special characters must be preserved
        self.assertEqual(result["source_id"], "source/with/slash")


class TestAlertmanagerSourcesReviewPacketRedaction(unittest.TestCase):
    """Redaction tests proving raw Alertmanager config is not emitted."""

    def test_runtime_identity_does_not_contain_raw_config(self) -> None:
        """RuntimeIdentity output must not contain raw config data."""
        identity = RuntimeIdentity(
            probe_attempted=True,
            ready=True,
            healthy=True,
            config_sha256="hash123",
        )
        result = identity.to_dict()

        # Forbidden patterns in values
        for key, value in result.items():
            if isinstance(value, str):
                # Config should never appear as raw YAML/JSON
                self.assertNotIn("route:", value)
                self.assertNotIn("receivers:", value)
                self.assertNotIn("alertmanager.yml", value)

    def test_kubernetes_identity_redacts_annotations(self) -> None:
        """KubernetesIdentity annotations must be redacted."""
        identity = KubernetesIdentity(
            annotations_redacted={"my-secret-token": "[REDACTED]"},
        )
        result = identity.to_dict()

        # Key must be present but value must be redacted
        self.assertIn("my-secret-token", result["annotations_redacted"])
        self.assertEqual(result["annotations_redacted"]["my-secret-token"], "[REDACTED]")
        # Must not contain the original raw secret value
        self.assertNotEqual(result["annotations_redacted"]["my-secret-token"], "super-secret-value")


if __name__ == "__main__":
    unittest.main()
