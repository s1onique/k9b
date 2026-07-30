"""Runtime static-scope authority for the experimental build lane.

Dual-range model: separates RUNTIME_BASE (runtime source evolution) from
LANE_BASE (lane authority evolution), with a mandatory SUBJECT head.

Three mutually-exclusive categories:
  A. RUNTIME_PATHS  - Python under src/k8s_diag_agent/ changed since RUNTIME_BASE
  B. LANE_PATHS     - Lane authority scripts/tests changed since LANE_BASE
  H. HISTORICAL     - Python files present in RUNTIME_BASE tree but NOT changed
                      in either range (historical non-runtime)
  D. UNCLASSIFIED   - Any path not matched by A, B, or H.  D > 0 is HARD FAIL.

Mechanics:

* ``git diff -z --diff-filter=ACMRT RUNTIME_BASE..SUBJECT -- '*.py'`` → runtime_changed
* ``git diff -z --diff-filter=ACMRT LANE_BASE..SUBJECT -- '*.py'`` → lane_changed
* ``git ls-tree -r --name-only RUNTIME_BASE -- '*.py'`` → all_historical_python
* All paths consumed raw NUL-delimited from subprocess (no tr / mapfile).
* Repository-relative POSIX paths only.
* Reject: absolute paths, ``..``, backslashes, embedded NUL, duplicates.

Outputs a single structured JSON record (one line) to ``--output`` plus a
human-readable summary on stdout.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Default SHAs (CORRECTION07 baseline).
# ---------------------------------------------------------------------------

DEFAULT_RUNTIME_BASE_SHA = "f09348dc6f7dd8887c51278ee0a504c7e22d1417"
DEFAULT_LANE_BASE_SHA = "9141f4699674353ac82a85e4fe543030ccfc1c42"

# ---------------------------------------------------------------------------
# Scope policy (CORRECTION07 contract).
# ---------------------------------------------------------------------------

# Category A: runtime source prefix.
RUNTIME_SOURCE_PREFIXES: tuple[str, ...] = (
    "src/k8s_diag_agent/",
)

# Category B: experimental-lane authority.  Production scripts that own
# the experimental build lane and the directly associated contract tests.
EXPERIMENTAL_LANE_AUTHORITY_PATHS: frozenset[str] = frozenset({
    # Runtime gate runner
    "scripts/ci/run_promotion_runtime_gate.py",
    "scripts/ci/promotion_runtime_gate_manifest.py",
    "scripts/ci/promotion_runtime_gate_pytest.py",
    "scripts/ci/promotion_runtime_gate_transcript.py",
    # Static scope
    "scripts/ci/promotion_runtime_static_scope.py",
    "scripts/ci/promotion_runtime_static_gate_runner.py",
    # Plugin
    "scripts/ci/pytest_runtime_gate_plugin.py",
    # Bootstrap
    "scripts/ci/bootstrap_python_dev.sh",
    # Verification scripts
    "scripts/verify_promotion_experimental_lab_build_lane.py",
    "scripts/verify_promotion_experimental_lab_build_lane_bootstrap.py",
    "scripts/verify_promotion_experimental_lab_build_lane_schema.py",
    # Contract tests
    "tests/unit/test_promotion_experimental_lab_build_lane_contract.py",
    "tests/unit/test_promotion_experimental_lab_build_lane_clean_env.py",
    # R1/R12 legacy tests (still exist)
    "tests/unit/test_promotion_static_scope_authority_r12.py",
    "tests/unit/test_promotion_static_gate_runner_r12.py",
    "tests/unit/test_promotion_runtime_gate_collect_execute_split_r12.py",
    "tests/unit/test_promotion_runtime_gate_structured_outcomes_r12.py",
    "tests/unit/test_promotion_runtime_gate_manifest_identity_r12.py",
    "tests/unit/test_promotion_runtime_gate_transcript_writer_r12.py",
    "tests/unit/test_promotion_runtime_gate_static_scope_integration_r12.py",
    # CORRECTION06/07 new tests
    "tests/unit/test_runtime_gate_plugin_and_runner.py",
    "tests/unit/test_promotion_static_scope_negative_proofs.py",
})


# ---------------------------------------------------------------------------
# Errors and dataclasses.
# ---------------------------------------------------------------------------


class ScopeError(RuntimeError):
    """Raised when the inventory is invalid or classification fails."""


@dataclasses.dataclass(frozen=True)
class ScopeRecord:
    """Complete scope record for the dual-range model."""

    # Identifiers
    runtime_base_sha: str
    lane_base_sha: str
    subject_sha: str
    subject_tree: str
    repo_root: str

    # Path buckets
    runtime_paths: tuple[str, ...]
    lane_paths: tuple[str, ...]
    historical_nonruntime_paths: tuple[str, ...]

    # Counts
    runtime_count: int
    lane_count: int
    historical_nonruntime_count: int
    unclassified_count: int  # MUST be 0 (hard fail if > 0)

    # Union of runtime + lane (all paths checked by static gate)
    included_paths: tuple[str, ...]

    # Integrity
    inventory_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime_base_sha": self.runtime_base_sha,
            "lane_base_sha": self.lane_base_sha,
            "subject_sha": self.subject_sha,
            "subject_tree": self.subject_tree,
            "repo_root": self.repo_root,
            "runtime_paths": list(self.runtime_paths),
            "lane_paths": list(self.lane_paths),
            "historical_nonruntime_paths": list(self.historical_nonruntime_paths),
            "runtime_count": self.runtime_count,
            "lane_count": self.lane_count,
            "historical_nonruntime_count": self.historical_nonruntime_count,
            "unclassified_count": self.unclassified_count,
            "included_paths": list(self.included_paths),
            "inventory_sha256": self.inventory_sha256,
        }


# ---------------------------------------------------------------------------
# Git helpers (NUL-safe).
# ---------------------------------------------------------------------------


def _resolve_revision(repo_root: Path, revision: str) -> str:
    """Resolve a short or full SHA to its full 40-char SHA. Fail closed."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ScopeError(f"failed to resolve revision {revision!r}: {proc.stderr}")
    return proc.stdout.strip()


