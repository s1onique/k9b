#!/usr/bin/env python3
"""Boundary verifier for incident lifecycle domain module.

This script checks that the incident lifecycle domain module maintains proper
boundaries and does not leak IO, Kubernetes, HTTP, subprocess, or store dependencies.

Checks performed:
1. incident_lifecycle.py does not import forbidden modules (including dotted imports).
2. Transition reason strings remain in an allowlist (domain module only).
3. Direct status assignments outside allowlisted files are detected (repo-wide).
4. Domain module remains pure (no IO dependencies).
5. Store modules reference typed lifecycle core functions.

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
    2 - Script error (e.g., file not found)
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Modules that the domain module must NOT import (top-level and dotted)
_FORBIDDEN_IMPORT_PREFIXES: frozenset[str] = frozenset({
    "subprocess",
    "requests",
    "httpx",
    "kubernetes",
    "fastapi",
    "flask",
    "aiohttp",
    "urllib3",
    # Filesystem writing helpers (forbidden for pure domain)
    "pathlib",
    "os",
    "shutil",
    # Store adapters
    "k8s_diag_agent.collect.incident_store",
    "k8s_diag_agent.collect.incident_store_provider",
    # Logging (pure functions should not log)
    "logging",
    # Random (pure functions should be deterministic)
    "random",
})


def _is_forbidden_module(module: str) -> bool:
    """Check if a module matches any forbidden import prefix.

    Handles both top-level imports (e.g., 'subprocess') and
    dotted imports (e.g., 'k8s_diag_agent.collect.incident_store').
    """
    return any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for forbidden in _FORBIDDEN_IMPORT_PREFIXES
    )


# Allowed rejection reason codes (derived from TransitionRejectionReason alias)
ALLOWED_REJECTION_REASONS: frozenset[str] = frozenset({
    "terminal_incident",
    "invalid_transition",
    "missing_review_packet",
    "missing_snapshot_bundle",
    "duplicate_self_reference",
})

# Stable public contract for rejection reasons (cross-check against typed alias)
EXPECTED_STABLE_REJECTION_REASONS: frozenset[str] = frozenset({
    "terminal_incident",
    "invalid_transition",
    "missing_review_packet",
    "missing_snapshot_bundle",
    "duplicate_self_reference",
})


# Functions allowed to project lifecycle status back into the persistence model.
# Only the adapter function that applies typed domain state may assign incident.status.
_ALLOWED_STATUS_PROJECTION_FUNCTIONS: frozenset[tuple[str, str]] = frozenset({
    (
        "src/k8s_diag_agent/collect/incident_lifecycle_domain_adapter.py",
        "_apply_lifecycle_transition",
    ),
})


# Required lifecycle transition function CALLS in the transitions module
# These must be actual AST.Call nodes, not just string presence
_REQUIRED_LIFECYCLE_CALLS: frozenset[str] = frozenset({
    "domain_mark_collecting_evidence",
    "domain_mark_ready_for_review",
    "domain_mark_investigating",
    "domain_suppress_incident",
    "domain_mark_duplicate",
    "domain_resolve_incident",
})


class BoundaryChecker(ast.NodeVisitor):
    """AST visitor to check for domain boundary violations."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.errors: list[str] = []
        self.imports: list[str] = []
        self.is_domain_module: bool = "domain/incident_lifecycle" in filepath
        self._function_stack: list[str] = []

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
        ) in _ALLOWED_STATUS_PROJECTION_FUNCTIONS

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

    def visit_Import(self, node: ast.Import) -> None:
        """Check import statements."""
        for alias in node.names:
            name = alias.name
            if _is_forbidden_module(name):
                self.errors.append(
                    f"{self.filepath}:{node.lineno}: Forbidden import '{name}'"
                )
            self.imports.append(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from ... import statements."""
        if node.module:
            module = node.module
            if _is_forbidden_module(module):
                self.errors.append(
                    f"{self.filepath}:{node.lineno}: "
                    f"Forbidden import '{module}' from 'from {module} import ...'"
                )
        self.generic_visit(node)

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


def check_forbidden_imports(filepath: str) -> list[str]:
    """Check that a module doesn't import forbidden dependencies."""
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        return [f"Syntax error in {filepath}: {e}"]

    checker = BoundaryChecker(filepath)
    checker.visit(tree)
    errors.extend(checker.errors)

    return errors


def _is_literal_subscript(node: ast.Subscript) -> bool:
    """Check if subscript is Literal[...] or typing.Literal[...], not another type.

    This ensures we only extract from actual Literal types, not from
    incorrectly named types like NotLiteral[...] or Sequence[...].
    """
    if isinstance(node.value, ast.Name):
        return node.value.id == "Literal"
    if isinstance(node.value, ast.Attribute):
        # Handle: typing.Literal[...]
        return node.value.attr == "Literal"
    return False


def _extract_literal_string_args(node: ast.expr) -> set[str]:
    """Extract string literal arguments from a Literal[...] subscript.

    Handles:
    - Literal["a", "b"]
    - Literal["a"]  (single element)
    - typing.Literal["a", "b"]

    Returns empty set if node is not a Literal subscript.
    """
    reasons: set[str] = set()

    # Handle subscript: must be Literal[...] specifically
    if isinstance(node, ast.Subscript):
        # REJECT: NotLiteral[...] or other non-Literal subscripts
        if not _is_literal_subscript(node):
            return reasons

        # The slice contains the literal values (e.g., "a", "b")
        slice_node = node.slice

        # Single element: Literal["a"]
        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
            reasons.add(slice_node.value)
        # Tuple of elements: Literal["a", "b"]
        elif isinstance(slice_node, ast.Tuple):
            for elt in slice_node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    reasons.add(elt.value)

    return reasons


def extract_transition_rejection_reasons(filepath: str) -> set[str]:
    """Extract rejection reason values from TransitionRejectionReason alias using AST.

    Parses the module and finds an assignment named `TransitionRejectionReason`
    with a Literal[...] value.

    Supports:
    - TransitionRejectionReason = Literal["a", "b"]
    - TransitionRejectionReason: TypeAlias = Literal["a", "b"]

    Returns:
        Set of string literal values from the alias, or empty set if not found.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return set()

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return set()

    for node in tree.body:
        target_name: str | None = None
        value: ast.expr | None = None

        # Simple assignment: TransitionRejectionReason = Literal[...]
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == "TransitionRejectionReason":
                    target_name = node.targets[0].id
                    value = node.value

        # Annotated assignment: TransitionRejectionReason = Literal[...] (no annotation)
        # or TransitionRejectionReason: TypeAlias = Literal[...]
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id == "TransitionRejectionReason":
                    target_name = node.target.id
                    value = node.value

        if target_name == "TransitionRejectionReason" and value is not None:
            return _extract_literal_string_args(value)

    return set()


def check_rejection_reason_type_alias(filepath: str) -> list[str]:
    """Check that TransitionRejectionReason alias exists and is properly typed.

    Verifies:
    - TransitionRejectionReason alias exists
    - Alias contains values (not empty)
    - Alias values match the expected stable public contract
    - TransitionRejected class exists
    - TransitionRejected.reason field exists and is annotated as TransitionRejectionReason
    """
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    # Extract reasons from the alias
    extracted_reasons = extract_transition_rejection_reasons(filepath)

    if not extracted_reasons:
        errors.append(
            f"{filepath}: TransitionRejectionReason alias missing or empty. "
            f"Expected a Literal[...] with rejection reason codes."
        )
        return errors

    # Check that extracted reasons match the expected stable contract
    if extracted_reasons != EXPECTED_STABLE_REJECTION_REASONS:
        missing = EXPECTED_STABLE_REJECTION_REASONS - extracted_reasons
        extra = extracted_reasons - EXPECTED_STABLE_REJECTION_REASONS
        if missing:
            errors.append(
                f"{filepath}: TransitionRejectionReason missing expected values: {sorted(missing)}"
            )
        if extra:
            errors.append(
                f"{filepath}: TransitionRejectionReason has unexpected values: {sorted(extra)}"
            )

    # Check TransitionRejected class and reason field
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return errors

    found_transition_rejected = False
    found_reason_field = False
    reason_correctly_typed = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TransitionRejected":
            found_transition_rejected = True
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name) and item.target.id == "reason":
                        found_reason_field = True
                        # Check if type annotation is exactly TransitionRejectionReason
                        if isinstance(item.annotation, ast.Name):
                            if item.annotation.id == "TransitionRejectionReason":
                                reason_correctly_typed = True
                            elif item.annotation.id in ("str", "object", "Any"):
                                errors.append(
                                    f"{filepath}:{item.lineno}: "
                                    f"TransitionRejected.reason is typed as '{item.annotation.id}' (too wide), "
                                    f"should be 'TransitionRejectionReason'"
                                )
                        # Also check for typing.String, Sequence, etc. (too wide)
                        elif isinstance(item.annotation, ast.Subscript):
                            if isinstance(item.annotation.value, ast.Name):
                                wide_types = ("String", "Sequence", "List", "Iterable", "Collection")
                                if item.annotation.value.id in wide_types:
                                    errors.append(
                                        f"{filepath}:{item.lineno}: "
                                        f"TransitionRejected.reason uses {item.annotation.value.id}[...] (too wide), "
                                        f"should be 'TransitionRejectionReason'"
                                    )

    # Require TransitionRejected class to exist
    if not found_transition_rejected:
        errors.append(
            f"{filepath}: TransitionRejected class is missing. "
            f"Expected a dataclass with reason field typed as TransitionRejectionReason."
        )

    # Require reason field to exist
    if found_transition_rejected and not found_reason_field:
        errors.append(
            f"{filepath}: TransitionRejected.reason field is missing. "
            f"Expected: reason: TransitionRejectionReason"
        )

    # Require reason field to be correctly typed
    if found_reason_field and not reason_correctly_typed:
        errors.append(
            f"{filepath}: TransitionRejected.reason must be annotated as "
            f"'TransitionRejectionReason', not 'str', 'object', or other widened types."
        )

    return errors


def check_reason_allowlist(filepath: str) -> list[str]:
    """Check that rejection reasons are from the allowlist (domain module only).

    Uses AST extraction to derive allowed reasons from TransitionRejectionReason alias.
    """
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    # Derive allowed reasons from the typed alias
    allowed_reasons = extract_transition_rejection_reasons(filepath)

    if not allowed_reasons:
        # Fallback to static allowlist if extraction fails
        allowed_reasons = set(ALLOWED_REJECTION_REASONS)

    # Look for reason assignments
    for lineno, line in enumerate(source.splitlines(), start=1):
        # Match patterns like: reason="..." or reason='...'
        if 'reason="' in line or "reason='" in line:
            # Extract the reason string
            match = re.search(r'reason=["\']([^"\']+)["\']', line)
            if match:
                reason = match.group(1)
                if reason not in allowed_reasons:
                    errors.append(
                        f"{filepath}:{lineno}: Unknown rejection reason '{reason}' "
                        f"(expected one of {sorted(allowed_reasons)})"
                    )

    return errors


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

    checker = BoundaryChecker(filepath)
    checker.visit(tree)
    # Return all status-related errors (both assignment and replace projection)
    errors.extend(
        error for error in checker.errors
        if ".status assignment" in error or "status projection" in error
    )

    return errors


def _get_called_names(tree: ast.AST) -> set[str]:
    """Extract all function call names from an AST."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def check_transition_adapter_uses_lifecycle_core(filepath: str) -> list[str]:
    """Check that transition adapter calls typed lifecycle transition functions.

    This ensures that lifecycle transitions go through the typed domain core
    via actual function calls, not just imports or string presence.

    Uses AST analysis to verify that required domain functions are actually
    called, not just imported or commented.
    """
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        return [f"Syntax error in {filepath}: {e}"]

    # Get all function calls via AST
    called_names = _get_called_names(tree)

    # Check for required function calls
    for required_call in _REQUIRED_LIFECYCLE_CALLS:
        if required_call not in called_names:
            errors.append(
                f"{filepath}: Missing required lifecycle core CALL '{required_call}'. "
                f"Transition adapter must CALL typed domain functions, not just import them."
            )

    return errors


def iter_python_files(root: Path) -> list[Path]:
    """Iterate over all Python files in a directory, excluding virtual envs."""
    return [
        path
        for path in root.rglob("*.py")
        if ".venv" not in path.parts and "__pycache__" not in path.parts
    ]


# Files excluded from status projection checks.
# After ACT-K9B-HULK-LEGACY-INCIDENT-TRANSITIONS-RETIRE01, no files are excluded.
# The only allowed status projection is in:
#   incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition
#
# Invariant: Direct status projection is forbidden except:
# 1. incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition (primary seam)
_EXCLUDED_FROM_STATUS_CHECKS: frozenset[str] = frozenset()


def main(argv: list[str] | None = None) -> int:
    """Run boundary checks."""
    if argv is None:
        argv = sys.argv

    # Default paths
    domain_module = Path("src/k8s_diag_agent/domain/incident_lifecycle.py")
    transitions_module = Path("src/k8s_diag_agent/collect/incident_lifecycle_transitions.py")
    repo_root = Path("src")

    errors: list[str] = []

    # Check domain module exists
    if not domain_module.exists():
        errors.append(f"Domain module not found: {domain_module}")
        print("\n".join(errors))
        return 2

    # Check 1: Domain module imports (no forbidden dependencies)
    import_errors = check_forbidden_imports(str(domain_module))
    if import_errors:
        errors.extend(import_errors)

    # Check 2: Rejection reasons are in allowlist (domain module only)
    reason_errors = check_reason_allowlist(str(domain_module))
    if reason_errors:
        errors.extend(reason_errors)

    # Check 2b: TransitionRejectionReason alias is properly typed
    type_alias_errors = check_rejection_reason_type_alias(str(domain_module))
    if type_alias_errors:
        errors.extend(type_alias_errors)

    # Check 3: Status assignments (repo-wide)
    python_files = iter_python_files(repo_root)
    status_errors: list[str] = []
    for filepath in python_files:
        # Skip files excluded from status checks (legacy files being phased out)
        if str(filepath) in _EXCLUDED_FROM_STATUS_CHECKS:
            continue
        file_errors = check_status_assignments(str(filepath))
        status_errors.extend(file_errors)

    if status_errors:
        errors.extend(status_errors)

    # Check 4: Transition adapter calls typed lifecycle core (transitions module only)
    if transitions_module.exists():
        transition_errors = check_transition_adapter_uses_lifecycle_core(str(transitions_module))
        errors.extend(transition_errors)

    # Report results
    if errors:
        print("BOUNDARY VERIFICATION FAILED")
        print("=" * 60)
        for error in errors:
            print(f"  {error}")
        print("=" * 60)
        print(f"Found {len(errors)} boundary violation(s)")
        return 1
    else:
        print("BOUNDARY VERIFICATION PASSED")
        print("=" * 60)
        print("  Domain module has no forbidden imports")
        print("  Rejection reasons are in allowlist")
        print("  No direct .status mutations detected outside allowed files")
        print("  Transition adapter calls typed lifecycle core functions")
        print("  Module is isolated from IO, Kubernetes, HTTP dependencies")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
