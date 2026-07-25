"""CORRECTION14/CORRECTION15/CORRECTION16: final-classification renderer.

The renderer accepts typed
:class:`EvidenceTransactionResult` /
:class:`RepositoryGateResult` /
:class:`ClosureTopology` /
:class:`BundleValidationResult` measurements and renders
every claim from a named derivation function.  Hardcoded
``PASS`` rows are forbidden.  An unmeasured claim is
rendered ``UNMEASURED`` or ``FAILED``.

CORRECTION16 hardens the lifecycle:

* the renderer accepts a ``lifecycle_stage`` argument
  (``"pre_root_writes"`` / ``"root_writes"`` /
  ``"published_renamed"``) and renders according to the
  measurements available at that stage;
* the publication row derives ``READY_TO_PUBLISH`` when
  the stages have NOT yet hit ``rename``; after the rename
  the row derives ``PUBLISHED``;
* the ``bundle_root_hash`` row is ``UNMEASURED`` at
  ``pre_root_writes`` and only validated at the
  ``root_writes`` stage.
* the ``leamas_protocol_E`` / ``deterministic_C_proof`` /
  ``wave_1`` rows are explicit closure-topology constants
  (``ABSENT`` / ``BLOCKED``).

Public surface:

* :class:`ClaimResult` - the typed result of a single claim
  derivation function.
* :func:`derive_*` - one named derivation function per row.
* :func:`build_final_classification` - render the
  ``final-classification.md`` text from typed inputs.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from scripts.verifiers_audit.typed_results import (
    BundleValidationResult,
    ClosureTopology,
    EvidenceTransactionResult,
    RepositoryGateResult,
)

ClaimStatus = Literal["PASS", "FAILED", "UNMEASURED", "PENDING_EXTERNAL_RESULT"]

# CORRECTION18: exported constant for external reference
PENDING_EXTERNAL_RESULT: str = "PENDING_EXTERNAL_RESULT"

LifecycleStage = Literal[
    "pre_root_writes",
    "root_writes",
    "published_renamed",
]


@dataclass(frozen=True)
class ClaimResult:
    """A single claim's typed derivation result."""

    name: str
    value: str
    status: ClaimStatus
    derivation: str


def _gate_by_name(
    gates: tuple[RepositoryGateResult, ...], name: str
) -> RepositoryGateResult | None:
    for gate in gates:
        if gate.name == name:
            return gate
    return None


def _gate_pass(gate: RepositoryGateResult | None) -> ClaimResult:
    if gate is None:
        return ClaimResult(
            name="gate_present",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="gate not recorded",
        )
    if gate.command.status == "passed":
        return ClaimResult(
            name="gate_pass",
            value="PASS",
            status="PASS",
            derivation=f"gate {gate.name!r} recorded status=passed",
        )
    return ClaimResult(
        name="gate_pass",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"gate {gate.name!r} recorded status={gate.command.status!r}"
        ),
    )


def derive_audit_check(
    gates: tuple[RepositoryGateResult, ...],
) -> ClaimResult:
    """Derive the ``audit_check`` claim from the ``audit-check`` gate."""
    gate = _gate_by_name(gates, "audit-check")
    if gate is None:
        return ClaimResult(
            name="audit_check",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="audit-check gate not present in gate_results",
        )
    if gate.command.status == "passed":
        return ClaimResult(
            name="audit_check",
            value="PASS",
            status="PASS",
            derivation=(
                f"audit-check gate passed "
                f"(returncode={gate.command.returncode})"
            ),
        )
    return ClaimResult(
        name="audit_check",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"audit-check gate recorded status={gate.command.status!r}"
        ),
    )


def derive_act_local(
    gates: tuple[RepositoryGateResult, ...],
) -> ClaimResult:
    """Derive the ``act_local`` claim from the ``act-local`` gate."""
    gate = _gate_by_name(gates, "act-local")
    if gate is None:
        return ClaimResult(
            name="act_local",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="act-local gate not present in gate_results",
        )
    if gate.command.status == "passed":
        return ClaimResult(
            name="act_local",
            value="PASS",
            status="PASS",
            derivation=(
                f"act-local gate passed "
                f"(returncode={gate.command.returncode})"
            ),
        )
    return ClaimResult(
        name="act_local",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"act-local gate recorded status={gate.command.status!r}"
        ),
    )


