"""Rules for docs_inventory verifier.

Contains all validation logic for inventory checks.
"""

from __future__ import annotations

from pathlib import Path

from docs_inventory_contract import (
    REPO_ROOT,
    INVENTORY_CSV,
    ALLOWED_DOC_CLASS,
    ALLOWED_TRUTH_STATUS,
    ARCHIVED_STATUSES,
    BOOLEAN_VALUES,
    InventoryCheckResult,
)
from docs_inventory_loader import get_scope_files


# Required columns
REQUIRED_COLUMNS = {
    "doc_path",
    "doc_class",
    "truth_status",
    "owner_area",
    "generated_by",
    "replacement_doc",
    "claim_trace_required",
    "notes",
}


def check_csv_parse(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that CSV has required columns and parses correctly."""
    result = InventoryCheckResult()

    if not rows:
        result.add_error("Inventory is empty (no data rows)")
        return result

    actual_columns = set(rows[0].keys())
    missing_columns = REQUIRED_COLUMNS - actual_columns
    if missing_columns:
        result.add_error(f"Missing required columns: {', '.join(sorted(missing_columns))}")

    return result


def check_no_duplicate_paths(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check for duplicate doc_path entries."""
    result = InventoryCheckResult()

    paths = [row.get("doc_path", "").strip() for row in rows]
    seen: dict[str, int] = {}
    for i, path in enumerate(paths):
        if path in seen:
            result.add_error(f"Duplicate doc_path '{path}' at row {i + 2} (first seen at row {seen[path] + 2})")
        else:
            seen[path] = i

    return result


def check_doc_class_valid(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that all doc_class values are from allowed enum."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        doc_class = row.get("doc_class", "").strip()
        if doc_class not in ALLOWED_DOC_CLASS:
            result.add_error(
                f"Row {i + 2}: invalid doc_class '{doc_class}' "
                f"(allowed: {', '.join(sorted(ALLOWED_DOC_CLASS))})"
            )

    return result


def check_truth_status_valid(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that all truth_status values are from allowed enum."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        truth_status = row.get("truth_status", "").strip()
        if truth_status not in ALLOWED_TRUTH_STATUS:
            result.add_error(
                f"Row {i + 2}: invalid truth_status '{truth_status}' "
                f"(allowed: {', '.join(sorted(ALLOWED_TRUTH_STATUS))})"
            )

    return result


def check_generated_docs_have_generator(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that generated docs have generated_by set."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        doc_class = row.get("doc_class", "").strip()
        generated_by = row.get("generated_by", "").strip()

        if doc_class == "generated" and not generated_by:
            result.add_error(
                f"Row {i + 2}: doc_class='generated' but generated_by is empty"
            )

    return result


def check_superseded_docs_have_replacement(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that superseded docs have replacement_doc or clear notes."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        truth_status = (row.get("truth_status") or "").strip()
        replacement_doc = (row.get("replacement_doc") or "").strip()
        notes = (row.get("notes") or "").strip()

        if truth_status == "superseded" and not replacement_doc and not notes:
            result.add_error(
                f"Row {i + 2}: truth_status='superseded' but both replacement_doc and notes are empty"
            )

    return result


def check_historical_not_current(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that historical docs don't have truth_status='current'."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        doc_class = row.get("doc_class", "").strip()
        truth_status = row.get("truth_status", "").strip()

        if doc_class == "historical" and truth_status == "current":
            result.add_error(
                f"Row {i + 2}: doc_class='historical' but truth_status='current' (conflicting)"
            )

    return result


def check_claim_trace_boolean(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that claim_trace_required is a strict boolean."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        claim_trace = row.get("claim_trace_required", "").strip().lower()
        if claim_trace not in BOOLEAN_VALUES:
            result.add_error(
                f"Row {i + 2}: claim_trace_required='{claim_trace}' is not a valid boolean "
                f"(expected: true or false)"
            )

    return result


def check_all_docs_in_inventory(rows: list[dict[str, str]], scope_files: set[Path], repo_root: Path | None = None) -> InventoryCheckResult:
    """Check that every in-scope doc exists in the inventory."""
    result = InventoryCheckResult()
    root = repo_root if repo_root is not None else REPO_ROOT

    inventory_paths: set[str] = set()
    for row in rows:
        inventory_paths.add(row.get("doc_path", "").strip())

    for file_path in sorted(scope_files):
        rel_path = file_path.relative_to(root)
        rel_path_str = str(rel_path).replace("\\", "/")

        if rel_path_str not in inventory_paths:
            result.add_error(f"Scope file '{rel_path_str}' is not in inventory")

    return result


def check_inventory_paths_exist(rows: list[dict[str, str]], repo_root: Path | None = None) -> InventoryCheckResult:
    """Check that every inventory path exists (unless archived/deleted with valid status)."""
    result = InventoryCheckResult()
    root = repo_root if repo_root is not None else REPO_ROOT

    for i, row in enumerate(rows):
        doc_path = row.get("doc_path", "").strip()
        truth_status = row.get("truth_status", "").strip()

        if not doc_path:
            result.add_error(f"Row {i + 2}: doc_path is empty")
            continue

        file_path = root / doc_path

        if not file_path.exists():
            if truth_status in ARCHIVED_STATUSES:
                result.add_warning(
                    f"Row {i + 2}: inventory path '{doc_path}' does not exist (status={truth_status}, OK if archived)"
                )
            else:
                result.add_error(
                    f"Row {i + 2}: inventory path '{doc_path}' does not exist "
                    f"(status={truth_status}, expected historical/superseded if intentionally removed)"
                )

    return result


def get_all_checks(rows: list[dict[str, str]], scope_files: set[Path], repo_root: Path | None = None) -> list[tuple[str, InventoryCheckResult]]:
    """Return all check results."""
    return [
        ("CSV structure", check_csv_parse(rows)),
        ("No duplicate paths", check_no_duplicate_paths(rows)),
        ("Valid doc_class", check_doc_class_valid(rows)),
        ("Valid truth_status", check_truth_status_valid(rows)),
        ("Generated docs have generator", check_generated_docs_have_generator(rows)),
        ("Superseded docs have replacement", check_superseded_docs_have_replacement(rows)),
        ("Historical not marked current", check_historical_not_current(rows)),
        ("claim_trace_required is boolean", check_claim_trace_boolean(rows)),
        ("All scope docs in inventory", check_all_docs_in_inventory(rows, scope_files, repo_root)),
        ("Inventory paths exist", check_inventory_paths_exist(rows, repo_root)),
    ]
