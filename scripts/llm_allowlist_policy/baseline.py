"""Baseline CSV parsing and validation.

This module handles reading and validating the machine-readable baseline ledger.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Expected CSV headers
EXPECTED_HEADERS = ["path", "source", "reason", "owner", "status", "migration_note"]

# Valid source values
VALID_SOURCES = {"llm_friendly_allowlist_py", "llm-friendly-ignore"}

# Valid status values
VALID_STATUSES = {"grandfathered", "planned_removal"}


def normalize_path(path_str: str) -> str:
    """Normalize a path to repo-relative POSIX format."""
    path_str = path_str.replace("\\", "/")
    path_str = path_str.lstrip("/")
    return path_str


def is_valid_repo_path(path_str: str) -> tuple[bool, str]:
    """Check if a path is a valid repo-relative path.

    Returns:
        (is_valid, error_message)
    """
    if not path_str:
        return False, "Path is empty"

    if "\x00" in path_str:
        return False, "Path contains null byte"

    parts = path_str.split("/")
    depth = 0
    for part in parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                return False, f"Path escapes repo: {path_str}"
        elif part and part != ".":
            depth += 1

    if path_str.startswith(".."):
        return False, f"Path starts with '..': {path_str}"

    suspicious = ["~", "`"]
    for pattern in suspicious:
        if pattern in path_str:
            return False, f"Path contains suspicious pattern: {pattern}"

    return True, ""


def validate_baseline_row(row: dict, line_num: int) -> list[str]:
    """Validate a single baseline CSV row.

    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    path = row.get("path", "").strip()

    for field in EXPECTED_HEADERS:
        value = row.get(field, "").strip()
        if not value:
            errors.append(f"Line {line_num}: Missing required field '{field}'")

    if path:
        normalized = normalize_path(path)
        is_valid, error_msg = is_valid_repo_path(normalized)
        if not is_valid:
            errors.append(f"Line {line_num}: Invalid path '{path}': {error_msg}")

    source = row.get("source", "").strip()
    if source and source not in VALID_SOURCES:
        errors.append(
            f"Line {line_num}: Invalid source '{source}'. "
            f"Must be one of: {sorted(VALID_SOURCES)}"
        )

    status = row.get("status", "").strip()
    if status and status not in VALID_STATUSES:
        errors.append(
            f"Line {line_num}: Invalid status '{status}'. "
            f"Must be one of: {sorted(VALID_STATUSES)}"
        )

    return errors


def check_baseline_duplicates(entries: list[dict]) -> list[str]:
    """Check for duplicate paths in baseline.

    Returns:
        List of error messages
    """
    errors = []
    seen: dict[str, int] = {}

    for entry in entries:
        path = normalize_path(entry.get("path", "").strip())
        if path in seen:
            errors.append(
                f"Duplicate baseline entry for path: {path} "
                "(first seen earlier, duplicates ignored)"
            )
        else:
            seen[path] = 1

    return errors


def parse_baseline_csv(csv_path: Path) -> tuple[list[dict], list[str]]:
    """Parse the baseline CSV file.

    Returns:
        (entries, errors) where entries is a list of dicts and errors is a list of error messages
    """
    errors: list[str] = []
    entries: list[dict] = []

    if not csv_path.exists():
        errors.append(f"Baseline CSV not found: {csv_path}")
        return entries, errors

    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except csv.Error as e:
        errors.append(f"CSV parse error: {e}")
        return entries, errors
    except OSError as e:
        errors.append(f"Cannot read baseline CSV: {e}")
        return entries, errors

    if not rows:
        errors.append("Baseline CSV is empty")
        return entries, errors

    actual_headers = list(rows[0].keys()) if rows else []
    if actual_headers != EXPECTED_HEADERS:
        missing = set(EXPECTED_HEADERS) - set(actual_headers)
        extra = set(actual_headers) - set(EXPECTED_HEADERS)
        if missing:
            errors.append(f"Missing required headers: {sorted(missing)}")
        if extra:
            errors.append(f"Unexpected headers: {sorted(extra)}")

    for i, row in enumerate(rows, start=2):
        # Check for CSV overflow (DictReader uses restkey for surplus fields)
        # If a row has more fields than headers, those extra values appear in a special key
        row_keys = list(row.keys())
        if any(k is None for k in row_keys):
            errors.append(f"Line {i}: Row has too many columns (overflow detected)")
            continue

        row_errors = validate_baseline_row(row, i)
        errors.extend(row_errors)
        if not row_errors:
            entries.append(dict(row))

    return entries, errors
