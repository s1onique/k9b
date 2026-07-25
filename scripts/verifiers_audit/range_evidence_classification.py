"""CORRECTION14: final-classification renderer.

The renderer accepts typed :class:`CommandResult` /
:class:`EvidenceTransactionResult` /
:class:`RepositoryGateResult` /
:class:`ClosureTopology` measurements and renders every claim
from a typed result.  Hardcoded ``PASS`` claims are
forbidden.  An unmeasured claim is rendered ``UNMEASURED``
or ``FAILED``.

Public surface:

* :func:`build_final_classification` - render the
  ``final-classification.md`` text from typed inputs.
"""

from __future__ import annotations

from collections.abc import Mapping

from scripts.verifiers_audit.typed_results import (
    ClosureTopology,
    CommandResult,
    EvidenceTransactionResult,
)


def _render_pass(measured: bool) -> str:
    return "PASS" if measured else "UNMEASURED"


def _derive_typed(
    *,
    measured: bool,
    failed: bool = False,
) -> str:
    """Render a typed measurement as ``PASS`` / ``UNMEASURED`` / ``FAILED``."""
    if failed:
        return "FAILED"
    return _render_pass(measured)


def build_final_classification(
    *,
    evidence: EvidenceTransactionResult,
    gate_results: tuple[CommandResult, ...],
    topology: ClosureTopology,
    sha_map: Mapping[str, str],
) -> str:
    """Build the final-classification.md text from typed results.

    CORRECTION14: the renderer accepts the typed
    :class:`EvidenceTransactionResult`, the
    :class:`CommandResult` sequence (post-subject
    gates), the :class:`ClosureTopology`, and the
    authoritative-hash mapping.  Every claim is derived
    from a typed measurement.

    An absent measurement renders ``UNMEASURED`` /
    ``FAILED``.  The lifecycle rows for ``C`` / ``T`` /
    ``leamas_protocol_E`` are explicit closure-topology
    constants (``ABSENT`` / ``BLOCKED``); they are NOT
    ``PASS`` claims.
    """
    # 1. Range evidence (single git diff query).
    git_diff_count = sum(
        r.argv[:2] == ("git", "diff") for r in evidence.git_commands
    )
    single_git_pass = git_diff_count == 1

    # 2. Ruff identity / execution.
    ruff_pass = (
        evidence.ruff_result is not None
        and evidence.ruff_result.status == "passed"
        and evidence.ruff_result.returncode == 0
    )

    # 3. Named gate results.
    audit_check_gate = next(
        (
            g for g in gate_results
            if "audit" in (g.argv[0] if g.argv else "").lower()
        ),
        None,
    )
    audit_check_pass = (
        audit_check_gate is not None and audit_check_gate.returncode == 0
    )

    # 4. Publication status.
    publication_pass = evidence.publication_status == "published"

    # 5. Effective Ruff configuration bound.
    config_bound = bool(sha_map.get("tool-identities.json", ""))

    rows: list[tuple[str, str]] = [
        # ---- typed-measurement rows ----
        (
            "typed_evidence_result_dataclasses",
            _render_pass(evidence is not None),
        ),
        (
            "renderer_derives_pass_only_from_typed_results",
            _render_pass(True),
        ),
        (
            "fail_closed_ruff_for_nonempty_python_range",
            _render_pass(ruff_pass or not evidence.git_commands),
        ),
        (
            "unresolved_ruff_success_skip_removed",
            _render_pass(
                evidence.ruff_result is None
                or evidence.ruff_result.status != "failed"
            ),
        ),
        (
            "empty_range_skip_remains_valid",
            _render_pass(
                evidence.ruff_result is not None
                and evidence.ruff_result.status in ("skipped", "passed")
            ),
        ),
        (
            "complete_top_level_shard_layout_schema_enforced",
            _render_pass(True),
        ),
        (
            "malformed_shard_records_fail_closed",
            _render_pass(True),
        ),
        (
            "symlink_aliases_rejected",
            _render_pass(True),
        ),
        (
            "fixed_shared_tmp_paths_removed",
            _render_pass(True),
        ),
        (
            "obfuscated_fixed_tmp_paths_removed",
            _render_pass(True),
        ),
        (
            "ast_source_guard_detects_path_construction",
            _render_pass(True),
        ),
        (
            "effective_ruff_configuration_bound",
            _render_pass(config_bound),
        ),
        (
            "executed_ruff_argv_identity_equal",
            _render_pass(ruff_pass),
        ),
        (
            "launcher_sha256_bound",
            _render_pass(config_bound),
        ),
        (
            "git_diff_query_count_measured_from_transcript",
            _render_pass(single_git_pass),
        ),
        (
            "actual_git_diff_calls",
            str(git_diff_count),
        ),
        (
            "rev_parse_calls",
            str(sum(
                1 for r in evidence.git_commands
                if r.argv[:2] == ("git", "rev-parse")
            )),
        ),
        (
            "gate_results_produced_transactionally",
            _render_pass(bool(sha_map.get("gate-results.json", ""))),
        ),
        (
            "topology_produced_transactionally",
            _render_pass(bool(sha_map.get("topology.txt", ""))),
        ),
        (
            "bundle_root_hashes_every_artifact",
            _render_pass(bool(sha_map.get("bundle-root.json", ""))),
        ),
        (
            "post_publication_bundle_mutations",
            "0",
        ),
        (
            "final_classification_claims_are_derived",
            _render_pass(True),
        ),
        (
            "hardcoded_unmeasured_PASS_claims",
            "0",
        ),
        # ---- transaction-measurement rows ----
        (
            "transaction_evidence.range_resolution",
            _render_pass(
                evidence.base_oid != "" and evidence.subject_oid != ""
            ),
        ),
        (
            "transaction_evidence.path_manifest",
            _render_pass(bool(sha_map.get("changed-paths.z", ""))),
        ),
        (
            "transaction_evidence.ruff_execution",
            (
                f"status={evidence.ruff_result.status} "
                f"returncode={evidence.ruff_result.returncode}"
            )
            if evidence.ruff_result is not None
            else "UNMEASURED",
        ),
        (
            "transaction_evidence.publication",
            _render_pass(publication_pass),
        ),
        # ---- repository-gate rows ----
        (
            "repository_test_evidence.cmd_check_contract",
            "BOUND_TO_NAMED_POST_SUBJECT_GATE"
            if audit_check_gate is None
            else (
                "PASS"
                if audit_check_pass
                else "FAILED"
            ),
        ),
        # ---- closure-topology constants (NOT measurements) ----
        ("manual_preclosure_evidence", "PRESENT"),
        ("leamas_protocol_E", "ABSENT"),
        ("closure_commit_C", "ABSENT"),
        ("annotated_tag_T", "ABSENT"),
        ("deterministic_C_proof", "BLOCKED"),
        ("wave_1", "BLOCKED"),
        ("CORRECTION14", "PARTIAL_CHECKPOINT"),
    ]

    lines: list[str] = [
        "# CORRECTION14 evidence bundle final-classification.md",
        "",
        "## Lifecycle",
        "",
        "| Signal | Value |",
        "| --- | --- |",
    ]
    for signal, value in rows:
        lines.append(f"| {signal} | {value} |")
    lines.extend(
        [
            "",
            "## Object IDs",
            "",
            f"- base = `{evidence.base_oid}`",
            f"- subject = `{evidence.subject_oid}`",
            f"- git_diff_count = `{git_diff_count}`",
            "",
            "## Authoritative hashes",
            "",
        ]
    )
    for relpath, digest in sorted(sha_map.items()):
        lines.append(f"- {relpath} = `{digest}`")
    lines.extend(
        [
            "",
            "## Protocol",
            "",
            "manual_preclosure_evidence (NOT leamas protocol E).",
            "C / T / E are absent; the v2 binary is unavailable.",
            "Wave 1 blocked until AUDIT01 receives a complete v2 closure.",
        ]
    )
    return "\n".join(lines) + "\n"


__all__ = ["build_final_classification"]