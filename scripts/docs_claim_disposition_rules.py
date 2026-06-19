"""Rules for docs_claim_disposition verifier.

Validation checks for disposition ledger content.
"""

from __future__ import annotations

from scripts.docs_claim_disposition_contract import (
    ALLOWED_DISPOSITIONS,
    ALLOWED_REASON_CODES,
    CANDIDATE_ID_PATTERN,
    CLAIM_ID_PATTERN,
    DISPOSITION_CLAIMS_DIR,
    DISPOSITION_SHARD_COUNT,
    DISPOSITIONS_ALLOWING_EMPTY_NOTES,
    DISPOSITIONS_REQUIRING_CLAIM_ID,
    DISPOSITIONS_REQUIRING_COVERED_BY_CLAIM_ID,
    DISPOSITIONS_REQUIRING_REASON_CODE,
    DispositionCheckResult,
    get_disposition_csv_path,
)


def check_disposition_csv_exists() -> DispositionCheckResult:
    """Check that disposition ledger shards exist."""
    result = DispositionCheckResult()
    
    # Check if shards exist
    shard_exists = False
    for i in range(DISPOSITION_SHARD_COUNT):
        shard_path = get_disposition_csv_path(i)
        if shard_path.exists():
            shard_exists = True
            break
    
    # Fallback: check for legacy monolithic file
    legacy_path = DISPOSITION_CLAIMS_DIR / "docs_claim_dispositions.csv"
    if shard_exists:
        result.add_info(f"Disposition ledger shards found in {DISPOSITION_CLAIMS_DIR}")
    elif legacy_path.exists():
        result.add_info(f"Legacy monolithic disposition ledger found: {legacy_path}")
    else:
        result.add_error(f"Disposition ledger not found (expected shards in {DISPOSITION_CLAIMS_DIR})")
    
    return result


def check_no_duplicate_dispositions(
    dispositions: list[dict[str, str]]
) -> DispositionCheckResult:
    """Check for duplicate candidate_id in disposition ledger."""
    result = DispositionCheckResult()
    seen: dict[str, int] = {}
    for i, row in enumerate(dispositions):
        cid = row.get("candidate_id", "").strip()
        if cid:
            if cid not in seen:
                seen[cid] = i + 2  # +2 for 1-based + header
            else:
                result.add_error(
                    f"Row {i + 2}: duplicate candidate_id '{cid}' "
                    f"(first seen at row {seen[cid]})"
                )
    return result


def check_disposition_enum_valid(
    dispositions: list[dict[str, str]]
) -> DispositionCheckResult:
    """Check that disposition values are valid."""
    result = DispositionCheckResult()
    for i, row in enumerate(dispositions):
        disp = row.get("disposition", "").strip()
        if not disp:
            result.add_error(f"Row {i + 2}: empty disposition")
        elif disp not in ALLOWED_DISPOSITIONS:
            result.add_error(
                f"Row {i + 2}: invalid disposition '{disp}' "
                f"(allowed: {', '.join(sorted(ALLOWED_DISPOSITIONS))})"
            )
    return result


def check_reason_code_enum_valid(
    dispositions: list[dict[str, str]]
) -> DispositionCheckResult:
    """Check that reason_code values are valid."""
    result = DispositionCheckResult()
    for i, row in enumerate(dispositions):
        reason = row.get("reason_code", "").strip()
        disp = row.get("disposition", "").strip()

        # Check if reason_code is required for this disposition
        if disp in DISPOSITIONS_REQUIRING_REASON_CODE:
            if not reason:
                result.add_error(
                    f"Row {i + 2}: disposition '{disp}' requires reason_code"
                )
            elif reason not in ALLOWED_REASON_CODES:
                result.add_error(
                    f"Row {i + 2}: invalid reason_code '{reason}' "
                    f"(allowed: {', '.join(sorted(ALLOWED_REASON_CODES))})"
                )
        elif reason and reason not in ALLOWED_REASON_CODES:
            result.add_error(
                f"Row {i + 2}: invalid reason_code '{reason}' "
                f"(allowed: {', '.join(sorted(ALLOWED_REASON_CODES))})"
            )
    return result


def check_claim_id_valid_for_disposition(
    dispositions: list[dict[str, str]],
    valid_claim_ids: set[str],
) -> DispositionCheckResult:
    """Check that claim_id is valid for dispositions that require it."""
    result = DispositionCheckResult()
    for i, row in enumerate(dispositions):
        disp = row.get("disposition", "").strip()
        claim_id = row.get("claim_id", "").strip()

        if disp in DISPOSITIONS_REQUIRING_CLAIM_ID:
            if not claim_id:
                result.add_error(
                    f"Row {i + 2}: disposition '{disp}' requires claim_id"
                )
            elif not CLAIM_ID_PATTERN.match(claim_id):
                result.add_error(
                    f"Row {i + 2}: invalid claim_id format '{claim_id}' "
                    "(expected format: DOC-CLAIM-0001)"
                )
            elif claim_id not in valid_claim_ids:
                result.add_error(
                    f"Row {i + 2}: claim_id '{claim_id}' not found in registry"
                )
    return result


