"""Forbidden import checks for the incident lifecycle boundary verifier."""

from __future__ import annotations

import ast
import sys

# Modules that the domain module must NOT import (top-level and dotted)
FORBIDDEN_IMPORT_PREFIXES: frozenset[str] = frozenset({
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
        for forbidden in FORBIDDEN_IMPORT_PREFIXES
    )


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


# Allow list of exported names for backward compatibility
if __name__ == "__main__":
    sys.exit(0)
