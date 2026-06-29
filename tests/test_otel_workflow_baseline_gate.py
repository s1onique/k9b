# Copyright (c) 2025 Artem Chistyakov
# SPDX-License-Identifier: MIT

"""Tests for OTel workflow baseline gates.

These tests verify that the OTel workflow uses the common baseline pattern
(ensure_k9b_lab_baseline), avoids direct helm install, and uses resolved
Service URLs instead of hard-coded ports.
"""

from __future__ import annotations

from tests.otel_workflow_common_gates_helpers import (
    FRONTEND_SMOKE,
    OTEL_WORKFLOW,
    TRAFFIC_SCRIPT,
    read_text,
)


class TestOtelWorkflowBaselineGates:
    """Test that OTel workflow uses common baseline patterns."""

    def test_otel_workflow_uses_k9b_lab_baseline(self) -> None:
        """OTel workflow should use ensure_k9b_lab_baseline script."""
        content = read_text(OTEL_WORKFLOW)

        # Should reference the k9b lab baseline script
        assert "ensure_k9b_lab_baseline" in content, \
            "OTel workflow should use ensure_k9b_lab_baseline script"

    def test_otel_workflow_no_direct_helm_install(self) -> None:
        """OTel workflow should NOT directly run helm upgrade --install k9b."""
        content = read_text(OTEL_WORKFLOW)

        # Should use the baseline script instead of direct helm install
        assert "helm upgrade --install k9b" not in content, \
            "OTel workflow should use ensure_k9b_lab_baseline instead of direct helm install"


class TestOtelFrontendTrafficContract:
    """Test that frontend traffic uses resolved Service URLs."""

    def test_frontend_smoke_file_exists(self) -> None:
        """Frontend smoke script should exist."""
        assert FRONTEND_SMOKE.exists(), \
            "k9b_otel_frontend_smoke.py should exist"

    def test_frontend_smoke_resolves_service_port(self) -> None:
        """Frontend smoke should resolve port from Service, not hard-code."""
        from scripts.k9b_otel_frontend_smoke import _find_http_port

        # Test port finding logic with common port patterns
        ports = [
            {"name": "http", "port": 8080},
            {"name": "metrics", "port": 9090},
        ]

        # Should find 8080 as the HTTP port
        found_port = _find_http_port(ports)
        assert found_port == 8080, "Should find HTTP port 8080"

    def test_frontend_smoke_finds_named_http_port(self) -> None:
        """Frontend smoke should find named HTTP ports."""
        from scripts.k9b_otel_frontend_smoke import _find_http_port

        # Test with named port
        ports = [
            {"name": "http-web", "port": 3000},
            {"name": "grpc", "port": 50051},
        ]

        found_port = _find_http_port(ports)
        assert found_port == 3000, "Should find HTTP-named port 3000"

    def test_traffic_uses_resolve_service_url(self) -> None:
        """Traffic generation should use resolve_service_http_url."""
        content = read_text(TRAFFIC_SCRIPT)

        # Should import and use resolve_service_http_url
        assert "resolve_service_http_url" in content, \
            "Traffic should use resolve_service_http_url for port resolution"


class TestOtelLabFailureClassification:
    """Test OTel lab failure classification."""

    def test_failure_backend_unhealthy(self) -> None:
        """k9b backend unhealthy should be classified early."""
        from scripts.k9b_otel_demo_lab_constants import FAILURE_BACKEND_HEALTH_FAILED

        assert FAILURE_BACKEND_HEALTH_FAILED == "backend_health_failed"

    def test_failure_frontend_unreachable(self) -> None:
        """Frontend unreachable should be classified."""
        from scripts.k9b_otel_frontend_smoke import FAILURE_FRONTEND_SMOKE_NO_SUCCESS

        assert FAILURE_FRONTEND_SMOKE_NO_SUCCESS == "frontend_smoke_no_success"

    def test_failure_traffic_target_missing(self) -> None:
        """Traffic target missing should be classified."""
        from scripts.k9b_otel_demo_lab_constants import FAILURE_TRAFFIC_TARGET_SERVICE_MISSING

        assert FAILURE_TRAFFIC_TARGET_SERVICE_MISSING == "traffic_target_service_missing"


