#!/usr/bin/env python3
"""CLI wrapper for semantic disposition diff reporter.

This script is the entry point; all logic lives in modular sub-packages:
- docs_claim_disposition_diff_loader  -- git/ref and CSV loading
- docs_claim_disposition_diff_model   -- diff computation
- docs_claim_disposition_diff_report  -- human/JSON formatting
- docs_claim_disposition_diff_selftest -- self-test fixtures

Usage:
    python scripts/diff_docs_claim_dispositions.py --self-test
    python scripts/diff_docs_claim_dispositions.py --base-ref HEAD~1 --target-ref HEAD
    python scripts/diff_docs_claim_dispositions.py --base-ref 7540e6d --target-ref 11dbdc0
    python scripts/diff_docs_claim_dispositions.py --base-ref HEAD~1 --target-ref HEAD --json /tmp/diff.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docs_claim_disposition_diff_loader import load_dispositions_from_dir, load_dispositions_from_ref
from docs_claim_disposition_diff_model import compute_diff
from docs_claim_disposition_diff_report import format_human_output, format_json_output
from docs_claim_disposition_diff_selftest import run_self_test


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

    # Check for duplicates across shards
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
        filtered_rows = [
            r for r in diff_result["changed_rows"] if r["candidate_id"] == args.candidate_id
        ]
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
