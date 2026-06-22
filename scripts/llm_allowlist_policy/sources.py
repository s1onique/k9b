"""Allowlist source parsing.

This module handles reading allowlist entries from the actual sources:
- scripts/llm_friendly_allowlist.py
- .llm-friendly-ignore files

Supports AST parsing for Python files where possible, with regex fallback.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .baseline import normalize_path


class AllowlistExtractor(ast.NodeVisitor):
    """AST visitor that extracts ALLOWLIST entries from Python modules."""

    def __init__(self) -> None:
        self.paths: set[str] = set()
        self.errors: list[str] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit assignment nodes to find ALLOWLIST assignments."""
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "ALLOWLIST":
                self._extract_from_list(node.value)
        self.generic_visit(node)

    def _extract_from_list(self, node: ast.expr) -> None:
        """Extract tuple entries from a list expression.
        
        FAILS CLOSED: If ALLOWLIST is not a literal list, this is an error.
        """
        if isinstance(node, ast.List):
            for elt in node.elts:
                self._extract_tuple_entry(elt)
        elif isinstance(node, ast.Name):
            # FAIL CLOSED: Variable reference is not acceptable
            # ALLOWLIST must be a literal list of tuples
            self.errors.append(
                f"ALLOWLIST is a variable reference ({node.id}), not a literal list. "
                "Only literal ALLOWLIST = [(path, reason), ...] is acceptable."
            )
        else:
            self.errors.append(f"Unexpected ALLOWLIST structure type: {type(node).__name__}")

    def _extract_tuple_entry(self, node: ast.expr) -> None:
        """Extract (path, reason) tuple entry."""
        if isinstance(node, ast.Tuple):
            if len(node.elts) >= 1:
                first_elt = node.elts[0]
                if isinstance(first_elt, ast.Constant) and isinstance(first_elt.value, str):
                    normalized = normalize_path(first_elt.value)
                    self.paths.add(normalized)
                elif isinstance(first_elt, ast.Str):  # Python 3.7 compatibility
                    if isinstance(first_elt.s, str):
                        normalized = normalize_path(first_elt.s)
                        self.paths.add(normalized)
                    else:
                        self.errors.append(f"Unexpected ast.Str value type: {type(first_elt.s).__name__}")
                else:
                    self.errors.append(f"Unexpected tuple first element type: {type(first_elt).__name__}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Single string (edge case)
            normalized = normalize_path(node.value)
            self.paths.add(normalized)


def parse_allowlist_from_python(python_path: Path) -> tuple[set[str], list[str]]:
    """Parse the allowlist from the Python module.

    Uses AST parsing where possible, with regex fallback for edge cases.
    If AST parsing fails critically, falls back to regex-only.

    Returns:
        (paths, errors) where paths is a set of allowlisted paths
    """
    errors: list[str] = []
    paths: set[str] = set()

    if not python_path.exists():
        errors.append(f"Allowlist Python file not found: {python_path}")
        return paths, errors

    try:
        with open(python_path, encoding="utf-8") as f:
            content = f.read()

        # Try AST parsing first (preferred)
        try:
            tree = ast.parse(content, filename=str(python_path))
            extractor = AllowlistExtractor()
            extractor.visit(tree)
            
            # Only use AST results if we found the ALLOWLIST variable
            if extractor.paths or "ALLOWLIST" in content:
                paths.update(extractor.paths)
                errors.extend(extractor.errors)
                return paths, errors
        except SyntaxError as e:
            errors.append(f"AST parse error: {e} - falling back to regex")
        except ValueError as e:
            errors.append(f"AST value error: {e} - falling back to regex")

        # Regex fallback
        pattern = r'\("([^"]+)",\s*"([^"]+)"\)'
        matches = re.findall(pattern, content)

        for path, _reason in matches:
            normalized = normalize_path(path)
            paths.add(normalized)

    except OSError as e:
        errors.append(f"Cannot read allowlist Python file: {e}")
    except re.error as e:
        errors.append(f"Regex error parsing allowlist: {e}")

    return paths, errors


def find_llm_friendly_ignore_files(
    repo_root: Path,
) -> tuple[dict[str, str], list[str]]:
    """Find all .llm-friendly-ignore files and parse their contents.

    CRITICAL: This function FAILS on repo escape attempts.
    Entries that resolve outside the repo are not silently ignored -
    they are reported as policy errors.

    Returns:
        (file_entries, errors) where file_entries maps actual file path to ignore_file path
    """
    errors: list[str] = []
    file_entries: dict[str, str] = {}

    for ignore_file in repo_root.rglob(".llm-friendly-ignore"):
        try:
            with open(ignore_file, encoding="utf-8") as f:
                lines = f.readlines()

            ignore_dir = ignore_file.parent
            ignore_file_rel = str(ignore_file.relative_to(repo_root))

            for line_num, line in enumerate(lines, start=1):
                line = line.strip()
                if line and not line.startswith("#"):
                    # The line is relative to the ignore file's directory
                    ignored_file = (ignore_dir / line).resolve()
                    try:
                        ignored_file_rel = str(
                            ignored_file.relative_to(repo_root.resolve())
                        )
                        file_entries[normalize_path(ignored_file_rel)] = (
                            ignore_file_rel
                        )
                    except ValueError:
                        # CRITICAL: File escapes repo - this is a POLICY ERROR
                        # Not silently ignored - must be reported
                        escaped_path = str(ignored_file)
                        errors.append(
                            f"{ignore_file_rel}:{line_num}: "
                            f"Path '{escaped_path}' escapes repo boundary. "
                            "This is not allowed in .llm-friendly-ignore files."
                        )
        except OSError as e:
            errors.append(f"Cannot read {ignore_file}: {e}")

    return file_entries, errors


def get_current_allowlist_entries(
    repo_root: Path,
) -> tuple[set[str], list[str]]:
    """Get all current allowlist entries from all sources.

    Returns:
        (paths, errors)
    """
    all_paths: set[str] = set()
    all_errors: list[str] = []

    allowlist_py = repo_root / "scripts" / "llm_friendly_allowlist.py"
    py_paths, py_errors = parse_allowlist_from_python(allowlist_py)
    all_paths.update(py_paths)
    all_errors.extend(py_errors)

    ignore_files, ignore_errors = find_llm_friendly_ignore_files(repo_root)
    all_errors.extend(ignore_errors)

    for actual_file, ignore_file in ignore_files.items():
        all_paths.add(f"{actual_file}:{ignore_file}")

    return all_paths, all_errors
