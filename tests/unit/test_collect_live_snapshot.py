import json
import os
import unittest
from collections.abc import Callable, Sequence
from typing import Any
from unittest.mock import patch

from k8s_diag_agent.collect.live_snapshot import (
    _kubectl,
    _parse_server_version,
    collect_cluster_snapshot,
    list_kube_contexts,
)
from k8s_diag_agent.kubernetes_auth import is_in_cluster
from k8s_diag_agent.security.kubectl_errors import KubectlExecutionError


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


class TimeoutTest(unittest.TestCase):
    """Tests for command timeout/error behavior using run_kubectl seam."""

    @patch("k8s_diag_agent.collect.live_snapshot.run_kubectl")
    def test_timeout_raises_runtime_error(self, mock_run_kubectl: Any) -> None:
        """Test that kubectl timeout is converted to RuntimeError."""
        from k8s_diag_agent.collect.live_snapshot import KUBECTL_COMMAND_TIMEOUT_SECONDS, list_kube_contexts

        # Simulate KubectlExecutionError being raised by run_kubectl (timeout path)
        mock_run_kubectl.side_effect = KubectlExecutionError(
            "`kubectl` timed out after 60s. Cluster may be unresponsive or under load.",
            command=["kubectl", "config", "get-contexts", "-o", "name"],
            elapsed_seconds=KUBECTL_COMMAND_TIMEOUT_SECONDS,
        )

        with self.assertRaises(RuntimeError) as ctx:
            list_kube_contexts()

        # Verify timeout message is informative but safe
        error_msg = str(ctx.exception)
        self.assertIn("timed out", error_msg)
        self.assertIn(str(KUBECTL_COMMAND_TIMEOUT_SECONDS), error_msg)
        self.assertIn("kubectl", error_msg)
        self.assertNotIn("--token", error_msg)
        self.assertNotIn("kubeconfig", error_msg)

    @patch("k8s_diag_agent.collect.live_snapshot.run_kubectl")
    def test_oserror_raises_runtime_error_with_architecture_hint(self, mock_run_kubectl: Any) -> None:
        """Test that OSError (exec format error) is converted to RuntimeError with architecture hint."""
        from k8s_diag_agent.collect.live_snapshot import list_kube_contexts

        mock_run_kubectl.side_effect = KubectlExecutionError(
            "Failed to execute kubectl: [Errno 8] Exec format error: 'kubectl'. "
            "Check that the binary exists and matches the container CPU architecture.",
            command=["kubectl", "config", "get-contexts", "-o", "name"],
        )

        with self.assertRaises(RuntimeError) as ctx:
            list_kube_contexts()

        error_msg = str(ctx.exception)
        self.assertIn("Failed to execute", error_msg)
        self.assertIn("architecture", error_msg)
        self.assertNotIn("--token", error_msg)
        self.assertNotIn("kubeconfig", error_msg)

    @patch("k8s_diag_agent.collect.live_snapshot.run_kubectl")
    def test_file_not_found_raises_specific_message(self, mock_run_kubectl: Any) -> None:
        """Test that FileNotFoundError returns 'not found' message, not architecture hint."""
        from k8s_diag_agent.collect.live_snapshot import list_kube_contexts

        mock_run_kubectl.side_effect = KubectlExecutionError(
            "Command `kubectl` not found. Ensure kubectl is on PATH.",
            command=["kubectl", "config", "get-contexts", "-o", "name"],
        )

        with self.assertRaises(RuntimeError) as ctx:
            list_kube_contexts()

        error_msg = str(ctx.exception)
        self.assertIn("not found", error_msg)
        self.assertIn("kubectl", error_msg)
        self.assertNotIn("architecture", error_msg)
        self.assertNotIn("--token", error_msg)
        self.assertNotIn("kubeconfig", error_msg)


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


class InClusterAuthTest(unittest.TestCase):
    """Tests for in-cluster authentication mode."""

    def test_is_in_cluster_returns_false_when_kubeconfig_set(self) -> None:
        """When KUBECONFIG is set, in-cluster detection should return False."""
        with patch.dict(os.environ, {"KUBECONFIG": "/some/path"}, clear=False):
            with patch("pathlib.Path.exists", return_value=True):
                result = is_in_cluster()
                self.assertFalse(result)

    def test_is_in_cluster_returns_false_when_no_service_account(self) -> None:
        """When service account files don't exist, should return False."""
        env_without_kubeconfig = {k: v for k, v in os.environ.items() if k != "KUBECONFIG"}
        with patch.dict(os.environ, env_without_kubeconfig, clear=True):
            with patch("pathlib.Path.exists", return_value=False):
                result = is_in_cluster()
                self.assertFalse(result)

    def test_is_in_cluster_returns_true_when_service_account_present(self) -> None:
        """When service account files exist and KUBECONFIG is not set, should return True."""
        env_without_kubeconfig = {k: v for k, v in os.environ.items() if k != "KUBECONFIG"}
        with patch.dict(os.environ, env_without_kubeconfig, clear=True):
            with patch("pathlib.Path.exists", return_value=True):
                result = is_in_cluster()
                self.assertTrue(result)

    @patch("k8s_diag_agent.collect.live_snapshot._run_command")
    def test_list_kube_contexts_returns_in_cluster_in_cluster_mode(self, run_command: Any) -> None:
        """When in-cluster, list_kube_contexts should return ['in-cluster']."""
        with patch("k8s_diag_agent.collect.live_snapshot.is_in_cluster", return_value=True):
            contexts = list_kube_contexts()
            self.assertEqual(contexts, ["in-cluster"])
            run_command.assert_not_called()

    @patch("k8s_diag_agent.collect.live_snapshot._run_command")
    def test_list_kube_contexts_uses_kubeconfig_when_not_in_cluster(self, run_command: Any) -> None:
        """When not in-cluster, should use kubeconfig context discovery."""
        run_command.return_value = "context1\ncontext2\n"
        
        with patch("k8s_diag_agent.collect.live_snapshot.is_in_cluster", return_value=False):
            contexts = list_kube_contexts()
            self.assertEqual(contexts, ["context1", "context2"])
            run_command.assert_called_once_with(
                ["kubectl", "config", "get-contexts", "-o", "name"],
                chunk_size=None,
            )

    def test_kubectl_in_cluster_mode_skips_context_flag(self) -> None:
        """When context is 'in-cluster', kubectl should not use --context."""
        with patch("k8s_diag_agent.collect.live_snapshot._run_command") as run_command:
            run_command.return_value = '{"items": []}'
            _kubectl("in-cluster", "get", "pods", "-o", "json")
            run_command.assert_called_once_with(["kubectl", "get", "pods", "-o", "json"])

    def test_kubectl_normal_context_uses_context_flag(self) -> None:
        """When context is a kubeconfig name, kubectl should use --context."""
        with patch("k8s_diag_agent.collect.live_snapshot._run_command") as run_command:
            run_command.return_value = '{"items": []}'
            _kubectl("my-cluster", "get", "pods", "-o", "json")
            run_command.assert_called_once_with(
                ["kubectl", "get", "pods", "-o", "json", "--context", "my-cluster"]
            )
