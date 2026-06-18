"""test_api_runtime_status.py - Tests for runtime status API.

Tests cover:
- Log counts derived from real fixture input (deterministic with injected clock)
- Missing log data returns unavailable (None)
- Malformed JSON lines don't crash the endpoint
- PVC usage via statvfs (real filesystem stats when path exists)
- PVC usage unavailable when path does not exist
- Window boundary tests using injected clock
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.ui.api_runtime_status import (
    _build_log_windows_from_health_log,
    _build_pvc_usage_from_statvfs,
    _build_pvc_usage_unavailable,
    _count_severity_by_window,
    _empty_log_windows,
    _get_filesystem_stats,
    build_runtime_status_payload,
)

# Fixed reference time for deterministic tests
_REFERENCE_TIME = datetime(2026, 6, 6, 22, 40, 0, tzinfo=UTC)


def _make_log_entry(timestamp: datetime, severity: str, component: str = "test") -> str:
    """Helper to create a JSON log entry string."""
    return json.dumps({
        "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "severity": severity,
        "component": component,
    })


def _write_health_log(tmp_path: Path, entries: list[str]) -> None:
    """Helper to write a health.log file."""
    health_log = tmp_path / "health" / "health.log"
    health_log.parent.mkdir(parents=True)
    health_log.write_text("\n".join(entries) + "\n", encoding="utf-8")


class TestLogWindowCounts:
    """Tests for log window count extraction from health.log."""

    def test_counts_from_real_fixture(self, tmp_path: Path) -> None:
        """Log counts are derived from real structured log fixture input."""
        # Entries at 22:35, 22:36, 22:37, 22:38 - all within 5m window (22:35 to 22:40)
        entries = [
            _make_log_entry(datetime(2026, 6, 6, 22, 35, 0, tzinfo=UTC), "WARNING"),
            _make_log_entry(datetime(2026, 6, 6, 22, 36, 0, tzinfo=UTC), "ERROR"),
            _make_log_entry(datetime(2026, 6, 6, 22, 37, 0, tzinfo=UTC), "WARNING"),
            _make_log_entry(datetime(2026, 6, 6, 22, 38, 0, tzinfo=UTC), "INFO"),
        ]
        _write_health_log(tmp_path, entries)

        result = _build_log_windows_from_health_log(tmp_path, now=_REFERENCE_TIME)

        # 2 WARNING, 1 ERROR in the 5m window (22:35 to 22:40)
        assert result.backend.m5.warning == 2
        assert result.backend.m5.error == 1
        assert result.scheduler.m5.warning == 2
        assert result.scheduler.m5.error == 1

    def test_missing_log_file_returns_unavailable(self, tmp_path: Path) -> None:
        """Missing health.log returns unavailable state (None values)."""
        # No health.log created - path does not exist
        result = _build_log_windows_from_health_log(tmp_path, now=_REFERENCE_TIME)

        assert result.backend.m5.warning is None
        assert result.backend.m5.error is None
        assert result.backend.m10.warning is None
        assert result.backend.m10.error is None
        assert result.backend.m15.warning is None
        assert result.backend.m15.error is None
        assert result.scheduler.m5.warning is None

    def test_malformed_json_lines_handled_gracefully(self, tmp_path: Path) -> None:
        """Malformed JSON lines are skipped without crashing."""
        entries = [
            _make_log_entry(datetime(2026, 6, 6, 22, 35, 0, tzinfo=UTC), "WARNING"),
            "not valid json",
            _make_log_entry(datetime(2026, 6, 6, 22, 36, 0, tzinfo=UTC), "ERROR"),
            "also not valid",
            _make_log_entry(datetime(2026, 6, 6, 22, 37, 0, tzinfo=UTC), "INFO"),
        ]
        _write_health_log(tmp_path, entries)

        result = _build_log_windows_from_health_log(tmp_path, now=_REFERENCE_TIME)

        # Should count valid entries only
        assert result.backend.m5.warning == 1
        assert result.backend.m5.error == 1

    def test_empty_log_file_returns_zero_counts(self, tmp_path: Path) -> None:
        """Empty health.log returns explicit zero counts, not unavailable."""
        _write_health_log(tmp_path, [])

        result = _build_log_windows_from_health_log(tmp_path, now=_REFERENCE_TIME)

        # Empty file = no entries = zero explicit counts (0), not unavailable (None)
        assert result.backend.m5.warning == 0
        assert result.backend.m5.error == 0

    def test_zero_counts_are_explicit_not_unavailable(self, tmp_path: Path) -> None:
        """Zero error/warning counts are explicit (0), not unavailable (None)."""
        # Only INFO-level entries (which are filtered out)
        entries = [
            _make_log_entry(datetime(2026, 6, 6, 22, 35, 0, tzinfo=UTC), "INFO"),
            _make_log_entry(datetime(2026, 6, 6, 22, 36, 0, tzinfo=UTC), "INFO"),
        ]
        _write_health_log(tmp_path, entries)

        result = _build_log_windows_from_health_log(tmp_path, now=_REFERENCE_TIME)

        # 0 explicit counts (INFO is filtered, ERROR/WARNING are 0)
        assert result.backend.m5.warning == 0
        assert result.backend.m5.error == 0
        assert result.backend.m10.warning == 0
        assert result.backend.m10.error == 0
        assert result.backend.m15.warning == 0
        assert result.backend.m15.error == 0

    def test_partial_log_file_handled(self, tmp_path: Path) -> None:
        """Partial/missing fields in log entries don't crash counting."""
        entries = [
            _make_log_entry(datetime(2026, 6, 6, 22, 35, 0, tzinfo=UTC), "WARNING"),
            '{"timestamp": "2026-06-06T22:36:00Z"}',  # Missing severity - skipped
            _make_log_entry(datetime(2026, 6, 6, 22, 36, 30, tzinfo=UTC), "ERROR"),
            _make_log_entry(datetime(2026, 6, 6, 22, 37, 0, tzinfo=UTC), "WARNING"),
        ]
        _write_health_log(tmp_path, entries)

        result = _build_log_windows_from_health_log(tmp_path, now=_REFERENCE_TIME)

        # Should count valid entries: 2 WARNING, 1 ERROR
        assert result.backend.m5.warning == 2
        assert result.backend.m5.error == 1


