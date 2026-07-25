"""CORRECTION12: detached range evidence bound to production functions.

The CLI / library entry point in this module is the canonical
producer of the detached evidence in
``/tmp/closure_evidence_12/``.  It calls the production
:func:`changed_paths`, :func:`changed_python_paths`, and
:func:`build_ruff_argv` functions from :mod:`scope` and
executes the resulting Ruff argv.  No independent shell
command regenerates the path manifests; the same prod code
drives both the test-suite expectations and the detached
evidence.

The exit code is nonzero on any failure (range resolution,
ruff execution, or disk write).  On success the script
records stdout, stderr, exit codes, and SHA-256 hashes for
each detached manifest, so the bundle can be reproduced and
audited independently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import cast

from scripts.verifiers_audit.discovery import REPO_ROOT
from scripts.verifiers_audit.scope import (
    build_ruff_argv,
    changed_paths,
    changed_python_paths,
)


def _write_lines(path: Path, lines: list[str]) -> None:
    """Write ``lines`` to ``path`` with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    path.write_text(payload, encoding="utf-8")


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_captured(argv: list[str], repo_root: Path) -> dict[str, object]:
    """Run ``argv`` (CWD ``repo_root``) and capture stdout/stderr/exit."""
    start = time.monotonic()
    proc = subprocess.run(
        argv,
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )
    elapsed = time.monotonic() - start
    return {
        "argv": list(argv),
        "cwd": str(repo_root),
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "stdout": proc.stdout.decode("utf-8", errors="replace"),
        "stderr": proc.stderr.decode("utf-8", errors="replace"),
        "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(),
    }


def collect_range_evidence(
    *,
    base: str,
    subject: str,
    repo_root: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Produce the detached evidence bundle for ``base..subject``.

    The function:

    1. calls :func:`changed_paths` to produce the changed-paths
       manifest;
    2. calls :func:`changed_python_paths` to produce the
       Python-paths manifest;
    3. calls :func:`build_ruff_argv` to produce the Ruff argv
       used to execute the lint check;
    4. writes the three manifests to ``output_dir``;
    5. executes the Ruff argv in ``repo_root`` and records
       stdout, stderr, exit code, and hashes;
    6. returns a manifest dict that the CLI serialises to
       ``manifest.json``.

    Each manifest entry lists the path, content, and SHA-256
    of the file.  The ruff invocation record is bound to the
    same argv that was used to construct the path list, so
    the test-suite equality assertion (changed_python_paths
    output == ruff-input-paths.txt == paths in executed Ruff
    argv) holds by construction.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    # 1. changed paths
    all_paths = changed_paths(base, subject, repo_root=repo_root)
    # 2. python paths
    py_paths = changed_python_paths(base, subject, repo_root=repo_root)
    # 3. ruff argv
    ruff_argv = build_ruff_argv(py_paths)
    ruff_paths = list(ruff_argv[2:])

    # 4. write the three manifests
    changed_paths_path = output_dir / "changed-paths.txt"
    changed_python_paths_path = output_dir / "changed-python-paths.txt"
    ruff_input_paths_path = output_dir / "ruff-input-paths.txt"
    ruff_argv_path = output_dir / "ruff-argv.json"

    _write_lines(changed_paths_path, list(all_paths))
    _write_lines(changed_python_paths_path, list(py_paths))
    _write_lines(ruff_input_paths_path, ruff_paths)
    ruff_argv_path.write_text(
        json.dumps(list(ruff_argv), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 5. execute the Ruff argv
    ruff_run = _run_captured(list(ruff_argv), repo_root)

    # 6. build the manifest
    commands = [
        {
            "name": "git-diff-factory",
            "argv": [
                "git",
                "diff",
                "--name-only",
                "-z",
                "--diff-filter=ACMRT",
                base,
                subject,
            ],
            "cwd": str(repo_root),
        },
        {
            "name": "ruff-check",
            "argv": list(ruff_argv),
            "cwd": str(repo_root),
            "exit_code": ruff_run["exit_code"],
            "stdout_sha256": ruff_run["stdout_sha256"],
            "stderr_sha256": ruff_run["stderr_sha256"],
        },
    ]

    manifest = {
        "schema_version": "leamas.v2.closure-evidence/1",
        "base": base,
        "subject": subject,
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "range": {
            "method": "git-diff-factory",
            "diff_args": [
                "--name-only",
                "-z",
                "--diff-filter=ACMRT",
                base,
                subject,
            ],
        },
        "changed_paths": {
            "relpath": "changed-paths.txt",
            "sha256": _sha256_of(changed_paths_path),
            "count": len(all_paths),
        },
        "changed_python_paths": {
            "relpath": "changed-python-paths.txt",
            "sha256": _sha256_of(changed_python_paths_path),
            "count": len(py_paths),
        },
        "ruff_argv": {
            "relpath": "ruff-argv.json",
            "sha256": _sha256_of(ruff_argv_path),
            "argv": list(ruff_argv),
        },
        "ruff_input_paths": {
            "relpath": "ruff-input-paths.txt",
            "sha256": _sha256_of(ruff_input_paths_path),
            "count": len(ruff_paths),
        },
        "ruff_run": ruff_run,
        "commands": commands,
        "protocol_stage": "manual-preclosure-evidence",
        "leamas_protocol_E": False,
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        required=True,
        help="Closure range base revision (commit-ish).",
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Closure range subject revision (commit-ish).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root for the git diff (default: REPO_ROOT).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for the detached evidence bundle.",
    )
    args = parser.parse_args(argv)
    try:
        manifest = collect_range_evidence(
            base=args.base,
            subject=args.subject,
            repo_root=args.repo_root,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    changed_paths_meta = cast("dict[str, object]", manifest["changed_paths"])
    changed_python_meta = cast(
        "dict[str, object]", manifest["changed_python_paths"]
    )
    ruff_input_meta = cast("dict[str, object]", manifest["ruff_input_paths"])
    ruff_run_meta = cast("dict[str, object]", manifest["ruff_run"])
    print(
        f"wrote {manifest_path}: changed={changed_paths_meta['count']} "
        f"python={changed_python_meta['count']} "
        f"ruff_paths={ruff_input_meta['count']} "
        f"ruff_rc={ruff_run_meta['exit_code']}"
    )
    # The exit code is nonzero if the Ruff run failed; success
    # in the range evidence path is contingent on Ruff success
    # on the changed Python paths.
    return 0 if cast(int, ruff_run_meta["exit_code"]) == 0 else 1



if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
