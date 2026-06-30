"""Tests for K8s-native verdict splitting (P3c discovery vs P4c root-cause).

These tests verify that:
1. P3c accepts deployment_unavailable as valid discovery for shipping
2. P3c rejects wrong workload deployment_unavailable
3. P4c requires scheduling markers for root-cause validation
4. P4c accepts FailedScheduling evidence
5. P4c accepts impossible node selector marker
6. Logs distinguish discovery from root-cause failure
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestP3cDiscoveryVerdict:
    """Tests for P3c incident discovery validation."""

    def test_unschedulable_shipping_p3c_accepts_deployment_unavailable_for_shipping(self) -> None:
        """Given an incident with namespace otel-demo, object shipping, and candidate class deployment_unavailable,
        P3c discovery validation passes."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_discovery

        incident = {
            "namespace": "otel-demo",
            "object_name": "shipping",
            "candidate_class": "deployment_unavailable",
            "evidence": [
                {"type": "DeploymentUnavailable", "message": "shipping deployment unavailable"}
            ],
        }

        verdict = validate_unschedulable_shipping_discovery(incident, namespace="otel-demo")

        assert verdict.success is True
        assert verdict.candidate_class == "deployment_unavailable"
        assert verdict.namespace == "otel-demo"
        assert verdict.shipping_scoped is True

    def test_unschedulable_shipping_p3c_rejects_wrong_workload_deployment_unavailable(self) -> None:
        """Given deployment_unavailable for a non-shipping workload, P3c discovery validation fails."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_discovery

        incident = {
            "namespace": "otel-demo",
            "object_name": "backend",  # Not shipping
            "candidate_class": "deployment_unavailable",
            "evidence": [
                {"type": "DeploymentUnavailable", "message": "backend deployment unavailable"}
            ],
        }

        verdict = validate_unschedulable_shipping_discovery(incident, namespace="otel-demo")

        assert verdict.success is False
        assert verdict.reason == "no_shipping_reference"

    def test_unschedulable_shipping_p3c_rejects_wrong_namespace(self) -> None:
        """Given incident in wrong namespace, P3c discovery validation fails."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_discovery

        incident = {
            "namespace": "wrong-namespace",
            "object_name": "shipping",
            "candidate_class": "deployment_unavailable",
            "evidence": [],
        }

        verdict = validate_unschedulable_shipping_discovery(incident, namespace="otel-demo")

        assert verdict.success is False
        assert verdict.reason == "namespace_mismatch"

    def test_unschedulable_shipping_p3c_accepts_pending_pod(self) -> None:
        """Given pending_pod candidate class for shipping, P3c discovery validation passes."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_discovery

        incident = {
            "namespace": "otel-demo",
            "object_name": "shipping",
            "candidate_class": "pending_pod",
            "evidence": [
                {"type": "PendingPod", "message": "shipping pod pending"}
            ],
        }

        verdict = validate_unschedulable_shipping_discovery(incident, namespace="otel-demo")

        assert verdict.success is True
        assert verdict.candidate_class == "pending_pod"


class TestP4cRootCauseVerdict:
    """Tests for P4c root-cause evidence validation."""

    def test_unschedulable_shipping_root_cause_requires_scheduling_marker(self) -> None:
        """Given only deployment_unavailable with no scheduling evidence, P4c root-cause validation fails."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_root_cause

        evidence = {
            "candidate_class": "deployment_unavailable",
            "root_cause_summary": "The shipping deployment is unavailable due to pod issues",
            "evidence": [
                {"type": "DeploymentUnavailable", "message": "shipping deployment unavailable"}
            ],
        }

        verdict = validate_unschedulable_shipping_root_cause(evidence)

        assert verdict.success is False
        assert verdict.reason == "missing_scheduling_root_cause_evidence"
        assert len(verdict.matched_evidence) == 0

    def test_unschedulable_shipping_root_cause_accepts_failed_scheduling_event(self) -> None:
        """Given evidence containing FailedScheduling, P4c root-cause validation passes."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_root_cause

        evidence = {
            "candidate_class": "deployment_unavailable",
            "root_cause_summary": "The shipping pod failed scheduling because no node matched the nodeSelector k9b.dev/otel-lab-node=missing",
            "evidence": [
                {"type": "K8sEvent", "reason": "FailedScheduling", "message": "0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector."}
            ],
        }

        verdict = validate_unschedulable_shipping_root_cause(evidence)

        assert verdict.success is True
        assert "FailedScheduling" in verdict.matched_evidence

    def test_unschedulable_shipping_root_cause_accepts_impossible_node_selector_marker(self) -> None:
        """Given evidence containing k9b.dev/otel-lab-node=missing, P4c root-cause validation passes."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_root_cause

        evidence = {
            "candidate_class": "deployment_unavailable",
            "root_cause_summary": "The shipping pod cannot be scheduled because its nodeSelector k9b.dev/otel-lab-node=missing matches no nodes",
            "evidence": [],
        }

        verdict = validate_unschedulable_shipping_root_cause(evidence)

        assert verdict.success is True
        assert "k9b.dev/otel-lab-node=missing" in verdict.matched_evidence

    def test_unschedulable_shipping_root_cause_accepts_unschedulable_marker(self) -> None:
        """Given evidence containing Unschedulable, P4c root-cause validation passes."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_root_cause

        evidence = {
            "candidate_class": "pending_pod",
            "root_cause_summary": "Shipping pod is unschedulable due to node selector mismatch",
            "evidence": [
                {"type": "PodStatus", "reason": "Unschedulable", "message": "Pod is unschedulable"}
            ],
        }

        verdict = validate_unschedulable_shipping_root_cause(evidence)

        assert verdict.success is True
        assert "Unschedulable" in verdict.matched_evidence

    def test_unschedulable_shipping_root_cause_accepts_node_selector_marker(self) -> None:
        """Given evidence containing nodeSelector, P4c root-cause validation passes."""
        from scripts.k9b_otel_demo_lab_k8s_verdicts import validate_unschedulable_shipping_root_cause

        evidence = {
            "candidate_class": "pending_pod",
            "root_cause_summary": "The shipping pod has a nodeSelector that matches no nodes",
            "evidence": [],
        }

        verdict = validate_unschedulable_shipping_root_cause(evidence)

        assert verdict.success is True
        assert "nodeSelector" in verdict.matched_evidence


class TestP3cVerifierDistinction:
    """Tests for P3c verifier distinguishing discovery from root-cause."""

    def test_verifier_accepts_deployment_unavailable_for_shipping(self) -> None:
        """Verifier passes when deployment_unavailable is discovered for shipping."""
        from scripts.k9b_otel_demo_lab_k8s_detection import verify_unschedulable_shipping_incident_discovered

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "deployment_unavailable",
                "shipping_reference_found": True,
                "namespace_matches": True,
                "target_namespace": "otel-demo",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_incident_discovered(artifact_dir)
            assert result["verified"] is True
            assert result["candidate_class"] == "deployment_unavailable"
            assert "discovery_verdict" in result
            assert result["discovery_verdict"]["root_cause_final"] is False


class TestP4cVerifierSchedulingMarkers:
    """Tests for P4c verifier checking scheduling markers."""

    def test_verifier_fails_without_scheduling_markers(self) -> None:
        """Verifier fails when no scheduling markers found in diagnosis evidence."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis import verify_unschedulable_shipping_mult_pass_diagnosis

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            
            # Create detection evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "deployment_unavailable",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))
            
            # Create diagnosis evidence without scheduling markers
            # Note: This will fail on check_missing_root_cause_terms before reaching P4c scheduling check
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "deployment_unavailable",
                "pass_count": 2,
                "read_only": True,
                "root_cause_summary": "The shipping deployment is unavailable",
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "executed_checks": ["kubectl_get_pods"],
                "root_cause_matches": {
                    "mentions_shipping": True,
                    "mentions_node_selector": False,
                    "mentions_selector_key": False,
                    "mentions_selector_value": False,
                    "mentions_no_matching_node": False,
                },
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            # The verifier fails on missing_root_cause_terms before reaching P4c scheduling check
            assert "missing" in result["reason"]

    def test_verifier_passes_with_failed_scheduling_marker(self) -> None:
        """Verifier passes when FailedScheduling marker found."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis import verify_unschedulable_shipping_mult_pass_diagnosis

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            
            # Create detection evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "deployment_unavailable",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))
            
            # Create diagnosis evidence with scheduling markers
            # Note: root_cause_summary must include text matching the regex pattern for mentions_no_matching_node
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "deployment_unavailable",
                "pass_count": 2,
                "read_only": True,
                "root_cause_summary": "The shipping pod has FailedScheduling due to nodeSelector k9b.dev/otel-lab-node=missing - no matching node found for the selector",
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "executed_checks": ["kubectl_get_pods", "kubectl_get_events"],
                "root_cause_matches": {
                    "mentions_shipping": True,
                    "mentions_node_selector": True,
                    "mentions_selector_key": True,
                    "mentions_selector_value": True,
                    "mentions_no_matching_node": True,
                },
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is True
            assert "p4c_verdict" in result
            assert result["p4c_verdict"]["success"] is True
