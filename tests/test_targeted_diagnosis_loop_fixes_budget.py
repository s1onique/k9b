"""Regression tests for budget-state isolation via incident ID determinism.

Tests that reset_diagnosis_loop_budget and get_budget_status correctly handle
budget files for specific incidents without affecting others.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture(autouse=True)
def fake_provider_preflight_time(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Mock time functions and shrink deadline for fast tests."""
    import scripts.lab_common.provider_preflight as provider_preflight

    now = 0.0
    sleeps: list[float] = []

    def fake_time() -> float:
        return now

    def fake_sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(float(seconds))
        now += max(float(seconds), 0.0)

    monkeypatch.setattr(provider_preflight.time, "time", fake_time)
    monkeypatch.setattr(provider_preflight.time, "sleep", fake_sleep)
    monkeypatch.setattr(provider_preflight, "PREFLIGHT_RETRY_DEADLINE_SECONDS", 1, raising=False)

    return sleeps


class TestBudgetStateIsolation:
    """Tests for budget-state isolation via incident ID determinism."""

    def test_budget_reset_clears_review_packets(self) -> None:
        """reset_diagnosis_loop_budget removes auto-{incident_id}-*-review-packet.json files."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status,
            reset_diagnosis_loop_budget,
        )

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            # Create mock budget files with deterministic incident ID
            incident_id = "test-incident-123"
            (external_analysis_dir / f"auto-{incident_id}-0-diagnosis-review-packet.json").write_text('{"findings":[]}')
            (external_analysis_dir / f"auto-{incident_id}-1-diagnosis-review-packet.json").write_text('{"findings":[]}')
            (external_analysis_dir / f"auto-{incident_id}-2-diagnosis-review-packet.json").write_text('{"findings":[]}')

            # Non-budget file should remain
            (external_analysis_dir / "other-artifact.json").write_text('{}')

            # Verify files exist
            status_before = get_budget_status(external_analysis_dir, incident_id)
            assert status_before["review_packet_count"] == 3
            assert status_before["budget_exhausted"] is True

            # Reset budget
            removed = reset_diagnosis_loop_budget(external_analysis_dir, incident_id)
            assert removed == 3

            # Verify budget files removed
            status_after = get_budget_status(external_analysis_dir, incident_id)
            assert status_after["review_packet_count"] == 0
            assert status_after["budget_clean"] is True

            # Non-budget file should remain
            assert (external_analysis_dir / "other-artifact.json").exists()

    def test_budget_status_counts_review_packets(self) -> None:
        """get_budget_status correctly counts auto-{incident_id}-*-review-packet.json files."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import get_budget_status

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            incident_id = "test-incident-456"

            # No files
            status = get_budget_status(external_analysis_dir, incident_id)
            assert status["review_packet_count"] == 0
            assert status["budget_clean"] is True
            assert status["budget_exhausted"] is False

            # Add some files
            (external_analysis_dir / f"auto-{incident_id}-0-diagnosis-review-packet.json").write_text('{"findings":[]}')
            (external_analysis_dir / f"auto-{incident_id}-1-diagnosis-review-packet.json").write_text('{"findings":[]}')

            status = get_budget_status(external_analysis_dir, incident_id)
            assert status["review_packet_count"] == 2
            assert status["budget_clean"] is False
            assert status["budget_exhausted"] is True
