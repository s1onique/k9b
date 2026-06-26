#!/usr/bin/env python3
"""Extended tests for rollout classifier - deployment and PVC failure classes.

Tests: success detection, PVC pending, deployment conditions, timeout handling
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import importlib

import scripts.k9b_cnpg_live_lab_bootstrap as bootstrap  # noqa: E402

importlib.reload(bootstrap)

from scripts.k9b_cnpg_live_lab_bootstrap import (  # noqa: E402
    FAILURE_CRASH_LOOP,
    FAILURE_DEPLOYMENT_PROGRESS_DEADLINE,
    FAILURE_DEPLOYMENT_REPLICA_FAILURE,
    FAILURE_FAILED_SCHEDULING,
    FAILURE_IMAGE_PULL_BACKOFF,
    FAILURE_ROLLOUT_TIMEOUT,
    FAILURE_SNAPSHOT_COLLECTION_FAILED,
    _check_deployment_progress_deadline,
    _check_deployment_replica_failure,
    _check_failed_scheduling,
    _check_pvc_pending,
    _check_rollout_success,
    classify_rollout_state,
)


class TestSuccessDetection:
    """Tests for healthy rollout success detection."""

    def test_detects_success_when_all_healthy(self) -> None:
        """Should detect success when all expected workloads are healthy."""
        pods_json = json.dumps({
            "items": [
                {"metadata": {"name": "k9b-backend-abc123",
                              "ownerReferences": [{"kind": "ReplicaSet",
                                                  "name": "k9b-backend-abc12345"}]},
                 "status": {"phase": "Running",
                           "conditions": [{"type": "Ready", "status": "True"}]}},
                {"metadata": {"name": "k9b-frontend-def456",
                              "ownerReferences": [{"kind": "ReplicaSet",
                                                  "name": "k9b-frontend-def67890"}]},
                 "status": {"phase": "Running",
                           "conditions": [{"type": "Ready", "status": "True"}]}},
                {"metadata": {"name": "k9b-scheduler-ghi789",
                              "ownerReferences": [{"kind": "ReplicaSet",
                                                  "name": "k9b-scheduler-ghi78901"}]},
                 "status": {"phase": "Running",
                           "conditions": [{"type": "Ready", "status": "True"}]}}
            ]
        })
        deployments_json = json.dumps({
            "items": [
                {"metadata": {"name": "k9b-backend", "generation": 1},
                 "spec": {"replicas": 1},
                 "status": {"replicas": 1, "availableReplicas": 1,
                           "updatedReplicas": 1, "observedGeneration": 1,
                           "conditions": [{"type": "Available", "status": "True"}]}},
                {"metadata": {"name": "k9b-frontend", "generation": 1},
                 "spec": {"replicas": 1},
                 "status": {"replicas": 1, "availableReplicas": 1,
                           "updatedReplicas": 1, "observedGeneration": 1,
                           "conditions": [{"type": "Available", "status": "True"}]}},
                {"metadata": {"name": "k9b-scheduler", "generation": 1},
                 "spec": {"replicas": 1},
                 "status": {"replicas": 1, "availableReplicas": 1,
                           "updatedReplicas": 1, "observedGeneration": 1,
                           "conditions": [{"type": "Available", "status": "True"}]}}
            ]
        })
        assert _check_rollout_success(pods_json, deployments_json, '{"items": []}') is True

    def test_no_success_when_pods_not_ready(self) -> None:
        """Should NOT detect success when pods are not Ready."""
        pods_json = json.dumps({
            "items": [{"metadata": {"name": "not-ready-pod"},
                       "status": {"phase": "Running",
                                "conditions": [{"type": "Ready", "status": "False"}]}}]
        })
        deployments_json = json.dumps({
            "items": [{"metadata": {"name": "k9b-backend", "generation": 1},
                       "spec": {"replicas": 1},
                       "status": {"replicas": 1, "availableReplicas": 0,
                                 "updatedReplicas": 0, "observedGeneration": 1,
                                 "conditions": [{"type": "Available", "status": "False"}]}}]
        })
        assert _check_rollout_success(pods_json, deployments_json, '{"items": []}') is False

    def test_no_success_when_deployment_not_rolled_out(self) -> None:
        """Should NOT detect success when deployment not fully rolled out."""
        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({
            "items": [{"metadata": {"name": "k9b-backend", "generation": 2},
                       "spec": {"replicas": 2},
                       "status": {"replicas": 2, "availableReplicas": 1,
                                 "updatedReplicas": 2, "observedGeneration": 1,
                                 "conditions": []}}]
        })
        assert _check_rollout_success(pods_json, deployments_json, '{"items": []}') is False

    def test_no_success_when_pvc_not_bound(self) -> None:
        """Should NOT detect success when PVC is not Bound."""
        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({
            "items": [{"metadata": {"name": "k9b-backend", "generation": 1},
                       "spec": {"replicas": 1},
                       "status": {"replicas": 1, "availableReplicas": 1,
                                 "updatedReplicas": 1, "observedGeneration": 1,
                                 "conditions": [{"type": "Available", "status": "True"}]}}]
        })
        pvc_json = json.dumps({"items": [{"metadata": {"name": "data-pvc"},
                                          "status": {"phase": "Pending"}}]})
        assert _check_rollout_success(pods_json, deployments_json, pvc_json) is False

    def test_no_success_when_missing_expected_workloads(self) -> None:
        """Should NOT detect success when expected workloads are missing."""
        pods_json = json.dumps({
            "items": [{"metadata": {"name": "k9b-backend-abc123",
                                    "ownerReferences": [{"kind": "ReplicaSet",
                                                        "name": "k9b-backend-abc12345"}]},
                       "status": {"phase": "Running",
                                "conditions": [{"type": "Ready", "status": "True"}]}}]
        })
        deployments_json = json.dumps({
            "items": [{"metadata": {"name": "k9b-backend", "generation": 1},
                       "spec": {"replicas": 1},
                       "status": {"replicas": 1, "availableReplicas": 1,
                                 "updatedReplicas": 1, "observedGeneration": 1,
                                 "conditions": [{"type": "Available", "status": "True"}]}}]
        })
        # Only k9b-backend present, missing k9b-frontend and k9b-scheduler
        assert _check_rollout_success(pods_json, deployments_json, '{"items": []}') is False

    def test_no_success_when_pod_has_no_ready_condition(self) -> None:
        """Should NOT detect success when Running pod has no Ready condition at all."""
        pods_json = json.dumps({
            "items": [
                {"metadata": {"name": "k9b-backend-abc123",
                              "ownerReferences": [{"kind": "ReplicaSet",
                                                  "name": "k9b-backend-abc12345"}]},
                 "status": {"phase": "Running", "conditions": []}},
                {"metadata": {"name": "k9b-frontend-def456",
                              "ownerReferences": [{"kind": "ReplicaSet",
                                                  "name": "k9b-frontend-def67890"}]},
                 "status": {"phase": "Running",
                           "conditions": [{"type": "Ready", "status": "True"}]}},
                {"metadata": {"name": "k9b-scheduler-ghi789",
                              "ownerReferences": [{"kind": "ReplicaSet",
                                                  "name": "k9b-scheduler-ghi78901"}]},
                 "status": {"phase": "Running",
                           "conditions": [{"type": "Ready", "status": "True"}]}}
            ]
        })
        deployments_json = json.dumps({
            "items": [
                {"metadata": {"name": "k9b-backend", "generation": 1},
                 "spec": {"replicas": 1},
                 "status": {"replicas": 1, "availableReplicas": 1,
                           "updatedReplicas": 1, "observedGeneration": 1,
                           "conditions": [{"type": "Available", "status": "True"}]}},
                {"metadata": {"name": "k9b-frontend", "generation": 1},
                 "spec": {"replicas": 1},
                 "status": {"replicas": 1, "availableReplicas": 1,
                           "updatedReplicas": 1, "observedGeneration": 1,
                           "conditions": [{"type": "Available", "status": "True"}]}},
                {"metadata": {"name": "k9b-scheduler", "generation": 1},
                 "spec": {"replicas": 1},
                 "status": {"replicas": 1, "availableReplicas": 1,
                           "updatedReplicas": 1, "observedGeneration": 1,
                           "conditions": [{"type": "Available", "status": "True"}]}}
            ]
        })
        # k9b-backend has no Ready condition - should not count as success
        assert _check_rollout_success(pods_json, deployments_json, '{"items": []}') is False


class TestFailedScheduling:
    """Tests for failed_scheduling failure class (text fallback)."""

    def test_detects_unschedulable_pod(self) -> None:
        """Should detect Unschedulable condition on pod."""
        pods_json = json.dumps({
            "items": [{"metadata": {"name": "unschedulable-pod"},
                       "status": {"phase": "Pending",
                                "conditions": [{"type": "PodScheduled", "status": "False",
                                              "reason": "Unschedulable",
                                              "message": "0/2 nodes are available"}]}}]
        })
        is_fatal, reason, message = _check_failed_scheduling(pods_json, "")
        assert is_fatal is True
        assert reason == "Unschedulable"

    def test_detects_from_events_text(self) -> None:
        """Should detect failed scheduling from events text fallback."""
        pods_json = "{}"
        events_text = "Warning FailedScheduling Pod/k9b-backend - no nodes available for scheduling"
        is_fatal, reason, message = _check_failed_scheduling(pods_json, events_text)
        assert is_fatal is True
        assert reason == "FailedScheduling"

    def test_classify_rollout_state_detects_scheduling(self) -> None:
        """Should classify as failed_scheduling in full classifier."""
        pods_json = json.dumps({
            "items": [{"metadata": {"name": "stuck-pod"},
                       "status": {"phase": "Pending",
                                "conditions": [{"type": "PodScheduled", "status": "False",
                                              "reason": "InsufficientMemory",
                                              "message": "cannot schedule"}]}}]
        })
        result = classify_rollout_state(pods_json, '{"items": []}', '{"items": []}',
                                        "failed to schedule")
        assert result.fatal is True
        assert result.failure_class == FAILURE_FAILED_SCHEDULING
        assert "stuck-pod" in result.affected_pods


class TestPVCPending:
    """Tests for pvc_pending failure class."""

    def test_detects_pending_pvc(self) -> None:
        """Should detect PVC not in Bound state."""
        pvcs = [{"name": "data-pvc", "status": "Pending", "reason": "Waiting for volume"}]
        is_fatal, status, reason, _failure_class = _check_pvc_pending(pvcs)
        assert is_fatal is True
        assert status == "Pending"

    def test_detects_lost_pvc(self) -> None:
        """Should detect PVC in Lost state."""
        pvcs = [{"name": "data-pvc", "status": "Lost", "reason": "ClaimLost"}]
        is_fatal, status, reason, _failure_class = _check_pvc_pending(pvcs)
        assert is_fatal is True
        assert status == "Lost"

    def test_no_false_positive_for_bound_pvc(self) -> None:
        """Should NOT detect issue for Bound PVC."""
        pvcs = [{"name": "data-pvc", "status": "Bound", "reason": ""}]
        is_fatal, status, reason, _failure_class = _check_pvc_pending(pvcs)
        assert is_fatal is False

    def test_classify_rollout_state_detects_pvc_pending(self) -> None:
        """Should classify as pvc_pending in full classifier.
        
        Note: PVC pending is non-fatal during initial polling (WaitForFirstConsumer mode).
        It becomes fatal only after the deadline expires without a pod consuming the PVC.
        This test verifies that ordinary pending PVCs are tracked - the fatal behavior
        is gated by deadline expiration in monitor_rollout.
        """
        # Use Immediate binding mode so pending PVC is not WaitForFirstConsumer
        storage_class_json = json.dumps({
            "items": [{
                "metadata": {"name": "standard"},
                "provisioner": "k8s.io/minikube-hostpath",
                "volumeBindingMode": "Immediate"
            }]
        })
        pvc_json = json.dumps({
            "items": [{"metadata": {"name": "data-pvc", "namespace": "default"},
                       "spec": {"storageClassName": "standard"},
                       "status": {"phase": "Pending",
                                "reason": "Waiting for persistent volumes"}}]
        })
        result = classify_rollout_state(
            '{"items": []}',
            '{"items": []}',
            pvc_json,
            "",
            "",  # events_json
            storage_class_json,  # storage_class_json
            True  # storage_class_available
        )
        # PVC pending without StorageClass evidence is non-fatal during polling
        # (it's WaitForFirstConsumer-safe to wait)
        assert result.fatal is False
        assert result.failure_class == "pvc_pending"
        assert "data-pvc" in result.affected_pvcs


class TestDeploymentConditions:
    """Tests for deployment condition failure classes."""

    def test_detects_replica_failure(self) -> None:
        """Should detect ReplicaFailure condition."""
        conditions = [
            {"type": "Available", "status": "True"},
            {"type": "ReplicaFailure", "status": "True",
             "message": "Scaling failed: insufficient quota"}
        ]
        is_fatal, reason, message = _check_deployment_replica_failure(conditions)
        assert is_fatal is True
        assert reason == "ReplicaFailure"

    def test_detects_progress_deadline_exceeded(self) -> None:
        """Should detect ProgressDeadlineExceeded condition."""
        conditions = [
            {"type": "Available", "status": "False"},
            {"type": "Progressing", "status": "False",
             "reason": "ProgressDeadlineExceeded",
             "message": "Deployment was terminated"}
        ]
        is_fatal, reason, message = _check_deployment_progress_deadline(conditions)
        assert is_fatal is True
        assert reason == "ProgressDeadlineExceeded"

    def test_classify_rollout_state_detects_replica_failure(self) -> None:
        """Should classify as deployment_replica_failure in full classifier."""
        deployments_json = json.dumps({
            "items": [{"metadata": {"name": "k9b-backend"},
                       "status": {"conditions": [
                           {"type": "ReplicaFailure", "status": "True",
                            "message": "Scaling failed"}
                       ]}}]
        })
        result = classify_rollout_state('{"items": []}', deployments_json,
                                        '{"items": []}', "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_DEPLOYMENT_REPLICA_FAILURE

    def test_classify_rollout_state_detects_progress_deadline(self) -> None:
        """Should classify as deployment_progress_deadline in full classifier."""
        deployments_json = json.dumps({
            "items": [{"metadata": {"name": "k9b-backend"},
                       "status": {"conditions": [
                           {"type": "Progressing", "status": "False",
                            "reason": "ProgressDeadlineExceeded",
                            "message": "was terminated"}
                       ]}}]
        })
        result = classify_rollout_state('{"items": []}', deployments_json,
                                        '{"items": []}', "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_DEPLOYMENT_PROGRESS_DEADLINE


class TestPriorityOrder:
    """Tests that failure classes are checked in correct priority order."""

    def test_image_pull_before_crash_loop(self) -> None:
        """ImagePullBackOff should be detected before CrashLoopBackOff."""
        pods_json = json.dumps({
            "items": [{"metadata": {"name": "both-issues"},
                       "status": {"containerStatuses": [
                           {"name": "app",
                            "state": {"waiting": {"reason": "ImagePullBackOff",
                                                  "message": "pull fail"}}},
                           {"name": "sidecar",
                            "state": {"waiting": {"reason": "CrashLoopBackOff",
                                                  "message": "crash"}}}
                       ]}}]
        })
        result = classify_rollout_state(pods_json, '{"items": []}', '{"items": []}', "")
        assert result.failure_class == FAILURE_IMAGE_PULL_BACKOFF

    def test_crash_loop_before_scheduling(self) -> None:
        """CrashLoopBackOff should be detected before scheduling issues."""
        pods_json = json.dumps({
            "items": [{"metadata": {"name": "crashing"},
                       "status": {"phase": "CrashLoopBackOff",
                                "containerStatuses": [
                                    {"name": "app",
                                     "state": {"waiting": {"reason": "CrashLoopBackOff",
                                                           "message": "back-off"}}}
                                ]}}]
        })
        result = classify_rollout_state(pods_json, '{"items": []}', '{"items": []}',
                                        "failed to schedule")
        assert result.failure_class == FAILURE_CRASH_LOOP

    def test_scheduling_before_pvc(self) -> None:
        """FailedScheduling should be detected before PVC issues."""
        pods_json = json.dumps({
            "items": [{"metadata": {"name": "stuck"},
                       "status": {"phase": "Pending",
                                "conditions": [{"type": "PodScheduled", "status": "False",
                                              "reason": "Unschedulable",
                                              "message": "cannot schedule"}]}}]
        })
        pvc_json = json.dumps({"items": [{"metadata": {"name": "data"},
                                          "status": {"phase": "Pending"}}]})
        result = classify_rollout_state(pods_json, '{"items": []}', pvc_json,
                                        "failed to schedule")
        assert result.failure_class == FAILURE_FAILED_SCHEDULING


class TestTimeoutHandling:
    """Tests for rollout timeout handling."""

    def test_timeout_is_failure_class(self) -> None:
        """FAILURE_ROLLOUT_TIMEOUT constant is defined."""
        assert FAILURE_ROLLOUT_TIMEOUT == "rollout_timeout"

    def test_no_false_positive_for_progressing_workload(self) -> None:
        """Should NOT classify as fatal when workload is still progressing."""
        pods_json = json.dumps({
            "items": [{"metadata": {"name": "creating-pod"},
                       "status": {"phase": "Pending",
                                "conditions": [{"type": "Ready", "status": "Unknown"}]}}]
        })
        deployments_json = json.dumps({
            "items": [{"metadata": {"name": "k9b-backend", "generation": 1},
                       "spec": {"replicas": 1},
                       "status": {"replicas": 1, "availableReplicas": 0,
                                 "updatedReplicas": 0, "observedGeneration": 0,
                                 "conditions": [
                                     {"type": "Progressing", "status": "True",
                                      "reason": "NewReplicaSetCreated"}
                                 ]}}]
        })
        assert _check_rollout_success(pods_json, deployments_json, '{"items": []}') is False
        result = classify_rollout_state(pods_json, deployments_json, '{"items": []}', "")
        assert result.fatal is False
        assert result.failure_class == ""


class TestSnapshotCollectionFailure:
    """Tests for kubectl snapshot collection failures."""

    def test_pvc_collection_failure_returns_snapshot_failed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Should return rollout_snapshot_collection_failed when PVC collection fails.
        
        Even if pods and deployments collections succeed, PVC collection failure
        must result in FAILURE_SNAPSHOT_COLLECTION_FAILED.
        """
        from scripts.k9b_cnpg_live_lab_bootstrap import (  # noqa: E402
            KubectlResult,
            monitor_rollout,
        )

        def fake_collect(
            *args: object, **kwargs: object
        ) -> tuple[KubectlResult, KubectlResult, KubectlResult, KubectlResult, KubectlResult, KubectlResult]:
            return (
                KubectlResult(json_data='{"items": []}', success=True),
                KubectlResult(json_data='{"items": []}', success=True),
                KubectlResult(json_data="{}", success=False, error_message="pvc forbidden"),
                KubectlResult(json_data="{}", text_data="", success=True),
                KubectlResult(json_data='{"items": []}', success=True),
                KubectlResult(json_data='{"items": []}', success=True),
            )

        monkeypatch.setattr(
            "scripts.k9b_cnpg_live_lab_bootstrap._collect_rollout_snapshot",
            fake_collect,
        )

        diagnosis = monitor_rollout(
            kubeconfig="/tmp/fake-kubeconfig",
            namespace="k9b-live-lab",
            artifact_dir=tmp_path,
            deadline_seconds=1,
            poll_interval=0,
        )

        assert diagnosis.fatal is True
        assert diagnosis.failure_class == FAILURE_SNAPSHOT_COLLECTION_FAILED
        assert diagnosis.diagnostics["pvc_success"] is False
        assert "pvc forbidden" in diagnosis.diagnostics["pvc_error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
