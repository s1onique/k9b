"""Tests for message sanitization and output format.

Covers: _sanitize_message, to_dict, evidence_needed format, deterministic IDs
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_candidates import (
    _sanitize_message,
    detect_incident_candidates,
)
from k8s_diag_agent.collect.incident_models import (
    PodHealthStatus,
    PodSummary,
)


def make_pod(
    name: str,
    namespace: str = "default",
    health_status: PodHealthStatus = PodHealthStatus.RUNNING,
    reason: str | None = None,
    message: str | None = None,
) -> PodSummary:
    """Helper to create test pod summaries."""
    return PodSummary(
        name=name,
        namespace=namespace,
        phase=health_status.value,
        health_status=health_status,
        restart_count=0,
        node="node-1",
        image_refs=("image:v1",),
        reason=reason,
        message=message,
        is_failing=health_status != PodHealthStatus.RUNNING,
    )


class TestMessageSanitization(unittest.TestCase):
    """Test message sanitization."""

    def test_long_message_truncated(self) -> None:
        """Long messages should be truncated to max_length."""
        long_message = "x" * 500
        result = _sanitize_message(long_message)
        self.assertLessEqual(len(result), 200)

    def test_token_pattern_redacted(self) -> None:
        """Bearer token pattern should be redacted."""
        message = "Using bearer token abc123xyz for authentication"
        result = _sanitize_message(message)
        self.assertNotIn("abc123xyz", result)
        self.assertIn("[REDACTED]", result)

    def test_jwt_pattern_redacted(self) -> None:
        """JWT tokens should be redacted."""
        message = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THs7Z8"
        result = _sanitize_message(message)
        self.assertNotIn("eyJ", result)
        self.assertIn("[REDACTED]", result)

    def test_whitespace_normalized(self) -> None:
        """Excessive whitespace should be normalized."""
        message = "Error    occurred   with   multiple   spaces"
        result = _sanitize_message(message)
        self.assertNotIn("  ", result)  # No double spaces

    def test_none_message_returns_empty(self) -> None:
        """None message should return empty string."""
        result = _sanitize_message(None)
        self.assertEqual(result, "")



class TestToDictOutput(unittest.TestCase):
    """Test the to_dict output format."""

    def test_to_dict_includes_all_required_fields(self) -> None:
        """to_dict output should match required schema."""
        pod = make_pod(
            name="test-pod",
            namespace="k9b",
            health_status=PodHealthStatus.CRASH_LOOP,
            reason="CrashLoopBackOff",
            message="Back-off message",
        )
        candidates = detect_incident_candidates([pod], [], [])
        result = candidates[0].to_dict()

        self.assertIn("candidate_id", result)
        self.assertIn("namespace", result)
        self.assertIn("object_kind", result)
        self.assertIn("object_name", result)
        self.assertIn("class", result)
        self.assertIn("severity", result)
        self.assertIn("signals", result)
        self.assertIn("evidence_needed", result)

        self.assertEqual(result["class"], "crash_loop")
        self.assertEqual(result["severity"], "error")
        self.assertIsInstance(result["signals"], list)
        self.assertIsInstance(result["evidence_needed"], list)

    def test_to_dict_signal_format(self) -> None:
        """Signal format should match required schema."""
        pod = make_pod(
            name="test-pod",
            health_status=PodHealthStatus.IMAGE_PULL_ERROR,
            reason="ImagePullBackOff",
            message="failed to pull image",
        )
        candidates = detect_incident_candidates([pod], [], [])
        signal = candidates[0].to_dict()["signals"][0]

        self.assertIn("source", signal)
        self.assertIn("reason", signal)
        self.assertIn("message", signal)


class TestEvidenceNeededFormat(unittest.TestCase):
    """Test that evidence_needed uses generic types, not kubectl commands."""

    def test_no_kubectl_wording_in_evidence_needed(self) -> None:
        """Evidence needed should not contain kubectl command wording."""
        pod = make_pod(
            name="crashloop-pod",
            health_status=PodHealthStatus.CRASH_LOOP,
        )
        candidates = detect_incident_candidates([pod], [], [])

        self.assertEqual(len(candidates), 1)
        evidence_needed = candidates[0].evidence_needed

        for item in evidence_needed:
            # Evidence types should not look like kubectl commands
            self.assertNotIn("kubectl", item.lower())
            self.assertFalse(
                item.startswith("get ") or item.startswith("describe "),
                f"Evidence needed item '{item}' looks like a kubectl verb",
            )
            self.assertFalse(
                item.startswith("-") or " -" in item,
                f"Evidence needed item '{item}' looks like a kubectl flag",
            )

    def test_evidence_needed_is_generic(self) -> None:
        """Evidence needed should use generic evidence types."""
        pod = make_pod(
            name="crashloop-pod",
            health_status=PodHealthStatus.CRASH_LOOP,
        )
        candidates = detect_incident_candidates([pod], [], [])

        evidence_needed = list(candidates[0].evidence_needed)
        # Should be things like "pod_logs", "pod_describe" not "kubectl logs pod-name"
        for item in evidence_needed:
            self.assertTrue(
                item.islower(),
                f"Evidence needed item '{item}' should be lowercase",
            )
            self.assertFalse(
                item.startswith("-"),
                f"Evidence needed item '{item}' should not be a flag",
            )


class TestDeterministicCandidateIds(unittest.TestCase):
    """Test that candidate IDs are deterministic."""

    def test_candidate_ids_deterministic_across_calls(self) -> None:
        """Same input should always produce same candidate IDs."""
        pod = make_pod(
            name="test-pod",
            namespace="prod",
            health_status=PodHealthStatus.CRASH_LOOP,
        )

        result1 = detect_incident_candidates([pod], [], [])
        result2 = detect_incident_candidates([pod], [], [])
        result3 = detect_incident_candidates([pod], [], [])

        self.assertEqual(result1[0].candidate_id, result2[0].candidate_id)
        self.assertEqual(result2[0].candidate_id, result3[0].candidate_id)

    def test_candidate_ids_sorted(self) -> None:
        """Candidates should be returned sorted by candidate_id."""
        pod1 = make_pod(name="zebra", namespace="default", health_status=PodHealthStatus.CRASH_LOOP)
        pod2 = make_pod(name="apple", namespace="default", health_status=PodHealthStatus.CRASH_LOOP)

        candidates = detect_incident_candidates([pod1, pod2], [], [])

        ids = [c.candidate_id for c in candidates]
        self.assertEqual(ids, sorted(ids))


class TestEmptyInputs(unittest.TestCase):
    """Test handling of empty inputs."""

    def test_empty_pods_deployments_events(self) -> None:
        """Empty inputs should return empty candidates."""
        candidates = detect_incident_candidates([], [], [])
        self.assertEqual(len(candidates), 0)


if __name__ == "__main__":
    unittest.main()
