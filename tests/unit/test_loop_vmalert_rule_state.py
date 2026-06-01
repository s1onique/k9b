"""Unit tests for vmalert rule state collection runner in health loop.

Tests cover:
- run_vmalert_rule_state_collection(): missing inventory returns None
- No eligible sources returns None
- Eligible source writes artifact and returns stats
- FileExistsError is non-fatal
- OSError/RuntimeError/ValueError from write is non-fatal and logged
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from k8s_diag_agent.external_analysis.vmalert_rule_state_artifact import (
    VmalertRuleStateArtifact,
)

# Import the function under test
from k8s_diag_agent.health.loop_vmalert_rule_state import (
    run_vmalert_rule_state_collection,
)

# --- Test Fixtures ---


@pytest.fixture
def directories(tmp_path: Path) -> dict[str, Path]:
    """Return directories dict for the function."""
    return {"root": tmp_path}


@pytest.fixture
def eligible_inventory() -> Any:
    """Return inventory with eligible source."""
    from k8s_diag_agent.external_analysis.vmalert_discovery import (
        VmalertSource,
        VmalertSourceInventory,
        VmalertSourceState,
    )

    inventory = VmalertSourceInventory()
    inventory.add_source(
        VmalertSource(
            source_id="service:ns/vmalert",
            endpoint="http://vmalert.ns:8080",
            namespace="ns",
            name="vmalert",
            state=VmalertSourceState.DISCOVERED,
        )
    )
    return inventory


# --- run_vmalert_rule_state_collection Tests ---


class TestRunVmalertRuleStateCollection:
    """Tests for run_vmalert_rule_state_collection()."""

    def test_missing_inventory_returns_none_quietly(
        self,
        directories: dict[str, Path],
    ) -> None:
        """Missing inventory returns None without raising."""
        result = run_vmalert_rule_state_collection(
            inventory=None,
            directories=directories,
            run_id="test-run-001",
        )

        assert result is None

    def test_no_eligible_sources_returns_none_quietly(
        self,
        directories: dict[str, Path],
    ) -> None:
        """No eligible sources returns None without raising."""
        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            VmalertSource,
            VmalertSourceInventory,
            VmalertSourceState,
        )

        inventory = VmalertSourceInventory()
        # Add only non-eligible sources
        inventory.add_source(
            VmalertSource(
                source_id="degraded",
                endpoint="http://degraded:8080",
                state=VmalertSourceState.DEGRADED,
            )
        )
        inventory.add_source(
            VmalertSource(
                source_id="missing",
                endpoint="http://missing:8080",
                state=VmalertSourceState.MISSING,
            )
        )

        result = run_vmalert_rule_state_collection(
            inventory=inventory,
            directories=directories,
            run_id="test-run-002",
        )

        assert result is None

    def test_eligible_source_writes_artifact_and_returns_stats(
        self,
        directories: dict[str, Path],
        eligible_inventory: Any,
    ) -> None:
        """Eligible source writes artifact and returns stats."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T10:00:00Z",
        )

        # Patch where it's used (inside run_vmalert_rule_state_collection)
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ):
            result = run_vmalert_rule_state_collection(
                inventory=eligible_inventory,
                directories=directories,
                run_id="test-run-003",
            )

        assert result is not None
        assert result["source_count"] == 1
        assert result["fetched_source_count"] == 1
        assert result["failed_source_count"] == 0

    def test_file_exists_error_is_non_fatal(
        self,
        directories: dict[str, Path],
        eligible_inventory: Any,
    ) -> None:
        """FileExistsError is caught and non-fatal."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T10:00:00Z",
        )

        # First call creates the artifact
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ):
            run_vmalert_rule_state_collection(
                inventory=eligible_inventory,
                directories=directories,
                run_id="test-run-004",
            )

        # Second call with same run_id should NOT raise (FileExistsError is caught)
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ):
            result2 = run_vmalert_rule_state_collection(
                inventory=eligible_inventory,
                directories=directories,
                run_id="test-run-004",
            )

        # Should return stats without raising
        assert result2 is not None
        assert result2["source_count"] == 1

    def test_os_error_from_write_is_non_fatal_and_logged(
        self,
        directories: dict[str, Path],
        eligible_inventory: Any,
    ) -> None:
        """OSError from write is non-fatal."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T10:00:00Z",
        )

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ), patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.write_vmalert_rule_state",
            side_effect=OSError("Disk full"),
        ), patch(
            "k8s_diag_agent.health.loop_vmalert_rule_state._log"
        ) as mock_log:
            result = run_vmalert_rule_state_collection(
                inventory=eligible_inventory,
                directories=directories,
                run_id="test-run-005",
            )

        # Should return stats without raising
        assert result is not None
        assert result["source_count"] == 1

        # Should have logged a warning
        mock_log.assert_called()

    def test_runtime_error_from_write_is_non_fatal(
        self,
        directories: dict[str, Path],
        eligible_inventory: Any,
    ) -> None:
        """RuntimeError from write is non-fatal."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T10:00:00Z",
        )

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ), patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.write_vmalert_rule_state",
            side_effect=RuntimeError("Serialization failed"),
        ):
            result = run_vmalert_rule_state_collection(
                inventory=eligible_inventory,
                directories=directories,
                run_id="test-run-006",
            )

        # Should return stats without raising
        assert result is not None

    def test_value_error_from_write_is_non_fatal(
        self,
        directories: dict[str, Path],
        eligible_inventory: Any,
    ) -> None:
        """ValueError from write is non-fatal."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T10:00:00Z",
        )

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ), patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.write_vmalert_rule_state",
            side_effect=ValueError("Invalid artifact data"),
        ):
            result = run_vmalert_rule_state_collection(
                inventory=eligible_inventory,
                directories=directories,
                run_id="test-run-007",
            )

        # Should return stats without raising
        assert result is not None

    def test_includes_all_expected_stats_fields(
        self,
        directories: dict[str, Path],
        eligible_inventory: Any,
    ) -> None:
        """Result includes all expected stats fields."""
        artifact = VmalertRuleStateArtifact(
            source_count=2,
            fetched_source_count=1,
            failed_source_count=1,
            alerts=(),
            rule_groups=(),
            fetch_errors=({"error": "test"},),
            captured_at="2024-01-01T10:00:00Z",
        )

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ):
            result = run_vmalert_rule_state_collection(
                inventory=eligible_inventory,
                directories=directories,
                run_id="test-run-008",
            )

        assert result is not None
        assert "source_count" in result
        assert "fetched_source_count" in result
        assert "failed_source_count" in result
        assert "alert_count" in result
        assert "firing_alert_count" in result
        assert "pending_alert_count" in result
        assert "critical_firing_count" in result
        assert "rule_group_count" in result
        assert "fetch_error_count" in result
        assert "captured_at" in result

    def test_cluster_label_passed_to_logging(
        self,
        directories: dict[str, Path],
        eligible_inventory: Any,
    ) -> None:
        """cluster_label is passed through to logging."""
        artifact = VmalertRuleStateArtifact(
            source_count=0,
            fetched_source_count=0,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T10:00:00Z",
        )

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ), patch(
            "k8s_diag_agent.health.loop_vmalert_rule_state._log"
        ) as mock_log:
            run_vmalert_rule_state_collection(
                inventory=eligible_inventory,
                directories=directories,
                run_id="test-run-009",
                cluster_label="test-cluster",
            )

        # Check that cluster_label appears in logged events
        log_args = mock_log.call_args_list
        cluster_label_in_logs = any(
            "test-cluster" in str(call)
            for call in log_args
        )
        assert cluster_label_in_logs

    def test_includes_all_eligible_states(
        self,
        directories: dict[str, Path],
    ) -> None:
        """All eligible states are handled correctly."""
        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            VmalertSource,
            VmalertSourceInventory,
            VmalertSourceState,
        )

        inventory = VmalertSourceInventory()

        # All eligible states
        eligible_states = [
            VmalertSourceState.DISCOVERED,
            VmalertSourceState.AUTO_TRACKED,
            VmalertSourceState.MANUAL,
            VmalertSourceState.DISCOVERED_BUT_UNVERIFIED,
        ]

        for i, state in enumerate(eligible_states):
            inventory.add_source(
                VmalertSource(
                    source_id=f"source-{i}",
                    endpoint=f"http://source-{i}:8080",
                    state=state,
                )
            )

        artifact = VmalertRuleStateArtifact(
            source_count=len(eligible_states),
            fetched_source_count=len(eligible_states),
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T10:00:00Z",
        )

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_rule_state_artifact.collect_vmalert_rule_state",
            return_value=artifact,
        ):
            result = run_vmalert_rule_state_collection(
                inventory=inventory,
                directories=directories,
                run_id="test-run-010",
            )

        assert result is not None
        assert result["source_count"] == len(eligible_states)