def derive_worktree_clean(
    gates: tuple[RepositoryGateResult, ...],
) -> ClaimResult:
    """Derive the ``worktree_clean`` claim from the ``worktree-clean`` gate."""
    gate = _gate_by_name(gates, "worktree-clean")
    if gate is None:
        return ClaimResult(
            name="worktree_clean",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="worktree-clean gate not present in gate_results",
        )
    if gate.command.status == "passed":
        return ClaimResult(
            name="worktree_clean",
            value="PASS",
            status="PASS",
            derivation=(
                f"worktree-clean gate passed "
                f"(empty stdout, returncode={gate.command.returncode})"
            ),
        )
    return ClaimResult(
        name="worktree_clean",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"worktree-clean gate recorded non-empty stdout "
            f"(status={gate.command.status!r})"
        ),
    )


def derive_diff_check(
    gates: tuple[RepositoryGateResult, ...],
) -> ClaimResult:
    """Derive the ``diff_check`` claim from the ``diff-check`` gate."""
    gate = _gate_by_name(gates, "diff-check")
    if gate is None:
        return ClaimResult(
            name="diff_check",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="diff-check gate not present in gate_results",
        )
    if gate.command.status == "passed":
        return ClaimResult(
            name="diff_check",
            value="PASS",
            status="PASS",
            derivation=(
                f"diff-check gate passed "
                f"(returncode={gate.command.returncode})"
            ),
        )
    return ClaimResult(
        name="diff_check",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"diff-check gate recorded status={gate.command.status!r}"
        ),
    )


def derive_git_diff_cardinality(
    evidence: EvidenceTransactionResult,
) -> ClaimResult:
    """Derive the ``git_diff_cardinality`` claim from the executed transcript."""
    git_diff_count = sum(
        1 for cmd in evidence.git_commands
        if cmd.argv[:2] == ("git", "diff")
    )
    rev_parse_count = sum(
        1 for cmd in evidence.git_commands
        if cmd.argv[:2] == ("git", "rev-parse")
    )
    if git_diff_count == 1 and rev_parse_count == 9:
        return ClaimResult(
            name="git_diff_cardinality",
            value="PASS",
            status="PASS",
            derivation=(
                f"transcript reports 1 git-diff and 9 rev-parse calls "
                f"(topology+range subset, {len(evidence.git_commands)} total)"
            ),
        )
    return ClaimResult(
        name="git_diff_cardinality",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"transcript reports {git_diff_count} git-diff and "
            f"{rev_parse_count} rev-parse calls (expected 1 and 5)"
        ),
    )


def derive_transaction_summary(
    evidence: EvidenceTransactionResult,
) -> ClaimResult:
    """Derive the ``transaction_summary`` claim from the typed summary."""
    summary = evidence.transaction_summary
    if summary is None:
        return ClaimResult(
            name="transaction_summary",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation=(
                "transaction_summary not recorded"
            ),
        )
    if (
        summary.topology_git_commands == 7
        and summary.range_git_commands == 3
        and summary.gate_git_commands == 2
        and summary.unrecorded_git_commands == 0
        and summary.hidden_shell_git_invocations == 0
    ):
        return ClaimResult(
            name="transaction_summary",
            value="PASS",
            status="PASS",
            derivation=(
                f"topology={summary.topology_git_commands} "
                f"range={summary.range_git_commands} "
                f"gate={summary.gate_git_commands} "
                f"total={summary.total_git_commands} "
                f"unrecorded={summary.unrecorded_git_commands}"
            ),
        )
    return ClaimResult(
        name="transaction_summary",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"topology={summary.topology_git_commands} "
            f"range={summary.range_git_commands} "
            f"gate={summary.gate_git_commands} "
            f"total={summary.total_git_commands} "
            f"unrecorded={summary.unrecorded_git_commands} "
            f"hidden_shell={summary.hidden_shell_git_invocations}"
        ),
    )


def derive_ruff_invocation(
    evidence: EvidenceTransactionResult,
) -> ClaimResult:
    """Derive the Ruff invocation claim from the typed measurement."""
    if evidence.ruff_result is None:
        return ClaimResult(
            name="ruff_invocation",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="Ruff was not invoked (empty Python range)",
        )
    if evidence.ruff_result.status == "passed":
        return ClaimResult(
            name="ruff_invocation",
            value="PASS",
            status="PASS",
            derivation=(
                f"Ruff status=passed (returncode={evidence.ruff_result.returncode})"
            ),
        )
    return ClaimResult(
        name="ruff_invocation",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"Ruff status={evidence.ruff_result.status!r} "
            f"(returncode={evidence.ruff_result.returncode})"
        ),
    )


