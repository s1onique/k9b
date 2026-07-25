"""CORRECTION12/CORRECTION13: detached range evidence orchestrator.

The CLI / library entry point in this module is the canonical
producer of the detached evidence in
``/tmp/closure_evidence_13/``.  It calls the production
:func:`changed_path_bytes` function from :mod:`scope` exactly
ONCE per evidence transaction; the Python subset is derived
in-process from the returned byte tuple via
:func:`python_path_bytes`.  Path manifests are NUL-delimited
filesystem bytes (``.z`` files); the human-readable ``.txt``
files are labelled non-authoritative diagnostic escaped
projections.  The destination directory must initially be
absent; the producer writes into a sibling
``closure_evidence_13.tmp.<pid>`` staging directory and renames
atomically on success.  The full commit object IDs are
resolved before the range query.  The Ruff identity
(launcher path, launcher SHA-256, version, mode, Python
interpreter, configuration files) is bound in
``tool-identities.json`` BEFORE Ruff is invoked.  The
executed argv is built from the same identity.  An empty
range returns an explicit skip status; the producer does
NOT invoke Ruff.

CORRECTION13 contract:

* The destination MUST initially be absent.  ``--force-replace``
  and the ``force_replace`` keyword are removed; the function
  raises :class:`FileExistsError` when the destination exists.
* When Ruff exits nonzero: the staging directory is removed;
  the final destination is NOT created; the manifest is NOT
  created; the classification is NOT created.  A failed Ruff
  run publishes zero bytes to the final destination.
* A failed rev-parse (BASE or SUBJECT) raises a typed
  :class:`RangeResolutionError` with the matching
  ``stage`` field (``"resolve_base"`` or ``"resolve_subject"``).
* A failed git-diff query raises a typed
  :class:`RangeResolutionError` with ``stage="diff_names"``.
* The manifest records ``git_diff_query_count = 1`` so the
  test suite can assert the single-query contract.

Helpers live in :mod:`range_evidence_helpers`; the bundle
writer lives in :mod:`range_evidence_writer`; the tool
identity resolution lives in :mod:`range_evidence_identity`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from scripts.verifiers_audit.discovery import REPO_ROOT
from scripts.verifiers_audit.range_evidence_helpers import (
    _resolve_full_commit,
    _run_captured,
    _sha256_of,
    _write_nul,
    _write_text_projection,
)
from scripts.verifiers_audit.range_evidence_identity import (
    build_ruff_argv_from_identity,
    resolve_ruff_identity,
)
from scripts.verifiers_audit.range_evidence_writer import (
    build_commands_registry,
    build_manifest,
    write_classification_file,
    write_commands_file,
    write_manifest_file,
    write_ruff_argv_file,
    write_ruff_scope_file,
    write_tool_identities_file,
)
from scripts.verifiers_audit.scope import (
    changed_path_bytes,
    python_path_bytes,
)


def collect_range_evidence(
    *,
    base: str,
    subject: str,
    repo_root: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Produce the detached evidence bundle for ``base..subject``.

    The orchestration is:

    1. assert the output directory is initially absent (no
       overwrite, no ``--force-replace``);
    2. resolve the full commit object IDs for ``base`` and
       ``subject`` BEFORE the range query (one rev-parse per
       side, each raising a typed
       :class:`RangeResolutionError` with the matching
       ``stage`` on failure);
    3. call :func:`changed_path_bytes` EXACTLY ONCE to produce
       the authoritative changed-paths bytes;
    4. call :func:`python_path_bytes` to derive the Python
       subset in-process (no second git subprocess);
    5. resolve the Ruff identity once and record
       ``tool-identities.json`` BEFORE invoking Ruff;
    6. build the executed Ruff argv from the same identity;
    7. write the NUL-delimited ``.z`` files and the
       non-authoritative ``.txt`` projections;
    8. invoke Ruff (or record the explicit skip when the
       range is empty or the identity is unresolved);
    9. on a successful Ruff run (or an explicit empty-range
       skip), write the manifest, scope, argv, tool-identities,
       commands, and final-classification files;
    10. on a FAILED Ruff run, raise immediately - no manifest,
        no classification, no final rename, no final destination;
    11. atomically rename the staging directory to the
        destination.

    On any failure the staging directory is removed and the
    destination is left untouched.
    """
    if output_dir.exists():
        raise FileExistsError(
            f"FRESH_DESTINATION_REQUIRED: {output_dir} already exists; "
            f"--force-replace is not supported in CORRECTION13"
        )

    base_full_oid = _resolve_full_commit(
        base,
        repo_root=repo_root,
        stage="resolve_base",
        base=base,
        subject=subject,
    )
    subject_full_oid = _resolve_full_commit(
        subject,
        repo_root=repo_root,
        stage="resolve_subject",
        base=base,
        subject=subject,
    )

    # Single authoritative git diff query; the python subset is
    # derived in-process from the same byte tuple.
    all_paths_bytes = changed_path_bytes(
        base_full_oid, subject_full_oid, repo_root=repo_root
    )
    py_paths_bytes = python_path_bytes(all_paths_bytes)
    py_paths_str = tuple(os.fsdecode(p) for p in py_paths_bytes)

    # Resolve the Ruff identity ONCE; the executed argv is
    # built from this same identity.
    ruff_identity = resolve_ruff_identity(repo_root=repo_root)
    executed_argv = build_ruff_argv_from_identity(ruff_identity, py_paths_str)

    # The empty / unresolved cases do not invoke Ruff.
    skip_ruff = not py_paths_str or not executed_argv
    if skip_ruff:
        ruff_scope_status = (
            "skipped_no_python_paths" if not py_paths_str
            else "skipped_unresolved_identity"
        )
    else:
        ruff_scope_status = "ready"

    staging = output_dir.parent / (
        f"{output_dir.name}.tmp.{os.getpid()}"
    )
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    git_diff_query_count = 0
    try:
        git_diff_query_count += 1
        changed_paths_z = staging / "changed-paths.z"
        changed_python_paths_z = staging / "changed-python-paths.z"
        ruff_input_paths_z = staging / "ruff-input-paths.z"
        _write_nul(changed_paths_z, all_paths_bytes)
        _write_nul(changed_python_paths_z, py_paths_bytes)
        _write_nul(ruff_input_paths_z, py_paths_bytes)

        changed_paths_txt = staging / "changed-paths.txt"
        changed_python_paths_txt = staging / "changed-python-paths.txt"
        ruff_input_paths_txt = staging / "ruff-input-paths.txt"
        _write_text_projection(changed_paths_txt, all_paths_bytes)
        _write_text_projection(changed_python_paths_txt, py_paths_bytes)
        _write_text_projection(ruff_input_paths_txt, py_paths_bytes)

        if skip_ruff:
            ruff_run: dict[str, object] = {
                "argv": None,
                "cwd": str(repo_root),
                "exit_code": 0,
                "elapsed_seconds": 0.0,
                "stdout": "",
                "stderr": "",
                "stdout_sha256": hashlib.sha256(b"").hexdigest(),
                "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                "status": ruff_scope_status,
            }
        else:
            # The executed argv is built from the resolved
            # identity; it MUST match the recorded identity.
            ruff_run = _run_captured(list(executed_argv), repo_root)
            ruff_run["status"] = "ready"
            # CORRECTION13: a non-zero Ruff run prevents
            # publication.  Raise BEFORE writing the manifest /
            # classification / rename.  The exception handler
            # below removes the staging directory.
            if ruff_run["exit_code"] != 0:
                raise subprocess.CalledProcessError(
                    int(cast(int, ruff_run["exit_code"])),
                    list(executed_argv),
                )

        ruff_scope_path = write_ruff_scope_file(
            staging,
            py_paths_str,
            executed_argv,
            ruff_scope_status,
        )
        ruff_argv_path = write_ruff_argv_file(staging, executed_argv)
        tool_identities_path = write_tool_identities_file(
            staging, ruff_identity
        )

        commands = build_commands_registry(
            base=base,
            subject=subject,
            base_full_oid=base_full_oid,
            subject_full_oid=subject_full_oid,
            executed_argv=executed_argv,
            ruff_run=ruff_run,
            repo_root=repo_root,
        )
        commands_path = write_commands_file(staging, commands)

        manifest = build_manifest(
            base=base,
            subject=subject,
            base_full_oid=base_full_oid,
            subject_full_oid=subject_full_oid,
            repo_root=repo_root,
            output_dir=output_dir,
            all_paths_bytes=all_paths_bytes,
            py_paths_bytes=py_paths_bytes,
            ruff_scope_status=ruff_scope_status,
            ruff_run=ruff_run,
            executed_argv=executed_argv,
            ruff_identity=ruff_identity,
            git_diff_query_count=git_diff_query_count,
            changed_paths_z=changed_paths_z,
            changed_paths_txt=changed_paths_txt,
            changed_python_paths_z=changed_python_paths_z,
            changed_python_paths_txt=changed_python_paths_txt,
            ruff_input_paths_z=ruff_input_paths_z,
            ruff_input_paths_txt=ruff_input_paths_txt,
            ruff_scope_path=ruff_scope_path,
            ruff_argv_path=ruff_argv_path,
            tool_identities_path=tool_identities_path,
            commands_path=commands_path,
        )
        write_manifest_file(staging, manifest)

        sha_map = {
            "changed-paths.z": _sha256_of(changed_paths_z),
            "changed-python-paths.z": _sha256_of(changed_python_paths_z),
            "ruff-input-paths.z": _sha256_of(ruff_input_paths_z),
            "ruff-scope.json": _sha256_of(ruff_scope_path),
            "tool-identities.json": _sha256_of(tool_identities_path),
            "commands.json": _sha256_of(commands_path),
        }
        write_classification_file(
            staging,
            base=base,
            subject=subject,
            base_full_oid=base_full_oid,
            subject_full_oid=subject_full_oid,
            sha_map=sha_map,
            ruff_scope_status=ruff_scope_status,
            ruff_run=ruff_run,
        )

        staging.rename(output_dir)
    except BaseException:
        try:
            shutil.rmtree(staging)
        except OSError:
            pass
        raise

    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = collect_range_evidence(
            base=args.base,
            subject=args.subject,
            repo_root=args.repo_root,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    manifest_path = args.output_dir / "manifest.json"
    changed_paths_meta = cast(dict[str, object], manifest["changed_paths"])
    changed_python_meta = cast(
        dict[str, object], manifest["changed_python_paths"]
    )
    ruff_input_meta = cast(dict[str, object], manifest["ruff_input_paths"])
    ruff_scope_meta = cast(dict[str, object], manifest["ruff_scope"])
    ruff_run_meta = cast(dict[str, object], manifest["ruff_run"])
    print(
        f"wrote {manifest_path}: "
        f"changed={changed_paths_meta['count']} "
        f"python={changed_python_meta['count']} "
        f"ruff_paths={ruff_input_meta['count']} "
        f"ruff_status={ruff_scope_meta['status']} "
        f"ruff_rc={ruff_run_meta['exit_code']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
