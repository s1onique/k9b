"""Runtime static-gate runner (Ruff + mypy) for the experimental build lane.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION06

This script is the SINGLE authority that runs the runtime-scoped Ruff
and mypy checks for the experimental build lane.

Contract:

* Inputs come exclusively from the static-scope authority produced by
  ``scripts/ci/promotion_runtime_static_scope.py``.  No ad-hoc
  ``git diff`` invocation.
* Ruff and mypy are invoked through ``subprocess.run([...])`` with an
  argv list, never shell-expanded.
* Both tools remain BLOCKING.  No ``|| true``, no
  ``continue-on-error``, no grep-based silent exclusion.
* mypy follows imported runtime modules under the repository's normal
  ``mypy.ini`` configuration.
* Output record is emitted as a single structured JSON line to
  ``--output`` (if given) and a human-readable summary on stdout.

Required output fields:

  scope_inventory_sha256
  ruff_target_count
  ruff_exit_code
  mypy_target_count
  mypy_exit_code
  deferred_path_count
  unclassified_count
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

from promotion_runtime_static_scope import (
    ScopeError,
    ScopeRecord,
    build_scope,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclasses.dataclass(frozen=True)
class GateRecord:
    scope_inventory_sha256: str
    ruff_target_count: int
    ruff_exit_code: int
    mypy_target_count: int
    mypy_exit_code: int
    deferred_path_count: int
    unclassified_count: int

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def _invoke(argv: list[str], cwd: Path) -> int:
    """Run the supplied argv list; return the subprocess exit code."""
    proc = subprocess.run(argv, cwd=cwd, check=False)
    return proc.returncode


def run_gate(
    repo_root: Path,
    scope: ScopeRecord,
    python_executable: str = sys.executable,
) -> GateRecord:
    """Execute Ruff + mypy against the scope authority's included paths.

    Raises:
        ScopeError: if the scope record has zero included paths.
    """
    included = list(scope.included_paths)
    if not included:
        raise ScopeError(
            "scope authority returned zero included paths; refusing to "
            "run Ruff/mypy against an empty target set"
        )

    ruff_rc = _invoke(
        [python_executable, "-m", "ruff", "check", *included],
        cwd=repo_root,
    )
    mypy_rc = _invoke(
        [python_executable, "-m", "mypy", *included],
        cwd=repo_root,
    )

    return GateRecord(
        scope_inventory_sha256=scope.inventory_sha256,
        ruff_target_count=len(included),
        ruff_exit_code=ruff_rc,
        mypy_target_count=len(included),
        mypy_exit_code=mypy_rc,
        deferred_path_count=len(scope.deferred_paths_with_reasons),
        unclassified_count=scope.unclassified_count,
    )


def _verify_scope_checksum(scope: ScopeRecord) -> None:
    """Verify the scope record's checksum by re-hashing included paths.

    P0-5 contract: the static gate must consume and verify the
    checksummed scope record, not independently recompute it.
    """
    import hashlib

    included = sorted(scope.included_paths)
    # NUL-delimited canonical hash matching build_scope().
    inventory_bytes = b"\x00".join(
        p.encode("utf-8") for p in included
    ) + b"\x00"
    computed = hashlib.sha256(inventory_bytes).hexdigest()
    if computed != scope.inventory_sha256:
        raise ScopeError(
            f"scope record checksum mismatch: expected {scope.inventory_sha256}, "
            f"computed {computed} — record may have been tampered with; "
            "the gate must not recompute scope independently"
        )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="promotion_runtime_static_gate_runner.py",
        description=__doc__,
    )
    parser.add_argument(
        "--scope-record",
        type=Path,
        default=None,
        help="Path to a pre-produced scope authority JSON record",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--scope-output",
        type=Path,
        default=None,
        help="Optional path to write the scope authority JSON record to "
        "(used when --scope-record is not given)",
    )
    args = parser.parse_args(argv)

    # P0-5: consume pre-produced scope record, verify its checksum.
    if args.scope_record is not None:
        scope_data = json.loads(args.scope_record.read_text(encoding="utf-8"))
        # Reconstruct ScopeRecord from JSON.
        included_paths_raw = scope_data.get("included_paths", [])
        deferred_paths_raw = scope_data.get("deferred_paths_with_reasons", [])
        deferred_paths: list[tuple[str, str]] = [
            (d["path"], d["reason"]) for d in deferred_paths_raw
        ]
        scope = ScopeRecord(
            base_sha=scope_data["base_sha"],
            subject_sha=scope_data["subject_sha"],
            repo_root=scope_data.get("repo_root", "."),
            changed_python_count=scope_data.get("changed_python_count", 0),
            runtime_source_count=scope_data.get("runtime_source_count", 0),
            lane_authority_count=scope_data.get("lane_authority_count", 0),
            deferred_count=scope_data.get("deferred_count", 0),
            unclassified_count=scope_data.get("unclassified_count", 0),
            included_paths=tuple(included_paths_raw),
            deferred_paths_with_reasons=tuple(deferred_paths),
            inventory_sha256=scope_data["inventory_sha256"],
            raw_inventory_sha256=scope_data.get("raw_inventory_sha256", ""),
        )
        # P0-5: verify checksum — fail closed on mismatch.
        try:
            _verify_scope_checksum(scope)
        except ScopeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
    else:
        # Fallback: produce scope record (used by tests/CI that chain the two).
        try:
            scope = build_scope(args.repo_root, "HEAD~1", "HEAD")
        except ScopeError as exc:
            print(f"FAIL: scope authority rejected inventory: {exc}", file=sys.stderr)
            return 2
        if args.scope_output is not None:
            args.scope_output.parent.mkdir(parents=True, exist_ok=True)
            args.scope_output.write_text(
                json.dumps(scope.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    try:
        record = run_gate(args.repo_root, scope)
    except ScopeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    payload = record.to_dict()
    serialised = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised + "\n", encoding="utf-8")

    print(
        "OK: runtime static gate\n"
        f"  scope_inventory_sha256 = {record.scope_inventory_sha256}\n"
        f"  ruff_target_count      = {record.ruff_target_count}\n"
        f"  ruff_exit_code         = {record.ruff_exit_code}\n"
        f"  mypy_target_count      = {record.mypy_target_count}\n"
        f"  mypy_exit_code         = {record.mypy_exit_code}\n"
        f"  deferred_path_count    = {record.deferred_path_count}\n"
        f"  unclassified_count     = {record.unclassified_count}"
    )
    # Exit non-zero if either tool reported errors.
    if record.ruff_exit_code != 0 or record.mypy_exit_code != 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())