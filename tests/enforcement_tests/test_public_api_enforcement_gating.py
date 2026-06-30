"""Tests for max_checks_per_pass overflow enforcement."""
from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import DiagnosisLoopPolicy

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_read_only_check_runner import ReadOnlyCheckHandler


@pytest.fixture
def sample_policy() -> DiagnosisLoopPolicy:
    """Default policy for testing."""
    return DiagnosisLoopPolicy.live_lab_default()


@pytest.fixture
def sample_case_file() -> dict[str, Any]:
    """Sample case file for testing."""
    return {
        "incident": {
            "incident_id": "test-incident-123",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "severity": "warning",
        },
        "events": [],
        "pods": [],
    }


class TestMaxChecksPerPassEnforcement:
    """Tests for max_checks_per_pass overflow enforcement."""

    def test_max_checks_per_pass_overflow_rejected(
        self,
        sample_case_file: dict[str, Any],
    ) -> None:
        """When accepted checks exceed max_checks_per_pass, overflow should be explicitly rejected."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        policy = DiagnosisLoopPolicy(max_checks_per_pass=1, max_passes=5, max_total_checks=10)
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                    {"check_id": "check_2", "title": "Check 2"},
                    {"check_id": "check_3", "title": "Check 3"},
                ]
            }
        }
        
        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
            "check_2": lambda c, now=None: {"check_id": "check_2", "status": "completed"},
            "check_3": lambda c, now=None: {"check_id": "check_3", "status": "completed"},
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
        
        pass_artifact = result.get("pass_artifact", {})
        gate_summary = pass_artifact.get("gate_summary", {})
        
        assert gate_summary.get("accepted") == 1, f"Expected 1 accepted, got {gate_summary.get('accepted')}"
        
        rejected_checks = gate_summary.get("rejected_checks", [])
        overflow_rejections = [r for r in rejected_checks if r.get("rejection_reason") == "max_checks_per_pass_exceeded"]
        assert len(overflow_rejections) >= 2, f"Expected 2 overflow rejections, got {len(overflow_rejections)}: {overflow_rejections}"

    def test_accepted_checks_and_fingerprints_lengths_match(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Accepted checks and fingerprints should always have matching lengths."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                    {"check_id": "check_2", "title": "Check 2"},
                ]
            }
        }
        
        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
            "check_2": lambda c, now=None: {"check_id": "check_2", "status": "completed"},
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=sample_policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
        
        pass_artifact = result.get("pass_artifact", {})
        accepted_checks = pass_artifact.get("accepted_checks", [])
        check_fingerprints = pass_artifact.get("check_fingerprints", [])
        
        assert len(accepted_checks) == len(check_fingerprints), (
            f"Length mismatch: accepted_checks={len(accepted_checks)}, check_fingerprints={len(check_fingerprints)}"
        )
        
        all_seen = set(pass_artifact.get("all_seen_fingerprints", []))
        assert set(check_fingerprints).issubset(all_seen), "check_fingerprints should be subset of all_seen_fingerprints"

    def test_max_checks_per_pass_overflow_not_in_accepted_fingerprints(
        self,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Overflow checks from max_checks_per_pass should NOT appear in accepted fingerprints."""
        from k8s_diag_agent.collect.runtime import run_policy_enforced_loop_pass
        
        policy = DiagnosisLoopPolicy(max_checks_per_pass=1)
        
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                    {"check_id": "check_2", "title": "Check 2"},
                ]
            }
        }
        
        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
            "check_2": lambda c, now=None: {"check_id": "check_2", "status": "completed"},
        }
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )
        
        pass_artifact = result.get("pass_artifact", {})
        accepted_checks = pass_artifact.get("accepted_checks", [])
        check_fingerprints = pass_artifact.get("check_fingerprints", [])
        all_seen = set(pass_artifact.get("all_seen_fingerprints", []))
        
        assert set(check_fingerprints).issubset(all_seen), (
            f"Accepted fingerprints {check_fingerprints} should be subset of all_seen {all_seen}"
        )
        
        assert len(accepted_checks) == len(check_fingerprints), (
            f"Length mismatch: accepted_checks={len(accepted_checks)}, check_fingerprints={len(check_fingerprints)}"
        )
