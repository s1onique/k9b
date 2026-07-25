"""CORRECTION14/CORRECTION15: typed evidence-result dataclasses.

Every claim in the final-classification.md file MUST be derived
from a typed :class:`ExecutedCommand` /
:class:`EvidenceTransactionResult` /
:class:`RepositoryGateResult` /
:class:`BundleValidationResult` measurement.  Hardcoded
``PASS`` rows are forbidden.  An unmeasured claim is rendered
``UNMEASURED`` or ``FAILED``; an absent row is omitted from the
output entirely (the lifecycle rows for ``C`` / ``T`` /
``leamas_protocol_E`` are still emitted with their
``ABSENT`` / ``BLOCKED`` values because they are explicit
closure-topology constants, not measurements).

Public surface:

* :class:`ExecutedCommand` - one executed command with the
  raw stdout/stderr bytes preserved in memory; the
  ``stdout_sha256`` / ``stderr_sha256`` properties are derived
  from those bytes (CORRECTION15).
* :class:`EvidenceTransactionResult` - the entire detached
  evidence transaction (base_oid, subject_oid, git_commands,
  ruff_result, publication_status, authoritative_hashes).
* :class:`RepositoryGateResult` - one captured post-subject
  gate command with a closed semantic ``name`` (Literal).
* :class:`ClosureTopology` - the deterministic closure
  topology record (F15, F15_tree, plan_blob, S15, S15_tree,
  parent_F15, parent_S15).
* :class:`BundleValidationResult` - the bundle validation
  outcome (declarative set, computed set, missing/extra,
  symmetric difference).
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

CommandStatus = Literal["passed", "failed", "skipped"]
"""The terminal status of a single executed command.

* ``"passed"`` - the command exited zero AND produced the
  expected outcome (e.g. ``git diff`` returned a path tuple).
* ``"failed"`` - the command exited non-zero OR returned an
  outcome the caller has rejected (e.g. a Ruff run with
  findings when the contract required clean output).
* ``"skipped"`` - the command was not invoked because the
  preconditions for invocation were not met (empty Python
  range; non-zero exit impossible to satisfy).
"""


PublicationStatus = Literal["ready_to_publish", "published", "failed"]
"""The terminal publication status of the evidence transaction.

* ``"ready_to_publish"`` - every required artifact is present
  on disk; the staging directory is ready for atomic rename.
* ``"published"`` - the rename succeeded; the bundle is
  immutable from this point forward.
* ``"failed"`` - any precondition failed; the staging
  directory was removed and the final destination does not
  exist.
"""


RepositoryGateName = Literal[
    "audit01-pytest",
    "audit01-ruff",
    "audit01-mypy",
    "audit-check",
    "act-local",
    "diff-check",
    "worktree-clean",
]
"""CORRECTION15: closed set of semantic gate names.

