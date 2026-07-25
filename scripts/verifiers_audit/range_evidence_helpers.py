"""CORRECTION13/CORRECTION14: detached range evidence helpers.

Low-level helpers for the range-evidence producer:

* :func:`_sha256_of` - single-file SHA-256 computation.
* :func:`_write_nul` - NUL-delimited filesystem bytes writer.
* :func:`_write_text_projection` - non-authoritative
  ``.txt`` projection writer with a labelled header.
* :func:`_resolve_full_commit` - full git object ID
  resolution via ``git rev-parse``.
* :func:`_run_captured` - subprocess capture wrapper.
* :class:`GitRunner` - CORRECTION14 injected command seam for
  every Git invocation.  The seam records the actual argv
  executed by the producer; the cardinality of the
  ``git diff`` calls is derived from the recorded transcript,
  NOT from a wrapper call count.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from scripts.verifiers_audit.typed_results import CommandResult


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_nul(path: Path, items: tuple[bytes, ...]) -> None:
    """Write ``items`` to ``path`` as NUL-delimited bytes.

    Empty ``items`` yields an empty file.  Non-empty ``items``
    yields ``b"\\0".join(items) + b"\\0"`` so the file's
    trailing byte is a NUL.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not items:
        path.write_bytes(b"")
        return
    path.write_bytes(b"\0".join(items) + b"\0")


def _write_text_projection(
    path: Path, items: tuple[bytes, ...]
) -> None:
    """Write the non-authoritative ``.txt`` projection.

    The header is exactly ``authority: false`` and
    ``encoding: diagnostic escaped projection``.  Every
    path byte is rendered as a Python repr-style escape so
    embedded NULs, newlines, and non-ASCII bytes are visible
    in the file.  The projection is NEVER the source of
    truth; the authoritative path is the ``.z`` file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "\n".join(
        [
            "authority: false",
            "encoding: diagnostic escaped projection",
            "format: repr-escaped per entry",
            "",
        ]
    )
    body = "\n".join(repr(raw) for raw in items)
    path.write_text(header + body + "\n", encoding="utf-8")


def _resolve_full_commit(
    rev: str,
    *,
    repo_root: Path,
    stage: str,
    base: str,
    subject: str,
) -> str:
    """Return the full 40-char SHA object ID for ``rev``.

    Uses ``git rev-parse --verify "${rev}^{commit}"`` so the
    caller always receives an unambiguous object ID, never
    the abbreviated form.  On non-zero exit the function
    raises :class:`RangeResolutionError` with the supplied
    ``stage`` (``"resolve_base"`` for the BASE revision,
    ``"resolve_subject"`` for the SUBJECT revision).  A bare
    :class:`RuntimeError` at the evidence-transaction boundary
    is forbidden.
    """
    argv: tuple[str, ...] = (
        "git",
        "rev-parse",
        "--verify",
        f"{rev}^{{commit}}",
    )
    proc = subprocess.run(
        list(argv),
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        from scripts.verifiers_audit.scope import RangeResolutionError

        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=argv,
            returncode=proc.returncode,
            stderr=(
                os.fsdecode(proc.stderr) if proc.stderr else ""
            ),
            stage=stage,  # type: ignore[arg-type]
        )
    return proc.stdout.decode("utf-8").strip()


def _run_captured(argv: list[str], repo_root: Path) -> dict[str, object]:
    """Run ``argv`` (CWD ``repo_root``) and capture stdout/stderr/exit."""
    start = time.monotonic()
    proc = subprocess.run(
        argv, cwd=str(repo_root), capture_output=True, check=False
    )
    elapsed = time.monotonic() - start
    return {
        "argv": list(argv),
        "cwd": str(repo_root),
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "stdout": proc.stdout.decode("utf-8", errors="replace"),
        "stderr": proc.stderr.decode("utf-8", errors="replace"),
        "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(),
    }


class GitRunner(Protocol):
    """CORRECTION14: injected command seam for every Git invocation.

    The producer invokes :meth:`GitRunner.run` exactly ONCE
    per Git execution.  The seam records the executed argv
    verbatim so the cardinality of the ``git diff`` calls is
    derived from the recorded transcript, NOT from a wrapper
    call count.

    Implementations MUST:

    * invoke ``subprocess.run`` with the supplied ``argv``;
    * capture stdout/stderr in bytes (no ``text=True``);
    * return a :class:`CommandResult` whose ``status`` is
      ``"passed"`` when the command exited zero AND produced
      the expected outcome, ``"failed"`` otherwise;
    * preserve the argv verbatim (``tuple`` not ``list``).

    The default implementation (:class:`SubprocessGitRunner`)
    runs in-process.
    """

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
    ) -> CommandResult:
        ...


class SubprocessGitRunner:
    """CORRECTION14: default in-process GitRunner.

    Runs the supplied argv via :func:`subprocess.run` with
    ``capture_output=True``, ``text=False``, ``check=False``.
    The ``status`` field is ``"passed"`` when ``returncode ==
    0`` AND stdout is non-empty (the git diff command MUST
    produce bytes; an empty stdout from a git diff is treated
    as a valid equal-commit range, so the status is
    ``"passed"`` regardless of stdout length).  When
    ``returncode != 0`` the status is ``"failed"``.
    """

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
    ) -> CommandResult:
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            check=False,
        )
        stdout_sha256 = hashlib.sha256(proc.stdout).hexdigest()
        stderr_sha256 = hashlib.sha256(proc.stderr).hexdigest()
        status: str
        if proc.returncode != 0:
            status = "failed"
        else:
            status = "passed"
        return CommandResult(
            argv=tuple(argv),
            returncode=proc.returncode,
            stdout_sha256=stdout_sha256,
            stderr_sha256=stderr_sha256,
            status=status,  # type: ignore[arg-type]
        )


def capture_post_subject_gate(
    argv: list[str],
    *,
    cwd: Path,
) -> CommandResult:
    """CORRECTION14: capture a post-subject gate as a typed result.

    The function wraps :class:`SubprocessGitRunner`-style
    capture for arbitrary gate commands (pytest, ruff, mypy,
    audit-check, verify_all.sh --act-local --skip-gate-summary).
    The returned :class:`CommandResult` is the SOLE authority
    for whether the gate ``passed``.  The gate row MUST be
    recorded in ``gate-results.json`` exactly once per gate.
    """
    runner = SubprocessGitRunner()
    return runner.run(tuple(argv), cwd=cwd)


def collect_git_results(
    runners: Iterable[CommandResult],
) -> tuple[CommandResult, ...]:
    """CORRECTION14: derive the executed-transcript view of Git runs.

    The function returns a tuple of the supplied runners
    verbatim so the caller can derive
    ``git_diff_query_count = sum(r.argv[:2] == ('git', 'diff')
    for r in git_results)``.  The cardinality is measured
    from the EXECUTED transcript (the captured argv), NOT
    from any wrapper call count.
    """
    return tuple(runners)