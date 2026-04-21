"""Tests for ComparisonTriggerArtifact identity (artifact_id field)."""
from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.health.loop import (
    ComparisonTriggerArtifact,
    TriggerDetail,
)


class TestComparisonTriggerArtifactIdentity:
    """Tests for artifact_id generation, serialization, and backward compatibility."""

    def test_artifact_id_generated_for_new_artifacts(self) -> None:
        """New artifacts generated via to_dict() should include an artifact_id when set."""
        trigger = ComparisonTriggerArtifact(
            run_label="test",
            run_id="test-run",
            timestamp=datetime.now(UTC),
            primary="ctx1",
            secondary="ctx2",
            primary_label="cluster-a",
            secondary_label="cluster-b",
            trigger_reasons=("control_plane_version",),
            comparison_summary={"nodes": 0},
            differences={},
            trigger_details=(
                TriggerDetail(
                    type="control_plane_version",
                    reason="control plane version drift (v1.28 vs v1.29)",
                    baseline_expectation="v1.28.x",
                    actual_value="v1.28 vs v1.29",
                    previous_run_value=None,
                    why="Drift detected",
                    next_check="Check upgrade status",
                    peer_roles=None,
                    classification=None,
                ),
            ),
            comparison_intent="suspicious drift",
            expected_drift_categories=(),
            ignored_drift_categories=(),
            peer_notes=None,
            notes=None,
            artifact_id="trigger-a1b2c3d4",
        )
        data = trigger.to_dict()
        assert "artifact_id" in data
        assert data["artifact_id"] == "trigger-a1b2c3d4"

    def test_artifact_id_omitted_when_none(self) -> None:
        """artifact_id should be omitted from to_dict() when None (legacy behavior)."""
        trigger = ComparisonTriggerArtifact(
            run_label="test",
            run_id="test-run",
            timestamp=datetime.now(UTC),
            primary="ctx1",
            secondary="ctx2",
            primary_label="cluster-a",
            secondary_label="cluster-b",
            trigger_reasons=(),
            comparison_summary={},
            differences={},
            trigger_details=(),
            comparison_intent="suspicious drift",
            expected_drift_categories=(),
            ignored_drift_categories=(),
            artifact_id=None,  # Legacy artifact
        )
        data = trigger.to_dict()
        # artifact_id should not appear when None (backward compat)
        assert "artifact_id" not in data

    def test_from_dict_parses_artifact_id(self) -> None:
        """from_dict should correctly parse artifact_id when present."""
        raw = {
            "run_label": "test",
            "run_id": "test-run",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "primary": "ctx1",
            "secondary": "ctx2",
            "primary_label": "cluster-a",
            "secondary_label": "cluster-b",
            "trigger_reasons": [],
            "comparison_summary": {},
            "differences": {},
            "trigger_details": [],
            "comparison_intent": "suspicious drift",
            "expected_drift_categories": [],
            "ignored_drift_categories": [],
            "artifact_id": "trigger-xyz789",
        }
        artifact = ComparisonTriggerArtifact.from_dict(raw)
        assert artifact.artifact_id == "trigger-xyz789"

    def test_from_dict_backward_compat_no_artifact_id(self) -> None:
        """from_dict should handle legacy artifacts without artifact_id (returns None)."""
        raw = {
            "run_label": "legacy",
            "run_id": "legacy-run",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "primary": "ctx1",
            "secondary": "ctx2",
            "primary_label": "cluster-a",
            "secondary_label": "cluster-b",
            "trigger_reasons": [],
            "comparison_summary": {},
            "differences": {},
            "trigger_details": [],
            "comparison_intent": "suspicious drift",
            "expected_drift_categories": [],
            "ignored_drift_categories": [],
            # No artifact_id field - legacy artifact
        }
        artifact = ComparisonTriggerArtifact.from_dict(raw)
        assert artifact.artifact_id is None

    def test_from_dict_backward_compat_empty_string(self) -> None:
        """from_dict should treat empty string artifact_id as None."""
        raw = {
            "run_label": "test",
            "run_id": "test-run",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "primary": "ctx1",
            "secondary": "ctx2",
            "primary_label": "cluster-a",
            "secondary_label": "cluster-b",
            "trigger_reasons": [],
            "comparison_summary": {},
            "differences": {},
            "trigger_details": [],
            "comparison_intent": "suspicious drift",
            "expected_drift_categories": [],
            "ignored_drift_categories": [],
            "artifact_id": "",  # Empty string treated as None
        }
        artifact = ComparisonTriggerArtifact.from_dict(raw)
        assert artifact.artifact_id is None

    def test_artifact_id_distinct_from_run_id_and_trigger_fields(self) -> None:
        """artifact_id must be distinct from run_id, primary, secondary, and trigger reasons."""
        from k8s_diag_agent.identity.artifact import new_artifact_id
        trigger_id = new_artifact_id()
        # artifact_id must not equal run_id or any cluster identifier
        assert trigger_id != "test-run-123"
        assert trigger_id != "ctx1"
        assert trigger_id != "ctx2"
        assert trigger_id != "cluster-a"
        assert trigger_id != "cluster-b"
        # IDs should be unique per invocation
        other_id = new_artifact_id()
        assert trigger_id != other_id

    def test_roundtrip_new_artifact(self) -> None:
        """New artifact with artifact_id should survive to_dict -> from_dict roundtrip."""
        original = ComparisonTriggerArtifact(
            run_label="test",
            run_id="test-run",
            timestamp=datetime.now(UTC),
            primary="ctx1",
            secondary="ctx2",
            primary_label="cluster-a",
            secondary_label="cluster-b",
            trigger_reasons=("watched_helm_release",),
            comparison_summary={"helm": 1},
            differences={},
            trigger_details=(
                TriggerDetail(
                    type="watched_helm_release",
                    reason="release drift",
                    baseline_expectation=None,
                    actual_value="v1.0 vs v2.0",
                    previous_run_value=None,
                    why="Drift",
                    next_check=None,
                    peer_roles=None,
                    classification=None,
                ),
            ),
            comparison_intent="expected drift",
            expected_drift_categories=(),
            ignored_drift_categories=(),
            peer_notes="notes",
            notes="summary",
            artifact_id="trigger-new-001",
        )
        data = original.to_dict()
        restored = ComparisonTriggerArtifact.from_dict(data)
        assert restored.artifact_id == original.artifact_id
        assert restored.run_label == original.run_label
        assert restored.primary == original.primary
        assert restored.secondary == original.secondary
        assert restored.trigger_reasons == original.trigger_reasons
        assert len(restored.trigger_details) == len(original.trigger_details)
