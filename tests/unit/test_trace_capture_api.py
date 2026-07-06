"""Tests for trace_capture_api module - latency measurement verification."""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add trace-capture to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from trace_capture_api import (
    APIExerciseConfig,
    _make_request,
    exercise_diagnosis_handoff,
    exercise_health_details,
    exercise_incident_detail,
    exercise_incident_list,
)


class TestLatencyMeasurement:
    """Tests verifying latency_ms is present and non-negative in all results."""

    def test_make_request_returns_latency(self):
        """Test that _make_request returns latency_ms as third tuple element."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"status": "ok"}'

        with patch("urllib.request.urlopen", return_value=mock_response):
            status, body, latency_ms = _make_request("GET", "http://test.com/api")
            assert isinstance(latency_ms, float)
            assert latency_ms >= 0

    def test_make_request_latency_non_negative_on_http_error(self):
        """Test that latency is non-negative even on HTTPError."""
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="http://test.com", code=500, msg="Server Error", hdrs={}, fp=None
        )):
            status, body, latency_ms = _make_request("GET", "http://test.com/api")
            assert latency_ms >= 0

    def test_make_request_latency_non_negative_on_url_error(self):
        """Test that latency is non-negative even on URLError."""
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            status, body, latency_ms = _make_request("GET", "http://test.com/api")
            assert latency_ms >= 0

    def test_health_details_includes_latency(self):
        """Test successful health_details includes latency_ms."""
        # Mock the entire context manager behavior
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.status = 200
        mock_context.read.return_value = b'{"status": "healthy"}'

        with patch("urllib.request.urlopen", return_value=mock_context):
            config = APIExerciseConfig()
            result = exercise_health_details(config)

            assert "latency_ms" in result
            assert isinstance(result["latency_ms"], float)
            assert result["latency_ms"] >= 0

    def test_health_details_failed_includes_latency(self):
        """Test failed health_details also includes latency_ms."""
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            config = APIExerciseConfig()
            result = exercise_health_details(config)

            assert "latency_ms" in result
            assert isinstance(result["latency_ms"], float)

    def test_incident_list_includes_latency(self):
        """Test successful incident_list includes latency_ms."""
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.status = 200
        mock_context.read.return_value = b'{"incidents": []}'

        with patch("urllib.request.urlopen", return_value=mock_context):
            config = APIExerciseConfig()
            result = exercise_incident_list(config)

            assert "latency_ms" in result
            assert isinstance(result["latency_ms"], float)
            assert result["latency_ms"] >= 0

    def test_incident_detail_with_id_includes_latency(self):
        """Test successful incident_detail includes latency_ms."""
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.status = 200
        mock_context.read.return_value = b'{"incident_id": "123"}'

        with patch("urllib.request.urlopen", return_value=mock_context):
            config = APIExerciseConfig(incident_id="test-incident-123")
            result = exercise_incident_detail(config)

            assert "latency_ms" in result
            assert isinstance(result["latency_ms"], float)
            assert result["latency_ms"] >= 0

    def test_incident_detail_without_id_includes_latency_zero(self):
        """Test incident_detail without ID returns latency_ms=0.0."""
        config = APIExerciseConfig(incident_id=None)
        result = exercise_incident_detail(config)

        assert "latency_ms" in result
        assert result["latency_ms"] == 0.0

    def test_diagnosis_handoff_includes_latency(self):
        """Test successful diagnosis_handoff includes latency_ms."""
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.status = 200
        mock_context.read.return_value = b'{"status": "ok"}'

        with patch("urllib.request.urlopen", return_value=mock_context):
            config = APIExerciseConfig(incident_id="test-incident-123")
            result = exercise_diagnosis_handoff(config)

            assert "latency_ms" in result
            assert isinstance(result["latency_ms"], float)
            assert result["latency_ms"] >= 0

    def test_diagnosis_handoff_without_id_includes_latency_zero(self):
        """Test diagnosis_handoff without ID returns latency_ms=0.0."""
        config = APIExerciseConfig(incident_id=None)
        result = exercise_diagnosis_handoff(config)

        assert "latency_ms" in result
        assert result["latency_ms"] == 0.0

    def test_latency_is_measured_not_zero_for_slow_response(self):
        """Test that latency reflects actual elapsed time for slow responses."""
        import time

        def slow_response(*args, **kwargs):
            time.sleep(0.05)  # 50ms delay
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"data": "ok"}'
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=slow_response):
            status, body, latency_ms = _make_request("GET", "http://test.com/api")
            # Should be at least 50ms due to our sleep
            assert latency_ms >= 50.0


class TestBaselineGenerationWithLatency:
    """Tests verifying baseline generation handles latency correctly."""

    def test_successful_result_latency_for_baseline(self):
        """Test that successful API results include latency for baseline computation."""
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.status = 200
        mock_context.read.return_value = b'{"status": "healthy"}'

        with patch("urllib.request.urlopen", return_value=mock_context):
            config = APIExerciseConfig()
            result = exercise_health_details(config)

            # Verify result can be used for baseline generation
            assert result["success"] is True
            assert "latency_ms" in result
            assert result["latency_ms"] > 0

    def test_baseline_does_not_accept_missing_latency(self):
        """Test that results without latency_ms would break baseline."""
        # This test documents the contract: all results must have latency_ms
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.status = 200
        mock_context.read.return_value = b'{"status": "healthy"}'

        with patch("urllib.request.urlopen", return_value=mock_context):
            config = APIExerciseConfig()
            result = exercise_health_details(config)

            # The result must have latency_ms for baseline generation
            assert "latency_ms" in result, "All API results must include latency_ms"
