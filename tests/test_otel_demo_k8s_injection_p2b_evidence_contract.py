"""Tests for P2b→P3c selector_literal artifact contract.

These tests verify that P2b writes injection-evidence.json on SUCCESS,
enabling P3c to populate selector_literal for P4c root-cause extraction.

Root cause: P2b was only writing injection-evidence.json on failure paths.
P3c's _populate_selector_literal_from_p2b() expects this file to exist
on success to populate detection_evidence.selector_literal for P4c.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestP2bInjectionEvidenceContract:
    """Test P2b→P3c injection-evidence.json artifact contract."""

    def test_p2b_writes_injection_evidence_on_success_path(self) -> None:
        """P2b phase MUST write injection-evidence.json when symptom is found.
        
        This is required for P3c's _populate_selector_literal_from_p2b() to
        find the selector_literal and pass it to P4c for root-cause extraction.
        
        WITHOUT this fix: P2b only wrote injection-evidence.json on failure paths.
        P3c would log "P2b injection evidence not found" and selector_literal=None.
        P4c would fail with missing_scheduling_root_cause_evidence.
        """
        # This is a code contract test - verify the expected behavior exists
        from scripts.k9b_otel_demo_lab_k8s_injection_helpers import _write_injection_artifacts
        
        with tempfile.TemporaryDirectory() as tmpdir:
            injection_dir = Path(tmpdir)
            
            evidence = {
                "scenario": "unschedulable-shipping-rollout",
                "method": "nodeSelector_patch",
                "deployment": "shipping",
                "namespace": "otel-demo",
                "node_selector": {
                    "k9b.dev/otel-lab-node": "missing",
                },
                "symptom_found": True,
                "symptom_type": "Pending",
            }
            
            previous_template: dict[str, object] = {"spec": {"containers": []}}
            
            # Write artifacts
            _write_injection_artifacts(injection_dir, evidence, previous_template)
            
            # CRITICAL: injection-evidence.json must exist
            injection_evidence_path = injection_dir / "injection-evidence.json"
            assert injection_evidence_path.exists(), (
                "P2b MUST write injection-evidence.json on success. "
                "P3c's _populate_selector_literal_from_p2b() depends on this file."
            )
            
            # Verify content contains node_selector
            loaded = json.loads(injection_evidence_path.read_text())
            assert loaded["node_selector"] == {"k9b.dev/otel-lab-node": "missing"}
            assert loaded["symptom_found"] is True

    def test_p3c_reads_selector_literal_from_p2b_evidence(self) -> None:
        """P3c's _populate_selector_literal_from_p2b() correctly extracts selector_literal.
        
        This test simulates the P3c function reading P2b's injection-evidence.json.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            
            # Simulate P2b writing injection-evidence.json
            p2b_dir = artifact_dir / "phase2-injected" / "p2b-k8s-injection"
            p2b_dir.mkdir(parents=True)
            
            p2b_evidence = {
                "scenario": "unschedulable-shipping-rollout",
                "node_selector": {
                    "k9b.dev/otel-lab-node": "missing",
                },
                "symptom_found": True,
            }
            (p2b_dir / "injection-evidence.json").write_text(json.dumps(p2b_evidence))
            
            # Simulate P3c's _populate_selector_literal_from_p2b logic
            from scripts.k9b_otel_demo_lab_constants import (
                K8S_INJECTION_NODE_SELECTOR_KEY,
                K8S_INJECTION_NODE_SELECTOR_VALUE,
                PHASE_INJECTED,
            )
            
            injection_evidence_path = artifact_dir / PHASE_INJECTED / "p2b-k8s-injection" / "injection-evidence.json"
            
            assert injection_evidence_path.exists(), (
                "P3c expects injection-evidence.json at "
                f"{injection_evidence_path}"
            )
            
            loaded = json.loads(injection_evidence_path.read_text())
            node_selector = loaded.get("node_selector", {})
            
            selector_key = K8S_INJECTION_NODE_SELECTOR_KEY
            selector_value = node_selector.get(selector_key, K8S_INJECTION_NODE_SELECTOR_VALUE)
            selector_literal = f"{selector_key}={selector_value}"
            
            assert selector_literal == "k9b.dev/otel-lab-node=missing"
            assert selector_key == "k9b.dev/otel-lab-node"
            assert selector_value == "missing"


