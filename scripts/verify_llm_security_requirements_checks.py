"""Check functions for LLM security requirements verification.

This module contains all verification check functions and helpers.
Import constants from verify_llm_security_requirements_contract.
"""

from __future__ import annotations

import csv
from pathlib import Path

from _verify_helpers import check_ref_exists, check_refs_exist, is_na_placeholder
from verify_llm_security_requirements_contract import (
    ALLOWED_ASSURANCE_LEVEL,
    ALLOWED_CLAIM_CATEGORY,
    ALLOWED_SECURITY_DOMAIN,
    ALLOWED_STATUS,
    REGISTRY_CSV,
    REPO_ROOT,
    REQ_ID_PATTERN,
    REQ_REF_PATTERN,
    REQUIRED_COLUMNS,
    REQCheckResult,
)


def read_registry(csv_path: Path) -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the registry CSV. Returns (rows, error_msg)."""
    if not csv_path.exists():
        return [], f"Registry file not found: {csv_path}"

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading registry: {e}"


def check_csv_parse(rows: list[dict[str, str]], header: list[str]) -> REQCheckResult:
    """Check that CSV has required columns in exact order."""
    result = REQCheckResult()

    if not rows:
        result.add_error("Registry is empty (no data rows)")
        return result

    if header != REQUIRED_COLUMNS:
        result.add_error(
            f"CSV header must match required columns exactly and in order. Got: {header}"
        )

    return result


def check_no_duplicate_ids(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check for duplicate req_id values."""
    result = REQCheckResult()

    ids = [row.get("req_id", "").strip() for row in rows]
    seen: dict[str, int] = {}
    for i, req_id in enumerate(ids):
        if req_id in seen:
            result.add_error(
                f"Duplicate req_id '{req_id}' at row {i + 2} "
                f"(first seen at row {seen[req_id] + 2})"
            )
        else:
            seen[req_id] = i

    return result


