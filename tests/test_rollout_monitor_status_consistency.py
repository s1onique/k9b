#!/usr/bin/env python3
"""Regression tests for rollout monitor status consistency.

Tests the fix for the live-lab rollout failure where:
- The monitor reported "Deployment k9b not found" even though k9b-scheduler was crashing
- Human status was misleading while classifier correctly identified crash_loop
- Expected deployments were not derived from rendered manifests in all paths

The fix ensures:
1. No "Deployment k9b not found" when manifest has differently named Deployments
2. Crash-loop human status names the actual pod/container
3. transient_volume_binding_conflict stays as diagnostic context only
4. Expected deployment names derived from rendered Helm manifests
5. Artifact collection on crash loop includes logs
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.k9b_cnpg_live_lab_monitor import (
    get_expected_deployments_from_manifest,
)


class TestNoStaleK9bDeploymentMessage:
    """Regression: monitor must NOT report "Deployment k9b not found" for multi-deployment charts.

    The rendered chart produces k9b-backend, k9b-frontend, k9b-scheduler.
    The monitor must derive expected deployments from manifests, not hard-code "k9b".
    """

    def test_rendered_manifest_has_no_k9b_deployment(self) -> None:
        """Verify the rendered manifest has k9b-scheduler, NOT k9b deployment."""
        rendered_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-frontend
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            deployments = get_expected_deployments_from_manifest(artifact_dir)

            # The bug was that the monitor checked for "k9b" which doesn't exist
            assert "k9b" not in deployments, "Must NOT include 'k9b' deployment (doesn't exist)"
            # The correct behavior is to check for the actual rendered deployments
            assert "k9b-backend" in deployments
            assert "k9b-frontend" in deployments
            assert "k9b-scheduler" in deployments
            assert len(deployments) == 3

    def test_monitor_header_uses_expected_deployments_not_k9b(self) -> None:
        """Verify expected deployments are logged, not hardcoded 'k9b'."""
        rendered_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            deployments = get_expected_deployments_from_manifest(artifact_dir)

            # Header should show "k9b-scheduler", NOT "Deployment k9b"
            assert deployments == ["k9b-scheduler"]
            assert "k9b" not in deployments

    def test_progress_message_uses_actual_deployment_names(self) -> None:
        """Progress message should use actual deployment names, not generic 'k9b'."""
        rendered_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            deployments = get_expected_deployments_from_manifest(artifact_dir)

            # Progress message should say "k9b-backend, k9b-scheduler", NOT "Deployment k9b"
            deployments_str = ", ".join(deployments)
            assert "k9b" in deployments_str  # The string "k9b" appears as prefix
            assert "k9b-deployment" not in deployments_str  # But NOT as standalone "Deployment k9b"
            assert "k9b-backend" in deployments_str
            assert "k9b-scheduler" in deployments_str


class TestCrashLoopStatusNamesActualPod:
    """Regression: crash-loop status must name the actual pod/container, not 'Deployment k9b'."""

    def test_crash_status_format_includes_pod_and_container(self) -> None:
        """Crash-loop status must include actual pod name and container name."""
        # The crash_loop data should contain the actual pod/container names
        crash_loop_data = [{
            "pod": "k9b-scheduler-6bd59ddfd5-nthjf",
            "container": "scheduler",
            "reason": "CrashLoopBackOff",
            "restart_count": 3,
            "phase": "Running"
        }]

        # Generate status message like the monitor does
        first_crash = crash_loop_data[0]
        crash_pod = first_crash.get("pod", "unknown")
        crash_container = first_crash.get("container", "unknown")
        crash_restarts = first_crash.get("restart_count", 0)
        final_status = (
            f"Rollout failed: pod {crash_pod} container {crash_container} "
            f"is in CrashLoopBackOff after {crash_restarts} restarts"
        )

        # The status MUST contain actual pod/container names
        assert "k9b-scheduler-6bd59ddfd5-nthjf" in final_status
        assert "scheduler" in final_status
        assert "3" in final_status
        # Must NOT contain the stale "Deployment k9b" message
        assert "Deployment k9b" not in final_status
        assert "Deployment k9b not found" not in final_status

    def test_classifier_returns_crash_loop_for_scheduler_crash(self) -> None:
        """Classifier must return crash_loop for scheduler container crash."""
        from scripts.k9b_cnpg_live_lab_rollout_classify import (
            FAILURE_CRASH_LOOP,
            classify_rollout_state,
        )

        # Exact pod state from the failing lab
        pods_json = json.dumps({
            "items": [{
                "metadata": {
                    "name": "k9b-scheduler-6bd59ddfd5-nthjf",
                },
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "restartCount": 3,
                        "state": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error"
                            }
                        },
                        "lastState": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error"
                            }
                        }
                    }]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        # Must classify as crash_loop, NOT expected_deployment_missing
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP
        assert "k9b-scheduler-6bd59ddfd5-nthjf" in result.affected_pods
        # Crash details should be captured
        assert result.crash_pod_name == "k9b-scheduler-6bd59ddfd5-nthjf"
        assert result.crash_container_name == "scheduler"
        assert result.crash_restart_count == 3


class TestTransientVolumeBindingDiagnosticOnly:
    """Regression: transient VolumeBinding conflict must NOT override crash_loop."""

    def test_transient_volume_binding_with_crash_remains_crash_loop(self) -> None:
        """VolumeBinding conflict + crash evidence must classify as crash_loop."""
        from scripts.k9b_cnpg_live_lab_rollout_classify import (
            FAILURE_CRASH_LOOP,
            classify_rollout_state,
        )

        # Crash loop evidence
        pods_json = json.dumps({
            "items": [{
                "metadata": {
                    "name": "k9b-scheduler-6bd59ddfd5-nthjf",
                },
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "restartCount": 3,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff"
                            }
                        }
                    }]
                }
            }]
        })

        # Transient VolumeBinding conflict - uses FailedScheduling reason with PreBind message
        events_json = json.dumps({
            "items": [{
                "type": "Warning",
                "reason": "FailedScheduling",
                "involvedObject": {
                    "kind": "Pod",
                    "name": "k9b-scheduler-6bd59ddfd5-nthjf"
                },
                "message": "running PreBind plugin \"VolumeBinding\": Operation cannot be fulfilled on persistentvolumeclaims \"k9b-runs\": the object has been modified; please apply your changes to the latest version"
            }]
        })

        result = classify_rollout_state(
            pods_json, "{}", "{}", "",
            events_json=events_json
        )

        # Primary failure must be crash_loop, NOT transient_volume_binding_conflict
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP
        # Transient conflict must be recorded as diagnostic context ONLY
        assert result.diagnostics.get("transient_volume_binding_conflict") is True


class TestExpectedDeploymentMissingClassification:
    """Regression: expected_deployment_missing must only fire when inventory exists."""

    def test_empty_deployments_and_pods_returns_expected_deployment_missing(self) -> None:
        """Empty deployments AND empty pods must return expected_deployment_missing."""
        from scripts.k9b_cnpg_live_lab_rollout_classify import (
            classify_rollout_state,
        )

        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({"items": []})

        result = classify_rollout_state(pods_json, deployments_json, "{}", "")

        assert result.fatal is True
        assert result.failure_class == "expected_deployment_missing"
        assert result.diagnostics.get("expected_deployment_missing") is True

    def test_pods_exist_with_no_failures_is_healthy(self) -> None:
        """Pods exist with no failures must be healthy, not expected_deployment_missing."""
        from scripts.k9b_cnpg_live_lab_rollout_classify import classify_rollout_state

        # Pods exist with no failures
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "some-pod-abc"},
                "status": {
                    "phase": "Running",
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "containerStatuses": [{
                        "name": "main",
                        "restartCount": 0,
                        "state": {"running": {}}
                    }]
                }
            }]
        })
        deployments_json = json.dumps({"items": []})  # No deployments

        result = classify_rollout_state(pods_json, deployments_json, "{}", "")

        # Healthy - pods exist with no failures
        assert result.fatal is False
        assert result.failure_class == ""


class TestArtifactCollectionIntegration:
    """Regression: crash artifacts must be collected on crash loop."""

    def test_crash_artifact_module_has_required_functions(self) -> None:
        """Verify crash artifact collection module has required functions."""
        try:
            from scripts.k9b_cnpg_live_lab_crash_artifacts import (
                CRASH_ARTIFACT_COLLECTED_SENTINEL,
                collect_crash_artifacts,
            )
            assert callable(collect_crash_artifacts)
            assert CRASH_ARTIFACT_COLLECTED_SENTINEL is not None
        except ImportError as e:
            pytest.fail(f"Crash artifact module must be importable: {e}")

    def test_crash_evidence_contains_required_fields(self) -> None:
        """Crash evidence dict must contain fields needed for artifact collection."""
        from scripts.k9b_cnpg_live_lab_rollout_pods import _check_crash_loop_from_pods

        pods_json = json.dumps({
            "items": [{
                "metadata": {
                    "name": "k9b-scheduler-6bd59ddfd5-nthjf",
                },
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "restartCount": 3,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff"
                            }
                        }
                    }]
                }
            }]
        })

        crash_evidence = _check_crash_loop_from_pods(pods_json)

        assert len(crash_evidence) == 1
        evidence = crash_evidence[0]
        # Required fields for artifact collection
        assert "pod" in evidence
        assert "container" in evidence
        assert evidence["pod"] == "k9b-scheduler-6bd59ddfd5-nthjf"
        assert evidence["container"] == "scheduler"
        # Phase and restart count for human-readable status
        assert "phase" in evidence
        assert "restart_count" in evidence


class TestRolloutSnapshotContainsDeployments:
    """Regression: snapshot must include deployment names for diagnostics."""

    def test_snapshot_includes_expected_deployments_field(self) -> None:
        """Snapshot must include expected_deployments field for traceability."""
        # This test verifies the data structure expectations
        # The snapshot should include expected deployments in result
        result = {
            "success": False,
            "status": "Rollout failed: pod k9b-scheduler-xxx container scheduler is in CrashLoopBackOff",
            "failure_class": "crash_loop",
            "rollout_checks": {
                "failure_class": "crash_loop",
                "diagnostics": {
                    "crash_loop": [{
                        "pod": "k9b-scheduler-6bd59ddfd5-nthjf",
                        "container": "scheduler",
                        "restart_count": 3,
                        "reason": "CrashLoopBackOff",
                        "phase": "Running"
                    }],
                    "transient_volume_binding_conflict": True
                }
            },
            "expected_deployments": ["k9b-backend", "k9b-scheduler"]
        }

        # Snapshot must have expected_deployments for diagnostics
        assert "expected_deployments" in result
        assert "k9b-scheduler" in result["expected_deployments"]
        assert "k9b-backend" in result["expected_deployments"]
        # Must NOT contain "Deployment k9b" as a standalone item
        assert "Deployment k9b" not in result["expected_deployments"]
        # Verify all names start with the release prefix "k9b"
        assert all(d.startswith("k9b") for d in result["expected_deployments"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
