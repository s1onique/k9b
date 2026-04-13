#!/usr/bin/env python3
"""Export next-check execution results for batch usefulness review.

This script creates a reviewer-friendly JSON file containing executed next-check
artifacts that can be sent to an external reviewer model for batch usefulness evaluation.

Output: runs/health/diagnostic-packs/latest/next_check_usefulness_review.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from k8s_diag_agent.external_analysis.artifact import (  # noqa: E402
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)

# Schema version for the export file
EXPORT_SCHEMA_VERSION = "next-check-usefulness-review/v1"

# Directory name for the stable "latest" unpacked pack mirror
LATEST_PACK_DIR_NAME = "latest"


def export_next_check_usefulness_review(
    runs_dir: Path,
    *,
    run_id: str | None = None,
    use_run_scoped_path: bool = True,
) -> Path:
    """Export next-check execution artifacts for batch review.

    Args:
        runs_dir: Path to the runs directory (contains health/)
        run_id: Optional specific run_id to filter by. If not provided,
                uses the latest run from ui-index.json.
        use_run_scoped_path: If True (default), write to a run-scoped path.
                             The run-scoped path is: health/diagnostic-packs/{run_id}/next_check_usefulness_review.json
                             If False, writes to: health/diagnostic-packs/latest/next_check_usefulness_review.json

    Returns:
        Path to the exported JSON file.
    """
    runs_dir = runs_dir.expanduser().resolve()
    run_health_dir = runs_dir / "health"

    # Determine the run_id to use
    if not run_id:
        run_id = _find_latest_run_id(run_health_dir)

    if not run_id:
        raise ValueError("Could not determine run_id. Provide --run-id or ensure ui-index.json exists.")

    # Load run metadata from ui-index.json
    index_path = run_health_dir / "ui-index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"UI index missing: {index_path}")

    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    run_entry = index_data.get("run", {})
    run_label = str(run_entry.get("run_label") or run_id)

    # Collect next-check execution artifacts
    external_analysis_dir = run_health_dir / "external-analysis"
    if not external_analysis_dir.exists():
        raise FileNotFoundError(f"External analysis directory missing: {external_analysis_dir}")

    # Find all next-check-execution artifacts for this run
    execution_artifacts: list[ExternalAnalysisArtifact] = []
    for artifact_file in external_analysis_dir.glob("*.json"):
        if run_id not in artifact_file.name:
            continue
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            artifact = ExternalAnalysisArtifact.from_dict(artifact_data)
            if artifact.purpose == ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION:
                execution_artifacts.append(artifact)
        except (json.JSONDecodeError, KeyError, ValueError):
            # Skip malformed artifacts
            continue

    # Build export entries
    entries = []
    for artifact in sorted(execution_artifacts, key=lambda a: a.timestamp):
        entry = _build_export_entry(artifact, run_health_dir)
        entries.append(entry)

    # Build export document
    export_data = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_label": run_label,
        "generated_at": datetime.now(UTC).isoformat(),
        "entry_count": len(entries),
        "entries": entries,
    }

    # Determine output directory based on use_run_scoped_path flag
    if use_run_scoped_path:
        # Run-scoped path: health/diagnostic-packs/{run_id}/next_check_usefulness_review.json
        output_dir = run_health_dir / "diagnostic-packs" / run_id
    else:
        # Latest path: health/diagnostic-packs/latest/next_check_usefulness_review.json
        output_dir = run_health_dir / "diagnostic-packs" / LATEST_PACK_DIR_NAME

    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "next_check_usefulness_review.json"
    output_path.write_text(json.dumps(export_data, indent=2), encoding="utf-8")

    # Log structured event for observability
    _log_export_event(
        event="usefulness-review-exported",
        message=f"Exported usefulness review to {output_path}",
        run_id=run_id,
        run_label=run_label,
        metadata={
            "output_path": str(output_path),
            "output_dir": str(output_dir),
            "use_run_scoped_path": use_run_scoped_path,
            "entry_count": len(entries),
            "file_exists": output_path.exists(),
        },
    )

    return output_path


def _log_export_event(
    *,
    event: str,
    message: str,
    run_id: str,
    run_label: str,
    metadata: dict[str, object],
    severity: str = "INFO",
) -> None:
    """Emit a structured log event for usefulness review export."""
    # Import here to avoid circular imports
    import sys
    from pathlib import Path as PathLocal

    ROOT = PathLocal(__file__).resolve().parents[1]
    SRC_PATH = ROOT / "src"
    if str(SRC_PATH) not in sys.path:
        sys.path.insert(0, str(SRC_PATH))

    try:
        from k8s_diag_agent.structured_logging import emit_structured_log

        emit_structured_log(
            component="usefulness-review-export",
            message=message,
            severity=severity,
            run_id=run_id,
            run_label=run_label,
            metadata=metadata,
            event=event,
        )
    except ImportError:
        # Fallback to print if structured logging not available
        print(f"[{severity}] {message}: {metadata}")


def _find_latest_run_id(run_health_dir: Path) -> str | None:
    """Find the run_id from the current ui-index.json."""
    index_path = run_health_dir / "ui-index.json"
    if not index_path.exists():
        return None

    try:
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        run_entry = index_data.get("run", {})
        return str(run_entry.get("run_id")) if run_entry.get("run_id") else None
    except (json.JSONDecodeError, ValueError):
        return None


def _build_export_entry(
    artifact: ExternalAnalysisArtifact,
    run_health_dir: Path,
) -> dict[str, object]:
    """Build a single export entry from an execution artifact."""
    # Extract payload data
    payload = artifact.payload or {}

    # Get candidate info from payload
    candidate_id = payload.get("candidateId") or payload.get("candidate_id")
    candidate_index = payload.get("candidateIndex") or payload.get("candidate_index")

    # Build command preview
    description = payload.get("candidate_description") or payload.get("description")
    command_family = payload.get("command_family") or payload.get("suggested_command_family")
    command_preview = payload.get("command_preview")

    # Determine execution status
    execution_status = _determine_execution_status(artifact)

    # Get result summary and suggested move
    result_summary = artifact.summary
    suggested_next_operator_move = _extract_suggested_move(artifact, payload)

    # Get artifact path relative to run_health_dir
    artifact_path = None
    if artifact.artifact_path:
        try:
            artifact_path = str(Path(artifact.artifact_path).relative_to(run_health_dir))
        except ValueError:
            artifact_path = str(artifact.artifact_path)

    return {
        "artifact_path": artifact_path,
        "run_id": artifact.run_id,
        "run_label": artifact.run_label,
        "candidate_id": candidate_id,
        "candidate_index": candidate_index,
        "cluster_label": artifact.cluster_label,
        "command_preview": command_preview,
        "command_family": command_family,
        "description": description,
        "execution_status": execution_status,
        "timed_out": artifact.timed_out,
        "status": artifact.status.value,
        "result_summary": result_summary,
        "suggested_next_operator_move": suggested_next_operator_move,
        "timestamp": artifact.timestamp.isoformat(),
        # Include usefulness if already set (for incremental review)
        "usefulness_class": artifact.usefulness_class.value if artifact.usefulness_class else None,
        "usefulness_summary": artifact.usefulness_summary,
    }


def _determine_execution_status(artifact: ExternalAnalysisArtifact) -> str:
    """Determine the execution status string."""
    if artifact.timed_out:
        return "timed-out"
    if artifact.status == ExternalAnalysisStatus.SUCCESS:
        return "success"
    if artifact.status == ExternalAnalysisStatus.FAILED:
        return "failed"
    if artifact.status == ExternalAnalysisStatus.SKIPPED:
        return "skipped"
    return str(artifact.status.value)


def _extract_suggested_move(
    artifact: ExternalAnalysisArtifact,
    payload: dict[str, object],
) -> str | None:
    """Extract the suggested next operator move from the artifact."""
    # First try payload
    if payload:
        suggested = payload.get("suggestedNextOperatorMove") or payload.get("suggested_next_operator_move")
        if suggested:
            return str(suggested)

    # Then try direct artifact fields
    if artifact.summary:
        # Extract from summary if it contains a suggested action
        return str(artifact.summary)

    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export next-check execution results for batch usefulness review."
    )
    parser.add_argument(
        "--runs-dir",
        required=True,
        help="Path to the runs directory (contains health/)",
    )
    parser.add_argument(
        "--run-id",
        help="Specific run_id to export. If not provided, uses latest run from ui-index.json",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs_dir = Path(args.runs_dir)

    try:
        output_path = export_next_check_usefulness_review(
            runs_dir,
            run_id=args.run_id,
        )
        print(f"Exported to: {output_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()