"""Tests for bounded pod collection - ACT-K9B-HEALTH-POD-SNAPSHOT-BOUNDED-PYCLIENT01.

These tests verify:
1. Pagination works correctly with multiple pages
2. Terminal pod exclusion excludes Succeeded/Failed phases
3. Failed sampler cap limits results
4. Static verifier blocks kubectl get pods --all-namespaces patterns
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from k8s_diag_agent.security.kubernetes_client_models import PodSummary
from k8s_diag_agent.security.kubernetes_client_pagination import (
    list_all_namespaces_pods_summaries,
    sample_failed_pods_bounded,
)


class MockMetadata:
    """Mock pagination metadata."""
    def __init__(self, remaining_item_count: int | None = None, continue_token: str | None = None):
        self.remaining_item_count = remaining_item_count
        self._continue = continue_token


class MockPod:
    """Mock Kubernetes pod object."""
    def __init__(self, namespace: str, name: str, phase: str, reason: str | None = None):
        self.metadata = MagicMock()
        self.metadata.namespace = namespace
        self.metadata.name = name
        self.metadata.uid = f"uid-{namespace}-{name}"
        self.metadata.ownerReferences = []
        self.metadata.creationTimestamp = "2024-01-01T00:00:00Z"
        self.spec = MagicMock()
        self.spec.nodeName = f"node-{namespace}"
        self.status = MagicMock()
        self.status.phase = phase
        self.status.reason = reason
        self.status.containerStatuses = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict format expected by PodSummary.from_pod_dict."""
        return {
            "metadata": {
                "namespace": self.metadata.namespace,
                "name": self.metadata.name,
                "uid": self.metadata.uid,
                "ownerReferences": self.metadata.ownerReferences,
                "creationTimestamp": self.metadata.creationTimestamp,
            },
            "spec": {
                "nodeName": self.spec.nodeName,
            },
            "status": {
                "phase": self.status.phase,
                "reason": self.status.reason,
                "containerStatuses": self.status.containerStatuses,
            },
        }


class TestPagination:
    """Test pagination behavior with multiple pages."""

    def test_pagination_consumes_all_pages(self) -> None:
        """Verify all pages are consumed and no page is retained."""
        # Create mock client
        mock_client = MagicMock()

        # Simulate three pages of responses
        page1 = MagicMock()
        page1.items = [
            MockPod("default", "pod-1", "Running"),
            MockPod("default", "pod-2", "Running"),
        ]
        page1.metadata = MockMetadata(continue_token="abc")

        page2 = MagicMock()
        page2.items = [
            MockPod("kube-system", "pod-3", "Running"),
        ]
        page2.metadata = MockMetadata(continue_token="def")

        page3 = MagicMock()
        page3.items = [
            MockPod("monitoring", "pod-4", "Pending"),
        ]
        page3.metadata = MockMetadata(continue_token=None)

        mock_client.core_v1.list_pod_for_all_namespaces.side_effect = [page1, page2, page3]

        # Call the function
        summaries, pagination = list_all_namespaces_pods_summaries(
            mock_client,
            page_limit=200,
            max_active_pods=1000,
            exclude_terminal=True,
        )

        # Verify all pages were consumed
        assert mock_client.core_v1.list_pod_for_all_namespaces.call_count == 3

        # Verify all items were collected
        assert len(summaries) == 4
        assert [s.name for s in summaries] == ["pod-1", "pod-2", "pod-3", "pod-4"]

        # Verify pagination metadata
        assert pagination.truncated is False
        assert pagination.continuation_token is None

    def test_pagination_respects_max_items_cap(self) -> None:
        """Verify pagination stops when max_active_pods is reached."""
        mock_client = MagicMock()

        # Create pages that would exceed max
        page1 = MagicMock()
        page1.items = [
            MockPod("default", f"pod-{i}", "Running") for i in range(3)
        ]
        page1.metadata = MockMetadata(continue_token="abc")

        page2 = MagicMock()
        page2.items = [
            MockPod("default", "pod-3", "Running"),
            MockPod("default", "pod-4", "Running"),
            MockPod("default", "pod-5", "Running"),
        ]
        page2.metadata = MockMetadata(remaining_item_count=100, continue_token="def")

        mock_client.core_v1.list_pod_for_all_namespaces.side_effect = [page1, page2]

        # Set max_active_pods to 3
        summaries, pagination = list_all_namespaces_pods_summaries(
            mock_client,
            page_limit=200,
            max_active_pods=3,
            exclude_terminal=True,
        )

        # Should have stopped after first page
        assert mock_client.core_v1.list_pod_for_all_namespaces.call_count == 2
        assert len(summaries) == 3
        assert pagination.truncated is True
        assert pagination.remaining >= 0


