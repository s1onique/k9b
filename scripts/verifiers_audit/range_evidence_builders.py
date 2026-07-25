"""CORRECTION14/CORRECTION15/CORRECTION16: detached range evidence manifest + topology
builders.

The functions in this module are extracted from
:mod:`range_evidence_writer` to keep both modules under the
500-line LLM-friendly threshold.  They accept typed
:class:`EvidenceTransactionResult` /
:class:`ClosureTopology` arguments and return dicts that the
file-writer layer serialises to disk.

CORRECTION16: the ``build_topology`` function accepts the
transaction-derived topology record (when the closure
topology is not yet produced by the orchestrator).  The
``build_manifest_from_evidence`` function adds the
``pytest-input-paths.z`` / ``mypy-input-paths.z`` /
respective ``.txt`` projections to the manifest.

The bundle-root builder lives in
:mod:`range_evidence_bundle`; this module owns only the
``manifest.json`` and ``topology.txt`` builders so the
bundle module's strict directory enumeration remains
isolated.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from pathlib import Path

from scripts.verifiers_audit.range_evidence_helpers import _sha256_of
from scripts.verifiers_audit.typed_results import (
    ClosureTopology,
    EvidenceTransactionResult,
)


def build_topology(
    *,
    topology: ClosureTopology | None,
    base_full_oid: str,
    subject_full_oid: str,
    git_diff_query_count: int,
    rescue_branches: tuple[str, ...] = (),
    f16_full_oid: str | None = None,
    f16_tree: str | None = None,
    plan_blob: str | None = None,
    s16_full_oid: str | None = None,
    s16_tree: str | None = None,
    parent_f16: str | None = None,
    parent_s16: str | None = None,
    plan_path: str | None = None,
) -> str:
    """Build the ``topology.txt`` text content.

    The text records F16 / S16 / parent_F16 / parent_S16 /
    plan_blob.  When ``topology`` is supplied the legacy
    fields are used; otherwise the individual CORRECTION16
    fields are emitted.  The recorded fields are the
    transcript-derived values, NOT the caller-supplied
    environment identities.
    """
    lines: list[str] = ["CORRECTION16 topology.txt", ""]

    if topology is not None:
        # Use the legacy closure topology record.
        lines.extend(
            [
                "## Plan-freeze commit",
                "",
                f"F16 = {topology.F16}",
                f"F16_tree = {topology.F16_tree}",
                f"plan_blob = {topology.plan_blob}",
                f"parent_F16 = {topology.parent_F16}",
            ]
        )
        if topology.S16 is not None:
            lines.extend(
                [
                    "",
                    "## Subject commit",
                    "",
                    f"S16 = {topology.S16}",
                    f"S16_tree = {topology.S16_tree or '(unknown)'}",
                    f"parent_S16 = {topology.parent_S16 or '(unknown)'}",
                ]
            )
    else:
        # Use the CORRECTION16 transactional fields.
        lines.extend(
            [
                "## Plan-freeze commit",
                "",
                f"F16 = {f16_full_oid or ''}",
                f"F16_tree = {f16_tree or ''}",
                f"plan_blob = {plan_blob or ''}",
                f"parent_F16 = {parent_f16 or ''}",
                f"plan_path = {plan_path or ''}",
                "",
                "## Subject commit",
                "",
                f"S16 = {s16_full_oid or ''}",
                f"S16_tree = {s16_tree or ''}",
                f"parent_S16 = {parent_s16 or ''}",
            ]
        )

    lines.extend(
        [
            "",
            "## Evidence transaction",
            "",
            f"base_full_oid = {base_full_oid}",
            f"subject_full_oid = {subject_full_oid}",
            f"git_diff_query_count = {git_diff_query_count}",
            "",
            "## Rescue branches",
            "",
        ]
    )
    for branch in rescue_branches:
        lines.append(f"- {branch}")
    if not rescue_branches:
        lines.append("- (none recorded)")
    return "\n".join(lines) + "\n"


def build_manifest_from_evidence(
    *,
    evidence: EvidenceTransactionResult,
    base: str,
    subject: str,
    repo_root: Path,
    all_paths_bytes: tuple[bytes, ...],
    py_paths_bytes: tuple[bytes, ...],
    ruff_scope_status: str,
    ruff_identity: dict[str, object],
    git_diff_query_count: int,
    changed_paths_z: Path,
    changed_paths_txt: Path,
    changed_python_paths_z: Path,
    changed_python_paths_txt: Path,
    ruff_input_paths_z: Path,
    ruff_input_paths_txt: Path,
    pytest_input_paths_z: Path | None = None,
    pytest_input_paths_txt: Path | None = None,
    mypy_input_paths_z: Path | None = None,
    mypy_input_paths_txt: Path | None = None,
    ruff_scope_path: Path,
    ruff_argv_path: Path,
    tool_identities_path: Path,
    commands_path: Path,
    topology_path: Path,
    gate_path: Path,
) -> dict[str, object]:
    """Build the manifest dict from the typed evidence result.

    CORRECTION16: ``pytest_input_paths_z`` /
    ``pytest_input_paths_txt`` / ``mypy_input_paths_z`` /
    ``mypy_input_paths_txt`` are CORRECTION16 artifacts; the
    ``publication_state`` field is the typed
    ``evidence.publication_status``.
    """
    authoritative = evidence.authoritative_hashes
    manifest: dict[str, object] = {
        "schema_version": "leamas.v2.closure-evidence/2",
        "base": base,
        "subject": subject,
        "base_full_oid": evidence.base_oid,
        "subject_full_oid": evidence.subject_oid,
        "repo_root": str(repo_root),
        "git_diff_query_count": git_diff_query_count,
        "range": {
            "method": "git-diff-factory",
            "base_full_oid": evidence.base_oid,
            "subject_full_oid": evidence.subject_oid,
            "diff_args": [
                "--name-only",
                "-z",
                "--diff-filter=ACMRT",
                evidence.base_oid,
                evidence.subject_oid,
            ],
        },
        "changed_paths": {
            "relpath": "changed-paths.z",
            "text_relpath": "changed-paths.txt",
            "sha256": _sha256_of(changed_paths_z),
            "text_sha256": _sha256_of(changed_paths_txt),
            "count": len(all_paths_bytes),
            "authoritative_sha256": authoritative.get(
                "changed-paths.z", ""
            ),
        },
        "changed_python_paths": {
            "relpath": "changed-python-paths.z",
            "text_relpath": "changed-python-paths.txt",
            "sha256": _sha256_of(changed_python_paths_z),
            "text_sha256": _sha256_of(changed_python_paths_txt),
            "count": len(py_paths_bytes),
            "authoritative_sha256": authoritative.get(
                "changed-python-paths.z", ""
            ),
        },
        "ruff_input_paths": {
            "relpath": "ruff-input-paths.z",
            "text_relpath": "ruff-input-paths.txt",
            "sha256": _sha256_of(ruff_input_paths_z),
            "text_sha256": _sha256_of(ruff_input_paths_txt),
            "count": len(py_paths_bytes),
            "authoritative_sha256": authoritative.get(
                "ruff-input-paths.z", ""
            ),
        },
        "ruff_scope": {
            "relpath": "ruff-scope.json",
            "sha256": _sha256_of(ruff_scope_path),
            "status": ruff_scope_status,
            "authoritative_sha256": authoritative.get("ruff-scope.json", ""),
        },
        "ruff_argv": {
            "relpath": "ruff-argv.json",
            "sha256": _sha256_of(ruff_argv_path),
            "argv": list(evidence.ruff_result.argv) if evidence.ruff_result else None,
            "authoritative_sha256": authoritative.get("ruff-argv.json", ""),
        },
        "tool_identities": {
            "relpath": "tool-identities.json",
            "sha256": _sha256_of(tool_identities_path),
            "launcher_path": ruff_identity.get("launcher_path"),
            "launcher_sha256": ruff_identity.get("launcher_sha256"),
            "ruff_version": ruff_identity.get("ruff_version"),
            "ruff_invocation_mode": ruff_identity.get("ruff_invocation_mode"),
            "config_path": ruff_identity.get("config_path"),
            "config_sha256": ruff_identity.get("config_sha256"),
            "extended_config_chain": ruff_identity.get("extended_config_chain"),
            "authoritative_sha256": authoritative.get(
                "tool-identities.json", ""
            ),
        },
        "commands": {
            "relpath": "commands.json",
            "sha256": _sha256_of(commands_path),
            "authoritative_sha256": authoritative.get("commands.json", ""),
        },
        "topology": {
            "relpath": "topology.txt",
            "sha256": _sha256_of(topology_path),
            "authoritative_sha256": authoritative.get("topology.txt", ""),
        },
        "gate_results": {
            "relpath": "gate-results.json",
            "sha256": _sha256_of(gate_path),
            "authoritative_sha256": authoritative.get("gate-results.json", ""),
        },
        "ruff_run": (
            {
                "argv": list(evidence.ruff_result.argv),
                "returncode": evidence.ruff_result.returncode,
                "stdout_sha256": evidence.ruff_result.stdout_sha256,
                "stderr_sha256": evidence.ruff_result.stderr_sha256,
                "status": evidence.ruff_result.status,
            }
            if evidence.ruff_result is not None
            else None
        ),
        "transaction_summary": {
            "topology_git_commands": evidence.transaction_summary.topology_git_commands,
            "range_git_commands": evidence.transaction_summary.range_git_commands,
            "gate_git_commands": evidence.transaction_summary.gate_git_commands,
            "total_git_commands": evidence.transaction_summary.total_git_commands,
            "unrecorded_git_commands": evidence.transaction_summary.unrecorded_git_commands,
            "hidden_shell_git_invocations": evidence.transaction_summary.hidden_shell_git_invocations,
        },
        "repository_topology": {
            "F16": evidence.repository_topology.F16,
            "F16_tree": evidence.repository_topology.F16_tree,
            "plan_blob": evidence.repository_topology.plan_blob,
            "S16": evidence.repository_topology.S16,
            "S16_tree": evidence.repository_topology.S16_tree,
            "parent_F16": evidence.repository_topology.parent_F16,
            "parent_S16": evidence.repository_topology.parent_S16,
            "plan_path": evidence.repository_topology.plan_path,
        },
        "ruff_equivalence": {
            "explicit_returncode": evidence.ruff_equivalence.explicit_returncode,
            "canonical_returncode": evidence.ruff_equivalence.canonical_returncode,
            "explicit_diagnostics_sha256": evidence.ruff_equivalence.explicit_diagnostics_sha256,
            "canonical_diagnostics_sha256": evidence.ruff_equivalence.canonical_diagnostics_sha256,
            "ruff_version": evidence.ruff_equivalence.ruff_version,
            "input_path_tuple_sha256": evidence.ruff_equivalence.input_path_tuple_sha256,
            "config_path": evidence.ruff_equivalence.config_path,
            "config_sha256": evidence.ruff_equivalence.config_sha256,
            "equivalent": evidence.ruff_equivalence.equivalent,
        },
        "all_gates_pass": evidence.all_gates_pass,
        "protocol_stage": "manual-preclosure-evidence",
        "leamas_protocol_E": False,
        "publication_state": (
            "READY_TO_PUBLISH"
            if evidence.publication_status == "ready_to_publish"
            else evidence.publication_status.upper()
        ),
        "publication_status": evidence.publication_status,
    }
    if (
        pytest_input_paths_z is not None
        and pytest_input_paths_txt is not None
    ):
        manifest["pytest_input_paths"] = {
            "relpath": "pytest-input-paths.z",
            "text_relpath": "pytest-input-paths.txt",
            "sha256": _sha256_of(pytest_input_paths_z),
            "text_sha256": _sha256_of(pytest_input_paths_txt),
            "count": len(py_paths_bytes),
            "authoritative_sha256": authoritative.get(
                "pytest-input-paths.z", ""
            ),
        }
    if (
        mypy_input_paths_z is not None
        and mypy_input_paths_txt is not None
    ):
        manifest["mypy_input_paths"] = {
            "relpath": "mypy-input-paths.z",
            "text_relpath": "mypy-input-paths.txt",
            "sha256": _sha256_of(mypy_input_paths_z),
            "text_sha256": _sha256_of(mypy_input_paths_txt),
            "count": len(py_paths_bytes),
            "authoritative_sha256": authoritative.get(
                "mypy-input-paths.z", ""
            ),
        }
    return manifest


__all__ = [
    "build_manifest_from_evidence",
    "build_topology",
]
