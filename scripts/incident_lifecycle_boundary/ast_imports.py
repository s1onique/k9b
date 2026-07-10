"""Shared AST import resolution utilities.

Provides reusable helpers for resolving Python imports during AST analysis.
"""

from __future__ import annotations

import ast
from pathlib import Path


def resolve_import_source(node: ast.ImportFrom, filepath: str) -> str | None:
    """Resolve the file path for a from ... import statement.

    Returns the resolved file path if the module exists, None otherwise.

    Handles:
    - Relative imports (from .module import)
    - Absolute imports (from package.submodule import)
    - __future__ imports (skipped)
    - Importing from src/ when not found locally

    Args:
        node: The ast.ImportFrom node
        filepath: Path to the file containing the import

    Returns:
        Resolved file path or None
    """
    if node.module is None:
        return None

    # Skip __future__ imports
    if node.module == "__future__":
        return None

    current_dir = Path(filepath).parent
    module_path = node.module
    parts = module_path.split(".")

    # Handle relative imports
    # level=0: absolute import
    # level=1: from .module import (relative to current package)
    # level=2: from ..module import (parent package)
    # level=3: from ...module import (grandparent package)
    if node.level > 0:
        target_dir = current_dir
        # level=1 means current package, not parent - don't go up
        for _ in range(node.level - 1):
            target_dir = target_dir.parent
        if parts:
            candidate = target_dir.joinpath(*parts)
            if candidate.with_suffix(".py").exists():
                return str(candidate.with_suffix(".py"))
            if (candidate / "__init__.py").exists():
                return str(candidate / "__init__.py")
        return None

    # Handle absolute imports like k8s_diag_agent.collect.xxx
    # We need to find the repo root (where src/ is) and resolve from there

    # Find repo root by looking for src/ directory
    current = current_dir
    repo_root = None
    for _ in range(15):  # Limit search depth
        if (current / "src").exists():
            repo_root = current
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    if repo_root is not None:
        # Resolve from repo_root/src/
        src_candidate = repo_root / "src"
        src_candidate = src_candidate.joinpath(*parts)
        if src_candidate.with_suffix(".py").exists():
            return str(src_candidate.with_suffix(".py"))
        if (src_candidate / "__init__.py").exists():
            return str(src_candidate / "__init__.py")

    # Also try relative to current file (for relative absolute imports)
    candidate = current_dir.joinpath(*parts)
    if candidate.with_suffix(".py").exists():
        return str(candidate.with_suffix(".py"))
    if (candidate / "__init__.py").exists():
        return str(candidate / "__init__.py")

    return None


def iter_import_aliases(node: ast.ImportFrom) -> dict[str, str]:
    """Extract alias mapping from an ImportFrom node.

    Returns dict mapping local_name -> original_name.
    Handles aliased imports like: from foo import bar as baz

    Args:
        node: The ast.ImportFrom node

    Returns:
        Dict mapping local names to original names
    """
    aliases: dict[str, str] = {}
    if node.module is None:
        return aliases

    for alias_node in node.names:
        name = alias_node.name
        # Skip wildcard imports
        if name == "*":
            continue
        local_name = alias_node.asname if alias_node.asname else name
        aliases[local_name] = name

    return aliases


def collect_imports(tree: ast.AST, filepath: str) -> tuple[dict[str, str], dict[str, str]]:
    """Collect import information from an AST.

    Args:
        tree: Parsed AST tree
        filepath: Path to the file

    Returns:
        Tuple of (import_sources, imported_names):
        - import_sources: local_name -> module_path
        - imported_names: local_name -> original_name
    """
    import_sources: dict[str, str] = {}
    imported_names: dict[str, str] = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom):
            resolved = resolve_import_source(node, filepath)
            if resolved:
                for local_name, original_name in iter_import_aliases(node).items():
                    import_sources[local_name] = resolved
                    imported_names[local_name] = original_name

    return import_sources, imported_names