def _git_changed_python(
    repo_root: Path, base_sha: str, subject_sha: str
) -> bytes:
    """Return raw NUL-delimited changed-python bytes from ``git diff -z``.

    Newlines inside filenames are preserved as part of the same record
    because we never call ``tr '\\0' '\\n'`` or any newline-based splitter.
    """
    cmd = [
        "git",
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACMRT",
        f"{base_sha}..{subject_sha}",
        "--",
        "*.py",
    ]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise ScopeError(f"git diff failed: {stderr}")
    return proc.stdout


def _git_ls_tree_python(repo_root: Path, treeish: str) -> bytes:
    """Return raw NUL-delimited Python file list from ``git ls-tree -r``."""
    cmd = [
        "git",
        "ls-tree",
        "--name-only",
        "-z",
        "--recurse-submodules",
        treeish,
        "--",
        "*.py",
    ]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise ScopeError(f"git ls-tree failed: {stderr}")
    return proc.stdout


def _git_rev_parse_head(repo_root: Path) -> str:
    """Return the current checked-out SHA (HEAD)."""
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ScopeError(f"git rev-parse HEAD failed: {proc.stderr}")
    return proc.stdout.strip()


def _git_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    """Return True if ancestor is an ancestor of descendant."""
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def _split_nul_records(raw: bytes) -> list[bytes]:
    """Split raw NUL-delimited bytes into records, preserving newlines."""
    if raw.endswith(b"\x00"):
        raw = raw[:-1]
    if b"" == raw:
        return []
    return raw.split(b"\x00")


# ---------------------------------------------------------------------------
# Validation of a single path record.
# ---------------------------------------------------------------------------


