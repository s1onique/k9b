#!/usr/bin/env python3
"""Import batch usefulness feedback for executed next checks.

This script reads a JSON file containing batch usefulness judgments and applies
them to existing next-check-execution artifacts.

Input: JSON file with usefulness feedback (schema: next-check-usefulness-feedback/v1)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from k8s_diag_agent.external_analysis.artifact import (  # noqa: E402
    ExternalAnalysisPurpose,
    UsefulnessClass,
)

# Schema version for the import file
IMPORT_SCHEMA_VERSION = "next-check-usefulness-feedback/v1"

# Supported usefulness classes (must match the contract)
SUPPORTED_USEFULNESS_CLASSES = frozenset({
    UsefulnessClass.USEFUL.value,
    UsefulnessClass.PARTIAL.value,
    UsefulnessClass.NOISY.value,
    UsefulnessClass.EMPTY.value,
})


def import_next_check_usefulness_feedback(
    runs_dir: Path,
    input_file: Path,
) -> tuple[int, int]:
    """Import batch usefulness feedback for next-check executions.

    Args:
        runs_dir: Path to the runs directory (contains health/)
        input_file: Path to the JSON file containing usefulness feedback

    Returns:
        Tuple of (success_count, error_count)
    """
    runs_dir = runs_dir.expanduser().resolve()
    run_health_dir = runs_dir / "health"

    # Read and validate input file
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    input_data = json.loads(input_file.read_text(encoding="utf-8"))

    # Validate schema version
    schema_version = input_data.get("schema_version")
    if schema_version != IMPORT_SCHEMA_VERSION:
        raise ValueError(
            f"Invalid schema version: {schema_version!r}. "
            f"Expected: {IMPORT_SCHEMA_VERSION!r}"
        )

    # Validate entries exist
    entries = input_data.get("entries")
    if not entries or not isinstance(entries, list):
        raise ValueError("Input file must contain a non-empty 'entries' list")

    success_count = 0
    error_count = 0

    # Process each entry
    for idx, entry in enumerate(entries):
        try:
            _process_entry(entry, run_health_dir)
            success_count += 1
        except ValueError as e:
            error_count += 1
            print(f"Error in entry {idx}: {e}", file=sys.stderr)

    return success_count, error_count


def _process_entry(entry: dict[str, object], run_health_dir: Path) -> None:
    """Process a single feedback entry.

    Args:
        entry: The feedback entry from the input file
        run_health_dir: Path to the health directory

    Raises:
        ValueError: If the entry is invalid
    """
    # Validate required fields
    artifact_path_raw = entry.get("artifact_path")
    if not artifact_path_raw or not isinstance(artifact_path_raw, str):
        raise ValueError("Missing or invalid field: artifact_path")
    artifact_path: str = artifact_path_raw

    usefulness_class_raw = entry.get("usefulness_class")
    if not usefulness_class_raw or not isinstance(usefulness_class_raw, str):
        raise ValueError("Missing or invalid field: usefulness_class")
    usefulness_class: str = usefulness_class_raw

    # Validate usefulness_class is supported
    if usefulness_class not in SUPPORTED_USEFULNESS_CLASSES:
        raise ValueError(
            f"Invalid usefulness_class: {usefulness_class!r}. "
            f"Must be one of: {sorted(SUPPORTED_USEFULNESS_CLASSES)}"
        )

    # Resolve the artifact path
    full_artifact_path = run_health_dir / artifact_path

    # Validate artifact exists
    if not full_artifact_path.exists():
        raise ValueError(f"Artifact not found: {artifact_path}")

    # Load the artifact
    try:
        artifact_data = json.loads(full_artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in artifact: {artifact_path}") from e

    # Validate purpose is next-check-execution
    purpose = artifact_data.get("purpose")
    if purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION.value:
        raise ValueError(
            f"Artifact purpose is {purpose!r}, not {ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION.value}: {artifact_path}"
        )

    # Update usefulness fields
    artifact_data["usefulness_class"] = usefulness_class
    usefulness_summary = entry.get("usefulness_summary")
    if usefulness_summary:
        artifact_data["usefulness_summary"] = usefulness_summary
    else:
        # Remove if previously set and now empty
        artifact_data.pop("usefulness_summary", None)

    # Write the updated artifact back
    full_artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import batch usefulness feedback for next-check executions."
    )
    parser.add_argument(
        "--runs-dir",
        required=True,
        help="Path to the runs directory (contains health/)",
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to the JSON file containing usefulness feedback",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs_dir = Path(args.runs_dir)
    input_file = Path(args.input_file)

    try:
        success_count, error_count = import_next_check_usefulness_feedback(
            runs_dir,
            input_file,
        )

        print(f"Import complete: {success_count} succeeded, {error_count} errors")

        if error_count > 0:
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()