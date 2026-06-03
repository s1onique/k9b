"""Core tests for ExecutionResultDigest class and builders.

Tests cover:
- ExecutionResultDigest class instantiation and properties
- build_execution_result_digest function
- build_execution_result_digests batch function
- review_input.build_execution_context function
"""

import unittest

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    UsefulnessClass,
)
from k8s_diag_agent.external_analysis.result_digest import (
    ExecutionResultDigest,
    build_execution_result_digest,
    build_execution_result_digests,
)
from k8s_diag_agent.external_analysis.review_input import (
    build_execution_context,
    execution_context_to_dict,
)


class TestExecutionResultDigestClass(unittest.TestCase):
    """Tests for ExecutionResultDigest dataclass."""

    def test_execution_result_digest_instantiation(self) -> None:
        """Test creating ExecutionResultDigest with all fields."""
        digest = ExecutionResultDigest(
            artifact_path="/path/to/execution.json",
            candidate_id="abc123",
            candidate_description="kubectl describe pod nginx",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context="default",
            summary="[useful] Pod running normally",
            signals=("CrashLoopBackOff", "OOMKilled"),
            stdout_truncated=False,
            stderr_truncated=False,
        )

        self.assertEqual(digest.artifact_path, "/path/to/execution.json")
        self.assertEqual(digest.candidate_id, "abc123")
        self.assertEqual(digest.candidate_description, "kubectl describe pod nginx")
        self.assertEqual(digest.status, "success")
        self.assertEqual(digest.usefulness_class, "useful")
        self.assertEqual(digest.target_cluster, "prod-cluster")
        self.assertEqual(digest.target_context, "default")
        self.assertEqual(digest.summary, "[useful] Pod running normally")
        self.assertEqual(digest.signals, ("CrashLoopBackOff", "OOMKilled"))
        self.assertFalse(digest.stdout_truncated)
        self.assertFalse(digest.stderr_truncated)

    def test_execution_result_digest_with_none_optional_fields(self) -> None:
        """Test creating ExecutionResultDigest with None optional fields."""
        digest = ExecutionResultDigest(
            artifact_path=None,
            candidate_id=None,
            candidate_description=None,
            status="failed",
            usefulness_class=None,
            target_cluster=None,
            target_context=None,
            summary=None,
            signals=(),
            stdout_truncated=None,
            stderr_truncated=None,
        )

        self.assertIsNone(digest.artifact_path)
        self.assertIsNone(digest.candidate_id)
        self.assertIsNone(digest.candidate_description)
        self.assertEqual(digest.status, "failed")
        self.assertIsNone(digest.usefulness_class)
        self.assertIsNone(digest.target_cluster)
        self.assertIsNone(digest.target_context)
        self.assertIsNone(digest.summary)
        self.assertEqual(digest.signals, ())
        self.assertIsNone(digest.stdout_truncated)
        self.assertIsNone(digest.stderr_truncated)

    def test_execution_result_digest_to_dict(self) -> None:
        """Test ExecutionResultDigest serialization."""
        digest = ExecutionResultDigest(
            artifact_path="/path/to/execution.json",
            candidate_id="abc123",
            candidate_description="kubectl describe pod nginx",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context=None,
            summary="[useful] OK",
            signals=("CrashLoopBackOff",),
            stdout_truncated=False,
            stderr_truncated=False,
        )

        result = digest.to_dict()

        self.assertEqual(result["artifactPath"], "/path/to/execution.json")
        self.assertEqual(result["candidateId"], "abc123")
        self.assertEqual(result["candidateDescription"], "kubectl describe pod nginx")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["usefulnessClass"], "useful")
        self.assertEqual(result["targetCluster"], "prod-cluster")
        self.assertIsNone(result["targetContext"])
        self.assertEqual(result["summary"], "[useful] OK")
        self.assertEqual(result["signals"], ["CrashLoopBackOff"])
        self.assertFalse(result["stdoutTruncated"])
        self.assertFalse(result["stderrTruncated"])

    def test_execution_result_digest_is_frozen(self) -> None:
        """Test that ExecutionResultDigest is frozen and immutable."""
        digest = ExecutionResultDigest(
            artifact_path="/path/to/execution.json",
            candidate_id="abc123",
            candidate_description="kubectl describe pod nginx",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context=None,
            summary="[useful] OK",
            signals=(),
            stdout_truncated=False,
            stderr_truncated=False,
        )

        with self.assertRaises(AttributeError):
            digest.status = "failed"  # type: ignore[misc]


