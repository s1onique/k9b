"""Tests for Alertmanager artifact portability in diagnostic pack export/replay."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, cast

from scripts.build_diagnostic_pack import (
    _build_alertmanager_context,
    create_diagnostic_pack,
)
from tests.fixtures.ui_index_sample import sample_ui_index


def _make_alert(alertname: str, severity: str = "warning", **labels: str) -> dict[str, Any]:
    """Create a mock Alertmanager alert."""
    base_labels = {"alertname": alertname, "severity": severity, "cluster": "prod", "namespace": "default"}
    base_labels.update(labels)
    return {
        "labels": base_labels,
        "annotations": {"summary": f"Alert {alertname} fired"},
        "state": "active",
        "startsAt": "2024-01-01T00:00:00Z",
    }


class TestDiagnosticPackAlertmanagerArtifacts:
    """Tests for Alertmanager artifact inclusion in diagnostic pack."""

    def _build_run_structure(self, tmp_path: Path, run_id: str, include_alertmanager: bool = True) -> Path:
        """Build a minimal run structure for testing."""
        runs_dir = tmp_path / "runs"
        health_dir = runs_dir / "health"
        
        # Create directories
        for folder in ("assessments", "drilldowns", "triggers", "comparisons", "reviews", "external-analysis"):
            (health_dir / folder).mkdir(parents=True, exist_ok=True)
        
        # Write ui-index
        index_data = sample_ui_index()
        run_payload = cast(dict[str, object], index_data["run"])
        run_payload["run_id"] = run_id
        run_payload["run_label"] = "health-run"
        (health_dir / "ui-index.json").write_text(json.dumps(index_data), encoding="utf-8")
        
        # Write minimal artifacts
        assessment_payload = {
            "cluster_label": "cluster-a",
            "assessment": {"health_rating": "healthy"},
        }
        (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
            json.dumps(assessment_payload), encoding="utf-8"
        )
        (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text("{}", encoding="utf-8")
        (health_dir / "triggers" / f"{run_id}-cluster-a.json").write_text("{}", encoding="utf-8")
        (health_dir / "reviews" / f"{run_id}-review.json").write_text(
            json.dumps({"rating": "ok"}), encoding="utf-8"
        )
        (health_dir / "external-analysis" / f"{run_id}-review-enrichment.json").write_text("{}", encoding="utf-8")
        (health_dir / "external-analysis" / f"{run_id}-next-check-plan.json").write_text("{}", encoding="utf-8")
        
        return runs_dir

    def test_pack_includes_alertmanager_snapshot_artifact(self, tmp_path: Path) -> None:
        """Diagnostic pack includes Alertmanager snapshot artifact when present."""
        run_id = "run-with-am"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        health_dir = runs_dir / "health"
        
        # Write Alertmanager snapshot artifact
        snapshot_data = {
            "status": "success",
            "alerts": [_make_alert("HighCPU", "warning")],
            "labels": {"cluster": "prod"},
            "annotations": {},
            "startsAt": "2024-01-01T00:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://alertmanager/-/alerts",
            "fingerprint": "abc123",
        }
        (health_dir / f"{run_id}-alertmanager-snapshot.json").write_text(
            json.dumps(snapshot_data), encoding="utf-8"
        )
        
        # Build pack
        packs_dir = tmp_path / "packs"
        pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Verify ZIP contains the snapshot
        with zipfile.ZipFile(pack_path, "r") as archive:
            names = set(archive.namelist())
            expected_path = f"{run_id}-alertmanager-snapshot.json"
            assert expected_path in names, f"Expected {expected_path} in {names}"

    def test_pack_includes_alertmanager_compact_artifact(self, tmp_path: Path) -> None:
        """Diagnostic pack includes Alertmanager compact artifact when present."""
        run_id = "run-with-compact"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        health_dir = runs_dir / "health"
        
        # Write Alertmanager compact artifact
        compact_data = {
            "status": "ok",
            "alert_count": 5,
            "severity_counts": {"critical": 1, "warning": 3, "info": 1},
            "state_counts": {"active": 3, "pending": 2},
            "top_alert_names": ["HighCPU", "DiskFull", "MemoryPressure"],
            "affected_namespaces": ["default", "monitoring", "kube-system"],
            "affected_clusters": ["prod"],
            "affected_services": ["api-server", "etcd"],
            "truncated": False,
            "captured_at": "2024-01-01T00:00:00Z",
        }
        (health_dir / f"{run_id}-alertmanager-compact.json").write_text(
            json.dumps(compact_data), encoding="utf-8"
        )
        
        # Build pack
        packs_dir = tmp_path / "packs"
        pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Verify ZIP contains the compact
        with zipfile.ZipFile(pack_path, "r") as archive:
            names = set(archive.namelist())
            expected_path = f"{run_id}-alertmanager-compact.json"
            assert expected_path in names, f"Expected {expected_path} in {names}"

    def test_pack_succeeds_when_alertmanager_artifacts_missing(self, tmp_path: Path) -> None:
        """Diagnostic pack export still succeeds when Alertmanager artifacts are missing."""
        run_id = "run-no-am"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        
        # Build pack WITHOUT Alertmanager artifacts
        packs_dir = tmp_path / "packs"
        pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Should succeed
        assert pack_path.exists()
        
        # Verify ZIP is valid and contains expected core files
        with zipfile.ZipFile(pack_path, "r") as archive:
            names = set(archive.namelist())
            assert "review_bundle.json" in names
            assert "review_input_14b.json" in names
            assert "manifest.json" in names

    def test_review_bundle_includes_alertmanager_context(self, tmp_path: Path) -> None:
        """Review bundle includes alertmanager_context with compact data."""
        run_id = "run-am-context"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        health_dir = runs_dir / "health"
        
        # Write Alertmanager compact artifact
        compact_data = {
            "status": "ok",
            "alert_count": 3,
            "severity_counts": {"warning": 2, "critical": 1},
            "state_counts": {"active": 3},
            "top_alert_names": ["HighCPU", "DiskFull"],
            "affected_namespaces": ["default"],
            "affected_clusters": ["prod"],
            "affected_services": [],
            "truncated": False,
            "captured_at": "2024-01-01T00:00:00Z",
        }
        (health_dir / f"{run_id}-alertmanager-compact.json").write_text(
            json.dumps(compact_data), encoding="utf-8"
        )
        
        # Build pack
        packs_dir = tmp_path / "packs"
        pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Verify review_bundle contains alertmanager_context
        with zipfile.ZipFile(pack_path, "r") as archive:
            bundle = json.loads(archive.read("review_bundle.json"))
            
            # Check alertmanager_context is present
            assert "alertmanager_context" in bundle
            
            ctx = bundle["alertmanager_context"]
            assert ctx["available"] is True
            assert ctx["source"] == "run_artifact"
            assert ctx["status"] == "ok"
            assert ctx["compact"] is not None
            assert ctx["compact"]["alert_count"] == 3

    def test_review_bundle_includes_unavailable_context_when_no_artifacts(self, tmp_path: Path) -> None:
        """Review bundle includes unavailable alertmanager_context when artifacts are missing."""
        run_id = "run-no-am-context"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        
        # Build pack WITHOUT Alertmanager artifacts
        packs_dir = tmp_path / "packs"
        pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Verify review_bundle contains alertmanager_context with unavailable status
        with zipfile.ZipFile(pack_path, "r") as archive:
            bundle = json.loads(archive.read("review_bundle.json"))
            
            assert "alertmanager_context" in bundle
            ctx = bundle["alertmanager_context"]
            assert ctx["available"] is False
            assert ctx["source"] == "unavailable"

    def test_review_input_includes_alertmanager_context(self, tmp_path: Path) -> None:
        """Review input (14b) includes alertmanager_context for replay."""
        run_id = "run-replay-am"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        health_dir = runs_dir / "health"
        
        # Write Alertmanager compact artifact
        compact_data = {
            "status": "disabled",
            "alert_count": 0,
            "severity_counts": {},
            "state_counts": {},
            "top_alert_names": [],
            "affected_namespaces": [],
            "affected_clusters": [],
            "affected_services": [],
            "truncated": False,
            "captured_at": "2024-01-01T00:00:00Z",
        }
        (health_dir / f"{run_id}-alertmanager-compact.json").write_text(
            json.dumps(compact_data), encoding="utf-8"
        )
        
        # Build pack
        packs_dir = tmp_path / "packs"
        pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Verify review_input contains alertmanager_context
        with zipfile.ZipFile(pack_path, "r") as archive:
            review_input = json.loads(archive.read("review_input_14b.json"))
            
            assert "alertmanager_context" in review_input
            ctx = review_input["alertmanager_context"]
            assert ctx["available"] is True
            assert ctx["status"] == "disabled"
            # Status semantics preserved
            assert ctx["compact"]["status"] == "disabled"

    def test_alertmanager_status_semantics_preserved(self, tmp_path: Path) -> None:
        """Alertmanager error/disabled/empty statuses survive bundle/export roundtrip."""
        run_id = "run-status-semantics"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        health_dir = runs_dir / "health"
        
        # Test with different statuses
        for status in ("ok", "empty", "disabled", "timeout", "upstream_error", "invalid_response"):
            compact_data: dict[str, Any] = {
                "status": status,
                "alert_count": 0,
                "severity_counts": {},
                "state_counts": {},
                "top_alert_names": [],
                "affected_namespaces": [],
                "affected_clusters": [],
                "affected_services": [],
                "truncated": False,
                "captured_at": "2024-01-01T00:00:00Z",
            }
            status_run_id = f"{run_id}-{status}"
            (health_dir / f"{status_run_id}-alertmanager-compact.json").write_text(
                json.dumps(compact_data), encoding="utf-8"
            )
            
            # Build pack
            packs_dir = tmp_path / "packs"
            pack_path = create_diagnostic_pack(status_run_id, runs_dir, output_dir=packs_dir)
            
            # Verify status survives roundtrip
            with zipfile.ZipFile(pack_path, "r") as archive:
                bundle = json.loads(archive.read("review_bundle.json"))
                ctx = bundle["alertmanager_context"]
                
                assert ctx["available"] is True
                assert ctx["status"] == status, f"Expected status {status}, got {ctx['status']}"
                assert ctx["compact"]["status"] == status

    def test_replay_can_reconstruct_alertmanager_context(self, tmp_path: Path) -> None:
        """Offline replay can reconstruct Alertmanager context from exported/stored artifacts only."""
        run_id = "run-replayable"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        health_dir = runs_dir / "health"
        
        # Write both snapshot and compact
        snapshot_data = {
            "status": "success",
            "alerts": [_make_alert("TestAlert", "warning")],
            "labels": {"cluster": "prod"},
            "annotations": {},
            "startsAt": "2024-01-01T00:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://alertmanager/-/alerts",
            "fingerprint": "test123",
        }
        (health_dir / f"{run_id}-alertmanager-snapshot.json").write_text(
            json.dumps(snapshot_data), encoding="utf-8"
        )
        
        compact_data = {
            "status": "ok",
            "alert_count": 1,
            "severity_counts": {"warning": 1},
            "state_counts": {"active": 1},
            "top_alert_names": ["TestAlert"],
            "affected_namespaces": ["default"],
            "affected_clusters": ["prod"],
            "affected_services": [],
            "truncated": False,
            "captured_at": "2024-01-01T00:00:00Z",
        }
        (health_dir / f"{run_id}-alertmanager-compact.json").write_text(
            json.dumps(compact_data), encoding="utf-8"
        )
        
        # Build pack
        packs_dir = tmp_path / "packs"
        pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Simulate offline replay: extract and reconstruct context from stored artifacts
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(pack_path, "r") as archive:
            archive.extractall(extract_dir)
        
        # Replay: read artifacts from extracted pack
        compact_path = extract_dir / f"{run_id}-alertmanager-compact.json"
        snapshot_path = extract_dir / f"{run_id}-alertmanager-snapshot.json"
        
        # Verify both artifacts are present in extracted pack
        assert compact_path.exists(), "Compact artifact should be in pack"
        assert snapshot_path.exists(), "Snapshot artifact should be in pack"
        
        # Reconstruct context from stored artifacts
        with open(compact_path) as f:
            compact_replay = json.load(f)
        
        # Verify context matches original
        assert compact_replay["status"] == "ok"
        assert compact_replay["alert_count"] == 1
        assert "TestAlert" in compact_replay["top_alert_names"]

    def test_manifest_reflects_alertmanager_artifacts(self, tmp_path: Path) -> None:
        """Manifest/index of exported contents reflects Alertmanager artifacts correctly."""
        run_id = "run-manifest-am"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        health_dir = runs_dir / "health"
        
        # Write both Alertmanager artifacts
        (health_dir / f"{run_id}-alertmanager-snapshot.json").write_text(
            json.dumps({"status": "success", "alerts": []}), encoding="utf-8"
        )
        (health_dir / f"{run_id}-alertmanager-compact.json").write_text(
            json.dumps({"status": "ok", "alert_count": 0}), encoding="utf-8"
        )
        
        # Build pack
        packs_dir = tmp_path / "packs"
        pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Verify manifest includes Alertmanager artifacts
        with zipfile.ZipFile(pack_path, "r") as archive:
            manifest = json.loads(archive.read("manifest.json"))
            
            file_paths = [entry["path"] for entry in manifest.get("files", [])]
            assert f"{run_id}-alertmanager-snapshot.json" in file_paths
            assert f"{run_id}-alertmanager-compact.json" in file_paths

    def test_latest_pack_mirror_includes_alertmanager_context(self, tmp_path: Path) -> None:
        """Latest pack mirror includes Alertmanager context for easy inspection."""
        run_id = "run-latest-am"
        runs_dir = self._build_run_structure(tmp_path, run_id)
        health_dir = runs_dir / "health"
        
        # Write Alertmanager compact artifact
        compact_data = {
            "status": "ok",
            "alert_count": 2,
            "severity_counts": {"warning": 2},
            "state_counts": {"active": 2},
            "top_alert_names": ["Alert1", "Alert2"],
            "affected_namespaces": ["default"],
            "affected_clusters": ["prod"],
            "affected_services": [],
            "truncated": False,
            "captured_at": "2024-01-01T00:00:00Z",
        }
        (health_dir / f"{run_id}-alertmanager-compact.json").write_text(
            json.dumps(compact_data), encoding="utf-8"
        )
        
        # Build pack
        packs_dir = tmp_path / "packs"
        create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
        
        # Verify latest mirror contains alertmanager_context in review_bundle.json
        latest_dir = packs_dir / "latest"
        bundle_path = latest_dir / "review_bundle.json"
        
        assert bundle_path.exists()
        
        with open(bundle_path) as f:
            bundle = json.load(f)
        
        assert "alertmanager_context" in bundle
        assert bundle["alertmanager_context"]["available"] is True
        assert bundle["alertmanager_context"]["compact"]["alert_count"] == 2


class TestBuildAlertmanagerContext:
    """Unit tests for _build_alertmanager_context function."""

    def test_returns_unavailable_when_no_artifacts(self, tmp_path: Path) -> None:
        """Returns unavailable context when neither snapshot nor compact exists."""
        ctx = _build_alertmanager_context(tmp_path, "nonexistent-run")
        
        assert ctx["available"] is False
        assert ctx["source"] == "unavailable"
        assert ctx["status"] is None
        assert ctx["compact"] is None
        assert ctx["snapshot_available"] is False

    def test_returns_unavailable_when_only_snapshot_exists(self, tmp_path: Path) -> None:
        """Returns unavailable context when only snapshot exists (compact required)."""
        # Write only snapshot
        (tmp_path / "test-run-alertmanager-snapshot.json").write_text(
            json.dumps({"status": "success", "alerts": []}), encoding="utf-8"
        )
        
        ctx = _build_alertmanager_context(tmp_path, "test-run")
        
        assert ctx["available"] is False
        assert ctx["snapshot_available"] is True

    def test_returns_available_when_compact_exists(self, tmp_path: Path) -> None:
        """Returns available context when compact exists."""
        compact_data = {
            "status": "ok",
            "alert_count": 5,
            "severity_counts": {"warning": 3, "critical": 2},
            "state_counts": {"active": 5},
            "top_alert_names": ["HighCPU", "DiskFull"],
            "affected_namespaces": ["default", "monitoring"],
            "affected_clusters": ["prod"],
            "affected_services": [],
            "truncated": False,
            "captured_at": "2024-01-01T00:00:00Z",
        }
        (tmp_path / "test-run-alertmanager-compact.json").write_text(
            json.dumps(compact_data), encoding="utf-8"
        )
        
        ctx = _build_alertmanager_context(tmp_path, "test-run")
        
        assert ctx["available"] is True
        assert ctx["source"] == "run_artifact"
        assert ctx["status"] == "ok"
        assert ctx["compact"] is not None
        compact = cast(dict[str, Any], ctx["compact"])
        assert compact["alert_count"] == 5
        assert ctx["snapshot_available"] is False

    def test_indicates_snapshot_available_when_both_exist(self, tmp_path: Path) -> None:
        """Indicates snapshot is available when both artifacts exist."""
        (tmp_path / "test-run-alertmanager-snapshot.json").write_text(
            json.dumps({"status": "success", "alerts": []}), encoding="utf-8"
        )
        (tmp_path / "test-run-alertmanager-compact.json").write_text(
            json.dumps({"status": "ok", "alert_count": 0}), encoding="utf-8"
        )
        
        ctx = _build_alertmanager_context(tmp_path, "test-run")
        
        assert ctx["available"] is True
        assert ctx["snapshot_available"] is True

    def test_no_live_fetch_performed(self, tmp_path: Path) -> None:
        """Verify no live Alertmanager fetch is performed during context building."""
        # Build context with no artifacts
        ctx = _build_alertmanager_context(tmp_path, "any-run")
        
        # Should be unavailable, not fetching live data
        assert ctx["available"] is False
        assert ctx["source"] == "unavailable"
