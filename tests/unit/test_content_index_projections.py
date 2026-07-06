"""Tests for content index projections.

Tests projection generation and safety validation.
"""

from __future__ import annotations

import json
from pathlib import Path

from k8s_diag_agent.content_index.projections import (
    PROJECTION_API_SUMMARY,
    ProjectionBuilder,
    ProjectionConfig,
    contains_forbidden_content,
    create_projections,
    detect_content_kind,
    project_generic,
    project_incident,
    project_lab_result,
    project_perf_baseline_summary,
    project_trace_capture_summary,
    strip_forbidden_fields,
    truncate_string,
    validate_projection_safety,
)


class TestTruncateString:
    """Test string truncation."""

    def test_truncate_short_string(self) -> None:
        """Short strings are not truncated."""
        result = truncate_string("short", 10)
        assert result == "short"

    def test_truncate_long_string(self) -> None:
        """Long strings are truncated with ellipsis."""
        result = truncate_string("this is a long string", 10)
        assert result == "this is..."
        assert len(result) == 10


class TestContainsForbiddenContent:
    """Test forbidden content detection."""

    def test_detects_secret(self) -> None:
        """Detects secret field."""
        data = {"api_secret": "value", "normal": "data"}
        result = contains_forbidden_content(data)
        assert "api_secret" in result

    def test_detects_token(self) -> None:
        """Detects token field."""
        data = {"bearer_token": "value", "normal": "data"}
        result = contains_forbidden_content(data)
        assert "bearer_token" in result

    def test_detects_absolute_path(self) -> None:
        """Detects absolute path in values."""
        data = {"path": "/absolute/path.json"}
        result = contains_forbidden_content(data)
        assert any("absolute_path" in r for r in result)

    def test_safe_data_no_forbidden(self) -> None:
        """Safe data has no forbidden content."""
        data = {"title": "Test", "status": "open"}
        result = contains_forbidden_content(data)
        assert len(result) == 0


class TestStripForbiddenFields:
    """Test forbidden field stripping."""

    def test_strips_forbidden_fields(self) -> None:
        """Forbidden fields are stripped."""
        data = {
            "content_id": "123",
            "safe_title": "Test",
            "api_secret": "secret",
            "bearer_token": "token",
        }
        result = strip_forbidden_fields(data)
        assert "content_id" in result
        assert "safe_title" in result
        assert "api_secret" not in result
        assert "bearer_token" not in result

    def test_preserves_allowed_fields(self) -> None:
        """Allowed fields are preserved."""
        data = {
            "content_id": "123",
            "safe_title": "Test",
            "status": "open",
            "severity": "high",
        }
        result = strip_forbidden_fields(data)
        assert result == data

    def test_strips_nested_forbidden_fields(self) -> None:
        """Nested forbidden fields are stripped."""
        data = {
            "outer": {
                "inner": "value",
                "secret_key": "secret",
            }
        }
        result = strip_forbidden_fields(data)
        assert "outer" in result
        assert "inner" in result["outer"]
        assert "secret_key" not in result["outer"]


class TestDetectContentKind:
    """Test content kind detection."""

    def test_detects_lab_result(self) -> None:
        """Detects lab result from file name."""
        path = Path("fixtures/lab/pass/lab-result.json")
        result = detect_content_kind(path)
        assert result == "lab_result"

    def test_detects_trace_summary(self) -> None:
        """Detects trace summary from file name."""
        path = Path("trace-capture/trace-summary.json")
        result = detect_content_kind(path)
        assert result == "trace_capture_summary"

    def test_detects_perf_baseline(self) -> None:
        """Detects perf baseline from file name."""
        path = Path("trace-capture/perf-baseline/backend-api-baseline-summary.json")
        result = detect_content_kind(path)
        assert result == "perf_baseline_summary"

    def test_detects_from_content(self) -> None:
        """Detects content kind from file content."""
        path = Path("test.json")
        content = {
            "schema_version": "k9b.lab.v1",
            "scenario": "test",
        }
        result = detect_content_kind(path, content)
        assert result == "lab_result"

    def test_detects_unknown(self) -> None:
        """Returns None for unknown content."""
        path = Path("unknown/random.json")
        result = detect_content_kind(path)
        assert result is None


