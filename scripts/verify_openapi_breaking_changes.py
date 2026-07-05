#!/usr/bin/env python3
"""OpenAPI breaking-change snapshot gate.

This script compares the current OpenAPI schema against a committed baseline
and fails CI on accidental breaking changes such as:
- Removed endpoints
- Changed HTTP methods
- Removed response fields
- Changed response types
- Removed parameters
- Renamed operation IDs
- Changed request requirements

Run:
    .venv/bin/python scripts/verify_openapi_breaking_changes.py
    .venv/bin/python scripts/verify_openapi_breaking_changes.py --update-baseline
    .venv/bin/python scripts/verify_openapi_breaking_changes.py --report build/openapi/openapi-breaking-report.txt

Exit codes:
    0 - Success (no breaking changes)
    1 - Breaking changes detected or baseline missing
    2 - oasdiff tool unavailable
    3 - Schema export failed
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# OASDIFF_VERSION pins the tool to a reproducible release
OASDIFF_VERSION = "v1.21.0"

# OASDIFF_BIN allows overriding oasdiff with a pre-installed binary (for CI caching).
# When set, skip go run and use the binary directly.
# This avoids the ~28s go module download cost in CI environments.
_OASDIFF_BIN: str | None = None


def _resolve_oasdiff_binary() -> str | None:
    """Resolve oasdiff binary path from OASDIFF_BIN env var or PATH.
    
    Returns:
        Absolute path to oasdiff binary if found, None otherwise.
    """
    global _OASDIFF_BIN
    if _OASDIFF_BIN is not None:
        return _OASDIFF_BIN
    
    import os
    env_bin = os.environ.get("OASDIFF_BIN", "").strip()
    if env_bin:
        if os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
            _OASDIFF_BIN = env_bin
            return _OASDIFF_BIN
        # Check if it's just "oasdiff" and resolve from PATH
        if env_bin == "oasdiff":
            import shutil
            resolved = shutil.which("oasdiff")
            if resolved:
                _OASDIFF_BIN = resolved
                return _OASDIFF_BIN
        return None
    
    # Check PATH for oasdiff
    import shutil
    resolved = shutil.which("oasdiff")
    if resolved:
        _OASDIFF_BIN = resolved
        return _OASDIFF_BIN
    
    return None

# Default paths
DEFAULT_BASELINE = Path("docs/api/openapi/k9b-openapi-baseline.json")
DEFAULT_CURRENT = Path("build/openapi/k9b-openapi.json")
DEFAULT_BREAKING_REPORT = Path("build/openapi/openapi-breaking-report.txt")
DEFAULT_CHANGELOG_REPORT = Path("build/openapi/openapi-changelog-report.txt")
DEFAULT_OPERATION_IDS_BASELINE = Path("docs/api/openapi/operation-ids-baseline.txt")
DEFAULT_OPERATION_IDS_CURRENT = Path("build/openapi/operation-ids-current.txt")


def _run_oasdiff(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run oasdiff using binary or go run for reproducible versioning.
    
    Prefers OASDIFF_BIN environment variable or PATH-resolved oasdiff to avoid
    the ~28s go module download cost in CI environments.
    """
    binary = _resolve_oasdiff_binary()
    if binary:
        cmd = [binary] + args
    else:
        cmd = ["go", "run", f"github.com/oasdiff/oasdiff@{OASDIFF_VERSION}"] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
    )


def _check_oasdiff_available() -> bool:
    """Check if oasdiff is available via binary or go run."""
    binary = _resolve_oasdiff_binary()
    if binary:
        return True
    try:
        _run_oasdiff(["--help"], check=False)
        return True
    except Exception:
        return False


def export_current_schema(output_path: Path) -> None:
    """Export the current OpenAPI schema to a file."""
    try:
        from k8s_diag_agent.ui.api_contract import build_openapi_schema
    except ImportError as e:
        raise RuntimeError(f"Failed to import build_openapi_schema: {e}") from e

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        schema = build_openapi_schema()
    except Exception as e:
        raise RuntimeError(f"Failed to build OpenAPI schema: {e}") from e

    # Write deterministic JSON with sorted keys
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def update_baseline(current_schema_path: Path, baseline_path: Path) -> None:
    """Copy current schema to baseline path."""
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current_schema_path, baseline_path)


