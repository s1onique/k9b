#!/usr/bin/env python3
"""Shared library for schema lab recovery state dump.

Provides reusable components for the recovery state dump script.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    """Captured result for a command we run."""

    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def command_text(self) -> str:
        return " ".join(shlex.quote(arg) for arg in self.args)


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: int | None = None,
) -> CommandResult:
    """Run a command without shell expansion.

    We intentionally avoid shell=True so the script is easier to audit and does
    not inherit shell quoting hazards. Every command is passed as an argv list.
    """

    try:
        completed = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            args=list(args),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            args=list(args),
            returncode=127,
            stdout="",
            stderr=f"command not found: {exc}",
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            args=list(args),
            returncode=124,
            stdout=_timeout_output(exc.stdout),
            stderr=_timeout_output(exc.stderr) + f"\ncommand timed out after {timeout_seconds}s",
        )


def safe_relative(path: Path, root: Path) -> str:
    """Return a readable repo-relative path when possible."""

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def git_output(root: Path, args: Sequence[str]) -> CommandResult:
    """Run a git command from the repo root."""

    return run_command(["git", *args], cwd=root)


def diff_has_added_non_header_lines(diff_text: str) -> list[str]:
    """Return added diff lines excluding diff metadata.

    Any addition to allowlist/ignore files is suspect. This function is strict:
    it ignores only diff headers (`+++`) and hunk metadata, then reports every
    remaining added line.
    """

    added: list[str] = []
    for line in diff_text.splitlines():
        if not line.startswith("+"):
            continue
        if line.startswith("+++"):
            continue
        added.append(line)
    return added


def _timeout_output(value: str | bytes | None) -> str:
    """Convert subprocess timeout output to string safely.

    When subprocess.run is called with text=True, stdout/stderr are str.
    But TimeoutExpired.exception.stdout/stderr may still be bytes if the process
    was killed before completing the text conversion.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
