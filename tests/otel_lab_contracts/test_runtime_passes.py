"""Tests for runtime loop-pass verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestLoopPassPathDiscovery:
    """Tests for loop-pass artifact path discovery."""

    def test_finds_artifacts_at_new_canonical_path(self) -> None:
        """Discovery finds artifacts at current canonical path: external-analysis/diagnosis-loop-passes/."""
        from scripts.otel_lab_contracts.runtime_passes import find_loop_pass_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create artifacts at new canonical path
            loop_dir = artifact_dir / "external-analysis" / "diagnosis-loop-passes"
            loop_dir.mkdir(parents=True)

            artifact = self._make_valid_pass_artifact(1)
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            artifacts, path_desc = find_loop_pass_artifacts(artifact_dir)

            assert len(artifacts) == 1
            assert "external-analysis" in path_desc
            assert "diagnosis-loop-passes" in path_desc

    def test_falls_back_to_legacy_path(self) -> None:
        """Discovery falls back to legacy path: phase4-diagnosis/p4c-k8s-multipass-diagnosis/loop-passes/."""
        from scripts.otel_lab_contracts.runtime_passes import find_loop_pass_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create artifacts at legacy path (no canonical path exists)
            loop_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            loop_dir.mkdir(parents=True)

            artifact = self._make_valid_pass_artifact(1)
            (loop_dir / "pass-1.json").write_text(json.dumps(artifact))

            artifacts, path_desc = find_loop_pass_artifacts(artifact_dir)

            assert len(artifacts) == 1
            assert "phase4-diagnosis" in path_desc
            assert "loop-passes" in path_desc

    def test_prefers_canonical_over_legacy_path(self) -> None:
        """Discovery prefers canonical path when both exist."""
        from scripts.otel_lab_contracts.runtime_passes import find_loop_pass_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create artifacts at BOTH paths
            canonical_dir = artifact_dir / "external-analysis" / "diagnosis-loop-passes"
            canonical_dir.mkdir(parents=True)
            canonical_artifact = self._make_valid_pass_artifact(1)
            (canonical_dir / "pass-1.json").write_text(json.dumps(canonical_artifact))

            legacy_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
            legacy_dir.mkdir(parents=True)
            legacy_artifact = self._make_valid_pass_artifact(2)
            (legacy_dir / "pass-2.json").write_text(json.dumps(legacy_artifact))

            artifacts, path_desc = find_loop_pass_artifacts(artifact_dir)

            # Should prefer canonical path
            assert len(artifacts) == 1
            assert "external-analysis" in path_desc

    def test_returns_empty_when_no_path_exists(self) -> None:
        """Discovery returns empty when no loop-pass path exists."""
        from scripts.otel_lab_contracts.runtime_passes import find_loop_pass_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            artifacts, path_desc = find_loop_pass_artifacts(artifact_dir)

            assert artifacts == []
            assert path_desc == "none"

    def test_loads_embedded_in_diagnosis_evidence(self) -> None:
        """Discovery loads embedded pass_artifacts from diagnosis-evidence.json."""
        from scripts.otel_lab_contracts.runtime_passes import find_loop_pass_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create embedded evidence at canonical path
            evidence_dir = artifact_dir / "external-analysis"
            evidence_dir.mkdir(parents=True)

            evidence = {
                "pass_artifacts": [
                    self._make_valid_pass_artifact(1),
                    self._make_valid_pass_artifact(2),
                ]
            }
            (evidence_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            artifacts, path_desc = find_loop_pass_artifacts(artifact_dir)

            # Should find the embedded evidence
            assert len(artifacts) == 1  # One evidence file marker
            assert "embedded" in path_desc

    @staticmethod
    def _make_valid_pass_artifact(pass_index: int) -> dict:
        """Create a valid pass artifact for testing."""
        return {
            "loop_run_id": f"run-{pass_index}",
            "incident_id": "inc-123",
            "pass_index": pass_index,
            "case_file_hash": f"hash{pass_index}",
            "proposed_checks": [],
            "accepted_checks": [],
            "rejected_checks": [],
            "check_fingerprints": [],
            "new_evidence_hashes": [],
            "duplicate_check_count": 0,
            "unsafe_check_count": 0,
            "root_cause_summary": "Test",
            "confidence": "high",
            "should_continue": pass_index < 2,
            "stop_reason": "max_passes_reached" if pass_index == 2 else None,
            "safety_metadata": {
                "policy_enforced": True,
                "mutating_checks_executed_count": 0,
                "sensitive_reads_executed_count": 0,
            },
            "gate_summary": {"rejected_checks": []},
        }


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
