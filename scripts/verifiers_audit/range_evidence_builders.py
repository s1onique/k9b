"""CORRECTION14: detached range evidence manifest + topology + bundle-root
builders.

The functions in this module are extracted from
:mod:`range_evidence_writer` to keep both modules under the
500-line LLM-friendly threshold.  They accept typed
:class:`EvidenceTransactionResult` /
:class:`ClosureTopology` arguments and return dicts that the
file-writer layer serialises to disk.
"""

from __future__ import annotations

from collections.abc import Mapping
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
    """Build the topology.txt text content.

    The text records:

    * F14, F14_tree, plan_blob;
    * S14, S14_tree (when present);
    * parent_F14, parent_S14;
    * base_full_oid, subject_full_oid;
    * git_diff_query_count;
    * rescue_branches.
    """
    lines: list[str] = [
        "CORRECTION14 topology.txt",
        "",
        "## Plan-freeze commit",
        "",
        f"F14 = {topology.F14}",
        f"F14_tree = {topology.F14_tree}",
        f"plan_blob = {topology.plan_blob}",
        f"parent_F14 = {topology.parent_F14}",
    ]
    if topology.S14 is not None:
        lines.extend(
            [
                "",
                "## Subject commit",
                "",
                f"S14 = {topology.S14}",
                f"S14_tree = {topology.S14_tree or '(unknown)'}",
                f"parent_S14 = {topology.parent_S14 or '(unknown)'}",
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
    output_dir: Path,
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

    CORRECTION14: every required artifact hash is bound from
    ``authoritative_hashes`` so the manifest is consistent
    with the on-disk files.
    """
    authoritative = evidence.authoritative_hashes
    return {
        "schema_version": "leamas.v2.closure-evidence/2",
        "base": base,
        "subject": subject,
        "base_full_oid": evidence.base_oid,
        "subject_full_oid": evidence.subject_oid,
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
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
        "publication_status": evidence.publication_status,
    }


def build_bundle_root(
    *,
    topology: ClosureTopology,
    staging: Path,
    authoritative_hashes: Mapping[str, str],
) -> dict[str, object]:
    """Build the bundle-root.json dict.

    The bundle-root hashes every other final artifact and
    binds F14, F14_tree, plan_blob, S14, S14_tree,
    parent_F14, parent_S14, files (relpath -> sha256).
    The hashes in ``files`` are taken from
    ``authoritative_hashes`` so the bundle-root is
    consistent with the on-disk files at publication time.
    """
    return {
        "schema_version": "leamas.v2.bundle-root/1",
        "F14": topology.F14,
        "F14_tree": topology.F14_tree,
        "plan_blob": topology.plan_blob,
        "S14": topology.S14,
        "S14_tree": topology.S14_tree,
        "parent_F14": topology.parent_F14,
        "parent_S14": topology.parent_S14,
        "staging_root": str(staging),
        "files": dict(authoritative_hashes),
    }


__all__ = [
    "build_bundle_root",
    "build_manifest_from_evidence",
    "build_topology",
]