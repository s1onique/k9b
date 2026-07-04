"""Integration tests for verify_pod_failure_symptom with mocked kubectl."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from verify_pod_failure_impl import (
    SymptomClass,
    verify_pod_failure_symptom,
)


class TestVerifyPodFailureSymptomIntegration(unittest.TestCase):
    """Integration tests for verify_pod_failure_symptom with mocked kubectl."""

    def _make_pod_status(
        self,
        phase: str = "Pending",
        reason: str = "",
        message: str = "",
        ready: str = "Unknown",
    ) -> dict:
        """Helper to create pod status dict."""
        status: dict = {"status": {"phase": phase}}
        if reason:
            status["status"]["containerStatuses"] = [
                {"state": {"waiting": {"reason": reason, "message": message}}, "ready": ready != "True"}
            ]
        return status

    @patch("verify_pod_failure_impl.run_kubectl")
    @patch("verify_pod_failure_impl.time.sleep")
    def test_pod_not_found_returns_timeout(
        self, mock_sleep: MagicMock, mock_kubectl: MagicMock
    ) -> None:
        """Should return timeout when pod not found."""
        # Always return failure (pod not found)
        mock_kubectl.return_value = (1, "", "not found")
        # Make sleep instant
        mock_sleep.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            result = verify_pod_failure_symptom(
                kubeconfig="/tmp/kubeconfig",
                namespace="test-ns",
                pod_name="test-pod",
                deadline=10,
                poll_interval=1,
                artifact_dir=Path(tmpdir),
                wait_timeout=1,  # Fast timeout instead of 60s
            )

        self.assertEqual(result.symptom_class, SymptomClass.TIMEOUT)
        self.assertTrue(result.fatal)
        self.assertEqual(result.pod_phase, "NotFound")

    @patch("verify_pod_failure_impl.run_kubectl")
    @patch("verify_pod_failure_impl.time.sleep")
    def test_pending_container_creating_keeps_polling(
        self, mock_sleep: MagicMock, mock_kubectl: MagicMock
    ) -> None:
        """Should continue polling during Pending/ContainerCreating."""
        # Make sleep instant to avoid slow polling
        mock_sleep.return_value = None

        call_count = 0

        def kubectl_side_effect(*args: str, **kwargs: int) -> tuple[int, str, str]:
            nonlocal call_count
            call_count += 1
            # First few calls return Pending/ContainerCreating
            if "get" in args[2] and "pod" in args[2]:
                if call_count < 3:
                    pod_status = {
                        "status": {
                            "phase": "Pending",
                            "containerStatuses": [
                                {"state": {"waiting": {"reason": "ContainerCreating"}}}
                            ],
                        }
                    }
                    return (0, json.dumps(pod_status), "")
                # Then return Running/NotReady
                pod_status = {
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{"ready": False}],
                    }
                }
                return (0, json.dumps(pod_status), "")
            if "describe" in args[2]:
                return (0, "Readiness: exec /bin/false", "")
            if "events" in args[2]:
                return (0, json.dumps({"items": []}), "")
            return (0, "{}", "")

        mock_kubectl.side_effect = kubectl_side_effect

        with tempfile.TemporaryDirectory() as tmpdir:
            result = verify_pod_failure_symptom(
                kubeconfig="/tmp/kubeconfig",
                namespace="test-ns",
                pod_name="test-pod",
                deadline=15,
                poll_interval=1,
                artifact_dir=Path(tmpdir),
            )

        # Should eventually succeed when pod becomes Running
        self.assertEqual(result.symptom_class, SymptomClass.OBSERVED)
        self.assertFalse(result.fatal)
        self.assertEqual(result.pod_phase, "Running")

    @patch("verify_pod_failure_impl.run_kubectl")
    @patch("verify_pod_failure_impl.time.sleep")
    def test_image_pull_backoff_is_fatal(
        self, mock_sleep: MagicMock, mock_kubectl: MagicMock
    ) -> None:
        """Should return fatal result for ImagePullBackOff."""
        # Make sleep instant
        mock_sleep.return_value = None

        call_count = 0

        def kubectl_side_effect(*args: str, **kwargs: int) -> tuple[int, str, str]:
            nonlocal call_count
            call_count += 1
            if "get" in args[2] and "pod" in args[2]:
                pod_status = {
                    "status": {
                        "phase": "Pending",
                        "containerStatuses": [
                            {"state": {"waiting": {"reason": "ImagePullBackOff", "message": "backoff"}}}
                        ],
                    }
                }
                return (0, json.dumps(pod_status), "")
            if "describe" in args[2]:
                return (0, "ImagePullBackOff: failed to pull image", "")
            if "events" in args[2]:
                return (0, json.dumps({"items": []}), "")
            return (0, "{}", "")

        mock_kubectl.side_effect = kubectl_side_effect

        with tempfile.TemporaryDirectory() as tmpdir:
            result = verify_pod_failure_symptom(
                kubeconfig="/tmp/kubeconfig",
                namespace="test-ns",
                pod_name="test-pod",
                deadline=30,
                poll_interval=5,
                artifact_dir=Path(tmpdir),
            )

        self.assertEqual(result.symptom_class, SymptomClass.IMAGE_PULL_BACKOFF)
        self.assertTrue(result.fatal)

    @patch("verify_pod_failure_impl.run_kubectl")
    @patch("verify_pod_failure_impl.time.sleep")
    def test_timeout_returns_timeout_class(
        self, mock_sleep: MagicMock, mock_kubectl: MagicMock
    ) -> None:
        """Should return TIMEOUT when deadline exceeded."""
        call_count = 0

        def kubectl_side_effect(*args: str, **kwargs: int) -> tuple[int, str, str]:
            nonlocal call_count
            call_count += 1
            if "get" in args[2] and "pod" in args[2]:
                # Always return Pending/ContainerCreating
                pod_status = {
                    "status": {
                        "phase": "Pending",
                        "containerStatuses": [
                            {"state": {"waiting": {"reason": "ContainerCreating"}}}
                        ],
                    }
                }
                return (0, json.dumps(pod_status), "")
            if "describe" in args[2]:
                return (0, "ContainerCreating", "")
            if "events" in args[2]:
                return (0, json.dumps({"items": []}), "")
            return (0, "{}", "")

        mock_kubectl.side_effect = kubectl_side_effect
        # Make sleep very fast to speed up test
        mock_sleep.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            result = verify_pod_failure_symptom(
                kubeconfig="/tmp/kubeconfig",
                namespace="test-ns",
                pod_name="test-pod",
                deadline=2,  # Very short deadline
                poll_interval=0.1,
                artifact_dir=Path(tmpdir),
            )

        # Should eventually timeout
        self.assertEqual(result.symptom_class, SymptomClass.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
