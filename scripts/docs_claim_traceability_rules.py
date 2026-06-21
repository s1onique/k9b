"""Rules for docs_claim_traceability verifier.

Contains all validation logic for claim traceability checks.
"""

from __future__ import annotations

from docs_claim_traceability_contract import (
    ALLOWED_COVERAGE_STRENGTH,
    ALLOWED_EVIDENCE_KIND,
    ALLOWED_VERIFICATION_STATUS,
    MATRIX_CSV,
    PATH_VALIDATED_KINDS,
    REPO_ROOT,
    REQUIRED_COLUMNS,
    TRACE_ID_PATTERN,
    TraceabilityCheckResult,
    read_csv_header,
)
from docs_claim_traceability_rules_linked import check_linked_claims_valid


def check_csv_parse(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that CSV has required columns in exact order, no duplicates."""
    result = TraceabilityCheckResult()

    if not rows:
        result.add_error("Matrix is empty (no data rows)")
        return result

    header, error = read_csv_header(MATRIX_CSV)
    if error:
        result.add_error(f"Failed to read CSV header: {error}")
        return result

    seen: set[str] = set()
    duplicates: list[str] = []
    for col in header:
        if col in seen:
            duplicates.append(col)
        else:
            seen.add(col)
    if duplicates:
        result.add_error(f"Duplicate header columns: {', '.join(sorted(duplicates))}")

    if header != REQUIRED_COLUMNS:
        result.add_error(
            "CSV header must match required columns exactly and in order. "
            f"Got: {header}"
        )

    return result


def check_no_duplicate_trace_ids(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check for duplicate trace_id values."""
    result = TraceabilityCheckResult()

    ids = [row.get("trace_id", "").strip() for row in rows]
    seen: dict[str, int] = {}
    for i, trace_id in enumerate(ids):
        if trace_id in seen:
            result.add_error(
                f"Duplicate trace_id '{trace_id}' at row {i + 2} "
                f"(first seen at row {seen[trace_id] + 2})"
            )
        else:
            seen[trace_id] = i

    return result


def check_no_duplicate_tuples(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check for duplicate (claim_id, evidence_kind, evidence_ref) tuples."""
    result = TraceabilityCheckResult()

    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        claim_id = row.get("claim_id", "").strip()
        evidence_kind = row.get("evidence_kind", "").strip()
        evidence_ref = row.get("evidence_ref", "").strip()

        key_str = f"{claim_id}|{evidence_kind}|{evidence_ref}"

        if key_str in seen:
            result.add_error(
                f"Duplicate (claim_id, evidence_kind, evidence_ref) tuple at row {i + 2} "
                f"(first seen at row {seen[key_str] + 2})"
            )
        else:
            seen[key_str] = i

    return result


def check_trace_id_format(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that trace_id matches DOC-TRACE-0001 pattern."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        trace_id = row.get("trace_id", "").strip()
        if not trace_id:
            result.add_error(f"Row {i + 2}: trace_id is empty")
            continue

        if not TRACE_ID_PATTERN.match(trace_id):
            result.add_error(
                f"Row {i + 2}: trace_id '{trace_id}' does not match pattern DOC-TRACE-0001 "
                f"(expected: prefix DOC-TRACE-, 4-digit zero-padded suffix)"
            )

    return result


def check_trace_ids_sorted(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that trace IDs are sorted ascending."""
    result = TraceabilityCheckResult()

    ids = [row.get("trace_id", "").strip() for row in rows]
    sorted_ids = sorted(ids)

    if ids != sorted_ids:
        result.add_error(
            f"Trace IDs are not sorted ascending. "
            f"Current order: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}"
        )

    return result


def check_claim_ids_exist_in_registry(
    rows: list[dict[str, str]], registry_rows: list[dict[str, str]]
) -> TraceabilityCheckResult:
    """Check that all claim_id values exist in the claims registry."""
    result = TraceabilityCheckResult()

    registry_ids = {row.get("claim_id", "").strip() for row in registry_rows}

    for i, row in enumerate(rows):
        claim_id = row.get("claim_id", "").strip()
        if not claim_id:
            result.add_error(f"Row {i + 2}: claim_id is empty")
            continue

        if claim_id not in registry_ids:
            result.add_error(
                f"Row {i + 2}: claim_id '{claim_id}' is not in docs_claims_registry.csv"
            )

    return result


def check_all_evidence_required_claims_traced(
    rows: list[dict[str, str]], registry_rows: list[dict[str, str]]
) -> TraceabilityCheckResult:
    """Check that every claim with evidence_required=true appears in matrix."""
    result = TraceabilityCheckResult()

    required_claims: set[str] = set()
    for row in registry_rows:
        claim_id = row.get("claim_id", "").strip()
        evidence_required = row.get("evidence_required", "").strip().lower()
        if evidence_required == "true":
            required_claims.add(claim_id)

    traced_claims: set[str] = set()
    for row in rows:
        claim_id = row.get("claim_id", "").strip()
        if claim_id:
            traced_claims.add(claim_id)

    missing = required_claims - traced_claims
    if missing:
        for claim_id in sorted(missing):
            result.add_error(
                f"Claim '{claim_id}' has evidence_required=true but is not in traceability matrix"
            )

    return result


def check_evidence_kind_valid(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that evidence_kind is from allowed enum."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        evidence_kind = row.get("evidence_kind", "").strip()
        if evidence_kind not in ALLOWED_EVIDENCE_KIND:
            result.add_error(
                f"Row {i + 2}: invalid evidence_kind '{evidence_kind}' "
                f"(allowed: {', '.join(sorted(ALLOWED_EVIDENCE_KIND))})"
            )

    return result


def check_coverage_strength_valid(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that coverage_strength is from allowed enum."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        coverage_strength = row.get("coverage_strength", "").strip()
        if coverage_strength not in ALLOWED_COVERAGE_STRENGTH:
            result.add_error(
                f"Row {i + 2}: invalid coverage_strength '{coverage_strength}' "
                f"(allowed: {', '.join(sorted(ALLOWED_COVERAGE_STRENGTH))})"
            )

    return result


def check_verification_status_valid(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that verification_status is from allowed enum."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        verification_status = row.get("verification_status", "").strip()
        if verification_status not in ALLOWED_VERIFICATION_STATUS:
            result.add_error(
                f"Row {i + 2}: invalid verification_status '{verification_status}' "
                f"(allowed: {', '.join(sorted(ALLOWED_VERIFICATION_STATUS))})"
            )

    return result


def check_evidence_ref_non_empty(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that evidence_ref is non-empty unless evidence_kind=none."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        evidence_kind = row.get("evidence_kind", "").strip()
        evidence_ref = row.get("evidence_ref", "").strip()

        if evidence_kind != "none" and not evidence_ref:
            result.add_error(
                f"Row {i + 2}: evidence_kind='{evidence_kind}' but evidence_ref is empty "
                f"(evidence_ref required for non-none evidence_kind)"
            )

    return result


def check_evidence_path_exists(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that evidence_path exists on disk for validated evidence kinds."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        evidence_kind = row.get("evidence_kind", "").strip()
        evidence_path = row.get("evidence_path", "").strip()

        if evidence_kind in PATH_VALIDATED_KINDS:
            if not evidence_path:
                result.add_error(
                    f"Row {i + 2}: evidence_kind='{evidence_kind}' but evidence_path is empty "
                    f"(evidence_path required for {evidence_kind} evidence)"
                )
                continue

            file_path = REPO_ROOT / evidence_path
            if not file_path.exists():
                result.add_error(
                    f"Row {i + 2}: evidence_path '{evidence_path}' does not exist on disk "
                    f"(for {evidence_kind} evidence)"
                )

    return result


def check_gate_name_for_ci_gate(
    rows: list[dict[str, str]], gate_mapping: dict[str, object]
) -> TraceabilityCheckResult:
    """Check that gate_name is non-empty for ci_gate and exists in mapping."""
    result = TraceabilityCheckResult()

    required_gates = gate_mapping.get("required_gates", {})
    if isinstance(required_gates, dict):
        valid_gate_names = set(required_gates.keys())
    else:
        valid_gate_names = set()

    for i, row in enumerate(rows):
        evidence_kind = row.get("evidence_kind", "").strip()
        gate_name = row.get("gate_name", "").strip()

        if evidence_kind == "ci_gate":
            if not gate_name:
                result.add_error(
                    f"Row {i + 2}: evidence_kind='ci_gate' but gate_name is empty "
                    f"(gate_name required for ci_gate evidence)"
                )
            elif gate_name not in valid_gate_names:
                result.add_warning(
                    f"Row {i + 2}: gate_name '{gate_name}' is not in ci_gate_mapping.json "
                    f"(known gates: {', '.join(sorted(valid_gate_names))})"
                )

    return result


def check_semantic_combinations(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check semantic combinations of evidence_kind, coverage_strength, verification_status."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        evidence_kind = (row.get("evidence_kind") or "").strip()
        coverage_strength = (row.get("coverage_strength") or "").strip()
        verification_status = (row.get("verification_status") or "").strip()
        notes = (row.get("notes") or "").strip()

        # evidence_kind=none requires coverage_strength=none
        if evidence_kind == "none" and coverage_strength != "none":
            result.add_error(
                f"Row {i + 2}: evidence_kind='none' but coverage_strength='{coverage_strength}' "
                f"(expected: none)"
            )

        # coverage_strength=direct must not use evidence_kind=none
        if coverage_strength == "direct" and evidence_kind == "none":
            result.add_error(
                f"Row {i + 2}: coverage_strength='direct' but evidence_kind='none' "
                f"(direct coverage requires actual evidence)"
            )

        # verification_status=verified must not use coverage_strength=none
        if verification_status == "verified" and coverage_strength == "none":
            result.add_error(
                f"Row {i + 2}: verification_status='verified' but coverage_strength='none' "
                f"(verified evidence must have coverage)"
            )

        # manual_only requires meaningful notes
        if verification_status == "manual_only" and not notes:
            result.add_error(
                f"Row {i + 2}: verification_status='manual_only' but notes is empty "
                f"(manual_only verification requires meaningful notes)"
            )

        # unsupported requires meaningful notes
        if verification_status == "unsupported" and not notes:
            result.add_error(
                f"Row {i + 2}: verification_status='unsupported' but notes is empty "
                f"(unsupported verification requires meaningful notes)"
            )

    return result


def get_all_checks(
    rows: list[dict[str, str]],
    registry_rows: list[dict[str, str]],
    gate_mapping: dict[str, object],
) -> list[tuple[str, TraceabilityCheckResult]]:
    """Return all check results."""
    return [
        ("CSV structure", check_csv_parse(rows)),
        ("No duplicate trace_id", check_no_duplicate_trace_ids(rows)),
        ("No duplicate tuples", check_no_duplicate_tuples(rows)),
        ("trace_id format", check_trace_id_format(rows)),
        ("trace_id sorted ascending", check_trace_ids_sorted(rows)),
        ("claim_id exists in registry", check_claim_ids_exist_in_registry(rows, registry_rows)),
        ("evidence_required claims traced", check_all_evidence_required_claims_traced(rows, registry_rows)),
        ("evidence_kind valid", check_evidence_kind_valid(rows)),
        ("coverage_strength valid", check_coverage_strength_valid(rows)),
        ("verification_status valid", check_verification_status_valid(rows)),
        ("evidence_ref non-empty", check_evidence_ref_non_empty(rows)),
        ("evidence_path exists", check_evidence_path_exists(rows)),
        ("gate_name for ci_gate", check_gate_name_for_ci_gate(rows, gate_mapping)),
        ("Semantic combinations", check_semantic_combinations(rows)),
        ("Linked claims valid", check_linked_claims_valid(rows, registry_rows)),
    ]
