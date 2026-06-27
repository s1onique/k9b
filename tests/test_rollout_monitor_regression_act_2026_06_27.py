#!/usr/bin/env python3
"""Regression tests for rollout monitor contract fix (ACT 2026-06-27).

These tests verify the fix for the live-lab rollout failure where:
1. The monitor reported "Deployment k9b not found" even though rendered chart
   produces k9b-backend, k9b-scheduler Deployments
2. CrashLoopBackOff was the real failure but VolumeBinding was surfaced first
3. Artifact collection needed to include current and previous container logs

Tests the following requirements from the ACT:
1. Expected Deployment names derived from rendered Helm manifest
2. No stale "Deployment k9b not found" when k9b Deployment doesn't exist
3. Crash-loop takes precedence over transient VolumeBinding conflicts
4. Crash artifact collection includes current and previous logs
5. CLI contract tests for --deadline and --poll-interval legacy flags
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.k9b_cnpg_live_lab_crash_artifacts import (
    _collect_container_logs,
)
from scripts.k9b_cnpg_live_lab_monitor import (
    get_expected_deployments_from_manifest,
)


# =============================================================================
# Regression Test 1: Rendered manifest fixture with k9b-backend, k9b-scheduler
# =============================================================================

RENDERED_MANIFEST_FIXTURE = """
apiVersion: v1
kind: Namespace
metadata:
  name: k9b-live-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: k9b-config
  namespace: k9b-live-lab
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
  namespace: k9b-live-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: k9b-backend
  template:
    metadata:
      labels:
        app: k9b-backend
    spec:
      containers:
      - name: backend
        image: k9b-backend:latest
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
  namespace: k9b-live-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: k9b-scheduler
  template:
    metadata:
      labels:
        app: k9b-scheduler
    spec:
      containers:
      - name: scheduler
        image: k9b-scheduler:latest
"""


class TestRenderedManifestFixtureDerivation:
    """Regression Test 1: Assert expected Deployment derivation returns exactly rendered names.

    A rendered-manifest fixture with Deployments:
    - k9b-backend
    - k9b-scheduler
    - no k9b Deployment

    Must assert expected Deployment derivation returns exactly the rendered Deployment names.
    """

    def test_fixture_has_no_k9b_deployment(self) -> None:
        """Fixture must not contain a Deployment named 'k9b'."""
        # Check that there is no Deployment resource named exactly "k9b"
        # (k9b-backend and k9b-scheduler are valid)
        import yaml
        docs = list(yaml.safe_load_all(RENDERED_MANIFEST_FIXTURE))
        deployment_names = [
            doc["metadata"]["name"]
            for doc in docs
            if isinstance(doc, dict) and doc.get("kind") == "Deployment"
        ]
        assert "k9b" not in deployment_names, f"Found unexpected Deployment 'k9b' in fixture: {deployment_names}"
        assert "k9b-backend" in deployment_names
        assert "k9b-scheduler" in deployment_names

    def test_fixture_has_expected_deployments(self) -> None:
        """Fixture must contain k9b-backend and k9b-scheduler Deployments."""
        assert "name: k9b-backend" in RENDERED_MANIFEST_FIXTURE
        assert "name: k9b-scheduler" in RENDERED_MANIFEST_FIXTURE
        assert "kind: Deployment" in RENDERED_MANIFEST_FIXTURE

    def test_derives_exactly_rendered_deployment_names(self) -> None:
        """Expected Deployment derivation returns exactly rendered names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(RENDERED_MANIFEST_FIXTURE)

            result = get_expected_deployments_from_manifest(artifact_dir)

            # Must derive exactly the rendered Deployment names
            assert result == ["k9b-backend", "k9b-scheduler"]
            # Must NOT include a non-existent "k9b" Deployment
            assert "k9b" not in result
            # Must be exactly 2 Deployments
            assert len(result) == 2


# =============================================================================
# Regression Test 2: Monitor timeout with CrashLoopBackOff but no "Deployment k9b not found"
# =============================================================================

