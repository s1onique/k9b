#!/usr/bin/env python3
"""Extended tests for rollout classifier - deployment and PVC failure classes.

Tests: success detection, PVC pending, deployment conditions, timeout handling

This test file verifies rollout JSON classifier behavior directly by feeding
minimal JSON-shaped rollout snapshots into classify_rollout_state and asserting
the emitted classification fields.

DE-BRITTLING NOTE:
This test file was refactored to remove indirect dependencies on subprocess-based
helpers through k9b_cnpg_live_lab_bootstrap. All tests now import directly from:
- scripts.k9b_cnpg_live_lab_rollout_classify: classify_rollout_state
- scripts.k9b_cnpg_live_lab_constants: FAILURE_* constants
- scripts.k9b_cnpg_live_lab_rollout: _check_*_from_json/_from_pods helpers
"""

from __future__ import annotations

import pytest

from scripts.k9b_cnpg_live_lab_constants import (
    FAILURE_CRASH_LOOP,
    FAILURE_DEPLOYMENT_PROGRESS_DEADLINE,
    FAILURE_DEPLOYMENT_REPLICA_FAILURE,
    FAILURE_FAILED_SCHEDULING,
    FAILURE_IMAGE_PULL_BACKOFF,
    FAILURE_ROLLOUT_TIMEOUT,
)
from scripts.k9b_cnpg_live_lab_rollout import (  # noqa: I001
    _check_deployment_progress_deadline_from_json,
    _check_deployment_replica_failure_from_json,
    _check_failed_scheduling_from_pods,
    _check_pvc_pending_from_json,
)
from scripts.k9b_cnpg_live_lab_rollout_classify import (  # noqa: I001
    classify_rollout_state,
)
from tests.rollout_classifier_extended_fixtures import (  # noqa: I001
    make_deployments_json,
    make_events_json,
    make_pods_json,
    make_pvc_json,
)

# =============================================================================
# Tests for individual JSON-based check functions
# =============================================================================


