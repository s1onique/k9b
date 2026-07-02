"""OpenAPI operation metadata and naming tests.

Tests that:
- Operations have required metadata (operationId, tags, summary)
- Operation IDs are unique and client-safe
- Path parameters are documented
"""

from __future__ import annotations

import re
from collections import Counter

from k8s_diag_agent.ui.api_contract import build_openapi_schema


class TestOpenAPIOperationNaming:
    """Tests for operation ID naming conventions."""

    def test_operation_ids_are_client_safe(self) -> None:
        """Operation IDs must be client-safe (snake_case, lowercase, no special chars)."""
        from k8s_diag_agent.ui.api_routes_registry import API_ROUTES

        issues: list[tuple[str, str, str]] = []

        for op in API_ROUTES:
            op_id = op.operation_id
            if not op_id:
                issues.append((op.method, op.path, "<empty>"))
                continue
            # Client-safe: lowercase, alphanumeric + underscore, starts with letter
            if not re.fullmatch(r"[a-z][a-z0-9_]*", op_id):
                issues.append((op.method, op.path, op_id))

        assert not issues, f"Operation IDs are not client-safe: {issues}"


class TestOpenAPIOperationMetadata:
    """Tests that all operations have required metadata."""

    def test_all_operations_have_operation_id(self) -> None:
        """Every operation must have an operationId."""
        schema = build_openapi_schema()
        missing: list[tuple[str, str]] = []

        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                if not operation.get("operationId"):
                    missing.append((method.upper(), path))

        assert not missing, f"Operations missing operationId: {missing}"

    def test_all_operations_have_tags(self) -> None:
        """Every operation must have at least one tag."""
        schema = build_openapi_schema()
        missing: list[tuple[str, str]] = []

        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                if not operation.get("tags"):
                    missing.append((method.upper(), path))

        assert not missing, f"Operations missing tags: {missing}"

    def test_all_operations_have_summary(self) -> None:
        """Every operation must have a summary."""
        schema = build_openapi_schema()
        missing: list[tuple[str, str]] = []

        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                if not operation.get("summary"):
                    missing.append((method.upper(), path))

        assert not missing, f"Operations missing summary: {missing}"

    def test_operation_ids_are_unique(self) -> None:
        """Operation IDs must be unique across the schema."""
        schema = build_openapi_schema()
        operation_ids: list[str] = []

        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                op_id = operation.get("operationId")
                if op_id:
                    operation_ids.append(op_id)

        duplicates = [
            op_id
            for op_id, count in Counter(operation_ids).items()
            if count > 1
        ]

        assert not duplicates, f"Duplicate operationId values: {duplicates}"


class TestOpenAPICompleteness:
    """Tests that all routes in the registry are consistent."""

    def test_all_operations_have_path_params_documented(self) -> None:
        """Operations with path parameters should document them."""
        schema = build_openapi_schema()
        issues: list[tuple[str, str, str]] = []

        for path, methods in schema["paths"].items():
            # Check if path has template parameters
            path_params = re.findall(r"\{(\w+)\}", path)
            if not path_params:
                continue

            for method, operation in methods.items():
                op_params = operation.get("parameters", [])
                param_names = {p["name"] for p in op_params if p.get("in") == "path"}

                for expected_param in path_params:
                    if expected_param not in param_names:
                        issues.append(
                            (
                                method.upper(),
                                path,
                                f"path param '{expected_param}' not documented",
                            )
                        )

        assert not issues, f"Path parameters not documented: {issues}"


class TestOpenAPIContractGate:
    """Master test that ensures the entire contract is valid.

    This is the primary gate for CI. All other tests are subsets of this check.
    """

    def test_openapi_contract_gate(self) -> None:
        """Comprehensive contract validation."""
        schema = build_openapi_schema()

        # 1. Schema structure
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

        # 2. At least some endpoints
        total_operations = sum(
            len(methods)
            for methods in schema["paths"].values()
        )
        assert total_operations >= 10, f"Expected at least 10 operations, found {total_operations}"

        # 3. All operations have metadata
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                assert operation.get("operationId"), f"{method.upper()} {path} missing operationId"
                assert operation.get("tags"), f"{method.upper()} {path} missing tags"
                assert operation.get("summary"), f"{method.upper()} {path} missing summary"

        # 4. All success responses have schemas
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                for status_code, response in operation.get("responses", {}).items():
                    if status_code.startswith("2") and status_code != "204":
                        assert "content" in response, f"{method.upper()} {path} {status_code} missing content"
                        assert "application/json" in response.get("content", {}), (
                            f"{method.upper()} {path} {status_code} missing JSON schema"
                        )
