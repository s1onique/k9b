"""Rules for docs_claim_candidate_coverage verifier.

Validation checks for candidate CSV content.
"""

from __future__ import annotations

from docs_claim_candidate_coverage_contract import (
    REGISTRATION_STATUS_VALUES,
    SEVERITY_VALUES,
    CoverageCheckResult,
)


def check_generated_csv_exists(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Check that generated CSV exists and has content."""
    result = CoverageCheckResult()
    if not candidates:
        result.add_warning("Generated candidate CSV is empty")
    else:
        result.add_info(f"Generated CSV has {len(candidates)} candidates")
    return result


def check_no_duplicate_candidate_ids(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Check for duplicate candidate IDs in generated output."""
    result = CoverageCheckResult()
    ids: dict[str, list[int]] = {}
    for i, row in enumerate(candidates):
        candidate_id = row.get("candidate_id", "").strip()
        if candidate_id:
            if candidate_id not in ids:
                ids[candidate_id] = []
            ids[candidate_id].append(i + 2)

    duplicate_count = 0
    for candidate_id, rows in ids.items():
        if len(rows) > 1:
            duplicate_count += 1

    if duplicate_count > 0:
        result.add_info(
            f"Found {duplicate_count} duplicate candidate IDs (expected - same claim text generates same ID)"
        )
    return result


def check_registration_status_valid(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Check that registration_status values are valid."""
    result = CoverageCheckResult()
    for i, row in enumerate(candidates):
        status = row.get("registration_status", "").strip()
        if status and status not in REGISTRATION_STATUS_VALUES:
            result.add_error(
                f"Row {i + 2}: invalid registration_status '{status}' "
                f"(allowed: {', '.join(sorted(REGISTRATION_STATUS_VALUES))})"
            )
    return result


def check_severity_valid(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Check that candidate_severity values are valid."""
    result = CoverageCheckResult()
    for i, row in enumerate(candidates):
        severity = row.get("candidate_severity", "").strip()
        if severity and severity not in SEVERITY_VALUES:
            result.add_error(
                f"Row {i + 2}: invalid candidate_severity '{severity}' "
                f"(allowed: {', '.join(sorted(SEVERITY_VALUES))})"
            )
    return result


def check_high_severity_unregistered_current_trace_required(
    candidates: list[dict[str, str]]
) -> CoverageCheckResult:
    """WARN on high-severity unregistered current candidates with trace_required=true."""
    result = CoverageCheckResult()
    warnings: list[str] = []
    for row in candidates:
        severity = row.get("candidate_severity", "").strip()
        reg_status = row.get("registration_status", "").strip()
        truth_status = row.get("truth_status", "").strip()
        trace_required = row.get("claim_trace_required", "").strip().lower()
        doc_path = row.get("doc_path", "").strip()
        candidate_id = row.get("candidate_id", "").strip()

        if (severity == "high" and
            reg_status == "unregistered" and
            truth_status == "current" and
            trace_required == "true"):
            warnings.append(
                f"  {candidate_id}: {doc_path} (severity={severity}, trace_required=true)"
            )

    if warnings:
        result.add_warning(
            "High-severity unregistered current claims with trace_required=true (advisory):\n"
            + "\n".join(warnings)
        )
    return result


def check_high_severity_unregistered_current_not_required(
    candidates: list[dict[str, str]]
) -> CoverageCheckResult:
    """WARN on high-severity unregistered current candidates with trace_required=false."""
    result = CoverageCheckResult()
    warnings: list[str] = []
    for row in candidates:
        severity = row.get("candidate_severity", "").strip()
        reg_status = row.get("registration_status", "").strip()
        truth_status = row.get("truth_status", "").strip()
        trace_required = row.get("claim_trace_required", "").strip().lower()
        doc_path = row.get("doc_path", "").strip()
        candidate_id = row.get("candidate_id", "").strip()

        if (severity == "high" and
            reg_status == "unregistered" and
            truth_status == "current" and
            trace_required == "false"):
            warnings.append(
                f"  {candidate_id}: {doc_path} (severity={severity}, trace_required=false)"
            )

    if warnings:
        result.add_warning(
            "High-severity unregistered current claims with trace_required=false (warning only):\n"
            + "\n".join(warnings)
        )
    return result


def check_stale_historical_candidates(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Report stale/historical candidates without failing."""
    result = CoverageCheckResult()
    stale_count = 0
    historical_count = 0
    stale_docs: set[str] = set()
    historical_docs: set[str] = set()

    for row in candidates:
        truth_status = row.get("truth_status", "").strip()
        doc_path = row.get("doc_path", "").strip()

        if truth_status in ("stale",):
            stale_count += 1
            stale_docs.add(doc_path)
        elif truth_status in ("historical",):
            historical_count += 1
            historical_docs.add(doc_path)

    if stale_count:
        result.add_info(f"Stale candidates: {stale_count} (docs: {', '.join(sorted(stale_docs))})")
    if historical_count:
        result.add_info(f"Historical candidates: {historical_count} (docs: {', '.join(sorted(historical_docs))})")

    return result


def check_candidates_registered(candidates: list[dict[str, str]]) -> CoverageCheckResult:
    """Count and report registration statistics."""
    result = CoverageCheckResult()
    registered = 0
    unregistered = 0
    ignored = 0

    for row in candidates:
        status = row.get("registration_status", "").strip()
        if status == "registered":
            registered += 1
        elif status == "unregistered":
            unregistered += 1
        else:
            ignored += 1

    total = len(candidates)
    result.add_info(
        f"Registration status: {registered} registered, {unregistered} unregistered, "
        f"{ignored} ignored (total: {total})"
    )
    return result
