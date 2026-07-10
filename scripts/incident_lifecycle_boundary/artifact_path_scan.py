"""AST scanning utilities for artifact path verification.

This module contains:
- extract_path_newtype_aliases(): Extract NewType aliases from Python file
- extract_constructor_functions(): Extract function definitions from Python file
- _extract_aliases_from_file(): Internal helper for alias extraction
- _extract_constructors_from_file(): Internal helper for constructor extraction

Uses AST parsing to analyze Python source files for type definitions.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .ast_imports import iter_import_aliases, resolve_import_source


def _extract_aliases_from_file(filepath: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Extract NewType aliases and import info from a single file.

    Returns:
        Tuple of (aliases, import_sources, imported_names):
        - aliases: local_name -> base_type
        - import_sources: local_name -> module_path
        - imported_names: local_name -> original_name
    """
    aliases: dict[str, str] = {}
    import_sources: dict[str, str] = {}
    imported_names: dict[str, str] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return aliases, import_sources, imported_names

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return aliases, import_sources, imported_names

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            resolved = resolve_import_source(node, filepath)
            if resolved:
                for local_name, original_name in iter_import_aliases(node).items():
                    import_sources[local_name] = resolved
                    imported_names[local_name] = original_name

        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target_name = node.targets[0].id
                value = node.value
                if isinstance(value, ast.Call):
                    if isinstance(value.func, ast.Name) and value.func.id == "NewType":
                        if len(value.args) >= 2:
                            second_arg = value.args[1]
                            if isinstance(second_arg, ast.Name) and second_arg.id == "str":
                                aliases[target_name] = "str"
                            elif isinstance(second_arg, ast.Constant) and second_arg.value == "str":
                                aliases[target_name] = "str"

    return aliases, import_sources, imported_names


def extract_path_newtype_aliases(
    filepath: str,
    _visited: set[str] | None = None,
    _cache: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    """Extract path/reference NewType aliases from a Python file.

    Recursively follows imports to find definitions in imported modules.
    Uses memoization to avoid re-parsing files.
    Uses separate visited set to prevent infinite recursion on cycles.

    Returns:
        Dict mapping alias name to base type (e.g., {"SafeRelativeArtifactPath": "str"}).
    """
    if _visited is None:
        _visited = set()
    if _cache is None:
        _cache = {}

    real_path = str(Path(filepath).resolve())

    # Return cached result if available
    if real_path in _cache:
        return _cache[real_path]

    # Cycle detection - return empty if already being processed
    if real_path in _visited:
        return {}

    # Mark as being processed (for cycle detection)
    _visited.add(real_path)

    # Extract from this file
    aliases, import_sources, imported_names = _extract_aliases_from_file(filepath)

    # Recursively follow imports for names not found at top level
    for local_name, module_path in import_sources.items():
        if local_name not in aliases:
            # Recursive call - it will use visited set for cycle detection
            # and share the cache for memoization
            mod_aliases = extract_path_newtype_aliases(module_path, _visited, _cache)
            original = imported_names.get(local_name, local_name)
            if original in mod_aliases:
                aliases[local_name] = mod_aliases[original]

    # Cache the completed result.
    _cache[real_path] = aliases

    # Remove from visited set - allow re-entry from different paths
    _visited.discard(real_path)

    return aliases


def _extract_constructors_from_file(filepath: str) -> tuple[set[str], dict[str, str], dict[str, str]]:
    """Extract constructor functions and import info from a single file.

    Returns:
        Tuple of (constructors, import_sources, imported_names):
        - constructors: set of function names
        - import_sources: local_name -> module_path
        - imported_names: local_name -> original_name
    """
    constructors: set[str] = set()
    import_sources: dict[str, str] = {}
    imported_names: dict[str, str] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return constructors, import_sources, imported_names

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return constructors, import_sources, imported_names

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            resolved = resolve_import_source(node, filepath)
            if resolved:
                for local_name, original_name in iter_import_aliases(node).items():
                    import_sources[local_name] = resolved
                    imported_names[local_name] = original_name

        if isinstance(node, ast.FunctionDef):
            constructors.add(node.name)

    return constructors, import_sources, imported_names


def extract_constructor_functions(
    filepath: str,
    _visited: set[str] | None = None,
    _cache: dict[str, set[str]] | None = None,
) -> set[str]:
    """Extract function definitions that are constructors from a Python file.

    Recursively follows imports to find definitions in imported modules.
    Uses memoization to avoid re-parsing files.
    Uses separate visited set to prevent infinite recursion on cycles.

    Returns:
        Set of function names that are defined in the file.
    """
    if _visited is None:
        _visited = set()
    if _cache is None:
        _cache = {}

    real_path = str(Path(filepath).resolve())

    # Return cached result if available
    if real_path in _cache:
        return _cache[real_path]

    # Cycle detection - return empty if already being processed
    if real_path in _visited:
        return set()

    # Mark as being processed (for cycle detection)
    _visited.add(real_path)

    # Extract from this file
    constructors, import_sources, imported_names = _extract_constructors_from_file(filepath)

    # Recursively follow imports for names not found at top level
    for local_name, module_path in import_sources.items():
        if local_name not in constructors:
            # Recursive call - it will use visited set for cycle detection
            # and share the cache for memoization
            mod_constructors = extract_constructor_functions(module_path, _visited, _cache)
            original = imported_names.get(local_name, local_name)
            if original in mod_constructors:
                constructors.add(local_name)

    # Cache the completed result.
    _cache[real_path] = constructors

    # Remove from visited set - allow re-entry from different paths
    _visited.discard(real_path)

    return constructors


__all__ = [
    "extract_path_newtype_aliases",
    "extract_constructor_functions",
]
