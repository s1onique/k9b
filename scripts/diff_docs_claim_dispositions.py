#!/usr/bin/env python3
"""Semantic diff reporter for documentation claim disposition shards.

Compares parsed disposition rows by candidate_id across git refs, reports changed
fields, validates stable row sets and disposition counts, and emits optional
deterministic JSON.

This enables future long-tail documentation truthfulness tranches to be reviewable
even when CSV-safe writers reserialize entire shards.

Usage:
    python scripts/diff_docs_claim_dispositions.py --base-ref HEAD~1 --target-ref HEAD
    python scripts/diff_docs_claim_dispositions.py --base-ref 7540e6d --target-ref 11dbdc0
    python scripts/diff_docs_claim_dispositions.py --base-ref HEAD~1 --target-ref HEAD --json /tmp/diff.json
    python scripts/diff_docs_claim_dispositions.py --self-test
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Constants duplicated from verify_docs_claim_disposition_csv_integrity.py
# (not imported to avoid CLI coupling)
REPO_ROOT = Path(__file__).parent.parent
SHARDS_DIR = REPO_ROOT / "docs" / "claims"
SHARD_PATTERN = "docs_claim_dispositions-shard-*.csv"
CANDIDATE_ID_RE = re.compile(r"^DOC-CAND-[0-9a-f]{12}$")
REQUIRED_COLUMNS = [
    "candidate_id",
    "disposition",
    "claim_id",
    "covered_by_claim_id",
    "reason_code",
    "reviewed_at",
    "reviewer_notes",
]
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


def git_ls_tree(ref: str, path: str) -> list[str]:
    """List files at path within a git ref using ls-tree.

    Args:
        ref: Git ref (commit, branch, tag, etc.)
        path: Relative path within repo

    Returns:
        List of relative file paths from the repo root

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-tree", "-r", "--name-only", ref, "--", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def git_show(ref: str, path: str) -> str:
    """Get file content from a git ref.

    Args:
        ref: Git ref
        path: Relative path within repo

    Returns:
        File content as string

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{ref}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def load_dispositions_from_ref(ref: str) -> tuple[list[dict[str, str]], list[str]]:
    """Load all disposition shards from a git ref.

    Args:
        ref: Git ref to load from

    Returns:
        (rows, errors) where rows is list of parsed CSV rows and errors is list
        of validation error messages
    """
    errors: list[str] = []
    all_rows: list[dict[str, str]] = []

    # Find all shard files in the ref
    try:
        shard_paths = git_ls_tree(ref, "docs/claims")
    except subprocess.CalledProcessError as exc:
        return [], [f"git ls-tree failed: {exc.stderr.strip()}"]

    shard_files = sorted(p for p in shard_paths if "docs_claim_dispositions-shard-" in p and p.endswith(".csv"))

    if not shard_files:
        return [], [f"No disposition shards found in ref {ref}"]

    for shard_path in shard_files:
        try:
            content = git_show(ref, shard_path)
        except subprocess.CalledProcessError as exc:
            errors.append(f"git show failed for {shard_path}: {exc.stderr.strip()}")
            continue

        shard_errors, shard_rows = _parse_shard_content(shard_path, content)
        errors.extend(shard_errors)
        all_rows.extend(shard_rows)

    # Validate overall structure
    if not all_rows and not errors:
        errors.append(f"No data rows found in any shard from ref {ref}")

    return all_rows, errors


def load_dispositions_from_dir(base_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Load all disposition shards from a local directory.

    Args:
        base_dir: Directory containing disposition shards

    Returns:
        (rows, errors)
    """
    errors: list[str] = []
    all_rows: list[dict[str, str]] = []

    shard_files = sorted(base_dir.glob("docs/claims/docs_claim_dispositions-shard-*.csv"))

    if not shard_files:
        return [], [f"No disposition shards found in {base_dir}/docs/claims/"]

    for shard_path in shard_files:
        try:
            content = shard_path.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"Failed to read {shard_path}: {exc}")
            continue

        shard_errors, shard_rows = _parse_shard_content(str(shard_path), content)
        errors.extend(shard_errors)
        all_rows.extend(shard_rows)

    return all_rows, errors


