"""OpenAPI contract tests for AlertManager-source operations.

This module proves the AlertManager-source OpenAPI contract at the
schema/registry level:

* Every AlertManager-source operation exposes exactly one tag: ``alertmanager``.
* None of the four source-specific AlertManager operations place ``sourceId``
  in the URL path. ``sourceId`` is transported as follows:
    - ``perform_alertmanager_source_action``: required JSON body field.
    - ``probe_alertmanager_source``: required JSON body field.
    - ``get_alertmanager_source_debug_packet``: required query parameter.
    - ``get_alertmanager_source_promotion_review``: required query parameter.
* No AlertManager-source path contains a ``{source_id}`` placeholder.

Dispatcher-level assertions (the live HTTP-layer code path that the TypeScript
client ultimately calls into) live in
``test_openapi_alertmanager_source_dispatch.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from k8s_diag_agent.ui.api_contract import build_openapi_schema
from k8s_diag_agent.ui.api_contract_types import APIOperation
from k8s_diag_agent.ui.api_request_schemas import (
    ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA,
    ALERTMANAGER_SOURCE_PROBE_REQUEST_SCHEMA,
)
from k8s_diag_agent.ui.api_routes_registry import API_ROUTES

# =============================================================================
# Constants
# =============================================================================

ALERTMANAGER_SOURCE_OPERATION_IDS: tuple[str, ...] = (
    "get_alertmanager_sources_review_packet",
    "get_alertmanager_source_debug_packet",
    "get_alertmanager_source_promotion_review",
    "probe_alertmanager_source",
    "perform_alertmanager_source_action",
)

# Source-specific operations whose URL paths must not contain {source_id}.
SOURCE_SPECIFIC_OPERATION_IDS: tuple[str, ...] = (
    "get_alertmanager_source_debug_packet",
    "get_alertmanager_source_promotion_review",
    "probe_alertmanager_source",
    "perform_alertmanager_source_action",
)

QUERY_BASED_OPERATION_IDS: tuple[str, ...] = (
    "get_alertmanager_source_debug_packet",
    "get_alertmanager_source_promotion_review",
)

BODY_BASED_OPERATION_IDS: tuple[str, ...] = (
    "perform_alertmanager_source_action",
    "probe_alertmanager_source",
)


def _op_by_id(op_id: str) -> APIOperation:
    for op in API_ROUTES:
        if op.operation_id == op_id:
            return op
    raise AssertionError(f"Operation {op_id} not found in API_ROUTES registry")


def _openapi_operation(
    schema: dict[str, Any], op_id: str
) -> tuple[str, str, dict[str, Any]]:
    """Return ``(path, method, operation)`` for the operationId in the OpenAPI schema."""
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if operation.get("operationId") == op_id:
                return path, method, operation
    raise AssertionError(f"OpenAPI schema missing operationId {op_id}")


# =============================================================================
# Schema-level tag assertions
# =============================================================================


class TestAlertManagerSourceTagOwnership:
    """Every AlertManager-source operation carries exactly the alertmanager tag."""

    def test_alertmanager_source_ops_have_single_alertmanager_tag(self) -> None:
        for op_id in ALERTMANAGER_SOURCE_OPERATION_IDS:
            op = _op_by_id(op_id)
            assert op.tags == ("alertmanager",), (
                f"Operation {op_id} must have exactly one tag "
                f"('alertmanager'); got {op.tags!r}"
            )

    def test_no_alertmanager_source_op_uses_legacy_dual_tag(self) -> None:
        """The legacy dual (incidents, alertmanager) tag tuple must not appear."""
        for op in API_ROUTES:
            if not op.operation_id.startswith(
                (
                    "get_alertmanager_source",
                    "probe_alertmanager_source",
                    "perform_alertmanager_source_action",
                )
            ):
                continue
            assert "incidents" not in op.tags, (
                f"Operation {op.operation_id} still carries the legacy "
                f"'incidents' tag alongside 'alertmanager': {op.tags!r}"
            )
            assert op.tags == ("alertmanager",), (
                f"Operation {op.operation_id} tags={op.tags!r} should be "
                f"exactly ('alertmanager',)."
            )

    def test_openapi_schema_emits_single_alertmanager_tag(self) -> None:
        schema = build_openapi_schema()
        for op_id in ALERTMANAGER_SOURCE_OPERATION_IDS:
            _, _, operation = _openapi_operation(schema, op_id)
            assert operation["tags"] == ["alertmanager"], (
                f"OpenAPI operation {op_id} tags should be ['alertmanager']; "
                f"got {operation['tags']!r}"
            )


# =============================================================================
# Schema-level sourceId transport assertions
# =============================================================================


class TestAlertManagerSourcePathLayout:
    """Source-specific AlertManager paths must not contain {source_id}."""

    def test_source_specific_paths_have_no_source_id_placeholder(self) -> None:
        for op_id in SOURCE_SPECIFIC_OPERATION_IDS:
            op = _op_by_id(op_id)
            assert "{source_id}" not in op.path, (
                f"Operation {op_id} path {op.path!r} still contains "
                f"the {{source_id}} placeholder."
            )

    def test_source_specific_paths_have_no_source_id_path_param(self) -> None:
        for op_id in SOURCE_SPECIFIC_OPERATION_IDS:
            op = _op_by_id(op_id)
            assert "source_id" not in op.path_params, (
                f"Operation {op_id} must not declare source_id as a path_param; "
                f"got {op.path_params!r}"
            )

    def test_openapi_schema_paths_have_no_source_id(self) -> None:
        schema = build_openapi_schema()
        for op_id in SOURCE_SPECIFIC_OPERATION_IDS:
            path, _, _ = _openapi_operation(schema, op_id)
            assert "{source_id}" not in path, (
                f"OpenAPI schema path {path!r} for {op_id} still contains "
                f"{{source_id}}."
            )


class TestAlertManagerSourceQueryParams:
    """Debug and promotion-review use sourceId as a required query parameter."""

    def test_path_based_ops_declare_source_id_query_param(self) -> None:
        for op_id in QUERY_BASED_OPERATION_IDS:
            op = _op_by_id(op_id)
            assert "sourceId" in op.query_params, (
                f"Operation {op_id} must declare 'sourceId' as a query param."
            )
            assert "sourceId" in op.required_query_params, (
                f"Operation {op_id} must declare 'sourceId' as a required "
                f"query param."
            )

    def test_openapi_query_param_is_required_and_named_source_id(self) -> None:
        schema = build_openapi_schema()
        for op_id in QUERY_BASED_OPERATION_IDS:
            _, _, operation = _openapi_operation(schema, op_id)
            params = operation.get("parameters", [])
            query_params = [p for p in params if p.get("in") == "query"]
            assert any(
                p.get("name") == "sourceId" and p.get("required") is True
                for p in query_params
            ), (
                f"Operation {op_id} must declare a required query parameter "
                f"named 'sourceId'; got {query_params!r}"
            )

    def test_path_based_ops_do_not_have_source_id_in_request_body(self) -> None:
        schema = build_openapi_schema()
        for op_id in QUERY_BASED_OPERATION_IDS:
            _, _, operation = _openapi_operation(schema, op_id)
            assert "requestBody" not in operation, (
                f"GET operation {op_id} should not have a request body; "
                f"got {operation.get('requestBody')!r}"
            )


class TestAlertManagerSourceBodyParams:
    """Action and probe must serialise sourceId inside the JSON body."""

    def test_body_based_ops_declare_source_id_request_schema(self) -> None:
        for op_id in BODY_BASED_OPERATION_IDS:
            op = _op_by_id(op_id)
            assert op.request_schema is not None, (
                f"Operation {op_id} must declare a request_schema."
            )
            required = op.request_schema.required or []
            assert "sourceId" in required, (
                f"Operation {op_id} request_schema must mark 'sourceId' as "
                f"required; got required={required!r}"
            )

    def test_action_request_schema_requires_source_id(self) -> None:
        schema = ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA
        assert schema.required is not None
        assert "sourceId" in schema.required

    def test_probe_request_schema_requires_source_id(self) -> None:
        schema = ALERTMANAGER_SOURCE_PROBE_REQUEST_SCHEMA
        assert schema.required is not None
        assert "sourceId" in schema.required

    def test_body_based_ops_do_not_have_source_id_query_param(self) -> None:
        for op_id in BODY_BASED_OPERATION_IDS:
            op = _op_by_id(op_id)
            assert "sourceId" not in (op.query_params or ()), (
                f"Operation {op_id} must not declare 'sourceId' as a query "
                f"param; got {op.query_params!r}"
            )

    def test_openapi_body_schemas_require_source_id(self) -> None:
        schema = build_openapi_schema()
        for op_id in BODY_BASED_OPERATION_IDS:
            _, _, operation = _openapi_operation(schema, op_id)
            request_body = operation.get("requestBody")
            assert request_body is not None, (
                f"Operation {op_id} must declare a requestBody."
            )
            body_schema = (
                request_body.get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            assert body_schema is not None, (
                f"Operation {op_id} requestBody must have an application/json schema."
            )
            required = body_schema.get("required") or []
            assert "sourceId" in required, (
                f"Operation {op_id} request body must require 'sourceId'; "
                f"got required={required!r}"
            )


# =============================================================================
# Operation-IDs policy: no source_id path placeholder, single tag in JSON
# =============================================================================


class TestAlertManagerSourceSchemaSummary:
    """Top-level schema invariants required by the contract."""

    def test_alertmanager_tag_defined_in_schema_tags(self) -> None:
        schema = build_openapi_schema()
        tag_names = {t["name"] for t in schema.get("tags", [])}
        assert "alertmanager" in tag_names

    def test_alertmanager_source_ops_paths_in_paths_section(self) -> None:
        schema = build_openapi_schema()
        expected_paths = {
            "/api/runs/{run_id}/alertmanager-sources/action",
            "/api/runs/{run_id}/alertmanager-sources/review-packet",
            "/api/runs/{run_id}/alertmanager-sources/debug-packet",
            "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe",
            "/api/runs/{run_id}/alertmanager-sources/promotion-review",
        }
        assert expected_paths.issubset(set(schema["paths"].keys())), (
            f"Missing alertmanager-source paths: "
            f"{expected_paths - set(schema['paths'].keys())}"
        )


# =============================================================================
# Generated client invariants
# =============================================================================


class TestGeneratedClientOwnership:
    """The pinned OpenAPI Generator output must put AlertManager-source
    operations only under ``AlertmanagerApi``, never under ``IncidentsApi``."""

    import_check_path = "frontend/src/generated/k9b-api"

    def _generated_files(self) -> dict[str, str]:
        """Read the generated apis/ TypeScript files from disk.

        Returns a mapping from API class name (e.g. ``AlertmanagerApi``) to
        the full contents of ``frontend/src/generated/k9b-api/apis/<name>.ts``.
        """
        apis_dir = Path(self.import_check_path) / "apis"
        files: dict[str, str] = {}
        for path in sorted(apis_dir.glob("*.ts")):
            if path.name == "index.ts":
                continue
            files[path.stem] = path.read_text(encoding="utf-8")
        return files

    def _resolved_apis_dir(self) -> Path:
        """Resolve the generated client ``apis/`` directory.

        Looks for the generated client relative to the repo root. Tests can
        run with varying CWDs; the resolver tries common candidates in order
        before failing with a clear error.
        """
        candidates = [
            Path(self.import_check_path) / "apis",
            Path(__file__).resolve().parent.parent.parent
            / self.import_check_path
            / "apis",
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        raise AssertionError(
            f"Cannot locate generated client apis/ directory. Tried: "
            f"{[str(c) for c in candidates]}"
        )

    @staticmethod
    def _operation_id_to_method_name(op_id: str) -> str:
        """Convert a snake_case operationId into the camelCase method name
        that the OpenAPI Generator emits in TypeScript.

        Example: ``get_alertmanager_source_debug_packet`` ->
        ``getAlertmanagerSourceDebugPacket``.
        """
        parts = op_id.split("_")
        return parts[0] + "".join(p.title() for p in parts[1:])

    def test_each_alertmanager_source_op_appears_in_exactly_one_api_class(
        self,
    ) -> None:
        """Each operationId must appear in exactly one generated API class.

        This guards against the legacy dual-tag regression that produced
        duplicate methods across ``IncidentsApi`` and ``AlertmanagerApi``.
        """
        apis_dir = self._resolved_apis_dir()
        op_to_class: dict[str, str] = {}
        for api_file in sorted(apis_dir.glob("*.ts")):
            if api_file.name == "index.ts":
                continue
            content = api_file.read_text(encoding="utf-8")
            for op_id in ALERTMANAGER_SOURCE_OPERATION_IDS:
                method_name = self._operation_id_to_method_name(op_id)
                # The OpenAPI Generator emits a canonical method signature
                # ``async <methodName>(`` followed by the request params.
                if f"async {method_name}(" in content:
                    if op_id in op_to_class:
                        raise AssertionError(
                            f"Operation {op_id} appears in both "
                            f"{op_to_class[op_id]} and {api_file.stem}. "
                            f"Each operation must live in exactly one class."
                        )
                    op_to_class[op_id] = api_file.stem
        for op_id in ALERTMANAGER_SOURCE_OPERATION_IDS:
            assert op_id in op_to_class, (
                f"Operation {op_id} is missing from the generated client. "
                f"Found: {sorted(op_to_class)}"
            )
            assert op_to_class[op_id] == "AlertmanagerApi", (
                f"Operation {op_id} should live under AlertmanagerApi, "
                f"got {op_to_class[op_id]!r}"
            )

    def test_no_generated_path_contains_source_id_placeholder(self) -> None:
        """None of the four source-specific operations should keep a
        ``{source_id}`` template in their generated path strings."""
        apis_dir = self._resolved_apis_dir()
        alertmanager_api = apis_dir / "AlertmanagerApi.ts"
        assert alertmanager_api.exists(), (
            f"Expected {alertmanager_api} to exist after generation."
        )
        content = alertmanager_api.read_text(encoding="utf-8")
        assert "{source_id}" not in content, (
            f"{alertmanager_api} still contains the {{source_id}} placeholder."
        )


# =============================================================================
# Determinism: re-generating the OpenAPI schema must produce the same JSON.
# =============================================================================


class TestOpenAPISchemaDeterminism:
    """Generating the schema twice must yield the same JSON text."""

    def test_build_openapi_schema_is_deterministic(self) -> None:
        schema_a = build_openapi_schema()
        schema_b = build_openapi_schema()
        assert json.dumps(schema_a, sort_keys=True) == json.dumps(
            schema_b, sort_keys=True
        )
