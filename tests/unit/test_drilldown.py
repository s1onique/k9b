import json
from collections.abc import Sequence

from k8s_diag_agent.health.drilldown import DrilldownCollector


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
    recorder = CommandRecorder()
    collector = DrilldownCollector(
        max_warning_events=5,
        max_non_running_pods=2,
        max_pod_descriptions=1,
        max_rollout_namespaces=1,
        max_rollouts=0,
        command_runner=recorder,
    )
    evidence = collector.collect("cluster", ["default"])
    assert len(evidence.non_running_pods) == 2
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
    """Regression test: real context names should still include --context."""
    recorder = CommandRecorder()
    collector = DrilldownCollector(
        max_warning_events=1,
        max_non_running_pods=0,
        max_pod_descriptions=0,
        max_rollout_namespaces=0,
        max_rollouts=0,
        command_runner=recorder,
    )
    collector.collect("my-prod-cluster", ["default"])
    
    # Verify commands with kubectl include --context for real contexts
    kubectl_commands = [cmd for cmd in recorder.commands if "kubectl" in cmd]
    assert len(kubectl_commands) > 0, "No kubectl commands recorded"
    for command in kubectl_commands:
        cmd_str = " ".join(command)
        assert "--context" in cmd_str, f"Missing --context in command: {cmd_str}"
        assert "my-prod-cluster" in cmd_str, f"Missing context name in command: {cmd_str}"
