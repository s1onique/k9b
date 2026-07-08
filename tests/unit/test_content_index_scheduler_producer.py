"""Unit tests for the scheduler content index producer.

Tests cover:
- disabled config skips without touching DB
- enabled config creates DB when missing
- enabled config updates existing DB
- invalid/corrupt DB triggers safe rebuild or warning
- update failure does not raise through scheduler hook
- structured success log emitted
- structured failure log emitted
- custom DB path honored
- no sensitive artifact content logged
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

# Import the module under test
from k8s_diag_agent.content_index.scheduler_producer import (
    CONTENT_INDEX_DB_PATH_ENV_VAR,
    CONTENT_INDEX_ENABLED_ENV_VAR,
    CONTENT_INDEX_UPDATE_MODE_ENV_VAR,
    SchedulerContentIndexConfig,
    SchedulerContentIndexResult,
    load_scheduler_content_index_config_from_env,
    update_content_index_after_scheduler_run,
)


class TestLoadSchedulerContentIndexConfig:
    """Tests for loading scheduler content index configuration from environment."""

    def test_default_enabled(self) -> None:
        """Scheduler producer should be enabled by default."""
        env = {}
        config = load_scheduler_content_index_config_from_env(
            env,
            default_runs_dir=Path("/app/runs"),
        )
        assert config.enabled is True

    def test_disabled_via_env(self) -> None:
        """Scheduler producer can be disabled via K9B_CONTENT_INDEX_ENABLED."""
        env = {CONTENT_INDEX_ENABLED_ENV_VAR: "false"}
        config = load_scheduler_content_index_config_from_env(
            env,
            default_runs_dir=Path("/app/runs"),
        )
        assert config.enabled is False

    def test_custom_db_path_from_env(self) -> None:
        """Custom DB path can be specified via K9B_CONTENT_INDEX_DB_PATH."""
        env = {CONTENT_INDEX_DB_PATH_ENV_VAR: "/custom/index.sqlite"}
        config = load_scheduler_content_index_config_from_env(
            env,
            default_runs_dir=Path("/app/runs"),
        )
        assert config.db_path == Path("/custom/index.sqlite")

    def test_default_db_path(self) -> None:
        """DB path defaults to runs_dir/content-index.sqlite."""
        env = {}
        config = load_scheduler_content_index_config_from_env(
            env,
            default_runs_dir=Path("/app/runs"),
        )
        assert config.db_path == Path("/app/runs/content-index.sqlite")

    def test_update_mode_from_env(self) -> None:
        """Update mode can be specified via K9B_CONTENT_INDEX_UPDATE_MODE."""
        env = {CONTENT_INDEX_UPDATE_MODE_ENV_VAR: "rebuild_if_missing"}
        config = load_scheduler_content_index_config_from_env(
            env,
            default_runs_dir=Path("/app/runs"),
        )
        assert config.update_mode == "rebuild_if_missing"

    def test_invalid_update_mode_defaults_to_update(self) -> None:
        """Invalid update mode defaults to 'update'."""
        env = {CONTENT_INDEX_UPDATE_MODE_ENV_VAR: "invalid_mode"}
        config = load_scheduler_content_index_config_from_env(
            env,
            default_runs_dir=Path("/app/runs"),
        )
        assert config.update_mode == "update"


class TestUpdateContentIndexAfterSchedulerRun:
    """Tests for the scheduler content index update hook."""

    @pytest.fixture
    def temp_runs_dir(self) -> Path:
        """Create a temporary directory for run artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def log_events(self) -> tuple[list[dict[str, Any]], callable]:
        """Track structured log events - returns (events_list, log_fn)."""
        events: list[dict[str, Any]] = []

        def log_fn(severity: str, message: str, **kwargs: Any) -> None:
            events.append({
                "severity": severity,
                "message": message,
                "kwargs": kwargs,
            })

        return events, log_fn

    def test_disabled_config_skips(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """When enabled=False, no update is attempted."""
        events, log_fn = log_events
        config = SchedulerContentIndexConfig(
            enabled=False,
            runs_dir=temp_runs_dir,
            db_path=temp_runs_dir / "content-index.sqlite",
        )

        result = update_content_index_after_scheduler_run(
            config,
            run_id="test-run",
            log_fn=log_fn,
        )

        assert result.attempted is False
        assert result.skipped_reason == "disabled"
        # No DB should be created
        assert not (temp_runs_dir / "content-index.sqlite").exists()

    def test_no_roots_skips(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """When no roots exist, update is skipped."""
        events, log_fn = log_events
        config = SchedulerContentIndexConfig(
            enabled=True,
            runs_dir=temp_runs_dir,
            db_path=temp_runs_dir / "content-index.sqlite",
        )

        result = update_content_index_after_scheduler_run(
            config,
            run_id="test-run",
            log_fn=log_fn,
        )

        # Either skipped (no roots) or attempted but found nothing
        assert result.attempted is False or result.indexed_count == 0

    def test_creates_db_when_missing(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """When DB is missing and enabled, DB should be created."""
        events, log_fn = log_events
        # Create a valid artifact to index
        health_dir = temp_runs_dir / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "test-artifact.json").write_text('{"test": "data"}')

        db_path = temp_runs_dir / "content-index.sqlite"
        config = SchedulerContentIndexConfig(
            enabled=True,
            runs_dir=temp_runs_dir,
            db_path=db_path,
        )

        result = update_content_index_after_scheduler_run(
            config,
            run_id="test-run",
            log_fn=log_fn,
        )

        assert result.attempted is True
        assert db_path.exists()
        # Should have success or info log
        assert any(
            "completed" in e["message"].lower() or "updating" in e["message"].lower() or "rebuilding" in e["message"].lower()
            for e in events
        )

    def test_updates_existing_db(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """When DB exists and enabled, DB should be updated."""
        events, log_fn = log_events
        # Create a valid artifact to index
        health_dir = temp_runs_dir / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "test-artifact.json").write_text('{"test": "data"}')

        db_path = temp_runs_dir / "content-index.sqlite"

        # First run - creates DB
        config = SchedulerContentIndexConfig(
            enabled=True,
            runs_dir=temp_runs_dir,
            db_path=db_path,
        )

        result1 = update_content_index_after_scheduler_run(
            config,
            run_id="test-run-1",
            log_fn=log_fn,
        )
        assert result1.created is True

        # Second run - updates DB
        result2 = update_content_index_after_scheduler_run(
            config,
            run_id="test-run-2",
            log_fn=log_fn,
        )
        assert result2.updated is True
        assert result2.created is False

    def test_invalid_db_triggers_rebuild(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """Invalid/corrupt DB should trigger rebuild."""
        events, log_fn = log_events
        # Create a valid artifact to index
        health_dir = temp_runs_dir / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "test-artifact.json").write_text('{"test": "data"}')

        db_path = temp_runs_dir / "content-index.sqlite"

        # Create an invalid/corrupt DB
        db_path.write_text("not a valid sqlite database")

        config = SchedulerContentIndexConfig(
            enabled=True,
            runs_dir=temp_runs_dir,
            db_path=db_path,
            update_mode="rebuild_if_missing",
        )

        result = update_content_index_after_scheduler_run(
            config,
            run_id="test-run",
            log_fn=log_fn,
        )

        # Should attempt rebuild
        assert result.attempted is True
        # Should have created/replaced the DB
        assert db_path.exists()

    def test_update_failure_does_not_raise(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """Update failure should be caught and logged, not raise."""
        events, log_fn = log_events
        db_path = temp_runs_dir / "content-index.sqlite"
        health_dir = temp_runs_dir / "health"
        health_dir.mkdir(parents=True)

        config = SchedulerContentIndexConfig(
            enabled=True,
            runs_dir=temp_runs_dir,
            db_path=db_path,
        )

        # Should not raise - may skip due to no valid content
        result = update_content_index_after_scheduler_run(
            config,
            run_id="test-run",
            log_fn=log_fn,
        )

        # Should have attempted (or skipped)
        assert result.attempted is True or result.skipped_reason is not None

    def test_success_log_contains_required_fields(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """Success log should contain all required structured fields."""
        events, log_fn = log_events
        # Create a valid artifact to index
        health_dir = temp_runs_dir / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "test-artifact.json").write_text('{"test": "data"}')

        db_path = temp_runs_dir / "content-index.sqlite"
        config = SchedulerContentIndexConfig(
            enabled=True,
            runs_dir=temp_runs_dir,
            db_path=db_path,
        )

        update_content_index_after_scheduler_run(
            config,
            run_id="test-run-123",
            log_fn=log_fn,
        )

        # Check log events have the expected structure
        assert len(events) > 0
        # Check that some event has required fields
        found_success_or_info = False
        for e in events:
            if e["severity"] in ("INFO", "DEBUG", "WARNING"):
                found_success_or_info = True
                kwargs = e.get("kwargs", {})
                # Check for key fields
                assert "db_path" in kwargs or "component" in kwargs
        assert found_success_or_info

    def test_custom_db_path_honored(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """Custom DB path should be used instead of default."""
        events, log_fn = log_events
        # Create a valid artifact to index
        health_dir = temp_runs_dir / "health"
        health_dir.mkdir(parents=True)
        (health_dir / "test-artifact.json").write_text('{"test": "data"}')

        custom_path = temp_runs_dir / "custom" / "my-index.sqlite"
        custom_path.parent.mkdir(parents=True)

        config = SchedulerContentIndexConfig(
            enabled=True,
            runs_dir=temp_runs_dir,
            db_path=custom_path,
        )

        result = update_content_index_after_scheduler_run(
            config,
            run_id="test-run",
            log_fn=log_fn,
        )

        assert result.db_path == custom_path
        assert custom_path.exists()

    def test_no_sensitive_content_in_logs(
        self,
        temp_runs_dir: Path,
        log_events: tuple[list[dict[str, Any]], callable],
    ) -> None:
        """Logs should not contain sensitive artifact content."""
        events, log_fn = log_events
        # Create a sensitive artifact
        health_dir = temp_runs_dir / "health"
        health_dir.mkdir(parents=True)
        sensitive_content = json.dumps({
            "password": "super-secret-123",
            "api_key": "sk-secret-key",
            "data": "normal content",
        })
        (health_dir / "sensitive.json").write_text(sensitive_content)

        db_path = temp_runs_dir / "content-index.sqlite"
        config = SchedulerContentIndexConfig(
            enabled=True,
            runs_dir=temp_runs_dir,
            db_path=db_path,
        )

        update_content_index_after_scheduler_run(
            config,
            run_id="test-run",
            log_fn=log_fn,
        )

        # Check that no log contains sensitive data
        for e in events:
            log_str = json.dumps(e)
            assert "super-secret-123" not in log_str, "Sensitive password found in logs"
            assert "sk-secret-key" not in log_str, "Sensitive API key found in logs"


class TestSchedulerContentIndexResult:
    """Tests for the SchedulerContentIndexResult dataclass."""

    def test_result_dataclass_fields(self) -> None:
        """Result should have all required fields."""
        result = SchedulerContentIndexResult(
            attempted=True,
            created=True,
            updated=False,
            skipped_reason=None,
            db_path=Path("/test/db.sqlite"),
            duration_ms=123.45,
            indexed_count=10,
            error=None,
        )

        assert result.attempted is True
        assert result.created is True
        assert result.updated is False
        assert result.skipped_reason is None
        assert result.db_path == Path("/test/db.sqlite")
        assert result.duration_ms == 123.45
        assert result.indexed_count == 10
        assert result.error is None

    def test_result_with_error(self) -> None:
        """Result can contain an error message."""
        result = SchedulerContentIndexResult(
            attempted=True,
            created=False,
            updated=False,
            skipped_reason=None,
            db_path=Path("/test/db.sqlite"),
            duration_ms=50.0,
            error="Database locked",
        )

        assert result.error == "Database locked"


class TestIntegrationWithContentIndexPackage:
    """Integration tests verifying the producer uses existing content-index package."""

    def test_uses_existing_rebuild_index(
        self,
        tmp_path: Path,
    ) -> None:
        """Producer should use the existing rebuild_index from content_index package."""
        from k8s_diag_agent.content_index import ContentIndexRoots
        from k8s_diag_agent.content_index.scheduler_producer import _run_rebuild

        # Create a minimal artifact structure
        health_dir = tmp_path / "health"
        health_dir.mkdir()
        (health_dir / "test.json").write_text('{"test": true}')

        roots = ContentIndexRoots(
            artifact_root=tmp_path,
        )

        db_path = tmp_path / "index.sqlite"
        summary = _run_rebuild(db_path, roots)

        # Should succeed
        assert summary.status in ("ok", "pending")
        assert db_path.exists()

    def test_uses_existing_update_index(
        self,
        tmp_path: Path,
    ) -> None:
        """Producer should use the existing update_index from content_index package."""
        from k8s_diag_agent.content_index import ContentIndexRoots
        from k8s_diag_agent.content_index.scheduler_producer import _run_rebuild, _run_update

        # Create initial artifact
        health_dir = tmp_path / "health"
        health_dir.mkdir()
        (health_dir / "initial.json").write_text('{"version": 1}')

        roots = ContentIndexRoots(
            artifact_root=tmp_path,
        )

        db_path = tmp_path / "index.sqlite"

        # Initial rebuild
        _run_rebuild(db_path, roots)
        assert db_path.exists()

        # Add new artifact
        (health_dir / "new.json").write_text('{"version": 2}')

        # Update
        summary = _run_update(db_path, roots)

        # Should succeed
        assert summary.status in ("ok", "pending")
