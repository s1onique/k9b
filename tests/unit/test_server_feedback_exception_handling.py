"""Tests for server_feedback.py exception handling security hardening.

Tests cover:
- Malformed JSON returns 400
- Artifact read errors return 500 with safe logging
- Artifact write errors return 500 with safe logging
- UI index touch failures are non-fatal
- Logs exclude raw feedback content
"""

import json
import shutil
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.ui.server_feedback import (
    handle_alertmanager_relevance_feedback,
    handle_usefulness_feedback,
)


class MockHealthUIRequestHandler:
    """Minimal mock handler for testing feedback functions."""

    def __init__(self, tmpdir: Path) -> None:
        self._tmpdir = tmpdir.resolve()
        self.runs_dir = (tmpdir / "runs").resolve()
        self._health_root = tmpdir.resolve()
        self.headers: dict[str, str] = {}
        self.rfile = BytesIO()
        self._sent_json: list[tuple[dict, int]] = []

    def _send_json(self, data: dict, status: int = 200) -> None:
        self._sent_json.append((data, status))

    @property
    def sent_response(self) -> tuple[dict, int] | None:
        return self._sent_json[-1] if self._sent_json else None

    @property
    def all_responses(self) -> list[tuple[dict, int]]:
        return self._sent_json.copy()


class TestUsefulnessFeedbackMalformedPayload(unittest.TestCase):
    """Tests for malformed request handling in usefulness feedback."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.handler = MockHealthUIRequestHandler(self.tmpdir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_invalid_json_returns_400(self) -> None:
        """Malformed JSON should return 400."""
        self.handler.headers["Content-Length"] = str(len(b"not valid json"))
        self.handler.rfile = BytesIO(b"not valid json")
        handle_usefulness_feedback(self.handler)
        response, status = self.handler.sent_response
        self.assertEqual(status, 400)
        self.assertIn("error", response)

    def test_invalid_utf8_returns_400(self) -> None:
        """Invalid UTF-8 bytes should return 400."""
        invalid_utf8 = b"\xff\xfe invalid json"
        self.handler.headers["Content-Length"] = str(len(invalid_utf8))
        self.handler.rfile = BytesIO(invalid_utf8)
        handle_usefulness_feedback(self.handler)
        response, status = self.handler.sent_response
        self.assertEqual(status, 400)

    def test_non_dict_json_returns_400(self) -> None:
        """Non-dict JSON should return 400."""
        self.handler.headers["Content-Length"] = str(len(b'"just a string"'))
        self.handler.rfile = BytesIO(b'"just a string"')
        handle_usefulness_feedback(self.handler)
        response, status = self.handler.sent_response
        self.assertEqual(status, 400)


class TestAlertmanagerFeedbackMalformedPayload(unittest.TestCase):
    """Tests for malformed request handling in alertmanager relevance feedback."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.handler = MockHealthUIRequestHandler(self.tmpdir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_invalid_json_returns_400(self) -> None:
        """Malformed JSON should return 400."""
        self.handler.headers["Content-Length"] = str(len(b"not valid json"))
        self.handler.rfile = BytesIO(b"not valid json")
        handle_alertmanager_relevance_feedback(self.handler)
        response, status = self.handler.sent_response
        self.assertEqual(status, 400)
        self.assertIn("error", response)

    def test_invalid_utf8_returns_400(self) -> None:
        """Invalid UTF-8 bytes should return 400."""
        invalid_utf8 = b"\xff\xfe invalid json"
        self.handler.headers["Content-Length"] = str(len(invalid_utf8))
        self.handler.rfile = BytesIO(invalid_utf8)
        handle_alertmanager_relevance_feedback(self.handler)
        response, status = self.handler.sent_response
        self.assertEqual(status, 400)

    def test_non_dict_json_returns_400(self) -> None:
        """Non-dict JSON should return 400."""
        self.handler.headers["Content-Length"] = str(len(b'"just a string"'))
        self.handler.rfile = BytesIO(b'"just a string"')
        handle_alertmanager_relevance_feedback(self.handler)
        response, status = self.handler.sent_response
        self.assertEqual(status, 400)


