"""Tests for external analysis failure artifact metadata."""

import unittest
from typing import cast

from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus


class TestFailureMetadataRoundtrip(unittest.TestCase):
    """Test that failure_metadata is preserved in serialization/deserialization."""

    def test_failure_metadata_in_to_dict(self) -> None:
        """Test that failure_metadata appears in to_dict output."""
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="run-123",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="Read timed out after 120 seconds",
            failure_metadata={
                "failure_class": "llm_client_read_timeout",
                "exception_type": "ReadTimeout",
                "timeout_seconds": 120,
                "elapsed_ms": 120034,
                "endpoint": "http://192.168.99.134:32597/v1/chat/completions",
                "summary": "Read timed out",
            },
        )
        data = artifact.to_dict()
        self.assertIn("failure_metadata", data)
        failure_metadata = cast(dict[str, object], data["failure_metadata"])
        self.assertEqual(failure_metadata["failure_class"], "llm_client_read_timeout")
        self.assertEqual(failure_metadata["exception_type"], "ReadTimeout")

    def test_failure_metadata_roundtrip(self) -> None:
        """Test that failure_metadata survives round-trip."""
        original = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="run-456",
            cluster_label="cluster-b",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="Connection timeout",
            failure_metadata={
                "failure_class": "llm_client_connect_timeout",
                "exception_type": "ConnectTimeout",
                "timeout_seconds": 120,
                "elapsed_ms": 5001,
                "endpoint": "http://example.com/v1/chat/completions",
                "summary": "Connect timeout",
            },
        )
        data = original.to_dict()
        loaded = ExternalAnalysisArtifact.from_dict(data)
        self.assertIsNotNone(loaded.failure_metadata)
        loaded_metadata = cast(dict[str, object], loaded.failure_metadata)
        self.assertEqual(loaded_metadata["failure_class"], "llm_client_connect_timeout")
        self.assertEqual(loaded_metadata["exception_type"], "ConnectTimeout")

    def test_failure_metadata_none_for_success(self) -> None:
        """Test that success artifacts have no failure_metadata."""
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="run-789",
            cluster_label="cluster-c",
            status=ExternalAnalysisStatus.SUCCESS,
            summary="Enrichment completed",
        )
        data = artifact.to_dict()
        self.assertNotIn("failure_metadata", data)

    def test_failure_metadata_none_when_not_set(self) -> None:
        """Test that from_dict handles missing failure_metadata."""
        raw = {
            "tool_name": "llamacpp",
            "run_id": "run-old",
            "cluster_label": "cluster-x",
            "status": "failed",
            "error_summary": "Some error",
            # No failure_metadata field
        }
        loaded = ExternalAnalysisArtifact.from_dict(raw)
        self.assertIsNone(loaded.failure_metadata)


class TestFailureMetadataStructure(unittest.TestCase):
    """Test the structure of failure metadata."""

    def test_minimal_failure_metadata(self) -> None:
        """Test artifact with minimal failure metadata."""
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="run-min",
            cluster_label="cluster-y",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="Unknown error",
            failure_metadata={
                "failure_class": "llm_adapter_error",
                "exception_type": "RuntimeError",
            },
        )
        data = artifact.to_dict()
        failure_metadata = cast(dict[str, object], data["failure_metadata"])
        self.assertEqual(failure_metadata["failure_class"], "llm_adapter_error")

    def test_complete_failure_metadata(self) -> None:
        """Test artifact with complete failure metadata."""
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="run-full",
            cluster_label="cluster-z",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="HTTP 500 error",
            failure_metadata={
                "failure_class": "llm_server_http_error",
                "exception_type": "HTTPError",
                "timeout_seconds": 120,
                "elapsed_ms": 125000,
                "endpoint": "http://192.168.99.134:32597/v1/chat/completions",
                "summary": "HTTP 500: Internal Server Error",
            },
        )
        data = artifact.to_dict()
        failure_metadata = cast(dict[str, object], data["failure_metadata"])
        self.assertEqual(failure_metadata["failure_class"], "llm_server_http_error")
        self.assertEqual(failure_metadata["exception_type"], "HTTPError")
        self.assertEqual(failure_metadata["timeout_seconds"], 120)
        self.assertEqual(failure_metadata["elapsed_ms"], 125000)
        endpoint = cast(str, failure_metadata["endpoint"])
        self.assertIn("/v1/chat/completions", endpoint)


if __name__ == "__main__":
    unittest.main()