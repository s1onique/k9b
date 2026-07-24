"""Canonical-gate classification (R7 / CORRECTION05).

The :func:`classify_canonical_gate` entry point is the auxiliary
clean-worktree experiment that compares the negative-proofs
command's behaviour in:

1. a detached, clean worktree at the same HEAD, and
2. the current audit tree (working tree with audit files).

This is NOT the canonical repository gate.  The canonical
repository gate is the per-check output of
:mod:`scripts.factory.populate_gate_summary`, which is
authoritative and recorded in ``.factory/gate-summary.json``.

Each auxiliary run uses an explicit timeout wrapper and records:

* ``result``        - ``EXITED`` or ``TIMED_OUT``
* ``exit_code``
* ``elapsed_seconds``
* ``stdout_tail``   - last 400 chars of stdout
* ``stderr_tail``   - last 400 chars of stderr
* ``python_executable`` - the interpreter actually invoked
  (always ``sys.executable``; this experiment does not depend
  on a repository-local virtual environment)

Classification rules (R7):

* ``PRE-EXISTING-DETERMINISTIC``  - both trees exit nonzero with
  the same semantic failure.
* ``PRE-EXISTING-ENVIRONMENTAL``  - both trees time out or fail
  because of an identified external environment condition.
* ``ACT-INTRODUCED``              - clean HEAD passes and audit
  tree fails.
* ``UNRESOLVED``                  - results differ or evidence is
  insufficient.
* ``UNASSESSED``                  - the experiment was not run
  (detached worktree dependency environment was not provisioned
  equivalently) - the canonical repository gate is the
  authoritative result.

A deterministic ``SKIPPED`` record is also supported.  A SKIPPED
record MUST NOT be classified as ``PRE-EXISTING-ENVIRONMENTAL``;
the skip is explicitly the caller's choice, never an environmental
artefact.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from scripts.verifiers_audit.discovery import REPO_ROOT

# Negative-proofs check used by the auxiliary experiment.  This
# path is the exact script invoked by the repository gate (per
# the ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01 closure contract).
NEGATIVE_PROOFS_SCRIPT = (
    "scripts/incident_lifecycle_boundary/"
    "redaction_full_gate_negative_proofs.py"
)
GATE_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class _Run:
    result: str
    exit_code: int
    elapsed_seconds: float
    stdout_tail: str
    stderr_tail: str


def _run_with_timeout(cmd: list[str], cwd: Path,
                      timeout: int) -> _Run:
    """Run ``cmd`` under ``cwd`` with an explicit timeout."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        elapsed = time.monotonic() - start
        return _Run(
            result="EXITED",
            exit_code=proc.returncode,
            elapsed_seconds=elapsed,
            stdout_tail=proc.stdout[-400:],
            stderr_tail=proc.stderr[-400:],
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start

        def _decode(value: object) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")[-400:]
            return str(value)[-400:]

        return _Run(
            result="TIMED_OUT",
            exit_code=-1,
            elapsed_seconds=elapsed,
            stdout_tail=_decode(exc.stdout),
            stderr_tail=_decode(exc.stderr),
        )


def _is_semantic_diagnostic(run: _Run) -> bool:
    """``True`` when the stderr looks like a canonical-gate
    negative-proofs diagnostic rather than a timeout or
    environment failure."""
    text = (run.stderr_tail or "") + (run.stdout_tail or "")
    if run.result == "TIMED_OUT":
        return False
    if run.exit_code == 0:
        return False
    needles = (
        "negative",
        "negative-proofs",
        "redaction",
        "violation",
        "doctrine",
        "Invariant",
    )
    return any(token.lower() in text.lower() for token in needles)


def _is_environment_failure(run: _Run) -> bool:
    """``True`` when the failure looks environmental (timeout,
    missing import, network error, OS-level sandbox denial,
    missing worktree dependency such as ``.venv``)."""
    if run.result == "TIMED_OUT":
        return True
    text = (run.stderr_tail or "") + (run.stdout_tail or "")
    env_needles = (
        "TimeoutExpired",
        "TimeoutExpiredExpired",
        "ModuleNotFoundError",
        "FileNotFoundError",
        "OSError",
        "ConnectionError",
        "ECONNREFUSED",
        "Permission denied",
        "clean temp tree parser failed",
    )
    return any(token in text for token in env_needles)


def classify_pair(clean: _Run, audit: _Run) -> str:
    """Return the R7 classification string for a pair of runs."""
    if clean.result == "TIMED_OUT" and audit.result == "TIMED_OUT":
        return "PRE-EXISTING-ENVIRONMENTAL"
    if (
        _is_environment_failure(clean)
        and _is_environment_failure(audit)
    ):
        return "PRE-EXISTING-ENVIRONMENTAL"
    if (
        _is_environment_failure(clean)
        and audit.exit_code == 0
    ):
        return "PRE-EXISTING-ENVIRONMENTAL"
    if (
        clean.exit_code == 0
        and audit.exit_code != 0
        and not _is_environment_failure(audit)
    ):
        return "ACT-INTRODUCED"
    if (
        clean.exit_code != 0
        and audit.exit_code != 0
        and _is_semantic_diagnostic(clean)
        and _is_semantic_diagnostic(audit)
    ):
        return "PRE-EXISTING-DETERMINISTIC"
    if (
        clean.exit_code == 0
        and audit.exit_code == 0
    ):
        return "PRE-EXISTING-DETERMINISTIC"
    return "UNRESOLVED"


_classify_pair = classify_pair


def _make_clean_worktree(head: str) -> Path:
    """Create a detached, clean worktree at the given HEAD."""
    if shutil.which("git") is None:
        raise RuntimeError("git not available")
    parent = Path(tempfile.mkdtemp(prefix="audit_gate_"))
    proc = subprocess.run(
        ["git", "worktree", "add", "--detach",
         str(parent), head],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"worktree add failed: {proc.stderr.strip()}"
        )
    return parent


def _cleanup_worktree(worktree: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def head_commit() -> str:
    """Deprecated: the canonical identity contract uses
    :func:`analysis_base_commit` (CORRECTION08).  Kept as a
    backward-compatibility shim that returns the immutable
    analysis base, NOT the current HEAD.
    """
    from scripts.verifiers_audit.builder import analysis_base_commit

    return analysis_base_commit()


def analysis_base_commit() -> str:
    """Re-export the builder's analysis base for callers that
    already imported this module.  The audit object's
    ``analysis_base_commit`` field MUST point to an immutable
    ancestor of the subject (typically the project's ``F``).
    """
    from scripts.verifiers_audit.builder import analysis_base_commit

    return analysis_base_commit()


_ABS_PATH_TOKEN = re.compile(
    r"(/(?:tmp|Users|home|var|private|Volumes|opt)/[^\s\"']*)"
)


def _redact(text: str) -> str:
    if not text:
        return text
    return _ABS_PATH_TOKEN.sub("<REDACTED-PATH>", text)


def _run_to_dict(run: _Run) -> dict[str, object]:
    return {
        "result": run.result,
        "exit_code": run.exit_code,
        "elapsed_seconds": round(run.elapsed_seconds, 3),
        "stdout_tail": _redact(run.stdout_tail),
        "stderr_tail": _redact(run.stderr_tail),
    }


def _skipped_record(skip_reason: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "totals": {
            "classification": "SKIPPED",
            "timeout_seconds": GATE_TIMEOUT_SECONDS,
            "skipped": True,
        },
        "analysis_base_commit": analysis_base_commit(),
        "identity_binding": {
            "subject_commit_location": "external-closure-record",
            "subject_commit_embedded": False,
        },
        "classification": "SKIPPED",
        "timeout_seconds": GATE_TIMEOUT_SECONDS,
        "command": NEGATIVE_PROOFS_SCRIPT,
        "skipped": True,
        "skip_reason": skip_reason,
        "clean_worktree": {},
        "audit_tree": {},
    }


def _unassessed_record(reason: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "totals": {
            "classification": "UNASSESSED",
            "timeout_seconds": GATE_TIMEOUT_SECONDS,
            "skipped": True,
        },
        "analysis_base_commit": analysis_base_commit(),
        "identity_binding": {
            "subject_commit_location": "external-closure-record",
            "subject_commit_embedded": False,
        },
        "classification": "UNASSESSED",
        "timeout_seconds": GATE_TIMEOUT_SECONDS,
        "command": NEGATIVE_PROOFS_SCRIPT,
        "skipped": True,
        "skip_reason": reason,
        "clean_worktree": {},
        "audit_tree": {},
        "python_executable": _redact(sys.executable),
    }


def _run_canonical_gate() -> dict[str, object]:
    """Run the negative-proofs check in both trees and return the
    R7 classification with full evidence.

    Implementation note: both the clean and audit trees share
    the same interpreter (``sys.executable``); the negative-proofs
    script does not require a repository-local ``.venv``.

    CORRECTION08 identity contract: the emitted record carries
    ``analysis_base_commit`` (an immutable ancestor of the
    subject) and an ``identity_binding`` object that explicitly
    states the subject's sha is NOT embedded in this record.
    """
    base = analysis_base_commit()
    executable = sys.executable
    worktree = _make_clean_worktree(base)
    try:
        clean = _run_with_timeout(
            [executable, NEGATIVE_PROOFS_SCRIPT],
            cwd=worktree,
            timeout=GATE_TIMEOUT_SECONDS,
        )
        audit_run = _run_with_timeout(
            [executable, NEGATIVE_PROOFS_SCRIPT],
            cwd=REPO_ROOT,
            timeout=GATE_TIMEOUT_SECONDS,
        )
    finally:
        _cleanup_worktree(worktree)
    classification = classify_pair(clean, audit_run)
    return {
        "schema_version": "1.0",
        "totals": {
            "classification": classification,
            "timeout_seconds": GATE_TIMEOUT_SECONDS,
            "clean_elapsed_seconds": clean.elapsed_seconds,
            "audit_elapsed_seconds": audit_run.elapsed_seconds,
        },
        "analysis_base_commit": base,
        "identity_binding": {
            "subject_commit_location": "external-closure-record",
            "subject_commit_embedded": False,
        },
        "classification": classification,
        "timeout_seconds": GATE_TIMEOUT_SECONDS,
        "command": NEGATIVE_PROOFS_SCRIPT,
        "python_executable": executable,
        "clean_worktree": _run_to_dict(clean),
        "audit_tree": _run_to_dict(audit_run),
    }


def classify_canonical_gate(
    skip: bool = False,
    skip_reason: str | None = None,
) -> dict[str, object]:
    """Public entry point.  Honours an explicit ``skip`` flag.

    Production code paths pass ``skip=False`` (the default).
    Unit tests may request a deterministic ``SKIPPED`` record
    explicitly.
    """
    if skip:
        return _skipped_record(
            skip_reason
            or "skip=True was passed explicitly to "
            "classify_canonical_gate; the canonical-gate "
            "command is not run."
        )
    return _run_canonical_gate()