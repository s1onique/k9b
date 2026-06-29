"""Tests for OTel Demo K8s-native incident discovery - Verifier.

These tests verify standalone verifier function.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestK8sDetectionVerifier:
    """Test standalone verifier function."""

    def test_verifier_returns_false_when_evidence_missing(self) -> None:
        """Verifier returns False when detection evidence doesn't exist."""
        from scripts.k9b_otel_demo_lab_k8s_detection import verify_unschedulable_shipping_incident_discovered

        artifact_dir = Path("/tmp/nonexistent")
        result = verify_unschedulable_shipping_incident_discovered(artifact_dir)
        assert result["verified"] is False
        assert result["reason"] == "detection_evidence_not_found"

    def test_verifier_returns_false_when_discovery_failed(self) -> None:
        """Verifier returns False when discovery success is False."""
        from scripts.k9b_otel_demo_lab_k8s_detection import verify_unschedulable_shipping_incident_discovered

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            evidence = {
                "discovery_success": False,
                "failure_reason": "no_incident_found",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_incident_discovered(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "no_incident_found"

    def test_verifier_returns_false_when_validation_failed(self) -> None:
        """Verifier returns False when validation_success is False."""
        from scripts.k9b_otel_demo_lab_k8s_detection import verify_unschedulable_shipping_incident_discovered

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            evidence = {
                "discovery_success": True,
                "validation_success": False,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "shipping_reference_found": True,
                "namespace_matches": True,
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_incident_discovered(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "validation_failed"

    def test_verifier_returns_false_when_no_shipping_reference(self) -> None:
        """Verifier returns False when no shipping reference found."""
        from scripts.k9b_otel_demo_lab_k8s_detection import verify_unschedulable_shipping_incident_discovered

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "shipping_reference_found": False,
                "namespace_matches": True,
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_incident_discovered(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "no_shipping_reference"

    def test_verifier_passes_with_all_validations(self) -> None:
        """Verifier passes when all validations pass."""
        from scripts.k9b_otel_demo_lab_k8s_detection import verify_unschedulable_shipping_incident_discovered

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "shipping_reference_found": True,
                "namespace_matches": True,
                "target_namespace": "otel-demo",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_incident_discovered(artifact_dir)
            assert result["verified"] is True
            assert result["incident_id"] == "inc-123"
            assert result["candidate_class"] == "pending_pod"


class TestK8sDetectionArtifactSchema:
    """Test detection artifact schema contains required fields."""

    def test_verifier_checks_all_required_fields(self) -> None:
        """Verifier checks all required fields for strict validation."""
        from scripts.k9b_otel_demo_lab_k8s_detection import verify_unschedulable_shipping_incident_discovered

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            # Complete evidence with all required fields
            evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "shipping_reference_found": True,
                "namespace_matches": True,
                "target_namespace": "otel-demo",
                "discovery_source": "k9b_backend_api",
                "discovery_trigger": "snapshot_api",
                "signal_count": 2,
                "evidence_count": 2,
                "matching_signals": [{"type": "PendingPod"}],
                "matching_evidence": [{"type": "PendingPod"}],
                "poll_attempts": 3,
                "timeout_seconds": 120,
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_incident_discovered(artifact_dir)
            assert result["verified"] is True
