"""Canonical active-diagnosis status values and predicates.

This module provides the authoritative source of truth for which incident statuses
are considered "active" (eligible for automatic diagnosis). The status values
and predicates in this module are used by:
- Query predicates (SQL WHERE clauses)
- Partial index definitions (schema)
- Verifiers (to detect drift between query and schema)

Design invariants:
- This is a closed set of source-code constants, safe from SQL injection
- The ACTIVE_DIAGNOSIS_STATUS_VALUES tuple must match exactly between
  the query predicate and the partial index WHERE clause
- Any drift between query and schema predicates should fail verification
"""

from __future__ import annotations

# =============================================================================
# Canonical Active Status Values
# =============================================================================

# The canonical ordered sequence of active-diagnosis statuses.
# This tuple must be used consistently across:
# - Query predicates (ACTIVE_STATUS_PREDICATE)
# - Partial index WHERE clauses
# - Verifiers
ACTIVE_DIAGNOSIS_STATUS_VALUES = (
    "open",
    "collecting_evidence",
    "investigating",
    "ready_for_review",
)


# =============================================================================
# Query Predicate
# =============================================================================

# Canonical SQL predicate for filtering active incidents.
# Uses literal values (not bound parameters) so SQLite's query planner
# can match the partial index predicate.
# IMPORTANT: This predicate text must match the partial index WHERE clause exactly.
ACTIVE_STATUS_PREDICATE = (
    f"status IN ('{ACTIVE_DIAGNOSIS_STATUS_VALUES[0]}', "
    f"'{ACTIVE_DIAGNOSIS_STATUS_VALUES[1]}', "
    f"'{ACTIVE_DIAGNOSIS_STATUS_VALUES[2]}', "
    f"'{ACTIVE_DIAGNOSIS_STATUS_VALUES[3]}')"
)


# =============================================================================
# Schema Predicate
# =============================================================================

# The partial index WHERE clause predicate text.
# This should match ACTIVE_STATUS_PREDICATE exactly.
PARTIAL_INDEX_WHERE_PREDICATE = (
    "status IN ('open', 'collecting_evidence', 'investigating', 'ready_for_review')"
)


# =============================================================================
# Verification
# =============================================================================


def verify_predicate_consistency() -> tuple[bool, str]:
    """Verify that query predicate and index predicate are consistent.

    Returns:
        Tuple of (is_consistent, message)
    """
    # Normalize for comparison (remove whitespace differences)
    normalized_query = " ".join(ACTIVE_STATUS_PREDICATE.split())
    normalized_index = " ".join(PARTIAL_INDEX_WHERE_PREDICATE.split())

    if normalized_query != normalized_index:
        return False, (
            f"Predicate mismatch:\n"
            f"  Query: {ACTIVE_STATUS_PREDICATE}\n"
            f"  Index: {PARTIAL_INDEX_WHERE_PREDICATE}\n"
            f"Expected: status IN ('open', 'collecting_evidence', 'investigating', 'ready_for_review')"
        )

    # Verify all status values are present in the correct order
    for i, status in enumerate(ACTIVE_DIAGNOSIS_STATUS_VALUES):
        if status not in ACTIVE_STATUS_PREDICATE:
            return False, f"Status '{status}' not found in ACTIVE_STATUS_PREDICATE"

    return True, "Predicates are consistent"


def verify_status_values_match_index(index_sql: str) -> tuple[bool, str]:
    """Verify that an index's WHERE clause matches the canonical status values.

    Args:
        index_sql: The CREATE INDEX statement with WHERE clause

    Returns:
        Tuple of (is_consistent, message)
    """
    if "WHERE" not in index_sql:
        return False, "Index SQL does not contain WHERE clause"

    # Extract WHERE clause (keep the "WHERE" prefix for extraction)
    where_start = index_sql.upper().find("WHERE")
    where_clause = index_sql[where_start:].strip()

    # Normalize for comparison - strip the "WHERE" prefix since PARTIAL_INDEX_WHERE_PREDICATE doesn't have it
    # This handles: "WHERE status IN (...)" → "status IN (...)"
    normalized_where = " ".join(where_clause.split())
    if normalized_where.upper().startswith("WHERE "):
        normalized_where = normalized_where[6:]  # Strip "WHERE " prefix
    expected_normalized = " ".join(PARTIAL_INDEX_WHERE_PREDICATE.split())

    if normalized_where != expected_normalized:
        return False, (
            f"Index WHERE clause does not match canonical predicate:\n"
            f"  Index: {where_clause}\n"
            f"  Expected: {PARTIAL_INDEX_WHERE_PREDICATE}"
        )

    return True, "Index WHERE clause matches canonical predicate"


__all__ = [
    "ACTIVE_DIAGNOSIS_STATUS_VALUES",
    "ACTIVE_STATUS_PREDICATE",
    "PARTIAL_INDEX_WHERE_PREDICATE",
    "verify_predicate_consistency",
    "verify_status_values_match_index",
]