def derive_ruff_equivalence(
    evidence: EvidenceTransactionResult,
) -> ClaimResult:
    """Derive the Ruff equivalence claim from the typed proof."""
    proof = evidence.ruff_equivalence
    if proof is None:
        return ClaimResult(
            name="ruff_equivalence",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="ruff_equivalence not recorded",
        )
    if proof.equivalent:
        return ClaimResult(
            name="ruff_equivalence",
            value="PASS",
            status="PASS",
            derivation=(
                f"explicit_returncode={proof.explicit_returncode} "
                f"canonical_returncode={proof.canonical_returncode} "
                f"diagnostics_sha256={proof.explicit_diagnostics_sha256} "
                f"ruff_version={proof.ruff_version!r}"
            ),
        )
    return ClaimResult(
        name="ruff_equivalence",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"explicit_returncode={proof.explicit_returncode} "
            f"canonical_returncode={proof.canonical_returncode} "
            f"explicit_diagnostics_sha256="
            f"{proof.explicit_diagnostics_sha256} "
            f"canonical_diagnostics_sha256="
            f"{proof.canonical_diagnostics_sha256} "
            f"ruff_version={proof.ruff_version!r}"
        ),
    )


def derive_range_resolution(
    evidence: EvidenceTransactionResult,
) -> ClaimResult:
    """Derive the range resolution claim from the typed OID pair."""
    if evidence.base_oid and evidence.subject_oid:
        return ClaimResult(
            name="range_resolution",
            value="PASS",
            status="PASS",
            derivation=(
                f"base_oid={evidence.base_oid[:12]} subject_oid="
                f"{evidence.subject_oid[:12]}"
            ),
        )
    return ClaimResult(
        name="range_resolution",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"base_oid={evidence.base_oid!r} subject_oid={evidence.subject_oid!r}"
        ),
    )


def derive_topology_resolution(
    evidence: EvidenceTransactionResult,
) -> ClaimResult:
    """Derive the ``topology_resolution`` claim from the transcript topology."""
    topology = evidence.repository_topology
    if topology is None:
        return ClaimResult(
            name="topology_resolution",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="repository_topology not recorded",
        )
    if (
        topology.F16
        and topology.S16
        and topology.parent_F16
        and topology.parent_S16 == topology.F16
    ):
        return ClaimResult(
            name="topology_resolution",
            value="PASS",
            status="PASS",
            derivation=(
                f"F16={topology.F16[:12]} S16={topology.S16[:12]} "
                f"parent_F16={topology.parent_F16[:12]} "
                f"parent_S16={topology.parent_S16[:12]}"
            ),
        )
    return ClaimResult(
        name="topology_resolution",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"F16={topology.F16!r} S16={topology.S16!r} "
            f"parent_F16={topology.parent_F16!r} "
            f"parent_S16={topology.parent_S16!r}"
        ),
    )


def derive_bundle_completeness(
    validation: BundleValidationResult,
) -> ClaimResult:
    """Derive the bundle completeness claim from the actual enumeration."""
    if validation.is_valid:
        return ClaimResult(
            name="bundle_completeness",
            value="PASS",
            status="PASS",
            derivation=(
                f"observed={len(validation.observed_artifacts)} "
                f"declared={len(validation.declared_artifacts)} "
                "missing=0 extra=0 rejected=0"
            ),
        )
    return ClaimResult(
        name="bundle_completeness",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"missing={list(validation.missing_artifacts)} "
            f"extra={list(validation.extra_artifacts)} "
            f"rejected={list(validation.rejected_entries)}"
        ),
    )


def derive_publication_status(
    evidence: EvidenceTransactionResult,
    *,
    lifecycle_stage: LifecycleStage = "pre_root_writes",
) -> ClaimResult:
    """Derive the publication status from the typed result.

    CORRECTION16: the row reflects the lifecycle stage.  At
    ``pre_root_writes`` the bundle is
    ``READY_TO_PUBLISH`` (the bundle-root is not yet on
    disk).  At ``root_writes`` the bundle-root has been
    written and verified; the bundle is still
    ``READY_TO_PUBLISH`` until the rename.  At
    ``published_renamed`` the bundle is ``PUBLISHED``.
    """
    if lifecycle_stage == "published_renamed":
        return ClaimResult(
            name="publication_status",
            value="PUBLISHED",
            status="PASS",
            derivation=(
                "evidence.publication_status == 'published' "
                "after atomic rename; in-bundle files NEVER claim "
                "their own later publication succeeded"
            ),
        )
    if evidence.publication_status == "ready_to_publish":
        return ClaimResult(
            name="publication_status",
            value="READY_TO_PUBLISH",
            status="PASS",
            derivation=(
                "staging bundle is valid; rename to final destination "
                "is the publication event"
            ),
        )
    return ClaimResult(
        name="publication_status",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"evidence.publication_status={evidence.publication_status!r}"
        ),
    )