def check_covered_by_claim_id_valid(
    dispositions: list[dict[str, str]],
    valid_claim_ids: set[str],
) -> DispositionCheckResult:
    """Check that covered_by_claim_id is valid for dispositions that require it."""
    result = DispositionCheckResult()
    for i, row in enumerate(dispositions):
        disp = row.get("disposition", "").strip()
        covered_by = row.get("covered_by_claim_id", "").strip()

        if disp in DISPOSITIONS_REQUIRING_COVERED_BY_CLAIM_ID:
            if not covered_by:
                result.add_error(
                    f"Row {i + 2}: disposition '{disp}' requires covered_by_claim_id"
                )
            elif not CLAIM_ID_PATTERN.match(covered_by):
                result.add_error(
                    f"Row {i + 2}: invalid covered_by_claim_id format '{covered_by}' "
                    "(expected format: DOC-CLAIM-0001)"
                )
            elif covered_by not in valid_claim_ids:
                result.add_error(
                    f"Row {i + 2}: covered_by_claim_id '{covered_by}' not found in registry"
                )
    return result


def check_candidate_id_valid(
    dispositions: list[dict[str, str]],
    valid_candidate_ids: set[str],
) -> DispositionCheckResult:
    """Check that candidate_id values are valid."""
    result = DispositionCheckResult()
    for i, row in enumerate(dispositions):
        cid = row.get("candidate_id", "").strip()
        if not cid:
            result.add_error(f"Row {i + 2}: empty candidate_id")
        elif not CANDIDATE_ID_PATTERN.match(cid):
            result.add_error(
                f"Row {i + 2}: invalid candidate_id format '{cid}' "
                "(expected format: DOC-CAND-<12-char-hex>)"
            )
        elif valid_candidate_ids and cid not in valid_candidate_ids:
            result.add_error(
                f"Row {i + 2}: candidate_id '{cid}' not found in generated candidates"
            )
    return result


def check_reviewed_at_valid(
    dispositions: list[dict[str, str]]
) -> DispositionCheckResult:
    """Check that reviewed_at is populated."""
    result = DispositionCheckResult()
    for i, row in enumerate(dispositions):
        reviewed = row.get("reviewed_at", "").strip()
        if not reviewed:
            result.add_error(f"Row {i + 2}: empty reviewed_at")
    return result


def check_reviewer_notes_required(
    dispositions: list[dict[str, str]]
) -> DispositionCheckResult:
    """Check that reviewer_notes is populated where required."""
    result = DispositionCheckResult()
    for i, row in enumerate(dispositions):
        disp = row.get("disposition", "").strip()
        notes = row.get("reviewer_notes", "").strip()

        if disp not in DISPOSITIONS_ALLOWING_EMPTY_NOTES and not notes:
            result.add_error(
                f"Row {i + 2}: disposition '{disp}' requires non-empty reviewer_notes"
            )
    return result


def check_all_candidates_have_disposition(
    dispositions: list[dict[str, str]],
    candidate_ids: set[str],
) -> DispositionCheckResult:
    """Check that every generated candidate has exactly one disposition."""
    result = DispositionCheckResult()

    disposition_ids = {row.get("candidate_id", "").strip() for row in dispositions}
    disposition_ids.discard("")  # Remove empty

    # Find missing candidates
    missing = candidate_ids - disposition_ids
    if missing:
        # Only show first 10 to avoid flooding output
        missing_list = sorted(list(missing))[:10]
        result.add_error(
            f"{len(missing)} candidates without disposition. "
            f"Examples: {', '.join(missing_list)}"
        )

    # Find extra dispositions (shouldn't happen but check anyway)
    extra = disposition_ids - candidate_ids
    if extra:
        extra_list = sorted(list(extra))[:10]
        result.add_error(
            f"{len(extra)} dispositions reference unknown candidates. "
            f"Examples: {', '.join(extra_list)}"
        )

    return result


def check_disposition_statistics(
    dispositions: list[dict[str, str]]
) -> DispositionCheckResult:
    """Count and report disposition statistics."""
    result = DispositionCheckResult()

    counts: dict[str, int] = {}
    for row in dispositions:
        disp = row.get("disposition", "").strip() or "(empty)"
        counts[disp] = counts.get(disp, 0) + 1

    result.add_info(f"Disposition statistics (total: {len(dispositions)}):")
    for disp, count in sorted(counts.items()):
        result.add_info(f"  {disp}: {count}")

    return result