def run_oasdiff_breaking(
    baseline_path: Path,
    current_path: Path,
    report_path: Path,
) -> tuple[int, str]:
    """Run oasdiff breaking check and write report.

    Returns:
        Tuple of (exit_code, stdout).
        exit_code is non-zero if breaking changes are detected.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = _run_oasdiff(
            ["breaking", "--fail-on", "ERR", str(baseline_path), str(current_path)],
            check=False,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to run oasdiff: {e}\n"
            "Ensure Go is installed: https://go.dev/doc/install"
        ) from e

    # oasdiff with --fail-on ERR exits non-zero on breaking changes
    exit_code = result.returncode

    # Write report
    report_content = result.stdout
    if result.stderr:
        report_content += "\n\n[STDERR]\n" + result.stderr
    report_path.write_text(report_content, encoding="utf-8")

    return exit_code, result.stdout


def run_oasdiff_changelog(
    baseline_path: Path,
    current_path: Path,
    report_path: Path,
) -> None:
    """Run oasdiff changelog for broader significant-change reporting."""
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = _run_oasdiff(
            ["changelog", str(baseline_path), str(current_path)],
            check=False,
        )
    except Exception:
        # Non-fatal - changelog is optional
        report_path.write_text(
            "[Changelog check skipped - oasdiff unavailable]\n",
            encoding="utf-8",
        )
        return

    report_path.write_text(result.stdout, encoding="utf-8")


def write_operation_id_snapshot(schema_path: Path, output_path: Path) -> None:
    """Write operation ID snapshot from OpenAPI schema.

    Format: METHOD /path operation_id
    """
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ops = []
    for path, methods in sorted(schema.get("paths", {}).items()):
        for method, details in sorted(methods.items()):
            op_id = details.get("operationId", "")
            ops.append(f"{method.upper()} {path} {op_id}")

    output_path.write_text(
        "# Operation ID snapshot\n"
        "# Format: METHOD /path operation_id\n"
        "# Generated from k9b API_ROUTES registry.\n"
        + "\n".join(ops)
        + "\n",
        encoding="utf-8",
    )


def _parse_operation_id_map(path: Path) -> dict[tuple[str, str], str]:
    """Parse operation ID file into (method, path) -> operationId mapping."""
    result: dict[tuple[str, str], str] = {}
    for line in _parse_operation_ids(path):
        method, route, op_id = line.split(" ", 2)
        result[(method, route)] = op_id
    return result


def compare_operation_id_snapshots(
    baseline_path: Path,
    current_path: Path,
) -> list[str]:
    """Compare operation ID snapshots by (METHOD, path) -> operationId mapping.

    Returns:
        List of breaking changes (removed routes or renamed operation IDs).
        Additive routes/operations are NOT considered breaking.
    """
    baseline = _parse_operation_id_map(baseline_path)
    current = _parse_operation_id_map(current_path)

    breaking: list[str] = []

    for (method, route), old_op_id in sorted(baseline.items()):
        if (method, route) not in current:
            breaking.append(f"Removed operation route: {method} {route} ({old_op_id})")
            continue

        new_op_id = current[(method, route)]
        if new_op_id != old_op_id:
            breaking.append(
                f"Renamed operation ID for {method} {route}: "
                f"{old_op_id} -> {new_op_id}"
            )

    return breaking


def _parse_operation_ids(path: Path) -> list[str]:
    """Parse operation ID file, excluding comments and empty lines."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return sorted(lines)


def update_operation_id_baseline(current_path: Path, baseline_path: Path) -> None:
    """Update operation ID baseline from current snapshot."""
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current_path, baseline_path)