class TestProjectionBuilder:
    """Test projection builder."""

    def test_builder_adds_fields(self) -> None:
        """Builder adds fields correctly."""
        builder = ProjectionBuilder("test-123", "incident")
        builder.add_field("status", "open")
        builder.add_status("open")

        assert builder._data["status"] == "open"

    def test_builder_adds_safe_title(self) -> None:
        """Builder adds safe title with truncation."""
        config = ProjectionConfig(max_title_length=10)
        builder = ProjectionBuilder("test-123", "incident", config)
        builder.add_safe_title("This is a very long title")

        assert builder._data["safe_title"] == "This is..."

    def test_builder_adds_safe_summary(self) -> None:
        """Builder adds safe summary with truncation."""
        config = ProjectionConfig(max_summary_length=20)
        builder = ProjectionBuilder("test-123", "incident", config)
        builder.add_safe_summary("This is a very long summary that should be truncated")

        # Truncates to 17 chars (max_length - 3) + "..."
        assert builder._data["safe_summary"] == "This is a very lo..."
        assert len(builder._data["safe_summary"]) == 20

    def test_builder_builds_summary(self) -> None:
        """Builder builds valid summary projection."""
        builder = ProjectionBuilder("test-123", "incident")
        builder.add_safe_title("Test Title")
        builder.add_status("open")

        projection = builder.build_summary()

        assert projection.content_id == "test-123"
        assert projection.projection_kind == PROJECTION_API_SUMMARY
        assert projection.projection_json is not None

        # Verify valid JSON
        data = json.loads(projection.projection_json)
        assert data["safe_title"] == "Test Title"


class TestProjectLabResult:
    """Test lab result projection."""

    def test_project_lab_result(self) -> None:
        """Projects lab result correctly."""
        path = Path("fixtures/lab/pass/lab-result.json")
        data = {
            "ok": True,
            "scenario": "pod-failure",
            "cluster_mode": "local",
            "started_at": "2026-06-16T10:00:00Z",
            "finished_at": "2026-06-16T10:15:00Z",
        }

        projections = project_lab_result("lab-1", path, data)

        assert len(projections) >= 1
        summary = projections[0]
        assert summary.content_id == "lab-1"
        assert summary.projection_kind == PROJECTION_API_SUMMARY

        # Verify JSON
        proj_data = json.loads(summary.projection_json)
        assert proj_data["content_kind"] == "lab_result"
        assert "safe_title" in proj_data


class TestProjectTraceCaptureSummary:
    """Test trace capture summary projection."""

    def test_project_trace_capture_summary(self) -> None:
        """Projects trace capture summary correctly."""
        path = Path("trace-capture/trace-summary.json")
        data = {
            "schema_version": "k9b.trace_capture.v1",
            "service_name": "k9b-backend",
            "trace_count": 5,
            "span_count": 10,
            "http_span_count": 5,
            "generated_at": "2026-07-06T06:25:23Z",
        }

        projections = project_trace_capture_summary("trace-1", path, data)

        assert len(projections) >= 1
        summary = projections[0]
        assert summary.content_id == "trace-1"

        proj_data = json.loads(summary.projection_json)
        assert proj_data["content_kind"] == "trace_capture_summary"
        assert "counts" in proj_data
        assert proj_data["counts"]["traces"] == 5


