"""Shared fixtures and helpers for incident diagnosis service tests.

This module contains common test fixtures, fake providers, and helper functions
used across all incident diagnosis service test modules.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_lifecycle import Incident

import pytest

from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,  # noqa: F401 - re-exported for use by test modules
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"


@pytest.fixture
def case_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def manifest(case_dir: Path) -> dict:
    with open(case_dir / "manifest.json") as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture
def expected(case_dir: Path) -> dict:
    with open(case_dir / "expected.json") as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture
def evidence_provider(case_dir: Path) -> GoldenCaseEvidenceProvider:
    return GoldenCaseEvidenceProvider(case_dir)


@pytest.fixture(autouse=True)
def cleanup_store() -> Generator[None, None, None]:
    """Reset incident store before and after each test."""
    reset_incident_store()
    yield
    reset_incident_store()


def _create_test_incident(
    incident_id: str,
    namespace: str = "test-namespace",
    object_kind: str = "Pod",
    object_name: str = "test-pod",
    severity: str = "medium",
) -> Incident:
    """Create a valid test incident with all required fields."""
    from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus

    now = datetime.now(UTC)
    return Incident(
        incident_id=incident_id,
        source_candidate_id=f"candidate-{incident_id}",
        namespace=namespace,
        object_kind=object_kind,
        object_name=object_name,
        raw_object_kind=None,
        candidate_class="PodFailure",
        severity=severity,
        status=IncidentStatus.OPEN,
        first_observed_at=now,
        last_observed_at=now,
    )


class FakeDiagnosisProvider:
    """Fake diagnosis provider for testing the service."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def complete(self, prompt: str) -> str:
        """Return deterministic response."""
        del prompt
        return json.dumps(self.response)


class FakeArtifactWriter:
    """Fake artifact writer that records calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.last_diagnosis: dict[str, Any] | None = None

    def write_diagnosis_artifact(
        self,
        output_dir: Path,
        incident_id: str,
        diagnosis: dict[str, Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        """Record the call and return success."""
        self.calls.append({
            "output_dir": str(output_dir),
            "incident_id": incident_id,
            "now": now.isoformat(),
        })
        self.last_diagnosis = diagnosis
        return {
            "written": True,
            "artifact_path": str(output_dir / f"{incident_id}-diagnosis.json"),
            "name": f"{incident_id}-diagnosis.json",
        }