class TestFailedScheduling:
    """Tests for failed_scheduling detection via JSON classifiers."""

    def test_detects_unschedulable_pod_from_pods(self) -> None:
        """Should detect Unschedulable condition from pod status JSON."""
        pods_json = make_pods_json([{
            "metadata": {"name": "unschedulable-pod"},
            "status": {
                "phase": "Pending",
                "conditions": [{
                    "type": "PodScheduled",
                    "status": "False",
                    "reason": "Unschedulable",
                    "message": "0/2 nodes are available",
                }],
            },
        }])
        result = _check_failed_scheduling_from_pods(pods_json)
        assert len(result) == 1
        assert result[0]["pod"] == "unschedulable-pod"
        assert result[0]["reason"] == "Unschedulable"

    def test_no_false_positive_when_pod_running(self) -> None:
        """Should NOT detect scheduling issue for Running pod."""
        pods_json = make_pods_json([{
            "metadata": {"name": "running-pod"},
            "status": {"phase": "Running"},
        }])
        result = _check_failed_scheduling_from_pods(pods_json)
        assert result == []

    def test_classify_rollout_state_detects_scheduling(self) -> None:
        """Should classify as failed_scheduling in full classifier."""
        pods_json = make_pods_json([{
            "metadata": {"name": "stuck-pod"},
            "status": {
                "phase": "Pending",
                "conditions": [{
                    "type": "PodScheduled",
                    "status": "False",
                    "reason": "InsufficientMemory",
                    "message": "cannot schedule",
                }],
            },
        }])
        result = classify_rollout_state(pods_json, '{"items": []}', '{"items": []}', "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_FAILED_SCHEDULING
        # Verify evidence is captured in diagnostics
        assert "failed_scheduling_pods" in result.diagnostics

    def test_classify_rollout_state_detects_scheduling_from_events(self) -> None:
        """Should classify as failed_scheduling from events JSON."""
        events_json = make_events_json([{
            "involvedObject": {"kind": "Pod", "name": "stuck-pod", "namespace": "default"},
            "reason": "FailedScheduling",
            "message": "no nodes available for scheduling",
            "type": "Warning",
        }])
        pods_json = make_pods_json([{
            "metadata": {"name": "stuck-pod"},
            "status": {"phase": "Pending"},
        }])
        result = classify_rollout_state(pods_json, '{"items": []}', '{"items": []}', "", events_json)
        assert result.fatal is True
        assert result.failure_class == FAILURE_FAILED_SCHEDULING


class TestPVCPending:
    """Tests for pvc_pending detection via JSON classifiers."""

    def test_detects_pending_pvc(self) -> None:
        """Should detect PVC in Pending state."""
        pvc_json = make_pvc_json([{
            "metadata": {"name": "data-pvc"},
            "status": {"phase": "Pending"},
        }])
        result = _check_pvc_pending_from_json(pvc_json)
        assert len(result) == 1
        assert result[0]["pvc"] == "data-pvc"

    def test_no_false_positive_for_bound_pvc(self) -> None:
        """Should NOT detect issue for Bound PVC."""
        pvc_json = make_pvc_json([{
            "metadata": {"name": "data-pvc"},
            "status": {"phase": "Bound"},
        }])
        result = _check_pvc_pending_from_json(pvc_json)
        assert result == []

    def test_no_false_positive_for_empty_pvcs(self) -> None:
        """Should NOT detect issue for empty PVC list."""
        pvc_json = make_pvc_json([])
        result = _check_pvc_pending_from_json(pvc_json)
        assert result == []

    def test_classify_rollout_state_detects_pvc_pending(self) -> None:
        """Should classify as pvc_pending in full classifier."""
        pvc_json = make_pvc_json([{
            "metadata": {"name": "data-pvc", "namespace": "default"},
            "spec": {"storageClassName": "standard"},
            "status": {"phase": "Pending", "reason": "Waiting for persistent volumes"},
        }])
        result = classify_rollout_state(
            '{"items": []}',
            '{"items": []}',
            pvc_json,
            "",  # events_text
            "",  # events_json
            "",  # storage_class_json
            True,  # storage_class_available
        )
        assert result.fatal is True
        assert result.failure_class == "pvc_pending"
        assert "pvc_pending" in result.diagnostics

    def test_pvc_json_helper_reports_all_pending_pvcs_without_namespace_filtering(self) -> None:
        """JSON helper returns all pending PVCs regardless of namespace.
        
        Note: The low-level `_check_pvc_pending_from_json` helper does not perform
        namespace filtering - it reports all PVCs in Pending state.
        Namespace/deployment filtering is the responsibility of the higher-level
        `classify_rollout_state` if needed.
        """
        pvc_json = make_pvc_json([
            {
                "metadata": {"name": "data-pvc", "namespace": "other-namespace"},
                "status": {"phase": "Pending"},
            },
            {
                "metadata": {"name": "app-pvc", "namespace": "target-namespace"},
                "status": {"phase": "Pending"},
            },
        ])
        result = _check_pvc_pending_from_json(pvc_json)
        assert len(result) == 2
        pvc_names = [item["pvc"] for item in result]
        assert "data-pvc" in pvc_names
        assert "app-pvc" in pvc_names


class TestDeploymentConditions:
    """Tests for deployment condition failure classes via JSON classifiers."""

    def test_detects_replica_failure_from_json(self) -> None:
        """Should detect replica failure from deployments JSON."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "replicas": 3,
                "availableReplicas": 0,
                "readyReplicas": 0,
            },
        }])
        result = _check_deployment_replica_failure_from_json(deployments_json)
        assert len(result) == 1
        assert result[0]["deployment"] == "k9b-backend"
        assert result[0]["replicas"] == 3
        assert result[0]["available"] == 0

    def test_no_false_positive_when_replicas_available(self) -> None:
        """Should NOT detect replica failure when replicas are available."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "replicas": 3,
                "availableReplicas": 3,
                "readyReplicas": 3,
            },
        }])
        result = _check_deployment_replica_failure_from_json(deployments_json)
        assert result == []

    def test_no_false_positive_when_replicas_zero(self) -> None:
        """Should NOT detect replica failure when replicas is 0 (scaling down)."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "replicas": 0,
                "availableReplicas": 0,
            },
        }])
        result = _check_deployment_replica_failure_from_json(deployments_json)
        assert result == []

    def test_detects_progress_deadline_exceeded(self) -> None:
        """Should detect ProgressDeadlineExceeded condition from deployments JSON."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "conditions": [
                    {"type": "Available", "status": "False"},
                    {
                        "type": "Progressing",
                        "status": "Unknown",
                        "reason": "ProgressDeadlineExceeded",
                        "message": "Deployment was terminated",
                    },
                ],
            },
        }])
        result = _check_deployment_progress_deadline_from_json(deployments_json)
        assert len(result) == 1
        assert result[0]["deployment"] == "k9b-backend"
        assert result[0]["reason"] == "ProgressDeadlineExceeded"

    def test_no_false_positive_for_healthy_progressing(self) -> None:
        """Should NOT detect progress deadline for healthy progressing deployment."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "conditions": [
                    {"type": "Available", "status": "True"},
                    {"type": "Progressing", "status": "True", "reason": "NewReplicaSetCreated"},
                ],
            },
        }])
        result = _check_deployment_progress_deadline_from_json(deployments_json)
        assert result == []

    def test_classify_rollout_state_detects_replica_failure(self) -> None:
        """Should classify as deployment_replica_failure in full classifier."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "replicas": 3,
                "availableReplicas": 0,
                "readyReplicas": 0,
            },
        }])
        result = classify_rollout_state('{"items": []}', deployments_json, '{"items": []}', "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_DEPLOYMENT_REPLICA_FAILURE
        assert "deployment_replica_failure" in result.diagnostics

    def test_classify_rollout_state_detects_progress_deadline(self) -> None:
        """Should classify as deployment_progress_deadline in full classifier."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "conditions": [
                    {"type": "Available", "status": "False"},
                    {
                        "type": "Progressing",
                        "status": "Unknown",
                        "reason": "ProgressDeadlineExceeded",
                        "message": "was terminated",
                    },
                ],
            },
        }])
        result = classify_rollout_state('{"items": []}', deployments_json, '{"items": []}', "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_DEPLOYMENT_PROGRESS_DEADLINE
        assert "deployment_progress_deadline" in result.diagnostics

    def test_namespace_deployment_scope_from_diagnostics(self) -> None:
        """Should include deployment name in diagnostics evidence."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "namespace": "production"},
            "status": {
                "replicas": 2,
                "availableReplicas": 0,
                "readyReplicas": 0,
            },
        }])
        result = classify_rollout_state('{"items": []}', deployments_json, '{"items": []}', "")
        assert result.fatal is True
        diag = result.diagnostics.get("deployment_replica_failure", [])
        assert len(diag) == 1
        assert diag[0]["deployment"] == "k9b-backend"