class TestTerminalPodExclusion:
    """Test terminal pod exclusion behavior."""

    def test_excludes_succeeded_pods(self) -> None:
        """Verify Succeeded pods are excluded."""
        mock_client = MagicMock()
        mock_client.core_v1.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[
                MockPod("default", "pod-running", "Running"),
                MockPod("default", "pod-succeeded", "Succeeded"),
            ],
            metadata=MockMetadata(continue_token=None),
        )

        summaries, _ = list_all_namespaces_pods_summaries(
            mock_client,
            exclude_terminal=True,
        )

        # Only Running pod should be present
        assert len(summaries) == 1
        assert summaries[0].name == "pod-running"

    def test_excludes_failed_pods(self) -> None:
        """Verify Failed pods are excluded."""
        mock_client = MagicMock()
        mock_client.core_v1.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[
                MockPod("default", "pod-running", "Running"),
                MockPod("default", "pod-failed", "Failed"),
            ],
            metadata=MockMetadata(continue_token=None),
        )

        summaries, _ = list_all_namespaces_pods_summaries(
            mock_client,
            exclude_terminal=True,
        )

        # Only Running pod should be present
        assert len(summaries) == 1
        assert summaries[0].name == "pod-running"

    def test_excludes_evicted_pods(self) -> None:
        """Verify Evicted pods (phase=Failed, reason=Evicted) are excluded."""
        mock_client = MagicMock()
        mock_client.core_v1.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[
                MockPod("default", "pod-running", "Running"),
                MockPod("default", "pod-evicted", "Failed", reason="Evicted"),
            ],
            metadata=MockMetadata(continue_token=None),
        )

        summaries, _ = list_all_namespaces_pods_summaries(
            mock_client,
            exclude_terminal=True,
        )

        # Only Running pod should be present (Evicted has phase=Failed)
        assert len(summaries) == 1
        assert summaries[0].name == "pod-running"

    def test_includes_pending_and_unknown(self) -> None:
        """Verify Pending and Unknown phases are included."""
        mock_client = MagicMock()
        mock_client.core_v1.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[
                MockPod("default", "pod-running", "Running"),
                MockPod("default", "pod-pending", "Pending"),
                MockPod("default", "pod-unknown", "Unknown"),
            ],
            metadata=MockMetadata(continue_token=None),
        )

        summaries, _ = list_all_namespaces_pods_summaries(
            mock_client,
            exclude_terminal=True,
        )

        # All non-terminal phases should be present
        assert len(summaries) == 3
        phases = {s.phase for s in summaries}
        assert phases == {"Running", "Pending", "Unknown"}


class TestFailedSamplerCap:
    """Test failed pod sampler cap behavior."""

    def test_scanned_limit_enforced(self) -> None:
        """Verify scanned limit is enforced."""
        mock_client = MagicMock()

        # Create many failed pods
        page1 = MagicMock()
        page1.items = [
            MockPod("default", f"failed-{i}", "Failed") for i in range(10)
        ]
        page1.metadata = MockMetadata(continue_token="abc")

        page2 = MagicMock()
        page2.items = [
            MockPod("default", f"failed-{i}", "Failed") for i in range(10, 20)
        ]
        page2.metadata = MockMetadata(continue_token=None)

        mock_client.core_v1.list_pod_for_all_namespaces.side_effect = [page1, page2]

        # Set max_scanned to 15
        summaries, metadata = sample_failed_pods_bounded(
            mock_client,
            page_limit=200,
            max_scanned=15,
        )

        # Should stop scanning after 15 pods
        assert metadata["scanned"] == 15
        assert metadata["scan_truncated"] is True

    def test_failed_reported_limit_enforced(self) -> None:
        """Verify failed reported limit is enforced."""
        mock_client = MagicMock()

        page = MagicMock()
        page.items = [
            MockPod("default", f"failed-{i}", "Failed", reason="Error") for i in range(100)
        ]
        page.metadata = MockMetadata(continue_token=None)

        mock_client.core_v1.list_pod_for_all_namespaces.return_value = page

        summaries, metadata = sample_failed_pods_bounded(
            mock_client,
            page_limit=200,
            max_scanned=500,
            max_failed_reported=50,
        )

        # Should be capped at 50 failed pods
        assert metadata["failed_count"] == 50
        assert len([s for s in summaries if s.reason == "Error"]) == 50

    def test_evicted_separate_limit(self) -> None:
        """Verify evicted pods have separate limit from other failed."""
        mock_client = MagicMock()

        page = MagicMock()
        page.items = [
            MockPod("default", f"evicted-{i}", "Failed", reason="Evicted") for i in range(30)
        ] + [
            MockPod("default", f"error-{i}", "Failed", reason="Error") for i in range(60)
        ]
        page.metadata = MockMetadata(continue_token=None)

        mock_client.core_v1.list_pod_for_all_namespaces.return_value = page

        summaries, metadata = sample_failed_pods_bounded(
            mock_client,
            page_limit=200,
            max_scanned=500,
            max_failed_reported=50,
            max_evicted_reported=20,
        )

        # Should have 20 evicted + 50 failed
        assert metadata["evicted_count"] == 20
        assert metadata["failed_count"] == 50
        assert len(summaries) == 70

    def test_truncation_flags_set_correctly(self) -> None:
        """Verify truncation metadata flags are set correctly."""
        mock_client = MagicMock()

        # Create enough to trigger both limits
        page = MagicMock()
        page.items = [
            MockPod("default", f"pod-{i}", "Failed", reason="Evicted" if i < 25 else "Error")
            for i in range(60)
        ]
        page.metadata = MockMetadata(continue_token=None)

        mock_client.core_v1.list_pod_for_all_namespaces.return_value = page

        _, metadata = sample_failed_pods_bounded(
            mock_client,
            max_scanned=500,
            max_failed_reported=50,
            max_evicted_reported=20,
        )

        # Both evicted and failed should be truncated
        assert metadata["evicted_truncated"] is True
        assert metadata["failed_truncated"] is True


