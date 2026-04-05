import json
from typing import Sequence

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
