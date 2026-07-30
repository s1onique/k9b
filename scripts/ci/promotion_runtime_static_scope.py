"""Runtime static-scope authority for the experimental build lane.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION06

This script is the SINGLE authority that classifies the changed Python
paths between ``BASE_SHA`` and ``SUBJECT_SHA`` into four mutually-exclusive
categories:

  A. RUNTIME_SOURCE
     All Python below the deployed runtime package and any path the
     runtime package imports at production.  These paths are always
     included in the static gate.

  B. EXPERIMENTAL_LANE_AUTHORITY
     The experimental lane's production scripts and the directly
     associated contract tests for that lane.

  C. EXPLICITLY_DEFERRED_INFRASTRUCTURE
     Non-runtime Factory and unfinished canonical qualification
     infrastructure whose typing debt is NOT introduced by this lane
     and whose failure is explicitly out-of-scope for the experimental
     images.

     Every excluded path MUST have a typed reason from
     ``DEFERRED_REASONS``.

  D. UNCLASSIFIED
     Any path not matched by A, B, or an approved explicit deferred
     rule.  ``UNCLASSIFIED > 0`` is a HARD FAILURE.

No path may disappear silently.

Mechanics:

* The changed-path inventory is obtained via::

      git diff --name-only -z --diff-filter=ACMRT
          BASE_SHA..SUBJECT_SHA -- '*.py'

  consumed raw NUL-delimited from the subprocess (no tr / mapfile with
  newline conversion, so filenames containing newlines survive).
* Repository-relative POSIX paths only.
* Reject: absolute paths, ``..``, backslashes, embedded NUL corruption,
  duplicates, paths outside the repository.

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
# Scope policy (CORRECTION06 contract).
# ---------------------------------------------------------------------------

# Category A: runtime source.  All Python below the deployed runtime package.
RUNTIME_SOURCE_PREFIXES: tuple[str, ...] = (
    "src/k8s_diag_agent/",
)

# Category B: experimental-lane authority.  Production scripts that own
# the experimental build lane and the directly associated contract tests.
EXPERIMENTAL_LANE_AUTHORITY_PATHS: frozenset[str] = frozenset(
    {
        "scripts/ci/run_promotion_runtime_gate.py",
        "scripts/ci/promotion_runtime_static_scope.py",
        "scripts/ci/promotion_runtime_static_gate_runner.py",
        "scripts/ci/pytest_runtime_gate_plugin.py",
        "scripts/ci/bootstrap_python_dev.sh",
        "scripts/verify_promotion_experimental_lab_build_lane.py",
        "scripts/verify_promotion_experimental_lab_build_lane_bootstrap.py",
        "scripts/verify_promotion_experimental_lab_build_lane_schema.py",
        "tests/unit/test_promotion_experimental_lab_build_lane_contract.py",
        "tests/unit/test_promotion_experimental_lab_build_lane_clean_env.py",
        "tests/unit/test_promotion_static_scope_authority_r12.py",
        "tests/unit/test_promotion_static_gate_runner_r12.py",
        "tests/unit/test_promotion_runtime_gate_collect_execute_split_r12.py",
        "tests/unit/test_promotion_runtime_gate_structured_outcomes_r12.py",
        "tests/unit/test_promotion_runtime_gate_manifest_identity_r12.py",
        "tests/unit/test_promotion_runtime_gate_transcript_writer_r12.py",
        "tests/unit/test_promotion_runtime_gate_static_scope_integration_r12.py",
        "tests/unit/test_runtime_gate_plugin_and_runner.py",
    }
)

# Category C: explicitly deferred infrastructure with typed reasons.
# Each path maps to the canonical reason so deferred_paths_with_reasons
# is fully populated.
DEFERRED_PATHS: dict[str, str] = {
    "scripts/factory/gate_summary_ruff_target_verifier.py":
        "factory_evidence_debt",
    "scripts/qualification_timing/collect_timing.py":
        "qualification_timing_debt",
    "scripts/qualification_timing/pytest_plugin.py":
        "qualification_timing_debt",
    "tests/verifiers/test_act_k9b_hulk_promotion_automated_closure_live_qualification_and_ci_timing01_wave_correction01_workflow_structure.py":
        "canonical_workflow_test_debt",
    "tests/unit/test_qualification_record_negative_proofs.py":
        "qualification_timing_debt",
}

DEFERRED_REASONS: frozenset[str] = frozenset(
    {
        "factory_evidence_debt",
        "qualification_timing_debt",
        "canonical_workflow_test_debt",
    }
)


# ---------------------------------------------------------------------------
# Errors and dataclasses.
# ---------------------------------------------------------------------------


class ScopeError(RuntimeError):
    """Raised when the inventory is invalid or classification fails."""


@dataclasses.dataclass(frozen=True)
class ScopeRecord:
    base_sha: str
    subject_sha: str
    repo_root: str
    changed_python_count: int
    runtime_source_count: int
    lane_authority_count: int
    deferred_count: int
    unclassified_count: int
    included_paths: tuple[str, ...]
    deferred_paths_with_reasons: tuple[tuple[str, str], ...]
    inventory_sha256: str
    raw_inventory_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "base_sha": self.base_sha,
            "subject_sha": self.subject_sha,
            "repo_root": self.repo_root,
            "changed_python_count": self.changed_python_count,
            "runtime_source_count": self.runtime_source_count,
            "lane_authority_count": self.lane_authority_count,
            "deferred_count": self.deferred_count,
            "unclassified_count": self.unclassified_count,
            "included_paths": list(self.included_paths),
            "deferred_paths_with_reasons": [
                {"path": p, "reason": r}
                for p, r in self.deferred_paths_with_reasons
            ],
            "inventory_sha256": self.inventory_sha256,
            "raw_inventory_sha256": self.raw_inventory_sha256,
        }


# ---------------------------------------------------------------------------
# Inventory acquisition (true NUL-safe).
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


def _split_nul_records(raw: bytes) -> list[bytes]:
    """Split raw NUL-delimited bytes into records, preserving newlines."""
    # Git's ``-z`` uses NUL (0x00) as the terminator between records and
    # appends a trailing NUL.  Strip the trailing terminator only when the
    # buffer actually ends with one.
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

    Reject embedded NUL corruption, absolute paths, traversal, backslashes
    and paths outside the repository.
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
# Classification.
# ---------------------------------------------------------------------------


def _classify(path: str) -> str:
    """Return one of A/B/C/D category codes for a single path.

    Precedence: RUNTIME_SOURCE > EXPERIMENTAL_LANE_AUTHORITY >
    EXPLICITLY_DEFERRED_INFRASTRUCTURE > UNCLASSIFIED.  A path that is
    runtime source MUST NOT be deferred or unclassified.
    """
    for prefix in RUNTIME_SOURCE_PREFIXES:
        if path.startswith(prefix):
            return "A"
    if path in EXPERIMENTAL_LANE_AUTHORITY_PATHS:
        return "B"
    if path in DEFERRED_PATHS:
        reason = DEFERRED_PATHS[path]
        if reason not in DEFERRED_REASONS:
            raise ScopeError(
                f"deferred path {path!r} has unrecognised reason {reason!r}; "
                f"must be one of {sorted(DEFERRED_REASONS)}"
            )
        return "C"
    return "D"


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------


def build_scope(
    repo_root: Path, base_sha: str, subject_sha: str
) -> ScopeRecord:
    """Build a structured ScopeRecord for the given revision range."""
    base_full = _resolve_revision(repo_root, base_sha)
    subject_full = _resolve_revision(repo_root, subject_sha)
    raw_bytes = _git_changed_python(repo_root, base_full, subject_full)
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    records = _split_nul_records(raw_bytes)

    seen: set[str] = set()
    included: list[str] = []
    deferred: list[tuple[str, str]] = []
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}

    for record in records:
        path = _validate_path_record(record)
        if path in seen:
            raise ScopeError(f"duplicate changed-path record: {path!r}")
        seen.add(path)
        if not (repo_root / path).exists():
            # P0-5: --diff-filter=ACMRT does NOT include deletions, so a
            # missing post-image path is a hard error, not silently skipped.
            raise ScopeError(
                f"changed path does not exist on disk: {path!r} "
                "(use git diff --diff-filter=ACMRT to check); "
                "deleted paths must not be in the diff range"
            )
        category = _classify(path)
        counts[category] += 1
        if category == "A" or category == "B":
            included.append(path)
        elif category == "C":
            deferred.append((path, DEFERRED_PATHS[path]))
        else:
            # D: UNCLASSIFIED - hard fail below.
            pass

    # Hard-fail on UNCLASSIFIED.
    if counts["D"] > 0:
        # Re-run classification to produce the unclassified list for the
        # error message.
        unclassified = [
            path
            for record in records
            for path in [_validate_path_record(record)]
            if _classify(path) == "D"
        ]
        raise ScopeError(
            "unclassified changed Python paths (rejected): "
            + ", ".join(sorted(unclassified))
        )

    included_sorted = sorted(included)
    deferred_sorted = sorted(deferred)

    # P0-5: NUL-delimited canonical hashing.  Each path is encoded as
    # UTF-8 and terminated with NUL so path lists that differ only by
    # having embedded newlines produce different hashes.
    inventory_bytes = b"\x00".join(
        p.encode("utf-8") for p in included_sorted
    ) + b"\x00"
    inventory_sha = hashlib.sha256(inventory_bytes).hexdigest()

    # P0-5: scope evidence must not contain absolute host paths.
    # Store "." (cwd-relative) as the canonical representation.
    return ScopeRecord(
        base_sha=base_full,
        subject_sha=subject_full,
        repo_root=".",
        changed_python_count=len(records),
        runtime_source_count=counts["A"],
        lane_authority_count=counts["B"],
        deferred_count=counts["C"],
        unclassified_count=counts["D"],
        included_paths=tuple(included_sorted),
        deferred_paths_with_reasons=tuple(deferred_sorted),
        inventory_sha256=inventory_sha,
        raw_inventory_sha256=raw_sha,
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="promotion_runtime_static_scope.py",
        description=__doc__,
    )
    parser.add_argument(
        "--base-sha",
        required=True,
        help="Range base SHA (must resolve via git rev-parse)",
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
        record = build_scope(args.repo_root, args.base_sha, args.subject_sha)
    except ScopeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    payload = record.to_dict()
    serialised = json.dumps(payload, indent=2, sort_keys=True)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised + "\n", encoding="utf-8")

    print(
        "OK: static scope authority\n"
        f"  base_sha                = {record.base_sha}\n"
        f"  subject_sha             = {record.subject_sha}\n"
        f"  changed_python_count    = {record.changed_python_count}\n"
        f"  runtime_source_count    = {record.runtime_source_count}\n"
        f"  lane_authority_count    = {record.lane_authority_count}\n"
        f"  deferred_count          = {record.deferred_count}\n"
        f"  unclassified_count      = {record.unclassified_count}\n"
        f"  inventory_sha256        = {record.inventory_sha256}\n"
        f"  raw_inventory_sha256    = {record.raw_inventory_sha256}\n"
        f"  included_paths          = {len(record.included_paths)}\n"
        f"  deferred_paths_with_reasons = {len(record.deferred_paths_with_reasons)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())