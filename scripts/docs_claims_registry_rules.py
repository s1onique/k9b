"""Rules for docs_claims_registry verifier.

Contains all validation logic for claim registry checks.
"""

from __future__ import annotations

import re

from docs_claims_registry_contract import (
    REPO_ROOT,
    ALLOWED_CLAIM_TYPE,
    ALLOWED_CLAIM_STATUS,
    ALLOWED_EVIDENCE_STATUS,
    ALLOWED_FRESHNESS_POLICY,
    BOOLEAN_VALUES,
    CLAIM_ID_PATTERN,
    REQUIRED_COLUMNS,
    RegistryCheckResult,
)
from docs_claims_registry_loader import (
    read_csv_header,
    get_inventory_status,
)
from docs_claims_registry_rules_candidates import check_candidate_ids_valid


# Valid archived/deleted statuses that exempt existence check
ARCHIVED_STATUSES = {"historical", "superseded"}


def check_csv_parse(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that CSV has required columns in exact order, no duplicates."""
    result = RegistryCheckResult()

    if not rows:
        result.add_error("Registry is empty (no data rows)")
        return result

    # Read raw header for strict validation
    header, error = read_csv_header(REPO_ROOT / "docs" / "claims" / "docs_claims_registry.csv")
    if error:
        result.add_error(f"Failed to read CSV header: {error}")
        return result

    # Check for duplicate header columns
    seen: set[str] = set()
    duplicates: list[str] = []
    for col in header:
        if col in seen:
            duplicates.append(col)
        else:
            seen.add(col)
    if duplicates:
        result.add_error(f"Duplicate header columns: {', '.join(sorted(duplicates))}")

    # Check header matches required columns exactly and in order
    if header != REQUIRED_COLUMNS:
        result.add_error(
            "CSV header must match required columns exactly and in order. "
            f"Got: {header}"
        )

    return result


def check_no_duplicate_ids(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check for duplicate claim_id values."""
    result = RegistryCheckResult()

    ids = [row.get("claim_id", "").strip() for row in rows]
    seen: dict[str, int] = {}
    for i, claim_id in enumerate(ids):
        if claim_id in seen:
            result.add_error(
                f"Duplicate claim_id '{claim_id}' at row {i + 2} "
                f"(first seen at row {seen[claim_id] + 2})"
            )
        else:
            seen[claim_id] = i

    return result


def check_no_duplicate_tuples(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check for duplicate (doc_path, anchor, claim_text) tuples."""
    result = RegistryCheckResult()

    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        doc_path = row.get("doc_path", "").strip()
        anchor = row.get("anchor", "").strip()
        claim_text = row.get("claim_text", "").strip()

        key_str = f"{doc_path}|{anchor}|{claim_text}"

        if key_str in seen:
            result.add_error(
                f"Duplicate (doc_path, anchor, claim_text) tuple at row {i + 2} "
                f"(first seen at row {seen[key_str] + 2})"
            )
        else:
            seen[key_str] = i

    return result


def check_claim_id_format(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim_id matches DOC-CLAIM-0001 pattern."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_id = row.get("claim_id", "").strip()
        if not claim_id:
            result.add_error(f"Row {i + 2}: claim_id is empty")
            continue

        if not CLAIM_ID_PATTERN.match(claim_id):
            result.add_error(
                f"Row {i + 2}: claim_id '{claim_id}' does not match pattern DOC-CLAIM-0001 "
                f"(expected: prefix DOC-CLAIM-, 4-digit zero-padded suffix)"
            )

    return result


def check_claim_ids_sorted(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim IDs are sorted ascending."""
    result = RegistryCheckResult()

    ids = [row.get("claim_id", "").strip() for row in rows]
    sorted_ids = sorted(ids)

    if ids != sorted_ids:
        result.add_error(
            f"Claim IDs are not sorted ascending. "
            f"Current order: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}"
        )

    return result


def check_doc_paths_in_inventory(
    rows: list[dict[str, str]], inventory_paths: set[str]
) -> RegistryCheckResult:
    """Check that all doc_path values exist in the docs inventory."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        doc_path = row.get("doc_path", "").strip()
        if not doc_path:
            result.add_error(f"Row {i + 2}: doc_path is empty")
            continue

        if doc_path not in inventory_paths:
            result.add_error(
                f"Row {i + 2}: doc_path '{doc_path}' is not in docs_inventory.csv"
            )

    return result


def check_doc_paths_exist(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that all doc_path values exist on disk (unless historical/superseded)."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        doc_path = row.get("doc_path", "").strip()
        claim_status = row.get("claim_status", "").strip()
        inventory_status = get_inventory_status(doc_path)

        if not doc_path:
            continue

        file_path = REPO_ROOT / doc_path

        if not file_path.exists():
            # Allow if archived/deleted status
            effective_status = inventory_status or claim_status
            if effective_status in ARCHIVED_STATUSES:
                result.add_warning(
                    f"Row {i + 2}: doc_path '{doc_path}' does not exist "
                    f"(status={effective_status}, OK if archived)"
                )
            else:
                result.add_error(
                    f"Row {i + 2}: doc_path '{doc_path}' does not exist "
                    f"(status={effective_status}, expected historical/superseded if intentionally removed)"
                )

    return result


def check_anchor_non_empty(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that anchor is non-empty."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        anchor = row.get("anchor", "").strip()
        if not anchor:
            result.add_error(f"Row {i + 2}: anchor is empty")

    return result


def check_claim_text_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim_text is non-empty and reasonably bounded."""
    result = RegistryCheckResult()
    MIN_LENGTH = 10
    MAX_LENGTH = 2000

    for i, row in enumerate(rows):
        claim_text = row.get("claim_text", "").strip()
        if not claim_text:
            result.add_error(f"Row {i + 2}: claim_text is empty")
            continue

        if len(claim_text) < MIN_LENGTH:
            result.add_error(
                f"Row {i + 2}: claim_text is too short ({len(claim_text)} chars, "
                f"minimum {MIN_LENGTH})"
            )

        if len(claim_text) > MAX_LENGTH:
            result.add_warning(
                f"Row {i + 2}: claim_text is very long ({len(claim_text)} chars, "
                f"consider splitting)"
            )

    return result


def check_claim_type_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim_type is from allowed enum."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_type = row.get("claim_type", "").strip()
        if claim_type not in ALLOWED_CLAIM_TYPE:
            result.add_error(
                f"Row {i + 2}: invalid claim_type '{claim_type}' "
                f"(allowed: {', '.join(sorted(ALLOWED_CLAIM_TYPE))})"
            )

    return result


def check_claim_status_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim_status is from allowed enum."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        if claim_status not in ALLOWED_CLAIM_STATUS:
            result.add_error(
                f"Row {i + 2}: invalid claim_status '{claim_status}' "
                f"(allowed: {', '.join(sorted(ALLOWED_CLAIM_STATUS))})"
            )

    return result


def check_evidence_required_boolean(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that evidence_required is a strict boolean."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        evidence_required = row.get("evidence_required", "").strip().lower()
        if evidence_required not in BOOLEAN_VALUES:
            result.add_error(
                f"Row {i + 2}: evidence_required='{evidence_required}' is not a valid boolean "
                f"(expected: true or false)"
            )

    return result


def check_evidence_status_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that evidence_status is from allowed enum."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        evidence_status = row.get("evidence_status", "").strip()
        if evidence_status not in ALLOWED_EVIDENCE_STATUS:
            result.add_error(
                f"Row {i + 2}: invalid evidence_status '{evidence_status}' "
                f"(allowed: {', '.join(sorted(ALLOWED_EVIDENCE_STATUS))})"
            )

    return result


def check_freshness_policy_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that freshness_policy is from allowed enum."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        freshness_policy = row.get("freshness_policy", "").strip()
        if freshness_policy not in ALLOWED_FRESHNESS_POLICY:
            result.add_error(
                f"Row {i + 2}: invalid freshness_policy '{freshness_policy}' "
                f"(allowed: {', '.join(sorted(ALLOWED_FRESHNESS_POLICY))})"
            )

    return result


def check_owner_area_non_empty(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that owner_area is non-empty."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        owner_area = row.get("owner_area", "").strip()
        if not owner_area:
            result.add_error(f"Row {i + 2}: owner_area is empty")

    return result


def check_current_claims_not_unsupported(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that current claims do not have evidence_status=unsupported."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()

        if claim_status == "current" and evidence_status == "unsupported":
            result.add_error(
                f"Row {i + 2}: claim_status='current' but evidence_status='unsupported' "
                f"(current claims must have supported evidence)"
            )

    return result


def check_unsupported_claims_not_current(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that unsupported claims do not have claim_status=current."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()

        if evidence_status == "unsupported" and claim_status == "current":
            result.add_error(
                f"Row {i + 2}: evidence_status='unsupported' but claim_status='current' "
                f"(unsupported evidence cannot back current claims)"
            )

    return result


def check_historical_freshness_policy(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that historical claims use historical_only or not_applicable freshness_policy."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        freshness_policy = row.get("freshness_policy", "").strip()

        if claim_status == "historical":
            if freshness_policy not in {"historical_only", "not_applicable"}:
                result.add_error(
                    f"Row {i + 2}: claim_status='historical' but freshness_policy='{freshness_policy}' "
                    f"(expected: historical_only or not_applicable)"
                )

    return result


def check_planned_claims_evidence(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that planned claims use appropriate evidence_status."""
    result = RegistryCheckResult()
    VALID_FOR_PLANNED = {"pending", "manual_only", "not_required"}

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()

        if claim_status == "planned":
            if evidence_status not in VALID_FOR_PLANNED:
                result.add_error(
                    f"Row {i + 2}: claim_status='planned' but evidence_status='{evidence_status}' "
                    f"(planned claims should use: {', '.join(sorted(VALID_FOR_PLANNED))})"
                )

    return result


def check_evidence_required_false(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that evidence_required=false uses evidence_status=not_required."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        evidence_required = row.get("evidence_required", "").strip().lower()
        evidence_status = row.get("evidence_status", "").strip()

        if evidence_required == "false" and evidence_status != "not_required":
            result.add_error(
                f"Row {i + 2}: evidence_required=false but evidence_status='{evidence_status}' "
                f"(expected: not_required)"
            )

    return result


def check_evidence_ref_for_linked(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that evidence_ref is non-empty if evidence_status is linked or manual_only."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        evidence_status = row.get("evidence_status", "").strip()
        evidence_ref = row.get("evidence_ref", "").strip()

        if evidence_status in {"linked", "manual_only"} and not evidence_ref:
            result.add_error(
                f"Row {i + 2}: evidence_status='{evidence_status}' but evidence_ref is empty "
                f"(evidence_ref required for linked/manual_only evidence)"
            )

    return result


def get_all_checks(
    rows: list[dict[str, str]], inventory_paths: set[str]
) -> list[tuple[str, RegistryCheckResult]]:
    """Return all check results for a given set of rows and inventory paths."""
    return [
        ("CSV structure", check_csv_parse(rows)),
        ("No duplicate claim_id", check_no_duplicate_ids(rows)),
        ("No duplicate tuples", check_no_duplicate_tuples(rows)),
        ("claim_id format", check_claim_id_format(rows)),
        ("claim_id sorted ascending", check_claim_ids_sorted(rows)),
        ("doc_path in inventory", check_doc_paths_in_inventory(rows, inventory_paths)),
        ("doc_path exists", check_doc_paths_exist(rows)),
        ("anchor non-empty", check_anchor_non_empty(rows)),
        ("claim_text valid", check_claim_text_valid(rows)),
        ("claim_type valid", check_claim_type_valid(rows)),
        ("claim_status valid", check_claim_status_valid(rows)),
        ("evidence_required boolean", check_evidence_required_boolean(rows)),
        ("evidence_status valid", check_evidence_status_valid(rows)),
        ("freshness_policy valid", check_freshness_policy_valid(rows)),
        ("owner_area non-empty", check_owner_area_non_empty(rows)),
        ("current claims not unsupported", check_current_claims_not_unsupported(rows)),
        ("unsupported claims not current", check_unsupported_claims_not_current(rows)),
        ("historical freshness policy", check_historical_freshness_policy(rows)),
        ("planned claims evidence", check_planned_claims_evidence(rows)),
        ("evidence_required=false", check_evidence_required_false(rows)),
        ("evidence_ref for linked", check_evidence_ref_for_linked(rows)),
        ("candidate_ids valid", check_candidate_ids_valid(rows)),
    ]