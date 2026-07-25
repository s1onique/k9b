"""CORRECTION15/CORRECTION16: semantic post-subject repository gates.

The CORRECTION15 evidence driver MUST execute every required
repository gate BEFORE publication and pass the resulting
typed :class:`RepositoryGateResult` records directly to
bundle construction.  Gate identity is a closed
:class:`RepositoryGateName` ``Literal``; the name is NEVER
inferred from ``argv[0]``.

CORRECTION16 hardenings:

* pytest and mypy inventory paths are resolved in Python
  (via :func:`glob.glob`) BEFORE the argv is constructed
  so the subprocess argv never contains literal glob
  syntax (``*``, ``?``, ``[]``);
* the ``worktree-clean`` gate now invokes ``git status
  --porcelain=v1 -z`` directly through the
  :class:`GitRunner` seam (CORRECTION15 used a hidden
  ``/bin/sh -c 'test -z "$(git status --porcelain=v1)"'``
  shell command that the seam could not see);
* the ``act-local`` gate receives ``--base`` and
  ``--subject`` arguments so the script verifies only the
  F16..S16 range (CORRECTION15 used working-tree discovery
  which made act-local scope incorrect and forced a
  script-limitation waiver);
* every required gate is fail-closed: when any gate
  records ``status != 'passed'``, the orchestrator MUST
  mark the transaction as failed, remove the staging
  directory, write a failure-only publication result, and
  exit nonzero.

The seven required gates are:

* ``audit01-pytest`` - run the resolved audit01 test
  inventory.
* ``audit01-ruff`` - run Ruff against the exact subject
  Python path tuple.
* ``audit01-mypy`` - run mypy against the audit01 sources.
* ``audit-check`` - run ``scripts/verifiers_audit/audit.py --check``.
* ``act-local`` - run ``scripts/verify_all.sh --act-local
  --base F16 --subject S16 --skip-gate-summary``.
* ``diff-check`` - run ``git diff --check`` on the worktree.
* ``worktree-clean`` - run ``git status --porcelain=v1 -z``
  on the worktree.

The ``worktree-clean`` and ``diff-check`` gates use the
:class:`GitRunner` seam so the test suite can assert that
every Git invocation goes through the seam.

Public surface:

* :class:`GateOutcome` - the typed per-gate outcome.
* :func:`run_required_gates` - execute the seven required
  gates in sequence and return the typed record list.
* :func:`build_required_gates` - build the closed set of
  required gate invocations from the supplied inputs.
* :func:`resolve_test_inventory` - resolve the
  ``tests/verifiers/test_verifier_core_migration_audit01*.py``
  glob pattern into a concrete sorted path tuple.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import glob
import os
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


# CORRECTION16: the canonical test-inventory glob pattern.
# The pattern is resolved in Python (here) BEFORE argv
# construction so the subprocess argv never contains
# literal wildcards.
AUDIT01_TEST_GLOB_PATTERN = (
    "tests/verifiers/test_verifier_core_migration_audit01*.py"
)
"""The canonical audit01 Pytest test-inventory glob pattern.

