"""Tests for the internal handler field access AST verifier.

These tests verify that the AST-based checker correctly:
1. Rejects forbidden domain field access in handler code
2. Allows field access within serializer functions
3. No variable name allowlist exists (alias bypass is prevented)
"""

from __future__ import annotations

import ast

from scripts.incident_lifecycle_boundary.internal_handler_field_access import (
    HandlerFieldAccessChecker,
)


class TestHandlerFieldAccessChecker:
    """Unit tests for the AST-based handler field access checker."""

    def _check_source(self, source: str) -> list[str]:
        """Helper to run the checker directly on AST."""
        tree = ast.parse(source)
        checker = HandlerFieldAccessChecker("test_handler.py")
        checker.visit(tree)
        return checker.errors

    def test_rejects_incident_status_direct_access(self) -> None:
        """Verify that direct access to incident.status is rejected."""
        source = '''
async def handle_list_incidents(request):
    incident = await get_incident()
    status_value = incident.status.value
    return {"status": status_value}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "status" in errors[0]

    def test_rejects_incident_first_observed_at_direct_access(self) -> None:
        """Verify that direct access to incident.first_observed_at is rejected."""
        source = '''
async def handle_get_incident(request, incident_id):
    inc = await get_incident(incident_id)
    timestamp = inc.first_observed_at.isoformat()
    return {"timestamp": timestamp}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "first_observed_at" in errors[0]

    def test_rejects_incident_incident_id_direct_access(self) -> None:
        """Verify that direct access to incident.incident_id is rejected."""
        source = '''
async def handle_get_incident(request):
    _incident = await fetch_incident()
    id_value = _incident.incident_id
    return {"id": id_value}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "incident_id" in errors[0]

    def test_rejects_incident_namespace_direct_access(self) -> None:
        """Verify that direct access to incident.namespace is rejected."""
        source = '''
async def handle_get_incident(request):
    inc_data = await get_incident()
    ns = inc_data.namespace
    return {"namespace": ns}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "namespace" in errors[0]

    def test_allows_serializer_function_field_access(self) -> None:
        """Verify that field access inside serializer functions is allowed."""
        source = '''
def build_incident_internal_detail_payload(incident):
    """Serializer function - field access is allowed here."""
    return {
        "incident_id": incident.incident_id,
        "namespace": incident.namespace,
        "status": incident.status.value,
        "created_at": incident.first_observed_at.isoformat(),
    }

async def handle_get_incident(request, incident_id):
    inc = await get_incident(incident_id)
    return build_incident_internal_detail_payload(inc)
'''
        errors = self._check_source(source)
        assert len(errors) == 0, f"Expected no errors, got: {errors}"

    def test_rejects_inc_on_forbidden_field(self) -> None:
        """Verify that inc.xxx on forbidden field is rejected."""
        source = '''
async def handle_get_incident(request):
    inc = await get_incident()
    return {"id": inc.incident_id}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "incident_id" in errors[0]

    def test_rejects_multiple_forbidden_fields(self) -> None:
        """Verify that multiple forbidden fields each generate an error."""
        source = '''
async def handle_get_incident(request):
    inc = await get_incident()
    return {
        "id": inc.incident_id,
        "namespace": inc.namespace,
        "status": inc.status.value,
    }
'''
        errors = self._check_source(source)
        assert len(errors) == 3


class TestHandlerFieldAccessCheckerAliasBypass:
    """Tests to prevent alias-based bypass of the verifier.

    These tests ensure that aliasing a variable to an incident-like name
    does not allow accessing forbidden domain fields.
    """

    def _check_source(self, source: str) -> list[str]:
        """Helper to run the checker directly on AST."""
        tree = ast.parse(source)
        checker = HandlerFieldAccessChecker("test_handler.py")
        checker.visit(tree)
        return checker.errors

    def test_rejects_incident_detail_alias_on_forbidden_field(self) -> None:
        """Verify that aliasing to incident_detail does NOT bypass the check.

        This is a critical regression test - the old ALLOWED_VARIABLE_PATTERNS
        allowlist would have allowed this pattern.
        """
        source = '''
