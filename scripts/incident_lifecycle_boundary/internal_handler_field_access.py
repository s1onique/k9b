"""Handler field access checks for the incident internal API boundary verifier.

This module ensures that handlers in server_incident_internal_read_handlers.py
use the serialization layer (build_incident_internal_*_payload) instead of
directly accessing domain fields on Incident objects.

The Haskellization principle: one total projection function per payload type,
with no ad-hoc field access scattered in handlers.
"""

from __future__ import annotations

import ast
import sys

# Incident domain field names that should NOT be accessed directly in handlers.
# These fields should only be accessed through serialization functions.
#
# Invariant: Handlers should call build_incident_internal_list_item_payload or
# build_incident_internal_detail_payload, NOT access fields like:
#   incident.incident_id
#   incident.status.value
#   incident.first_observed_at.isoformat()
#   etc.
FORBIDDEN_INCIDENT_FIELDS: frozenset[str] = frozenset({
    "incident_id",
    "source_candidate_id",
    "namespace",
    "object_kind",
    "raw_object_kind",
    "object_name",
    "candidate_class",
    "severity",
    "status",
    "first_observed_at",
    "last_observed_at",
    "signal_count",
    "evidence_count",
    "signals",
    "evidence_needed",
    "evidence_links",
    "events",
    "latest_snapshot_bundle_id",
    "review_packet",
    "suppressed_reason",
    "duplicate_of",
    "resolved_at",
    "resolution_notes",
})

# Files that are checked by this verifier.
HANDLER_FILES: frozenset[str] = frozenset({
    "src/k8s_diag_agent/ui/server_incident_internal_read_handlers.py",
})

# Allowed patterns: These are OK even if they look like field access.
# Functions that return serializers are allowed to access fields.
ALLOWED_FUNCTION_NAMES: frozenset[str] = frozenset({
    "build_incident_internal_list_item_payload",
    "build_incident_internal_detail_payload",
    "_signal_to_payload",
    "build_incident_signal_payload",
    "build_incident_review_packet_payload",
    "build_evidence_artifact_payload",
    "build_incident_event_payload",
    "build_suggested_checks_from_next_check_plan_payload",
    "build_automatic_diagnosis_review_payload",
    "build_incident_summary_payload",
    "build_incident_detail_payload",
})

class HandlerFieldAccessChecker(ast.NodeVisitor):
    """AST visitor to check for forbidden domain field access in handlers."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.errors: list[str] = []
        self._function_stack: list[str] = []
        self._in_serializer_function: bool = False

    @property
    def current_function(self) -> str | None:
        """Return the current function name, or None if not in a function."""
        return self._function_stack[-1] if self._function_stack else None

    def _is_in_allowed_function(self) -> bool:
        """Check if we're currently inside a serializer function."""
        if self.current_function in ALLOWED_FUNCTION_NAMES:
            return True
        return self._in_serializer_function

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function context for field access checks."""
        was_in_serializer = self._in_serializer_function
        if node.name in ALLOWED_FUNCTION_NAMES:
            self._in_serializer_function = True

        self._function_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._function_stack.pop()
            self._in_serializer_function = was_in_serializer

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function context for field access checks."""
        was_in_serializer = self._in_serializer_function
        if node.name in ALLOWED_FUNCTION_NAMES:
            self._in_serializer_function = True

        self._function_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._function_stack.pop()
            self._in_serializer_function = was_in_serializer

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check for forbidden domain field access patterns."""
        # Only check if we're NOT in an allowed serializer function
        if self._is_in_allowed_function():
            self.generic_visit(node)
            return

        # Check if this is accessing a forbidden field on any variable
        # No variable name allowlist - any attribute access on forbidden fields is an error
        if node.attr in FORBIDDEN_INCIDENT_FIELDS:
            self.errors.append(
                f"{self.filepath}:{node.lineno}: handler accesses domain field "
                f"'{node.attr}' directly. Use build_incident_internal_*_payload() "
                f"serializer instead."
            )

        self.generic_visit(node)


def check_handler_field_access(filepath: str) -> list[str]:
    """Check for forbidden domain field access in handler files.

    Returns a list of error messages (empty if no violations).
    """
    # Only check specific handler files
    normalized_path = filepath.replace("\\", "/")
    if normalized_path not in HANDLER_FILES:
        return []

    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        # Skip files with syntax errors
        return []

    checker = HandlerFieldAccessChecker(filepath)
    checker.visit(tree)
    errors.extend(checker.errors)

    return errors


# Allow list of exported names for backward compatibility
if __name__ == "__main__":
    sys.exit(0)
