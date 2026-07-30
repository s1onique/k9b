"""Runtime static-gate runner (Ruff + mypy) for the experimental build lane.

Owner: Ruff/mypy execution, scope record consumption.
ScopeRecord schema lives in promotion_runtime_static_scope_contract.py.
Git primitives live in promotion_runtime_static_scope_git.py.

Contract:
  - Inputs come exclusively from the static-scope authority produced by
    ``scripts/ci/promotion_runtime_static_scope.py``.  No ad-hoc git diff.
  - Ruff and mypy are invoked through subprocess.run([...]) with an argv list.
  - Both tools are BLOCKING.  No || true, no continue-on-error.
  - Output record is emitted as JSON to --output (if given) and stdout summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts.ci.promotion_runtime_static_scope_contract import ScopeRecord, ScopeError
from scripts.ci.promotion_runtime_static_scope_git import get_head_sha, get_subject_tree

REPO_ROOT = Path(__file__).resolve().parents[2]


def _invoke(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run the supplied argv list; return (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


def run_gate(
    repo_root: Path,
    scope: ScopeRecord,
    python_executable: str = sys.executable,
) -> dict[str, object]:
    """Execute Ruff + mypy against runtime_paths + lane_paths.

    Returns a dict with ruff and mypy results and scope metadata.

    Raises ScopeError if included path set is empty.
    """
    included = list(scope.runtime_paths) + list(scope.lane_paths)

    if not included:
        raise ScopeError(
            "scope authority returned zero included paths; "
            "refusing to run Ruff/mypy against an empty target set"
        )

    ruff_rc, ruff_out, ruff_err = _invoke(
        [python_executable, "-m", "ruff", "check", *included],
        cwd=repo_root,
    )
    mypy_rc, mypy_out, mypy_err = _invoke(
        [python_executable, "-m", "mypy", *included],
        cwd=repo_root,
    )

    return {
        "scope_record_sha256": scope.scope_record_sha256,
        "included_paths_sha256": scope.included_paths_sha256,
        "ruff_target_count": len(included),
        "ruff_exit_code": ruff_rc,
        "ruff_stdout_lines": ruff_out.count("\n"),
        "mypy_target_count": len(included),
        "mypy_exit_code": mypy_rc,
        "mypy_stdout_lines": mypy_out.count("\n"),
        "unclassified_count": scope.unclassified_count,
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="promotion_runtime_static_gate_runner.py",
        description="Run Ruff + mypy against the scope authority's included paths.",
    )
    parser.add_argument(
        "--scope-record",
        type=Path,
        required=True,
        help="Path to a pre-produced ScopeRecord JSON (required)",
    )
    parser.add_argument(
        "--expected-subject-sha",
        type=str,
        default=None,
        help="Subject SHA for workflow verification; fails if mismatch",
    )
    parser.add_argument(
        "--expected-subject-tree",
        type=str,
        default=None,
        help="Subject tree SHA for workflow verification; fails if mismatch",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the gate record JSON to this path",
    )
    args = parser.parse_args(argv)

    # --- Load and decode via contract ---------------------------------------
    scope_data = json.loads(args.scope_record.read_text(encoding="utf-8"))

    try:
        scope = ScopeRecord.from_dict(scope_data)
    except ScopeError as exc:
        print(f"FAIL: scope record decode error: {exc}", file=sys.stderr)
        return 2

    # --- Validate structure --------------------------------------------------
    try:
        scope.validate()
    except ScopeError as exc:
        print(f"FAIL: scope record validation error: {exc}", file=sys.stderr)
        return 2

    # --- Verify checksums -----------------------------------------------------
    try:
        scope.verify_checksums()
    except ScopeError as exc:
        print(f"FAIL: scope record checksum mismatch: {exc}", file=sys.stderr)
        return 2

    # --- Verify subject identity (P0-4) --------------------------------------
    if args.expected_subject_sha is not None:
        if scope.subject_sha != args.expected_subject_sha:
            print(
                f"FAIL: subject_sha mismatch: expected {args.expected_subject_sha}, "
                f"got {scope.subject_sha}",
                file=sys.stderr,
            )
            return 2

    if args.expected_subject_tree is not None:
        if scope.subject_tree != args.expected_subject_tree:
            print(
                f"FAIL: subject_tree mismatch: expected {args.expected_subject_tree}, "
                f"got {scope.subject_tree}",
                file=sys.stderr,
            )
            return 2

    # --- Independently verify HEAD and tree (defense-in-depth) ----------------
    try:
        head = get_head_sha(args.repo_root)
        tree = get_subject_tree(args.repo_root, head)
        if head != scope.subject_sha:
            print(
                f"FAIL: checked-out HEAD ({head}) != subject ({scope.subject_sha})",
                file=sys.stderr,
            )
            return 2
        if tree != scope.subject_tree:
            print(
                f"FAIL: HEAD tree ({tree}) != subject_tree ({scope.subject_tree})",
                file=sys.stderr,
            )
            return 2
    except Exception as exc:
        print(f"FAIL: local HEAD/tree verification failed: {exc}", file=sys.stderr)
        return 2

    # --- Execute gate --------------------------------------------------------
    try:
        record = run_gate(args.repo_root, scope)
    except ScopeError as exc:
        print(f"FAIL: gate execution error: {exc}", file=sys.stderr)
        return 2

    # --- Emit output --------------------------------------------------------
    serialised = json.dumps(record, indent=2, sort_keys=True)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised + "\n", encoding="utf-8")

    print(
        "OK: static gate\n"
        f"  scope_record_sha256       = {record['scope_record_sha256']}\n"
        f"  ruff_target_count         = {record['ruff_target_count']}\n"
        f"  ruff_exit_code            = {record['ruff_exit_code']}\n"
        f"  mypy_target_count         = {record['mypy_target_count']}\n"
        f"  mypy_exit_code            = {record['mypy_exit_code']}\n"
        f"  unclassified_count        = {record['unclassified_count']}"
    )

    # Exit non-zero if either tool failed
    if record["ruff_exit_code"] != 0 or record["mypy_exit_code"] != 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
