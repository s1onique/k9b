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

    def test_budget_reset_clears_loop_pass_artifacts_without_review_packets(self) -> None:
        """Regression test: reset clears loop pass artifacts even when no review packets exist.

        This tests the scenario where:
        - Loop pass artifacts exist (auto-{incident_id}-*-diagnosis-loop-pass.json)
        - No review packets exist
        - Reset should still clear the loop pass artifacts
        - Backend eligibility should then pass (not budget_exhausted)
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status,
            reset_diagnosis_loop_budget,
        )

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            incident_id = "stale-loop-pass-incident"

            # Create only loop pass artifacts (no review packets)
            # These are written by the runtime orchestrator
            (external_analysis_dir / f"auto-{incident_id}-20240101-run1-diagnosis-loop-pass.json").write_text(
                '{"pass_index": 1, "decision": "stop_budget_exhausted"}'
            )
            (external_analysis_dir / f"auto-{incident_id}-20240101-run2-diagnosis-loop-pass.json").write_text(
                '{"pass_index": 2, "decision": "stop_budget_exhausted"}'
            )

            # Verify initial state - budget should be exhausted by loop pass artifacts
            status_before = get_budget_status(external_analysis_dir, incident_id)
            assert status_before["review_packet_count"] == 0, "No review packets should exist"
            assert status_before["loop_pass_count"] == 2, "Should find 2 loop pass artifacts"
            assert status_before["total_auto_artifact_count"] == 2
            assert status_before["budget_exhausted"] is True, "Budget should be exhausted"

            # Reset budget
            removed = reset_diagnosis_loop_budget(external_analysis_dir, incident_id)
            assert removed == 2, "Should remove 2 loop pass artifacts"

            # Verify reset worked
            status_after = get_budget_status(external_analysis_dir, incident_id)
            assert status_after["review_packet_count"] == 0
            assert status_after["loop_pass_count"] == 0
            assert status_after["total_auto_artifact_count"] == 0
            assert status_after["budget_clean"] is True
            assert status_after["budget_exhausted"] is False, "Budget should be clean after reset"

    def test_budget_reset_clears_mixed_artifacts(self) -> None:
        """Test that reset clears both review packets and loop pass artifacts."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status,
            reset_diagnosis_loop_budget,
        )

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            incident_id = "mixed-artifact-incident"

            # Create both review packets and loop pass artifacts
            (external_analysis_dir / f"auto-{incident_id}-1-diagnosis-review-packet.json").write_text('{"findings":[]}')
            (external_analysis_dir / f"auto-{incident_id}-2-diagnosis-review-packet.json").write_text('{"findings":[]}')
            (external_analysis_dir / f"auto-{incident_id}-1-diagnosis-loop-pass.json").write_text('{"pass": 1}')
            (external_analysis_dir / f"auto-{incident_id}-2-diagnosis-loop-pass.json").write_text('{"pass": 2}')
            # Also create a generic auto artifact with resettable suffix
            (external_analysis_dir / f"auto-{incident_id}-1-read-only-check-result.json").write_text('{"check": "result"}')

            # Verify initial state
            status_before = get_budget_status(external_analysis_dir, incident_id)
            assert status_before["review_packet_count"] == 2
            assert status_before["loop_pass_count"] == 2
            assert status_before["other_auto_count"] == 1
            assert status_before["total_auto_artifact_count"] == 5
            assert status_before["budget_exhausted"] is True

            # Reset budget
            removed = reset_diagnosis_loop_budget(external_analysis_dir, incident_id)
            assert removed == 5, "Should remove all 5 artifacts"

            # Verify everything was cleared
            status_after = get_budget_status(external_analysis_dir, incident_id)
            assert status_after["total_auto_artifact_count"] == 0
            assert status_after["budget_clean"] is True
            assert status_after["budget_exhausted"] is False

    def test_budget_status_reports_all_artifact_types(self) -> None:
        """Test that get_budget_status correctly categorizes all artifact types.
        
        Note: Snapshots (auto-{incident_id}-snapshot.json) are NOT matched by
        _matches_diagnosis_artifact because they are not in BUDGET_RESETTABLE_SUFFIXES.
        Only known budget-affecting suffixes are matched.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import get_budget_status

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            incident_id = "comprehensive-artifact-test"

            # Create various artifact types
            (external_analysis_dir / f"auto-{incident_id}-1-diagnosis-review-packet.json").write_text('{}')
            (external_analysis_dir / f"auto-{incident_id}-1-diagnosis-loop-pass.json").write_text('{}')
            (external_analysis_dir / f"auto-{incident_id}-1-read-only-check-result.json").write_text('{}')

            status = get_budget_status(external_analysis_dir, incident_id)

            # Verify categorization
            assert "review_packets" in status["artifacts"]
            assert "loop_passes" in status["artifacts"]
            assert "other_auto" in status["artifacts"]
            assert len(status["artifacts"]["review_packets"]) == 1
            assert len(status["artifacts"]["loop_passes"]) == 1
            assert len(status["artifacts"]["other_auto"]) == 1  # read-only-check-result.json

    def test_budget_reset_does_not_affect_other_incidents(self) -> None:
        """Test that reset only clears artifacts for the target incident ID."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status,
            reset_diagnosis_loop_budget,
        )

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            # Create artifacts for two different incidents
            incident_a = "incident-a"
            incident_b = "incident-b"

            (external_analysis_dir / f"auto-{incident_a}-1-diagnosis-review-packet.json").write_text('{}')
            (external_analysis_dir / f"auto-{incident_b}-1-diagnosis-review-packet.json").write_text('{}')

            # Reset only incident A
            removed = reset_diagnosis_loop_budget(external_analysis_dir, incident_a)
            assert removed == 1

            # Verify incident B's artifacts still exist
            status_b = get_budget_status(external_analysis_dir, incident_b)
            assert status_b["review_packet_count"] == 1
            assert status_b["budget_exhausted"] is True

            # Verify incident A is clean
            status_a = get_budget_status(external_analysis_dir, incident_a)
            assert status_a["review_packet_count"] == 0
            assert status_a["budget_clean"] is True

    def test_budget_reset_preserves_non_budget_auto_snapshot_artifact(self) -> None:
        """Negative regression: reset does NOT remove snapshots (auto-{incident_id}-snapshot.json).
        
        This ensures the reset helper is safe and only removes budget-affecting artifacts,
        not arbitrary auto-generated files like snapshots.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status,
            reset_diagnosis_loop_budget,
        )

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            incident_id = "snapshot-preserve-incident"

            # Create a snapshot artifact (should NOT be removed)
            snapshot = external_analysis_dir / f"auto-{incident_id}-snapshot.json"
            snapshot.write_text('{"type": "snapshot", "data": "preserved"}')

            # Create a review packet (should be removed)
            review = external_analysis_dir / f"auto-{incident_id}-1-diagnosis-review-packet.json"
            review.write_text('{"findings":[]}')

            # Verify initial state - both files exist
            assert snapshot.exists(), "Snapshot should exist before reset"
            assert review.exists(), "Review packet should exist before reset"

            # Reset budget
            removed = reset_diagnosis_loop_budget(external_analysis_dir, incident_id)
            assert removed == 1, "Should remove only 1 artifact (review packet, not snapshot)"

            # Verify snapshot is preserved but review packet is removed
            assert snapshot.exists(), "Snapshot should be preserved after reset"
            assert not review.exists(), "Review packet should be removed"

            # Verify budget status reflects only review packet was counted/removed
            status_after = get_budget_status(external_analysis_dir, incident_id)
            assert status_after["review_packet_count"] == 0
            assert status_after["total_auto_artifact_count"] == 0
            assert status_after["budget_clean"] is True
