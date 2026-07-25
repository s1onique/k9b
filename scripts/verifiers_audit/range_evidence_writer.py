"""CORRECTION13/CORRECTION14/CORRECTION15: detached range evidence bundle writer.

The writer module owns the file-writer layer:

* :func:`build_commands_registry` - the ``commands.json`` builder.
* :func:`write_ruff_scope_file` - the ``ruff-scope.json`` writer.
* :func:`write_ruff_argv_file` - the ``ruff-argv.json`` writer.
* :func:`write_tool_identities_file` - the
  ``tool-identities.json`` writer.
* :func:`write_commands_file` - the ``commands.json`` writer.
* :func:`write_manifest_file` - the ``manifest.json`` writer.
* :func:`write_topology_file` - the ``topology.txt`` writer.
* :func:`write_gate_results_file` - the
  ``gate-results.json`` writer (CORRECTION15: gates
  use the closed semantic ``RepositoryGateName`` ``Literal``).
* :func:`write_classification_file` - the
  ``final-classification.md`` writer.

The manifest / topology / bundle-root builders live in
:mod:`range_evidence_builders` and :mod:`range_evidence_bundle`;
the typed result dataclasses live in :mod:`typed_results`;
the final-classification renderer lives in
:mod:`range_evidence_classification`.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment"
import json
from pathlib import Path

from scripts.verifiers_audit.typed_results import (
    ExecutedCommand,
    RepositoryGateResult,
)


def build_commands_registry(
    *,
    base: str,
    subject: str,
    base_full_oid: str,
    subject_full_oid: str,
    git_commands: tuple[ExecutedCommand, ...],
    ruff_result: ExecutedCommand | None,
    repo_root: Path,
) -> list[dict[str, object]]:
    """Build the post-subject commands registry.

    Every command's argv is recorded verbatim.  The
    ``git-rev-parse-base`` and ``git-rev-parse-subject``
    commands are ALWAYS recorded; the ``git-diff-factory``
    command is recorded with the FULL OIDs; the
    ``ruff-check`` command is recorded as the executed
    argv (or absent when the range was empty or the
    identity was unresolved).
    """
    commands: list[dict[str, object]] = [
        {
            "name": "git-rev-parse-base",
            "argv": (
                list(git_commands[0].argv) if git_commands
                else [
                    "git", "rev-parse", "--verify",
                    f"{base}^{{commit}}",
                ]
            ),
            "cwd": str(repo_root),
            "exit_code": git_commands[0].returncode if git_commands else -1,
            "stdout_sha256": (
                git_commands[0].stdout_sha256 if git_commands else ""
            ),
            "stderr_sha256": (
                git_commands[0].stderr_sha256 if git_commands else ""
            ),
            "status": git_commands[0].status if git_commands else "failed",
        },
        {
            "name": "git-rev-parse-subject",
            "argv": (
                list(git_commands[1].argv) if len(git_commands) > 1
                else [
                    "git", "rev-parse", "--verify",
                    f"{subject}^{{commit}}",
                ]
            ),
            "cwd": str(repo_root),
            "exit_code": (
                git_commands[1].returncode if len(git_commands) > 1 else -1
            ),
            "stdout_sha256": (
                git_commands[1].stdout_sha256
                if len(git_commands) > 1
                else ""
            ),
            "stderr_sha256": (
                git_commands[1].stderr_sha256
                if len(git_commands) > 1
                else ""
            ),
            "status": (
                git_commands[1].status if len(git_commands) > 1 else "failed"
            ),
        },
    ]
    if len(git_commands) > 2:
        diff = git_commands[2]
        commands.append(
            {
                "name": "git-diff-factory",
                "argv": list(diff.argv),
                "cwd": str(repo_root),
                "exit_code": diff.returncode,
                "stdout_sha256": diff.stdout_sha256,
                "stderr_sha256": diff.stderr_sha256,
                "status": diff.status,
            }
        )
    if ruff_result is not None:
        commands.append(
            {
                "name": "ruff-check",
                "argv": list(ruff_result.argv),
                "cwd": str(repo_root),
                "exit_code": ruff_result.returncode,
                "stdout_sha256": ruff_result.stdout_sha256,
                "stderr_sha256": ruff_result.stderr_sha256,
                "status": ruff_result.status,
            }
        )
    return commands


# ---------------------------------------------------------------------------
# File writers.
# ---------------------------------------------------------------------------


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


def write_topology_file(staging: Path, text: str) -> Path:
    """Write the ``topology.txt`` artefact."""
    path = staging / "topology.txt"
    path.write_text(text, encoding="utf-8")
    return path


def write_gate_results_file(
    staging: Path,
    gate_results: tuple[RepositoryGateResult, ...],
) -> Path:
    """Write the ``gate-results.json`` artefact.

    CORRECTION15: every gate row records the closed
    semantic ``name`` (the :class:`RepositoryGateName`
    ``Literal``) and the full underlying
    :class:`ExecutedCommand` (argv, cwd, returncode,
    stdout/stderr SHA-256, status).  The serialized form
    is the SOLE source of truth for whether a gate
    passed.
    """
    path = staging / "gate-results.json"
    payload: list[dict[str, object]] = []
    for result in gate_results:
        cmd = result.command
        payload.append(
            {
                "name": result.name,
                "argv": list(cmd.argv),
                "cwd": cmd.cwd,
                "exit_code": cmd.returncode,
                "stdout_sha256": cmd.stdout_sha256,
                "stderr_sha256": cmd.stderr_sha256,
                "status": cmd.status,
            }
        )
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def write_classification_file(
    staging: Path,
    text: str,
) -> Path:
    """Write the ``final-classification.md`` artefact."""
    path = staging / "final-classification.md"
    path.write_text(text, encoding="utf-8")
    return path


__all__ = [
    "build_commands_registry",
    "write_classification_file",
    "write_commands_file",
    "write_gate_results_file",
    "write_manifest_file",
    "write_ruff_argv_file",
    "write_ruff_scope_file",
    "write_tool_identities_file",
    "write_topology_file",
]
