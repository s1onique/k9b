"""CORRECTION13/CORRECTION14/CORRECTION15: detached range evidence helpers.

Low-level helpers for the range-evidence producer:

* :func:`_sha256_of` - single-file SHA-256 computation.
* :func:`_write_nul` - NUL-delimited filesystem bytes writer.
* :func:`_write_text_projection` - non-authoritative
  ``.txt`` projection writer with a labelled header.
* :func:`parse_nul_paths` - NUL-delimited ``git diff --name-only -z``
  stdout parser.
* :class:`GitRunner` - CORRECTION15: single authoritative
  command seam for every Git invocation.  The seam records
  the raw stdout/stderr bytes from the executed argv.  The
  cardinality of the recorded Git commands is derived from
  the recorded transcript, NOT from a wrapper call count.
* :class:`SubprocessGitRunner` - the default in-process
  :class:`GitRunner` implementation.  Uses ``subprocess.run``
  with ``capture_output=True`` and ``check=False`` so the
  raw bytes are returned to the caller.
* :func:`capture_command` - capture an arbitrary post-subject
  gate command as a typed :class:`ExecutedCommand`.

The seam is the SOLE production path for Git execution.  All
production code that needs to invoke Git MUST go through
:class:`GitRunner.run`; the test suite patches
``subprocess.run`` and fails any invocation outside the seam.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Protocol

from scripts.verifiers_audit.typed_results import (
    CommandStatus,
    ExecutedCommand,
)


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


def parse_nul_paths(raw: bytes) -> tuple[bytes, ...]:
    """Parse NUL-delimited ``git diff --name-only -z`` output.

    The function returns the exact path byte tuples in the
    order Git produced them; an empty trailing entry is
    NEVER emitted as a path.  The authoritative range query
    is the raw bytes from the diff command (see
    :meth:`GitRunner.run`); the parser is a pure-Python
    helper that operates on those bytes.
    """
    if not raw:
        return ()
    return tuple(entry for entry in raw.split(b"\0") if entry)


class GitRunner(Protocol):
    """CORRECTION15: single authoritative command seam.

    The producer invokes :meth:`GitRunner.run` exactly ONCE
    per Git execution.  The seam records the executed argv
    verbatim and the raw stdout/stderr bytes.  The
    cardinality of the recorded Git commands is derived
    from the executed transcript, NOT from a wrapper call
    count.

    Implementations MUST:

    * invoke ``subprocess.run`` with the supplied ``argv``;
    * capture stdout/stderr in bytes (no ``text=True``);
    * return a :class:`ExecutedCommand` whose ``status`` is
      ``"passed"`` when the command exited zero,
      ``"failed"`` otherwise (a ``"skipped"`` status is
      reserved for commands the caller chose not to invoke
      and is not produced by the seam);
    * preserve the argv verbatim (``tuple`` not ``list``);
    * preserve the raw stdout/stderr bytes verbatim.

    CORRECTION18: implementations MUST accept and pass
    an optional ``env`` parameter to subprocess.run.

    The default implementation (:class:`SubprocessGitRunner`)
    runs in-process.
    """

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        name: str = "",
        env: dict[str, str] | None = None,
    ) -> ExecutedCommand:
        ...


class SubprocessGitRunner:
    """CORRECTION15: default in-process GitRunner.

    Runs the supplied argv via :func:`subprocess.run` with
    ``capture_output=True``, ``text=False``, ``check=False``.
    The ``status`` field is ``"passed"`` when
    ``returncode == 0`` and ``"failed"`` otherwise.  The
    raw stdout/stderr bytes are returned to the caller; the
    ``stdout_sha256`` / ``stderr_sha256`` properties on the
    :class:`ExecutedCommand` are derived from those bytes.

    CORRECTION18: the runner accepts a COMPLETE environment
    mapping and passes it directly to subprocess.run without
    further merging.  The caller (gate executor) is solely
    responsible for constructing the effective environment
    from parent + overrides.  This avoids double-merging.
    """

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        name: str = "",
        env: dict[str, str] | None = None,
    ) -> ExecutedCommand:
        # CORRECTION18: env is already the complete effective environment.
        # Runner passes it directly to subprocess without merging.
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            check=False,
            env=env,
        )
        status: CommandStatus = "passed" if proc.returncode == 0 else "failed"
        return ExecutedCommand(
            name=name,
            argv=tuple(argv),
            cwd=str(cwd),
            returncode=proc.returncode,
            stdout=bytes(proc.stdout),
            stderr=bytes(proc.stderr),
            status=status,
        )


def _resolve_full_commit(
    rev: str,
    *,
    repo_root: Path,
    stage: str,
    base: str,
    subject: str,
) -> str:
    """Resolve the full 40-char SHA object ID for ``rev``.

    CORRECTION15: the function is a backward-compatibility
    shim around the authoritative
    :class:`SubprocessGitRunner` seam.  The full OID is
    derived from the captured stdout bytes.  On non-zero
    exit the function raises
    :class:`RangeResolutionError` with the supplied
    ``stage``.
    """
    argv: tuple[str, ...] = (
        "git",
        "rev-parse",
        "--verify",
        f"{rev}^{{commit}}",
    )
    runner = SubprocessGitRunner()
    result = runner.run(argv, cwd=repo_root, name=f"git-rev-parse-{stage}")
    if result.status == "failed":
        from scripts.verifiers_audit.scope import RangeResolutionError

        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=argv,
            returncode=result.returncode,
            stderr=os.fsdecode(result.stderr) if result.stderr else "",
            stage=stage,  # type: ignore[arg-type]
        )
    return os.fsdecode(result.stdout).strip()


def capture_command(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    name: str = "",
    env: dict[str, str] | None = None,
) -> ExecutedCommand:
    """CORRECTION15: capture an arbitrary command as a typed result.

    The function wraps :class:`SubprocessGitRunner` so callers
    that need a one-off capture (post-subject gates, Ruff, etc.)
    produce a typed :class:`ExecutedCommand` with raw bytes
    and the derived SHA-256 properties.  The function is the
    canonical capture helper for every non-Git command too; it
    deliberately uses the same interface as the Git seam so
    downstream code can treat all commands uniformly.

    CORRECTION18: when ``env`` is supplied, it is merged with
    os.environ and passed to subprocess.run.
    """
    runner = SubprocessGitRunner()
    return runner.run(argv, cwd=cwd, name=name, env=env)


__all__ = [
    "GitRunner",
    "SubprocessGitRunner",
    "_sha256_of",
    "_write_nul",
    "_write_text_projection",
    "capture_command",
    "parse_nul_paths",
]
