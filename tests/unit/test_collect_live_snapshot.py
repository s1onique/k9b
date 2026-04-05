import json
import subprocess
import unittest
from typing import Any, Callable, Sequence
from unittest.mock import patch

from k8s_diag_agent.collect.live_snapshot import _parse_server_version, collect_cluster_snapshot


def _make_runner(helm_failure: bool = False, crd_failure: bool = False) -> Callable[[Sequence[str]], str]:
    def runner(command: Sequence[str]) -> str:
        if command[0] == "helm":
            if helm_failure:
                raise RuntimeError("`helm` failed: not found")
            return "[]"
        if command[0] == "kubectl":
            if "crds" in command:
                if crd_failure:
                    raise RuntimeError("`kubectl` failed: permission denied")
                return json.dumps({"items": []})
            if "version" in command:
                return json.dumps({"serverVersion": {"gitVersion": "v1.28.0"}})
            if "nodes" in command:
                return json.dumps(
                    {
                        "items": [
                            {
                                "metadata": {"name": "node1"},
                                "status": {
                                    "conditions": [
                                        {"type": "Ready", "status": "True"}
                                    ]
                                },
                            }
                        ]
                    }
                )
            if "pods" in command:
                return json.dumps(
                    {
                        "items": [
                            {
                                "metadata": {"name": "pod1"},
                                "status": {"phase": "Running", "containerStatuses": []},
                            }
                        ]
                    }
                )
            if "jobs" in command:
                return json.dumps({"items": []})
            if "events" in command:
                return json.dumps({"items": []})
        return ""
    return runner


class LiveSnapshotCollectionTest(unittest.TestCase):
    @patch("k8s_diag_agent.collect.live_snapshot._run_command")
    def test_missing_helm_is_recorded(self, run_command: Any) -> None:
        run_command.side_effect = _make_runner(helm_failure=True)
        snapshot = collect_cluster_snapshot("demo")
        self.assertIn("helm", snapshot.collection_status.helm_error or "")
        self.assertEqual(snapshot.helm_releases, {})
        self.assertFalse(snapshot.collection_status.missing_evidence)
        self.assertEqual(snapshot.health_signals.node_conditions.total, 1)
        self.assertEqual(snapshot.health_signals.pod_counts.non_running, 0)

    @patch("k8s_diag_agent.collect.live_snapshot._run_command")
    def test_crd_listing_failure_becomes_missing_evidence(self, run_command: Any) -> None:
        run_command.side_effect = _make_runner(crd_failure=True)
        snapshot = collect_cluster_snapshot("demo")
        self.assertIn("crd_list", snapshot.collection_status.missing_evidence)
        self.assertEqual(snapshot.crds, {})
        self.assertEqual(snapshot.health_signals.job_failures, 0)
        self.assertEqual(snapshot.health_signals.warning_events, ())

    @patch("k8s_diag_agent.collect.live_snapshot._run_command")
    def test_succeeded_job_pods_not_counted_as_non_running(self, run_command: Any) -> None:
        base_runner = _make_runner()

        def runner(command: Sequence[str]) -> str:
            if command[0] == "kubectl" and "pods" in command:
                payload = {
                    "items": [
                        {
                            "metadata": {
                                "name": "backup-job-pod",
                                "ownerReferences": [
                                    {"kind": "Job", "name": "backup-job"}
                                ],
                            },
                            "status": {"phase": "Succeeded", "containerStatuses": []},
                        }
                    ]
                }
                return json.dumps(payload)
            return base_runner(command)

        run_command.side_effect = runner
        snapshot = collect_cluster_snapshot("demo")
        self.assertEqual(snapshot.health_signals.pod_counts.non_running, 0)
        self.assertEqual(snapshot.health_signals.pod_counts.completed_job_pods, 1)


class VersionParsingTest(unittest.TestCase):
    def test_parse_server_version_from_json(self) -> None:
        payload = {"serverVersion": {"gitVersion": "v1.28.0", "minor": "28"}}
        version = _parse_server_version(json.dumps(payload))
        self.assertEqual(version, "v1.28.0")

    def test_parse_server_version_handles_missing_git_version(self) -> None:
        payload = {"serverVersion": {"gitVersion": ""}}
        with self.assertRaises(RuntimeError) as ctx:
            _parse_server_version(json.dumps(payload))
        self.assertIn("serverVersion.gitVersion", str(ctx.exception))

    def test_parse_server_version_handles_invalid_json(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            _parse_server_version("not-json")
        self.assertIn("version output could not be parsed", str(ctx.exception))
