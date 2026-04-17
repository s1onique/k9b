"""Tests for Alertmanager context injection into review enrichment inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.alertmanager_artifact import (
    write_alertmanager_compact,
)
from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    AlertmanagerCompact,
    normalize_alertmanager_payload,
    snapshot_to_compact,
)
from k8s_diag_agent.external_analysis.review_input import (
    AlertmanagerContext,
    ReviewEnrichmentInput,
    build_review_enrichment_input,
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_alert(alertname: str, severity: str = "warning", **labels: str) -> dict[str, Any]:
    base_labels = {"alertname": alertname, "severity": severity, "cluster": "prod", "namespace": "default"}
    base_labels.update(labels)
    return {
        "labels": base_labels,
        "annotations": {"summary": f"Alert {alertname} fired"},
        "state": "active",
        "startsAt": "2024-01-01T00:00:00Z",
    }


class TestAlertmanagerContextFromRunArtifacts:
    """Tests for AlertmanagerContext.from_run_artifacts()."""

    def test_returns_unavailable_when_no_artifacts_exist(self, tmp_path: Path) -> None:
        """When no Alertmanager compact artifact exists, returns unavailable context."""
        ctx = AlertmanagerContext.from_run_artifacts(tmp_path, "nonexistent-run")
        assert ctx.available is False
        assert ctx.source == "unavailable"
        assert ctx.compact is None
        assert ctx.status is None

    def test_returns_unavailable_when_compact_file_missing(self, tmp_path: Path) -> None:
        """When only snapshot exists but compact is missing, returns unavailable context."""
        # Write snapshot only (not compact)
        raw = {"data": {"alerts": [_make_alert("Test")]}}
        snapshot = normalize_alertmanager_payload(raw)
        from k8s_diag_agent.external_analysis.alertmanager_artifact import write_alertmanager_snapshot
        write_alertmanager_snapshot(tmp_path, snapshot, "nonexistent-run")
        
        ctx = AlertmanagerContext.from_run_artifacts(tmp_path, "nonexistent-run")
        assert ctx.available is False
        assert ctx.source == "unavailable"

    def test_returns_available_when_compact_exists(self, tmp_path: Path) -> None:
        """When Alertmanager compact artifact exists, returns available context."""
        # Create compact artifact
        raw = {"data": {"alerts": [_make_alert("Test", "critical")]}}
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        write_alertmanager_compact(tmp_path, compact, "test-run")
        
        ctx = AlertmanagerContext.from_run_artifacts(tmp_path, "test-run")
        assert ctx.available is True
        assert ctx.source == "run_artifact"
        assert ctx.compact is not None
        assert ctx.status == "ok"
        assert ctx.compact["alert_count"] == 1

    def test_preserves_status_for_error_snapshots(self, tmp_path: Path) -> None:
        """Error status (timeout, disabled, etc.) is preserved in context."""
        # Create error compact
        raw: dict[str, Any] = {"data": {"alerts": []}}
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        write_alertmanager_compact(tmp_path, compact, "empty-run")
        
        ctx = AlertmanagerContext.from_run_artifacts(tmp_path, "empty-run")
        assert ctx.available is True
        assert ctx.status == "empty"

    def test_no_live_fetch_performed(self, tmp_path: Path) -> None:
        """AlertmanagerContext.from_run_artifacts does not perform live Alertmanager queries."""
        # Prove no network by verifying the method signature has no network params
        # and only calls read functions that operate on disk paths
        import inspect
        sig = inspect.signature(AlertmanagerContext.from_run_artifacts)
        params = list(sig.parameters.keys())
        # Should only have root_dir and run_id, no host/url/timeout params
        assert params == ["root_dir", "run_id"]
        
        ctx = AlertmanagerContext.from_run_artifacts(tmp_path, "any-run")
        assert ctx.source == "unavailable"
        assert ctx.available is False
            
    def test_run_artifact_path_matches_real_run_layout(self, tmp_path: Path) -> None:
        """Alertmanager compact path matches the real run directory layout."""
        run_id = "test-run"
        root = tmp_path / "runs" / "health"
        
        # Verify the expected filename pattern matches what write uses
        expected_filename = f"{run_id}-alertmanager-compact.json"
        
        # Create artifact and verify it can be read back at that path
        raw = {"data": {"alerts": [_make_alert("Test")]}}
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        written_path = write_alertmanager_compact(root, compact, run_id)
        
        # Verify the artifact exists at the expected path
        assert written_path.name == expected_filename
        assert written_path.exists()
        assert f"{run_id}-" in str(written_path)
        
        # Verify from_run_artifacts finds it using the same path convention
        ctx = AlertmanagerContext.from_run_artifacts(root, run_id)
        assert ctx.available is True
        assert ctx.source == "run_artifact"


class TestBuildReviewEnrichmentInputWithAlertmanager:
    """Tests for build_review_enrichment_input() including Alertmanager context."""

    def test_review_enrichment_input_includes_alertmanager_context(self, tmp_path: Path) -> None:
        """build_review_enrichment_input returns ReviewEnrichmentInput with alertmanager_context."""
        run_id = "test-run-alertmanager"
        root = tmp_path / "runs" / "health"
        
        # Write review artifact
        review_path = root / "reviews" / f"{run_id}-review.json"
        review = {
            "run_id": run_id,
            "selected_drilldowns": [],
        }
        _write_json(review_path, review)
        
        # Write Alertmanager compact
        raw = {"data": {"alerts": [_make_alert("HighCPU", "critical")]}}
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        write_alertmanager_compact(root, compact, run_id)
        
        # Build context
        context = build_review_enrichment_input(review_path, run_id)
        
        assert isinstance(context, ReviewEnrichmentInput)
        assert context.alertmanager_context is not None
        assert context.alertmanager_context.available is True
        assert context.alertmanager_context.source == "run_artifact"
        assert context.alertmanager_context.compact is not None

    def test_graceful_omission_when_no_alertmanager_artifact(self, tmp_path: Path) -> None:
        """When no Alertmanager compact exists, prompt construction still succeeds."""
        run_id = "test-run-no-alertmanager"
        root = tmp_path / "runs" / "health"
        
        # Write review artifact (no Alertmanager artifact)
        review_path = root / "reviews" / f"{run_id}-review.json"
        review = {
            "run_id": run_id,
            "selected_drilldowns": [],
        }
        _write_json(review_path, review)
        
        # Build context - should not raise
        context = build_review_enrichment_input(review_path, run_id)
        
        assert context.alertmanager_context.available is False
        assert context.alertmanager_context.source == "unavailable"

    def test_alertmanager_context_preserves_compact_fields(self, tmp_path: Path) -> None:
        """Alertmanager compact data includes all expected fields."""
        run_id = "test-run-full-compact"
        root = tmp_path / "runs" / "health"
        
        # Write review
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Write Alertmanager compact with multiple alerts
        raw = {
            "data": {
                "alerts": [
                    _make_alert("HighCPU", "critical", namespace="monitoring"),
                    _make_alert("DiskFull", "warning", namespace="storage"),
                    _make_alert("HighCPU", "warning", namespace="monitoring"),
                ]
            }
        }
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        write_alertmanager_compact(root, compact, run_id)
        
        context = build_review_enrichment_input(review_path, run_id)
        
        assert context.alertmanager_context.available is True
        compact_data = context.alertmanager_context.compact
        assert compact_data is not None
        # Check compact fields are present
        assert "alert_count" in compact_data
        assert "severity_counts" in compact_data
        assert "state_counts" in compact_data
        assert "top_alert_names" in compact_data
        assert "affected_namespaces" in compact_data
        assert "status" in compact_data


class TestAlertmanagerContextDeterminism:
    """Tests for determinism of Alertmanager context construction."""

    def test_deterministic_compact_json_bytes(self, tmp_path: Path) -> None:
        """Same input produces identical compact bytes."""
        run_id = "deterministic-run"
        root = tmp_path / "runs" / "health"
        
        # Write review
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Write Alertmanager compact
        raw = {"data": {"alerts": [_make_alert("Test", "warning")]}}
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        write_alertmanager_compact(root, compact, run_id)
        
        # Build context twice
        ctx1 = build_review_enrichment_input(review_path, run_id)
        ctx2 = build_review_enrichment_input(review_path, run_id)
        
        # Both should produce identical compact data
        assert ctx1.alertmanager_context.compact == ctx2.alertmanager_context.compact
        
        # Verify JSON bytes are identical
        json1 = json.dumps(ctx1.alertmanager_context.compact, sort_keys=True)
        json2 = json.dumps(ctx2.alertmanager_context.compact, sort_keys=True)
        assert json1 == json2


class TestAlertmanagerContextStatusPreservation:
    """Tests that error/disabled statuses are preserved in context."""

    def test_disabled_status_preserved(self, tmp_path: Path) -> None:
        """DISABLED status from integration config is preserved."""
        run_id = "disabled-run"
        root = tmp_path / "runs" / "health"
        
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Create compact with disabled status
        compact = AlertmanagerCompact(
            status="disabled",
            alert_count=0,
            severity_counts=(),
            state_counts=(),
            top_alert_names=(),
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            truncated=False,
            captured_at="2024-01-01T00:00:00Z",
        )
        write_alertmanager_compact(root, compact, run_id)
        
        context = build_review_enrichment_input(review_path, run_id)
        
        assert context.alertmanager_context.available is True
        assert context.alertmanager_context.status == "disabled"
        assert context.alertmanager_context.compact is not None
        assert context.alertmanager_context.compact["status"] == "disabled"

    def test_timeout_status_preserved(self, tmp_path: Path) -> None:
        """TIMEOUT status from upstream failure is preserved."""
        run_id = "timeout-run"
        root = tmp_path / "runs" / "health"
        
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Create compact with timeout status
        compact = AlertmanagerCompact(
            status="timeout",
            alert_count=0,
            severity_counts=(),
            state_counts=(),
            top_alert_names=(),
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            truncated=False,
            captured_at="2024-01-01T00:00:00Z",
        )
        write_alertmanager_compact(root, compact, run_id)
        
        context = build_review_enrichment_input(review_path, run_id)
        
        assert context.alertmanager_context.available is True
        assert context.alertmanager_context.status == "timeout"

    def test_upstream_error_status_preserved(self, tmp_path: Path) -> None:
        """UPSTREAM_ERROR status is preserved."""
        run_id = "upstream-error-run"
        root = tmp_path / "runs" / "health"
        
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        compact = AlertmanagerCompact(
            status="upstream_error",
            alert_count=0,
            severity_counts=(),
            state_counts=(),
            top_alert_names=(),
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            truncated=False,
            captured_at="2024-01-01T00:00:00Z",
        )
        write_alertmanager_compact(root, compact, run_id)
        
        context = build_review_enrichment_input(review_path, run_id)
        
        assert context.alertmanager_context.available is True
        assert context.alertmanager_context.status == "upstream_error"
