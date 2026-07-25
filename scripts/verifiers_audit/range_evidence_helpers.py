"""CORRECTION13: detached range evidence helpers.

Low-level helpers for the range-evidence producer:

* :func:`_sha256_of` — single-file SHA-256 computation.
* :func:`_write_nul` — NUL-delimited filesystem bytes writer.
* :func:`_write_text_projection` — non-authoritative
  ``.txt`` projection writer with a labelled header.
* :func:`_resolve_full_commit` — full git object ID
  resolution via ``git rev-parse``.
* :func:`_run_captured` — subprocess capture wrapper.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path


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