class TestBuildExecutionResultDigest(unittest.TestCase):
    """Tests for build_execution_result_digest function."""

    def test_builds_digest_from_artifact(self) -> None:
        """Test building ExecutionResultDigest from artifact."""
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-executor",
            run_id="run-exec-test",
            cluster_label="test-cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            summary="Pod nginx is running",
            usefulness_class=UsefulnessClass.USEFUL,
            artifact_path="/runs/health/external-analysis/run-exec-test-next-check-execution-0.json",
        )

        digest = build_execution_result_digest(artifact)

        self.assertEqual(digest.artifact_path, artifact.artifact_path)
        self.assertEqual(digest.status, "success")
        self.assertEqual(digest.usefulness_class, "useful")
        self.assertEqual(digest.target_cluster, "test-cluster")
        self.assertIsNotNone(digest.summary)

    def test_extracts_command_from_payload(self) -> None:
        """Test that command is extracted from payload."""
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-executor",
            run_id="run-exec-command",
            cluster_label="prod-cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            payload={"command": "kubectl describe pod nginx-pod", "exitCode": 0},
        )

        digest = build_execution_result_digest(artifact)

        self.assertEqual(digest.candidate_description, "kubectl describe pod nginx-pod")

    def test_truncates_long_command(self) -> None:
        """Test that long commands are truncated."""
        long_command = "kubectl describe pod " + "x" * 250
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-executor",
            run_id="run-exec-long",
            cluster_label="prod-cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            payload={"command": long_command},
        )

        digest = build_execution_result_digest(artifact)

        self.assertIsNotNone(digest.candidate_description)
        self.assertLess(len(digest.candidate_description), len(long_command))
        self.assertTrue(digest.candidate_description.endswith("…"))

    def test_handles_failed_status(self) -> None:
        """Test that failed status is properly recorded."""
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-executor",
            run_id="run-exec-failed",
            cluster_label="prod-cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="pod not found",
        )

        digest = build_execution_result_digest(artifact)

        self.assertEqual(digest.status, "failed")

    def test_uses_provided_candidate_id(self) -> None:
        """Test that provided candidate_id is used."""
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-executor",
            run_id="run-exec-cid",
            cluster_label="prod-cluster",
            status=ExternalAnalysisStatus.SUCCESS,
        )

        digest = build_execution_result_digest(artifact, candidate_id="custom-candidate-id")

        self.assertEqual(digest.candidate_id, "custom-candidate-id")

    def test_uses_provided_description(self) -> None:
        """Test that provided candidate_description is used."""
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-executor",
            run_id="run-exec-desc",
            cluster_label="prod-cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            payload={"command": "kubectl get pods"},
        )

        digest = build_execution_result_digest(
            artifact, candidate_description="Custom description"
        )

        self.assertEqual(digest.candidate_description, "Custom description")


class TestBuildExecutionResultDigests(unittest.TestCase):
    """Tests for build_execution_result_digests batch function."""

    def test_builds_digests_from_multiple_artifacts(self) -> None:
        """Test building digests from multiple artifacts."""
        artifacts = [
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-batch",
                cluster_label="cluster-1",
                status=ExternalAnalysisStatus.SUCCESS,
                summary="First check OK",
            ),
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-batch",
                cluster_label="cluster-2",
                status=ExternalAnalysisStatus.FAILED,
                summary="Second check failed",
            ),
        ]

        digests = build_execution_result_digests(artifacts)

        self.assertEqual(len(digests), 2)
        self.assertEqual(digests[0].target_cluster, "cluster-1")
        self.assertEqual(digests[1].target_cluster, "cluster-2")
        self.assertEqual(digests[0].status, "success")
        self.assertEqual(digests[1].status, "failed")

    def test_uses_provided_candidate_ids(self) -> None:
        """Test that provided candidate_ids are matched."""
        artifacts = [
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-ids",
                cluster_label="cluster-1",
                status=ExternalAnalysisStatus.SUCCESS,
            ),
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-ids",
                cluster_label="cluster-2",
                status=ExternalAnalysisStatus.SUCCESS,
            ),
        ]

        digests = build_execution_result_digests(
            artifacts, candidate_ids=("id-1", "id-2")
        )

        self.assertEqual(digests[0].candidate_id, "id-1")
        self.assertEqual(digests[1].candidate_id, "id-2")

    def test_handles_empty_candidate_ids(self) -> None:
        """Test that missing candidate_ids are treated as None."""
        artifacts = [
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-no-ids",
                cluster_label="cluster-1",
                status=ExternalAnalysisStatus.SUCCESS,
            ),
        ]

        digests = build_execution_result_digests(artifacts)

        self.assertIsNone(digests[0].candidate_id)

    def test_empty_list_returns_empty_tuple(self) -> None:
        """Test that empty list returns empty tuple."""
        digests = build_execution_result_digests([])
        self.assertEqual(digests, ())