The evidence driver MUST execute every required gate before
publication.  Gate identity is NEVER inferred from the argv
prefix; the closed ``Literal`` set is the SOLE authority for
the allowed names.
"""


@dataclass(frozen=True)
class ExecutedCommand:
    """CORRECTION15: one executed command and its outcome.

    * ``name`` - the semantic name of the command (e.g.
      ``"git-rev-parse-base"`` or the gate name).  Optional
      for ad-hoc captures; required for gates.
    * ``argv`` - the executed argv (tuple, never list).
    * ``cwd`` - the working directory (filesystem path).
    * ``returncode`` - the subprocess exit code.
    * ``stdout`` - the raw captured stdout bytes
      (CORRECTION15: bytes are preserved in memory; the
      ``stdout_sha256`` property is derived from them).
    * ``stderr`` - the raw captured stderr bytes
      (CORRECTION15: bytes are preserved in memory; the
      ``stderr_sha256`` property is derived from them).
    * ``status`` - the terminal status (``"passed"`` /
      ``"failed"`` / ``"skipped"``).
    """

    name: str
    argv: tuple[str, ...]
    cwd: str
    returncode: int
    stdout: bytes
    stderr: bytes
    status: CommandStatus

    @property
    def stdout_sha256(self) -> str:
        return hashlib.sha256(self.stdout).hexdigest()

    @property
    def stderr_sha256(self) -> str:
        return hashlib.sha256(self.stderr).hexdigest()


# CORRECTION14 backwards-compat alias.  Existing tests that
# import ``CommandResult`` continue to resolve; new code
# should prefer :class:`ExecutedCommand`.
CommandResult = ExecutedCommand


@dataclass(frozen=True)
class EvidenceTransactionResult:
    """CORRECTION14/CORRECTION15: the entire detached evidence
    transaction.

    * ``base_oid`` - the resolved full object ID of BASE.
    * ``subject_oid`` - the resolved full object ID of SUBJECT.
    * ``git_commands`` - every recorded Git command result.
    * ``ruff_result`` - the Ruff result (or ``None`` when Ruff
      was not invoked - empty Python range).
    * ``publication_status`` - the terminal publication status.
    * ``authoritative_hashes`` - SHA-256 of every authoritative
      final artifact (relpath -> hex digest).
    """

    base_oid: str
    subject_oid: str
    git_commands: tuple[ExecutedCommand, ...]
    ruff_result: ExecutedCommand | None
    publication_status: PublicationStatus
    authoritative_hashes: Mapping[str, str]


@dataclass(frozen=True)
class RepositoryGateResult:
    """CORRECTION15: one captured post-subject gate command.

    * ``name`` - the gate's closed semantic name (one of the
      values in :data:`RepositoryGateName`).  The name is
      NEVER inferred from ``argv[0]``.
    * ``command`` - the typed :class:`ExecutedCommand`
      produced by the evidence driver.

    The gate is treated as ``passed`` when the underlying
    :class:`ExecutedCommand` ``status`` is ``"passed"`` (which
    requires both ``returncode == 0`` and a non-empty captured
    outcome when the contract demands one).
    """

    name: RepositoryGateName
    command: ExecutedCommand


@dataclass(frozen=True)
class ClosureTopology:
    """CORRECTION14/CORRECTION15: the deterministic closure-topology record.

    * ``F15`` - the CORRECTION15 plan-freeze commit hash.
    * ``F15_tree`` - the tree hash of the F15 commit.
    * ``plan_blob`` - the SHA-256 of the plan file bytes.
    * ``S15`` - the CORRECTION15 subject commit hash (None
      when not yet authored).
    * ``S15_tree`` - the tree hash of the S15 commit (None
      when S15 is absent).
    * ``parent_F15`` - the parent of F15 (= S14).
    * ``parent_S15`` - the parent of S15 (= F15) when S15 is
      present; None otherwise.

    The dataclass is the SOLE authority for which commits
    bound the closure.  Renderers MUST consult it directly
    instead of hardcoding lifecycle strings.
    """

    F15: str
    F15_tree: str
    plan_blob: str
    S15: str | None
    S15_tree: str | None
    parent_F15: str
    parent_S15: str | None

    # CORRECTION14 backwards-compat aliases.
    @property
    def F14(self) -> str:  # pragma: no cover - alias
        return self.F15

    @property
    def F14_tree(self) -> str:  # pragma: no cover - alias
        return self.F15_tree

    @property
    def S14(self) -> str | None:  # pragma: no cover - alias
        return self.S15

    @property
    def S14_tree(self) -> str | None:  # pragma: no cover - alias
        return self.S15_tree

    @property
    def parent_F14(self) -> str:  # pragma: no cover - alias
        return self.parent_F15

    @property
    def parent_S14(self) -> str | None:  # pragma: no cover - alias
        return self.parent_S15


@dataclass(frozen=True)
class BundleValidationResult:
    """CORRECTION15: bundle validation outcome.

    * ``declared_artifacts`` - the complete declared final
      artifact set (no staging/output/temp absolute paths).
    * ``observed_artifacts`` - the actual directory
      enumeration result.
    * ``missing_artifacts`` - declared artifacts that are
      absent from the actual directory.
    * ``extra_artifacts`` - entries present in the actual
      directory that are not in the declared set.
    * ``rejected_entries`` - entries rejected for being a
      directory descendant, a symlink, a special file, or
      for an unexpected name.
    """

    declared_artifacts: tuple[str, ...]
    observed_artifacts: tuple[str, ...]
    missing_artifacts: tuple[str, ...]
    extra_artifacts: tuple[str, ...]
    rejected_entries: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return (
            not self.missing_artifacts
            and not self.extra_artifacts
            and not self.rejected_entries
        )


__all__ = [
    "BundleValidationResult",
    "ClosureTopology",
    "CommandResult",
    "CommandStatus",
    "EvidenceTransactionResult",
    "ExecutedCommand",
    "PublicationStatus",
    "RepositoryGateName",
    "RepositoryGateResult",
]
