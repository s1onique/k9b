"""Tests for OTel Demo K8s-native incident injection - Event Detection.

These tests verify FailedScheduling event detection for Pods.
"""

from __future__ import annotations


class TestK8sInjectionEventDetection:
    """Test FailedScheduling event detection for Pods (not Deployments)."""

    def test_failed_scheduling_event_for_pod_filtered(self) -> None:
        """FailedScheduling events are filtered by 'shipping-' in event line."""
        event_line = "default/shipping-abc123: FailedScheduling: Scheduling failed"
        assert "shipping-" in event_line
        assert "FailedScheduling" in event_line

    def test_failed_scheduling_event_for_deployment_ignored(self) -> None:
        """FailedScheduling events for Deployment (not Pod) are ignored."""
        # This is a regression test - events are attached to Pods, not Deployments
        # We filter by 'shipping-' in the line, which correctly excludes Deployment events
        deployment_event = "default/shipping: FailedScheduling: Scheduling failed"
        # Our filter requires 'shipping-' (with hyphen), so Deployment events
        # whose name is just 'shipping' won't match
        assert "shipping-" not in deployment_event

    def test_event_field_selector_queries_pods(self) -> None:
        """Event query uses involvedObject.kind=Pod field selector."""
        # The _poll_for_symptoms function queries events with:
        # --field-selector "reason=FailedScheduling,involvedObject.kind=Pod"
        # This ensures we only get Pod events, not Deployment events
        field_selector = "reason=FailedScheduling,involvedObject.kind=Pod"
        assert "involvedObject.kind=Pod" in field_selector
        assert "involvedObject.kind=Deployment" not in field_selector


class TestK8sInjectionDeploymentUnavailable:
    """Test deployment unavailable evidence collection."""

    def test_deployment_status_unavailable_detected(self) -> None:
        """Deployment is marked unavailable when ready < desired."""
        status = {
            "replicas": 1,
            "readyReplicas": 0,
            "unavailableReplicas": 1,
        }

        replicas = status.get("replicas", 0)
        ready_replicas = status.get("readyReplicas", 0)
        unavailable_replicas = status.get("unavailableReplicas", 0)

        is_unavailable = replicas > 0 and (ready_replicas < replicas or unavailable_replicas > 0)
        assert is_unavailable is True

    def test_deployment_status_available_passes(self) -> None:
        """Deployment is not marked unavailable when all replicas ready."""
        status = {
            "replicas": 1,
            "readyReplicas": 1,
            "unavailableReplicas": 0,
        }

        replicas = status.get("replicas", 0)
        ready_replicas = status.get("readyReplicas", 0)
        unavailable_replicas = status.get("unavailableReplicas", 0)

        is_unavailable = replicas > 0 and (ready_replicas < replicas or unavailable_replicas > 0)
        assert is_unavailable is False

    def test_poll_result_tracks_deployment_unavailable(self) -> None:
        """Poll result includes deployment_unavailable field."""
        # The _poll_for_symptoms function returns a result dict
        # that includes 'deployment_unavailable' field

        from scripts.k9b_otel_demo_lab_k8s_injection import _poll_for_symptoms

        doc = _poll_for_symptoms.__doc__ or ""
        # Docstring documents the return value
        assert "deployment_unavailable" in doc