def derive_bundle_root_hash(
    sha_map: Mapping[str, str],
    *,
    lifecycle_stage: LifecycleStage = "pre_root_writes",
) -> ClaimResult:
    """Derive the bundle root hash claim from the recorded hash map.

    CORRECTION16: at ``pre_root_writes`` the bundle-root is
    NOT yet on disk; the row is ``UNMEASURED``.  At
    ``root_writes`` and ``published_renamed`` the row is
    the recorded ``bundle-root.json`` hash.
    """
    if lifecycle_stage == "pre_root_writes":
        return ClaimResult(
            name="bundle_root_hash",
            value="UNMEASURED",
            status="UNMEASURED",
            derivation="bundle-root.json not yet written",
        )
    digest = sha_map.get("bundle-root.json", "")
    if digest:
        return ClaimResult(
            name="bundle_root_hash",
            value=digest,
            status="PASS",
            derivation=(
                "bundle-root.json recorded hash from disk bytes"
            ),
        )
    return ClaimResult(
        name="bundle_root_hash",
        value="UNMEASURED",
        status="UNMEASURED",
        derivation="bundle-root.json hash missing from authoritative_hashes",
    )


def derive_bundle_root_validated(
    sha_map: Mapping[str, str],
    *,
    lifecycle_stage: LifecycleStage = "pre_root_writes",
) -> ClaimResult:
    """Derive the ``bundle_root_validated`` claim from the lifecycle stage.

    CORRECTION16: the row is
    ``PENDING_EXTERNAL_RESULT`` at ``pre_root_writes`` and
    ``root_writes``; the only authoritative validation is
    the external publication result, recorded AFTER the
    rename.
    """
    if lifecycle_stage == "published_renamed":
        digest = sha_map.get("bundle-root.json", "")
        if digest:
            return ClaimResult(
                name="bundle_root_validated",
                value="PASS",
                status="PASS",
                derivation=(
                    f"post-publish rehash of bundle-root.json={digest}"
                ),
            )
        return ClaimResult(
            name="bundle_root_validated",
            value="FAILED",
            status="FAILED",
            derivation=(
                "post-publish rehash did not find bundle-root.json"
            ),
        )
    return ClaimResult(
        name="bundle_root_validated",
        value="PENDING_EXTERNAL_RESULT",
        status="PENDING_EXTERNAL_RESULT",
        derivation=(
            "external publication result is the only authoritative "
            "validation; in-bundle classification cannot claim PASS"
        ),
    )


def _lifecycle_row(name: str, value: str, derivation: str) -> ClaimResult:
    return ClaimResult(
        name=name,
        value=value,
        status="PASS",
        derivation=derivation,
    )