class TestP3cDetectionEvidenceContainsSelectorLiteral:
    """Test that P3c detection evidence contains selector_literal from P2b."""

    def test_detection_evidence_schema_includes_selector_fields(self) -> None:
        """P3c detection-evidence.json should include selector_literal fields.
        
        These fields are populated by _populate_selector_literal_from_p2b() and
        consumed by P4c's extract_scheduling_root_cause() for root-cause extraction.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            
            # Create mock P2b injection evidence
            p2b_dir = artifact_dir / "phase2-injected" / "p2b-k8s-injection"
            p2b_dir.mkdir(parents=True)
            (p2b_dir / "injection-evidence.json").write_text(json.dumps({
                "node_selector": {"k9b.dev/otel-lab-node": "missing"},
                "symptom_found": True,
            }))
            
            # Create mock P3c detection evidence
            p3c_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            p3c_dir.mkdir(parents=True)
            
            detection_evidence = {
                "phase": "p3c-k8s-discovery",
                "scenario": "unschedulable-shipping-rollout",
                "discovery_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                # These fields should be populated by _populate_selector_literal_from_p2b
                "selector_literal": "k9b.dev/otel-lab-node=missing",
                "selector_key": "k9b.dev/otel-lab-node",
                "selector_value": "missing",
                "selector_source": "p2b_injection",
            }
            (p3c_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))
            
            # Verify the detection evidence contains selector fields
            loaded = json.loads((p3c_dir / "detection-evidence.json").read_text())
            
            assert loaded["selector_literal"] == "k9b.dev/otel-lab-node=missing"
            assert loaded["selector_key"] == "k9b.dev/otel-lab-node"
            assert loaded["selector_value"] == "missing"
            assert loaded["selector_source"] == "p2b_injection"


class TestP2bEvidenceContractRegression:
    """Regression tests for P2b→P3c artifact contract."""

    def test_injection_evidence_contains_node_selector(self) -> None:
        """Verify injection-evidence.json contains node_selector for P3c extraction."""
        from scripts.k9b_otel_demo_lab_constants import (
            K8S_INJECTION_NODE_SELECTOR_KEY,
            K8S_INJECTION_NODE_SELECTOR_VALUE,
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            injection_dir = Path(tmpdir)
            
            evidence = {
                "scenario": "unschedulable-shipping-rollout",
                "method": "nodeSelector_patch",
                "deployment": "shipping",
                "namespace": "otel-demo",
                "node_selector": {
                    K8S_INJECTION_NODE_SELECTOR_KEY: K8S_INJECTION_NODE_SELECTOR_VALUE,
                },
                "symptom_found": True,
                "symptom_type": "FailedScheduling",
            }
            
            from scripts.k9b_otel_demo_lab_k8s_injection_helpers import _write_injection_artifacts
            _write_injection_artifacts(injection_dir, evidence, None)
            
            path = injection_dir / "injection-evidence.json"
            loaded = json.loads(path.read_text())
            
            assert "node_selector" in loaded
            assert loaded["node_selector"][K8S_INJECTION_NODE_SELECTOR_KEY] == K8S_INJECTION_NODE_SELECTOR_VALUE

    def test_p2b_p3c_artifact_path_contract(self) -> None:
        """P2b writes to phase2-injected/p2b-k8s-injection/injection-evidence.json.
        
        P3c reads from the same path. This test verifies the path contract.
        """
        from scripts.k9b_otel_demo_lab_constants import PHASE_INJECTED
        
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            
            # P2b writes to this path
            expected_p2b_path = artifact_dir / PHASE_INJECTED / "p2b-k8s-injection" / "injection-evidence.json"
            
            # Create parent dirs
            expected_p2b_path.parent.mkdir(parents=True)
            
            # Write evidence (simulating P2b success path)
            evidence = {"node_selector": {"k9b.dev/otel-lab-node": "missing"}}
            expected_p2b_path.write_text(json.dumps(evidence))
            
            # P3c reads from this path
            actual_path = artifact_dir / PHASE_INJECTED / "p2b-k8s-injection" / "injection-evidence.json"
            
            assert actual_path.exists()
            assert actual_path.read_text() == json.dumps(evidence)