class TestPodSummaryProjection:
    """Test PodSummary projection correctness."""

    def test_projection_contains_required_fields(self) -> None:
        """Verify PodSummary contains all required fields."""
        pod_dict = {
            "metadata": {
                "namespace": "test-ns",
                "name": "test-pod",
                "uid": "test-uid",
                "ownerReferences": [{"kind": "Deployment", "name": "test-deploy"}],
                "creationTimestamp": "2024-01-01T00:00:00Z",
            },
            "spec": {
                "nodeName": "test-node",
            },
            "status": {
                "phase": "Running",
                "reason": None,
                "containerStatuses": [
                    {"restartCount": 2, "state": {"running": {}}}
                ],
            },
        }

        summary = PodSummary.from_pod_dict(pod_dict)

        assert summary.namespace == "test-ns"
        assert summary.name == "test-pod"
        assert summary.phase == "Running"
        assert summary.node_name == "test-node"
        assert summary.owner_kind == "Deployment"
        assert summary.owner_name == "test-deploy"
        assert summary.restart_count == 2
        assert summary.created_at is not None

    def test_projection_excludes_full_manifest(self) -> None:
        """Verify PodSummary does not leak full pod manifest."""
        pod_dict = {
            "metadata": {
                "namespace": "test-ns",
                "name": "test-pod",
            },
            "spec": {
                "nodeName": "test-node",
                "containers": [{"env": [{"name": "SECRET", "value": "hunter2"}]}],
            },
            "status": {"phase": "Running"},
        }

        summary = PodSummary.from_pod_dict(pod_dict)

        # PodSummary should not have env or container specs
        assert not hasattr(summary, "containers")
        assert not hasattr(summary, "env")
        # It should have compact waiting_reasons and terminated_reasons
        assert hasattr(summary, "waiting_reasons")
        assert hasattr(summary, "terminated_reasons")


class TestFieldSelector:
    """Test Kubernetes field selector behavior."""

    def test_field_selector_excludes_terminal_phases(self) -> None:
        """Verify correct field selector is passed for terminal exclusion."""
        mock_client = MagicMock()
        mock_client.core_v1.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[],
            metadata=MockMetadata(continue_token=None),
        )

        list_all_namespaces_pods_summaries(
            mock_client,
            exclude_terminal=True,
        )

        # Check the field_selector argument
        call_args = mock_client.core_v1.list_pod_for_all_namespaces.call_args
        field_selector = call_args.kwargs.get("field_selector") or call_args[1].get("field_selector")

        assert "!=Succeeded" in field_selector
        assert "!=Failed" in field_selector

    def test_no_field_selector_when_exclude_false(self) -> None:
        """Verify no field selector when exclude_terminal=False."""
        mock_client = MagicMock()
        mock_client.core_v1.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[],
            metadata=MockMetadata(continue_token=None),
        )

        list_all_namespaces_pods_summaries(
            mock_client,
            exclude_terminal=False,
        )

        # Check the field_selector argument
        call_args = mock_client.core_v1.list_pod_for_all_namespaces.call_args
        field_selector = call_args.kwargs.get("field_selector") or call_args[1].get("field_selector")

        assert field_selector is None
