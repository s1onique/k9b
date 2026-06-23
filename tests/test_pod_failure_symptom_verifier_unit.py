"""Unit tests for pod failure symptom verifier helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import unittest

from verify_pod_failure_impl import (
    SymptomClass,
    SymptomVerificationResult,
    check_container_waiting_reason,
    check_readiness_probe_failure,
    check_success_condition,
    classify_fatal_state,
    is_intermediate_state,
)


class TestCheckContainerWaitingReason(unittest.TestCase):
    """Tests for check_container_waiting_reason."""

    def test_container_creating(self) -> None:
        pod_status: dict = {"status": {"containerStatuses": [{"state": {"waiting": {"reason": "ContainerCreating", "message": "container creating"}}, "ready": False}]}}
        reason, message = check_container_waiting_reason(pod_status)
        self.assertEqual(reason, "ContainerCreating")
        self.assertEqual(message, "container creating")

    def test_no_containers(self) -> None:
        pod_status: dict = {"status": {"containerStatuses": []}}
        reason, message = check_container_waiting_reason(pod_status)
        self.assertEqual(reason, "")

    def test_no_container_statuses(self) -> None:
        pod_status: dict = {"status": {}}
        reason, message = check_container_waiting_reason(pod_status)
        self.assertEqual(reason, "")

    def test_image_pull_backoff(self) -> None:
        pod_status: dict = {"status": {"containerStatuses": [{"state": {"waiting": {"reason": "ImagePullBackOff", "message": "backoff"}}, "ready": False}]}}
        reason, message = check_container_waiting_reason(pod_status)
        self.assertEqual(reason, "ImagePullBackOff")

    def test_err_image_pull(self) -> None:
        pod_status: dict = {"status": {"containerStatuses": [{"state": {"waiting": {"reason": "ErrImagePull", "message": "pull error"}}, "ready": False}]}}
        reason, message = check_container_waiting_reason(pod_status)
        self.assertEqual(reason, "ErrImagePull")


class TestCheckReadinessProbeFailure(unittest.TestCase):
    """Tests for check_readiness_probe_failure."""

    def test_running_not_ready(self) -> None:
        pod_status = {"status": {"phase": "Running", "containerStatuses": [{"ready": False}]}}
        result = check_readiness_probe_failure(pod_status, "")
        self.assertTrue(result)

    def test_running_ready(self) -> None:
        pod_status = {"status": {"phase": "Running", "containerStatuses": [{"ready": True}]}}
        result = check_readiness_probe_failure(pod_status, "")
        self.assertFalse(result)

    def test_exec_false_in_describe(self) -> None:
        pod_status = {"status": {"phase": "Running"}}
        describe = " Readiness:      exec /bin/false delay=1s timeout=1s period=5s #success=1 failure=1"
        result = check_readiness_probe_failure(pod_status, describe)
        self.assertTrue(result)

    def test_running_no_container_statuses(self) -> None:
        pod_status = {"status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "False"}]}}
        result = check_readiness_probe_failure(pod_status, "")
        self.assertTrue(result)


class TestClassifyFatalState(unittest.TestCase):
    """Tests for classify_fatal_state."""

    def test_image_pull_backoff_is_fatal(self) -> None:
        pod_status = {"status": {"phase": "Pending", "containerStatuses": [{"state": {"waiting": {"reason": "ImagePullBackOff"}}}]}}
        is_fatal, symptom_class, reason = classify_fatal_state(pod_status, "", [])
        self.assertTrue(is_fatal)
        self.assertEqual(symptom_class, SymptomClass.IMAGE_PULL_BACKOFF)

    def test_err_image_pull_is_fatal(self) -> None:
        pod_status = {"status": {"phase": "Pending", "containerStatuses": [{"state": {"waiting": {"reason": "ErrImagePull"}}}]}}
        is_fatal, symptom_class, reason = classify_fatal_state(pod_status, "", [])
        self.assertTrue(is_fatal)
        self.assertEqual(symptom_class, SymptomClass.IMAGE_PULL_BACKOFF)

    def test_failed_scheduling_is_fatal(self) -> None:
        pod_status = {"status": {"phase": "Pending"}}
        events = [{"reason": "FailedScheduling", "message": "0/1 nodes"}]
        is_fatal, symptom_class, reason = classify_fatal_state(pod_status, "", events)
        self.assertTrue(is_fatal)
        self.assertEqual(symptom_class, SymptomClass.SCHEDULING_FAILED)

    def test_create_container_config_error_is_fatal(self) -> None:
        pod_status = {"status": {"phase": "Pending", "containerStatuses": [{"state": {"waiting": {"reason": "CreateContainerConfigError"}}}]}}
        is_fatal, symptom_class, reason = classify_fatal_state(pod_status, "", [])
        self.assertTrue(is_fatal)
        self.assertEqual(symptom_class, SymptomClass.CREATE_CONTAINER_CONFIG_ERROR)

    def test_container_creating_is_not_fatal(self) -> None:
        pod_status = {"status": {"phase": "Pending", "containerStatuses": [{"state": {"waiting": {"reason": "ContainerCreating"}}}]}}
        is_fatal, symptom_class, reason = classify_fatal_state(pod_status, "", [])
        self.assertFalse(is_fatal)

    def test_pulling_is_not_fatal(self) -> None:
        pod_status = {"status": {"phase": "Pending", "containerStatuses": [{"state": {"waiting": {"reason": "PodInitializing"}}}]}}
        is_fatal, symptom_class, reason = classify_fatal_state(pod_status, "Pulling image", [])
        self.assertFalse(is_fatal)


class TestIsIntermediateState(unittest.TestCase):
    """Tests for is_intermediate_state."""

    def test_pending_is_intermediate(self) -> None:
        pod_status = {"status": {"phase": "Pending"}}
        is_intermediate, event = is_intermediate_state(pod_status, "")
        self.assertTrue(is_intermediate)

    def test_container_creating_is_intermediate(self) -> None:
        pod_status = {"status": {"phase": "Pending", "containerStatuses": [{"state": {"waiting": {"reason": "ContainerCreating"}}}]}}
        is_intermediate, event = is_intermediate_state(pod_status, "")
        self.assertTrue(is_intermediate)
        self.assertEqual(event, "ContainerCreating")

    def test_running_is_not_intermediate(self) -> None:
        pod_status = {"status": {"phase": "Running"}}
        is_intermediate, event = is_intermediate_state(pod_status, "")
        self.assertFalse(is_intermediate)


class TestCheckSuccessCondition(unittest.TestCase):
    """Tests for check_success_condition."""

    def test_running_ready_false_is_success(self) -> None:
        pod_status = {"status": {"phase": "Running", "containerStatuses": [{"ready": False}]}}
        describe = " Readiness: exec /bin/false"
        result = check_success_condition(pod_status, describe)
        self.assertTrue(result)

    def test_running_ready_true_is_not_success(self) -> None:
        pod_status = {"status": {"phase": "Running", "containerStatuses": [{"ready": True}]}}
        result = check_success_condition(pod_status, "")
        self.assertFalse(result)

    def test_running_unknown_ready_may_be_success(self) -> None:
        pod_status = {"status": {"phase": "Running", "containerStatuses": [{"ready": False, "started": None}]}}
        result = check_success_condition(pod_status, "")
        self.assertTrue(result)


class TestSymptomVerificationResult(unittest.TestCase):
    """Tests for SymptomVerificationResult dataclass."""

    def test_to_dict_includes_all_fields(self) -> None:
        result = SymptomVerificationResult(
            symptom_class=SymptomClass.OBSERVED,
            fatal=False,
            pod_phase="Running",
            pod_ready="False",
            container_state="Running",
            container_waiting_reason="",
            latest_event="",
            readiness_probe_failure_evidence=True,
            failure_reason="",
            elapsed_seconds=10.0,
            poll_count=5,
        )
        d = result.to_dict()
        self.assertIn("symptom_class", d)
        self.assertIn("fatal", d)
        self.assertIn("elapsed_seconds", d)

    def test_symptom_classes(self) -> None:
        expected_classes = ["OBSERVED", "TIMEOUT", "IMAGE_PULL_BACKOFF", "SCHEDULING_FAILED", "CREATE_CONTAINER_CONFIG_ERROR"]
        for cls_name in expected_classes:
            self.assertTrue(hasattr(SymptomClass, cls_name))


if __name__ == "__main__":
    unittest.main()