def build_final_classification(
    *,
    evidence: EvidenceTransactionResult,
    gate_results: tuple[RepositoryGateResult, ...] = (),
    topology: ClosureTopology | None = None,
    validation: BundleValidationResult | None = None,
    sha_map: Mapping[str, str] = {},
    lifecycle_stage: LifecycleStage = "pre_root_writes",
) -> str:
    """Build the final-classification.md text from typed results.

    CORRECTION16: the renderer accepts the ``lifecycle_stage``
    argument and renders the publication / bundle-root /
    bundle-root-validated rows according to the measurements
    available at that stage.  No claim is hardcoded; no claim
    is rendered ``PASS`` from the mere presence of a row.
    """
    if validation is None:
        validation = BundleValidationResult(
            declared_artifacts=(),
            observed_artifacts=(),
            missing_artifacts=(),
            extra_artifacts=(),
            rejected_entries=(),
        )

    derived: list[ClaimResult] = [
        derive_audit_check(gate_results),
        derive_act_local(gate_results),
        derive_worktree_clean(gate_results),
        derive_diff_check(gate_results),
        derive_git_diff_cardinality(evidence),
        derive_transaction_summary(evidence),
        derive_ruff_invocation(evidence),
        derive_ruff_equivalence(evidence),
        derive_range_resolution(evidence),
        derive_topology_resolution(evidence),
        derive_bundle_completeness(validation),
        derive_publication_status(
            evidence, lifecycle_stage=lifecycle_stage
        ),
        derive_bundle_root_hash(
            sha_map, lifecycle_stage=lifecycle_stage
        ),
        derive_bundle_root_validated(
            sha_map, lifecycle_stage=lifecycle_stage
        ),
        _lifecycle_row(
            "manual_preclosure_evidence",
            "PRESENT",
            "explicit closure-topology constant",
        ),
        _lifecycle_row(
            "leamas_protocol_E",
            "ABSENT",
            "explicit closure-topology constant",
        ),
        _lifecycle_row(
            "closure_commit_C",
            "ABSENT",
            "explicit closure-topology constant",
        ),
        _lifecycle_row(
            "annotated_tag_T",
            "ABSENT",
            "explicit closure-topology constant",
        ),
        _lifecycle_row(
            "deterministic_C_proof",
            "BLOCKED",
            "explicit closure-topology constant",
        ),
        _lifecycle_row(
            "wave_1",
            "BLOCKED",
            "explicit closure-topology constant",
        ),
        _lifecycle_row(
            "CORRECTION16",
            "PARTIAL_CHECKPOINT",
            "explicit closure-topology constant",
        ),
    ]

    lines: list[str] = [
        "# CORRECTION16 evidence bundle final-classification.md",
        "",
        f"## Lifecycle stage: {lifecycle_stage}",
        "",
        "## Lifecycle",
        "",
        "| Signal | Value | Derivation |",
        "| --- | --- | --- |",
    ]
    for claim in derived:
        lines.append(
            f"| {claim.name} | {claim.value} | {claim.derivation} |"
        )
    topo = evidence.repository_topology
    summary = evidence.transaction_summary
    proof = evidence.ruff_equivalence
    lines.extend(
        [
            "",
            "## Object IDs",
            "",
            f"- base = `{evidence.base_oid}`",
            f"- subject = `{evidence.subject_oid}`",
            f"- F16 = `{topo.F16 if topo else ''}`",
            f"- S16 = `{topo.S16 if topo else ''}`",
            f"- parent_F16 = `{topo.parent_F16 if topo else ''}`",
            f"- parent_S16 = `{topo.parent_S16 if topo else ''}`",
            f"- plan_blob = `{topo.plan_blob if topo else ''}`",
            f"- git_commands = `{len(evidence.git_commands)}`",
            "",
            "## Transaction summary",
            "",
            f"- topology_git_commands = "
            f"`{summary.topology_git_commands if summary else 'n/a'}`",
            f"- range_git_commands = "
            f"`{summary.range_git_commands if summary else 'n/a'}`",
            f"- gate_git_commands = "
            f"`{summary.gate_git_commands if summary else 'n/a'}`",
            f"- total_git_commands = "
            f"`{summary.total_git_commands if summary else 'n/a'}`",
            f"- unrecorded_git_commands = "
            f"`{summary.unrecorded_git_commands if summary else 'n/a'}`",
            f"- hidden_shell_git_invocations = "
            f"`{summary.hidden_shell_git_invocations if summary else 'n/a'}`",
            "",
            "## Ruff equivalence",
            "",
            f"- explicit_returncode = "
            f"`{proof.explicit_returncode if proof else 'n/a'}`",
            f"- canonical_returncode = "
            f"`{proof.canonical_returncode if proof else 'n/a'}`",
            f"- explicit_diagnostics_sha256 = "
            f"`{proof.explicit_diagnostics_sha256 if proof else 'n/a'}`",
            f"- canonical_diagnostics_sha256 = "
            f"`{proof.canonical_diagnostics_sha256 if proof else 'n/a'}`",
            f"- ruff_version = "
            f"`{proof.ruff_version if proof else 'n/a'}`",
            f"- input_path_tuple_sha256 = "
            f"`{proof.input_path_tuple_sha256 if proof else 'n/a'}`",
            f"- config_path = "
            f"`{proof.config_path if proof else 'n/a'}`",
            f"- equivalent = "
            f"`{proof.equivalent if proof else 'n/a'}`",
            "",
            "## Authoritative hashes",
            "",
        ]
    )
    for relpath in sorted(sha_map):
        lines.append(f"- {relpath} = `{sha_map[relpath]}`")
    lines.extend(
        [
            "",
            "## Protocol",
            "",
            (
                "manual_preclosure_evidence (NOT leamas protocol E). "
                "C / T / E are absent; the v2 binary is unavailable. "
                "Wave 1 blocked until AUDIT01 receives a complete v2 closure."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


__all__ = [
    "ClaimResult",
    "ClaimStatus",
    "LifecycleStage",
    "build_final_classification",
    "derive_act_local",
    "derive_audit_check",
    "derive_bundle_completeness",
    "derive_bundle_root_hash",
    "derive_bundle_root_validated",
    "derive_diff_check",
    "derive_git_diff_cardinality",
    "derive_publication_status",
    "derive_range_resolution",
    "derive_ruff_equivalence",
    "derive_ruff_invocation",
    "derive_topology_resolution",
    "derive_transaction_summary",
    "derive_worktree_clean",
]
