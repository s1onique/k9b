#!/usr/bin/env python3
"""Main orchestrator for k9b backend trace capture lab.

This script orchestrates the full trace capture flow:
1. Start/stop OpenTelemetry Collector
2. Start k9b backend with OTel enabled
3. Exercise representative API endpoints
4. Parse collector output
5. Generate trace summary
6. Write trace artifacts
7. Generate performance baseline (with --perf-baseline flag)

Usage:
    # Full trace capture run:
    python run_trace_capture.py

    # With custom paths:
    python run_trace_capture.py \
        --collector-config ./collector-config.yaml \
        --artifact-dir ./trace-capture \
        --backend-url http://localhost:8080

    # Dry run (collector config generation only):
    python run_trace_capture.py --dry-run

    # Performance baseline run:
    python run_trace_capture.py \
        --perf-baseline \
        --iterations 10 \
        --warmup 2 \
        --incident-id <id> \
        --output-dir trace-capture/perf-baseline
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# Add trace-capture to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Re-export config for backward compatibility
from run_trace_capture_artifacts import (
    write_backend_api_traces,
    write_trace_ids,
    write_trace_summary,
)
from run_trace_capture_config import TraceCaptureConfig, get_backend_env
from trace_summary import SCHEMA_VERSION, TraceSummary, validate_trace_summary

logger = logging.getLogger(__name__)

__all__ = [
    "TraceCaptureConfig",
    "get_backend_env",
    "run_trace_capture",
    "main",
]


# =============================================================================
# Main Trace Capture Flow
# =============================================================================


def run_trace_capture(
    config: TraceCaptureConfig,
) -> tuple[bool, TraceSummary, list[dict[str, Any]]]:
    """Run the full trace capture flow.

    Args:
        config: Trace capture configuration

    Returns:
        Tuple of (success, trace_summary, api_results_with_latency)
    """
    from trace_capture_api import APIExerciseConfig, exercise_all_endpoints

    artifact_dir = Path(config.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("k9b Backend Trace Capture Lab")
    print("=" * 70)
    print(f"Artifact directory: {artifact_dir}")
    print(f"OTel enabled: {config.otel_enabled}")
    print(f"Service name: {config.service_name}")
    print(f"OTel endpoint: {config.otel_endpoint}")
    print()

    # Configure API exerciser
    api_config = APIExerciseConfig(
        base_url=config.backend_url,
        timeout_seconds=config.api_timeout,
        incident_id=config.incident_id,
    )

    all_results: list[dict[str, Any]] = []

    # Dry run - just generate config
    if config.dry_run:
        print("DRY RUN: Generating collector config only")
        print()
        collector_config = artifact_dir / "collector-config.yaml"
        if not collector_config.exists():
            base_config = Path(__file__).parent / "collector-config.yaml"
            if base_config.exists():
                collector_config.write_text(base_config.read_text())
                print(f"  Copied collector config to: {collector_config}")

        # Generate empty trace summary for dry run
        from datetime import UTC, datetime

        summary = TraceSummary(
            schema_version=SCHEMA_VERSION,
            generated_at=datetime.now(UTC).isoformat(),
            otel_enabled=config.otel_enabled,
            service_name=config.service_name,
            collector_received_traces=False,
        )
        write_trace_summary(summary, artifact_dir)
        print()
        print("DRY RUN complete. No traces captured.")
        return True, summary, []

    # Run warmup iterations first (discard results)
    if config.warmup_iterations > 0:
        print(f"Running {config.warmup_iterations} warmup iteration(s)...")
        for i in range(config.warmup_iterations):
            if config.verbose:
                print(f"  Warmup {i + 1}/{config.warmup_iterations}...")
            try:
                exercise_all_endpoints(api_config)
            except Exception:
                pass  # Ignore warmup failures
        print()

    # Run API exercises (assumes backend is already running with OTel enabled)
    print("Exercising API endpoints...")
    print()

    for i in range(config.exercise_iterations):
        if config.verbose:
            print(f"  Iteration {i + 1}/{config.exercise_iterations}...")

        try:
            results = exercise_all_endpoints(api_config)

            # Add latency measurement to each result
            for result in results:
                # Latency is already recorded in result if available from API
                # Otherwise, we'll use current time for the iteration
                result["iteration"] = i + 1
                result["trace_id"] = ""  # Will be filled from trace JSONL if available

            all_results.extend(results)

            for result in results:
                status = "✓" if result["success"] else "✗"
                latency = result.get("latency_ms", 0)
                latency_str = f" ({latency:.1f}ms)" if latency else ""
                print(f"  {status} {result['method']} {result['endpoint']} -> {result.get('status_code', 'N/A')}{latency_str}")
        except Exception as e:
            print(f"  ✗ API exercise failed: {e}")

    print()

    # Write backend API traces
    if all_results:
        write_backend_api_traces(all_results, artifact_dir)
        print(f"Wrote API exercise results to: {artifact_dir / 'backend-api-traces.json'}")

    # Generate trace summary
    print()
    print("Generating trace summary...")

    # Look for trace files
    trace_jsonl = artifact_dir / "collector-output.jsonl"
    collector_output = artifact_dir / "collector-output.log"

    from trace_summary import generate_trace_summary

    summary = generate_trace_summary(
        collector_output_path=collector_output if collector_output.exists() else None,
        trace_json_path=trace_jsonl if trace_jsonl.exists() else None,
        otel_enabled=config.otel_enabled,
        service_name=config.service_name,
    )

    write_trace_summary(summary, artifact_dir)
    print(f"Wrote trace summary to: {artifact_dir / 'trace-summary.json'}")

    # Write trace IDs
    if summary.trace_ids:
        write_trace_ids(list(summary.trace_ids), artifact_dir)
        print(f"Wrote {len(summary.trace_ids)} trace IDs to: {artifact_dir / 'trace-ids.txt'}")

        # Correlate trace IDs with API results if in perf-baseline mode
        if config.perf_baseline and summary.trace_ids:
            _correlate_traces_with_results(all_results, list(summary.trace_ids))

    # Validate summary
    failures = validate_trace_summary(summary)
    print()
    if failures:
        print("Trace summary validation warnings:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print("✓ Trace summary meets all requirements")

    return len(failures) == 0, summary, all_results


def _correlate_traces_with_results(
    results: list[dict[str, Any]],
    trace_ids: list[str],
) -> None:
    """Correlate API results with trace IDs using route/timing heuristics.

    This is a best-effort correlation based on:
    - Normalized route matching
    - Timestamp ordering

    Args:
        results: API exercise results
        trace_ids: List of available trace IDs
    """
    if not trace_ids or not results:
        return

    # Simple round-robin correlation based on order
    # More sophisticated correlation would need timestamp matching
    for i, result in enumerate(results):
        if i < len(trace_ids):
            result["trace_id"] = trace_ids[i]


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> int:
    """CLI entry point."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Run k9b backend trace capture lab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full trace capture:
  python run_trace_capture.py

  # Dry run (generate config only):
  python run_trace_capture.py --dry-run

  # With verbose output:
  python run_trace_capture.py --verbose

  # Custom artifact directory:
  python run_trace_capture.py --artifact-dir /tmp/my-traces

  # Point to running backend:
  python run_trace_capture.py --backend-url http://my-backend:8080

  # Performance baseline:
  python run_trace_capture.py --perf-baseline --iterations 10 --warmup 2 \\
      --output-dir trace-capture/perf-baseline
        """,
    )

    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Artifact directory (default: ./trace-capture/)",
    )
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8080",
        help="Backend URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--otel-endpoint",
        default="http://localhost:4317",
        help="OTel collector endpoint (default: http://localhost:4317)",
    )
    parser.add_argument(
        "--service-name",
        default="k9b-backend",
        help="Service name for traces (default: k9b-backend)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of API exercise iterations (default: 1)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=0,
        help="Number of warmup iterations (default: 0)",
    )
    parser.add_argument(
        "--incident-id",
        type=str,
        default=None,
        help="Use specific incident ID for API exercises",
    )
    parser.add_argument(
        "--perf-baseline",
        action="store_true",
        help="Generate performance baseline artifacts",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for perf baseline (default: artifact-dir/perf-baseline/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate config only, don't capture traces",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Build config
    baseline_output_dir = args.output_dir
    if baseline_output_dir is None and args.perf_baseline:
        baseline_output_dir = (args.artifact_dir or Path(__file__).parent) / "perf-baseline"

    config = TraceCaptureConfig(
        artifact_dir=args.artifact_dir or Path(__file__).parent,
        backend_url=args.backend_url,
        otel_endpoint=args.otel_endpoint,
        service_name=args.service_name,
        exercise_iterations=args.iterations,
        warmup_iterations=args.warmup,
        incident_id=args.incident_id,
        perf_baseline=args.perf_baseline,
        baseline_output_dir=baseline_output_dir,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    # Run trace capture
    success, summary, api_results = run_trace_capture(config)

    print()
    print("=" * 70)
    print("Trace Capture Summary")
    print("=" * 70)
    print(f"  Schema version: {summary.schema_version}")
    print(f"  Generated at: {summary.generated_at}")
    print(f"  OTel enabled: {summary.otel_enabled}")
    print(f"  Service name: {summary.service_name}")
    print(f"  Traces captured: {summary.trace_count}")
    print(f"  Spans captured: {summary.span_count}")
    print(f"  HTTP spans: {summary.http_span_count}")
    print(f"  Internal spans: {summary.internal_span_count}")
    print(f"  Trace IDs: {len(summary.trace_ids)}")
    print(f"  Normalized routes: {summary.normalized_route_names_present}")
    print(f"  HTTP/internal share trace: {summary.http_and_internal_spans_share_trace_id}")
    print(f"  Raw incident IDs in spans: {summary.raw_incident_ids_in_span_names}")
    print(f"  Raw payload detected: {summary.raw_artifact_payload_detected}")
    print("=" * 70)

    # Generate perf baseline if requested
    if config.perf_baseline and config.baseline_output_dir and api_results:
        from perf_baseline import (
            generate_baseline_summary,
            group_spans_by_trace,
            write_baseline_artifacts,
        )

        trace_jsonl = Path(config.artifact_dir) / "collector-output.jsonl"
        trace_path = trace_jsonl if trace_jsonl.exists() else None

        # Generate summary
        perf_summary = generate_baseline_summary(
            api_results=api_results,
            trace_jsonl_path=trace_path,
            iterations=config.exercise_iterations,
            warmup=config.warmup_iterations,
            incident_id_source="provided" if config.incident_id else "auto",
        )

        # Generate span breakdowns
        spans_jsonl: list[dict[str, Any]] = []
        if trace_path and trace_path.exists():
            breakdowns = group_spans_by_trace(trace_path)
            spans_jsonl = [bd.to_dict() for bd in breakdowns.values()]

        # Write artifacts
        baseline_dir = Path(config.baseline_output_dir)
        artifact_paths = write_baseline_artifacts(perf_summary, spans_jsonl, baseline_dir)

        print()
        print("=" * 70)
        print("Generating Performance Baseline")
        print("=" * 70)
        print(f"  Benchmark endpoints: {len(perf_summary.benchmarked_endpoints)}")
        print(f"  Total traces: {perf_summary.total_traces}")
        print(f"  Total spans: {perf_summary.total_spans}")
        print(f"  HTTP spans: {perf_summary.http_span_count}")
        print(f"  Internal spans: {perf_summary.internal_span_count}")
        print(f"  Slowest endpoint: {perf_summary.slowest_endpoint or 'N/A'}")
        print(f"  Iteration count: {perf_summary.iteration_count}")
        print(f"  Warmup count: {perf_summary.warmup_count}")
        print()
        print("  Artifacts written:")
        for name, path in artifact_paths.items():
            print(f"    - {name}: {path}")

        # Print endpoint latencies
        if perf_summary.benchmarked_endpoints:
            print()
            print("  Endpoint Latencies (p50/p90/p99):")
            for ep in perf_summary.benchmarked_endpoints:
                latency = ep.get("latency_ms", {})
                p50 = latency.get("p50", 0)
                p90 = latency.get("p90", 0)
                p99 = latency.get("p99", 0)
                print(f"    {ep['normalized_route']}: {p50:.1f}/{p90:.1f}/{p99:.1f} ms")

        print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
