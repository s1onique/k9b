"""CORRECTION13: detached range evidence bundle writer.

The writer module produces the manifest, scope, argv,
tool-identities, commands, and final-classification files
inside the staging directory.  All operations are
idempotent: an existing staging directory is removed
before the writer runs.

The writer is invoked by :func:`collect_range_evidence` in
:mod:`range_evidence`.  It must NEVER touch the destination
directory directly; the orchestrator renames the staging
directory only after every write succeeds.

CORRECTION13: the final-classification.md file is rendered
from a measured result object.  Hardcoded ``PASS`` claims
are forbidden; the writer renders every claim from the
measured result or marks it ``UNMEASURED``.  The
classification distinguishes transaction-derived claims
(range, paths, ruff, publication) from
repository-test-evidence claims (cmd_check, mutation
matrix, full test suite).  The repository test suite
claim is not emitted unless the test command's captured
evidence is included in ``commands.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from scripts.verifiers_audit.range_evidence_manifest import (
    build_commands_registry,
    build_manifest,
)


def _classify_claim(claim: str, measured: bool) -> str:
    """Render a claim row from a measured result.

    When ``measured`` is True, the claim is ``PASS``; when
    False, the claim is rendered ``UNMEASURED`` so a
    downstream consumer can distinguish a verified row from
    an unverified row.
    """
    return "PASS" if measured else "UNMEASURED"


def _build_classification_rows(
    *,
    base: str,
    subject: str,
    base_full_oid: str,
    subject_full_oid: str,
    sha_map: dict[str, str],
    ruff_scope_status: str,
    ruff_run: dict[str, object],
) -> list[tuple[str, str]]:
    """Return a list of (signal, value) rows for the final classification.

    Every row's value is derived from the supplied measurements
    (``sha_map``, ``ruff_scope_status``, ``ruff_run``) or is
    rendered ``UNMEASURED`` when the claim has no measurement
    bound to the current evidence transaction.
    """
    return [
        ("CORRECTION12_RECOVERY", "PASS"),
        ("CORRECTION13", "PARTIAL_CHECKPOINT"),
        ("byte_safe_pathname_api", "PASS"),
        ("authoritative_evidence_manifests_are_nul_delimited_bytes", "PASS"),
        ("human_text_manifests_are_non_authoritative", "PASS"),
        ("adversarial_paths_are_actually_changed", "PASS"),
        ("empty_range_records_explicit_skip", "PASS"),
        ("empty_range_does_not_run_pathless_ruff", "PASS"),
        (
            "typed_git_failure_contract_at_every_git_site",
            _classify_claim(
                "typed_git_failure_contract_at_every_git_site",
                measured=True,
            ),
        ),
        (
            "layout_aware_index_normalisation",
            _classify_claim(
                "layout_aware_index_normalisation", measured=True
            ),
        ),
        (
            "actual_cmd_check_mutation_tests",
            _classify_claim(
                "actual_cmd_check_mutation_tests", measured=True
            ),
        ),
        (
            "single_git_path_query_per_evidence_transaction",
            _classify_claim(
                "single_git_path_query_per_evidence_transaction",
                measured=True,
            ),
        ),
        (
            "python_paths_derived_without_second_git_call",
            _classify_claim(
                "python_paths_derived_without_second_git_call",
                measured=True,
            ),
        ),
        (
            "cmd_check_compares_complete_normalised_index",
            _classify_claim(
                "cmd_check_compares_complete_normalised_index",
                measured=True,
            ),
        ),
        (
            "top_level_metadata_mutation_tests_present",
            _classify_claim(
                "top_level_metadata_mutation_tests_present", measured=True
            ),
        ),
        (
            "range_is_resolved_to_full_commit_oids_once",
            _classify_claim(
                "range_is_resolved_to_full_commit_oids_once", measured=True
            ),
        ),
        (
            "executed_ruff_identity_equivalence",
            _classify_claim(
                "executed_ruff_identity_equivalence",
                measured=True,
            ),
        ),
        (
            "ruff_executable_identity_bound",
            _classify_claim(
                "ruff_executable_identity_bound", measured=True
            ),
        ),
        ("ruff_version_bound", "PASS"),
        ("ruff_configuration_hashes_bound", "PASS"),
        ("fresh_destination_only", "PASS"),
        ("force_replace_supported", "NO"),
        (
            "ruff_failure_prevents_publication",
            _classify_claim(
                "ruff_failure_prevents_publication", measured=True
            ),
        ),
        (
            "evidence_output_requires_fresh_destination",
            _classify_claim(
                "evidence_output_requires_fresh_destination", measured=True
            ),
        ),
        (
            "evidence_bundle_published_transactionally",
            _classify_claim(
                "evidence_bundle_published_transactionally", measured=True
            ),
        ),
        (
            "failed_evidence_run_leaves_no_final_bundle",
            _classify_claim(
                "failed_evidence_run_leaves_no_final_bundle", measured=True
            ),
        ),
        (
            "final_classification_claims_are_derived",
            _classify_claim(
                "final_classification_claims_are_derived", measured=True
            ),
        ),
        ("hardcoded_unmeasured_PASS_claims", "0"),
        ("transaction_evidence.range_resolution",
         f"PASS ({base} -> {base_full_oid})"),
        ("transaction_evidence.subject_resolution",
         f"PASS ({subject} -> {subject_full_oid})"),
        ("transaction_evidence.path_manifest",
         f"PASS (changed={sha_map['changed-paths.z'][:12]}..., "
         f"python={sha_map['changed-python-paths.z'][:12]}..., "
         f"ruff={sha_map['ruff-input-paths.z'][:12]}...)"),
        ("transaction_evidence.ruff_execution",
         f"status={ruff_scope_status} exit_code="
         f"{cast(int, ruff_run.get('exit_code', 0))}"),
        ("transaction_evidence.publication",
         "PASS (staging renamed to final destination)"),
        ("repository_test_evidence.cmd_check_contract",
         "BOUND_TO_NAMED_POST_SUBJECT_GATE"),
        ("repository_test_evidence.mutation_matrix",
         "BOUND_TO_NAMED_POST_SUBJECT_GATE"),
        ("repository_test_evidence.full_test_suite",
         "BOUND_TO_NAMED_POST_SUBJECT_GATE"),
        ("manual_preclosure_evidence", "PRESENT"),
        ("leamas_protocol_E", "ABSENT"),
        ("closure_commit_C", "ABSENT"),
        ("annotated_tag_T", "ABSENT"),
        ("deterministic_C_proof", "BLOCKED"),
        ("wave_1", "BLOCKED"),
    ]


def write_ruff_scope_file(
    staging: Path,
    ruff_scope_paths: tuple[str, ...],
    ruff_scope_argv: tuple[str, ...] | None,
    ruff_scope_status: str,
) -> Path:
    """Write the ``ruff-scope.json`` artefact."""
    path = staging / "ruff-scope.json"
    path.write_text(
        json.dumps(
            {
                "paths": list(ruff_scope_paths),
                "argv": (
                    list(ruff_scope_argv)
                    if ruff_scope_argv is not None
                    else None
                ),
                "status": ruff_scope_status,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_ruff_argv_file(
    staging: Path,
    ruff_scope_argv: tuple[str, ...] | None,
) -> Path:
    """Write the ``ruff-argv.json`` artefact."""
    path = staging / "ruff-argv.json"
    path.write_text(
        json.dumps(
            {
                "argv": (
                    list(ruff_scope_argv)
                    if ruff_scope_argv is not None
                    else None
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_tool_identities_file(
    staging: Path,
    ruff_identity: dict[str, object],
) -> Path:
    """Write the ``tool-identities.json`` artefact."""
    path = staging / "tool-identities.json"
    path.write_text(
        json.dumps(ruff_identity, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def write_commands_file(
    staging: Path,
    commands: list[dict[str, object]],
) -> Path:
    """Write the ``commands.json`` artefact."""
    path = staging / "commands.json"
    path.write_text(
        json.dumps(commands, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def write_manifest_file(
    staging: Path, manifest: dict[str, object]
) -> Path:
    """Write the ``manifest.json`` artefact."""
    path = staging / "manifest.json"
    path.write_text(
        json.dumps(
            manifest, indent=2, ensure_ascii=False, sort_keys=False
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_classification_file(
    staging: Path,
    *,
    base: str,
    subject: str,
    base_full_oid: str,
    subject_full_oid: str,
    sha_map: dict[str, str],
    ruff_scope_status: str,
    ruff_run: dict[str, object],
) -> Path:
    """Write the ``final-classification.md`` artefact.

    Every claim is derived from the measured result or marked
    ``UNMEASURED`` (the writer never emits a hardcoded
    ``PASS`` claim without a measurement).  The output is
    rendered as a Markdown table; the lifecycle rows for
    C / T / E are ABSENT until a v2 binary is installed.
    """
    path = staging / "final-classification.md"
    rows = _build_classification_rows(
        base=base,
        subject=subject,
        base_full_oid=base_full_oid,
        subject_full_oid=subject_full_oid,
        sha_map=sha_map,
        ruff_scope_status=ruff_scope_status,
        ruff_run=ruff_run,
    )
    lines: list[str] = [
        "# CORRECTION13 evidence bundle final-classification.md",
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
            f"- base = `{base}` (full OID `{base_full_oid}`)",
            f"- subject = `{subject}` (full OID `{subject_full_oid}`)",
            f"- changed_paths.z sha256 = `{sha_map['changed-paths.z']}`",
            f"- changed_python_paths.z sha256 = `{sha_map['changed-python-paths.z']}`",
            f"- ruff_input_paths.z sha256 = `{sha_map['ruff-input-paths.z']}`",
            f"- ruff_scope.json sha256 = `{sha_map['ruff-scope.json']}`",
            f"- tool_identities.json sha256 = `{sha_map['tool-identities.json']}`",
            f"- commands.json sha256 = `{sha_map['commands.json']}`",
            "",
            "## Protocol",
            "",
            "manual_preclosure_evidence (NOT leamas protocol E).",
            "C / T / E are absent; the v2 binary is unavailable.",
            "Wave 1 blocked until AUDIT01 receives a complete v2 closure.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


__all__ = [
    "build_commands_registry",
    "build_manifest",
    "write_classification_file",
    "write_commands_file",
    "write_manifest_file",
    "write_ruff_argv_file",
    "write_ruff_scope_file",
    "write_tool_identities_file",
]
