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
                return "node1\n"
            if "pods" in command:
                return "pod1\npod2\n"
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

    @patch("k8s_diag_agent.collect.live_snapshot._run_command")
    def test_crd_listing_failure_becomes_missing_evidence(self, run_command: Any) -> None:
        run_command.side_effect = _make_runner(crd_failure=True)
        snapshot = collect_cluster_snapshot("demo")
        self.assertIn("crd_list", snapshot.collection_status.missing_evidence)
        self.assertEqual(snapshot.crds, {})


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
