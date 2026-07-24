"""Auxiliary two-tree R2 evidence collector (CORRECTION05).

Runs the negative-proofs command in BOTH:

1. a detached, clean worktree at the exact HEAD, and
2. the current audit tree,

and writes the persisted ``gate_classification.json`` with
populated ``clean_worktree`` and ``audit_tree`` records.

This is the auxiliary clean-worktree experiment, NOT the
canonical repository gate.  The canonical gate is the
per-check output of
:mod:`scripts.factory.populate_gate_summary`, which is
authoritative and recorded in ``.factory/gate-summary.json``.

Both the clean and audit trees invoke ``sys.executable`` so
the same Python interpreter runs the negative-proofs script in
both trees.  When the detached worktree cannot provision an
equivalent interpreter (for example, a CI runner with a
read-only ``.venv``) the collector persists an explicit
``UNASSESSED`` record instead of running the comparison.

Usage::

    .venv/bin/python scripts/verifiers_audit/collect_r2_evidence.py \
        --output docs/reports/verifier-core-migration-audit01/gate_classification.json \
        --timeout 1800
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment"
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from scripts.verifiers_audit.discovery import REPO_ROOT
from scripts.verifiers_audit.gate_classification import (
    NEGATIVE_PROOFS_SCRIPT,
    _unassessed_record,
    head_commit,
)

_ABS_PATH_TOKEN = re.compile(
    r"(/(?:tmp|Users|home|var|private|Volumes|opt)/[^\s\"']*)"
)


def _redact(text: str) -> str:
    if not text:
        return text
    return _ABS_PATH_TOKEN.sub("<REDACTED-PATH>", text)


def _run(cmd: list[str], cwd: Path, timeout: int) -> dict:
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
        return {
            "result": "EXITED",
            "exit_code": proc.returncode,
            "elapsed_seconds": round(elapsed, 3),
            "stdout_tail": _redact(proc.stdout[-1000:]),
            "stderr_tail": _redact(proc.stderr[-1000:]),
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start

        def _decode(value: object) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")[-1000:]
            return str(value)[-1000:]

        return {
            "result": "TIMED_OUT",
            "exit_code": -1,
            "elapsed_seconds": round(elapsed, 3),
            "stdout_tail": _decode(exc.stdout),
            "stderr_tail": _decode(exc.stderr),
        }


def _make_clean_worktree(head: str) -> Path:
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


def collect_and_persist(output: Path, timeout: int) -> dict:
    """Run the auxiliary two-tree experiment and persist the
    evidence.

    Implementation note: both the clean and audit trees share
    the same interpreter (``sys.executable``).  The negative-
    proofs script does not require a repository-local virtual
    environment; if it ever did, the canonical repository gate
    (not this experiment) is the authoritative result.
    """
    head = head_commit()
    executable = sys.executable
    worktree = _make_clean_worktree(head)
    try:
        clean = _run(
            [executable, NEGATIVE_PROOFS_SCRIPT],
            cwd=worktree,
            timeout=timeout,
        )
        audit_run = _run(
            [executable, NEGATIVE_PROOFS_SCRIPT],
            cwd=REPO_ROOT,
            timeout=timeout,
        )
    finally:
        _cleanup_worktree(worktree)

    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    clean_obj = _Run(
        result=clean["result"],
        exit_code=clean["exit_code"],
        elapsed_seconds=clean["elapsed_seconds"],
        stdout_tail=clean["stdout_tail"],
        stderr_tail=clean["stderr_tail"],
    )
    audit_obj = _Run(
        result=audit_run["result"],
        exit_code=audit_run["exit_code"],
        elapsed_seconds=audit_run["elapsed_seconds"],
        stdout_tail=audit_run["stdout_tail"],
        stderr_tail=audit_run["stderr_tail"],
    )
    classification = classify_pair(clean_obj, audit_obj)
    from scripts.verifiers_audit.builder import (
        analysis_base_commit,
        identity_binding,
    )
    base = analysis_base_commit()
    record = {
        "schema_version": "1.0",
        "totals": {
            "classification": classification,
            "timeout_seconds": timeout,
            "clean_elapsed_seconds": clean["elapsed_seconds"],
            "audit_elapsed_seconds": audit_run["elapsed_seconds"],
        },
        "analysis_base_commit": base,
        "identity_binding": identity_binding(),
        "classification": classification,
        "timeout_seconds": timeout,
        "command": NEGATIVE_PROOFS_SCRIPT,
        "python_executable": executable,
        "clean_worktree": clean,
        "audit_tree": audit_run,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return record


def collect_unassessed(output: Path, reason: str) -> dict:
    """Persist an explicit ``UNASSESSED`` auxiliary record.

    Use this when the detached worktree cannot provision an
    equivalent interpreter environment - the canonical
    repository gate (not this experiment) is the authoritative
    result.
    """
    record = _unassessed_record(reason)
    record["command"] = NEGATIVE_PROOFS_SCRIPT
    # Redact the absolute path so the persisted record never
    # contains a developer-machine path.  The validator
    # ``validate_no_absolute_paths`` rejects ``/tmp/``,
    # ``/Users/``, ``/home/``, ``/var/``, and ``/private/``.
    record["python_executable"] = _redact(sys.executable)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01" / "gate_classification.json",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Per-side timeout in seconds (default 1800).",
    )
    parser.add_argument(
        "--unassessed-reason",
        type=str,
        default="",
        help="If set, persist an UNASSESSED record with this reason "
        "instead of running the experiment.",
    )
    args = parser.parse_args(argv)
    if args.unassessed_reason:
        record = collect_unassessed(args.output, args.unassessed_reason)
    else:
        record = collect_and_persist(args.output, args.timeout)
    print(
        f"classification: {record['classification']}\n"
        f"command: {record['command']}\n"
        f"analysis_base_commit: {record['analysis_base_commit']}\n"
        f"identity_binding: {record['identity_binding']}\n"
        f"clean_elapsed_seconds: {record['totals'].get('clean_elapsed_seconds', 'n/a')}\n"
        f"audit_elapsed_seconds: {record['totals'].get('audit_elapsed_seconds', 'n/a')}\n"
        f"written: {args.output}",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())