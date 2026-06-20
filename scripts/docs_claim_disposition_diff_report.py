"""Output formatting for disposition semantic diff reporter.

Responsibilities:
- Format diff result as human-readable output
- Format diff result as deterministic JSON
"""
from __future__ import annotations

import json


def format_human_output(diff_result: dict, base_label: str, target_label: str) -> str:
    """Format diff result as human-readable output.

    Args:
        diff_result: Result from compute_diff
        base_label: Label for base (e.g., "HEAD~1")
        target_label: Label for target (e.g., "HEAD")

    Returns:
        Formatted string
    """
    lines: list[str] = []

    # Summary
    lines.append(f"[INFO] Loaded base ({base_label}): {diff_result['base_row_count']} rows")
    lines.append(f"[INFO] Loaded target ({target_label}): {diff_result['target_row_count']} rows")
    lines.append("")

    # Row set stability
    if diff_result["candidate_id_set_changed"]:
        lines.append("[FAIL] Candidate ID set changed")
        if diff_result["added_candidate_ids"]:
            added = diff_result["added_candidate_ids"]
            lines.append(
                f"  Added: {len(added)} ({added[:5]}...)" if len(added) > 5 else f"  Added: {added}"
            )
        if diff_result["removed_candidate_ids"]:
            removed = diff_result["removed_candidate_ids"]
            lines.append(
                f"  Removed: {len(removed)} ({removed[:5]}...)"
                if len(removed) > 5 else f"  Removed: {removed}"
            )
    else:
        lines.append("[PASS] Candidate ID set unchanged")

    # Disposition counts
    if diff_result["disposition_counts_changed"]:
        lines.append("[FAIL] Disposition counts changed")
        for disp in sorted(diff_result["disposition_counts_before"]):
            before = diff_result["disposition_counts_before"].get(disp, 0)
            after = diff_result["disposition_counts_after"].get(disp, 0)
            if before != after:
                lines.append(f"  {disp}: {before} -> {after}")
    else:
        lines.append("[PASS] Disposition counts unchanged")

    # Changed rows
    lines.append("")
    if diff_result["changed_candidate_count"] == 0:
        lines.append("[PASS] No semantic changes detected")
    else:
        lines.append(f"Changed candidates: {diff_result['changed_candidate_count']}")

        if diff_result["changed_field_counts"]:
            lines.append("Changed fields:")
            for field, count in sorted(diff_result["changed_field_counts"].items()):
                lines.append(f"  {field}: {count}")

        lines.append("")
        lines.append("Changed rows:")
        for row in diff_result["changed_rows"][:20]:  # Limit to 20 for display
            lines.append(f"  {row['candidate_id']}")
            for field in row["changed_fields"]:
                change = row["changes"][field]
                lines.append(f"    {field}:")
                if change["before"]:
                    lines.append(f"      - {change['before']}")
                if change["after"]:
                    lines.append(f"      + {change['after']}")

        if diff_result["changed_candidate_count"] > 20:
            lines.append(f"  ... and {diff_result['changed_candidate_count'] - 20} more")

    return "\n".join(lines)


def format_json_output(diff_result: dict, base_label: str, target_label: str) -> str:
    """Format diff result as deterministic JSON.

    Args:
        diff_result: Result from compute_diff
        base_label: Label for base
        target_label: Label for target

    Returns:
        JSON string
    """
    output = {
        "base": base_label,
        "target": target_label,
        "base_row_count": diff_result["base_row_count"],
        "target_row_count": diff_result["target_row_count"],
        "candidate_id_set_changed": diff_result["candidate_id_set_changed"],
        "added_candidate_ids": diff_result["added_candidate_ids"],
        "removed_candidate_ids": diff_result["removed_candidate_ids"],
        "common_candidate_count": diff_result["common_candidate_count"],
        "changed_candidate_count": diff_result["changed_candidate_count"],
        "unchanged_candidate_count": diff_result["unchanged_candidate_count"],
        "disposition_counts_before": diff_result["disposition_counts_before"],
        "disposition_counts_after": diff_result["disposition_counts_after"],
        "disposition_counts_changed": diff_result["disposition_counts_changed"],
        "changed_field_counts": diff_result["changed_field_counts"],
        "changed_rows": diff_result["changed_rows"],
    }
    return json.dumps(output, indent=2, sort_keys=True)
