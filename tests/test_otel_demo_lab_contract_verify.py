"""Tests for k9b_otel_demo_lab_contract_verify.

These tests verify the live-lab contract verifier for unschedulable-shipping scenario.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestP3cDiscoveryVerification:
    """Tests for P3c discovery contract verification."""

    def test_p3c_accepts_deployment_unavailable_shipping_without_rca(self) -> None:
        """P3c accepts deployment_unavailable with shipping reference, no RCA markers."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p3c_discovery,
        )

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
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p3c_discovery,
        )

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
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p3c_discovery,
        )

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
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p3c_discovery,
        )

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
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p3c_discovery,
        )

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


class TestP4cDiagnosisVerification:
    """Tests for P4c diagnosis contract verification."""

    def test_p4c_requires_shipping_identity(self) -> None:
        """P4c requires shipping reference in root_cause_summary."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p4c_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": "Generic deployment issue",  # No shipping!
                "executed_checks": [],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is False
            assert any("shipping" in e.lower() for e in report.errors)

    def test_p4c_requires_scheduling_marker(self) -> None:
        """P4c requires scheduling root-cause marker."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p4c_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": "The shipping deployment has issues",  # No scheduling marker!
                "executed_checks": [],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is False
            assert any("scheduling" in e.lower() for e in report.errors)

    def test_p4c_rejects_generic_deployment_unavailable(self) -> None:
        """P4c rejects diagnosis without scheduling-specific evidence."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p4c_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": "The shipping deployment is unavailable",  # No nodeSelector!
                "executed_checks": [],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is False
            assert any("scheduling" in e.lower() for e in report.errors)

    def test_p4c_accepts_valid_scheduling_diagnosis(self) -> None:
        """P4c accepts diagnosis with scheduling-specific evidence."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p4c_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing. No node has this label, "
                    "so the pod cannot be scheduled (FailedScheduling)."
                ),
                "executed_checks": ["kubectl_get_deployment", "kubectl_get_pods"],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_p4c_rejects_simulation(self) -> None:
        """P4c rejects when real_loop_invoked is False."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_p4c_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": False,  # Simulation!
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": (
                    "The shipping deployment has nodeSelector k9b.dev/otel-lab-node=missing"
                ),
                "executed_checks": [],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is False
            assert any("simulation" in e.lower() or "real_loop" in e.lower() for e in report.errors)


class TestRuntimeLoopPassVerification:
    """Tests for runtime loop-pass artifact verification."""

    def test_runtime_pass_artifact_requires_schema_fields(self) -> None:
        """Pass artifact must have all required schema fields."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_runtime_loop_passes,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            # Missing required fields
            artifact = {
                "loop_run_id": "run-1",
                "incident_id": "inc-123",
                # Missing: pass_index, case_file_hash, etc.
            }
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("missing required fields" in e.lower() for e in report.errors)

    def test_runtime_rejects_unsafe_executed_count(self) -> None:
        """Runtime rejects when unsafe_check_count > 0."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_runtime_loop_passes,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            artifact = {
                "loop_run_id": "run-1",
                "incident_id": "inc-123",
                "pass_index": 1,
                "case_file_hash": "abc123",
                "proposed_checks": ["check1"],
                "accepted_checks": ["check1"],
                "rejected_checks": [],
                "check_fingerprints": ["fp1"],
                "new_evidence_hashes": [],
                "duplicate_check_count": 0,
                "unsafe_check_count": 1,  # Unsafe!
                "root_cause_summary": "Test",
                "confidence": "high",
                "should_continue": True,
                "stop_reason": None,
                "safety_metadata": {
                    "policy_enforced": True,
                    "mutating_checks_executed_count": 0,
                    "sensitive_reads_executed_count": 0,
                },
                "gate_summary": {"rejected_checks": []},
            }
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("unsafe" in e.lower() for e in report.errors)

    def test_runtime_rejects_sensitive_executed_count(self) -> None:
        """Runtime rejects when sensitive_reads_executed_count > 0."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_runtime_loop_passes,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            artifact = {
                "loop_run_id": "run-1",
                "incident_id": "inc-123",
                "pass_index": 1,
                "case_file_hash": "abc123",
                "proposed_checks": ["check1"],
                "accepted_checks": ["check1"],
                "rejected_checks": [],
                "check_fingerprints": ["fp1"],
                "new_evidence_hashes": [],
                "duplicate_check_count": 0,
                "unsafe_check_count": 0,
                "root_cause_summary": "Test",
                "confidence": "high",
                "should_continue": True,
                "stop_reason": None,
                "safety_metadata": {
                    "policy_enforced": True,
                    "mutating_checks_executed_count": 0,
                    "sensitive_reads_executed_count": 1,  # Sensitive!
                },
                "gate_summary": {"rejected_checks": []},
            }
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("sensitive" in e.lower() for e in report.errors)

    def test_runtime_requires_accepted_checks_fingerprint_alignment(self) -> None:
        """Accepted checks must align with check fingerprints."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_runtime_loop_passes,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            artifact = {
                "loop_run_id": "run-1",
                "incident_id": "inc-123",
                "pass_index": 1,
                "case_file_hash": "abc123",
                "proposed_checks": ["check1", "check2"],
                "accepted_checks": ["check1", "check2"],
                "rejected_checks": [],
                "check_fingerprints": ["fp1"],  # Mismatch!
                "new_evidence_hashes": [],
                "duplicate_check_count": 0,
                "unsafe_check_count": 0,
                "root_cause_summary": "Test",
                "confidence": "high",
                "should_continue": True,
                "stop_reason": None,
                "safety_metadata": {
                    "policy_enforced": True,
                    "mutating_checks_executed_count": 0,
                    "sensitive_reads_executed_count": 0,
                },
                "gate_summary": {"rejected_checks": []},
            }
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("accepted_checks" in e.lower() and "fingerprints" in e.lower() for e in report.errors)

    def test_runtime_rejects_rejected_check_in_accepted_checks(self) -> None:
        """Rejected check IDs must not appear in accepted checks."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_runtime_loop_passes,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            artifact = {
                "loop_run_id": "run-1",
                "incident_id": "inc-123",
                "pass_index": 1,
                "case_file_hash": "abc123",
                "proposed_checks": ["check1", "check2"],
                "accepted_checks": ["check1", "check2"],
                "rejected_checks": ["check1"],  # check1 is also accepted!
                "check_fingerprints": ["fp1", "fp2"],
                "new_evidence_hashes": [],
                "duplicate_check_count": 0,
                "unsafe_check_count": 0,
                "root_cause_summary": "Test",
                "confidence": "high",
                "should_continue": True,
                "stop_reason": None,
                "safety_metadata": {
                    "policy_enforced": True,
                    "mutating_checks_executed_count": 0,
                    "sensitive_reads_executed_count": 0,
                },
                "gate_summary": {"rejected_checks": ["check1"]},
            }
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("rejected" in e.lower() and "accepted" in e.lower() for e in report.errors)


