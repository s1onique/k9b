"""Transition adapter lifecycle core call checks for the incident lifecycle boundary verifier."""

from __future__ import annotations

import ast
import sys

# Required lifecycle transition function CALLS in the transitions module
# These must be actual AST.Call nodes, not just string presence
REQUIRED_LIFECYCLE_CALLS: frozenset[str] = frozenset({
    "domain_mark_collecting_evidence",
    "domain_mark_ready_for_review",
    "domain_mark_investigating",
    "domain_suppress_incident",
    "domain_mark_duplicate",
    "domain_resolve_incident",
})


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
    for required_call in REQUIRED_LIFECYCLE_CALLS:
        if required_call not in called_names:
            errors.append(
                f"{filepath}: Missing required lifecycle core CALL '{required_call}'. "
                f"Transition adapter must CALL typed domain functions, not just import them."
            )

    return errors


# Allow list of exported names for backward compatibility
if __name__ == "__main__":
    sys.exit(0)