def check_req_id_format(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that req_id matches REQ-LLMSEC-0001 pattern."""
    result = REQCheckResult()

    for i, row in enumerate(rows):
        req_id = row.get("req_id", "").strip()
        if not req_id:
            result.add_error(f"Row {i + 2}: req_id is empty")
            continue

        if not REQ_ID_PATTERN.match(req_id):
            result.add_error(
                f"Row {i + 2}: req_id '{req_id}' does not match pattern REQ-LLMSEC-0001 "
                f"(expected: prefix REQ-LLMSEC-, 3+ digit zero-padded suffix)"
            )

    return result


def check_req_ids_sorted(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that REQ IDs are sorted ascending."""
    result = REQCheckResult()

    ids = [row.get("req_id", "").strip() for row in rows]
    sorted_ids = sorted(ids, key=lambda x: int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else 0)

    if ids != sorted_ids:
        result.add_error(
            f"REQ IDs are not sorted ascending. "
            f"Current order: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}"
        )

    return result


def check_required_fields(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that required fields are non-empty."""
    result = REQCheckResult()
    required_fields = ["req_id", "title", "requirement_text", "claim_category",
                       "security_domain", "assurance_level", "status"]

    for i, row in enumerate(rows):
        for field in required_fields:
            value = row.get(field, "").strip()
            if not value:
                result.add_error(f"Row {i + 2}: {field} is empty")

    return result


def check_enum_field(
    rows: list[dict[str, str]],
    field_name: str,
    allowed_values: set[str],
) -> REQCheckResult:
    """Check that a field has values from allowed enum."""
    result = REQCheckResult()

    for i, row in enumerate(rows):
        value = row.get(field_name, "").strip()
        if value not in allowed_values:
            result.add_error(
                f"Row {i + 2}: invalid {field_name} '{value}' "
                f"(allowed: {', '.join(sorted(allowed_values))})"
            )

    return result


def check_refs_non_empty_for_current(
    rows: list[dict[str, str]],
    field_name: str,
) -> REQCheckResult:
    """Check that refs are non-empty for current MUST/SHOULD."""
    result = REQCheckResult()

    for i, row in enumerate(rows):
        assurance_level = row.get("assurance_level", "").strip()
        status = row.get("status", "").strip()
        refs = row.get(field_name, "").strip()

        if assurance_level in {"MUST", "SHOULD"} and status == "current":
            if not refs:
                result.add_error(
                    f"Row {i + 2}: assurance_level='{assurance_level}' requires "
                    f"non-empty {field_name}"
                )

    return result


def check_na_requirements(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that N/A requirements have rationale."""
    result = REQCheckResult()

    for i, row in enumerate(rows):
        assurance_level = (row.get("assurance_level") or "").strip()
        notes = (row.get("notes") or "").strip()

        if assurance_level == "N/A":
            if "N/A" not in notes and "not used" not in notes.lower():
                result.add_warning(
                    f"Row {i + 2}: N/A requirement should include 'N/A' or 'not used' in notes"
                )

    return result


def check_source_doc_exists(rows: list[dict[str, str]], repo_root: Path | None = None) -> REQCheckResult:
    """Check that source_doc paths exist on disk."""
    result = REQCheckResult()
    root = repo_root or REPO_ROOT

    for i, row in enumerate(rows):
        source_doc = row.get("source_doc", "").strip()
        if not source_doc:
            continue
        # Handle N/A placeholders and glob patterns
        if is_na_placeholder(source_doc) or "*" in source_doc:
            continue
        exists, msg = check_ref_exists(source_doc, root)
        if not exists:
            result.add_error(f"Row {i + 2}: source_doc '{source_doc}' does not exist")

    return result


def _check_impl_refs_exist(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that implementation_ref paths exist on disk."""
    result = REQCheckResult()
    errors, _ = check_refs_exist(rows, "implementation_refs", REPO_ROOT)
    for err in errors:
        result.add_error(err)
    return result


def _check_ver_refs_exist(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that verification_ref paths exist on disk."""
    result = REQCheckResult()
    errors, _ = check_refs_exist(rows, "verification_refs", REPO_ROOT)
    for err in errors:
        result.add_error(err)
    return result


def check_dangling_req_refs(rows: list[dict[str, str]], repo_root: Path) -> REQCheckResult:
    """Check that all REQ-LLMSEC-* references in docs exist in the registry CSV."""
    result = REQCheckResult()

    # Collect all registered REQ IDs
    registered_ids = {row.get("req_id", "").strip() for row in rows}
    registered_ids.discard("")  # Remove empty

    # Scan docs for REQ ID references
    docs_to_scan = [
        repo_root / "docs" / "security",
        repo_root / "docs" / "requirements",
    ]

    for doc_dir in docs_to_scan:
        if not doc_dir.exists():
            continue
        for md_file in doc_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                refs = set(REQ_REF_PATTERN.findall(content))
                for ref in refs:
                    if ref not in registered_ids:
                        result.add_error(
                            f"Dangling REQ reference '{ref}' in {md_file.relative_to(repo_root)} "
                            f"- not found in {REGISTRY_CSV.name}"
                        )
            except Exception:
                pass  # Skip files that can't be read

    return result


def get_all_checks(rows: list[dict[str, str]], header: list[str], repo_root: Path | None = None) -> list[tuple[str, REQCheckResult]]:
    """Return all check results."""
    root = repo_root or REPO_ROOT
    return [
        ("CSV structure", check_csv_parse(rows, header)),
        ("No duplicate req_id", check_no_duplicate_ids(rows)),
        ("req_id format", check_req_id_format(rows)),
        ("req_id sorted ascending", check_req_ids_sorted(rows)),
        ("Required fields non-empty", check_required_fields(rows)),
        ("claim_category valid", check_enum_field(rows, "claim_category", ALLOWED_CLAIM_CATEGORY)),
        ("security_domain valid", check_enum_field(rows, "security_domain", ALLOWED_SECURITY_DOMAIN)),
        ("assurance_level valid", check_enum_field(rows, "assurance_level", ALLOWED_ASSURANCE_LEVEL)),
        ("status valid", check_enum_field(rows, "status", ALLOWED_STATUS)),
        ("implementation_refs for MUST/SHOULD", check_refs_non_empty_for_current(rows, "implementation_refs")),
        ("verification_refs for MUST/SHOULD", check_refs_non_empty_for_current(rows, "verification_refs")),
        ("N/A requirements rationale", check_na_requirements(rows)),
        ("source_doc exists", check_source_doc_exists(rows, root)),
        ("implementation_refs exist", _check_impl_refs_exist(rows)),
        ("verification_refs exist", _check_ver_refs_exist(rows)),
        ("dangling REQ refs in docs", check_dangling_req_refs(rows, root)),
    ]


def print_summary(rows: list[dict[str, str]]) -> None:
    """Print registry summary statistics."""
    if not rows:
        return

    category_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    level_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for row in rows:
        category = row.get("claim_category", "").strip()
        domain = row.get("security_domain", "").strip()
        level = row.get("assurance_level", "").strip()
        status = row.get("status", "").strip()

        category_counts[category] = category_counts.get(category, 0) + 1
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        level_counts[level] = level_counts.get(level, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\n=== REQ Register Summary ===")
    print(f"Total requirements registered: {len(rows)}")

    print("\nBy claim_category:")
    for ct, count in sorted(category_counts.items()):
        print(f"  {ct}: {count}")

    print("\nBy security_domain:")
    for sd, count in sorted(domain_counts.items()):
        print(f"  {sd}: {count}")

    print("\nBy assurance_level:")
    for al, count in sorted(level_counts.items()):
        print(f"  {al}: {count}")

    print("\nBy status:")
    for s, count in sorted(status_counts.items()):
        print(f"  {s}: {count}")
