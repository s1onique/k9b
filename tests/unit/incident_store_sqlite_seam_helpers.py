"""Shared test helpers for SQLite capability seam tests.

This module provides utilities for testing SQLiteIncidentStore and its
write context capability seam.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)


def make_candidate(
    name: str,
    namespace: str = "default",
    candidate_class: CandidateClass = CandidateClass.CRASH_LOOP,
) -> IncidentCandidate:
    """Helper to create test candidates."""
    return IncidentCandidate(
        candidate_id=f"{namespace}-{ObjectKind.POD.value.lower()}-{name}-{candidate_class.value}",
        namespace=namespace,
        object_kind=ObjectKind.POD,
        object_name=name,
        candidate_class=candidate_class,
        severity=Severity.ERROR,
        signals=(
            CandidateSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="Back-off restarting",
            ),
        ),
        evidence_needed=("pod_logs", "pod_describe"),
        raw_object_kind=None,
    )


class TempDbContext:
    """Context manager for temporary database cleanup."""

    def __init__(self) -> None:
        self._temp_dir: str | None = None
        self._db_path: Path | None = None

    def setup(self) -> Path:
        """Set up temporary database path."""
        self._temp_dir = tempfile.mkdtemp()
        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
        return self._db_path

    def cleanup(self) -> None:
        """Clean up temporary directory."""
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    @property
    def db_path(self) -> Path:
        """Get the database path."""
        if self._db_path is None:
            raise RuntimeError("TempDbContext.setup() must be called first")
        return self._db_path


__all__ = [
    "make_candidate",
    "TempDbContext",
]