def _parse_shard_content(shard_path: str, content: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a single shard's content with strict validation.

    Args:
        shard_path: Path for error messages
        content: Raw CSV content

    Returns:
        (errors, rows)
    """
    errors: list[str] = []
    rows: list[dict[str, str]] = []

    if not content.strip():
        return [f"{shard_path}: empty file"], []

    # Check for physical blank lines
    for line_num, line in enumerate(content.splitlines(), start=1):
        if line.strip() == "":
            errors.append(f"{shard_path}:{line_num}: physical blank line")
            return errors, []

    try:
        buf = io.StringIO(content)
        reader = csv.DictReader(buf)

        if reader.fieldnames is None:
            return [f"{shard_path}: no header row"], []

        if list(reader.fieldnames) != REQUIRED_COLUMNS:
            actual = reader.fieldnames
            if len(actual) > len(REQUIRED_COLUMNS):
                extra = [c for c in actual if c not in REQUIRED_COLUMNS]
                errors.append(f"{shard_path}: extra named columns: {extra}")
            elif len(actual) < len(REQUIRED_COLUMNS):
                missing = [c for c in REQUIRED_COLUMNS if c not in actual]
                errors.append(f"{shard_path}: missing required columns: {missing}")
            else:
                errors.append(f"{shard_path}: header mismatch")
            return errors, []

        for line_num, raw_row in enumerate(reader, start=2):
            if None in raw_row.values():
                errors.append(f"{shard_path}:{line_num}: row has fewer fields than header")
                continue

            if all(v == "" for v in raw_row.values()):
                errors.append(f"{shard_path}:{line_num}: blank row")
                continue

            if list(raw_row.keys()) != REQUIRED_COLUMNS:
                errors.append(f"{shard_path}:{line_num}: row shape mismatch")
                continue

            cid = raw_row.get("candidate_id", "")
            if not cid:
                errors.append(f"{shard_path}:{line_num}: empty candidate_id")
                continue

            if not CANDIDATE_ID_RE.match(cid):
                errors.append(f"{shard_path}:{line_num}: invalid candidate_id format: {cid!r}")
                continue

            # Check for duplicates within this shard
            if cid in [r.get("candidate_id") for r in rows]:
                errors.append(f"{shard_path}:{line_num}: duplicate candidate_id: {cid}")
                continue

            rows.append(raw_row)

        if not rows and not errors:
            errors.append(f"{shard_path}: header-only CSV (0 data rows)")

    except csv.Error as exc:
        errors.append(f"{shard_path}: csv.Error: {exc}")
    except Exception as exc:
        errors.append(f"{shard_path}: {type(exc).__name__}: {exc}")

    return errors, rows


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
            lines.append(f"  Added: {len(diff_result['added_candidate_ids'])} ({diff_result['added_candidate_ids'][:5]}...)" if len(diff_result['added_candidate_ids']) > 5 else f"  Added: {diff_result['added_candidate_ids']}")
        if diff_result["removed_candidate_ids"]:
            lines.append(f"  Removed: {len(diff_result['removed_candidate_ids'])} ({diff_result['removed_candidate_ids'][:5]}...)" if len(diff_result['removed_candidate_ids']) > 5 else f"  Removed: {diff_result['removed_candidate_ids']}")
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


# ---------------------------------------------------------------------------
# Self-test fixtures
# ---------------------------------------------------------------------------

FIXTURES: list[tuple[str, str, str, bool, bool, bool]] = [
    # (name, base_csv, target_csv, expect_pass, expect_changed, expect_changed_fields)
    (
        "identical inputs",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
            "DOC-CAND-000000000002,stale,,,obsolete_doc,2026-06-19,note2\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
            "DOC-CAND-000000000002,stale,,,obsolete_doc,2026-06-19,note2\n"
        ),
        True,  # expect_pass (no added/removed)
        False,  # expect_changed
        False,  # expect_field_changes
    ),
    (
        "reviewer_notes-only change",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,original note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,improved note after review\n"
        ),
        True,  # expect_pass (no added/removed)
        True,  # expect_changed
        True,  # expect_field_changes (reviewer_notes only)
    ),
    (
        "disposition change",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,stale,,,obsolete_doc,2026-06-19,note\n"
        ),
        False,  # expect_pass (disposition counts changed)
        True,  # expect_changed
        True,  # expect_field_changes (disposition, reason_code)
    ),
    (
        "added candidate ID",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
            "DOC-CAND-000000000002,stale,,,obsolete_doc,2026-06-19,new note\n"
        ),
        False,  # expect_pass (added candidate -> row set change)
        False,  # expect_changed (added IDs tracked separately, not in changed_rows)
        False,  # no field changes, only added row
    ),
    (
        "removed candidate ID",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
            "DOC-CAND-000000000002,stale,,,obsolete_doc,2026-06-19,note2\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
        ),
        False,  # expect_pass (removed candidate -> row set change)
        False,  # expect_changed (removed IDs tracked separately, not in changed_rows)
        False,  # no field changes, only removed row
    ),
    (
        "duplicate candidate ID in base",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note2\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note1\n"
        ),
        False,  # expect_pass (duplicate causes parse error)
        False,  # N/A
        False,  # N/A
    ),
    (
        "invalid candidate ID in target",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-INVALID,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        False,  # expect_pass (parse error)
        False,  # N/A
        False,  # N/A
    ),
    (
        "malformed/missing header in base",
        "",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-000000000001,ignored_by_policy,,,low_value_context,2026-06-19,note\n"
        ),
        False,  # expect_pass (parse error)
        False,  # N/A
        False,  # N/A
    ),
    (
        "ACT 5.0-like: broad reserialization with reviewer_notes changes only",
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            "DOC-CAND-49a09e000a77,ignored_by_policy,,,low_value_context,2026-06-19,Low-value prose fragment from: docs/data-model/incidents.md\n"
            "DOC-CAND-49a09e000a78,ignored_by_policy,,,low_value_context,2026-06-19,Another prose fragment\n"
            "DOC-CAND-49a09e000a79,stale,,,obsolete_doc,2026-06-19,Old stale note\n"
        ),
        (
            "candidate_id,disposition,claim_id,covered_by_claim_id,reason_code,reviewed_at,reviewer_notes\n"
            'DOC-CAND-49a09e000a77,ignored_by_policy,,,low_value_context,2026-06-19,"Low-value prose fragment from docs/data-model/incidents.md: schema table header label, formatting artifact not a claim (ACT 5.0 review)."\n'
            'DOC-CAND-49a09e000a78,ignored_by_policy,,,low_value_context,2026-06-19,"Another prose fragment updated (ACT 5.0 review)."\n'
            "DOC-CAND-49a09e000a79,stale,,,obsolete_doc,2026-06-19,Old stale note\n"
        ),
        True,  # expect_pass (no added/removed, no disposition changes)
        True,  # expect_changed
        True,  # expect_field_changes (reviewer_notes only)
    ),
]


def _parse_fixture_csv(content: str) -> tuple[list[dict[str, str]], list[str]]:
    """Parse fixture CSV content."""
    if not content.strip():
        return [], ["empty CSV"]
    errors, rows = _parse_shard_content("(fixture)", content)
    return rows, errors


def run_self_test() -> bool:
    """Run self-test fixtures. Returns True if all pass."""
    all_passed = True

    for name, base_csv, target_csv, expect_pass, expect_changed, expect_field_changes in FIXTURES:
        base_rows, base_errors = _parse_fixture_csv(base_csv)
        target_rows, target_errors = _parse_fixture_csv(target_csv)

        # Check for parse errors
        if base_errors or target_errors:
            if expect_pass:
                print(f"[FAIL] {name}: unexpected parse errors - base: {base_errors}, target: {target_errors}")
                all_passed = False
            else:
                print(f"[PASS] {name}: correctly rejected (parse error)")
            continue

        # Check duplicates
        base_ids = [r["candidate_id"] for r in base_rows]
        target_ids = [r["candidate_id"] for r in target_rows]
        if len(base_ids) != len(set(base_ids)):
            print(f"[FAIL] {name}: base has duplicate candidate IDs")
            all_passed = False
            continue
        if len(target_ids) != len(set(target_ids)):
            print(f"[FAIL] {name}: target has duplicate candidate IDs")
            all_passed = False
            continue

        # Compute diff
        diff_result = compute_diff(base_rows, target_rows)

        # Determine actual pass/fail
        # Pass means: no added/removed candidates AND (no field changes OR disposition counts unchanged)
        actual_pass = not diff_result["candidate_id_set_changed"]
        if actual_pass and diff_result["disposition_counts_changed"]:
            # Changed disposition counts fail by default
            actual_pass = False

        if actual_pass != expect_pass:
            print(f"[FAIL] {name}: pass={actual_pass}, expected pass={expect_pass}")
            all_passed = False
            continue

        if expect_changed:
            if diff_result["changed_candidate_count"] == 0:
                print(f"[FAIL] {name}: expected changes but got none")
                all_passed = False
                continue

        if expect_field_changes:
            if not diff_result["changed_field_counts"]:
                print(f"[FAIL] {name}: expected field changes but got none")
                all_passed = False
                continue

        # Verify JSON output is deterministic
        json_output = format_json_output(diff_result, "base", "target")
        try:
            parsed = json.loads(json_output)
            if not isinstance(parsed, dict):
                print(f"[FAIL] {name}: JSON output not a dict")
                all_passed = False
                continue
            # Re-serialize to check determinism
            re_serialized = json.dumps(parsed, indent=2, sort_keys=True)
            if json_output != re_serialized:
                print(f"[FAIL] {name}: JSON output not deterministic")
                all_passed = False
                continue
        except json.JSONDecodeError as exc:
            print(f"[FAIL] {name}: JSON output invalid: {exc}")
            all_passed = False
            continue

        print(f"[PASS] {name}")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Semantic diff reporter for documentation claim disposition shards"
    )
    parser.add_argument("--self-test", action="store_true", help="Run self-test fixtures and exit")
    parser.add_argument("--base-ref", help="Base git ref")
    parser.add_argument("--target-ref", help="Target git ref")
    parser.add_argument("--base-dir", type=Path, help="Base directory (alternative to --base-ref)")
    parser.add_argument("--target-dir", type=Path, help="Target directory (alternative to --target-ref)")
    parser.add_argument("--json", type=Path, help="Write JSON output to file")
    parser.add_argument("--candidate-id", help="Filter to specific candidate ID")
    parser.add_argument("--only-changed", action="store_true", help="Show only changed candidates")
    parser.add_argument(
        "--allow-row-set-change",
        action="store_true",
        help="Allow added/removed candidate IDs (for candidate regeneration workflows)",
    )

    args = parser.parse_args()

    if args.self_test:
        print("=== Self-Test Fixtures ===")
        ok = run_self_test()
        if not ok:
            print("\n[FAIL] self-test failed")
            return 1
        print("\n[PASS] all self-tests passed")
        return 0

    # Validate arguments
    has_refs = bool(args.base_ref) and bool(args.target_ref)
    has_dirs = bool(args.base_dir) and bool(args.target_dir)

    if not has_refs and not has_dirs:
        parser.error("Either --base-ref/--target-ref or --base-dir/--target-dir required")

    if has_refs and has_dirs:
        parser.error("Cannot specify both --base-ref/--target-ref and --base-dir/--target-dir")

    # Load dispositions
    if has_refs:
        base_label = args.base_ref
        target_label = args.target_ref
        base_rows, base_errors = load_dispositions_from_ref(args.base_ref)
        target_rows, target_errors = load_dispositions_from_ref(args.target_ref)
    else:
        base_label = str(args.base_dir)
        target_label = str(args.target_dir)
        base_rows, base_errors = load_dispositions_from_dir(args.base_dir)
        target_rows, target_errors = load_dispositions_from_dir(args.target_dir)

    # Report load errors
    if base_errors:
        print("[FAIL] Base load errors:")
        for err in base_errors:
            print(f"  {err}")
        return 1

    if target_errors:
        print("[FAIL] Target load errors:")
        for err in target_errors:
            print(f"  {err}")
        return 1

    # Check for duplicates
    base_ids = [r["candidate_id"] for r in base_rows]
    target_ids = [r["candidate_id"] for r in target_rows]
    if len(base_ids) != len(set(base_ids)):
        dupes = [cid for cid in set(base_ids) if base_ids.count(cid) > 1]
        print(f"[FAIL] Base has duplicate candidate IDs: {dupes}")
        return 1
    if len(target_ids) != len(set(target_ids)):
        dupes = [cid for cid in set(target_ids) if target_ids.count(cid) > 1]
        print(f"[FAIL] Target has duplicate candidate IDs: {dupes}")
        return 1

    # Compute diff
    diff_result = compute_diff(base_rows, target_rows)

    # Filter to specific candidate if requested
    if args.candidate_id:
        filtered_rows = [r for r in diff_result["changed_rows"] if r["candidate_id"] == args.candidate_id]
        diff_result["changed_rows"] = filtered_rows
        diff_result["changed_candidate_count"] = len(filtered_rows)

    # Write JSON if requested
    if args.json:
        json_output = format_json_output(diff_result, base_label, target_label)
        try:
            args.json.write_text(json_output, encoding="utf-8")
            print(f"[INFO] JSON output written to {args.json}")
        except Exception as exc:
            print(f"[FAIL] Failed to write JSON: {exc}")
            return 1

    # Determine pass/fail
    has_row_set_change = diff_result["candidate_id_set_changed"]
    has_disp_change = diff_result["disposition_counts_changed"]

    fail = False
    if has_row_set_change and not args.allow_row_set_change:
        fail = True
    if has_disp_change:
        fail = True

    # Print human output
    output = format_human_output(diff_result, base_label, target_label)
    print(output)

    if fail:
        print("\n[FAIL] Semantic diff failed")
        return 1

    print("\n[PASS] Semantic diff passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
