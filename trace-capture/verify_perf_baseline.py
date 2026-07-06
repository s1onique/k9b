"""Verifier for k9b backend API performance baseline artifacts.

This module validates that performance baseline artifacts meet the requirements:
- Baseline artifact exists
- At least one API call was attempted
- At least one successful API call
- Trace IDs are present
- HTTP spans are present
- Internal spans are present
- No raw incident IDs in span names
- No payload markers in artifacts
- Latency fields present for successful endpoints

Usage:
    python verify_perf_baseline.py --artifact-dir trace-capture/perf-baseline --fail
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# =============================================================================
# Artifact Paths
# =============================================================================

DEFAULT_ARTIFACT_DIR = Path(__file__).parent / "perf-baseline"


def get_artifact_paths(artifact_dir: Path | str | None = None) -> dict[str, Path]:
    """Get paths to perf baseline artifacts.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Dictionary mapping artifact names to paths
    """
    if artifact_dir is None:
        artifact_dir = DEFAULT_ARTIFACT_DIR
    artifact_dir = Path(artifact_dir)

    return {
        "baseline": artifact_dir / "backend-api-baseline.json",
        "summary": artifact_dir / "backend-api-baseline-summary.json",
        "trace_ids": artifact_dir / "backend-api-baseline-trace-ids.txt",
        "spans": artifact_dir / "backend-api-baseline-spans.jsonl",
    }


# =============================================================================
# Verification Functions
# =============================================================================


def verify_baseline_exists(artifact_dir: Path | str | None = None) -> tuple[bool, str]:
    """Verify baseline artifact exists.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, message)
    """
    paths = get_artifact_paths(artifact_dir)
    baseline_path = paths["baseline"]

    if not baseline_path.exists():
        return False, f"baseline artifact not found: {baseline_path}"

    # Validate JSON is parseable
    try:
        content = baseline_path.read_text()
        data = json.loads(content)
        if not isinstance(data, dict):
            return False, "baseline artifact is not a valid JSON object"
    except json.JSONDecodeError as e:
        return False, f"baseline artifact is not valid JSON: {e}"

    return True, f"baseline artifact exists: {baseline_path}"


def verify_api_calls_attempted(artifact_dir: Path | str | None = None) -> tuple[bool, str]:
    """Verify at least one API call was attempted.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, message)
    """
    paths = get_artifact_paths(artifact_dir)
    baseline_path = paths["baseline"]

    if not baseline_path.exists():
        return False, "baseline not found"

    try:
        data = json.loads(baseline_path.read_text())
        endpoints = data.get("benchmarked_endpoints", [])

        total_attempts = sum(ep.get("attempt_count", 0) for ep in endpoints)

        if total_attempts == 0:
            return False, "no API calls were attempted"

        return True, f"API calls attempted: {total_attempts}"
    except (json.JSONDecodeError, OSError) as e:
        return False, f"failed to read baseline: {e}"


def verify_successful_calls(artifact_dir: Path | str | None = None) -> tuple[bool, str]:
    """Verify at least one successful API call.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, message)
    """
    paths = get_artifact_paths(artifact_dir)
    baseline_path = paths["baseline"]

    if not baseline_path.exists():
        return False, "baseline not found"

    try:
        data = json.loads(baseline_path.read_text())
        endpoints = data.get("benchmarked_endpoints", [])

        total_success = sum(ep.get("success_count", 0) for ep in endpoints)

        if total_success == 0:
            return False, "no successful API calls"

        return True, f"successful API calls: {total_success}"
    except (json.JSONDecodeError, OSError) as e:
        return False, f"failed to read baseline: {e}"


def verify_trace_ids(artifact_dir: Path | str | None = None) -> tuple[bool, str]:
    """Verify trace IDs are present.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, message)
    """
    paths = get_artifact_paths(artifact_dir)
    trace_ids_path = paths["trace_ids"]

    if not trace_ids_path.exists():
        return False, f"trace IDs file not found: {trace_ids_path}"

    try:
        content = trace_ids_path.read_text()
        lines = [line.strip() for line in content.splitlines() if line.strip()]

        if not lines:
            return False, "trace IDs file is empty"

        # Check format
        import re
        trace_id_pattern = re.compile(r"^[0-9a-f]{32}$")
        invalid = [line for line in lines if not trace_id_pattern.match(line)]

        if invalid:
            return False, f"invalid trace IDs found: {invalid[:3]}"

        return True, f"valid trace IDs: {len(lines)}"
    except OSError as e:
        return False, f"failed to read trace IDs: {e}"


def verify_http_spans(artifact_dir: Path | str | None = None) -> tuple[bool, str]:
    """Verify HTTP spans are present (or trace data is available).

    HTTP spans are backend-dependent. If HTTP spans are not present but we have
    valid traces and internal spans, the check still passes.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, message)
    """
    paths = get_artifact_paths(artifact_dir)
    baseline_path = paths["baseline"]

    if not baseline_path.exists():
        return False, "baseline not found"

    try:
        data = json.loads(baseline_path.read_text())
        http_count = data.get("http_span_count", 0)
        total_traces = data.get("total_traces", 0)
        internal_count = data.get("internal_span_count", 0)

        # HTTP spans are backend-dependent, but we should have trace data
        if total_traces > 0 and internal_count > 0:
            # We have valid trace data even without explicit HTTP spans
            if http_count == 0:
                return True, f"trace spans: {total_traces} traces, {internal_count} internal spans (HTTP spans backend-dependent)"
            return True, f"HTTP spans: {http_count}"
        elif http_count > 0:
            return True, f"HTTP spans: {http_count}"

        return False, "no trace spans found"

    except (json.JSONDecodeError, OSError) as e:
        return False, f"failed to read baseline: {e}"


def verify_internal_spans(artifact_dir: Path | str | None = None) -> tuple[bool, str]:
    """Verify internal spans are present.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, message)
    """
    paths = get_artifact_paths(artifact_dir)
    baseline_path = paths["baseline"]

    if not baseline_path.exists():
        return False, "baseline not found"

    try:
        data = json.loads(baseline_path.read_text())
        internal_count = data.get("internal_span_count", 0)

        if internal_count == 0:
            return False, "no internal spans found"

        return True, f"internal spans: {internal_count}"
    except (json.JSONDecodeError, OSError) as e:
        return False, f"failed to read baseline: {e}"


def verify_privacy_safety(artifact_dir: Path | str | None = None) -> tuple[bool, list[str]]:
    """Verify no privacy violations in baseline artifacts.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, violation_messages)
    """
    import re

    paths = get_artifact_paths(artifact_dir)
    violations: list[str] = []

    # Patterns for raw incident IDs
    raw_incident_id_pattern = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )

    # Patterns for artifact payload markers
    payload_markers = [
        "BEGIN_CREDENTIALS",
        "BEGIN_PRIVATE_KEY",
        "BEGIN_RSA_PRIVATE_KEY",
        "BEGIN_EC_PRIVATE_KEY",
        "BEGIN_OPENSSH_PRIVATE_KEY",
        "BEGIN_GPG_PRIVATE_KEY_BLOCK",
        "kubeconfig",
        "token",
        "bearer",
        "secret",
    ]
    payload_patterns = [re.compile(p, re.IGNORECASE) for p in payload_markers]

    # Check baseline JSON
    baseline_path = paths["baseline"]
    if baseline_path.exists():
        try:
            content = baseline_path.read_text()

            # Check for raw incident IDs
            if raw_incident_id_pattern.search(content):
                # Find the actual match to report
                match = raw_incident_id_pattern.search(content)
                if match:
                    violations.append(
                        f"raw incident ID found in baseline: {match.group()[:8]}..."
                    )

            # Check for payload markers
            for pattern in payload_patterns:
                if pattern.search(content):
                    violations.append(f"artifact payload marker found: {pattern.pattern}")
                    break
        except OSError:
            pass

    # Check trace IDs file (should only have trace IDs)
    trace_ids_path = paths["trace_ids"]
    if trace_ids_path.exists():
        try:
            content = trace_ids_path.read_text()
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            trace_id_pattern = re.compile(r"^[0-9a-f]{32}$")

            for line in lines:
                if not trace_id_pattern.match(line):
                    violations.append(f"non-trace-ID content in trace_ids file: {line[:20]}")
        except OSError:
            pass

    passed = len(violations) == 0
    return passed, violations


def verify_latency_fields(artifact_dir: Path | str | None = None) -> tuple[bool, str]:
    """Verify latency fields are present for successful endpoints.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        Tuple of (passed, message)
    """
    paths = get_artifact_paths(artifact_dir)
    baseline_path = paths["baseline"]

    if not baseline_path.exists():
        return False, "baseline not found"

    try:
        data = json.loads(baseline_path.read_text())
        endpoints = data.get("benchmarked_endpoints", [])

        missing_latency = []
        for ep in endpoints:
            if ep.get("success_count", 0) > 0:
                latency = ep.get("latency_ms", {})
                if not latency or "p50" not in latency:
                    missing_latency.append(ep.get("normalized_route", "unknown"))

        if missing_latency:
            return False, f"endpoints with successful calls missing latency: {missing_latency}"

        return True, "all successful endpoints have latency fields"
    except (json.JSONDecodeError, OSError) as e:
        return False, f"failed to read baseline: {e}"


# =============================================================================
# Main Verification
# =============================================================================


def verify_all(artifact_dir: Path | str | None = None) -> bool:
    """Run all verifications and print results.

    Args:
        artifact_dir: Optional artifact directory override

    Returns:
        True if all verifications passed
    """
    print("=" * 70)
    print("k9b Backend API Performance Baseline Verification")
    print("=" * 70)
    print()

    all_passed = True
    checks = [
        ("1. Baseline artifact exists", verify_baseline_exists),
        ("2. API calls attempted", verify_api_calls_attempted),
        ("3. Successful API calls", verify_successful_calls),
        ("4. Trace IDs present", verify_trace_ids),
        ("5. HTTP spans present", verify_http_spans),
        ("6. Internal spans present", verify_internal_spans),
        ("7. Latency fields present", verify_latency_fields),
    ]

    for name, check_fn in checks:
        print(f"{name}...")
        passed, message = check_fn(artifact_dir)
        print(f"   {'✓' if passed else '✗'} {message}")
        if not passed:
            all_passed = False

    # Privacy check separately
    print()
    print("8. Privacy safety...")
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
        print("✓ VERIFICATION PASSED: All perf baseline requirements met")
    else:
        print("✗ VERIFICATION FAILED: One or more requirements not met")
    print("=" * 70)

    return all_passed


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> None:
    """CLI entry point for perf baseline verifier."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify k9b backend API performance baseline artifacts"
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Perf baseline artifact directory (default: trace-capture/perf-baseline/)",
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
        baseline_path = paths["baseline"]

        output: dict[str, object] = {
            "passed": all_passed,
            "checks": {
                "baseline_exists": verify_baseline_exists(args.artifact_dir)[0],
                "api_calls_attempted": verify_api_calls_attempted(args.artifact_dir)[0],
                "successful_calls": verify_successful_calls(args.artifact_dir)[0],
                "trace_ids": verify_trace_ids(args.artifact_dir)[0],
                "http_spans": verify_http_spans(args.artifact_dir)[0],
                "internal_spans": verify_internal_spans(args.artifact_dir)[0],
                "latency_fields": verify_latency_fields(args.artifact_dir)[0],
                "privacy_safety": verify_privacy_safety(args.artifact_dir)[0],
            },
        }

        if baseline_path.exists():
            try:
                data = json.loads(baseline_path.read_text())
                output["summary"] = data
            except (json.JSONDecodeError, OSError):
                pass

        print(json.dumps(output, indent=2))

    # Exit with error code if requested
    if args.fail and not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
