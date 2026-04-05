import json
import subprocess
import unittest
from unittest.mock import patch

from k8s_diag_agent.collect.live_snapshot import collect_cluster_snapshot


def _make_runner(helm_failure: bool = False, crd_failure: bool = False):
    def runner(command):
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
                return "Server Version: v1.28.0"
            if "nodes" in command:
                return "node1\n"
            if "pods" in command:
                return "pod1\npod2\n"
        return ""
    return runner


class LiveSnapshotCollectionTest(unittest.TestCase):
    @patch("k8s_diag_agent.collect.live_snapshot._run_command")
    def test_missing_helm_is_recorded(self, run_command):
        run_command.side_effect = _make_runner(helm_failure=True)
        snapshot = collect_cluster_snapshot("demo")
        self.assertIn("helm", snapshot.collection_status.helm_error or "")
        self.assertEqual(snapshot.helm_releases, {})
        self.assertFalse(snapshot.collection_status.missing_evidence)

    @patch("k8s_diag_agent.collect.live_snapshot._run_command")
    def test_crd_listing_failure_becomes_missing_evidence(self, run_command):
        run_command.side_effect = _make_runner(crd_failure=True)
        snapshot = collect_cluster_snapshot("demo")
        self.assertIn("crd_list", snapshot.collection_status.missing_evidence)
        self.assertEqual(snapshot.crds, {})
