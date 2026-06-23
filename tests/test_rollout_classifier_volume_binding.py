#!/usr/bin/env python3
"""Tests for transient VolumeBinding conflict detection in rollout classifier.

Tests the fix for the monitor false-positive where transient PVC/VolumeBinding race
during scheduler PreBind was incorrectly classified as fatal failed_scheduling.

The error message being detected:
    running PreBind plugin "VolumeBinding":
    Operation cannot be fulfilled on persistentvolumeclaims "k9b-runs":
    the object has been modified; please apply your changes...

This is transient and Kubernetes should retry automatically.
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
    _check_failed_scheduling_from_events,
    _is_transient_volume_binding_conflict,
    classify_rollout_state,
)


class TestTransientVolumeBindingConflict:
    """Tests for transient VolumeBinding PreBind conflict detection."""

    def test_is_transient_volume_binding_conflict_returns_true_for_prebind_race(self) -> None:
        """Should detect transient VolumeBinding PreBind race condition."""
        message = (
            "running PreBind plugin \"VolumeBinding\": "
            "Operation cannot be fulfilled on persistentvolumeclaims \"k9b-runs\": "
            "the object has been modified; please apply your changes to the latest version"
        )
        assert _is_transient_volume_binding_conflict("FailedScheduling", message) is True

    def test_is_transient_volume_binding_conflict_returns_true_for_variant_message(self) -> None:
        """Should detect transient conflict with slightly different message format."""
        message = (
            "Binding rejected: running PreBind plugin VolumeBinding: "
            "Operation cannot be fulfilled on persistentvolumeclaims \"data-pvc\": "
            "the object has been modified; please apply your changes"
        )
        assert _is_transient_volume_binding_conflict("FailedScheduling", message) is True

    def test_is_transient_volume_binding_conflict_returns_false_for_insufficient_cpu(self) -> None:
        """Should NOT detect as transient for insufficient CPU (fatal scheduling)."""
        message = "0/8 nodes are available: 1 InsufficientCPU, 7 node(s) had taints"
        assert _is_transient_volume_binding_conflict("FailedScheduling", message) is False

    def test_is_transient_volume_binding_conflict_returns_false_for_insufficient_memory(self) -> None:
        """Should NOT detect as transient for insufficient memory (fatal scheduling)."""
        message = "0/4 nodes are available: 2 InsufficientMemory, 2 node(s) had taints"
        assert _is_transient_volume_binding_conflict("FailedScheduling", message) is False

    def test_is_transient_volume_binding_conflict_returns_false_for_node_taints(self) -> None:
        """Should NOT detect as transient for node taints (fatal scheduling)."""
        message = "0/2 nodes are available: 2 node(s) had taints, 1 InsufficientCPU"
        assert _is_transient_volume_binding_conflict("FailedScheduling", message) is False

    def test_is_transient_volume_binding_conflict_returns_false_for_affinity(self) -> None:
        """Should NOT detect as transient for node affinity (fatal scheduling)."""
        message = "0/1 node is available: 1 node(s) didn't match pod affinity/anti-affinity"
        assert _is_transient_volume_binding_conflict("FailedScheduling", message) is False

    def test_is_transient_volume_binding_conflict_returns_false_for_different_reason(self) -> None:
        """Should NOT detect as transient for different event reasons."""
        message = "some error about volume binding"
        # Unschedulable reason should not be treated as transient
        assert _is_transient_volume_binding_conflict("Unschedulable", message) is False

    def test_is_transient_volume_binding_conflict_case_insensitive(self) -> None:
        """Should be case-insensitive when matching message patterns."""
        message = (
            "RUNNING PREBIND PLUGIN \"VOLUMEBINDING\": "
            "OPERATION CANNOT BE FULFILLED ON PERSISTENTVOLUMECLAIMS \"pvc\": "
            "THE OBJECT HAS BEEN MODIFIED; PLEASE APPLY YOUR CHANGES TO THE LATEST VERSION"
        )
        assert _is_transient_volume_binding_conflict("FailedScheduling", message) is True


class TestFailedSchedulingFromEventsWithTransient:
    """Tests for FailedScheduling detection from events JSON with transient handling."""

    def test_detects_transient_volume_binding_as_nonfatal(self) -> None:
        """Should return nonfatal for transient VolumeBinding PreBind race."""
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": (
                    "running PreBind plugin \"VolumeBinding\": "
                    "Operation cannot be fulfilled on persistentvolumeclaims \"k9b-runs\": "
                    "the object has been modified; please apply your changes to the latest version"
                ),
                "involvedObject": {"kind": "Pod", "name": "k9b-backend-abc123"}
            }]
        })

        is_fatal, reason, message = _check_failed_scheduling_from_events(events_json)
        assert is_fatal is False
        assert reason == ""
        assert "k9b-backend-abc123" in message

    def test_detects_insufficient_nodes_as_fatal(self) -> None:
        """Should return fatal for insufficient node availability."""
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": "0/8 nodes are available: 1 InsufficientCPU, 7 node(s) had taints",
                "involvedObject": {"kind": "Pod", "name": "stuck-pod"}
            }]
        })

        is_fatal, reason, message = _check_failed_scheduling_from_events(events_json)
        assert is_fatal is True
        assert reason == "FailedScheduling"

    def test_transient_only_from_failed_scheduling_reason(self) -> None:
        """Should only treat transient for FailedScheduling reason, not Unschedulable."""
        events_json = json.dumps({
            "items": [{
                "reason": "Unschedulable",
                "type": "Warning",
                "message": (
                    "running PreBind plugin VolumeBinding: "
                    "Operation cannot be fulfilled: the object has been modified"
                ),
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        })

        is_fatal, reason, message = _check_failed_scheduling_from_events(events_json)
        # Unschedulable is not the PreBind race pattern - should be fatal
        assert is_fatal is True


class TestClassifyRolloutStateWithTransient:
    """Tests for classify_rollout_state with transient VolumeBinding handling."""

    def test_transient_volume_binding_conflict_is_nonfatal(self) -> None:
        """Should classify transient VolumeBinding conflict as nonfatal."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-backend-abc123"},
                "status": {"phase": "Pending"}
            }]
        })
        deployments_json = json.dumps({"items": []})
        pvc_json = json.dumps({"items": []})
        events_text = ""

        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": (
                    "running PreBind plugin \"VolumeBinding\": "
                    "Operation cannot be fulfilled on persistentvolumeclaims \"k9b-runs\": "
                    "the object has been modified; please apply your changes to the latest version"
                ),
                "involvedObject": {"kind": "Pod", "name": "k9b-backend-abc123"}
            }]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        assert result.fatal is False
        assert result.failure_class == ""

    def test_transient_volume_binding_conflict_records_diagnostics(self) -> None:
        """Should record transient conflict in diagnostics."""
        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({"items": []})
        pvc_json = json.dumps({"items": []})
        events_text = ""

        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": (
                    "running PreBind plugin \"VolumeBinding\": "
                    "Operation cannot be fulfilled on persistentvolumeclaims \"k9b-runs\": "
                    "the object has been modified; please apply your changes to the latest version"
                ),
                "involvedObject": {"kind": "Pod", "name": "k9b-backend-abc123"}
            }]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        assert result.diagnostics.get("transient_volume_binding_conflict") is True
        assert "k9b-backend-abc123" in result.diagnostics.get("transient_volume_binding_pod", "")

    def test_failed_scheduling_with_node_availability_remains_fatal(self) -> None:
        """Should remain fatal for FailedScheduling with insufficient nodes."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "stuck-pod"},
                "status": {"phase": "Pending"}
            }]
        })
        deployments_json = json.dumps({"items": []})
        pvc_json = json.dumps({"items": []})
        events_text = ""

        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": "0/8 nodes are available: 1 InsufficientCPU, 7 node(s) had taints",
                "involvedObject": {"kind": "Pod", "name": "stuck-pod"}
            }]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        assert result.fatal is True
        assert result.failure_class == "failed_scheduling"

    def test_no_conflict_without_transient_message(self) -> None:
        """Should not record transient conflict when message doesn't match pattern."""
        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({"items": []})
        pvc_json = json.dumps({"items": []})
        events_text = ""

        # Message that mentions VolumeBinding but NOT the "object has been modified" pattern
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": "VolumeBinding: cannot find available volume",
                "involvedObject": {"kind": "Pod", "name": "pod-with-volume"}
            }]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        # This is still fatal because it's not the transient PreBind race
        assert result.fatal is True
        assert result.diagnostics.get("transient_volume_binding_conflict") is not True