def write_success_report(
    baseline_path: Path,
    current_path: Path,
    report_path: Path,
) -> None:
    """Write a success report when no breaking changes are found."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "No OpenAPI breaking changes detected.\n"
        f"Compared:\n"
        f"  - baseline: {baseline_path}\n"
        f"  - current: {current_path}\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenAPI breaking-change snapshot gate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    .venv/bin/python scripts/verify_openapi_breaking_changes.py
    .venv/bin/python scripts/verify_openapi_breaking_changes.py --update-baseline
    .venv/bin/python scripts/verify_openapi_breaking_changes.py --report build/openapi/openapi-breaking-report.txt
        """,
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Update the committed baseline from current schema and exit.",
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help=f"Path to baseline schema (default: {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--current",
        default=str(DEFAULT_CURRENT),
        help=f"Path to current schema (default: {DEFAULT_CURRENT})",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_BREAKING_REPORT),
        help=f"Path for breaking report (default: {DEFAULT_BREAKING_REPORT})",
    )
    parser.add_argument(
        "--changelog",
        default=str(DEFAULT_CHANGELOG_REPORT),
        help=f"Path for changelog report (default: {DEFAULT_CHANGELOG_REPORT})",
    )
    parser.add_argument(
        "--operation-ids-baseline",
        default=str(DEFAULT_OPERATION_IDS_BASELINE),
        help=f"Path to operation IDs baseline (default: {DEFAULT_OPERATION_IDS_BASELINE})",
    )
    parser.add_argument(
        "--operation-ids-current",
        default=str(DEFAULT_OPERATION_IDS_CURRENT),
        help=f"Path for current operation IDs (default: {DEFAULT_OPERATION_IDS_CURRENT})",
    )
    args = parser.parse_args(argv)

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)
    report_path = Path(args.report)
    changelog_path = Path(args.changelog)
    op_ids_baseline = Path(args.operation_ids_baseline)
    op_ids_current = Path(args.operation_ids_current)

    # Step 1: Export current schema
    print(f"Exporting current OpenAPI schema to {current_path}...")
    try:
        export_current_schema(current_path)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    # Step 2: Write current operation ID snapshot
    print(f"Writing operation ID snapshot to {op_ids_current}...")
    write_operation_id_snapshot(current_path, op_ids_current)

    # Step 3: Handle update-baseline mode
    if args.update_baseline:
        print(f"Updating baseline: {baseline_path}")
        update_baseline(current_path, baseline_path)
        print(f"Updating operation ID baseline: {op_ids_baseline}")
        update_operation_id_baseline(op_ids_current, op_ids_baseline)
        print("Baseline updated successfully.")
        return 0

    # Step 4: Verify baseline exists
    if not baseline_path.exists():
        print(
            f"Error: Baseline schema not found at {baseline_path}",
            file=sys.stderr,
        )
        print(
            "To create the baseline, run with --update-baseline",
            file=sys.stderr,
        )
        return 1

    if not op_ids_baseline.exists():
        print(
            f"Error: Operation ID baseline not found at {op_ids_baseline}",
            file=sys.stderr,
        )
        print(
            "To create the baseline, run with --update-baseline",
            file=sys.stderr,
        )
        return 1

    # Step 5: Check oasdiff availability
    if not _check_oasdiff_available():
        print(
            "Error: oasdiff is not available.",
            file=sys.stderr,
        )
        print(
            f"Install with: go install github.com/oasdiff/oasdiff@{OASDIFF_VERSION}",
            file=sys.stderr,
        )
        print(
            "Or run via: go run github.com/oasdiff/oasdiff@latest ...",
            file=sys.stderr,
        )
        return 2

    # Step 6: Run oasdiff breaking check
    print("Checking for OpenAPI breaking changes...")
    returncode, stdout = run_oasdiff_breaking(baseline_path, current_path, report_path)

    # Step 7: Run oasdiff changelog (non-fatal)
    print("Generating changelog report...")
    run_oasdiff_changelog(baseline_path, current_path, changelog_path)

    # Step 8: Check operation ID changes
    print("Checking operation ID changes...")
    op_id_changes = compare_operation_id_snapshots(op_ids_baseline, op_ids_current)
    op_id_breaking = [c for c in op_id_changes if "Removed" in c or "Renamed" in c]

    # Step 9: Determine overall result
    has_breaking = returncode != 0 or bool(op_id_breaking)

    if has_breaking:
        print()
        print("=" * 60)
        print("OPENAPI BREAKING CHANGES DETECTED")
        print("=" * 60)
        print()

        if returncode != 0:
            print("Structural breaking changes found by oasdiff:")
            print(f"  Report: {report_path}")
            print()
            # Print summary from oasdiff output
            lines = stdout.strip().splitlines()
            if lines:
                print("Summary:")
                for line in lines[:10]:
                    print(f"  {line}")

        for change in op_id_breaking:
            print(f"Operation ID change: {change}")

        print()
        print("To intentionally accept these changes:")
        print("  1. Review the breaking changes above")
        print("  2. Update frontend/client/callers as needed")
        print("  3. Run: .venv/bin/python scripts/verify_openapi_breaking_changes.py --update-baseline")
        print("  4. Include the report summary in your commit/PR notes")
        print()

        return 1

    # Success
    write_success_report(baseline_path, current_path, report_path)
    print()
    print("No OpenAPI breaking changes detected.")
    print(f"  Baseline: {baseline_path}")
    print(f"  Current: {current_path}")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