class TestBoundedLoopPolicy:
    """Tests for bounded-loop policy verification."""

    def test_bounded_loop_defaults_are_enforced(self) -> None:
        """Default bounded-loop policy is enforced when no policy metadata."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_runtime_loop_passes,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            # 3 passes (exceeds default max_passes=2)
            for i in range(3):
                artifact = {
                    "loop_run_id": f"run-{i+1}",
                    "incident_id": "inc-123",
                    "pass_index": i + 1,
                    "case_file_hash": f"hash{i}",
                    "proposed_checks": [],
                    "accepted_checks": [],
                    "rejected_checks": [],
                    "check_fingerprints": [],
                    "new_evidence_hashes": [],
                    "duplicate_check_count": 0,
                    "unsafe_check_count": 0,
                    "root_cause_summary": "Test",
                    "confidence": "high",
                    "should_continue": i < 2,
                    "stop_reason": "max_passes_reached" if i == 2 else None,
                    "safety_metadata": {
                        "policy_enforced": True,
                        "mutating_checks_executed_count": 0,
                        "sensitive_reads_executed_count": 0,
                    },
                    "gate_summary": {"rejected_checks": []},
                }
                (loop_dir / f"pass-{i+1}.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("pass count" in e.lower() for e in report.errors)


class TestSensitivePayloadScan:
    """Tests for sensitive payload scanning."""

    def test_sensitive_payload_scan_rejects_bearer_token(self) -> None:
        """Scan rejects artifacts with bearer token."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            scan_for_sensitive_payloads,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            artifact = {
                "incident_id": "inc-123",
                "evidence": {
                    "token": "Bearer eyJhbGciOiJSUzI1NiIs...",
                },
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
            assert any("sensitive" in e.lower() or "forbidden" in e.lower() for e in report.errors)

    def test_sensitive_payload_scan_allows_sensitive_read_denied(self) -> None:
        """Scan allows safe patterns like sensitive_read_denied."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            scan_for_sensitive_payloads,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            artifact = {
                "incident_id": "inc-123",
                "checks": [
                    {
                        "check_id": "kubectl_get_secrets",
                        "result": "sensitive_read_denied",
                    }
                ],
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_sensitive_payload_scan_rejects_kubeconfig(self) -> None:
        """Scan rejects artifacts with kubeconfig data."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            scan_for_sensitive_payloads,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            artifact = {
                "incident_id": "inc-123",
                "evidence": {
                    "kubeconfig": "apiVersion: v1\nclusters:\n- cluster:\n    server: https://...",
                },
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False


