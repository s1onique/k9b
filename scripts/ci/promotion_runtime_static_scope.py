"""Runtime static-scope producer for the experimental build lane.

Owner: CLI parsing, orchestration, record emission.
Delegates to:
  promotion_runtime_static_scope_contract: ScopeRecord schema/validation/checksums
  promotion_runtime_static_scope_git: Git primitives
  promotion_runtime_static_scope_policy: classification policy
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.ci.promotion_runtime_gate_manifest import load_manifest
from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
from scripts.ci.promotion_runtime_static_scope_git import (
    GitError,
    changed_python,
    get_head_sha,
    get_subject_tree,
    is_ancestor,
    resolve_revision,
)
from scripts.ci.promotion_runtime_static_scope_policy import (
    is_lane_authority_path,
    is_runtime_path,
    is_runtime_test_path,
    parse_nul_records,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_RUNTIME_BASE_SHA = "f09348dc6f7dd8887c51278ee0a504c7e22d1417"
DEFAULT_LANE_BASE_SHA = "9141f4699674353ac82a85e4fe543030ccfc1c42"


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="promotion_runtime_static_scope.py",
        description="Build a ScopeRecord for the dual-range experimental lane.",
    )
    parser.add_argument(
        "--runtime-base-sha",
        default=DEFAULT_RUNTIME_BASE_SHA,
        help=f"Runtime range base (default: {DEFAULT_RUNTIME_BASE_SHA})",
    )
    parser.add_argument(
        "--lane-base-sha",
        default=DEFAULT_LANE_BASE_SHA,
        help=f"Lane range base (default: {DEFAULT_LANE_BASE_SHA})",
    )
    parser.add_argument(
        "--subject-sha",
        required=True,
        help="Subject commit SHA (must be a full 40-char SHA or resolvable ref)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the ScopeRecord JSON to this path",
    )
    args = parser.parse_args(argv)

    try:
        record = build_scope(
            repo_root=args.repo_root,
            runtime_base_sha=args.runtime_base_sha,
            lane_base_sha=args.lane_base_sha,
            subject_sha=args.subject_sha,
        )
    except ScopeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except GitError as exc:
        print(f"FAIL: git error: {exc}", file=sys.stderr)
        return 1

    payload = record.to_dict()
    serialised = json.dumps(payload, indent=2, sort_keys=True)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised + "\n", encoding="utf-8")

    print(
        "OK: static scope (dual-range, CORRECTION08)\n"
        f"  runtime_base_sha               = {record.runtime_base_sha}\n"
        f"  lane_base_sha                  = {record.lane_base_sha}\n"
        f"  subject_sha                    = {record.subject_sha}\n"
        f"  subject_tree                   = {record.subject_tree}\n"
        f"  cumulative_changed_count       = {record.cumulative_changed_count}\n"
        f"  runtime_count                  = {record.runtime_count}\n"
        f"  lane_changed_count             = {record.lane_changed_count}\n"
        f"  lane_count                     = {record.lane_count}\n"
        f"  historical_nonruntime_count    = {record.historical_nonruntime_count}\n"
        f"  unclassified_count             = {record.unclassified_count}\n"
        f"  scope_record_sha256            = {record.scope_record_sha256}"
    )
    return 0


def build_scope(
    repo_root: Path,
    runtime_base_sha: str,
    lane_base_sha: str,
    subject_sha: str,
) -> ScopeRecord:
    """Build a ScopeRecord using the dual-range model.

    Resolves all revisions, validates topology, classifies paths, computes
    checksums, and returns a fully-validated ScopeRecord.
    """
    # --- P0-4: Resolve all revisions --------------------------------------
    runtime_full = resolve_revision(repo_root, runtime_base_sha)
    lane_full = resolve_revision(repo_root, lane_base_sha)
    subject_full = resolve_revision(repo_root, subject_sha)
    head_full = get_head_sha(repo_root)
    subject_tree = get_subject_tree(repo_root, subject_full)

    # --- P0-1: Topology checks -------------------------------------------
    if not is_ancestor(repo_root, runtime_full, subject_full):
        raise ScopeError(
            f"RUNTIME_BASE {runtime_full} is NOT an ancestor of SUBJECT {subject_full}"
        )
    if not is_ancestor(repo_root, lane_full, subject_full):
        raise ScopeError(
            f"LANE_BASE {lane_full} is NOT an ancestor of SUBJECT {subject_full}"
        )
    if head_full != subject_full:
        raise ScopeError(
            f"checked-out HEAD ({head_full}) != SUBJECT ({subject_full}); "
            "checkout SUBJECT before running static scope"
        )

    # --- CORRECTION10: Load manifest from subject object -----------------
    # This is subject-bound - reads from the Git object, not working tree
    manifest_report = load_manifest(
        repo_root=repo_root,
        subject_sha=subject_full,
        manifest_path="scripts/ci/promotion_runtime_tests.txt",
    )
    runtime_test_paths = manifest_report.runtime_test_paths

    # --- P0-5: Cumulative changed Python ----------------------------------
    cumulative_raw = changed_python(repo_root, runtime_full, subject_full)
    cumulative_paths = parse_nul_records(cumulative_raw)

    # Deduplicate
    cumulative_unique: list[str] = []
    seen: set[str] = set()
    for p in cumulative_paths:
        if p not in seen:
            seen.add(p)
            cumulative_unique.append(p)
    cumulative_sorted = tuple(sorted(cumulative_unique))

    # --- P0-6: Runtime bucket (src/k8s_diag_agent/ only) ------------------
    runtime_paths = tuple(sorted(p for p in cumulative_sorted if is_runtime_path(p)))

    # --- P0-7: Lane bucket (LANE_BASE..SUBJECT minus runtime) -------------
    lane_raw = changed_python(repo_root, lane_full, subject_full)
    lane_candidates = parse_nul_records(lane_raw)
    lane_candidates_set = frozenset(lane_candidates)

    # Subtract runtime_paths from lane candidates (expected overlap)
    lane_candidates_after_subtract = lane_candidates_set - frozenset(runtime_paths)

    # Classify remaining as lane or unclassified
    # CORRECTION10: Also classify manifest-listed runtime-test paths as lane authority.
    # Pass runtime_test_paths explicitly - no global cache.
    lane_paths: list[str] = []
    unclassified_paths: list[str] = []
    for p in sorted(lane_candidates_after_subtract):
        if is_lane_authority_path(p) or is_runtime_test_path(p, runtime_test_paths):
            lane_paths.append(p)
        else:
            unclassified_paths.append(p)

    lane_sorted = tuple(lane_paths)
    unclassified_sorted = tuple(unclassified_paths)

    # --- P0-8: Historical non-runtime bucket ------------------------------
    # Derive from cumulative minus runtime minus lane_changed (NOT from tree enumeration)
    runtime_set = frozenset(runtime_paths)
    lane_set = frozenset(lane_sorted)
    cumulative_set = frozenset(cumulative_sorted)

    historical_nonruntime = tuple(
        sorted(cumulative_set - runtime_set - lane_set)
    )

    # --- P0-9: Verify bucket invariants ------------------------------------
    if unclassified_sorted:
        raise ScopeError(
            f"unclassified paths (hard fail): {sorted(unclassified_sorted)!r}"
        )

    # --- Verify disk existence of included paths ----------------------------
    for path in runtime_paths:
        if not (repo_root / path).exists():
            raise ScopeError(f"runtime path does not exist on disk: {path!r}")
    for path in lane_sorted:
        if not (repo_root / path).exists():
            raise ScopeError(f"lane path does not exist on disk: {path!r}")

    # --- Build and checksum -------------------------------------------------
    record = ScopeRecord(
        runtime_base_sha=runtime_full,
        lane_base_sha=lane_full,
        subject_sha=subject_full,
        subject_tree=subject_tree,
        repo_root=".",
        cumulative_changed_python=cumulative_sorted,
        runtime_paths=runtime_paths,
        lane_changed_python=tuple(sorted(lane_candidates)),
        lane_paths=lane_sorted,
        historical_nonruntime_paths=historical_nonruntime,
        unclassified_paths=unclassified_sorted,
        cumulative_changed_count=len(cumulative_sorted),
        runtime_count=len(runtime_paths),
        lane_changed_count=len(lane_candidates),
        lane_count=len(lane_sorted),
        historical_nonruntime_count=len(historical_nonruntime),
        unclassified_count=len(unclassified_sorted),
        cumulative_changed_sha256="",
        runtime_paths_sha256="",
        lane_changed_sha256="",
        lane_paths_sha256="",
        historical_nonruntime_sha256="",
        unclassified_sha256="",
        included_paths_sha256="",
        scope_record_sha256="",
    )

    # Compute checksums
    record = record.with_checksums()

    # Validate the record
    record.validate()
    record.verify_checksums()

    return record


if __name__ == "__main__":
    sys.exit(_run())
