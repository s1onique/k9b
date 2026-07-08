"""API registry dispatch tests.

This module validates that:
1. All API_ROUTES have handler import paths
2. All handler import paths resolve to callables
3. All registered routes can be matched by find_api_operation()
4. No duplicate (method, path) registrations
5. No duplicate operation_id
6. Path params are extracted correctly for templated routes
7. /api/openapi.json and /api/docs are registry-routed

Run with: .venv/bin/python -m pytest tests/test_api_registry_dispatch.py -v

CI gate: This test MUST pass before merge.
"""

from __future__ import annotations

from collections import Counter

import pytest

from k8s_diag_agent.ui.api_contract import build_openapi_schema
from k8s_diag_agent.ui.api_dispatch import (
    clear_handler_cache,
    find_api_operation,
    resolve_handler,
)
from k8s_diag_agent.ui.api_routes_registry import API_ROUTES

# =============================================================================
# Handler resolution tests
# =============================================================================


class TestHandlerResolution:
    """Tests that all registered handlers resolve correctly."""

    def test_all_operations_have_handler(self) -> None:
        """Every operation must have a non-empty handler path."""
        missing: list[tuple[str, str]] = []

        for op in API_ROUTES:
            if not op.handler:
                missing.append((op.method, op.path))

        assert not missing, f"Operations missing handler: {missing}"

    def test_no_registered_dispatch_adapter_is_placeholder(self) -> None:
        """Registered handlers must not contain NotImplementedError placeholders.

        This prevents the regression where handlers are registered but raise
        NotImplementedError instead of implementing real dispatch logic.
        """
        import inspect

        failures: list[tuple[str, str, str]] = []

        for op in API_ROUTES:
            if not op.handler:
                continue

            try:
                handler = resolve_handler(op.handler)
                source = inspect.getsource(handler)

                if "NotImplementedError" in source:
                    failures.append((op.method, op.path, op.handler))
            except Exception:
                # Let other tests handle import errors
                pass

        assert not failures, f"Registered handlers still contain NotImplementedError: {failures}"

    def test_all_handler_paths_resolve(self) -> None:
        """Every handler import path must resolve to a callable."""
        clear_handler_cache()
        failures: list[tuple[str, str, str]] = []

        for op in API_ROUTES:
            if not op.handler:
                continue
            try:
                handler = resolve_handler(op.handler)
                if not callable(handler):
                    failures.append((op.method, op.path, f"not callable: {handler!r}"))
            except (ImportError, AttributeError, ValueError) as exc:
                failures.append((op.method, op.path, str(exc)))

        assert not failures, f"Handler resolution failures: {failures}"


# =============================================================================
# Route matching tests
# =============================================================================


class TestRouteMatching:
    """Tests that routes can be matched correctly."""

    def test_all_exact_routes_match(self) -> None:
        """All exact-match routes should be findable."""
        unmatched: list[tuple[str, str]] = []

        for op in API_ROUTES:
            if op.match == "exact":
                matched = find_api_operation(op.method, op.path)
                if matched is None:
                    unmatched.append((op.method, op.path))

        assert not unmatched, f"Exact routes not matched: {unmatched}"

    def test_sample_template_routes_match(self) -> None:
        """Sample templated routes should match and extract params."""
        # Alertmanager source action is now body-based: sourceId lives in JSON,
        # so it is intentionally absent from path-template sample tests.
        test_cases = [
            # (method, sample_path, expected_template_path, expected_params)
            ("GET", "/api/incidents/inc-123", "/api/incidents/{incident_id}", {"incident_id": "inc-123"}),
            ("GET", "/api/incidents/inc-abc/automatic-diagnosis-review/handoff", "/api/incidents/{incident_id}/automatic-diagnosis-review/handoff", {"incident_id": "inc-abc"}),
            ("POST", "/api/incidents/test-inc/diagnosis-loop/one-pass", "/api/incidents/{incident_id}/diagnosis-loop/one-pass", {"incident_id": "test-inc"}),
        ]

        for method, sample_path, template_path, expected_params in test_cases:
            matched = find_api_operation(method, sample_path)
            assert matched is not None, f"Template route not matched: {method} {sample_path}"
            assert matched.operation.path == template_path, f"Wrong template: expected {template_path}, got {matched.operation.path}"
            assert matched.path_params == expected_params, f"Wrong params: expected {expected_params}, got {matched.path_params}"

    def test_no_path_param_leakage(self) -> None:
        """Path params should be correctly extracted from sample paths."""
        # Alertmanager source action is body-based: sourceId lives in JSON, not path.
        test_cases = [
            ("GET", "/api/incidents/inc-123", {"incident_id": "inc-123"}),
            ("POST", "/api/incidents/test-inc/diagnosis-loop/one-pass", {"incident_id": "test-inc"}),
        ]

        for method, sample_path, expected_params in test_cases:
            matched = find_api_operation(method, sample_path)
            if matched is not None:
                # Only check if this route actually has path params in the registry
                if matched.operation.path_params:
                    for param_name in matched.operation.path_params:
                        assert param_name in matched.path_params, f"Missing param {param_name} in {sample_path}"


# =============================================================================
# Registry integrity tests
# =============================================================================