class TestOtelTraceVerification:
    """Tests for OTel trace verification."""

    def test_otel_trace_auto_skips_when_missing(self) -> None:
        """OTel traces in auto mode skip when no traces found."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            OtelTracesMode,
            VerificationReport,
            verify_otel_traces,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.AUTO, report)

            assert result is True
            assert any(c.reason == "skipped_missing" for c in report.checks)

    def test_otel_trace_require_fails_when_missing(self) -> None:
        """OTel traces in require mode fails when no traces found."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            OtelTracesMode,
            VerificationReport,
            verify_otel_traces,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.REQUIRE, report)

            assert result is False
            assert any("required" in e.lower() and "trace" in e.lower() for e in report.errors)

    def test_otel_trace_skip_does_not_inspect(self) -> None:
        """OTel traces in skip mode does not inspect."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            OtelTracesMode,
            VerificationReport,
            verify_otel_traces,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.SKIP, report)

            assert result is True
            assert any(c.reason == "skipped" for c in report.checks)

    def test_otel_trace_require_accepts_expected_spans(self) -> None:
        """OTel traces in require mode accepts traces with expected spans."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            OtelTracesMode,
            VerificationReport,
            verify_otel_traces,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create trace artifact with expected spans
            trace = {
                "spans": [
                    {"name": "k9b.diagnosis_loop.budget", "span_id": "1"},
                    {"name": "k9b.diagnosis_loop.plan", "span_id": "2"},
                    {"name": "k9b.diagnosis_loop.gate", "span_id": "3"},
                    {"name": "k9b.diagnosis_loop.execute", "span_id": "4"},
                    {"name": "k9b.diagnosis_loop.artifact", "span_id": "5"},
                ],
                "events": [
                    {"name": "k9b.diagnosis_loop.checks_executed"},
                    {"name": "k9b.diagnosis_loop.artifact_written"},
                ],
            }
            (artifact_dir / "traces.json").write_text(json.dumps(trace))

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.REQUIRE, report)

            assert result is True
            assert any(c.name == "otel_traces" and c.passed for c in report.checks)


class TestLabResultVerification:
    """Tests for lab-result.json verification."""

    def test_lab_result_requires_success_field(self) -> None:
        """Lab result must have success/status/outcome field."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_lab_result,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            lab_result = {"started_at": "2024-01-01T00:00:00Z"}
            (artifact_dir / "lab-result.json").write_text(json.dumps(lab_result))

            report = VerificationReport(passed=True)
            result = verify_lab_result(artifact_dir, True, report)

            assert result is False
            assert any("missing" in e.lower() and "success" in e.lower() for e in report.errors)

    def test_lab_result_requires_passed_when_flag_set(self) -> None:
        """Lab result must indicate success when --require-lab-passed is set."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_lab_result,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            lab_result = {"success": False, "status": "failed"}
            (artifact_dir / "lab-result.json").write_text(json.dumps(lab_result))

            report = VerificationReport(passed=True)
            result = verify_lab_result(artifact_dir, True, report)

            assert result is False
            assert any("failure" in e.lower() for e in report.errors)

    def test_lab_result_tolerates_missing_when_flag_not_set(self) -> None:
        """Lab result failure is tolerated when --require-lab-passed not set."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            VerificationReport,
            verify_lab_result,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            lab_result = {"success": False, "status": "failed"}
            (artifact_dir / "lab-result.json").write_text(json.dumps(lab_result))

            report = VerificationReport(passed=True)
            result = verify_lab_result(artifact_dir, False, report)

            assert result is True


class TestMainVerification:
    """Tests for main verification flow."""

    def test_full_verification_passes_with_valid_artifacts(self) -> None:
        """Full verification passes with complete valid artifacts."""
        from scripts.k9b_otel_demo_lab_contract_verify import (
            OtelTracesMode,
            verify_live_lab_contracts,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create valid lab result
            (artifact_dir / "lab-result.json").write_text(json.dumps({
                "success": True,
                "status": "passed",
            }))

            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            (detection_dir / "detection-evidence.json").write_text(json.dumps({
                "discovery_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "root_cause_summary": "The shipping deployment has issues",
                "shipping_reference_found": True,
                "namespace_matches": True,
            }))

            # Create valid P4c evidence
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps({
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": (
                    "The shipping deployment has nodeSelector k9b.dev/otel-lab-node=missing. "
                    "FailedScheduling event indicates pod cannot be scheduled."
                ),
                "executed_checks": ["kubectl_get_pods"],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }))

            # Create valid pass artifact
            loop_dir = diagnosis_dir / "loop-passes"
            loop_dir.mkdir(parents=True)
            (loop_dir / "pass-1.json").write_text(json.dumps({
                "loop_run_id": "run-1",
                "incident_id": "inc-123",
                "pass_index": 1,
                "case_file_hash": "abc123",
                "proposed_checks": [],
                "accepted_checks": [],
                "rejected_checks": [],
                "check_fingerprints": [],
                "new_evidence_hashes": [],
                "duplicate_check_count": 0,
                "unsafe_check_count": 0,
                "root_cause_summary": "Test",
                "confidence": "high",
                "should_continue": True,
                "stop_reason": None,
                "safety_metadata": {
                    "policy_enforced": True,
                    "mutating_checks_executed_count": 0,
                    "sensitive_reads_executed_count": 0,
                },
                "gate_summary": {"rejected_checks": []},
            }))

            report = verify_live_lab_contracts(
                artifact_dir=artifact_dir,
                scenario="unschedulable-shipping",
                require_lab_passed=True,
                otel_traces_mode=OtelTracesMode.AUTO,
            )

            assert report.passed is True