_ABS_RE = re.compile(r"^/|^[A-Za-z]:[\\/]")
_TRAVERSAL_SEG = re.compile(r"(^|/)\.\.($|/)")


def _validate_path_record(record: bytes) -> str:
    """Decode one NUL record into a clean repository-relative POSIX path.

    Reject embedded NUL corruption, absolute paths, traversal, backslashes.
    """
    if b"\x00" in record:
        raise ScopeError(f"embedded NUL in changed-path record: {record!r}")
    text = record.decode("utf-8")
    if "\\" in text:
        raise ScopeError(f"backslash in changed-path record: {text!r}")
    if _ABS_RE.match(text):
        raise ScopeError(f"absolute changed-path record: {text!r}")
    if _TRAVERSAL_SEG.search(text):
        raise ScopeError(f"traversal in changed-path record: {text!r}")
    if text.startswith("/"):
        raise ScopeError(f"leading slash in changed-path record: {text!r}")
    return text


# ---------------------------------------------------------------------------
# Classification helpers.
# ---------------------------------------------------------------------------


def _is_runtime_path(path: str) -> bool:
    """Return True if path is under the runtime source prefix."""
    for prefix in RUNTIME_SOURCE_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _is_lane_authority_path(path: str) -> bool:
    """Return True if path is in the experimental lane authority set."""
    return path in EXPERIMENTAL_LANE_AUTHORITY_PATHS


def _classify(path: str) -> str:
    """Return one of A/B/D category codes for a single path.

    A = runtime path
    B = lane authority path
    D = unclassified (hard fail)
    """
    if _is_runtime_path(path):
        return "A"
    if _is_lane_authority_path(path):
        return "B"
    return "D"


# ---------------------------------------------------------------------------
# ScopeRecord SHA-256 computation.
# ---------------------------------------------------------------------------


def _compute_inventory_sha256(record: ScopeRecord) -> str:
    """Compute SHA-256 over canonical JSON of all authoritative fields.

    Excludes the checksum field itself.
    """
    # Build authoritative payload (same fields as to_dict, minus checksum).
    payload = {
        "runtime_base_sha": record.runtime_base_sha,
        "lane_base_sha": record.lane_base_sha,
        "subject_sha": record.subject_sha,
        "subject_tree": record.subject_tree,
        "repo_root": record.repo_root,
        "runtime_paths": list(record.runtime_paths),
        "lane_paths": list(record.lane_paths),
        "historical_nonruntime_paths": list(record.historical_nonruntime_paths),
        "runtime_count": record.runtime_count,
        "lane_count": record.lane_count,
        "historical_nonruntime_count": record.historical_nonruntime_count,
        "unclassified_count": record.unclassified_count,
        "included_paths": list(record.included_paths),
    }
    # NUL-delimited canonical JSON for path ordering stability.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------


