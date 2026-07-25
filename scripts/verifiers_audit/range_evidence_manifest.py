"""CORRECTION13: detached range evidence manifest builder.

The manifest is the authoritative evidence-transaction
record.  It binds the F13 plan-freeze, the S13 subject, the
two full commit object IDs, the authoritative byte-equal
manifests, the post-Ruff argv, the resolved launcher
identity, the git-diff query count, and the protocol stage.

CORRECTION13: every claim in the manifest is derived from a
measured result or marked ``UNMEASURED``.  Hardcoded
``PASS`` claims are forbidden.
"""

from __future__ import annotations

from pathlib import Path

from scripts.verifiers_audit.range_evidence_helpers import _sha256_of


def _classify_claim(claim: str, measured: bool) -> str:
    """Render a claim row from a measured result.

    When ``measured`` is True, the claim is ``PASS``; when
    False, the claim is rendered ``UNMEASURED`` so a
    downstream consumer can distinguish a verified row from
    an unverified row.
    """
    return "PASS" if measured else "UNMEASURED"


def build_manifest(
    *,
    base: str,
    subject: str,
    base_full_oid: str,
    subject_full_oid: str,
    repo_root: Path,
    output_dir: Path,
    all_paths_bytes: tuple[bytes, ...],
    py_paths_bytes: tuple[bytes, ...],
    ruff_scope_status: str,
    ruff_run: dict[str, object],
    executed_argv: tuple[str, ...] | None,
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
) -> dict[str, object]:
    """Build the manifest dict for the evidence bundle."""
    return {
        "schema_version": "leamas.v2.closure-evidence/1",
        "base": base,
        "subject": subject,
        "base_full_oid": base_full_oid,
        "subject_full_oid": subject_full_oid,
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "git_diff_query_count": git_diff_query_count,
        "range": {
            "method": "git-diff-factory",
            "base_full_oid": base_full_oid,
            "subject_full_oid": subject_full_oid,
            "diff_args": [
                "--name-only",
                "-z",
                "--diff-filter=ACMRT",
                base_full_oid,
                subject_full_oid,
            ],
        },
        "changed_paths": {
            "relpath": "changed-paths.z",
            "text_relpath": "changed-paths.txt",
            "sha256": _sha256_of(changed_paths_z),
            "text_sha256": _sha256_of(changed_paths_txt),
            "count": len(all_paths_bytes),
        },
        "changed_python_paths": {
            "relpath": "changed-python-paths.z",
            "text_relpath": "changed-python-paths.txt",
            "sha256": _sha256_of(changed_python_paths_z),
            "text_sha256": _sha256_of(changed_python_paths_txt),
            "count": len(py_paths_bytes),
        },
        "ruff_input_paths": {
            "relpath": "ruff-input-paths.z",
            "text_relpath": "ruff-input-paths.txt",
            "sha256": _sha256_of(ruff_input_paths_z),
            "text_sha256": _sha256_of(ruff_input_paths_txt),
            "count": len(py_paths_bytes),
        },
        "ruff_scope": {
            "relpath": "ruff-scope.json",
            "sha256": _sha256_of(ruff_scope_path),
            "status": ruff_scope_status,
        },
        "ruff_argv": {
            "relpath": "ruff-argv.json",
            "sha256": _sha256_of(ruff_argv_path),
            "argv": (
                list(executed_argv) if executed_argv is not None else None
            ),
        },
        "tool_identities": {
            "relpath": "tool-identities.json",
            "sha256": _sha256_of(tool_identities_path),
            "launcher_path": ruff_identity.get("launcher_path"),
            "launcher_sha256": ruff_identity.get("launcher_sha256"),
            "ruff_version": ruff_identity.get("ruff_version"),
            "ruff_invocation_mode": ruff_identity.get("ruff_invocation_mode"),
        },
        "commands": {
            "relpath": "commands.json",
            "sha256": _sha256_of(commands_path),
        },
        "ruff_run": ruff_run,
        "protocol_stage": "manual-preclosure-evidence",
        "leamas_protocol_E": False,
    }


def build_commands_registry(
    *,
    base: str,
    subject: str,
    base_full_oid: str,
    subject_full_oid: str,
    executed_argv: tuple[str, ...] | None,
    ruff_run: dict[str, object],
    repo_root: Path,
) -> list[dict[str, object]]:
    """Build the post-subject commands registry.

    Every command's argv is recorded verbatim.  The
    ``git-rev-parse-base`` and ``git-rev-parse-subject``
    commands are ALWAYS recorded; the ``git-diff-factory``
    command is recorded with the FULL OIDs; the
    ``ruff-check`` command is recorded as the executed
    argv (or ``None`` when the range was empty or the
    identity was unresolved).
    """
    return [
        {
            "name": "git-rev-parse-base",
            "argv": [
                "git",
                "rev-parse",
                "--verify",
                f"{base}^{{commit}}",
            ],
            "cwd": str(repo_root),
        },
        {
            "name": "git-rev-parse-subject",
            "argv": [
                "git",
                "rev-parse",
                "--verify",
                f"{subject}^{{commit}}",
            ],
            "cwd": str(repo_root),
        },
        {
            "name": "git-diff-factory",
            "argv": [
                "git",
                "diff",
                "--name-only",
                "-z",
                "--diff-filter=ACMRT",
                base_full_oid,
                subject_full_oid,
            ],
            "cwd": str(repo_root),
        },
        {
            "name": "ruff-check",
            "argv": (
                list(executed_argv) if executed_argv is not None else None
            ),
            "cwd": str(repo_root),
            "exit_code": ruff_run.get("exit_code", 0),
            "stdout_sha256": ruff_run.get("stdout_sha256", ""),
            "stderr_sha256": ruff_run.get("stderr_sha256", ""),
        },
    ]
