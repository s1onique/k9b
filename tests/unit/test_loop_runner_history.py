"""Tests for loop_runner_history helper module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from k8s_diag_agent.health.loop_history import HealthHistoryEntry, HealthRating
from k8s_diag_agent.health.loop_runner_history import load_runner_history, persist_runner_history


class TestLoadRunnerHistory:
    """Tests for load_runner_history function."""

    def test_returns_empty_dict_when_file_missing(self, tmp_path: Path) -> None:
        """Preserves current behavior: returns empty dict for missing file."""
        history_path = tmp_path / "history.json"
        result = load_runner_history(history_path=history_path)
        assert result == {}

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        """Preserves current behavior: raises JSONDecodeError on empty file.

        Note: The original _load_history in loop.py calls json.loads directly
        without try/except, so empty files raise JSONDecodeError.
        """
        history_path = tmp_path / "history.json"
        history_path.write_text("", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_runner_history(history_path=history_path)

    def test_loads_single_entry(self, tmp_path: Path) -> None:
        """Returns expected entry for single cluster in history."""
        history_path = tmp_path / "history.json"
        data = {
            "cluster-1": {
                "node_count": 5,
                "pod_count": 100,
                "control_plane_version": "v1.28.0",
                "health_rating": "healthy",
                "missing_evidence": [],
                "watched_helm_releases": {},
                "watched_crd_families": {},
                "node_conditions": {},
                "pod_counts": {},
            }
        }
        history_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_runner_history(history_path=history_path)
        assert "cluster-1" in result
        entry = result["cluster-1"]
        assert entry.cluster_id == "cluster-1"
        assert entry.node_count == 5
        assert entry.pod_count == 100
        assert entry.control_plane_version == "v1.28.0"
        assert entry.health_rating == HealthRating.HEALTHY

    def test_loads_multiple_entries(self, tmp_path: Path) -> None:
        """Returns expected entries for multiple clusters in history."""
        history_path = tmp_path / "history.json"
        data = {
            "cluster-1": {
                "node_count": 5,
                "pod_count": 100,
                "control_plane_version": "v1.28.0",
                "health_rating": "healthy",
                "missing_evidence": [],
                "watched_helm_releases": {},
                "watched_crd_families": {},
                "node_conditions": {},
                "pod_counts": {},
            },
            "cluster-2": {
                "node_count": 3,
                "pod_count": 50,
                "control_plane_version": "v1.27.0",
                "health_rating": "degraded",
                "missing_evidence": ["nodes"],
                "watched_helm_releases": {},
                "watched_crd_families": {},
                "node_conditions": {},
                "pod_counts": {},
            },
        }
        history_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_runner_history(history_path=history_path)
        assert len(result) == 2
        assert result["cluster-1"].node_count == 5
        assert result["cluster-2"].health_rating == HealthRating.DEGRADED

    def test_preserves_watched_helm_releases(self, tmp_path: Path) -> None:
        """Preserves watched helm releases in loaded entries."""
        history_path = tmp_path / "history.json"
        data = {
            "cluster-1": {
                "node_count": 5,
                "pod_count": 100,
                "control_plane_version": "v1.28.0",
                "health_rating": "healthy",
                "missing_evidence": [],
                "watched_helm_releases": {"ingress-nginx": "4.10.0", "cert-manager": "1.14.0"},
                "watched_crd_families": {},
                "node_conditions": {},
                "pod_counts": {},
            }
        }
        history_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_runner_history(history_path=history_path)
        assert result["cluster-1"].watched_helm_releases == {
            "ingress-nginx": "4.10.0",
            "cert-manager": "1.14.0",
        }

    def test_skips_non_dict_entries(self, tmp_path: Path) -> None:
        """Preserves current behavior: skips non-dict entries in history."""
        history_path = tmp_path / "history.json"
        data = {
            "cluster-1": {
                "node_count": 5,
                "pod_count": 100,
                "control_plane_version": "v1.28.0",
                "health_rating": "healthy",
                "missing_evidence": [],
                "watched_helm_releases": {},
                "watched_crd_families": {},
                "node_conditions": {},
                "pod_counts": {},
            },
            "cluster-2": "not-a-dict",  # Should be skipped
            "cluster-3": None,  # Should be skipped
        }
        history_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_runner_history(history_path=history_path)
        assert "cluster-1" in result
        assert "cluster-2" not in result
        assert "cluster-3" not in result


class TestPersistRunnerHistory:
    """Tests for persist_runner_history function."""

    def test_writes_history_json(self, tmp_path: Path) -> None:
        """Writes the same history payload shape as before."""
        history_path = tmp_path / "history.json"
        history_facts_dir = tmp_path / "history_facts"
        history_facts_dir.mkdir()
        directories = {"history": history_path, "history_facts": history_facts_dir}
        history: dict[str, HealthHistoryEntry] = {
            "cluster-1": HealthHistoryEntry(
                cluster_id="cluster-1",
                node_count=5,
                pod_count=100,
                control_plane_version="v1.28.0",
                health_rating=HealthRating.HEALTHY,
                missing_evidence=(),
            )
        }
        persist_runner_history(
            history=history,
            directories=directories,
            run_id="test-run-123",
            log_event_fn=None,
        )
        assert history_path.exists()
        loaded = json.loads(history_path.read_text(encoding="utf-8"))
        assert "cluster-1" in loaded
        assert loaded["cluster-1"]["node_count"] == 5
        assert loaded["cluster-1"]["health_rating"] == "healthy"

    def test_writes_fact_artifacts_when_dir_provided(self, tmp_path: Path) -> None:
        """Preserves fact artifact behavior when history_facts_dir is provided."""
        history_path = tmp_path / "history.json"
        history_facts_dir = tmp_path / "history_facts"
        history_facts_dir.mkdir()
        directories = {"history": history_path, "history_facts": history_facts_dir}
        history: dict[str, HealthHistoryEntry] = {
            "cluster-1": HealthHistoryEntry(
                cluster_id="cluster-1",
                node_count=5,
                pod_count=100,
                control_plane_version="v1.28.0",
                health_rating=HealthRating.HEALTHY,
                missing_evidence=(),
            )
        }
        persist_runner_history(
            history=history,
            directories=directories,
            run_id="test-run-456",
            log_event_fn=None,
        )
        # Fact artifacts are written with pattern: {run_id}-{cluster_id}-{artifact_id}.json
        fact_files = list(history_facts_dir.glob("test-run-456-*.json"))
        assert len(fact_files) >= 1
        # Verify fact artifact structure
        fact_data = json.loads(fact_files[0].read_text(encoding="utf-8"))
        assert "artifact_id" in fact_data
        assert fact_data["run_id"] == "test-run-456"
        assert fact_data["cluster_id"] == "cluster-1"
        assert "entry" in fact_data

    def test_continues_on_fact_artifact_write_failure(self, tmp_path: Path) -> None:
        """Fact artifact write failure is non-fatal; history.json still written."""
        history_path = tmp_path / "history.json"
        history_facts_dir = tmp_path / "history_facts"
        history_facts_dir.mkdir()
        directories = {"history": history_path, "history_facts": history_facts_dir}
        history: dict[str, HealthHistoryEntry] = {
            "cluster-1": HealthHistoryEntry(
                cluster_id="cluster-1",
                node_count=5,
                pod_count=100,
                control_plane_version="v1.28.0",
                health_rating=HealthRating.HEALTHY,
                missing_evidence=(),
            )
        }
        # Create a read-only directory to trigger OSError
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # read-only
        try:
            directories["history_facts"] = readonly_dir
            # Should not raise; history.json should still be written
            persist_runner_history(
                history=history,
                directories=directories,
                run_id="test-run-789",
                log_event_fn=None,
            )
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)
        # history.json should still exist
        assert history_path.exists()

    def test_works_without_history_facts_dir(self, tmp_path: Path) -> None:
        """Works when history_facts is not in directories dict."""
        history_path = tmp_path / "history.json"
        directories: dict[str, Path] = {"history": history_path}
        history: dict[str, HealthHistoryEntry] = {
            "cluster-1": HealthHistoryEntry(
                cluster_id="cluster-1",
                node_count=5,
                pod_count=100,
                control_plane_version="v1.28.0",
                health_rating=HealthRating.HEALTHY,
                missing_evidence=(),
            )
        }
        persist_runner_history(
            history=history,
            directories=directories,
            run_id="test-run-no-facts",
            log_event_fn=None,
        )
        assert history_path.exists()
        loaded = json.loads(history_path.read_text(encoding="utf-8"))
        assert "cluster-1" in loaded

    def test_logs_events_when_callback_provided(self, tmp_path: Path) -> None:
        """Logs INFO event on successful fact artifact write with metadata."""
        history_path = tmp_path / "history.json"
        history_facts_dir = tmp_path / "history_facts"
        history_facts_dir.mkdir()
        directories = {"history": history_path, "history_facts": history_facts_dir}
        history: dict[str, HealthHistoryEntry] = {
            "cluster-1": HealthHistoryEntry(
                cluster_id="cluster-1",
                node_count=5,
                pod_count=100,
                control_plane_version="v1.28.0",
                health_rating=HealthRating.HEALTHY,
                missing_evidence=(),
            )
        }
        logged_events: list[tuple[str, str, str, dict[str, object]]] = []

        def log_callback(component: str, severity: str, message: str, **metadata: object) -> None:
            logged_events.append((component, severity, message, dict(metadata)))

        persist_runner_history(
            history=history,
            directories=directories,
            run_id="test-run-logging",
            log_event_fn=log_callback,
        )
        # Check that INFO event was logged with metadata for fact artifacts
        info_events = [e for e in logged_events if e[1] == "INFO" and "history" in e[2].lower()]
        assert len(info_events) >= 1
        metadata = info_events[0][3]
        assert metadata.get("event") == "history-facts-written"
        assert metadata.get("artifact_count") == 1
        assert metadata.get("history_facts_dir") == str(history_facts_dir)

    def test_logs_failure_event_when_fact_write_fails(self, tmp_path: Path) -> None:
        """Logs WARNING event when fact artifact write fails, with severity_reason."""
        history_path = tmp_path / "history.json"
        readonly_dir = tmp_path / "readonly_facts"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # read-only
        directories: dict[str, Path] = {"history": history_path, "history_facts": readonly_dir}
        history: dict[str, HealthHistoryEntry] = {
            "cluster-1": HealthHistoryEntry(
                cluster_id="cluster-1",
                node_count=5,
                pod_count=100,
                control_plane_version="v1.28.0",
                health_rating=HealthRating.HEALTHY,
                missing_evidence=(),
            )
        }
        logged_events: list[tuple[str, str, str, dict[str, object]]] = []

        def log_callback(component: str, severity: str, message: str, **metadata: object) -> None:
            logged_events.append((component, severity, message, dict(metadata)))

        try:
            persist_runner_history(
                history=history,
                directories=directories,
                run_id="test-run-fail",
                log_event_fn=log_callback,
            )
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)
        # Check that WARNING event was logged for failure
        warning_events = [e for e in logged_events if e[1] == "WARNING"]
        assert len(warning_events) >= 1
        metadata = warning_events[0][3]
        assert metadata.get("event") == "history-facts-failed"
        assert "severity_reason" in metadata
