import json
from collections.abc import Sequence
from unittest.mock import MagicMock, patch

from k8s_diag_agent.health.drilldown import DrilldownCollector
from tests.unit.k8s_fake_client import FakeKubernetesReadClient


class MockPodSummary:
    """Mock PodSummary for testing."""
    def __init__(self, namespace: str, name: str, phase: str, reason: str | None = None, waiting_reasons: list[str] | None = None):
        self.namespace = namespace
        self.name = name
        self.phase = phase
        self.reason = reason
        self.waiting_reasons = waiting_reasons or []


class CommandRecorder:
    def __init__(self) -> None:
        self.commands: list[Sequence[str]] = []

    def __call__(self, command: Sequence[str]) -> str:
        self.commands.append(command)
        if "pods" in command:
            # return five non-running pods so we can test the limit
            items = []
            for index in range(5):
                items.append({
                    "metadata": {"namespace": "default", "name": f"pod-{index}"},
                    "status": {
                        "phase": "Pending",
                        "containerStatuses": [
                            {"state": {"waiting": {"reason": "CrashLoopBackOff"}}}
                        ],
                    },
                })
            return json.dumps({"items": items})
        if "events" in command:
            return json.dumps({"items": []})
        if "describe" in command:
            return "some pod status"
        if "deployments" in command or "statefulsets" in command:
            return json.dumps({"items": []})
        if "externalsecrets" in command:
            return json.dumps({"items": []})
        return "{}"


def test_drilldown_collector_limits_pods_and_descriptions() -> None:
    """Test that drilldown collector respects non_running_pods limit and describes limited pods."""
    # Mock the Kubernetes client to return non-running pods
    mock_client = MagicMock()
    mock_client.list_all_namespaces_pods_summaries.return_value = (
        [
            # 5 non-running pods for testing limit
            MockPodSummary("default", "pod-0", "Pending", reason="CrashLoopBackOff"),
            MockPodSummary("default", "pod-1", "Pending", reason="CrashLoopBackOff"),
            MockPodSummary("default", "pod-2", "Pending", reason="ImagePullBackOff"),
            MockPodSummary("default", "pod-3", "Failed", reason="Error"),
            MockPodSummary("default", "pod-4", "Pending"),
        ],
        MagicMock(truncated=False, remaining=0, items_returned=5),
    )

    recorder = CommandRecorder()
    collector = DrilldownCollector(
        max_warning_events=5,
        max_non_running_pods=2,  # Limit to 2 pods
        max_pod_descriptions=1,   # Limit descriptions to 1
        max_rollout_namespaces=1,
        max_rollouts=0,
        command_runner=recorder,
    )

    with patch("k8s_diag_agent.health.drilldown.get_cached_kubernetes_client", return_value=mock_client):
        evidence = collector.collect("cluster", ["default"])

    # Should respect max_non_running_pods limit
    assert len(evidence.non_running_pods) == 2
    # Should only describe max_pod_descriptions pods
    describe_calls = sum(1 for command in recorder.commands if "describe" in command)
    assert describe_calls == 1


def test_drilldown_collector_in_cluster_does_not_pass_context_flag() -> None:
    """Regression test: in-cluster context must NOT be passed to kubectl as --context.
    
    This tests the fix for the bug where internal marker "in-cluster" was being
    passed to kubectl as --context, causing collection failures.
    """
    recorder = CommandRecorder()
    collector = DrilldownCollector(
        max_warning_events=1,
        max_non_running_pods=0,
        max_pod_descriptions=0,
        max_rollout_namespaces=0,
        max_rollouts=0,
        command_runner=recorder,
    )
    collector.collect("in-cluster", ["default"])
    
    # Verify no command contains --context or in-cluster as context
    for command in recorder.commands:
        cmd_str = " ".join(command)
        assert "--context" not in cmd_str, f"Found --context in command: {cmd_str}"
        assert "in-cluster" not in cmd_str, f"Found in-cluster in command: {cmd_str}"


def test_drilldown_collector_in_cluster_underscore_does_not_pass_context_flag() -> None:
    """Regression test: in_cluster context must NOT be passed to kubectl as --context."""
    recorder = CommandRecorder()
    collector = DrilldownCollector(
        max_warning_events=1,
        max_non_running_pods=0,
        max_pod_descriptions=0,
        max_rollout_namespaces=0,
        max_rollouts=0,
        command_runner=recorder,
    )
    collector.collect("in_cluster", ["default"])
    
    # Verify no command contains --context or in_cluster as context
    for command in recorder.commands:
        cmd_str = " ".join(command)
        assert "--context" not in cmd_str, f"Found --context in command: {cmd_str}"
        assert "in_cluster" not in cmd_str, f"Found in_cluster in command: {cmd_str}"


def test_drilldown_collector_real_context_passes_context_flag() -> None:
    """Regression test: real context names should still include --context.
    
    Note: _collect_warning_events now uses Python client (via get_cached_kubernetes_client)
    instead of kubectl subprocess. We mock the client and verify kubectl commands
    from other operations (rollout status) include --context.
    """
    from datetime import UTC, datetime

    from k8s_diag_agent.security.kubernetes_client_models import EventProjection

    recorder = CommandRecorder()
    # Create fake client that returns warning events
    fake_client = FakeKubernetesReadClient()
    fake_client._warning_events = [
        EventProjection(
            namespace="default",
            name="test-event",
            event_type="Warning",
            reason="TestReason",
            message="Test message",
            involved_object_kind="Pod",
            involved_object_name="test-pod",
            creation_timestamp=datetime.now(UTC),
            count=1,
        )
    ]
    
    collector = DrilldownCollector(
        max_warning_events=1,
        max_non_running_pods=0,
        max_pod_descriptions=0,
        max_rollout_namespaces=1,
        max_rollouts=1,
        command_runner=recorder,
    )
    
    # Patch the client factory to return our fake
    import unittest.mock as mock
    with mock.patch(
        "k8s_diag_agent.health.drilldown.get_cached_kubernetes_client",
        return_value=fake_client,
    ):
        collector.collect("my-prod-cluster", ["default"])
    
    # Verify commands with kubectl include --context for real contexts
    kubectl_commands = [cmd for cmd in recorder.commands if "kubectl" in cmd]
    assert len(kubectl_commands) > 0, "No kubectl commands recorded"
    for command in kubectl_commands:
        cmd_str = " ".join(command)
        assert "--context" in cmd_str, f"Missing --context in command: {cmd_str}"
        assert "my-prod-cluster" in cmd_str, f"Missing context name in command: {cmd_str}"
