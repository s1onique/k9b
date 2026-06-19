"""Linked claims validation rules for docs_claim_traceability verifier.

Contains validation logic for linked claims and coverage reporting.
"""

from __future__ import annotations

from docs_claim_traceability_contract import TraceabilityCheckResult


def check_linked_claims_valid(
    rows: list[dict[str, str]], registry_rows: list[dict[str, str]]
) -> TraceabilityCheckResult:
    """Check that linked claims reference valid trace IDs and have proper evidence."""
    result = TraceabilityCheckResult()

    # Get trace IDs from matrix
    trace_ids = {row.get("trace_id", "").strip() for row in rows}

    # Get claims with evidence_status=linked
    linked_claims: dict[str, tuple[str, int]] = {}
    for i, row in enumerate(registry_rows):
        claim_id = row.get("claim_id", "").strip()
        evidence_status = row.get("evidence_status", "").strip()
        evidence_ref = row.get("evidence_ref", "").strip()

        if evidence_status == "linked" and claim_id:
            linked_claims[claim_id] = (evidence_ref, i + 2)

    # For each linked claim, verify trace IDs exist and have valid verification status
    for claim_id, (evidence_ref, row_num) in linked_claims.items():
        trace_refs = [t.strip() for t in evidence_ref.split(";") if t.strip()]

        if not trace_refs:
            result.add_error(
                f"Registry row {row_num}: claim '{claim_id}' has evidence_status='linked' "
                f"but evidence_ref is empty (must reference trace_id(s))"
            )
            continue

        for trace_ref in trace_refs:
            if trace_ref not in trace_ids:
                result.add_error(
                    f"Registry row {row_num}: claim '{claim_id}' references unknown trace_id "
                    f"'{trace_ref}' in evidence_ref"
                )

        claim_traces = [r for r in rows if r.get("claim_id", "").strip() == claim_id]
        valid_statuses = {"verified", "manual_only", "historical_only"}
        has_valid_status = any(
            r.get("verification_status", "").strip() in valid_statuses
            for r in claim_traces
        )

        if not has_valid_status:
            statuses = [r.get("verification_status", "") for r in claim_traces]
            result.add_error(
                f"Registry row {row_num}: claim '{claim_id}' has no trace rows with "
                f"verification_status in {valid_statuses}. Found: {statuses}"
            )

    # Check current claims are not linked only to historical_only evidence
    for i, row in enumerate(registry_rows):
        claim_id = row.get("claim_id", "").strip()
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()

        if claim_status == "current" and evidence_status == "linked":
            claim_traces = [r for r in rows if r.get("claim_id", "").strip() == claim_id]
            has_historical_only = all(
                r.get("verification_status", "").strip() == "historical_only"
                for r in claim_traces
            )
            if has_historical_only and claim_traces:
                result.add_error(
                    f"Registry row {i + 2}: claim '{claim_id}' is 'current' but is only "
                    f"linked to historical_only evidence (historical evidence cannot prove "
                    f"current behavior)"
                )

    return result


def print_coverage_report(
    rows: list[dict[str, str]], registry_rows: list[dict[str, str]]
) -> None:
    """Print coverage statistics for the traceability matrix."""
    if not rows:
        return

    total_traces = len(rows)
    total_claims = len(registry_rows)

    traced_claims = {row.get("claim_id", "").strip() for row in rows if row.get("claim_id")}
    claims_with_traces = len(traced_claims)

    verified_claims: set[str] = set()
    for row in rows:
        if row.get("verification_status", "").strip() == "verified":
            verified_claims.add(row.get("claim_id", "").strip())
    claims_with_verified = len(verified_claims)

    current_pending: list[str] = []
    stale_pending: list[str] = []
    for reg_row in registry_rows:
        claim_id = reg_row.get("claim_id", "").strip()
        claim_status = reg_row.get("claim_status", "").strip()
        evidence_status = reg_row.get("evidence_status", "").strip()

        if claim_id in traced_claims and evidence_status == "pending":
            if claim_status == "current":
                current_pending.append(claim_id)
            elif claim_status == "stale":
                stale_pending.append(claim_id)

    unsupported_traces = sum(
        1 for row in rows if row.get("verification_status", "").strip() == "unsupported"
    )

    by_evidence_kind: dict[str, int] = {}
    by_coverage_strength: dict[str, int] = {}
    by_verification_status: dict[str, int] = {}
    for row in rows:
        kind = row.get("evidence_kind", "").strip()
        strength = row.get("coverage_strength", "").strip()
        status = row.get("verification_status", "").strip()
        by_evidence_kind[kind] = by_evidence_kind.get(kind, 0) + 1
        by_coverage_strength[strength] = by_coverage_strength.get(strength, 0) + 1
        by_verification_status[status] = by_verification_status.get(status, 0) + 1

    trace_counts: dict[str, int] = {}
    for row in rows:
        claim_id = row.get("claim_id", "").strip()
        trace_counts[claim_id] = trace_counts.get(claim_id, 0) + 1
    top_claims = sorted(trace_counts.items(), key=lambda x: -x[1])[:5]

    print("\n=== Traceability Coverage Report ===")
    print(f"Total trace rows: {total_traces}")
    print(f"Total claims in registry: {total_claims}")
    print(f"Claims with at least one trace: {claims_with_traces}")
    print(f"Claims with verified evidence: {claims_with_verified}")
    print(f"Current claims pending evidence: {len(current_pending)}")
    print(f"Stale claims pending evidence: {len(stale_pending)}")
    print(f"Unsupported trace rows: {unsupported_traces}")

    print("\nBy evidence_kind:")
    for kind, count in sorted(by_evidence_kind.items()):
        print(f"  {kind}: {count}")

    print("\nBy coverage_strength:")
    for strength, count in sorted(by_coverage_strength.items()):
        print(f"  {strength}: {count}")

    print("\nBy verification_status:")
    for status, count in sorted(by_verification_status.items()):
        print(f"  {status}: {count}")

    print("\nTop claims by trace row count:")
    for claim_id, count in top_claims:
        print(f"  {claim_id}: {count} trace(s)")

    if current_pending:
        print(f"\nCurrent claims still pending evidence ({len(current_pending)}):")
        for claim_id in sorted(current_pending):
            print(f"  - {claim_id}")

    if stale_pending:
        print(f"\nStale claims with pending evidence ({len(stale_pending)}):")
        for claim_id in sorted(stale_pending):
            print(f"  - {claim_id}")