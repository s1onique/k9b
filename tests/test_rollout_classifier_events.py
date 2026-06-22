#!/usr/bin/env python3
"""Tests for rollout classifier event parsing (structural JSON).

Tests: FailedScheduling, Unhealthy/readiness from events JSON
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
    _check_readiness_probe_failed_from_events,
    classify_rollout_state,
)


class TestFailedSchedulingFromEventsJSON:
    """Tests for FailedScheduling detection from structural event JSON."""

    def test_detects_failed_scheduling_reason_from_json(self) -> None:
        """Should detect FailedScheduling from event.reason."""
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": "0/2 nodes are available: 1 InsufficientCPU, 1 node(s) had taints",
                "involvedObject": {"kind": "Pod", "name": "k9b-backend-abc123"}
            }]
        })
        
        is_fatal, reason, message = _check_failed_scheduling_from_events(events_json)
        assert is_fatal is True
        assert reason == "FailedScheduling"
        assert "k9b-backend-abc123" in message

    def test_detects_insufficient_memory_from_json(self) -> None:
        """Should detect InsufficientMemory from Warning event."""
        events_json = json.dumps({
            "items": [{
                "reason": "InsufficientMemory",
                "type": "Warning",
                "message": "Node did not have enough memory",
                "involvedObject": {"kind": "Pod", "name": "k9b-frontend-xyz789"}
            }]
        })
        
        is_fatal, reason, message = _check_failed_scheduling_from_events(events_json)
        assert is_fatal is True
        assert reason == "InsufficientMemory"

    def test_detects_unschedulable_from_json(self) -> None:
        """Should detect Unschedulable from Warning event."""
        events_json = json.dumps({
            "items": [{
                "reason": "Unschedulable",
                "type": "Warning",
                "message": "Pod cannot be scheduled",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        })
        
        is_fatal, reason, message = _check_failed_scheduling_from_events(events_json)
        assert is_fatal is True
        assert reason == "Unschedulable"

    def test_no_false_positive_for_normal_event(self) -> None:
        """Should NOT detect issue for normal (non-scheduling) events."""
        events_json = json.dumps({
            "items": [{
                "reason": "Scheduled",
                "type": "Normal",
                "message": "Successfully scheduled",
                "involvedObject": {"kind": "Pod", "name": "healthy-pod"}
            }]
        })
        
        is_fatal, reason, message = _check_failed_scheduling_from_events(events_json)
        assert is_fatal is False

    def test_classify_rollout_state_with_events_json(self) -> None:
        """Should classify as failed_scheduling when events JSON has FailedScheduling."""
        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({"items": []})
        pvc_json = json.dumps({"items": []})
        events_text = ""  # Not used - events_json is primary
        
        events_json = json.dumps({
            "items": [{
                "reason": "FailedScheduling",
                "type": "Warning",
                "message": "0/2 nodes available",
                "involvedObject": {"kind": "Pod", "name": "stuck-pod"}
            }]
        })
        
        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        assert result.fatal is True
        assert result.failure_class == "failed_scheduling"


class TestReadinessProbeFromEventsJSON:
    """Tests for readiness probe failure detection from structural event JSON."""

    def test_detects_unhealthy_with_readiness_message(self) -> None:
        """Should detect Unhealthy event with readiness message."""
        events_json = json.dumps({
            "items": [{
                "reason": "Unhealthy",
                "type": "Warning",
                "message": "Readiness probe failed: Get http://:8080/health: dial tcp",
                "involvedObject": {"kind": "Pod", "name": "unready-pod"}
            }]
        })
        
        is_fatal, reason, message = _check_readiness_probe_failed_from_events(events_json)
        assert is_fatal is True
        assert reason == "Unhealthy"
        assert "Readiness" in message

    def test_detects_readiness_probe_failed_reason(self) -> None:
        """Should detect ReadinessProbeFailed event reason."""
        events_json = json.dumps({
            "items": [{
                "reason": "ReadinessProbeFailed",
                "type": "Warning",
                "message": "Readiness probe failed",
                "involvedObject": {"kind": "Pod", "name": "probe-fail-pod"}
            }]
        })
        
        is_fatal, reason, message = _check_readiness_probe_failed_from_events(events_json)
        assert is_fatal is True
        assert reason == "ReadinessProbeFailed"

    def test_detects_liveness_probe_failed_reason(self) -> None:
        """Should detect LivenessProbeFailed event reason."""
        events_json = json.dumps({
            "items": [{
                "reason": "LivenessProbeFailed",
                "type": "Warning",
                "message": "Liveness probe failed",
                "involvedObject": {"kind": "Pod", "name": "liveness-fail-pod"}
            }]
        })
        
        is_fatal, reason, message = _check_readiness_probe_failed_from_events(events_json)
        assert is_fatal is True
        assert reason == "LivenessProbeFailed"

    def test_no_false_positive_for_normal_unhealthy(self) -> None:
        """Should NOT detect for Unhealthy without readiness message."""
        events_json = json.dumps({
            "items": [{
                "reason": "Unhealthy",
                "type": "Warning",
                "message": "Some other issue",
                "involvedObject": {"kind": "Pod", "name": "other-pod"}
            }]
        })
        
        is_fatal, reason, message = _check_readiness_probe_failed_from_events(events_json)
        assert is_fatal is False

    def test_classify_rollout_state_with_readiness_events(self) -> None:
        """Should classify as readiness_probe_failed from events JSON."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "probe-fail-pod"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{"name": "app", "ready": False}]
                }
            }]
        })
        deployments_json = json.dumps({"items": []})
        pvc_json = json.dumps({"items": []})
        events_text = ""
        
        events_json = json.dumps({
            "items": [{
                "reason": "Unhealthy",
                "type": "Warning",
                "message": "Readiness probe failed",
                "involvedObject": {"kind": "Pod", "name": "probe-fail-pod"}
            }]
        })
        
        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, events_text, events_json
        )
        assert result.fatal is True
        assert result.failure_class == "readiness_probe_failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