def build_scope(
    repo_root: Path,
    runtime_base_sha: str,
    lane_base_sha: str,
    subject_sha: str,
) -> ScopeRecord:
    """Build a structured ScopeRecord using the dual-range model.

    P0-1 topology checks:
    - runtime_base is ancestor of subject
    - lane_base is ancestor of subject
    - checked-out HEAD == subject_sha
    """
    runtime_full = _resolve_revision(repo_root, runtime_base_sha)
    lane_full = _resolve_revision(repo_root, lane_base_sha)
    subject_full = _resolve_revision(repo_root, subject_sha)
    head_full = _git_rev_parse_head(repo_root)

    # P0-1: topology checks
    if not _git_is_ancestor(repo_root, runtime_full, subject_full):
        raise ScopeError(
            f"P0-1 failed: RUNTIME_BASE {runtime_full} is NOT an ancestor of SUBJECT {subject_full}"
        )

    if not _git_is_ancestor(repo_root, lane_full, subject_full):
        raise ScopeError(
            f"P0-1 failed: LANE_BASE {lane_full} is NOT an ancestor of SUBJECT {subject_full}"
        )

    if head_full != subject_full:
        raise ScopeError(
            f"P0-1 failed: checked-out HEAD ({head_full}) != SUBJECT ({subject_full}); "
            f"must checkout SUBJECT before running static scope"
        )

    # -------------------------------------------------------------------------
    # Compute three ranges.
    # -------------------------------------------------------------------------

    # 1. runtime_changed: all Python files changed since RUNTIME_BASE.
    runtime_raw = _git_changed_python(repo_root, runtime_full, subject_full)
    runtime_records = _split_nul_records(runtime_raw)

    # 2. lane_changed: all Python files changed since LANE_BASE.
    lane_raw = _git_changed_python(repo_root, lane_full, subject_full)
    lane_records = _split_nul_records(lane_raw)

    # 3. historical_python: all Python files in RUNTIME_BASE tree.
    historical_raw = _git_ls_tree_python(repo_root, runtime_full)
    historical_records = _split_nul_records(historical_raw)

    # -------------------------------------------------------------------------
    # Parse and validate all paths.
    # -------------------------------------------------------------------------

    runtime_paths: list[str] = []
    lane_paths: list[str] = []
    historical_paths: list[str] = []

    for record in runtime_records:
        path = _validate_path_record(record)
        if not path:
            continue
        if path in runtime_paths:
            raise ScopeError(f"duplicate runtime_changed path: {path!r}")
        runtime_paths.append(path)

    for record in lane_records:
        path = _validate_path_record(record)
        if not path:
            continue
        if path in lane_paths:
            raise ScopeError(f"duplicate lane_changed path: {path!r}")
        lane_paths.append(path)

    for record in historical_records:
        path = _validate_path_record(record)
        if not path:
            continue
        historical_paths.append(path)

    # -------------------------------------------------------------------------
    # Compute historical_nonruntime_paths.
    # -------------------------------------------------------------------------
    # All Python in RUNTIME_BASE tree minus runtime_changed minus lane_changed.
    runtime_set = frozenset(runtime_paths)
    lane_set = frozenset(lane_paths)

    # Fail-closed: runtime and lane must not overlap.
    overlap = runtime_set & lane_set
    if overlap:
        raise ScopeError(
            "fail-closed: paths appear in both runtime_changed and lane_changed: "
            + ", ".join(sorted(overlap))
        )

    # Historical non-runtime: in historical tree but NOT in runtime_changed
    # and NOT in lane_changed.
    historical_set = frozenset(historical_paths)
    changed_set = runtime_set | lane_set
    historical_nonruntime = sorted(historical_set - changed_set)

    # -------------------------------------------------------------------------
    # Classification of changed paths (A=runtime, B=lane, D=unclassified).
    # -------------------------------------------------------------------------

    seen: set[str] = set()
    unclassified: list[str] = []

    for path in runtime_paths:
        if path in seen:
            raise ScopeError(f"duplicate path in runtime_changed: {path!r}")
        seen.add(path)

    for path in lane_paths:
        if path in seen:
            raise ScopeError(f"duplicate path in lane_changed: {path!r}")
        seen.add(path)

    for path in runtime_paths:
        category = _classify(path)
        if category == "D":
            unclassified.append(path)

    for path in lane_paths:
        category = _classify(path)
        if category == "D":
            unclassified.append(path)

    # Hard-fail on UNCLASSIFIED.
    if unclassified:
        raise ScopeError(
            "unclassified changed Python paths (hard fail): "
            + ", ".join(sorted(unclassified))
        )

    # -------------------------------------------------------------------------
    # Fail-closed: all runtime_paths must exist on disk at SUBJECT.
    # -------------------------------------------------------------------------
    for path in runtime_paths:
        if not (repo_root / path).exists():
            raise ScopeError(
                f"fail-closed: runtime_changed path does not exist on disk at SUBJECT: {path!r}"
            )

    # -------------------------------------------------------------------------
    # Fail-closed: all lane_paths must exist on disk at SUBJECT.
    # -------------------------------------------------------------------------
    for path in lane_paths:
        if not (repo_root / path).exists():
            raise ScopeError(
                f"fail-closed: lane_changed path does not exist on disk at SUBJECT: {path!r}"
            )

    # -------------------------------------------------------------------------
    # Assemble scope record.
    # -------------------------------------------------------------------------

    runtime_sorted = tuple(sorted(runtime_paths))
    lane_sorted = tuple(sorted(lane_paths))
    historical_nonruntime_sorted = tuple(historical_nonruntime)
    included_sorted = runtime_sorted + lane_sorted

    scope_record: ScopeRecord = ScopeRecord(
        runtime_base_sha=runtime_full,
        lane_base_sha=lane_full,
        subject_sha=subject_full,
        subject_tree=".",  # Canonical representation: cwd-relative.
        repo_root=".",
        runtime_paths=runtime_sorted,
        lane_paths=lane_sorted,
        historical_nonruntime_paths=historical_nonruntime_sorted,
        runtime_count=len(runtime_sorted),
        lane_count=len(lane_sorted),
        historical_nonruntime_count=len(historical_nonruntime_sorted),
        unclassified_count=len(unclassified),
        included_paths=included_sorted,
        inventory_sha256="",  # Filled below.
    )

    # Compute checksum over authoritative fields.
    checksum = _compute_inventory_sha256(scope_record)

    # Reconstruct with checksum (frozen dataclass workaround).
    return ScopeRecord(
        runtime_base_sha=scope_record.runtime_base_sha,
        lane_base_sha=scope_record.lane_base_sha,
        subject_sha=scope_record.subject_sha,
        subject_tree=scope_record.subject_tree,
        repo_root=scope_record.repo_root,
        runtime_paths=scope_record.runtime_paths,
        lane_paths=scope_record.lane_paths,
        historical_nonruntime_paths=scope_record.historical_nonruntime_paths,
        runtime_count=scope_record.runtime_count,
        lane_count=scope_record.lane_count,
        historical_nonruntime_count=scope_record.historical_nonruntime_count,
        unclassified_count=scope_record.unclassified_count,
        included_paths=scope_record.included_paths,
        inventory_sha256=checksum,
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="promotion_runtime_static_scope.py",
        description=__doc__,
    )
    parser.add_argument(
        "--runtime-base-sha",
        default=DEFAULT_RUNTIME_BASE_SHA,
        help=(
            "Range base SHA for runtime source evolution "
            f"(default: {DEFAULT_RUNTIME_BASE_SHA})"
        ),
    )
    parser.add_argument(
        "--lane-base-sha",
        default=DEFAULT_LANE_BASE_SHA,
        help=(
            "Range base SHA for lane authority evolution "
            f"(default: {DEFAULT_LANE_BASE_SHA})"
        ),
    )
    parser.add_argument(
        "--subject-sha",
        required=True,
        help="Range head SHA (must resolve via git rev-parse)",
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
        help="Optional path to write the structured JSON record to",
    )
    args = parser.parse_args(argv)

    try:
        record = build_scope(
            args.repo_root,
            args.runtime_base_sha,
            args.lane_base_sha,
            args.subject_sha,
        )
    except ScopeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    payload = record.to_dict()
    serialised = json.dumps(payload, indent=2, sort_keys=True)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised + "\n", encoding="utf-8")

    print(
        "OK: static scope authority (dual-range model)\n"
        f"  runtime_base_sha              = {record.runtime_base_sha}\n"
        f"  lane_base_sha                 = {record.lane_base_sha}\n"
        f"  subject_sha                   = {record.subject_sha}\n"
        f"  runtime_count                 = {record.runtime_count}\n"
        f"  lane_count                    = {record.lane_count}\n"
        f"  historical_nonruntime_count   = {record.historical_nonruntime_count}\n"
        f"  unclassified_count            = {record.unclassified_count}\n"
        f"  included_paths                = {len(record.included_paths)}\n"
        f"  inventory_sha256           = {record.inventory_sha256}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
