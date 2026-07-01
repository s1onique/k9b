"""Unit tests for incident_diagnosis_auto_loop config - budget discovery parity.

Tests cover budget artifact discovery parity between backend and lab helper.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    check_incident_eligibility,
)
from k8s_diag_agent.collect.incident_lifecycle import Incident
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
    get_budget_status_in_backend,
    get_budget_status_local,
)


@pytest.fixture
def clean_store() -> Iterator[IncidentStore]:
    """Provide a clean incident store for each test."""
    store = IncidentStore()
    set_incident_store(store)
    yield store
    set_incident_store(None)


@pytest.fixture
def temp_external_dir() -> Iterator[Path]:
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_open_incident(clean_store: IncidentStore) -> Iterator[Incident]:
    """Create a sample open incident for testing."""
    from k8s_diag_agent.collect.incident_candidates import (
        CandidateClass,
        CandidateSignal,
        IncidentCandidate,
        ObjectKind,
        Severity,
    )
    from k8s_diag_agent.collect.incident_lifecycle import open_incident_from_candidate

    candidate = IncidentCandidate(
        candidate_id="test-candidate-1",
        namespace="default",
        object_kind=ObjectKind.POD,
        object_name="failing-pod",
        raw_object_kind="Pod",
        candidate_class=CandidateClass.CRASH_LOOP,
        severity=Severity.WARNING,
        signals=(
            CandidateSignal(
                source="test",
                reason="test_reason",
                message="Test signal for auto loop",
            ),
        ),
        evidence_needed=("check_logs",),
    )

    incident = open_incident_from_candidate(candidate, datetime.now(UTC))
    clean_store._incidents[incident.incident_id] = incident
    yield incident


class TestBudgetDiscoveryParity:
    """Regression tests for budget artifact discovery parity between backend and lab helper."""

    def test_eligibility_discovers_nested_review_packets(
        self,
        clean_store: IncidentStore,
        sample_open_incident: Incident,
        temp_external_dir: Path,
    ) -> None:
        """Prove eligibility check discovers review packets in nested directories."""
        incident_id = sample_open_incident.incident_id

        # Create nested artifact structure like P4c writes
        nested_dir = temp_external_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        nested_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact in nested path
        artifact_name = f"auto-{incident_id}-20260107-123456-abc123-diagnosis-review-packet.json"
        (nested_dir / artifact_name).write_text('{"test": true}')

        # Check eligibility - must find nested artifact
        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(incident_id, config, temp_external_dir)

        assert result.eligible is False
        assert result.reason == "budget_exhausted"
        assert result.auto_pass_count == 1

        # Verify budget diagnostics show correct count
        assert len(result.budget_diagnostics) == 1
        diag = result.budget_diagnostics[0]
        assert diag.name == "review_packet_budget"
        assert diag.used == 1
        assert diag.limit == 1
        assert diag.exhausted is True
        assert diag.source == "review_packet_artifacts"
        assert diag.resettable is True

    def test_local_budget_reset_removes_nested_artifacts(
        self,
        clean_store: IncidentStore,
        sample_open_incident: Incident,
        temp_external_dir: Path,
    ) -> None:
        """Prove reset_diagnosis_loop_budget_local removes nested artifacts."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status_local,
            reset_diagnosis_loop_budget_local,
        )

        incident_id = sample_open_incident.incident_id

        # Create runs/health/external-analysis/ structure
        runs_dir = temp_external_dir / "runs"
        health_root = runs_dir / "health"
        external_analysis_dir = health_root / "external-analysis"
        nested_dir = external_analysis_dir / "phase4-diagnosis"
        nested_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact in nested layout
        artifact_name = f"auto-{incident_id}-20260107-123456-abc123-diagnosis-review-packet.json"
        (nested_dir / artifact_name).write_text('{"test": true}')

        # Verify local budget status sees the artifact
        status_before = get_budget_status_local(runs_dir, incident_id)
        assert status_before["review_packet_count"] == 1
        assert status_before["budget_exhausted"] is True

        # Reset via local function
        result = reset_diagnosis_loop_budget_local(runs_dir, incident_id)
        assert result.reset_file_count == 1
        assert result.execution_context == "local_filesystem"

        # Verify artifact was actually removed
        status_after = get_budget_status_local(runs_dir, incident_id)
        assert status_after["review_packet_count"] == 0
        assert status_after["budget_exhausted"] is False


class TestBudgetStatusSchema:
    """Schema consistency tests between backend script and parser."""

    def test_backend_status_parser_honors_status_script_schema(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Backend status must handle correct schema keys: exists, other_auto_count."""
        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps({
                    "exists": True,
                    "review_packet_count": 1,
                    "loop_pass_count": 0,
                    "other_auto_count": 1,
                    "budget_exhausted": True,
                }),
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        status = get_budget_status_in_backend(
            kubeconfig="/tmp/kubeconfig",
            namespace="k9b",
            incident_id="otel-demo-deployment-shipping-deployment_unavailable",
        )

        assert status["budget_clean"] is False
        assert status["review_packet_count"] == 1
        assert status["other_auto_count"] == 1
        assert status["total_auto_artifact_count"] == 2

    def test_local_budget_status_does_not_count_snapshot(self, tmp_path: Path) -> None:
        """Local status must not count non-budget files like snapshots."""
        incident_id = "otel-demo-deployment-shipping-deployment_unavailable"
        external = tmp_path / "runs" / "health" / "external-analysis"
        external.mkdir(parents=True)

        # Snapshot is NOT a budget-affecting artifact
        (external / f"auto-{incident_id}-snapshot.json").write_text("{}")

        status = get_budget_status_local(tmp_path / "runs", incident_id)

        assert status["total_auto_artifact_count"] == 0
        assert status["budget_exhausted"] is False