class TestProjectPerfBaselineSummary:
    """Test perf baseline summary projection."""

    def test_project_perf_baseline_summary(self) -> None:
        """Projects perf baseline summary correctly."""
        path = Path("trace-capture/perf-baseline/backend-api-baseline-summary.json")
        data = {
            "schema_version": "k9b.perf_baseline.v1",
            "total_traces": 5,
            "total_spans": 10,
            "iteration_count": 10,
            "endpoint_count": 4,
            "slowest_endpoint": "GET /api/health/details",
            "generated_at": "2026-07-06T06:25:23Z",
        }

        projections = project_perf_baseline_summary("perf-1", path, data)

        assert len(projections) >= 1
        summary = projections[0]
        assert summary.content_id == "perf-1"

        proj_data = json.loads(summary.projection_json)
        assert proj_data["content_kind"] == "perf_baseline_summary"
        assert "counts" in proj_data


class TestProjectIncident:
    """Test incident projection."""

    def test_project_incident(self) -> None:
        """Projects incident correctly."""
        path = Path("incidents/test-incident.json")
        data = {
            "title": "Test Incident",
            "summary": "Something went wrong",
            "status": "open",
            "severity": "high",
            "namespace": "default",
        }

        projections = project_incident("incident-1", path, data)

        assert len(projections) >= 1
        summary = projections[0]
        assert summary.content_id == "incident-1"

        proj_data = json.loads(summary.projection_json)
        assert proj_data["content_kind"] == "incident"
        assert proj_data["status"] == "open"
        assert proj_data["severity"] == "high"


class TestProjectGeneric:
    """Test generic projection."""

    def test_project_generic(self) -> None:
        """Projects generic content correctly."""
        path = Path("unknown/test.json")
        data = {
            "title": "Test Item",
            "description": "A test item",
            "timestamp": "2026-06-07T00:00:00Z",
        }

        projections = project_generic("generic-1", "unknown", path, data)

        assert len(projections) >= 1
        summary = projections[0]
        assert summary.content_id == "generic-1"

        proj_data = json.loads(summary.projection_json)
        assert "safe_title" in proj_data


class TestValidateProjectionSafety:
    """Test projection safety validation."""

    def test_valid_projection(self) -> None:
        """Valid projection passes safety check."""
        projection = {
            "content_id": "test-123",
            "content_kind": "incident",
            "safe_title": "Test",
            "status": "open",
        }
        json_str = json.dumps(projection)

        is_safe, issues = validate_projection_safety(json_str)
        assert is_safe
        assert len(issues) == 0

    def test_invalid_json(self) -> None:
        """Invalid JSON fails safety check."""
        is_safe, issues = validate_projection_safety("not valid json {")
        assert not is_safe
        assert any("Invalid JSON" in issue for issue in issues)

    def test_forbidden_field(self) -> None:
        """Forbidden fields fail safety check."""
        projection = {
            "content_id": "test-123",
            "api_secret": "secret-value",
        }
        json_str = json.dumps(projection)

        is_safe, issues = validate_projection_safety(json_str)
        assert not is_safe
        assert any("forbidden" in issue.lower() for issue in issues)

    def test_absolute_path(self) -> None:
        """Absolute paths fail safety check."""
        projection = {
            "content_id": "test-123",
            "path": "/absolute/path.json",
        }
        json_str = json.dumps(projection)

        is_safe, issues = validate_projection_safety(json_str)
        assert not is_safe
        assert any("absolute_path" in issue for issue in issues)


class TestCreateProjections:
    """Test projection creation dispatcher."""

    def test_creates_lab_result_projection(self) -> None:
        """Creates lab result projection via dispatcher."""
        path = Path("fixtures/lab/pass/lab-result.json")
        data = {
            "ok": True,
            "scenario": "test",
            "started_at": "2026-06-16T10:00:00Z",
        }

        projections = create_projections("lab-1", "lab_result", path, data)

        assert len(projections) >= 1
        assert projections[0].content_id == "lab-1"

    def test_creates_generic_projection(self) -> None:
        """Creates generic projection for unknown kind."""
        path = Path("unknown/test.json")
        data = {"title": "Test"}

        projections = create_projections("test-1", "unknown_kind", path, data)

        assert len(projections) >= 1
        assert projections[0].projection_kind == PROJECTION_API_SUMMARY
