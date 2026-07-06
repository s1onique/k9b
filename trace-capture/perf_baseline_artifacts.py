"""Artifact writing for perf_baseline module.

This module contains:
- Baseline artifact writing (JSON, summary, trace IDs, spans)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perf_baseline_contract import BaselineSummary


def write_baseline_artifacts(
    summary: BaselineSummary,
    spans_jsonl: list[dict[str, Any]],
    artifact_dir: Path,
) -> dict[str, Path]:
    """Write baseline artifacts to disk.

    Args:
        summary: Baseline summary
        spans_jsonl: List of span breakdown records
        artifact_dir: Directory to write to

    Returns:
        Dictionary mapping artifact name to path
    """
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    # Write main baseline
    baseline_path = artifact_dir / "backend-api-baseline.json"
    baseline_path.write_text(json.dumps(summary.to_dict(), indent=2))
    paths["baseline"] = baseline_path

    # Write summary
    summary_path = artifact_dir / "backend-api-baseline-summary.json"
    summary_data = {
        "schema_version": summary.schema_version,
        "generated_at": summary.generated_at,
        "total_traces": summary.total_traces,
        "total_spans": summary.total_spans,
        "http_span_count": summary.http_span_count,
        "internal_span_count": summary.internal_span_count,
        "slowest_endpoint": summary.slowest_endpoint,
        "iteration_count": summary.iteration_count,
        "warmup_count": summary.warmup_count,
        "endpoint_count": len(summary.benchmarked_endpoints),
    }
    summary_path.write_text(json.dumps(summary_data, indent=2))
    paths["summary"] = summary_path

    # Write trace IDs
    trace_ids_path = artifact_dir / "backend-api-baseline-trace-ids.txt"
    trace_ids: set[str] = set()
    for endpoint in summary.benchmarked_endpoints:
        trace_ids.update(endpoint.get("trace_ids", []))
    trace_ids_path.write_text("\n".join(sorted(trace_ids)))
    paths["trace_ids"] = trace_ids_path

    # Write spans JSONL
    spans_path = artifact_dir / "backend-api-baseline-spans.jsonl"
    with open(spans_path, "w") as f:
        for span in spans_jsonl:
            f.write(json.dumps(span) + "\n")
    paths["spans"] = spans_path

    return paths