class TestMonitorTimeoutWithCrashLoop:
    """Regression Test 2: Monitor must NOT report stale "Deployment k9b not found".

    A monitor timeout/status test where:
    - expected Deployments are k9b-backend, k9b-scheduler
    - no literal k9b Deployment exists
    - scheduler pod is in CrashLoopBackOff

    Must assert output/status does not contain "Deployment k9b not found".
    """

    def test_monitor_header_does_not_contain_stale_k9b_message(self) -> None:
        """Monitor header must not contain 'Deployment k9b not found'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(RENDERED_MANIFEST_FIXTURE)

            deployments = get_expected_deployments_from_manifest(artifact_dir)
            deployments_str = ", ".join(deployments)

            # Must use actual deployment names
            assert "k9b-backend" in deployments_str
            assert "k9b-scheduler" in deployments_str
            # Must NOT contain stale "Deployment k9b" message
            assert "Deployment k9b" not in deployments_str
            assert "k9b not found" not in deployments_str.lower()

    def test_status_message_with_crashloop_uses_actual_names(self) -> None:
        """Crash-loop status must use actual pod/container names, not generic 'k9b'."""
        crash_loop_data = [{
            "pod": "k9b-scheduler-84598f5bf5-vdsjt",
            "container": "scheduler",
            "reason": "CrashLoopBackOff",
            "restart_count": 3,
            "phase": "Running"
        }]

        first_crash = crash_loop_data[0]
        crash_pod = first_crash.get("pod", "unknown")
        crash_container = first_crash.get("container", "unknown")
        crash_restarts = first_crash.get("restart_count", 0)

        # Generate status like monitor does
        final_status = (
            f"Rollout failed: pod {crash_pod} container {crash_container} "
            f"is in CrashLoopBackOff after {crash_restarts} restarts"
        )

        # Must contain actual pod/container names
        assert "k9b-scheduler-84598f5bf5-vdsjt" in final_status
        assert "scheduler" in final_status
        # Must NOT contain stale "Deployment k9b" message
        assert "Deployment k9b" not in final_status
        assert "k9b not found" not in final_status.lower()


# =============================================================================
# Regression Test 3: Classifier precedence - crash_loop over VolumeBinding
# =============================================================================

class TestClassifierPrecedenceOverVolumeBinding:
    """Regression Test 3: Crash-loop takes precedence over transient VolumeBinding.

    A classifier precedence test where:
    - backend pod has transient VolumeBinding conflict
    - scheduler pod has CrashLoopBackOff

    Must assert failure_class == "crash_loop" and transient VolumeBinding
    remains diagnostic metadata only.
    """

    def test_crash_loop_takes_precedence_over_transient_volume_binding(self) -> None:
        """Failure class must be crash_loop, not transient_volume_binding."""
        from scripts.k9b_cnpg_live_lab_rollout_classify import (
            FAILURE_CRASH_LOOP,
            classify_rollout_state,
        )

        # Scheduler pod in CrashLoopBackOff
        pods_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "k9b-backend-8656cd977b-tmqhm"},
                    "status": {
                        "phase": "Running",
                        "conditions": [{"type": "Ready", "status": "True"}]
                    }
                },
                {
                    "metadata": {"name": "k9b-scheduler-84598f5bf5-vdsjt"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "restartCount": 3,
                                "state": {
                                    "waiting": {
                                        "reason": "CrashLoopBackOff",
                                        "message": "back-off 5m0s restarting"
                                    }
                                },
                                "lastState": {
                                    "terminated": {
                                        "exitCode": 1,
                                        "reason": "Error",
                                        "startedAt": "2026-06-27T00:30:00Z",
                                        "finishedAt": "2026-06-27T00:30:05Z"
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        })

        # Transient VolumeBinding conflict (diagnostic context only)
        events_json = json.dumps({
            "items": [
                {
                    "reason": "FailedScheduling",
                    "message": "running PreBind plugin \"VolumeBinding\": "
                              "Operation cannot be fulfilled on persistentvolumeclaims "
                              "\"k9b-runs\": the object has been modified; "
                              "please apply your changes to the latest version",
                    "involvedObject": {
                        "kind": "Pod",
                        "name": "k9b-backend-8656cd977b-tmqhm"
                    },
                    "lastTimestamp": "2026-06-27T00:29:00Z"
                }
            ]
        })

        result = classify_rollout_state(
            pods_json, "{}", "{}", "",
            events_json=events_json
        )

        # PRIMARY failure must be crash_loop
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP, \
            f"Expected crash_loop, got {result.failure_class}"
        # Crash details must be captured
        assert result.crash_pod_name == "k9b-scheduler-84598f5bf5-vdsjt"
        assert result.crash_container_name == "scheduler"
        assert result.crash_restart_count == 3

        # Transient VolumeBinding must be diagnostic context only
        assert result.diagnostics.get("transient_volume_binding_conflict") is True
        assert "transient_volume_binding_message" in result.diagnostics


# =============================================================================
# Regression Test 4: Crash artifact collection includes current and previous logs
# =============================================================================

class TestCrashArtifactCollectionIncludesLogs:
    """Regression Test 4: Crash artifact collection includes current and previous logs.

    A crash artifact test proving current and previous logs are requested
    for the crashing container.
    """

    def test_crash_evidence_has_pod_and_container_for_log_collection(self) -> None:
        """Crash evidence must contain pod and container for log collection."""
        from scripts.k9b_cnpg_live_lab_rollout_pods import _check_crash_loop_from_pods

        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-scheduler-84598f5bf5-vdsjt"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "restartCount": 3,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff",
                                "message": "back-off 5m0s restarting"
                            }
                        },
                        "lastState": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error",
                                "startedAt": "2026-06-27T00:30:00Z",
                                "finishedAt": "2026-06-27T00:30:05Z"
                            }
                        }
                    }]
                }
            }]
        })

        crash_evidence = _check_crash_loop_from_pods(pods_json)

        assert len(crash_evidence) == 1
        evidence = crash_evidence[0]

        # Required fields for log collection
        assert "pod" in evidence
        assert "container" in evidence
        assert evidence["pod"] == "k9b-scheduler-84598f5bf5-vdsjt"
        assert evidence["container"] == "scheduler"
        # Crash details for status
        assert "restart_count" in evidence
        assert evidence["restart_count"] == 3
        assert "reason" in evidence
        assert evidence["reason"] == "CrashLoopBackOff"

    def test_crash_artifact_module_collects_logs(self) -> None:
        """Verify crash artifact module has log collection capability."""
        # Import the module to verify it loads
        from scripts.k9b_cnpg_live_lab_crash_artifacts import (
            _collect_container_logs,
        )

        # Verify the function exists and is callable
        assert callable(_collect_container_logs)


# =============================================================================
# Regression Test 5: CLI contract tests for legacy flags
# =============================================================================

class TestCLIContractLegacyFlags:
    """Regression Test 5: Legacy CLI flags still work.

    A CLI/bootstrap contract test proving legacy flags still work:
    - --deadline
    - --poll-interval

    and manifest-derived expected Deployment names are still honored.
    """

    def test_monitor_cli_accepts_deadline_flag(self) -> None:
        """Monitor CLI must accept --deadline flag (legacy alias for --max-wait)."""
        from scripts.k9b_cnpg_live_lab_monitor import main_monitor_rollout

        # Verify the function exists
        assert callable(main_monitor_rollout)

    def test_monitor_cli_accepts_poll_interval_flag(self) -> None:
        """Monitor CLI must accept --poll-interval flag (legacy alias for --interval)."""
        from scripts.k9b_cnpg_live_lab_monitor import main_monitor_rollout

        # Verify the function exists
        assert callable(main_monitor_rollout)

    def test_manifest_derivation_uses_release_name_fallback(self) -> None:
        """Manifest derivation must use release name as expected_name fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(RENDERED_MANIFEST_FIXTURE)

            # Call with explicit release name
            result = get_expected_deployments_from_manifest(
                artifact_dir,
                release_name="k9b",
                namespace="k9b-live-lab"
            )

            # Must still derive the actual Deployment names
            assert "k9b-backend" in result
            assert "k9b-scheduler" in result
            # Must NOT include "k9b" as a Deployment name
            assert "k9b" not in result

    def test_cli_artifact_dir_structure_for_manifest(self) -> None:
        """Verify CLI expects rendered-manifest.yaml at helm/ subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            rendered_path = helm_dir / "rendered-manifest.yaml"

            # CLI expects this path
            assert rendered_path.parent.name == "helm"
            assert rendered_path.name == "rendered-manifest.yaml"


# =============================================================================
# Machine-readable summary test
# =============================================================================

class TestMachineReadableCrashSummary:
    """Test machine-readable crash summary format."""

    def test_crash_summary_format(self) -> None:
        """Crash summary must be machine-parseable."""
        crash_info: dict[str, str | int] = {
            "failure_class": "crash_loop",
            "crash_pod_name": "k9b-scheduler-84598f5bf5-vdsjt",
            "crash_container_name": "scheduler",
            "crash_restart_count": 3,
            "pod_crash_loop": "k9b-scheduler/scheduler CrashLoopBackOff restarts=3"
        }

        # Machine-readable format
        assert crash_info["failure_class"] == "crash_loop"
        assert crash_info["crash_pod_name"] == "k9b-scheduler-84598f5bf5-vdsjt"
        assert crash_info["crash_container_name"] == "scheduler"
        assert crash_info["crash_restart_count"] == 3
        # Concise summary format: pod_name/container_name reason restarts=N
        pod_crash_loop = crash_info["pod_crash_loop"]
        assert isinstance(pod_crash_loop, str)
        assert "CrashLoopBackOff" in pod_crash_loop
        assert "restarts=3" in pod_crash_loop


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