async def handle_get_incident(request):
    inc = await get_incident()
    # Aliasing to incident_detail should NOT bypass the check
    incident_detail = inc
    return {"id": incident_detail.incident_id}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "incident_id" in errors[0]

    def test_rejects_incident_summaries_alias_on_forbidden_field(self) -> None:
        """Verify that aliasing to incident_summaries does NOT bypass the check."""
        source = '''
async def handle_list_incidents(request):
    incidents = await get_incidents()
    # Aliasing should NOT bypass the check
    incident_summaries = incidents
    return {"count": len(incident_summaries)}
'''
        errors = self._check_source(source)
        # signals is a forbidden field, so accessing it should error
        # But wait, signals is being accessed, not incident_summaries.signals
        # Let's test with a direct field access on the alias
        source = '''
async def handle_list_incidents(request):
    incidents = await get_incidents()
    # Aliasing should NOT bypass the check
    incident_summaries = incidents
    return {"count": incident_summaries.signal_count}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "signal_count" in errors[0]

    def test_rejects_generic_alias_on_forbidden_field(self) -> None:
        """Verify that any alias to a forbidden variable name is still caught."""
        source = '''
async def handle_get_incident(request):
    original = await get_incident()
    alias = original
    return {"id": alias.incident_id}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "incident_id" in errors[0]


class TestHandlerFieldAccessCheckerEdgeCases:
    """Edge case tests for the handler field access checker."""

    def _check_source(self, source: str) -> list[str]:
        """Helper to run the checker directly on AST."""
        tree = ast.parse(source)
        checker = HandlerFieldAccessChecker("test_handler.py")
        checker.visit(tree)
        return checker.errors

    def test_allows_nested_serializer_functions(self) -> None:
        """Verify that nested function calls within serializers are allowed."""
        source = '''
def _signal_to_payload(signal):
    return {"source": signal.source}

def build_incident_internal_detail_payload(incident):
    signals = [_signal_to_payload(s) for s in incident.signals]
    return {
        "incident_id": incident.incident_id,
        "signals": signals,
    }

async def handle_get_incident(request, incident_id):
    inc = await get_incident(incident_id)
    return build_incident_internal_detail_payload(inc)
'''
        errors = self._check_source(source)
        assert len(errors) == 0, f"Expected no errors, got: {errors}"

    def test_rejects_non_incident_attribute_access(self) -> None:
        """Verify that non-forbidden attributes don't trigger errors."""
        source = '''
async def handle_get_incident(request):
    response = await http_get()
    # response.method is NOT a forbidden field
    return {"method": response.method}
'''
        errors = self._check_source(source)
        assert len(errors) == 0

    def test_rejects_nested_forbidden_access(self) -> None:
        """Verify nested access on incident objects is caught."""
        source = '''
async def handle_list_incidents(request):
    item = await get_item()
    # item.signals should trigger error since signals is forbidden
    return {"count": len(item.signals)}
'''
        errors = self._check_source(source)
        assert len(errors) == 1
        assert "signals" in errors[0]


class TestForbiddenIncidentFields:
    """Verify that the FORBIDDEN_INCIDENT_FIELDS set contains expected fields."""

    def test_contains_all_major_domain_fields(self) -> None:
        """Verify the forbidden set includes all major domain fields."""
        from scripts.incident_lifecycle_boundary.internal_handler_field_access import (
            FORBIDDEN_INCIDENT_FIELDS,
        )

        expected_fields = {
            "incident_id",
            "namespace",
            "status",
            "first_observed_at",
            "last_observed_at",
            "signals",
            "severity",
        }

        for field in expected_fields:
            assert field in FORBIDDEN_INCIDENT_FIELDS, (
                f"Expected {field} to be in FORBIDDEN_INCIDENT_FIELDS"
            )


class TestNoVariableNameAllowlist:
    """Verify that ALLOWED_VARIABLE_PATTERNS no longer exists.

    The verifier should be seam-based (forbidden attributes), not name-based.
    """

    def test_no_variable_name_allowlist_exists(self) -> None:
        """Verify ALLOWED_VARIABLE_PATTERNS has been removed.

        This prevents alias-based bypass of the field access checks.
        """
        import scripts.incident_lifecycle_boundary.internal_handler_field_access as verifier

        assert not hasattr(verifier, "ALLOWED_VARIABLE_PATTERNS"), (
            "ALLOWED_VARIABLE_PATTERNS should be removed to prevent alias bypass"
        )
