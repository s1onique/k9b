"""Tests for HTTP route normalization in http_spans module.

Tests that raw incident IDs are normalized to template placeholders
and that unknown routes don't leak sensitive path segments.
"""

from __future__ import annotations

from k8s_diag_agent.observability.http_spans import (
    get_route_normalization_result,
    normalize_http_route,
)


class TestRouteNormalization:
    """Tests for normalize_http_route function."""

    def test_incident_list_route(self) -> None:
        """GET /api/incidents should stay as-is."""
        result = normalize_http_route("GET", "/api/incidents")
        assert result == "GET /api/incidents"

    def test_incident_detail_route_normalizes_concrete_id(self) -> None:
        """GET /api/incidents/abc-123 should normalize to template."""
        result = normalize_http_route("GET", "/api/incidents/abc-123")
        assert result == "GET /api/incidents/{incident_id}"
        # Verify concrete ID is not in output
        assert "abc-123" not in result

    def test_incident_detail_route_with_uuid(self) -> None:
        """GET with UUID-format ID should normalize correctly."""
        result = normalize_http_route(
            "GET",
            "/api/incidents/1234abcd-5678-efgh-9999-ijklmnopqrst",
        )
        assert result == "GET /api/incidents/{incident_id}"
        # Verify UUID is not in output
        assert "1234abcd" not in result

    def test_automatic_diagnosis_route_normalizes_concrete_id(self) -> None:
        """Auto diagnosis route should normalize incident ID."""
        result = normalize_http_route(
            "GET",
            "/api/incidents/inc-001/automatic-diagnosis-loop/one-pass",
        )
        assert result == "GET /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass"
        assert "inc-001" not in result

    def test_diagnosis_loop_route_normalizes_concrete_id(self) -> None:
        """Diagnosis loop route should normalize incident ID."""
        result = normalize_http_route(
            "POST",
            "/api/incidents/my-incident/diagnosis-loop/one-pass",
        )
        assert result == "POST /api/incidents/{incident_id}/diagnosis-loop/one-pass"
        assert "my-incident" not in result

    def test_snapshot_route_stays_exact(self) -> None:
        """Snapshot endpoint should stay as-is (concrete path)."""
        result = normalize_http_route("POST", "/api/incidents/snapshot")
        assert result == "POST /api/incidents/snapshot"

    def test_review_packet_route_stays_exact(self) -> None:
        """Review packet endpoint should stay as-is."""
        result = normalize_http_route("POST", "/api/incidents/review-packet")
        assert result == "POST /api/incidents/review-packet"

    def test_handoff_route_normalizes_concrete_id(self) -> None:
        """Handoff route should normalize incident ID."""
        result = normalize_http_route(
            "POST",
            "/api/incidents/inc-xyz/automatic-diagnosis-review/handoff",
        )
        assert result == "POST /api/incidents/{incident_id}/automatic-diagnosis-review/handoff"
        assert "inc-xyz" not in result

    def test_one_pass_diagnosis_route_normalizes_concrete_id(self) -> None:
        """One-pass diagnosis route should normalize incident ID."""
        result = normalize_http_route(
            "POST",
            "/api/incidents/test-inc-42/one-pass-diagnosis",
        )
        assert result == "POST /api/incidents/{incident_id}/one-pass-diagnosis"
        assert "test-inc-42" not in result

    def test_health_details_route_stays_exact(self) -> None:
        """Health details endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/health/details")
        assert result == "GET /api/health/details"

    def test_health_route_stays_exact(self) -> None:
        """Health endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/health")
        assert result == "GET /api/health"

    def test_auth_login_route_stays_exact(self) -> None:
        """Auth login endpoint should stay as-is."""
        result = normalize_http_route("POST", "/api/auth/login")
        assert result == "POST /api/auth/login"

    def test_auth_status_route_stays_exact(self) -> None:
        """Auth status endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/auth/status")
        assert result == "GET /api/auth/status"

    def test_runs_list_route_stays_exact(self) -> None:
        """Runs list endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/runs")
        assert result == "GET /api/runs"

    def test_run_detail_route_stays_exact(self) -> None:
        """Run detail endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/run")
        assert result == "GET /api/run"

    def test_fleet_route_stays_exact(self) -> None:
        """Fleet endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/fleet")
        assert result == "GET /api/fleet"

    def test_proposals_route_stays_exact(self) -> None:
        """Proposals endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/proposals")
        assert result == "GET /api/proposals"

    def test_cluster_detail_route_stays_exact(self) -> None:
        """Cluster detail endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/cluster-detail")
        assert result == "GET /api/cluster-detail"

    def test_notifications_route_stays_exact(self) -> None:
        """Notifications endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/notifications")
        assert result == "GET /api/notifications"

    def test_next_check_execution_route_stays_exact(self) -> None:
        """Next check execution endpoint should stay as-is."""
        result = normalize_http_route("POST", "/api/next-check-execution")
        assert result == "POST /api/next-check-execution"

    def test_next_check_approval_route_stays_exact(self) -> None:
        """Next check approval endpoint should stay as-is."""
        result = normalize_http_route("POST", "/api/next-check-approval")
        assert result == "POST /api/next-check-approval"

    def test_deterministic_promotion_route_stays_exact(self) -> None:
        """Deterministic promotion endpoint should stay as-is."""
        result = normalize_http_route("POST", "/api/deterministic-next-check/promote")
        assert result == "POST /api/deterministic-next-check/promote"

    def test_usefulness_feedback_route_stays_exact(self) -> None:
        """Usefulness feedback endpoint should stay as-is."""
        result = normalize_http_route("POST", "/api/next-check-execution-usefulness")
        assert result == "POST /api/next-check-execution-usefulness"

    def test_alertmanager_relevance_feedback_route_stays_exact(self) -> None:
        """AlertManager relevance feedback endpoint should stay as-is."""
        result = normalize_http_route("POST", "/api/alertmanager-relevance-feedback")
        assert result == "POST /api/alertmanager-relevance-feedback"

    def test_batch_execution_route_stays_exact(self) -> None:
        """Batch execution endpoint should stay as-is."""
        result = normalize_http_route("POST", "/api/run-batch-next-check-execution")
        assert result == "POST /api/run-batch-next-check-execution"

    def test_run_alertmanager_source_action_route_normalizes(self) -> None:
        """Run AlertManager source action should normalize run_id and source_id."""
        result = normalize_http_route(
            "POST",
            "/api/runs/run-abc/alertmanager-sources/src-xyz/action",
        )
        assert result == "POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action"
        assert "run-abc" not in result
        assert "src-xyz" not in result

    def test_runtime_status_route_stays_exact(self) -> None:
        """Runtime status endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/runtime-status")
        assert result == "GET /api/runtime-status"

    def test_openapi_route_stays_exact(self) -> None:
        """OpenAPI endpoint should stay as-is."""
        result = normalize_http_route("GET", "/api/openapi.json")
        assert result == "GET /api/openapi.json"

    def test_unknown_api_route_does_not_leak_raw_path(self) -> None:
        """Unknown API routes should NOT leak raw path segments."""
        result = normalize_http_route(
            "GET",
            "/api/sensitive/admin/users/123/secrets",
        )
        # Should NOT contain any part of the original path
        assert "sensitive" not in result
        assert "admin" not in result
        assert "users" not in result
        assert "123" not in result
        assert "secrets" not in result
        # Should use safe fallback
        assert result == "GET /api/{unknown}"

    def test_unknown_api_route_fallback_format(self) -> None:
        """Unknown API routes should use /api/{unknown} format."""
        result = normalize_http_route("GET", "/api/totally-unknown/endpoint/here")
        assert result == "GET /api/{unknown}"

    def test_static_assets_route(self) -> None:
        """Non-API routes should use /{static} placeholder."""
        result = normalize_http_route("GET", "/static/app.js")
        assert result == "GET /{static}"

    def test_root_route(self) -> None:
        """Root route should use /{static} placeholder."""
        result = normalize_http_route("GET", "/")
        assert result == "GET /{static}"

    def test_query_string_stripped(self) -> None:
        """Query strings should be stripped during normalization."""
        result = normalize_http_route("GET", "/api/incidents?page=1&size=10")
        assert result == "GET /api/incidents"
        assert "?" not in result
        assert "page" not in result


class TestGetRouteNormalizationResult:
    """Tests for get_route_normalization_result function."""

    def test_known_route_returns_true(self) -> None:
        """Known routes should return is_known=True."""
        route, is_known = get_route_normalization_result(
            "GET",
            "/api/incidents/abc-123",
        )
        assert is_known is True
        assert route == "GET /api/incidents/{incident_id}"

    def test_unknown_route_returns_false(self) -> None:
        """Unknown routes should return is_known=False."""
        route, is_known = get_route_normalization_result(
            "GET",
            "/api/totally-made-up/endpoint",
        )
        assert is_known is False
        assert route == "GET /api/{unknown}"

    def test_static_route_returns_false(self) -> None:
        """Static routes should return is_known=False."""
        route, is_known = get_route_normalization_result("GET", "/favicon.ico")
        assert is_known is False
        assert route == "GET /{static}"
