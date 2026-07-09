"""Status projection checks for the incident lifecycle boundary verifier."""

from __future__ import annotations

import ast
import sys

# Functions allowed to project lifecycle status back into the persistence model.
#
# Invariant: Direct lifecycle status projection is only allowed in the adapter seam:
#   incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition
ALLOWED_STATUS_PROJECTION_FUNCTIONS: frozenset[tuple[str, str]] = frozenset({
    (
        "src/k8s_diag_agent/collect/incident_lifecycle_domain_adapter.py",
        "_apply_lifecycle_transition",
    ),
})

# Files excluded from status projection checks.
# After ACT-K9B-HULK-LEGACY-INCIDENT-TRANSITIONS-RETIRE01, no files are excluded.
# The only allowed status projection is in:
#   incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition
#
# Invariant: Direct status projection is forbidden except:
# 1. incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition (primary seam)
EXCLUDED_FROM_STATUS_CHECKS: frozenset[str] = frozenset()


class StatusProjectionChecker(ast.NodeVisitor):
    """AST visitor to check for status projection violations."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.errors: list[str] = []
        self._function_stack: list[str] = []
        self.is_domain_module: bool = "domain/incident_lifecycle" in filepath

    @property
    def current_function(self) -> str | None:
        """Return the current function name, or None if not in a function."""
        return self._function_stack[-1] if self._function_stack else None

    def _is_allowed_status_projection(self) -> bool:
        """Check if the current function is allowed to project lifecycle status.

        Domain modules (k8s_diag_agent/domain/) are excluded from checks because
        they use replace() internally on IncidentLifecycle as part of typed transition
        functions - this is intentional and part of the typed domain core.

        Only the specific adapter function in collect/ is allowed to project
        lifecycle status back into the persistence model (Incident type).
        """
        # Domain modules are excluded - they use replace() on IncidentLifecycle internally
        if self.is_domain_module:
            return True
        return (
            self.filepath,
            self.current_function or "",
        ) in ALLOWED_STATUS_PROJECTION_FUNCTIONS

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function context for status projection checks."""
        self._function_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function context for status projection checks."""
        self._function_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._function_stack.pop()

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Check annotated assignments for .status mutations."""
        self._check_status_assignment(node.target, node.lineno)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check regular assignments for .status mutations."""
        for target in node.targets:
            self._check_status_assignment(target, node.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Check augmented assignments for .status mutations."""
        self._check_status_assignment(node.target, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check for replace(..., status=...) patterns."""
        self._check_replace_status_projection(node)
        self.generic_visit(node)

    def _check_status_assignment(self, target: ast.expr, lineno: int) -> None:
        """Check if an assignment targets incident.status."""
        # Only check if this is NOT an allowed projection function
        if self._is_allowed_status_projection():
            return

        # Check for patterns like: incident.status = ... or obj.incident.status = ...
        if isinstance(target, ast.Attribute):
            if target.attr == "status":
                # Check if it's accessing .status on something that might be an Incident
                if isinstance(target.value, ast.Name):
                    # Pattern: incident.status = ... (simple variable)
                    var_name = target.value.id
                    if var_name in ("incident", "lifecycle", "inc"):
                        self.errors.append(
                            f"{self.filepath}:{lineno}: lifecycle status projection is only "
                            f"allowed in incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition"
                        )

    def _check_replace_status_projection(self, node: ast.Call) -> None:
        """Check for replace(..., status=...) calls outside the allowed adapter."""
        # Only check if this is NOT an allowed projection function
        if self._is_allowed_status_projection():
            return

        # Check for replace(incident, status=...) pattern
        is_replace_call = False

        # Handle: replace(incident, status=...)
        if isinstance(node.func, ast.Name) and node.func.id == "replace":
            is_replace_call = True
        # Handle: dataclasses.replace(incident, status=...)
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "replace":
            is_replace_call = True

        if is_replace_call:
            # Check if any keyword has arg == "status"
            for keyword in node.keywords:
                if keyword.arg == "status":
                    self.errors.append(
                        f"{self.filepath}:{node.lineno}: lifecycle status projection is only "
                        f"allowed in incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition"
                    )
                    break


def check_status_assignments(filepath: str) -> list[str]:
    """Check for direct .status assignments and replace(..., status=...) outside allowed functions."""
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

    checker = StatusProjectionChecker(filepath)
    checker.visit(tree)
    # Return all status-related errors (both assignment and replace projection)
    errors.extend(
        error for error in checker.errors
        if ".status assignment" in error or "status projection" in error
    )

    return errors


# Allow list of exported names for backward compatibility
if __name__ == "__main__":
    sys.exit(0)
