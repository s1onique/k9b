"""CORRECTION14/CORRECTION15: detached range evidence manifest + topology
builders.

The functions in this module are extracted from
:mod:`range_evidence_writer` to keep both modules under the
500-line LLM-friendly threshold.  They accept typed
:class:`EvidenceTransactionResult` /
:class:`ClosureTopology` arguments and return dicts that the
file-writer layer serialises to disk.

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
    topology: ClosureTopology,
    base_full_oid: str,
    subject_full_oid: str,
    git_diff_query_count: int,
    rescue_branches: tuple[str, ...] = (),
) -> str:
    """Build the ``topology.txt`` text content.

    The text records:

    * F15, F15_tree, plan_blob;
    * S15, S15_tree (when present);
    * parent_F15, parent_S15;
    * base_full_oid, subject_full_oid;
    * git_diff_query_count;
    * rescue_branches.
    """
    lines: list[str] = [
        "CORRECTION15 topology.txt",
        "",
        "## Plan-freeze commit",
        "",
        f"F15 = {topology.F15}",
        f"F15_tree = {topology.F15_tree}",
        f"plan_blob = {topology.plan_blob}",
        f"parent_F15 = {topology.parent_F15}",
    ]
    if topology.S15 is not None:
        lines.extend(
            [
                "",
                "## Subject commit",
                "",
                f"S15 = {topology.S15}",
                f"S15_tree = {topology.S15_tree or '(unknown)'}",
                f"parent_S15 = {topology.parent_S15 or '(unknown)'}",
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
    ruff_scope_path: Path,
    ruff_argv_path: Path,
    tool_identities_path: Path,
    commands_path: Path,
    topology_path: Path,
    gate_path: Path,
) -> dict[str, object]:
    """Build the manifest dict from the typed evidence result.

    CORRECTION15: the manifest records the
    ``publication_state`` of the staged bundle as
    ``READY_TO_PUBLISH``; the rename to the final
    destination records the manual publication result in a
    separate transcript outside the bundle.  The
    ``staging_root`` / ``output_dir`` / temporary absolute
    paths are NEVER recorded.
    """
    authoritative = evidence.authoritative_hashes
    return {
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
        "protocol_stage": "manual-preclosure-evidence",
        "leamas_protocol_E": False,
        "publication_state": (
            "READY_TO_PUBLISH"
            if evidence.publication_status == "ready_to_publish"
            else evidence.publication_status.upper()
        ),
        "publication_status": evidence.publication_status,
    }


__all__ = [
    "build_manifest_from_evidence",
    "build_topology",
]
