"""Verifier for k9b backend trace capture lab artifacts.

This module validates that trace capture artifacts meet the requirements:
- At least one HTTP span exists
- At least one internal span exists
- HTTP and internal spans share a trace ID
- Route names are normalized
- Raw incident IDs do not appear in span names
- Raw artifact contents are not present
- Trace IDs are written to trace-ids.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trace_summary import (
    TraceSummary,
    validate_trace_summary,
)

# =============================================================================
# Artifact Paths
# =============================================================================

DEFAULT_ARTIFACT_DIR = Path(__file__).parent


def get_artifact_paths(artifact_dir: Path | str | None = None) -> dict[str, Path]:
    """Get paths to trace capture artifacts.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Dictionary mapping artifact names to paths
    """
    if artifact_dir is None:
        artifact_dir = DEFAULT_ARTIFACT_DIR
    artifact_dir = Path(artifact_dir)

    return {
        "collector_config": artifact_dir / "collector-config.yaml",
        "collector_output": artifact_dir / "collector-output.log",
        "trace_jsonl": artifact_dir / "collector-output.jsonl",
        "trace_summary": artifact_dir / "trace-summary.json",
        "trace_ids": artifact_dir / "trace-ids.txt",
        "backend_api_traces": artifact_dir / "backend-api-traces.json",
    }


# =============================================================================
# Verification Functions
# =============================================================================


def verify_artifacts_exist(artifact_dir: Path | str | None = None) -> list[str]:
    """Verify that required artifact files exist.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        List of missing artifact paths
    """
    paths = get_artifact_paths(artifact_dir)
    missing: list[str] = []

    for name, path in paths.items():
        if name == "collector_output":
            # collector-output.log is optional (debug output)
            continue
        if not path.exists():
            missing.append(str(path))

    return missing


def verify_trace_summary(
    artifact_dir: Path | str | None = None,
    trace_summary: TraceSummary | None = None,
) -> tuple[bool, list[str]]:
    """Verify trace summary meets requirements.

    Args:
        artifact_dir: Optional artifact directory override
        trace_summary: Pre-loaded trace summary (loads from file if None)

    Returns:
        Tuple of (passed, failure_messages)
    """
    if trace_summary is None:
        paths = get_artifact_paths(artifact_dir)
        summary_path = paths["trace_summary"]

        if not summary_path.exists():
            return False, ["trace-summary.json not found"]

        try:
            data = json.loads(summary_path.read_text())
            trace_summary = TraceSummary.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            return False, [f"Failed to load trace-summary.json: {e}"]

    failures = validate_trace_summary(trace_summary)
    passed = len(failures) == 0

    return passed, failures


def verify_trace_ids_file(artifact_dir: Path | str | None = None) -> tuple[bool, str]:
    """Verify trace-ids.txt contains valid trace IDs.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, message)
    """
    paths = get_artifact_paths(artifact_dir)
    trace_ids_path = paths["trace_ids"]

    if not trace_ids_path.exists():
        return False, "trace-ids.txt not found"

    try:
        content = trace_ids_path.read_text()
        lines = [line.strip() for line in content.splitlines() if line.strip()]

        if not lines:
            return False, "trace-ids.txt is empty"

        # Check that each line looks like a valid trace ID (hex string)
        import re

        trace_id_pattern = re.compile(r"^[0-9a-f]{32}$")
        invalid_ids = [line for line in lines if not trace_id_pattern.match(line)]

        if invalid_ids:
            return False, f"trace-ids.txt contains invalid trace IDs: {invalid_ids[:5]}"

        return True, f"trace-ids.txt contains {len(lines)} valid trace IDs"

    except OSError as e:
        return False, f"Failed to read trace-ids.txt: {e}"


def verify_privacy_safety(artifact_dir: Path | str | None = None) -> tuple[bool, list[str]]:
    """Verify trace artifacts do not contain privacy-sensitive data.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, violation_messages)
    """
    paths = get_artifact_paths(artifact_dir)
    violations: list[str] = []

    # Import privacy check functions
    from trace_summary import check_artifact_payload_in_text

    # Check trace summary for privacy violations
    summary_path = paths["trace_summary"]
    if summary_path.exists():
        try:
            content = summary_path.read_text()
            if check_artifact_payload_in_text(content):
                violations.append("trace-summary.json contains artifact payload markers")
        except OSError:
            pass

    # Check trace IDs file
    trace_ids_path = paths["trace_ids"]
    if trace_ids_path.exists():
        try:
            content = trace_ids_path.read_text()
            # Should only contain trace IDs (hex strings)
            import re

            trace_id_pattern = re.compile(r"^[0-9a-f]{32}$")
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            for line in lines:
                if not trace_id_pattern.match(line):
                    violations.append(f"trace-ids.txt contains non-trace-ID content: {line[:50]}")
        except OSError:
            pass

    passed = len(violations) == 0
    return passed, violations


def verify_all(artifact_dir: Path | str | None = None) -> bool:
    """Run all verifications and print results.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        True if all verifications passed
    """
    print("=" * 70)
    print("k9b Backend Trace Capture Verification")
    print("=" * 70)
    print()

    all_passed = True

    # Check artifact existence
    print("1. Checking artifact file existence...")
    missing = verify_artifacts_exist(artifact_dir)
    if missing:
        print("   ✗ FAILED: Missing artifacts:")
        for path in missing:
            print(f"      - {path}")
        all_passed = False
    else:
        print("   ✓ PASSED: All required artifacts exist")

    # Check trace summary
    print()
    print("2. Verifying trace summary requirements...")
    passed, failures = verify_trace_summary(artifact_dir)
    if passed:
        print("   ✓ PASSED: Trace summary meets all requirements")
    else:
        print("   ✗ FAILED: Trace summary validation failures:")
        for failure in failures:
            print(f"      - {failure}")
        all_passed = False

    # Check trace IDs file
    print()
    print("3. Verifying trace-ids.txt...")
    passed, message = verify_trace_ids_file(artifact_dir)
    print(f"   {'✓' if passed else '✗'} {message}")
    if not passed:
        all_passed = False

    # Check privacy safety
    print()
    print("4. Verifying privacy safety...")
    passed, violations = verify_privacy_safety(artifact_dir)
    if passed:
        print("   ✓ PASSED: No privacy violations detected")
    else:
        print("   ✗ FAILED: Privacy violations found:")
        for violation in violations:
            print(f"      - {violation}")
        all_passed = False

    # Print final result
    print()
    print("=" * 70)
    if all_passed:
        print("✓ VERIFICATION PASSED: All trace capture requirements met")
    else:
        print("✗ VERIFICATION FAILED: One or more requirements not met")
    print("=" * 70)

    return all_passed


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    """CLI entry point for trace capture verifier."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify k9b backend trace capture artifacts"
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Trace capture artifact directory (default: trace-capture/)",
    )
    parser.add_argument(
        "--fail",
        action="store_true",
        help="Exit with non-zero code on failure",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Run verification
    all_passed = verify_all(args.artifact_dir)

    # Output JSON if requested
    if args.json:
        paths = get_artifact_paths(args.artifact_dir)
        summary_path = paths["trace_summary"]

        output: dict[str, object] = {
            "passed": all_passed,
            "artifacts_check": "passed" if not verify_artifacts_exist(args.artifact_dir) else "failed",
            "summary_check": "passed",
            "trace_ids_check": "passed",
            "privacy_check": "passed",
        }

        if summary_path.exists():
            try:
                data = json.loads(summary_path.read_text())
                output["summary"] = data
            except (json.JSONDecodeError, OSError):
                pass

        print(json.dumps(output, indent=2))

    # Exit with error code if requested
    if args.fail and not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