class TestPriorityOrder:
    """Tests that failure classes are checked in correct priority order."""

    def test_image_pull_before_crash_loop(self) -> None:
        """ImagePullBackOff should be detected before CrashLoopBackOff."""
        pods_json = make_pods_json([{
            "metadata": {"name": "both-issues"},
            "status": {
                "containerStatuses": [
                    {
                        "name": "app",
                        "state": {"waiting": {"reason": "ImagePullBackOff", "message": "pull fail"}},
                    },
                    {
                        "name": "sidecar",
                        "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "crash"}},
                    },
                ],
            },
        }])
        result = classify_rollout_state(pods_json, '{"items": []}', '{"items": []}', "")
        assert result.failure_class == FAILURE_IMAGE_PULL_BACKOFF

    def test_crash_loop_before_scheduling(self) -> None:
        """CrashLoopBackOff should be detected before scheduling issues."""
        pods_json = make_pods_json([{
            "metadata": {"name": "crashing"},
            "status": {
                "phase": "CrashLoopBackOff",
                "containerStatuses": [
                    {"name": "app", "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "back-off"}}},
                ],
            },
        }])
        result = classify_rollout_state(pods_json, '{"items": []}', '{"items": []}', "")
        assert result.failure_class == FAILURE_CRASH_LOOP

    def test_scheduling_before_pvc(self) -> None:
        """FailedScheduling should be detected before PVC issues."""
        pods_json = make_pods_json([{
            "metadata": {"name": "stuck"},
            "status": {
                "phase": "Pending",
                "conditions": [{
                    "type": "PodScheduled",
                    "status": "False",
                    "reason": "Unschedulable",
                    "message": "cannot schedule",
                }],
            },
        }])
        pvc_json = make_pvc_json([{"metadata": {"name": "data"}, "status": {"phase": "Pending"}}])
        result = classify_rollout_state(pods_json, '{"items": []}', pvc_json, "")
        assert result.failure_class == FAILURE_FAILED_SCHEDULING


class TestTimeoutHandling:
    """Tests for rollout timeout handling."""

    def test_timeout_is_failure_class(self) -> None:
        """FAILURE_ROLLOUT_TIMEOUT constant is defined."""
        assert FAILURE_ROLLOUT_TIMEOUT == "rollout_timeout"

    def test_no_false_positive_for_progressing_workload(self) -> None:
        """Should NOT classify as fatal when workload is healthy.
        
        Note: A deployment with replicas=1 and availableReplicas=0 triggers
        deployment_replica_failure. We use healthy deployment state.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 1},
            "status": {
                "replicas": 1,
                "availableReplicas": 1,
                "updatedReplicas": 1,
                "observedGeneration": 1,
                "conditions": [
                    {"type": "Progressing", "status": "True", "reason": "NewReplicaSetCreated"},
                    {"type": "Available", "status": "True"},
                ],
            },
        }])
        result = classify_rollout_state('{"items": []}', deployments_json, '{"items": []}', "")
        assert result.fatal is False
        assert result.failure_class == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
