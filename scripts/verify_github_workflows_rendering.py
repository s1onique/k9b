"""Terminal rendering helpers for GitHub workflow verification."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any


@dataclass(frozen=True)
class WorkflowError:
    """Structured error from workflow verification."""

    workflow_path: Path
    job_id: str | None = None
    step_index: int | None = None
    step_name: str | None = None
    error_type: str = "ERROR"
    message: str = ""

    def __str__(self) -> str:
        parts = [f"{self.error_type} in {self.workflow_path}"]
        for attr in ("job_id", "step_index", "step_name"):
            val = getattr(self, attr)
            if val is not None:
                parts.append(f"{attr.replace('_', ' ')} '{val}'" if isinstance(val, str) else f"{attr}[{val}]")
        parts.append(f": {self.message}")
        return " | ".join(parts)


def format_skipped_shells_report(
    skipped_shells: Sequence[tuple[WorkflowError, str]],
) -> str:
    """Format a report of skipped shell checks (non-bash shells)."""
    if not skipped_shells:
        return ""
    return (
        "\nSkipped shell checks (explicit non-bash shells):\n"
        + "\n".join(f"  - {detail}" for _, detail in skipped_shells)
        + "\n"
    )


def print_errors(errors: Sequence[WorkflowError], file: IO[Any] | None = None) -> None:
    """Print all errors to the given file (default: stderr)."""
    if file is None:
        file = sys.stderr
    for error in errors:
        print(error, file=file)


def print_warnings(warnings: Sequence[WorkflowError], file: IO[Any] | None = None) -> None:
    """Print all warnings to the given file (default: stderr)."""
    if file is None:
        file = sys.stderr
    for warning in warnings:
        print(warning, file=file)


def print_workflow_results(
    *,
    errors: Sequence[WorkflowError],
    warnings: Sequence[WorkflowError],
    skipped_shells: Sequence[tuple[WorkflowError, str]],
    ok: bool,
    file: IO[Any] | None = None,
) -> None:
    """Print formatted workflow verification results to the given file (default: stderr)."""
    if file is None:
        file = sys.stderr

    if errors:
        print(f"Found {len(errors)} error(s):", file=file)
        print_errors(errors, file=file)

    if skipped_shells:
        print(format_skipped_shells_report(skipped_shells), end="", file=file)

    print(f"\nWorkflow verification: {'PASS' if ok else 'FAIL'}", file=file)
