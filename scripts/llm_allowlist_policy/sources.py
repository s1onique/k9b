"""Allowlist source parsing.

This module handles reading allowlist entries from the actual sources:
- scripts/llm_friendly_allowlist.py
- .llm-friendly-ignore files
"""

from __future__ import annotations

import re
from pathlib import Path

from .baseline import normalize_path


def parse_allowlist_from_python(python_path: Path) -> tuple[set[str], list[str]]:
    """Parse the allowlist from the Python module.

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