class TestArtifactReadErrors(unittest.TestCase):
    """Tests for artifact read error handling."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.handler = MockHealthUIRequestHandler(self.tmpdir)
        # Set up directory structure
        self.runs_dir = self.tmpdir / "runs"
        self.runs_dir.mkdir(parents=True)
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True)
        self.handler.runs_dir = self.runs_dir
        self.handler._health_root = self.tmpdir

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_execution_artifact(self, content: str) -> Path:
        """Create a mock execution artifact."""
        artifact_path = self.external_dir / "test-execution.json"
        artifact_path.write_text(content, encoding="utf-8")
        return artifact_path

    def test_malformed_artifact_json_returns_500(self) -> None:
        """Malformed artifact JSON should return 500."""
        artifact_path = self._create_execution_artifact("{ invalid json }")
        # Path must be relative to runs_dir
        rel_path = str(artifact_path.relative_to(self.runs_dir))

        payload = json.dumps({
            "artifactPath": rel_path,
            "usefulnessClass": "useful",
        })

        self.handler.headers["Content-Length"] = str(len(payload))
        self.handler.rfile = BytesIO(payload.encode("utf-8"))

        # Mock the logger to capture log calls
        with patch("k8s_diag_agent.ui.server_feedback.logger") as mock_logger:
            handle_usefulness_feedback(self.handler)

        response, status = self.handler.sent_response
        self.assertEqual(status, 500)
        self.assertIn("error", response)
        # Error should NOT include raw exception details
        self.assertNotIn("Expecting", response["error"])
        self.assertNotIn("invalid", response["error"].lower())

        # Logger should have been called with error
        mock_logger.error.assert_called()
        call_args = mock_logger.error.call_args
        self.assertIn("Unable to read execution artifact", call_args[0][0])

    def test_corrupted_artifact_returns_500_with_safe_log(self) -> None:
        """Corrupted artifact should return 500 with safe log metadata."""
        artifact_path = self._create_execution_artifact("corrupted content {{{")
        # Path must be relative to runs_dir
        rel_path = str(artifact_path.relative_to(self.runs_dir))

        payload = json.dumps({
            "artifactPath": rel_path,
            "usefulnessClass": "useful",
        })

        self.handler.headers["Content-Length"] = str(len(payload))
        self.handler.rfile = BytesIO(payload.encode("utf-8"))

        with patch("k8s_diag_agent.ui.server_feedback.logger") as mock_logger:
            handle_usefulness_feedback(self.handler)

        response, status = self.handler.sent_response
        self.assertEqual(status, 500)

        # Logger should have safe metadata (relative paths, no absolute)
        mock_logger.error.assert_called()
        call_args = mock_logger.error.call_args
        _log_msg = call_args[0][0]
        extra = call_args[1]["extra"]
        self.assertIn("artifact_rel", extra)
        self.assertIn("run_id", extra)
        self.assertIn("error", extra)
        # Verify no absolute path leaks
        for value in extra.values():
            if isinstance(value, str):
                self.assertNotIn(str(self.tmpdir), value)


class TestArtifactWriteErrors(unittest.TestCase):
    """Tests for artifact write error handling."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
        self.handler = MockHealthUIRequestHandler(self.tmpdir)
        # Set up directory structure (use resolved paths)
        self.runs_dir = self.tmpdir / "runs"
        self.runs_dir.mkdir(parents=True)
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True)
        self.handler.runs_dir = self.runs_dir
        self.handler._health_root = self.tmpdir

        # Create valid execution artifact
        self.artifact_path = self.external_dir / "test-execution.json"
        execution_artifact = {
            "purpose": "next-check-execution",
            "run_id": "test-run",
            "cluster_label": "test-cluster",
            "status": "success",
        }
        self.artifact_path.write_text(json.dumps(execution_artifact), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @unittest.skip(
        "macOS enforces chmod restrictions inconsistently for non-root users"
    )
    def test_write_to_readonly_dir_returns_500(self) -> None:
        """Writing to read-only directory should return 500 with safe log.
        
        Note: This test requires non-root privileges to enforce chmod.
        """
        rel_path = str(self.artifact_path.relative_to(self.runs_dir))

        payload = json.dumps({
            "artifactPath": rel_path,
            "usefulnessClass": "useful",
        })

        self.handler.headers["Content-Length"] = str(len(payload))
        self.handler.rfile = BytesIO(payload.encode("utf-8"))

        # Make directory read-only
        external_analysis_dir = self.health_dir / "external-analysis"
        external_analysis_dir.chmod(0o555)

        try:
            with patch("k8s_diag_agent.ui.server_feedback.logger") as mock_logger:
                handle_usefulness_feedback(self.handler)

            response, status = self.handler.sent_response
            self.assertEqual(status, 500)
            self.assertIn("error", response)

            # Logger should have safe metadata (relative paths, no absolute)
            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            extra = call_args[1]["extra"]
            self.assertIn("review_filename", extra)
            self.assertIn("source_artifact_rel", extra)
            # Verify no absolute path leaks
            for value in extra.values():
                if isinstance(value, str):
                    self.assertNotIn(str(self.tmpdir), value)
        finally:
            external_analysis_dir.chmod(0o755)


class TestUIIndexTouchNonFatal(unittest.TestCase):
    """Tests for UI index touch failure handling (should be non-fatal)."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
        self.handler = MockHealthUIRequestHandler(self.tmpdir)
        # Set up directory structure (use resolved paths)
        self.runs_dir = self.tmpdir / "runs"
        self.runs_dir.mkdir(parents=True)
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True)
        self.handler.runs_dir = self.runs_dir
        self.handler._health_root = self.tmpdir

        # Create valid execution artifact
        self.artifact_path = self.external_dir / "test-execution.json"
        execution_artifact = {
            "purpose": "next-check-execution",
            "run_id": "test-run",
            "cluster_label": "test-cluster",
            "status": "success",
        }
        self.artifact_path.write_text(json.dumps(execution_artifact), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ui_index_touch_failure_is_non_fatal(self) -> None:
        """UI index touch failure should not prevent success response."""
        rel_path = str(self.artifact_path.relative_to(self.runs_dir))

        payload = json.dumps({
            "artifactPath": rel_path,
            "usefulnessClass": "useful",
            "usefulnessSummary": "Test summary",
        })

        self.handler.headers["Content-Length"] = str(len(payload))
        self.handler.rfile = BytesIO(payload.encode("utf-8"))

        # Create ui-index.json and make it read-only
        ui_index_path = self.health_dir / "ui-index.json"
        ui_index_path.write_text("{}", encoding="utf-8")
        ui_index_path.chmod(0o444)  # Read-only

        try:
            handle_usefulness_feedback(self.handler)
            response, status = self.handler.sent_response
            # Should still succeed even if touch fails
            self.assertEqual(status, 200)
            self.assertEqual(response["status"], "success")
        finally:
            ui_index_path.chmod(0o644)


class TestLogSecurity(unittest.TestCase):
    """Tests for log security - raw feedback content should not be logged."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
        self.handler = MockHealthUIRequestHandler(self.tmpdir)
        # Set up directory structure (use resolved paths)
        self.runs_dir = self.tmpdir / "runs"
        self.runs_dir.mkdir(parents=True)
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True)
        self.handler.runs_dir = self.runs_dir
        self.handler._health_root = self.tmpdir

        # Create valid execution artifact
        self.artifact_path = self.external_dir / "test-execution.json"
        execution_artifact = {
            "purpose": "next-check-execution",
            "run_id": "test-run",
            "cluster_label": "test-cluster",
            "status": "success",
        }
        self.artifact_path.write_text(json.dumps(execution_artifact), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_success_log_excludes_usefulness_summary(self) -> None:
        """Success log should NOT include usefulness_summary content."""
        rel_path = str(self.artifact_path.relative_to(self.runs_dir))

        # Use a summary that would be suspicious if logged
        sensitive_summary = "SECRET_API_KEY=abc123"
        payload = json.dumps({
            "artifactPath": rel_path,
            "usefulnessClass": "useful",
            "usefulnessSummary": sensitive_summary,
        })

        self.handler.headers["Content-Length"] = str(len(payload))
        self.handler.rfile = BytesIO(payload.encode("utf-8"))

        with patch("k8s_diag_agent.ui.server_feedback.logger") as mock_logger:
            handle_usefulness_feedback(self.handler)

        response, status = self.handler.sent_response
        self.assertEqual(status, 200)

        # Check that summary is NOT in log calls
        all_log_calls = str(mock_logger.info.call_args_list)
        self.assertNotIn(sensitive_summary, all_log_calls)
        self.assertNotIn("SECRET_API_KEY", all_log_calls)

    def test_success_log_excludes_alertmanager_summary(self) -> None:
        """Success log should NOT include alertmanager_relevance_summary content."""
        rel_path = str(self.artifact_path.relative_to(self.runs_dir))

        # Use a summary that would be suspicious if logged
        sensitive_summary = "SECRET_TOKEN=xyz789"
        payload = json.dumps({
            "artifactPath": rel_path,
            "alertmanagerRelevance": "relevant",
            "alertmanagerRelevanceSummary": sensitive_summary,
        })

        self.handler.headers["Content-Length"] = str(len(payload))
        self.handler.rfile = BytesIO(payload.encode("utf-8"))

        with patch("k8s_diag_agent.ui.server_feedback.logger") as mock_logger:
            handle_alertmanager_relevance_feedback(self.handler)

        response, status = self.handler.sent_response
        self.assertEqual(status, 200)

        # Check that summary is NOT in log calls
        all_log_calls = str(mock_logger.info.call_args_list)
        self.assertNotIn(sensitive_summary, all_log_calls)
        self.assertNotIn("SECRET_TOKEN", all_log_calls)


class TestValidFeedbackPath(unittest.TestCase):
    """Tests that valid feedback path still works correctly."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
        self.handler = MockHealthUIRequestHandler(self.tmpdir)
        # Set up directory structure (use resolved paths)
        self.runs_dir = self.tmpdir / "runs"
        self.runs_dir.mkdir(parents=True)
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True)
        self.handler.runs_dir = self.runs_dir
        self.handler._health_root = self.tmpdir

        # Create valid execution artifact
        self.artifact_path = self.external_dir / "test-execution.json"
        execution_artifact = {
            "purpose": "next-check-execution",
            "run_id": "test-run",
            "cluster_label": "test-cluster",
            "status": "success",
            "tool_name": "test-tool",
        }
        self.artifact_path.write_text(json.dumps(execution_artifact), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_usefulness_feedback_succeeds(self) -> None:
        """Valid usefulness feedback should succeed."""
        rel_path = str(self.artifact_path.relative_to(self.runs_dir))

        payload = json.dumps({
            "artifactPath": rel_path,
            "usefulnessClass": "useful",
            "usefulnessSummary": "Found relevant logs",
        })

        self.handler.headers["Content-Length"] = str(len(payload))
        self.handler.rfile = BytesIO(payload.encode("utf-8"))

        handle_usefulness_feedback(self.handler)
        response, status = self.handler.sent_response
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["usefulnessClass"], "useful")
        self.assertIn("reviewArtifactPath", response)

    def test_valid_alertmanager_feedback_succeeds(self) -> None:
        """Valid alertmanager relevance feedback should succeed."""
        rel_path = str(self.artifact_path.relative_to(self.runs_dir))

        payload = json.dumps({
            "artifactPath": rel_path,
            "alertmanagerRelevance": "relevant",
        })

        self.handler.headers["Content-Length"] = str(len(payload))
        self.handler.rfile = BytesIO(payload.encode("utf-8"))

        handle_alertmanager_relevance_feedback(self.handler)
        response, status = self.handler.sent_response
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["alertmanagerRelevance"], "relevant")
        self.assertIn("reviewArtifactPath", response)


if __name__ == "__main__":
    unittest.main()
