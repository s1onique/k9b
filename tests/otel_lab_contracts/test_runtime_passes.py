"""Tests for runtime loop-pass verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestRuntimeLoopPassVerification:
    """Tests for runtime loop-pass artifact verification."""

    def test_runtime_pass_artifact_requires_schema_fields(self) -> None:
        """Pass artifact must have all required schema fields."""
        from scripts.otel_lab_contracts import VerificationReport, verify_runtime_loop_passes

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
        from scripts.otel_lab_contracts import VerificationReport, verify_runtime_loop_passes

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
        from scripts.otel_lab_contracts import VerificationReport, verify_runtime_loop_passes

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
        from scripts.otel_lab_contracts import VerificationReport, verify_runtime_loop_passes

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


class TestRuntimeRejectedAcceptedOverlap:
    """Tests for rejected/accepted check overlap with dict checks."""

    def test_runtime_rejects_rejected_dict_check_id_in_accepted_dict_checks(self) -> None:
        """Runtime rejects when rejected dict check id appears in accepted dict checks."""
        from scripts.otel_lab_contracts import VerificationReport, verify_runtime_loop_passes

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            # Same check appears in both rejected and accepted (as dicts)
            artifact = {
                "loop_run_id": "run-1",
                "incident_id": "inc-123",
                "pass_index": 1,
                "case_file_hash": "abc123",
                "proposed_checks": [],
                "accepted_checks": [
                    {"check_id": "kubectl_get_pods", "name": "Get Pods"},
                ],
                "rejected_checks": [
                    {"check_id": "kubectl_get_pods", "name": "Get Pods"},
                ],
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
                    "sensitive_reads_executed_count": 0,
                },
                "gate_summary": {
                    "rejected_checks": [
                        {"check_id": "kubectl_get_pods", "name": "Get Pods"},
                    ]
                },
            }
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("rejected" in e.lower() and "accepted" in e.lower() for e in report.errors)

    def test_runtime_rejects_gate_summary_rejected_check_id_in_accepted_checks(self) -> None:
        """Runtime rejects when gate_summary rejected check overlaps accepted."""
        from scripts.otel_lab_contracts import VerificationReport, verify_runtime_loop_passes

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            artifact = {
                "loop_run_id": "run-1",
                "incident_id": "inc-123",
                "pass_index": 1,
                "case_file_hash": "abc123",
                "proposed_checks": [],
                "accepted_checks": ["kubectl_get_services"],
                "rejected_checks": ["kubectl_get_nodes"],
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
                    "sensitive_reads_executed_count": 0,
                },
                # gate_summary.rejected_checks has kubectl_get_services (overlap!)
                "gate_summary": {"rejected_checks": ["kubectl_get_services"]},
            }
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("gate_summary" in e.lower() and "rejected" in e.lower() for e in report.errors)


class TestBoundedLoopPolicy:
    """Tests for bounded-loop policy verification."""

    def test_bounded_loop_defaults_are_enforced(self) -> None:
        """Default bounded-loop policy is enforced when no policy metadata."""
        from scripts.otel_lab_contracts import VerificationReport, verify_runtime_loop_passes

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            # 3 passes (exceeds default max_passes=2)
            for i in range(3):
                artifact = {
                    "loop_run_id": f"run-{i + 1}",
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
                (loop_dir / f"pass-{i + 1}.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = verify_runtime_loop_passes(artifact_dir, report)

            assert result is False
            assert any("pass count" in e.lower() for e in report.errors)