class TestWindowBoundaries:
    """Boundary tests for sliding time windows using injected clock."""

    def test_entry_inside_5m_counts_for_all_windows(self, tmp_path: Path) -> None:
        """Entry at exactly 5 minutes ago counts for 5/10/15 minute windows."""
        entry_time = _REFERENCE_TIME - timedelta(minutes=5)
        _write_health_log(tmp_path, [_make_log_entry(entry_time, "WARNING")])

        result = _count_severity_by_window(tmp_path / "health" / "health.log", now=_REFERENCE_TIME)

        # Entry is >= window_start for all windows (>= 22:35, >= 22:30, >= 22:25)
        assert result[5]["WARNING"] == 1
        assert result[10]["WARNING"] == 1
        assert result[15]["WARNING"] == 1

    def test_entry_outside_5m_inside_10m(self, tmp_path: Path) -> None:
        """Entry at 7 minutes ago counts for 10/15 but not 5 minute window."""
        entry_time = _REFERENCE_TIME - timedelta(minutes=7)
        _write_health_log(tmp_path, [_make_log_entry(entry_time, "ERROR")])

        result = _count_severity_by_window(tmp_path / "health" / "health.log", now=_REFERENCE_TIME)

        # Entry is < 5m window_start (22:35), >= 10m window_start (22:30)
        assert result[5]["ERROR"] == 0
        assert result[10]["ERROR"] == 1
        assert result[15]["ERROR"] == 1

    def test_entry_outside_10m_inside_15m(self, tmp_path: Path) -> None:
        """Entry at 12 minutes ago counts only for 15 minute window."""
        entry_time = _REFERENCE_TIME - timedelta(minutes=12)
        _write_health_log(tmp_path, [_make_log_entry(entry_time, "WARNING")])

        result = _count_severity_by_window(tmp_path / "health" / "health.log", now=_REFERENCE_TIME)

        # Entry is < 5m and 10m window_starts, >= 15m window_start (22:25)
        assert result[5]["WARNING"] == 0
        assert result[10]["WARNING"] == 0
        assert result[15]["WARNING"] == 1

    def test_entry_outside_15m_counts_nothing(self, tmp_path: Path) -> None:
        """Entry at 20 minutes ago counts for no window."""
        entry_time = _REFERENCE_TIME - timedelta(minutes=20)
        _write_health_log(tmp_path, [_make_log_entry(entry_time, "ERROR")])

        result = _count_severity_by_window(tmp_path / "health" / "health.log", now=_REFERENCE_TIME)

        # Entry is < all window_starts
        assert result[5]["ERROR"] == 0
        assert result[10]["ERROR"] == 0
        assert result[15]["ERROR"] == 0

    def test_multiple_entries_at_window_boundaries(self, tmp_path: Path) -> None:
        """Multiple entries at different window boundaries are counted correctly."""
        entries = [
            _make_log_entry(_REFERENCE_TIME - timedelta(minutes=3), "WARNING"),  # All windows
            _make_log_entry(_REFERENCE_TIME - timedelta(minutes=7), "ERROR"),     # 10m, 15m only
            _make_log_entry(_REFERENCE_TIME - timedelta(minutes=12), "WARNING"),  # 15m only
            _make_log_entry(_REFERENCE_TIME - timedelta(minutes=18), "ERROR"),    # None
        ]
        _write_health_log(tmp_path, entries)

        result = _count_severity_by_window(tmp_path / "health" / "health.log", now=_REFERENCE_TIME)

        assert result[5]["WARNING"] == 1
        assert result[5]["ERROR"] == 0
        assert result[10]["WARNING"] == 1
        assert result[10]["ERROR"] == 1
        assert result[15]["WARNING"] == 2
        assert result[15]["ERROR"] == 1