class TestBuildExecutionContext(unittest.TestCase):
    """Tests for build_execution_context function."""

    def test_filters_execution_artifacts_only(self) -> None:
        """Test that only NEXT_CHECK_EXECUTION artifacts are included."""
        artifacts = (
            ExternalAnalysisArtifact(
                tool_name="planner",
                run_id="run-filter",
                cluster_label="cluster",
                status=ExternalAnalysisStatus.SUCCESS,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            ),
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-filter",
                cluster_label="cluster",
                status=ExternalAnalysisStatus.SUCCESS,
                purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            ),
        )

        context = build_execution_context(artifacts)

        self.assertEqual(len(context), 1)

    def test_skips_pending_artifacts(self) -> None:
        """Test that pending artifacts are skipped."""
        artifacts = (
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-pending",
                cluster_label="cluster",
                status=ExternalAnalysisStatus.PENDING,
                purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            ),
        )

        context = build_execution_context(artifacts)

        self.assertEqual(len(context), 0)

    def test_skips_skipped_artifacts(self) -> None:
        """Test that skipped artifacts are skipped."""
        artifacts = (
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-skipped",
                cluster_label="cluster",
                status=ExternalAnalysisStatus.SKIPPED,
                purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            ),
        )

        context = build_execution_context(artifacts)

        self.assertEqual(len(context), 0)

    def test_includes_failed_artifacts(self) -> None:
        """Test that failed artifacts are included (they have useful error info)."""
        artifacts = (
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-failed",
                cluster_label="cluster",
                status=ExternalAnalysisStatus.FAILED,
                purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
                error_summary="connection refused",
            ),
        )

        context = build_execution_context(artifacts)

        self.assertEqual(len(context), 1)
        self.assertEqual(context[0].status, "failed")

    def test_empty_artifacts_returns_empty_tuple(self) -> None:
        """Test that empty/None artifacts returns empty tuple."""
        self.assertEqual(build_execution_context(None), ())
        self.assertEqual(build_execution_context(()), ())

    def test_multiple_execution_artifacts(self) -> None:
        """Test that multiple execution artifacts are all included."""
        artifacts = (
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-multi",
                cluster_label="cluster-1",
                status=ExternalAnalysisStatus.SUCCESS,
                purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
                summary="Check 1",
            ),
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-multi",
                cluster_label="cluster-2",
                status=ExternalAnalysisStatus.SUCCESS,
                purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
                summary="Check 2",
            ),
            ExternalAnalysisArtifact(
                tool_name="executor",
                run_id="run-multi",
                cluster_label="cluster-3",
                status=ExternalAnalysisStatus.FAILED,
                purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
                summary="Check 3",
            ),
        )

        context = build_execution_context(artifacts)

        self.assertEqual(len(context), 3)


class TestExecutionContextToDict(unittest.TestCase):
    """Tests for execution_context_to_dict function."""

    def test_converts_digests_to_serializable_list(self) -> None:
        """Test that digests are converted to list of dicts."""
        digest = ExecutionResultDigest(
            artifact_path="/path/to/execution.json",
            candidate_id="abc123",
            candidate_description="kubectl describe pod nginx",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context=None,
            summary="[useful] OK",
            signals=("CrashLoopBackOff",),
            stdout_truncated=False,
            stderr_truncated=False,
        )

        result = execution_context_to_dict((digest,))

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["artifactPath"], "/path/to/execution.json")

    def test_empty_digests_returns_empty_list(self) -> None:
        """Test that empty digests returns empty list."""
        result = execution_context_to_dict(())
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()