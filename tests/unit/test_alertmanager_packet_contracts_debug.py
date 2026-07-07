"""Golden/contract tests for Alertmanager source debug packet.

Tests that the debug packet schema is stable and conforms to the canonical wire schema
k9b.alertmanager_source.debug_packet.v1.

Run with: python -m pytest tests/unit/test_alertmanager_packet_contracts_debug.py -v
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.alertmanager_source_debug_packet import (
    AlertmanagerSourceDebugPacket,
    DiscoveryReason,
    HttpProbeResult,
    HttpProbeResults,
    KubernetesProbeData,
)


class TestAlertmanagerSourceDebugPacketContract(unittest.TestCase):
    """Contract tests for AlertmanagerSourceDebugPacket canonical schema."""

    def test_schema_version_matches_canonical(self) -> None:
        """Schema version must be k9b.alertmanager_source.debug_packet.v1."""
        from k8s_diag_agent.external_analysis.alertmanager_source_debug_packet import SCHEMA_VERSION

        self.assertEqual(SCHEMA_VERSION, "k9b.alertmanager_source.debug_packet.v1")

    def test_debug_packet_to_dict_has_required_top_level_keys(self) -> None:
        """Debug packet must have all required top-level keys."""
        packet = AlertmanagerSourceDebugPacket(
            source_id="test-source",
            discovery_reason=DiscoveryReason(),
            kubernetes_probe=KubernetesProbeData(),
            http_probe=HttpProbeResults(),
        )
        result = packet.to_dict()

        # Required top-level keys
        required_keys = {
            "schema_version",
            "artifact_id",
            "generated_at",
            "source_id",
            "discovery_reason",
            "kubernetes_probe",
            "http_probe",
            "errors",
        }
        self.assertEqual(set(result.keys()), required_keys)

    def test_debug_packet_schema_version_in_output(self) -> None:
        """Schema version must appear in output dict."""
        packet = AlertmanagerSourceDebugPacket(
            source_id="test-source",
            discovery_reason=DiscoveryReason(),
            kubernetes_probe=KubernetesProbeData(),
            http_probe=HttpProbeResults(),
        )
        result = packet.to_dict()

        self.assertEqual(result["schema_version"], "k9b.alertmanager_source.debug_packet.v1")

    def test_debug_packet_http_probe_result_keys(self) -> None:
        """HttpProbeResult must have stable key names."""
        result = HttpProbeResult(
            url="http://alertmanager:9093/-/healthy",
            status_code=200,
            latency_ms=15.5,
            error=None,
        )
        output = result.to_dict()

        # Stable key names
        expected_keys = {"url", "status_code", "latency_ms", "error"}
        self.assertEqual(set(output.keys()), expected_keys)

    def test_debug_packet_http_probe_results_keys(self) -> None:
        """HttpProbeResults must have stable key names."""
        results = HttpProbeResults(
            healthy=HttpProbeResult(url="http://alertmanager:9093/-/healthy", status_code=200),
            ready=HttpProbeResult(url="http://alertmanager:9093/-/ready", status_code=200),
            status=HttpProbeResult(url="http://alertmanager:9093/api/v2/status", status_code=200),
        )
        output = results.to_dict()

        # Stable key names
        expected_keys = {"healthy", "ready", "status"}
        self.assertEqual(set(output.keys()), expected_keys)

    def test_debug_packet_kubernetes_probe_data_keys(self) -> None:
        """KubernetesProbeData must have stable key names."""
        data = KubernetesProbeData(
            service={"metadata": {"name": "alertmanager"}},
            endpoints={},
            endpoint_slices=[],
            pods=[],
            alertmanager_cr_matches=[],
            statefulset_matches=[],
        )
        output = data.to_dict()

        # Stable key names
        expected_keys = {
            "service",
            "endpoints",
            "endpoint_slices",
            "pods",
            "alertmanager_cr_matches",
            "statefulset_matches",
        }
        self.assertEqual(set(output.keys()), expected_keys)

    def test_debug_packet_discovery_reason_keys(self) -> None:
        """DiscoveryReason must have stable key names."""
        reason = DiscoveryReason(
            matched_heuristic="service_name_or_label",
            matched_fields=["service.metadata.name", "service.labels.app"],
            confidence="high",
        )
        output = reason.to_dict()

        # Stable key names
        expected_keys = {"matched_heuristic", "matched_fields", "confidence"}
        self.assertEqual(set(output.keys()), expected_keys)

    def test_debug_packet_source_id_with_special_chars(self) -> None:
        """Source IDs with slash/URL-encoded chars must be preserved."""
        packet = AlertmanagerSourceDebugPacket(
            source_id="source/with/slash/and%20space",
            discovery_reason=DiscoveryReason(),
            kubernetes_probe=KubernetesProbeData(),
            http_probe=HttpProbeResults(),
        )
        result = packet.to_dict()

        self.assertEqual(result["source_id"], "source/with/slash/and%20space")

    def test_debug_packet_errors_list(self) -> None:
        """Errors must be a list, even when empty."""
        packet = AlertmanagerSourceDebugPacket(
            source_id="test",
            discovery_reason=DiscoveryReason(),
            kubernetes_probe=KubernetesProbeData(),
            http_probe=HttpProbeResults(),
            errors=["Connection timeout", "Retry failed"],
        )
        result = packet.to_dict()

        self.assertIsInstance(result["errors"], list)
        self.assertEqual(len(result["errors"]), 2)


class TestAlertmanagerSourceDebugPacketProbeMapping(unittest.TestCase):
    """Probe mapping regression tests covering healthy=200 and ready=503."""

    def test_http_probes_maps_healthy_correctly(self) -> None:
        """HTTP probe results must map healthy status correctly."""
        # Simulate healthy probe returning 200
        healthy_result = HttpProbeResult(
            url="http://alertmanager:9093/-/healthy",
            status_code=200,
            latency_ms=5.0,
        )
        # Simulate ready probe returning 503 (not ready)
        ready_result = HttpProbeResult(
            url="http://alertmanager:9093/-/ready",
            status_code=503,
            latency_ms=10.0,
        )
        status_result = HttpProbeResult(
            url="http://alertmanager:9093/api/v2/status",
            status_code=200,
            latency_ms=20.0,
        )

        probes = HttpProbeResults(
            healthy=healthy_result,
            ready=ready_result,
            status=status_result,
        )
        output = probes.to_dict()

        # Verify healthy probe maps to healthy key
        self.assertEqual(output["healthy"]["status_code"], 200)
        self.assertIsNone(output["healthy"]["error"])

        # Verify ready probe maps to ready key
        self.assertEqual(output["ready"]["status_code"], 503)
        self.assertIsNone(output["ready"]["error"])  # 503 is still a valid HTTP response

    def test_http_probes_healthy_endpoint_returns_200_when_healthy(self) -> None:
        """Healthy endpoint should return 200 when Alertmanager is healthy."""
        healthy_result = HttpProbeResult(
            url="http://alertmanager:9093/-/healthy",
            status_code=200,
            latency_ms=3.0,
        )
        ready_result = HttpProbeResult(
            url="http://alertmanager:9093/-/ready",
            status_code=200,
            latency_ms=5.0,
        )

        probes = HttpProbeResults(
            healthy=healthy_result,
            ready=ready_result,
            status=None,
        )
        output = probes.to_dict()

        # Both healthy and ready should be 200
        self.assertEqual(output["healthy"]["status_code"], 200)
        self.assertEqual(output["ready"]["status_code"], 200)

    def test_http_probes_ready_endpoint_returns_503_when_not_ready(self) -> None:
        """Ready endpoint should return 503 when Alertmanager is not ready."""
        healthy_result = HttpProbeResult(
            url="http://alertmanager:9093/-/healthy",
            status_code=200,
            latency_ms=3.0,
        )
        ready_result = HttpProbeResult(
            url="http://alertmanager:9093/-/ready",
            status_code=503,
            latency_ms=100.0,
            error="Service not ready",
        )

        probes = HttpProbeResults(
            healthy=healthy_result,
            ready=ready_result,
            status=None,
        )
        output = probes.to_dict()

        # Ready should be 503
        self.assertEqual(output["ready"]["status_code"], 503)
        self.assertIsNotNone(output["ready"]["error"])

    def test_http_probes_error_propagates_to_probe_result(self) -> None:
        """Probe errors should be captured in the probe result."""
        error_result = HttpProbeResult(
            url="http://alertmanager:9093/-/healthy",
            status_code=None,
            latency_ms=5000.0,
            error="Connection refused",
        )

        probes = HttpProbeResults(
            healthy=error_result,
            ready=None,
            status=None,
        )
        output = probes.to_dict()

        self.assertIsNone(output["healthy"]["status_code"])
        self.assertEqual(output["healthy"]["error"], "Connection refused")


class TestAlertmanagerSourceDebugPacketRedaction(unittest.TestCase):
    """Redaction tests proving raw Alertmanager config is not emitted."""

    def test_http_probes_do_not_contain_raw_config(self) -> None:
        """HTTP probe results must not contain raw config data."""
        probes = HttpProbeResults(
            healthy=HttpProbeResult(url="http://alertmanager:9093/-/healthy", status_code=200),
            ready=HttpProbeResult(url="http://alertmanager:9093/-/ready", status_code=200),
            status=HttpProbeResult(url="http://alertmanager:9093/api/v2/status", status_code=200),
        )
        output = probes.to_dict()

        # Each probe result should only have URL, status_code, latency_ms, error
        for key in ["healthy", "ready", "status"]:
            probe = output[key]
            self.assertIn("url", probe)
            self.assertIn("status_code", probe)
            # No config fields allowed
            self.assertNotIn("config", probe)
            self.assertNotIn("receivers", probe)

    def test_kubernetes_probe_data_is_not_raw_config(self) -> None:
        """Kubernetes probe data must not be raw Alertmanager config."""
        k8s_data = KubernetesProbeData(
            service={"kind": "Service", "metadata": {"name": "alertmanager"}},
            endpoints={"kind": "Endpoints"},
            endpoint_slices=[],
            pods=[],
            alertmanager_cr_matches=[],
            statefulset_matches=[],
        )
        output = k8s_data.to_dict()

        # Should not contain Alertmanager config keys
        for key, value in output.items():
            if isinstance(value, dict):
                self.assertNotIn("config", value)
                self.assertNotIn("route", value)
                self.assertNotIn("receivers", value)


if __name__ == "__main__":
    unittest.main()
