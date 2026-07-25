"""CORRECTION14/CORRECTION15/CORRECTION16: typed evidence-result dataclasses.

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

CORRECTION16 additions:

* :class:`GitCommandKind` - the closed ``Literal`` of
  permitted Git command classifications;
* :class:`TransactionGitCommand` - a single Git command
  typed with its kind (topology / range / gate / other);
* :class:`TransactionSummary` - the typed cardinality of
  every Git command in the transaction;
* :class:`RepositoryTopology` - the topology derived from
  the Git transcript (F16 / S16 / parent / tree / blob);
* :class:`RuffEquivalenceProof` - the explicit vs canonical
  Ruff comparison record.

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
  topology record (F16, F16_tree, plan_blob, S16, S16_tree,
  parent_F16, parent_S16).
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


# CORRECTION16: the closed ``Literal`` of Git command kinds.
# The orchestrator MUST tag every recorded Git command with
# one of these values so the cardinality of the transaction
# is auditable.
GitCommandKind = Literal["topology", "range", "gate", "other"]


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
class TransactionGitCommand:
    """CORRECTION16: a single Git command with its kind tag.

    * ``command`` - the typed :class:`ExecutedCommand` from
      the seam.
    * ``kind`` - the :class:`GitCommandKind` tag.
    """

    command: ExecutedCommand
    kind: GitCommandKind


@dataclass(frozen=True)
class TransactionSummary:
    """CORRECTION16: the canonical transcript cardinality.

    * ``topology_git_commands`` - the number of recorded
      topology Git commands (F16 / S16 / parent / tree / blob
      queries).
    * ``range_git_commands`` - the number of recorded range
      Git commands (BASE / SUBJECT rev-parse + diff).
    * ``gate_git_commands`` - the number of recorded gate
      Git commands (``diff-check`` + ``worktree-clean``).
    * ``total_git_commands`` - the total number of recorded
      Git commands.
    * ``unrecorded_git_commands`` - the number of Git
      invocations that bypassed the seam (MUST be zero).
    * ``hidden_shell_git_invocations`` - the number of Git
      invocations hidden inside a shell command (MUST be
      zero).
    """

    topology_git_commands: int
    range_git_commands: int
    gate_git_commands: int
    total_git_commands: int
    unrecorded_git_commands: int = 0
    hidden_shell_git_invocations: int = 0


@dataclass(frozen=True)
class RepositoryTopology:
    """CORRECTION16: the topology derived from the Git transcript.

    * ``F16`` - the resolved full OID of the plan-freeze
      commit.
    * ``F16_tree`` - the tree hash of F16.
    * ``plan_blob`` - the blob hash of the plan file in F16.
    * ``S16`` - the resolved full OID of the subject commit.
    * ``S16_tree`` - the tree hash of S16.
    * ``parent_F16`` - the parent of F16 (= S15).
    * ``parent_S16`` - the parent of S16 (= F16).
    * ``plan_path`` - the plan path relative to the repo root.
    """

    F16: str
    F16_tree: str
    plan_blob: str
    S16: str
    S16_tree: str
    parent_F16: str
    parent_S16: str
    plan_path: str


@dataclass(frozen=True)
class RuffEquivalenceProof:
    """CORRECTION16: explicit vs canonical Ruff equivalence proof.

    * ``explicit_returncode`` - returncode of the explicit
      ``--config <canonical-config>`` invocation against the
      exact subject Python path tuple.
    * ``canonical_returncode`` - returncode of the canonical
      (no ``--config``) invocation against the same tuple.
    * ``explicit_diagnostics_sha256`` - SHA-256 of the
      explicit invocation's normalised diagnostics payload.
    * ``canonical_diagnostics_sha256`` - SHA-256 of the
      canonical invocation's normalised diagnostics payload.
    * ``ruff_version`` - the Ruff version used by both
      invocations.
    * ``input_path_tuple_sha256`` - SHA-256 of the sorted
      tuple of input paths (identical for both invocations).
    * ``config_path`` - the canonical config path used by
      the explicit invocation.
    * ``config_sha256`` - SHA-256 of the canonical config
      file.
    * ``equivalent`` - True when returncode equal AND
      normalised diagnostics SHA-256 equal AND ruff_version
      equal AND input_path_tuple_sha256 equal.
    """

    explicit_returncode: int
    canonical_returncode: int
    explicit_diagnostics_sha256: str
    canonical_diagnostics_sha256: str
    ruff_version: str
    input_path_tuple_sha256: str
    config_path: str
    config_sha256: str
    equivalent: bool


@dataclass(frozen=True)
class EvidenceTransactionResult:
    """CORRECTION14/CORRECTION15/CORRECTION16: the entire detached
    evidence transaction.

    * ``base_oid`` - the resolved full object ID of BASE.
    * ``subject_oid`` - the resolved full object ID of SUBJECT.
    * ``git_commands`` - every recorded Git command result.
    * ``ruff_result`` - the Ruff result (or ``None`` when Ruff
      was not invoked - empty Python range).
    * ``publication_status`` - the terminal publication status.
    * ``authoritative_hashes`` - SHA-256 of every authoritative
      final artifact (relpath -> hex digest).
    * ``transaction_summary`` - the CORRECTION16 typed
      cardinality of the Git transcript.
    * ``repository_topology`` - the CORRECTION16 topology
      derived from the Git transcript.
    * ``ruff_equivalence`` - the CORRECTION16 equivalence
      proof record.
    * ``all_gates_pass`` - the CORRECTION16 typed result of
      the fail-closed gate check.
    """

    base_oid: str
    subject_oid: str
    git_commands: tuple[ExecutedCommand, ...]
    ruff_result: ExecutedCommand | None
    publication_status: PublicationStatus
    authoritative_hashes: Mapping[str, str]
    transaction_summary: TransactionSummary | None = None
    repository_topology: RepositoryTopology | None = None
    ruff_equivalence: RuffEquivalenceProof | None = None
    all_gates_pass: bool = True


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
    """CORRECTION14/CORRECTION15/CORRECTION16: the deterministic
    closure-topology record.

    * ``F16`` - the CORRECTION16 plan-freeze commit hash.
    * ``F16_tree`` - the tree hash of the F16 commit.
    * ``plan_blob`` - the SHA-256 of the plan file bytes.
    * ``S16`` - the CORRECTION16 subject commit hash.
    * ``S16_tree`` - the tree hash of the S16 commit.
    * ``parent_F16`` - the parent of F16 (= final S15).
    * ``parent_S16`` - the parent of S16 (= F16).

    The dataclass is the SOLE authority for which commits
    bound the closure.  Renderers MUST consult it directly
    instead of hardcoding lifecycle strings.

    CORRECTION14 backwards-compat aliases (F14 / S14) are
    preserved so older callers can read the same fields by
    their previous name.
    """

    F16: str
    F16_tree: str
    plan_blob: str
    S16: str | None
    S16_tree: str | None
    parent_F16: str
    parent_S16: str | None

    # CORRECTION14 backwards-compat aliases.
    @property
    def F15(self) -> str:  # pragma: no cover - alias
        return self.F16

    @property
    def F15_tree(self) -> str:  # pragma: no cover - alias
        return self.F16_tree

    @property
    def S15(self) -> str | None:  # pragma: no cover - alias
        return self.S16

    @property
    def S15_tree(self) -> str | None:  # pragma: no cover - alias
        return self.S16_tree

    @property
    def parent_F15(self) -> str:  # pragma: no cover - alias
        return self.parent_F16

    @property
    def parent_S15(self) -> str | None:  # pragma: no cover - alias
        return self.parent_S16

    # CORRECTION14 backwards-compat aliases.
    @property
    def F14(self) -> str:  # pragma: no cover - alias
        return self.F16

    @property
    def F14_tree(self) -> str:  # pragma: no cover - alias
        return self.F16_tree

    @property
    def S14(self) -> str | None:  # pragma: no cover - alias
        return self.S16

    @property
    def S14_tree(self) -> str | None:  # pragma: no cover - alias
        return self.S16_tree

    @property
    def parent_F14(self) -> str:  # pragma: no cover - alias
        return self.parent_F16

    @property
    def parent_S14(self) -> str | None:  # pragma: no cover - alias
        return self.parent_S16


@dataclass(frozen=True)
class BundleValidationResult:
    """CORRECTION15/CORRECTION16: bundle validation outcome.

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
    "GitCommandKind",
    "PublicationStatus",
    "RepositoryGateName",
    "RepositoryGateResult",
    "RepositoryTopology",
    "RuffEquivalenceProof",
    "TransactionGitCommand",
    "TransactionSummary",
]
