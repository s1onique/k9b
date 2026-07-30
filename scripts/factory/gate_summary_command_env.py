"""Subprocess command environment + CommandSpec for the gate-summary producer.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION11-
RANGE-BOUND-EVIDENCE-TRUTH-AND-LLM-CAP01:

Extracted from :mod:`scripts.factory.populate_gate_summary` so the
producer stays under the LLM-friendly 500-line cap.  This module owns
the **subprocess-command environment** responsibility:

* :class:`CommandSpec` -- the canonical structured command the
  producer hands to a runner;
* :data:`Runner` -- the type alias for the runner callable;
* :func:`source_root` -- resolve the verifier source root for a
  repository-root / worktree seam;
* :func:`git_cwd` -- return the git command CWD (worktree only);
* :func:`build_child_env` -- build the canonical child-process
  environment used by every check in the gate-summary;
* :func:`build_child_env_with_guard` -- the same environment with the
  ``K9B_GATE_POPULATION_CHILD=1`` recursion guard propagated;
* :func:`run_subprocess` -- the canonical subprocess runner that
  turns a :class:`CommandSpec` into a :class:`CheckOutcome`.

The producer imports the runtime helpers from this module instead of
defining them inline.  Each helper is a single, named, canonical
entry point so the duplicate implementation that was previously
spread across the producer is now impossible to introduce.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION11:
# ``CheckOutcome`` is now single-owner.  Re-exported from the canonical
# ``scripts.factory.build_gate_summary`` module so the producer cannot
# silently drift to a duplicate shape.  The dataclass identity MUST
# be ``scripts.factory.build_gate_summary.CheckOutcome``; downstream
# loaders use ``isinstance`` against that exact class.
#
# We use a direct relative import within the ``scripts.factory``
# package so the module is imported under its canonical identity
# without altering ``sys.path``.  ``build_gate_summary`` is a sibling
# module in the same package and is always importable via a normal
# package-relative import.
from scripts.factory.build_gate_summary import CheckOutcome

SCRIPT_REPO = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = SCRIPT_REPO / ".venv" / "bin" / "python"


@dataclass(frozen=True)
class CommandSpec:
    """A named subprocess command in the populated gate."""

    name: str
    argv: list[str]
    expect_zero: bool = True
    cwd: Path | None = None
    env: dict[str, str] | None = None


Runner = Callable[[CommandSpec], CheckOutcome]


def source_root(repo_root: Path) -> Path:
    """Return the verifier source root for a repository-root/worktree seam."""
    if (repo_root / "src" / "k8s_diag_agent").exists():
        return repo_root / "src"
    return repo_root


def git_cwd(repo_root: Path) -> Path:
    """Use repo_root for git commands only when it is a git worktree."""
    return repo_root if (repo_root / ".git").exists() else SCRIPT_REPO


def build_child_env(repo_root: Path) -> dict[str, str]:
    """Build the child-process environment used by populate's checks.

    Note: ``K9B_GATE_POPULATION_CHILD=1`` is NOT propagated here; doing
    so would prevent legitimate ``populate`` invocations launched from
    the full-gate-negative-proofs and other test harnesses.  The
    recursion guard is propagated only to the
    ``targeted-repository-gate`` spec, since that is the only command
    that can actually trigger a populate -> verify -> populate cycle.
    """
    env = os.environ.copy()
    source = source_root(repo_root)
    # Deduplicate PYTHONPATH entries (separated by os.pathsep) so mypy
    # does not see the same module from two roots and emit
    # "Duplicate module" errors.
    existing_paths = env.get("PYTHONPATH", "").split(os.pathsep)
    seen: set[str] = set()
    ordered: list[str] = []
    for p in (
        str(source),
        str(SCRIPT_REPO),
        str(SCRIPT_REPO / "src"),
        *existing_paths,
    ):
        if not p or p in seen:
            continue
        seen.add(p)
        ordered.append(p)
    env["PYTHONPATH"] = os.pathsep.join(ordered)
    # MYPYPATH is intentionally not set: the child mypy invocation
    # uses explicit file paths relative to cwd (the repo root).
    # Setting MYPYPATH to the same root causes "Duplicate module"
    # errors.
    env.pop("MYPYPATH", None)
    env.setdefault("HOME", str(Path.home()))
    return env


def build_child_env_with_guard(repo_root: Path) -> dict[str, str]:
    """Like :func:`build_child_env` but propagates ``K9B_GATE_POPULATION_CHILD=1``.

    Used only for the ``targeted-repository-gate`` command, which
    routes through ``verify_all.sh --act-local`` and is the actual
    cycle path.
    """
    env = build_child_env(repo_root)
    env["K9B_GATE_POPULATION_CHILD"] = "1"
    return env


def run_subprocess(spec: CommandSpec) -> CheckOutcome:
    """Run a child command and derive a CheckOutcome from the subprocess result.

    The canonical subprocess runner.  Returns a :class:`CheckOutcome`
    with ``status="pass"`` when the exit code matches
    ``expect_zero`` (the default is zero) and ``status="fail"``
    otherwise.  Any :class:`OSError` or :class:`subprocess.TimeoutExpired`
    is caught and recorded as ``exit_code=127`` (or ``124`` for a
    timeout) so the producer never crashes on a transient subprocess
    failure.
    """
    started = time.time()
    try:
        proc = subprocess.run(
            spec.argv,
            capture_output=True,
            text=True,
            cwd=str(spec.cwd or SCRIPT_REPO),
            env=spec.env,
            timeout=300,
            check=False,
        )
        exit_code = proc.returncode
        output = (proc.stderr or "") + (proc.stdout or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        exit_code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 127
        output = str(exc)

    duration_ms = int((time.time() - started) * 1000)
    ok = (exit_code == 0) == spec.expect_zero
    return CheckOutcome(
        name=spec.name,
        status="pass" if ok else "fail",
        duration_ms=duration_ms,
        error_message=None if ok else output[:1000],
        command=shlex.join(spec.argv),
        exit_code=exit_code,
    )


__all__ = [
    "CheckOutcome",
    "CommandSpec",
    "Runner",
    "SCRIPT_REPO",
    "VENV_PYTHON",
    "build_child_env",
    "build_child_env_with_guard",
    "git_cwd",
    "run_subprocess",
    "source_root",
]
