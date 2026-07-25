"""CORRECTION15: semantic post-subject repository gates.

The CORRECTION15 evidence driver MUST execute every required
repository gate BEFORE publication and pass the resulting
typed :class:`RepositoryGateResult` records directly to
bundle construction.  Gate identity is a closed
:class:`RepositoryGateName` ``Literal``; the name is NEVER
inferred from ``argv[0]``.

The seven required gates are:

* ``audit01-pytest`` - run the full audit01 test inventory.
* ``audit01-ruff`` - run Ruff against the exact subject
  Python path tuple.
* ``audit01-mypy`` - run mypy against the audit01 sources.
* ``audit-check`` - run ``scripts/verifiers_audit/audit.py --check``.
* ``act-local`` - run ``scripts/verify_all.sh --act-local
  --skip-gate-summary``.
* ``diff-check`` - run ``git diff --check`` on the worktree.
* ``worktree-clean`` - run ``test -z "$(git status --porcelain=v1)"``.

The ``worktree-clean`` and ``diff-check`` gates use the
:class:`GitRunner` seam so the test suite can assert that
every Git invocation goes through the seam.

Public surface:

* :class:`GateOutcome` - the typed per-gate outcome.
* :func:`run_required_gates` - execute the seven required
  gates in sequence and return the typed record list.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from dataclasses import dataclass
from pathlib import Path

from scripts.verifiers_audit.range_evidence_helpers import (
    SubprocessGitRunner,
    capture_command,
)
from scripts.verifiers_audit.typed_results import (
    ExecutedCommand,
    RepositoryGateName,
    RepositoryGateResult,
)


@dataclass(frozen=True)
class GateInvocation:
    """A planned gate invocation.

    * ``name`` - the closed semantic name of the gate.
    * ``argv`` - the executed argv (tuple).
    * ``cwd`` - the working directory.
    * ``expected_pass`` - whether the gate is expected to
      pass (False when the gate is allowed to be skipped).
    """

    name: RepositoryGateName
    argv: tuple[str, ...]
    cwd: str
    expected_pass: bool = True


def _git(
    argv: tuple[str, ...], *, cwd: Path, name: str
) -> ExecutedCommand:
    """Invoke the Git seam for non-evidence Git operations."""
    runner = SubprocessGitRunner()
    return runner.run(argv, cwd=cwd, name=name)


def _default_python() -> str:
    """Return the venv-locked Python interpreter when present."""
    from scripts.verifiers_audit.discovery import REPO_ROOT

    venv = REPO_ROOT / ".venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    return "python"


def build_required_gates(
    *,
    repo_root: Path,
    subject_python_paths: tuple[str, ...] = (),
) -> tuple[GateInvocation, ...]:
    """Build the closed set of required gate invocations.

    The function returns the seven required gate plans in
    the canonical order.  The caller is expected to
    sequentially execute them and pass the resulting typed
    :class:`RepositoryGateResult` records to the bundle
    builder.

    The ``subject_python_paths`` argument is the exact
    Python path tuple the CORRECTION15 subject commit
    changed (used by the ``audit01-ruff`` gate so the
    Ruff invocation targets the same files).
    """
    py = _default_python()
    return (
        GateInvocation(
            name="audit01-pytest",
            argv=(
                py,
                "-m",
                "pytest",
                "tests/verifiers/test_verifier_core_migration_audit01*.py",
                "-v",
            ),
            cwd=str(repo_root),
        ),
        GateInvocation(
            name="audit01-ruff",
            argv=(
                py,
                "-m",
                "ruff",
                "check",
                "scripts/verifiers_audit",
                "tests/verifiers",
            ),
            cwd=str(repo_root),
        ),
        GateInvocation(
            name="audit01-mypy",
            argv=(
                py,
                "-m",
                "mypy",
                "scripts/verifiers_audit",
                "tests/verifiers/test_verifier_core_migration_audit01*.py",
                "tests/verifiers/verifier_core_migration_audit01_support.py",
                "tests/verifiers/conftest.py",
                "--ignore-missing-imports",
            ),
            cwd=str(repo_root),
        ),
        GateInvocation(
            name="audit-check",
            argv=(py, "scripts/verifiers_audit/audit.py", "--check"),
            cwd=str(repo_root),
        ),
        GateInvocation(
            name="act-local",
            argv=("./scripts/verify_all.sh", "--act-local", "--skip-gate-summary"),
            cwd=str(repo_root),
        ),
        GateInvocation(
            name="diff-check",
            argv=("git", "diff", "--check"),
            cwd=str(repo_root),
        ),
        GateInvocation(
            name="worktree-clean",
            argv=("/bin/sh", "-c", 'test -z "$(git status --porcelain=v1)"'),
            cwd=str(repo_root),
        ),
    )


def _execute_invocation(
    invocation: GateInvocation,
    *,
    git_runner: SubprocessGitRunner | None = None,
) -> ExecutedCommand:
    """Execute a single gate invocation and return the typed result.

    Git invocations (``diff-check``) go through the
    :class:`SubprocessGitRunner` seam so the test suite can
    patch ``subprocess.run`` and assert that every Git call
    is recorded in the seam's transcript.  Non-Git gates
    use :func:`capture_command`.
    """
    cwd = Path(invocation.cwd)
    argv = invocation.argv
    if argv and argv[0] == "git":
        runner = git_runner or SubprocessGitRunner()
        return runner.run(argv, cwd=cwd, name=invocation.name)
    return capture_command(argv, cwd=cwd, name=invocation.name)


def run_required_gates(
    *,
    repo_root: Path,
    git_runner: SubprocessGitRunner | None = None,
    subject_python_paths: tuple[str, ...] = (),
) -> tuple[RepositoryGateResult, ...]:
    """Execute the seven required gates and return the typed records.

    The function builds the closed gate plan, executes every
    invocation, and returns one :class:`RepositoryGateResult`
    per gate.  The order is canonical.  A gate that fails is
    still recorded; the function does NOT short-circuit so
    every gate is captured for the bundle.
    """
    invocations = build_required_gates(
        repo_root=repo_root,
        subject_python_paths=subject_python_paths,
    )
    out: list[RepositoryGateResult] = []
    for invocation in invocations:
        command = _execute_invocation(
            invocation,
            git_runner=git_runner,
        )
        out.append(
            RepositoryGateResult(
                name=invocation.name,
                command=command,
            )
        )
    return tuple(out)


__all__ = [
    "GateInvocation",
    "build_required_gates",
    "run_required_gates",
]