class TestTransientVolumeBindingWithPendingPVC:
    """Regression tests: transient VolumeBinding + Pending PVC should NOT be fatal.
    
    This is the critical false-positive path: a snapshot that has BOTH:
    1. Transient VolumeBinding PreBind race (nonfatal)
    2. Pending PVC (would normally be fatal pvc_pending)
    
    The classifier must return nonfatal in this case to avoid
    moving from false failed_scheduling to false pvc_pending.
    """

    def test_transient_volume_binding_with_pending_pvc_is_nonfatal(self) -> None:
        """CRITICAL: Transient VolumeBinding + Pending PVC should be nonfatal."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-backend-abc123"},
                "status": {"phase": "Pending"}
            }]
        })
        deployments_json = json.dumps({"items": []})
        events_text = ""

        # Pending PVC that would normally trigger pvc_pending classification
        pvc_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-runs", "namespace": "default"},
                "status": {"phase": "Pending", "reason": ""}
            }]
        })

        # BUT we also have the transient VolumeBinding PreBind race
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": (
                    "running PreBind plugin \"VolumeBinding\": "
                    "Operation cannot be fulfilled on persistentvolumeclaims \"k9b-runs\": "
                    "the object has been modified; please apply your changes to the latest version"
                ),
                "involvedObject": {"kind": "Pod", "name": "k9b-backend-abc123"}
            }]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        
        # Must be NONFATAL despite having Pending PVC
        # The transient conflict takes precedence over pvc_pending
        assert result.fatal is False, (
            "FAILURE: Transient VolumeBinding + Pending PVC should be nonfatal. "
            "This is the critical false-positive path being tested."
        )
        assert result.failure_class == ""
        
        # Diagnostics should record the transient conflict
        assert result.diagnostics.get("transient_volume_binding_conflict") is True
        assert "k9b-runs" in result.diagnostics.get("transient_volume_binding_message", "")
        
        # Should NOT classify as pvc_pending
        assert result.failure_class != "pvc_pending"

    def test_pending_pvc_without_transient_remains_fatal(self) -> None:
        """Pending PVC without transient VolumeBinding should still be fatal."""
        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({"items": []})
        events_text = ""

        # Pending PVC with no transient conflict
        pvc_json = json.dumps({
            "items": [{
                "metadata": {"name": "stuck-pvc", "namespace": "default"},
                "status": {"phase": "Pending", "reason": "Waiting for first consumer to be bound"}
            }]
        })

        # No VolumeBinding transient conflict - but we have InsufficientCPU
        # Note: failed_scheduling has priority over pvc_pending
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": "0/4 nodes are available: 2 InsufficientCPU",
                "involvedObject": {"kind": "Pod", "name": "unrelated-pod"}
            }]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        
        # Must be FATAL - failed_scheduling has priority over pvc_pending
        assert result.fatal is True
        assert result.failure_class == "failed_scheduling"
        
        # Should NOT record transient conflict
        assert result.diagnostics.get("transient_volume_binding_conflict") is not True

    def test_multiple_pvcs_one_pending_with_transient_is_nonfatal(self) -> None:
        """Multiple PVCs with one pending + transient conflict = nonfatal."""
        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({"items": []})
        events_text = ""

        # One bound PVC and one pending PVC
        pvc_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "bound-pvc", "namespace": "default"},
                    "status": {"phase": "Bound"}
                },
                {
                    "metadata": {"name": "pending-pvc", "namespace": "default"},
                    "status": {"phase": "Pending"}
                }
            ]
        })

        # Transient VolumeBinding race
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": (
                    "PreBind plugin VolumeBinding: "
                    "Operation cannot be fulfilled on persistentvolumeclaims \"pending-pvc\": "
                    "the object has been modified; please apply your changes"
                ),
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        
        # Must be NONFATAL - transient conflict present
        assert result.fatal is False
        assert result.diagnostics.get("transient_volume_binding_conflict") is True

    def test_transient_with_pod_scheduled_false_is_nonfatal(self) -> None:
        """CRITICAL: Transient VolumeBinding + PodScheduled=False/Unschedulable = nonfatal.
        
        This tests the fallback path where the pod condition has PodScheduled=False
        with Unschedulable reason. The transient check must run BEFORE the
        _check_failed_scheduling fallback to pod conditions.
        """
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-backend-abc123"},
                "status": {
                    "phase": "Pending",
                    "conditions": [{
                        "type": "PodScheduled",
                        "status": "False",
                        "reason": "Unschedulable",
                        "message": "0/4 nodes are available..."
                    }]
                }
            }]
        })
        deployments_json = json.dumps({"items": []})
        events_text = ""

        # Pending PVC
        pvc_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-runs", "namespace": "default"},
                "status": {"phase": "Pending"}
            }]
        })

        # Transient VolumeBinding race in events
        # Even though pod condition shows Unschedulable, transient event takes precedence
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": (
                    "running PreBind plugin \"VolumeBinding\": "
                    "Operation cannot be fulfilled on persistentvolumeclaims \"k9b-runs\": "
                    "the object has been modified; please apply your changes to the latest version"
                ),
                "involvedObject": {"kind": "Pod", "name": "k9b-backend-abc123"}
            }]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        
        # Must be NONFATAL despite PodScheduled=False in pod conditions
        # Transient VolumeBinding PreBind race takes precedence over pod condition fallback
        assert result.fatal is False, (
            "FAILURE: Transient VolumeBinding + PodScheduled=False should be nonfatal. "
            "The transient check must run before the failed_scheduling pod-condition fallback."
        )
        assert result.failure_class == ""
        
        # Diagnostics should record the transient conflict
        assert result.diagnostics.get("transient_volume_binding_conflict") is True
        assert "k9b-backend-abc123" in result.diagnostics.get("transient_volume_binding_pod", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
