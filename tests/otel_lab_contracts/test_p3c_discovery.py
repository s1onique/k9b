"""Tests for P3c discovery verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestP3cDiscoveryVerification:
    """Tests for P3c discovery contract verification."""

    def test_p3c_accepts_deployment_unavailable_shipping_without_rca(self) -> None:
        """P3c accepts deployment_unavailable with shipping reference, no RCA markers."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p3c_discovery

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            evidence = {
                "discovery_success": True,
                "incident_id": "inc-123",
                "candidate_class": "deployment_unavailable",
                "target_namespace": "otel-demo",
                "root_cause_summary": "The shipping deployment is unavailable",
                "shipping_reference_found": True,
                "namespace_matches": True,
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p3c_discovery(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_p3c_accepts_pending_pod_shipping(self) -> None:
        """P3c accepts pending_pod with shipping reference."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p3c_discovery

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            evidence = {
                "discovery_success": True,
                "incident_id": "inc-456",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "root_cause_summary": "Shipping pod is pending",
                "shipping_reference_found": True,
                "namespace_matches": True,
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p3c_discovery(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_p3c_rejects_wrong_namespace(self) -> None:
        """P3c rejects discovery with wrong namespace."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p3c_discovery

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            evidence = {
                "discovery_success": True,
                "incident_id": "inc-789",
                "candidate_class": "pending_pod",
                "target_namespace": "wrong-namespace",  # Wrong!
                "root_cause_summary": "Some pod is pending",
                "shipping_reference_found": True,
                "namespace_matches": False,
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p3c_discovery(artifact_dir, report)

            assert result is False
            assert "namespace" in str(report.errors).lower()

    def test_p3c_rejects_wrong_workload(self) -> None:
        """P3c rejects discovery without shipping reference."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p3c_discovery

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            evidence = {
                "discovery_success": True,
                "incident_id": "inc-101",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "root_cause_summary": "Some other deployment is pending",  # No shipping!
                "shipping_reference_found": False,
                "namespace_matches": True,
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p3c_discovery(artifact_dir, report)

            assert result is False
            assert any("shipping" in e.lower() for e in report.errors)

    def test_p3c_rejects_wrong_candidate_class(self) -> None:
        """P3c rejects unsupported candidate class."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p3c_discovery

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            evidence = {
                "discovery_success": True,
                "incident_id": "inc-202",
                "candidate_class": "unknown_class",  # Not accepted!
                "target_namespace": "otel-demo",
                "root_cause_summary": "Something is wrong",
                "shipping_reference_found": True,
                "namespace_matches": True,
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p3c_discovery(artifact_dir, report)

            assert result is False
            assert any("candidate_class" in e.lower() for e in report.errors)


class TestP3cShippingIdentityFromMultipleFields:
    """Tests for P3c shipping identity detection from multiple fields."""

    def test_p3c_accepts_shipping_from_object_name(self) -> None:
        """P3c accepts shipping identity from object_name field."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p3c_discovery

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            evidence = {
                "discovery_success": True,
                "incident_id": "inc-shipping-001",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "object_name": "shipping-backend-5f8d9b7c6-x9m2k",  # shipping in object_name
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p3c_discovery(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_p3c_accepts_shipping_from_incident_id(self) -> None:
        """P3c accepts shipping identity from incident_id field."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p3c_discovery

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            evidence = {
                "discovery_success": True,
                "incident_id": "inc-shipping-unavailable-123",  # shipping in incident_id
                "candidate_class": "deployment_unavailable",
                "target_namespace": "otel-demo",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p3c_discovery(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_p3c_accepts_shipping_from_matched_incident(self) -> None:
        """P3c accepts shipping identity from nested matched_incident structure."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p3c_discovery

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            evidence = {
                "discovery_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "matched_incident": {
                    "id": "shipping-incident-456",
                    "object_name": "shipping-deployment",
                },
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p3c_discovery(artifact_dir, report)

            assert result is True
            assert report.passed is True