class TestPvcUsage:
    """Tests for PVC usage extraction."""

    def test_pvc_returns_unavailable_none(self) -> None:
        """PVC usage returns None (unavailable) as no snapshot data exists."""
        result = _build_pvc_usage_unavailable()
        assert result is None

    def test_payload_pvc_returns_unavailable_when_path_not_found(self, tmp_path: Path) -> None:
        """RuntimeStatusPayload backend_pvc has unavailable_reason when mount path not found."""
        payload = build_runtime_status_payload(tmp_path, now=_REFERENCE_TIME)
        # PVC is now always populated (not None), with unavailable_reason when path missing
        assert payload.backend_pvc is not None
        assert payload.backend_pvc.name == "backend-data"
        assert payload.backend_pvc.source == "statvfs"
        assert payload.backend_pvc.capacity_bytes is None
        assert payload.backend_pvc.unavailable_reason is not None
        assert "not found" in payload.backend_pvc.unavailable_reason.lower()


class TestFullPayload:
    """Tests for complete runtime status payload building."""

    def test_build_payload_returns_valid_structure(self, tmp_path: Path) -> None:
        """Full payload has expected structure."""
        payload = build_runtime_status_payload(tmp_path, now=_REFERENCE_TIME)

        assert payload.log_windows is not None
        assert hasattr(payload.log_windows, "backend")
        assert hasattr(payload.log_windows, "scheduler")

    def test_build_payload_with_real_log_data(self, tmp_path: Path) -> None:
        """Full payload contains real data when health.log exists."""
        entries = [
            _make_log_entry(datetime(2026, 6, 6, 22, 35, 0, tzinfo=UTC), "WARNING"),
            _make_log_entry(datetime(2026, 6, 6, 22, 36, 0, tzinfo=UTC), "ERROR"),
        ]
        _write_health_log(tmp_path, entries)

        payload = build_runtime_status_payload(tmp_path, now=_REFERENCE_TIME)

        # PVC is always populated (not None), with unavailable_reason since path doesn't exist
        assert payload.backend_pvc is not None
        assert payload.backend_pvc.name == "backend-data"
        assert payload.backend_pvc.unavailable_reason is not None
        # Log windows have real data
        assert payload.log_windows.backend.m5.warning == 1
        assert payload.log_windows.backend.m5.error == 1

    def test_build_payload_missing_log_returns_unavailable(self, tmp_path: Path) -> None:
        """Full payload with missing log returns unavailable log state."""
        # No health.log created
        payload = build_runtime_status_payload(tmp_path, now=_REFERENCE_TIME)

        # PVC is always populated (not None), with unavailable_reason since path doesn't exist
        assert payload.backend_pvc is not None
        assert payload.backend_pvc.unavailable_reason is not None
        # Log windows are unavailable
        assert payload.log_windows.backend.m5.warning is None
        assert payload.log_windows.backend.m5.error is None


