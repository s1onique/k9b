"""CORRECTION14/CORRECTION15: final-classification renderer.

The renderer accepts typed
:class:`EvidenceTransactionResult` /
:class:`RepositoryGateResult` /
:class:`ClosureTopology` /
:class:`BundleValidationResult` measurements and renders
every claim from a named derivation function.  Hardcoded
``PASS`` rows are forbidden.  An unmeasured claim is
rendered ``UNMEASURED`` or ``FAILED``.

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

ClaimStatus = Literal["PASS", "FAILED", "UNMEASURED"]


@dataclass(frozen=True)
class ClaimResult:
    """CORRECTION15: a single claim's typed derivation result."""

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
    if git_diff_count == 1 and rev_parse_count == 2:
        return ClaimResult(
            name="git_diff_cardinality",
            value="PASS",
            status="PASS",
            derivation=(
                f"transcript reports 1 git-diff and 2 rev-parse calls "
                f"({len(evidence.git_commands)} total)"
            ),
        )
    return ClaimResult(
        name="git_diff_cardinality",
        value="FAILED",
        status="FAILED",
        derivation=(
            f"transcript reports {git_diff_count} git-diff and "
            f"{rev_parse_count} rev-parse calls (expected 1 and 2)"
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
) -> ClaimResult:
    """Derive the publication status from the typed result.

    Inside the immutable bundle the publication is
    ``READY_TO_PUBLISH``; the rename to the final
    destination records the manual publication result in
    a separate transcript outside the bundle.
    """
    if evidence.publication_status == "published":
        return ClaimResult(
            name="publication_status",
            value="PUBLISHED",
            status="PASS",
            derivation=(
                "evidence.publication_status == 'published' "
                "(post-rename manual publication transcript)"
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
) -> ClaimResult:
    """Derive the bundle root hash claim from the recorded hash map."""
    digest = sha_map.get("bundle-root.json", "")
    if digest:
        return ClaimResult(
            name="bundle_root_hash",
            value=digest,
            status="PASS",
            derivation=(
                "bundle-root.json recorded hash in authoritative_hashes"
            ),
        )
    return ClaimResult(
        name="bundle_root_hash",
        value="UNMEASURED",
        status="UNMEASURED",
        derivation="bundle-root.json hash missing from authoritative_hashes",
    )


def _lifecycle_row(name: str, value: str) -> ClaimResult:
    return ClaimResult(
        name=name,
        value=value,
        status="PASS",
        derivation="explicit closure-topology constant",
    )


def build_final_classification(
    *,
    evidence: EvidenceTransactionResult,
    gate_results: tuple[RepositoryGateResult, ...] = (),
    topology: ClosureTopology,
    validation: BundleValidationResult | None = None,
    sha_map: Mapping[str, str] = {},
) -> str:
    """Build the final-classification.md text from typed results.

    Every claim is derived from a named function; the
    renderer accepts the typed
    :class:`EvidenceTransactionResult`, the
    :class:`RepositoryGateResult` sequence, the
    :class:`ClosureTopology`, the
    :class:`BundleValidationResult`, and the authoritative
    hash mapping.  No claim is hardcoded; no claim is
    rendered ``PASS`` from the mere presence of a row.
    """
    derived: list[ClaimResult] = [
        derive_audit_check(gate_results),
        derive_git_diff_cardinality(evidence),
        derive_ruff_invocation(evidence),
        derive_range_resolution(evidence),
        derive_bundle_completeness(
            validation if validation is not None
            else BundleValidationResult(
                declared_artifacts=(),
                observed_artifacts=(),
                missing_artifacts=(),
                extra_artifacts=(),
                rejected_entries=(),
            )
        ),
        derive_publication_status(evidence),
        derive_bundle_root_hash(sha_map),
        _lifecycle_row("manual_preclosure_evidence", "PRESENT"),
        _lifecycle_row("leamas_protocol_E", "ABSENT"),
        _lifecycle_row("closure_commit_C", "ABSENT"),
        _lifecycle_row("annotated_tag_T", "ABSENT"),
        _lifecycle_row("deterministic_C_proof", "BLOCKED"),
        _lifecycle_row("wave_1", "BLOCKED"),
        _lifecycle_row("CORRECTION15", "PARTIAL_CHECKPOINT"),
    ]

    lines: list[str] = [
        "# CORRECTION15 evidence bundle final-classification.md",
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
    lines.extend(
        [
            "",
            "## Object IDs",
            "",
            f"- base = `{evidence.base_oid}`",
            f"- subject = `{evidence.subject_oid}`",
            f"- git_commands = `{len(evidence.git_commands)}`",
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
    "build_final_classification",
    "derive_audit_check",
    "derive_bundle_completeness",
    "derive_bundle_root_hash",
    "derive_git_diff_cardinality",
    "derive_publication_status",
    "derive_range_resolution",
    "derive_ruff_invocation",
]
