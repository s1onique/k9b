"""Shared fixtures for incident_next_check_artifact tests.

This module provides reusable test helpers for creating test incidents
with signals and writing plan artifacts to temp directories.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentSignal, IncidentStatus


def make_incident_with_signals(signals: list[IncidentSignal]) -> Incident:
    """Create a test incident with the given signals."""
    return Incident(
        incident_id="test-incident",
        source_candidate_id="cand-001",
        namespace="default",
        object_kind="Pod",
        object_name="my-pod",
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="high",
        status=IncidentStatus.OPEN,
        first_observed_at=datetime.now(UTC),
        last_observed_at=datetime.now(UTC),
        signals=signals,
    )


def make_incident_with_run_ids(run_ids: list[str | None]) -> Incident:
    """Create a test incident with signals having the given run_ids."""
    signals = []
    for run_id in run_ids:
        signals.append(
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="restarting",
                captured_at=datetime.now(UTC),
                run_id=run_id,
            )
        )
    return make_incident_with_signals(signals)


def write_plan_artifact(external_dir: Path, run_id: str, payload: dict) -> Path:
    """Write a plan artifact to the external_analysis directory.

    Returns the path to the written file.
    """
    external_dir.mkdir(parents=True, exist_ok=True)
    path = external_dir / f"{run_id}-next-check-plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_basic_plan_payload(run_id: str, candidates: list[dict] | None = None) -> dict:
    """Create a basic valid plan payload for testing."""
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": candidates or [
            {
                "linkage_status": "linked",
                "incident_id": "test-incident",
                "candidateId": f"check-{run_id}",
                "description": f"Check for {run_id}",
            },
        ],
    }
