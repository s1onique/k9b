"""Regression tests for budget reset nested path discovery.

Bug: Budget reset only scanned top-level files in external_analysis_dir,
missing artifacts in nested paths like:
- health/external-analysis/auto-{incident_id}-*-diagnosis-review-packet.json
- health/external-analysis/phase4-diagnosis/auto-{incident_id}-*-diagnosis-review-packet.json

The backend's eligibility check uses rglob-style discovery, causing a
source-of-truth mismatch where reset reports 0 files but backend still
returns budget_exhausted.

Fix: Use rglob to discover artifacts in all nested directories.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


class TestBudgetResetNestedPaths:
    """Tests for budget reset nested path discovery."""

    def test_reset_discovers_artifacts_in_nested_paths(self) -> None:
        """Test that reset_diagnosis_loop_budget finds artifacts in nested directories."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            reset_diagnosis_loop_budget,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            incident_id = "otel-demo-deployment-shipping-deployment_unavailable"

            # Create nested directory structure like the backend creates
            nested_dir = external_analysis_dir / "health" / "external-analysis"
            nested_dir.mkdir(parents=True, exist_ok=True)

            # Create artifact in nested path (matches real backend behavior)
            artifact_name = f"auto-{incident_id}-20260107-123456-abc123-diagnosis-review-packet.json"
            (nested_dir / artifact_name).write_text('{"test": true}')

            # Also create a top-level artifact for comparison
            top_level_artifact = f"auto-{incident_id}-20260107-654321-def456-diagnosis-review-packet.json"
            (external_analysis_dir / top_level_artifact).write_text('{"test": true}')

            # Reset should find BOTH artifacts
            removed = reset_diagnosis_loop_budget(external_analysis_dir, incident_id)

            assert removed == 2, (
                f"Expected 2 artifacts removed (nested + top-level), got {removed}. "
                "Budget reset must use rglob to discover nested artifacts."
            )

            # Verify both files were removed
            assert not (nested_dir / artifact_name).exists(), "Nested artifact should be removed"
            assert not (external_analysis_dir / top_level_artifact).exists(), (
                "Top-level artifact should be removed"
            )

    def test_reset_only_removes_matching_incident_id(self) -> None:
        """Test that reset only removes artifacts for the target incident ID."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            reset_diagnosis_loop_budget,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            target_incident_id = "otel-demo-deployment-shipping-deployment_unavailable"
            other_incident_id = "other-incident-123"

            # Create artifacts for both incidents
            nested_dir = external_analysis_dir / "health" / "external-analysis"
            nested_dir.mkdir(parents=True, exist_ok=True)

            # Target incident artifact
            target_artifact = f"auto-{target_incident_id}-20260107-123456-diagnosis-review-packet.json"
            (nested_dir / target_artifact).write_text('{"test": true}')

            # Other incident artifact (should NOT be removed)
            other_artifact = f"auto-{other_incident_id}-20260107-654321-diagnosis-review-packet.json"
            (nested_dir / other_artifact).write_text('{"test": true}')

            # Reset only target incident
            removed = reset_diagnosis_loop_budget(external_analysis_dir, target_incident_id)

            assert removed == 1, f"Expected 1 artifact removed, got {removed}"
            assert not (nested_dir / target_artifact).exists(), "Target artifact should be removed"
            assert (nested_dir / other_artifact).exists(), "Other incident artifact should remain"

    def test_get_budget_status_discovers_nested_artifacts(self) -> None:
        """Test that get_budget_status finds artifacts in nested directories."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            incident_id = "otel-demo-deployment-shipping-deployment_unavailable"

            # Create nested artifact
            nested_dir = external_analysis_dir / "health" / "external-analysis" / "phase4-diagnosis"
            nested_dir.mkdir(parents=True, exist_ok=True)
            artifact_name = f"auto-{incident_id}-20260107-123456-diagnosis-review-packet.json"
            (nested_dir / artifact_name).write_text('{"test": true}')

            # Check budget status
            status = get_budget_status(external_analysis_dir, incident_id)

            assert status["review_packet_count"] == 1, (
                f"Expected 1 review packet in nested path, got {status['review_packet_count']}. "
                "get_budget_status must use rglob to discover nested artifacts."
            )
            assert status["budget_exhausted"] is True
            assert artifact_name in status["review_packets"][0]

    def test_reset_handles_empty_directory(self) -> None:
        """Test that reset handles empty or non-existent directories gracefully."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            reset_diagnosis_loop_budget,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            # No artifacts exist
            removed = reset_diagnosis_loop_budget(external_analysis_dir, "any-incident")

            assert removed == 0, "Should return 0 when no artifacts exist"