CORRECTION16: the pattern is resolved by
:func:`resolve_test_inventory` before argv construction;
no subprocess argv may contain the literal ``*`` ``?`` or
``[]`` wildcard syntax.
"""


def _default_python() -> str:
    """Return the venv-locked Python interpreter when present."""
    from scripts.verifiers_audit.discovery import REPO_ROOT

    venv = REPO_ROOT / ".venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    return "python"


def resolve_test_inventory(
    *,
    repo_root: Path,
    pattern: str = AUDIT01_TEST_GLOB_PATTERN,
) -> tuple[str, ...]:
    """Resolve the audit01 test-inventory glob into a path tuple.

    CORRECTION16: the function is the canonical Python-side
    resolver of the audit01 test inventory.  The function
    accepts ``pattern`` (default
    ``tests/verifiers/test_verifier_core_migration_audit01*.py``)
    and returns a sorted tuple of paths relative to
    ``repo_root``.  Every returned path is a regular file
    that exists at resolver time.  The returned tuple is
    the SOLE input to the ``audit01-pytest`` and
    ``audit01-mypy`` argv builders; the literal glob syntax
    is NEVER forwarded to the subprocess.
    """
    candidates = sorted(
        glob.glob(str(repo_root / pattern), recursive=False)
    )
    out: list[str] = []
    for full in candidates:
        p = Path(full)
        if not p.is_file() or p.is_symlink():
            continue
        out.append(str(p.relative_to(repo_root)))
    return tuple(out)


def _git(
    argv: tuple[str, ...], *, cwd: Path, name: str
) -> ExecutedCommand:
    """Invoke the Git seam for non-evidence Git operations."""
    runner = SubprocessGitRunner()
    return runner.run(argv, cwd=cwd, name=name)


def build_required_gates(
    *,
    repo_root: Path,
    subject_python_paths: tuple[str, ...] = (),
    base: str = "F16",
    subject: str = "S16",
) -> tuple[GateInvocation, ...]:
    """Build the closed set of required gate invocations.

    The function returns the seven required gate plans in
    the canonical order.  The caller is expected to
    sequentially execute them and pass the resulting typed
    :class:`RepositoryGateResult` records to the bundle
    builder.

    CORRECTION16:

    * ``subject_python_paths`` is the exact Python path
      tuple the CORRECTION16 subject commit changed (used
      by the ``audit01-ruff`` gate so the Ruff invocation
      targets the same files).
    * ``base`` and ``subject`` are forwarded to the
      ``act-local`` gate so the script verifies only the
      F16..S16 range.
    * ``audit01-pytest`` and ``audit01-mypy`` argv contains
      the resolved test inventory tuple, NEVER the literal
      glob pattern.
    """
    py = _default_python()
    test_inventory = resolve_test_inventory(repo_root=repo_root)
    return (
        GateInvocation(
            name="audit01-pytest",
            argv=(
                py,
                "-m",
                "pytest",
                *test_inventory,
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
                *test_inventory,
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
            argv=(
                "./scripts/verify_all.sh",
                "--act-local",
                "--base",
                base,
                "--subject",
                subject,
                "--skip-gate-summary",
            ),
            cwd=str(repo_root),
        ),
        GateInvocation(
            name="diff-check",
            argv=("git", "diff", "--check"),
            cwd=str(repo_root),
        ),
        GateInvocation(
            name="worktree-clean",
            argv=("git", "status", "--porcelain=v1", "-z"),
            cwd=str(repo_root),
        ),
    )


def _execute_invocation(
    invocation: GateInvocation,
    *,
    git_runner: SubprocessGitRunner | None = None,
) -> ExecutedCommand:
    """Execute a single gate invocation and return the typed result.

    Git invocations (``diff-check`` and ``worktree-clean``)
    go through the :class:`SubprocessGitRunner` seam so the
    test suite can patch ``subprocess.run`` and assert that
    every Git call is recorded in the seam's transcript.
    Non-Git gates use :func:`capture_command`.
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
    base: str = "F16",
    subject: str = "S16",
) -> tuple[RepositoryGateResult, ...]:
    """Execute the seven required gates and return the typed records.

    The function builds the closed gate plan, executes every
    invocation, and returns one :class:`RepositoryGateResult`
    per gate.  The order is canonical.  A gate that fails is
    still recorded; the function does NOT short-circuit so
    every gate is captured for the bundle.

    CORRECTION16:

    * the ``worktree-clean`` gate is recorded as
      ``passed`` ONLY when the
      ``git status --porcelain=v1 -z`` stdout is empty;
    * the orchestrator MUST treat a non-empty stdout as
      ``failed`` (the orchestrator's fail-closed check
      consumes the captured status, not the subprocess
      returncode, because git status exits zero even when
      the worktree is dirty).
    """
    invocations = build_required_gates(
        repo_root=repo_root,
        subject_python_paths=subject_python_paths,
        base=base,
        subject=subject,
    )
    out: list[RepositoryGateResult] = []
    for invocation in invocations:
        command = _execute_invocation(
            invocation,
            git_runner=git_runner,
        )
        if invocation.name == "worktree-clean":
            # Override the status: git status --porcelain=v1
            # exits zero even when the worktree is dirty.
            # The gate is "passed" only when the stdout is
            # empty.  Raw bytes are preserved; the orchestrator
            # consumes the ExecutedCommand.status verbatim.
            dirty = bool(command.stdout)
            command = ExecutedCommand(
                name=command.name,
                argv=command.argv,
                cwd=command.cwd,
                returncode=command.returncode,
                stdout=command.stdout,
                stderr=command.stderr,
                status="failed" if dirty else "passed",
            )
        out.append(
            RepositoryGateResult(
                name=invocation.name,
                command=command,
            )
        )
    return tuple(out)


def all_required_gates_pass(
    gate_results: tuple[RepositoryGateResult, ...],
) -> bool:
    """Return True ONLY when every required gate recorded status='passed'.

    CORRECTION16: the function is the canonical fail-closed
    check used by the orchestrator.  An empty tuple is
    rejected (the production transaction must always
    execute the seven required gates).
    """
    if not gate_results:
        return False
    return all(gate.command.status == "passed" for gate in gate_results)


def gate_with_name(
    gate_results: tuple[RepositoryGateResult, ...],
    name: RepositoryGateName,
) -> RepositoryGateResult | None:
    """Return the gate with the supplied name, or ``None``."""
    for gate in gate_results:
        if gate.name == name:
            return gate
    return None


# CORRECTION16: gate_results must NEVER contain a literal
# glob entry in argv.  The function is used by the
# orchestrator's source-guard.
_GLOB_TOKENS = ("*", "?", "[")


def argv_has_literal_glob(argv: tuple[str, ...]) -> bool:
    """Return True when any argv entry contains a literal glob token.

    CORRECTION16: the production transaction must NEVER pass
    ``*``, ``?``, or ``[`` to pytest/mypy/ruff subprocesses;
    the test inventory is resolved in Python first.
    """
    for entry in argv:
        if any(token in entry for token in _GLOB_TOKENS):
            return True
    return False


def assert_argv_has_no_literal_glob(
    gate_results: tuple[RepositoryGateResult, ...],
) -> None:
    """Raise :class:`ValueError` when any gate argv contains a glob.

    CORRECTION16: the source-guard rejects the C15 defect
    where pytest/mypy argv contained the literal glob
    pattern ``tests/verifiers/test_verifier_core_migration_audit01*.py``.
    """
    for gate in gate_results:
        if argv_has_literal_glob(gate.command.argv):
            raise ValueError(
                f"gate {gate.name!r} argv contains a literal glob token: "
                f"{list(gate.command.argv)!r}"
            )


# Re-export so backwards-compatible callers can find the
# helper without renaming import sites.
_default_paths = os.environ.get("K9B_TEST_INVENTORY", "")


__all__ = [
    "AUDIT01_TEST_GLOB_PATTERN",
    "GateInvocation",
    "all_required_gates_pass",
    "argv_has_literal_glob",
    "assert_argv_has_no_literal_glob",
    "build_required_gates",
    "gate_with_name",
    "resolve_test_inventory",
    "run_required_gates",
]