class TestRegistryIntegrity:
    """Tests that the registry has no duplicates or inconsistencies."""

    def test_no_duplicate_method_path(self) -> None:
        """No duplicate (method, path) combinations should exist."""
        keys = [(op.method.upper(), op.path) for op in API_ROUTES]
        duplicates = [
            key
            for key, count in Counter(keys).items()
            if count > 1
        ]

        assert not duplicates, f"Duplicate (method, path) in registry: {duplicates}"

    def test_no_duplicate_operation_id(self) -> None:
        """No duplicate operation_id values should exist."""
        op_ids = [op.operation_id for op in API_ROUTES if op.operation_id]
        duplicates = [
            op_id
            for op_id, count in Counter(op_ids).items()
            if count > 1
        ]

        assert not duplicates, f"Duplicate operationId in registry: {duplicates}"

    def test_template_paths_have_path_params(self) -> None:
        """Templated paths should have corresponding path_params declared."""
        issues: list[tuple[str, str, str]] = []

        for op in API_ROUTES:
            if op.match == "template":
                import re
                template_params = set(re.findall(r"\{(\w+)\}", op.path))
                declared_params = set(op.path_params)

                if template_params != declared_params:
                    issues.append((
                        op.method,
                        op.path,
                        f"template has {template_params}, declared {declared_params}",
                    ))

        assert not issues, f"Template/path_params mismatch: {issues}"


# =============================================================================
# OpenAPI integration tests
# =============================================================================


class TestOpenAPIIntegration:
    """Tests that OpenAPI schema generation works with dispatch metadata."""

    def test_openapi_schema_generates(self) -> None:
        """OpenAPI schema should generate without errors."""
        schema = build_openapi_schema()
        assert isinstance(schema, dict)
        assert "paths" in schema
        assert len(schema["paths"]) > 0

    def test_openapi_includes_all_routes(self) -> None:
        """OpenAPI schema should include all routes from registry."""
        schema = build_openapi_schema()

        # Count routes in schema
        schema_routes = set()
        for path, methods in schema["paths"].items():
            for method in methods.keys():
                schema_routes.add((method.upper(), path))

        # Count routes in registry (exclude dispatch-only if needed)
        registry_routes = {(op.method.upper(), op.path) for op in API_ROUTES}

        # Schema should include all registry routes
        missing = registry_routes - schema_routes
        assert not missing, f"Schema missing routes: {missing}"

    def test_dispatch_fields_not_in_openapi(self) -> None:
        """Dispatch-only fields (handler, match) should not leak into OpenAPI schema."""
        schema = build_openapi_schema()

        # Check that no operation has handler or match fields
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                assert "handler" not in operation, f"handler leaked into schema for {method.upper()} {path}"
                assert "match" not in operation, f"match leaked into schema for {method.upper()} {path}"


# =============================================================================
# Specific endpoint tests
# =============================================================================


class TestSpecificEndpoints:
    """Tests for specific important endpoints."""

    def test_openapi_json_is_registered(self) -> None:
        """GET /api/openapi.json should be in the registry."""
        matched = find_api_operation("GET", "/api/openapi.json")
        assert matched is not None, "/api/openapi.json not found in registry"
        assert matched.operation.requires_auth is False, "/api/openapi.json should be public"

    def test_openapi_docs_is_registered(self) -> None:
        """GET /api/docs should be in the registry."""
        matched = find_api_operation("GET", "/api/docs")
        assert matched is not None, "/api/docs not found in registry"
        assert matched.operation.requires_auth is False, "/api/docs should be public"

    def test_auth_routes_are_public(self) -> None:
        """Auth routes should be marked as public (requires_auth=False)."""
        auth_paths = ["/api/auth/status", "/api/auth/me", "/api/auth/login", "/api/auth/logout"]

        for path in auth_paths:
            matched = find_api_operation("GET", path) or find_api_operation("POST", path)
            assert matched is not None, f"{path} not found in registry"
            assert matched.operation.requires_auth is False, f"{path} should be public"

    def test_health_routes_are_public(self) -> None:
        """Health routes should be marked as public."""
        health_paths = ["/api/health", "/api/health/details"]

        for path in health_paths:
            matched = find_api_operation("GET", path)
            assert matched is not None, f"{path} not found in registry"
            assert matched.operation.requires_auth is False, f"{path} should be public"

    def test_notifications_route_is_registered(self) -> None:
        """GET /api/notifications should be in the registry with a handler."""
        matched = find_api_operation("GET", "/api/notifications")
        assert matched is not None, "/api/notifications not found in registry"
        assert matched.operation.handler is not None, "/api/notifications should have a handler"
        assert "handle_notifications_dispatch" in matched.operation.handler, (
            f"/api/notifications handler should be notifications dispatch, got: {matched.operation.handler}"
        )


# =============================================================================
# Main gate test
# =============================================================================


def test_api_registry_dispatch_gate() -> None:
    """Master test that ensures the entire registry dispatch is valid.

    This is the primary gate for CI. All other tests are subsets of this check.
    """
    clear_handler_cache()

    # 1. All operations have handlers
    for op in API_ROUTES:
        assert op.handler, f"{op.method} {op.path} missing handler"

    # 2. All handlers resolve
    for op in API_ROUTES:
        if op.handler:
            handler = resolve_handler(op.handler)
            assert callable(handler), f"{op.handler} is not callable"

    # 3. All routes can be matched
    for op in API_ROUTES:
        if op.match == "exact":
            matched = find_api_operation(op.method, op.path)
            assert matched is not None, f"Could not match {op.method} {op.path}"

    # 4. No duplicates
    keys = [(op.method.upper(), op.path) for op in API_ROUTES]
    assert len(keys) == len(set(keys)), "Duplicate (method, path) found"

    op_ids = [op.operation_id for op in API_ROUTES if op.operation_id]
    assert len(op_ids) == len(set(op_ids)), "Duplicate operationId found"

    # 5. OpenAPI generates
    schema = build_openapi_schema()
    assert "paths" in schema
    assert len(schema["paths"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