class TestEmptyLogWindows:
    """Tests for _empty_log_windows helper."""

    def test_empty_returns_unavailable_for_all_windows(self) -> None:
        """_empty_log_windows returns None for all severity fields."""
        result = _empty_log_windows()

        assert result.backend.m5.warning is None
        assert result.backend.m5.error is None
        assert result.backend.m10.warning is None
        assert result.backend.m10.error is None
        assert result.backend.m15.warning is None
        assert result.backend.m15.error is None
        assert result.scheduler.m5.warning is None
        assert result.scheduler.m5.error is None
        assert result.scheduler.m10.warning is None
        assert result.scheduler.m10.error is None
        assert result.scheduler.m15.warning is None
        assert result.scheduler.m15.error is None


class TestSeverityCounting:
    """Tests for _count_severity_by_window helper."""

    def test_count_returns_counts_for_all_windows(self, tmp_path: Path) -> None:
        """_count_severity_by_window returns counts for 5, 10, 15 minute windows."""
        entries = [
            _make_log_entry(datetime(2026, 6, 6, 22, 35, 0, tzinfo=UTC), "WARNING"),
            _make_log_entry(datetime(2026, 6, 6, 22, 36, 0, tzinfo=UTC), "ERROR"),
            _make_log_entry(datetime(2026, 6, 6, 22, 37, 0, tzinfo=UTC), "WARNING"),
        ]
        _write_health_log(tmp_path, entries)

        result = _count_severity_by_window(tmp_path / "health" / "health.log", now=_REFERENCE_TIME)

        assert 5 in result
        assert 10 in result
        assert 15 in result
        assert "WARNING" in result[5]
        assert "ERROR" in result[5]

    def test_ignores_info_severity(self, tmp_path: Path) -> None:
        """INFO severity entries are not counted."""
        entries = [
            _make_log_entry(datetime(2026, 6, 6, 22, 35, 0, tzinfo=UTC), "INFO"),
            _make_log_entry(datetime(2026, 6, 6, 22, 36, 0, tzinfo=UTC), "DEBUG"),
        ]
        _write_health_log(tmp_path, entries)

        result = _count_severity_by_window(tmp_path / "health" / "health.log", now=_REFERENCE_TIME)

        assert result[5]["WARNING"] == 0
        assert result[5]["ERROR"] == 0


