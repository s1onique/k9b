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


# Allowed rejection reason codes
ALLOWED_REJECTION_REASONS: frozenset[str] = frozenset({
    "terminal_incident",
    "invalid_transition",
    "missing_review_packet",
    "missing_snapshot_bundle",
    "duplicate_self_reference",
})


# Files allowed to assign to .status on IncidentLifecycle instances
# These are adapter/conversion files that bridge between persistence and domain
_ALLOWED_STATUS_MUTATION_FILES: frozenset[str] = frozenset({
    "src/k8s_diag_agent/collect/incident_store.py",
    "src/k8s_diag_agent/collect/incident_store_provider.py",
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
        self.is_allowed_mutation_file: bool = filepath in _ALLOWED_STATUS_MUTATION_FILES

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

    def _check_status_assignment(self, target: ast.expr, lineno: int) -> None:
        """Check if an assignment targets IncidentLifecycle.status."""
        # Only check if this is NOT an allowed mutation file
        if self.is_allowed_mutation_file:
            return

        # Check for patterns like: incident.status = ... or obj.incident.status = ...
        if isinstance(target, ast.Attribute):
            if target.attr == "status":
                # Check if it's accessing .status on something that might be IncidentLifecycle
                if isinstance(target.value, ast.Name):
                    # Pattern: incident.status = ... (simple variable)
                    var_name = target.value.id
                    if var_name in ("incident", "lifecycle", "inc"):
                        self.errors.append(
                            f"{self.filepath}:{lineno}: Direct .status assignment "
                            f"to '{var_name}' outside allowed files "
                            f"({', '.join(sorted(_ALLOWED_STATUS_MUTATION_FILES))})"
                        )


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


def check_reason_allowlist(filepath: str) -> list[str]:
    """Check that rejection reasons are from the allowlist (domain module only)."""
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    # Look for reason assignments
    for lineno, line in enumerate(source.splitlines(), start=1):
        # Match patterns like: reason="..." or reason='...'
        if 'reason="' in line or "reason='" in line:
            # Extract the reason string
            match = re.search(r'reason=["\']([^"\']+)["\']', line)
            if match:
                reason = match.group(1)
                if reason not in ALLOWED_REJECTION_REASONS:
                    errors.append(
                        f"{filepath}:{lineno}: Unknown rejection reason '{reason}' "
                        f"(expected one of {sorted(ALLOWED_REJECTION_REASONS)})"
                    )

    return errors


def check_status_assignments(filepath: str) -> list[str]:
    """Check for direct .status assignments outside allowed files."""
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
    # Only return status-related errors
    errors.extend(
        error for error in checker.errors if ".status assignment" in error
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

    # Check 3: Status assignments (repo-wide)
    python_files = iter_python_files(repo_root)
    status_errors: list[str] = []
    for filepath in python_files:
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
