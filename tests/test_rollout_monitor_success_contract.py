#!/usr/bin/env python3
"""Tests for rollout monitor success/fatal contract.

These tests verify that the rollout monitor correctly handles the contract:
- if success=true, then failure_class must be empty/null/absent
- if success=true, then rollout_checks.fatal must be false/null/absent
- stale failure diagnostics must not be reported as current fatal state
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestRolloutMonitorSuccessContract:
    """Tests for rollout monitor success/fatal contract."""

    def test_success_clears_stale_failure_class(self) -> None:
        """Success=True should have empty failure_class even if diagnostics had failures."""
        from scripts.k9b_cnpg_live_lab_monitor import _classify_and_write_results

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Call with success=True but stale diagnostics from previous failures
            _classify_and_write_results(
                artifact_dir=artifact_dir,
                success=True,
                status="Rollout successful",
                failure_class="failed_scheduling",  # Stale failure from transient state
                diagnostics={"failed_scheduling_pods": []},  # Stale diagnostics
                crash_artifacts_collected=False,
                expected_deployments=["k9b-backend", "k9b-scheduler"],
                elapsed=45,
                deployments_str="k9b-backend, k9b-scheduler",
            )

            # Read result
            result = json.loads((artifact_dir / "rollout-result.json").read_text())

            # Contract: success=true must have empty/null failure_class
            assert result["success"] is True
            assert result["failure_class"] == ""
            assert result["rollout_checks"]["failure_class"] == ""

    def test_success_clears_stale_diagnostics(self) -> None:
        """Success=True should have empty diagnostics even if failure diagnostics were provided."""
        from scripts.k9b_cnpg_live_lab_monitor import _classify_and_write_results

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Call with success=True but stale diagnostics
            _classify_and_write_results(
                artifact_dir=artifact_dir,
                success=True,
                status="Rollout successful",
                failure_class="failed_scheduling",
                diagnostics={"failed_scheduling_pods": [{"pod": "test-pod", "reason": "FailedScheduling"}]},
                crash_artifacts_collected=False,
                expected_deployments=["k9b-backend"],
                elapsed=30,
                deployments_str="k9b-backend",
            )

            # Read result
            result = json.loads((artifact_dir / "rollout-result.json").read_text())

            # Contract: success=true must have empty/null diagnostics
            assert result["success"] is True
            assert result["rollout_checks"]["diagnostics"] == {}

    def test_failure_preserves_failure_class(self) -> None:
        """Failure=True should preserve failure_class."""
        from scripts.k9b_cnpg_live_lab_monitor import _classify_and_write_results

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Call with success=False (actual failure)
            _classify_and_write_results(
                artifact_dir=artifact_dir,
                success=False,
                status="Rollout failed",
                failure_class="crash_loop",
                diagnostics={"crash_loop": [{"pod": "test-pod", "container": "main", "restart_count": 5}]},
                crash_artifacts_collected=True,
                expected_deployments=["k9b-backend"],
                elapsed=60,
                deployments_str="k9b-backend",
            )

            # Read result
            result = json.loads((artifact_dir / "rollout-result.json").read_text())

            # Contract: failure=True must preserve failure_class
            assert result["success"] is False
            assert result["failure_class"] == "crash_loop"
            assert result["rollout_checks"]["failure_class"] == "crash_loop"
            assert "crash_loop" in result["rollout_checks"]["diagnostics"]

    def test_crash_loop_failure_uses_human_readable_status(self) -> None:
        """Crash loop failure should use human-readable status."""
        from scripts.k9b_cnpg_live_lab_monitor import _classify_and_write_results

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            _classify_and_write_results(
                artifact_dir=artifact_dir,
                success=False,
                status="Rollout failed",
                failure_class="crash_loop",
                diagnostics={
                    "crash_loop": [
                        {"pod": "test-pod", "container": "main", "restart_count": 5}
                    ]
                },
                crash_artifacts_collected=True,
                expected_deployments=["k9b-backend"],
                elapsed=60,
                deployments_str="k9b-backend",
            )

            # Read result
            result = json.loads((artifact_dir / "rollout-result.json").read_text())

            # Should have human-readable status
            assert "test-pod" in result["status"]
            assert "main" in result["status"]
            assert "CrashLoopBackOff" in result["status"] or "5 restarts" in result["status"]

    def test_expected_deployment_missing_failure(self) -> None:
        """Expected deployment missing should have appropriate status."""
        from scripts.k9b_cnpg_live_lab_monitor import _classify_and_write_results

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            _classify_and_write_results(
                artifact_dir=artifact_dir,
                success=False,
                status="Rollout timed out",
                failure_class="expected_deployment_missing",
                diagnostics={"expected_deployment_missing": True},
                crash_artifacts_collected=False,
                expected_deployments=["k9b-backend", "k9b-scheduler"],
                elapsed=90,
                deployments_str="k9b-backend, k9b-scheduler",
            )

            # Read result
            result = json.loads((artifact_dir / "rollout-result.json").read_text())

            # Should preserve the failure class
            assert result["success"] is False
            assert result["failure_class"] == "expected_deployment_missing"
            assert "not found" in result["status"] or "deployment" in result["status"]

    def test_bounded_summary_excludes_failure_on_success(self) -> None:
        """Bounded summary should not show failure_class when success=True."""
        from scripts.k9b_cnpg_live_lab_monitor import _classify_and_write_results

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            _classify_and_write_results(
                artifact_dir=artifact_dir,
                success=True,
                status="Rollout successful",
                failure_class="failed_scheduling",  # Stale
                diagnostics={},
                crash_artifacts_collected=False,
                expected_deployments=["k9b-backend"],
                elapsed=30,
                deployments_str="k9b-backend",
            )

            # Read bounded summary
            bounded = (artifact_dir / "bounded-summary.txt").read_text()

            # Should not mention stale failure_class
            assert "**Failure class**" not in bounded
            assert "failed_scheduling" not in bounded
            assert "**Success**: True" in bounded

    def test_bounded_summary_includes_failure_on_failure(self) -> None:
        """Bounded summary should show failure_class when success=False."""
        from scripts.k9b_cnpg_live_lab_monitor import _classify_and_write_results

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            _classify_and_write_results(
                artifact_dir=artifact_dir,
                success=False,
                status="Rollout failed",
                failure_class="crash_loop",
                diagnostics={"crash_loop": []},
                crash_artifacts_collected=False,
                expected_deployments=["k9b-backend"],
                elapsed=60,
                deployments_str="k9b-backend",
            )

            # Read bounded summary
            bounded = (artifact_dir / "bounded-summary.txt").read_text()

            # Should mention failure_class
            assert "**Failure class**" in bounded
            assert "crash_loop" in bounded
            assert "**Success**: False" in bounded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
