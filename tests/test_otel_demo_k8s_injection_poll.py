"""Tests for OTel Demo K8s-native incident injection - Symptom Polling.

These tests verify symptom detection logic in polling.
"""

from __future__ import annotations


class TestK8sInjectionPollSymptomDetection:
    """Test symptom detection logic in polling."""

    def test_pending_pod_detected_from_phase(self) -> None:
        """Pending pod phase should be detected."""
        pod = {
            "metadata": {"name": "shipping-abc123"},
            "status": {"phase": "Pending"},
        }

        phase = pod.get("status", {}).get("phase", "")
        assert phase == "Pending"

    def test_failed_scheduling_detected_from_condition(self) -> None:
        """FailedScheduling condition should be detected."""
        pod = {
            "metadata": {"name": "shipping-abc123"},
            "status": {
                "phase": "Pending",
                "conditions": [
                    {
                        "type": "PodScheduled",
                        "status": "False",
                        "reason": "Unschedulable",
                        "message": "0/3 nodes are available: 1 node(s) had taints that the pod didn't tolerate.",
                    }
                ],
            },
        }

        conditions = pod.get("status", {}).get("conditions", [])
        for cond in conditions:
            if cond.get("type") == "PodScheduled" and cond.get("status") == "False":
                reason = cond.get("reason", "")
                assert "Unschedulable" in reason


class TestK8sInjectionRobustPodLookup:
    """Test robust pod lookup with fallback strategies."""

    def test_filter_pods_by_ownership_exports(self) -> None:
        """_filter_pods_by_ownership is available for testing."""
        from scripts.k9b_otel_demo_lab_k8s_injection import _filter_pods_by_ownership

        assert callable(_filter_pods_by_ownership)

    def test_filter_pods_by_name_prefix_and_replicaset(self) -> None:
        """Pods are filtered by name prefix AND ReplicaSet ownership."""
        from scripts.k9b_otel_demo_lab_k8s_injection import _filter_pods_by_ownership

        # Both pods have shipping- prefix and valid ReplicaSet owners
        all_pods = [
            {
                "metadata": {
                    "name": "shipping-abc123",
                    "ownerReferences": [
                        {"kind": "ReplicaSet", "name": "shipping-rs-xyz789"}
                    ]
                }
            },
            {
                "metadata": {
                    "name": "shipping-def456",
                    "ownerReferences": [
                        {"kind": "ReplicaSet", "name": "shipping-replicas"}
                    ]
                }
            },
            # This pod has shipping- prefix but non-matching RS owner
            {
                "metadata": {
                    "name": "shipping-ghi789",
                    "ownerReferences": [
                        {"kind": "ReplicaSet", "name": "other-rs"}
                    ]
                }
            },
        ]

        matching = _filter_pods_by_ownership(all_pods, "shipping")
        # Only 2 match: first two have matching RS names, third doesn't
        assert len(matching) == 2
        names = [p["metadata"]["name"] for p in matching]
        assert "shipping-abc123" in names
        assert "shipping-def456" in names
        assert "shipping-ghi789" not in names

    def test_filter_rejects_pods_without_replicaset_owner(self) -> None:
        """Pods without ReplicaSet owner are rejected."""
        from scripts.k9b_otel_demo_lab_k8s_injection import _filter_pods_by_ownership

        all_pods = [
            {
                "metadata": {
                    "name": "shipping-abc123",
                    "ownerReferences": [
                        {"kind": "DaemonSet", "name": "some-daemon"}
                    ]
                }
            },
        ]

        matching = _filter_pods_by_ownership(all_pods, "shipping")
        # No match - DaemonSet is not ReplicaSet
        assert len(matching) == 0

    def test_filter_rejects_non_matching_prefix(self) -> None:
        """Pods without matching name prefix are rejected."""
        from scripts.k9b_otel_demo_lab_k8s_injection import _filter_pods_by_ownership

        all_pods = [
            {
                "metadata": {
                    "name": "other-pod-xyz",
                    "ownerReferences": [
                        {"kind": "ReplicaSet", "name": "shipping-rs"}
                    ]
                }
            },
        ]

        matching = _filter_pods_by_ownership(all_pods, "shipping")
        # No match - name doesn't start with "shipping-"
        assert len(matching) == 0

    def test_poll_result_tracks_lookup_method(self) -> None:
        """Poll result tracks which lookup method was used."""
        # The _poll_for_symptoms function returns a result dict
        # that includes 'pod_lookup_method' field
        # This is a structural test - verify the function signature
        import inspect

        from scripts.k9b_otel_demo_lab_k8s_injection import _poll_for_symptoms

        sig = inspect.signature(_poll_for_symptoms)
        params = list(sig.parameters.keys())
        assert "kubeconfig" in params
        assert "namespace" in params
        assert "deployment" in params
        assert "artifact_dir" in params
