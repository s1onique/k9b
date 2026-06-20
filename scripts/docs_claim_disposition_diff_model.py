"""Diff computation for disposition semantic diff reporter.

Responsibilities:
- Compute semantic diff between two sets of disposition rows
- Truncate reviewer notes for display
- All stdlib dependencies
"""
from __future__ import annotations

from collections import Counter

# Fields that matter for semantic diff (reviewer_notes is user-facing annotation)
SEMANTIC_FIELDS = [
    "candidate_id",
    "disposition",
    "claim_id",
    "covered_by_claim_id",
    "reason_code",
    "reviewed_at",
    "reviewer_notes",
]


class DiffError(Exception):
    """Raised when diff computation encounters structural problems."""
    pass


def compute_diff(
    base_rows: list[dict[str, str]],
    target_rows: list[dict[str, str]],
) -> dict:
    """Compute semantic diff between two sets of disposition rows.

    Args:
        base_rows: Rows from base ref/dir
        target_rows: Rows from target ref/dir

    Returns:
        Diff result dict with categories, counts, and changed rows
    """
    base_by_id = {row["candidate_id"]: row for row in base_rows}
    target_by_id = {row["candidate_id"]: row for row in target_rows}

    base_ids = set(base_by_id.keys())
    target_ids = set(target_by_id.keys())

    added_ids = sorted(target_ids - base_ids)
    removed_ids = sorted(base_ids - target_ids)
    common_ids = sorted(base_ids & target_ids)

    changed_rows: list[dict] = []
    field_change_counts: Counter = Counter()

    for cid in common_ids:
        base_row = base_by_id[cid]
        target_row = target_by_id[cid]

        changed_fields = []
        for field in SEMANTIC_FIELDS:
            if base_row.get(field, "") != target_row.get(field, ""):
                changed_fields.append(field)
                field_change_counts[field] += 1

        if changed_fields:
            # Build diff snippet for changed fields
            changes = {}
            for field in changed_fields:
                # Truncate reviewer_notes for display
                base_val = base_row.get(field, "")
                target_val = target_row.get(field, "")
                if field == "reviewer_notes":
                    base_val = _truncate_note(base_val)
                    target_val = _truncate_note(target_val)
                changes[field] = {
                    "before": base_val,
                    "after": target_val,
                }
            changed_rows.append({
                "candidate_id": cid,
                "changed_fields": changed_fields,
                "changes": changes,
            })

    # Sort changed rows by candidate_id
    changed_rows.sort(key=lambda x: x["candidate_id"])

    # Count dispositions
    base_disp_counts = Counter(row.get("disposition", "") for row in base_rows)
    target_disp_counts = Counter(row.get("disposition", "") for row in target_rows)

    return {
        "base_row_count": len(base_rows),
        "target_row_count": len(target_rows),
        "added_candidate_ids": added_ids,
        "removed_candidate_ids": removed_ids,
        "candidate_id_set_changed": bool(added_ids or removed_ids),
        "common_candidate_count": len(common_ids),
        "changed_candidate_count": len(changed_rows),
        "unchanged_candidate_count": len(common_ids) - len(changed_rows),
        "disposition_counts_before": dict(base_disp_counts),
        "disposition_counts_after": dict(target_disp_counts),
        "disposition_counts_changed": base_disp_counts != target_disp_counts,
        "changed_field_counts": dict(field_change_counts),
        "changed_rows": changed_rows,
    }


def _truncate_note(note: str, max_len: int = 120) -> str:
    """Truncate reviewer notes for display, preserving start and end."""
    if not note:
        return ""
    if len(note) <= max_len:
        return note
    # Try to preserve meaningful content
    return note[:max_len - 3] + "..."