class TestPvcUsageStatvfs:
    """Tests for PVC usage via os.statvfs()."""

    def test_statvfs_happy_path(self, tmp_path: Path) -> None:
        """PVC usage returns real stats when mount path exists and is readable."""
        # Create the mount path directory
        mount_path = tmp_path / "mount"
        mount_path.mkdir()

        # Mock statvfs to return predictable values
        # 1GB total, 512MB free, 512MB used (50%)
        mock_stat = type("MockStatvfs", (), {
            "f_frsize": 4096,
            "f_blocks": 262144,  # 1GB / 4096
            "f_bfree": 131072,   # 512MB / 4096
            "f_bavail": 131072,  # 512MB / 4096 (same as f_bfree for root)
        })()

        with patch("os.path.exists", return_value=True):
            with patch("os.statvfs", return_value=mock_stat):
                result = _get_filesystem_stats("test-pvc", str(mount_path))

        assert result.name == "test-pvc"
        assert result.used_bytes == 536870912  # 512MB
        assert result.free_bytes == 536870912  # 512MB
        assert result.capacity_bytes == 1073741824  # 1GB
        assert result.used_percent == 50
        assert result.source == "statvfs"
        assert result.unavailable_reason is None

    def test_missing_path_returns_unavailable(self, tmp_path: Path) -> None:
        """PVC usage returns unavailable when mount path does not exist."""
        result = _get_filesystem_stats("test-pvc", "/nonexistent/path")

        assert result.name == "test-pvc"
        assert result.used_bytes is None
        assert result.free_bytes is None
        assert result.capacity_bytes is None
        assert result.used_percent is None
        assert result.source == "statvfs"
        assert "not found" in result.unavailable_reason.lower()

    def test_zero_capacity_returns_unavailable(self, tmp_path: Path) -> None:
        """PVC usage returns unavailable when filesystem has zero capacity."""
        mount_path = tmp_path / "mount"
        mount_path.mkdir()

        # Mock statvfs with zero blocks
        mock_stat = type("MockStatvfs", (), {
            "f_frsize": 4096,
            "f_blocks": 0,
            "f_bfree": 0,
            "f_bavail": 0,
        })()

        with patch("os.path.exists", return_value=True):
            with patch("os.statvfs", return_value=mock_stat):
                result = _get_filesystem_stats("test-pvc", str(mount_path))

        assert result.used_bytes is None
        assert result.capacity_bytes is None
        assert result.used_percent is None
        assert result.unavailable_reason == "Zero capacity filesystem"

    def test_oserror_returns_unavailable(self, tmp_path: Path) -> None:
        """PVC usage returns unavailable when os.statvfs raises OSError."""
        mount_path = tmp_path / "mount"
        mount_path.mkdir()

        with patch("os.path.exists", return_value=True):
            with patch("os.statvfs", side_effect=OSError("Permission denied")):
                result = _get_filesystem_stats("test-pvc", str(mount_path))

        assert result.used_bytes is None
        assert result.free_bytes is None
        assert result.capacity_bytes is None
        assert result.used_percent is None
        assert result.source == "statvfs"
        assert "permission denied" in result.unavailable_reason.lower()

    def test_build_pvc_usage_from_statvfs_returns_none_for_unknown_pvc(self) -> None:
        """_build_pvc_usage_from_statvfs returns None for unknown PVC names."""
        result = _build_pvc_usage_from_statvfs("unknown-pvc")
        assert result is None

    def test_build_pvc_usage_from_statvfs_returns_stats_for_known_pvc(self, tmp_path: Path) -> None:
        """_build_pvc_usage_from_statvfs returns stats for configured PVC names."""
        # Mock statvfs to return predictable values
        mock_stat = type("MockStatvfs", (), {
            "f_frsize": 4096,
            "f_blocks": 262144,  # 1GB
            "f_bfree": 65536,    # 256MB free
            "f_bavail": 65536,   # 256MB available
        })()

        with patch("os.path.exists", return_value=True):
            with patch("os.statvfs", return_value=mock_stat):
                # backend-data is configured in _RUNTIME_STATUS_PVC_MOUNTS
                result = _build_pvc_usage_from_statvfs("backend-data")

        assert result is not None
        assert result.name == "backend-data"
        assert result.capacity_bytes == 1073741824  # 1GB
        assert result.source == "statvfs"


class TestPayloadPvcStatvfs:
    """Tests for RuntimeStatusPayload PVC field with statvfs."""

    def test_payload_pvc_has_statvfs_data(self, tmp_path: Path) -> None:
        """RuntimeStatusPayload backend_pvc contains statvfs data."""
        # Create health.log so log windows are populated
        _write_health_log(tmp_path, [])

        # Mock statvfs for the actual mount path check
        mock_stat = type("MockStatvfs", (), {
            "f_frsize": 4096,
            "f_blocks": 262144,
            "f_bfree": 131072,
            "f_bavail": 131072,
        })()

        # Must mock both os.path.exists AND os.statvfs
        with patch("os.path.exists", return_value=True):
            with patch("os.statvfs", return_value=mock_stat):
                payload = build_runtime_status_payload(tmp_path, now=_REFERENCE_TIME)

        # PVC should now be populated, not None
        assert payload.backend_pvc is not None
        assert payload.backend_pvc.name == "backend-data"
        assert payload.backend_pvc.source == "statvfs"
        assert payload.backend_pvc.capacity_bytes is not None

    def test_payload_to_dict_includes_pvc_fields(self, tmp_path: Path) -> None:
        """RuntimeStatusPayload.to_dict() includes source and unavailable_reason."""
        mock_stat = type("MockStatvfs", (), {
            "f_frsize": 4096,
            "f_blocks": 262144,
            "f_bfree": 131072,
            "f_bavail": 131072,
        })()

        # Must mock both os.path.exists AND os.statvfs
        with patch("os.path.exists", return_value=True):
            with patch("os.statvfs", return_value=mock_stat):
                payload = build_runtime_status_payload(tmp_path, now=_REFERENCE_TIME)

        # Convert to dict
        result = payload.to_dict()

        # Verify PVC fields are present
        assert result["backend_pvc"] is not None
        assert "source" in result["backend_pvc"]
        assert "unavailable_reason" in result["backend_pvc"]
        assert result["backend_pvc"]["source"] == "statvfs"
        assert result["backend_pvc"]["unavailable_reason"] is None
