"""Unit tests for vmalert rule state artifact persistence module.

Tests cover:
- VmalertRuleStateArtifact: counts, properties, to_dict/from_dict
- FetchError: to_dict
- build_rule_state_from_fetch_results(): aggregation logic
- write_vmalert_rule_state(): artifact writing
- read_vmalert_rule_state(): artifact reading
- collect_vmalert_rule_state(): collection orchestration
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from k8s_diag_agent.external_analysis.vmalert_client import (
    VmalertFetchResult,
    VmalertFetchStatus,
)
from k8s_diag_agent.external_analysis.vmalert_rule_state import (
    AlertState,
    VmalertAlertSignal,
    VmalertRuleGroup,
)
from k8s_diag_agent.external_analysis.vmalert_rule_state_artifact import (
    FetchError,
    VmalertRuleStateArtifact,
    build_rule_state_from_fetch_results,
    collect_vmalert_rule_state,
    read_vmalert_rule_state,
    vmalert_rule_state_exists,
    write_vmalert_rule_state,
)

# --- Test Fixtures ---


@pytest.fixture
def valid_fetch_result() -> VmalertFetchResult:
    """Valid fetch result with alerts."""
    return VmalertFetchResult(
        status=VmalertFetchStatus.OK,
        source_endpoint="http://vmalert.ns:8080",
        captured_at="2024-01-01T10:00:00Z",
        raw_response={
            "status": "success",
            "data": {
                "alerts": [
                    {
                        "state": "firing",
                        "labels": {
                            "alertname": "TestAlert",
                            "severity": "critical",
                        },
                    }
                ]
            },
        },
        fetch_duration_ms=100,
    )


@pytest.fixture
def failed_fetch_result() -> VmalertFetchResult:
    """Failed fetch result."""
    return VmalertFetchResult(
        status=VmalertFetchStatus.FETCH_ERROR,
        source_endpoint="http://vmalert.ns:8081",
        captured_at="2024-01-01T10:00:00Z",
        error="Connection refused",
    )


@pytest.fixture
def rules_fetch_result() -> VmalertFetchResult:
    """Fetch result with rules instead of alerts."""
    return VmalertFetchResult(
        status=VmalertFetchStatus.OK,
        source_endpoint="http://vmalert.ns:8080",
        captured_at="2024-01-01T10:00:00Z",
        raw_response={
            "status": "success",
            "data": {
                "groups": [
                    {
                        "name": "test-group",
                        "rules": [
                            {
                                "name": "TestRule",
                                "health": "ok",
                                "alerts": [
                                    {
                                        "state": "firing",
                                        "labels": {"alertname": "RuleAlert"},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        },
        fetch_duration_ms=150,
    )


# --- VmalertRuleStateArtifact Tests ---


class TestVmalertRuleStateArtifact:
    """Tests for VmalertRuleStateArtifact model."""

    def test_firing_alert_count_property(self) -> None:
        """firing_alert_count returns count of firing alerts."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(
                VmalertAlertSignal(
                    alertname="Firing1",
                    state=AlertState.FIRING,
                    severity="critical",
                ),
                VmalertAlertSignal(
                    alertname="Firing2",
                    state=AlertState.FIRING,
                ),
                VmalertAlertSignal(
                    alertname="Pending1",
                    state=AlertState.PENDING,
                ),
            ),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        assert artifact.firing_alert_count == 2

    def test_pending_alert_count_property(self) -> None:
        """pending_alert_count returns count of pending alerts."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(
                VmalertAlertSignal(
                    alertname="Firing1",
                    state=AlertState.FIRING,
                ),
                VmalertAlertSignal(
                    alertname="Pending1",
                    state=AlertState.PENDING,
                ),
                VmalertAlertSignal(
                    alertname="Pending2",
                    state=AlertState.PENDING,
                ),
            ),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        assert artifact.pending_alert_count == 2

    def test_critical_firing_count_property(self) -> None:
        """critical_firing_count returns count of critical firing alerts."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(
                VmalertAlertSignal(
                    alertname="Critical",
                    state=AlertState.FIRING,
                    severity="critical",
                ),
                VmalertAlertSignal(
                    alertname="Warning",
                    state=AlertState.FIRING,
                    severity="warning",
                ),
                VmalertAlertSignal(
                    alertname="CriticalPending",
                    state=AlertState.PENDING,
                    severity="critical",
                ),
            ),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        assert artifact.critical_firing_count == 1

    def test_firing_alerts_property(self) -> None:
        """firing_alerts returns only firing alerts."""
        firing = VmalertAlertSignal(alertname="Firing", state=AlertState.FIRING)
        pending = VmalertAlertSignal(alertname="Pending", state=AlertState.PENDING)

        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(firing, pending),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        assert len(artifact.firing_alerts) == 1
        assert artifact.firing_alerts[0].alertname == "Firing"

    def test_pending_alerts_property(self) -> None:
        """pending_alerts returns only pending alerts."""
        firing = VmalertAlertSignal(alertname="Firing", state=AlertState.FIRING)
        pending = VmalertAlertSignal(alertname="Pending", state=AlertState.PENDING)

        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(firing, pending),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        assert len(artifact.pending_alerts) == 1
        assert artifact.pending_alerts[0].alertname == "Pending"

    def test_critical_firing_alerts_property(self) -> None:
        """critical_firing_alerts returns only critical firing alerts."""
        critical = VmalertAlertSignal(
            alertname="Critical",
            state=AlertState.FIRING,
            severity="critical",
        )
        warning = VmalertAlertSignal(
            alertname="Warning",
            state=AlertState.FIRING,
            severity="warning",
        )

        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(critical, warning),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        assert len(artifact.critical_firing_alerts) == 1
        assert artifact.critical_firing_alerts[0].alertname == "Critical"

    def test_to_dict_roundtrip(self) -> None:
        """VmalertRuleStateArtifact survives to_dict/from_dict roundtrip."""
        original = VmalertRuleStateArtifact(
            source_count=2,
            fetched_source_count=1,
            failed_source_count=1,
            alerts=(
                VmalertAlertSignal(
                    alertname="Test",
                    state=AlertState.FIRING,
                    severity="critical",
                ),
            ),
            rule_groups=(
                VmalertRuleGroup(
                    name="test-group",
                    rule_count=5,
                    firing_alert_count=1,
                ),
            ),
            fetch_errors=(
                {"source_endpoint": "http://failed:8080", "status": "fetch_error", "error": "Failed"},
            ),
            captured_at="2024-01-01T00:00:00Z",
        )

        data = original.to_dict()
        restored = VmalertRuleStateArtifact.from_dict(data)

        assert restored.source_count == original.source_count
        assert restored.fetched_source_count == original.fetched_source_count
        assert restored.failed_source_count == original.failed_source_count
        assert len(restored.alerts) == len(original.alerts)
        assert len(restored.rule_groups) == len(original.rule_groups)
        assert len(restored.fetch_errors) == len(original.fetch_errors)

    def test_from_dict_handles_missing_fields(self) -> None:
        """from_dict handles missing fields gracefully."""
        data: dict[str, Any] = {}
        artifact = VmalertRuleStateArtifact.from_dict(data)

        assert artifact.source_count == 0
        assert artifact.fetched_source_count == 0
        assert artifact.failed_source_count == 0
        assert artifact.alerts == ()
        assert artifact.rule_groups == ()
        assert artifact.fetch_errors == ()


# --- FetchError Tests ---


class TestFetchError:
    """Tests for FetchError model."""

    def test_to_dict(self) -> None:
        """FetchError.to_dict returns expected structure."""
        error = FetchError(
            source_endpoint="http://test:8080",
            source_id="test-id",
            status="fetch_error",
            error="Connection refused",
        )

        data = error.to_dict()

        assert data["source_endpoint"] == "http://test:8080"
        assert data["source_id"] == "test-id"
        assert data["status"] == "fetch_error"
        assert data["error"] == "Connection refused"


# --- build_rule_state_from_fetch_results Tests ---


class TestBuildRuleStateFromFetchResults:
    """Tests for build_rule_state_from_fetch_results()."""

    def test_sets_non_empty_captured_at(self, valid_fetch_result: VmalertFetchResult) -> None:
        """Result has non-empty captured_at from first fetch result."""
        artifact = build_rule_state_from_fetch_results((valid_fetch_result,))

        assert artifact.captured_at is not None
        assert artifact.captured_at != ""
        assert artifact.captured_at == valid_fetch_result.captured_at

    def test_successful_result_normalizes_alerts(
        self, valid_fetch_result: VmalertFetchResult
    ) -> None:
        """Successful fetch results have normalized alerts."""
        artifact = build_rule_state_from_fetch_results((valid_fetch_result,))

        assert len(artifact.alerts) >= 1
        assert artifact.fetched_source_count == 1
        assert artifact.failed_source_count == 0

    def test_failed_result_increments_failed_source_count(
        self, failed_fetch_result: VmalertFetchResult
    ) -> None:
        """Failed fetch results increment failed_source_count."""
        artifact = build_rule_state_from_fetch_results((failed_fetch_result,))

        assert artifact.failed_source_count == 1
        assert artifact.fetched_source_count == 0
        assert len(artifact.fetch_errors) == 1

    def test_failed_result_records_fetch_errors(
        self, failed_fetch_result: VmalertFetchResult
    ) -> None:
        """Failed results record sanitized error."""
        artifact = build_rule_state_from_fetch_results((failed_fetch_result,))

        assert len(artifact.fetch_errors) == 1
        error = artifact.fetch_errors[0]
        assert error["source_endpoint"] == failed_fetch_result.source_endpoint
        assert error["status"] == failed_fetch_result.status.value

    def test_empty_fetch_results_returns_valid_artifact(self) -> None:
        """Empty fetch results returns artifact with current timestamp."""
        artifact = build_rule_state_from_fetch_results(())

        assert artifact.source_count == 0
        assert artifact.fetched_source_count == 0
        assert artifact.failed_source_count == 0
        assert artifact.captured_at is not None

    def test_mixed_success_and_failure(
        self,
        valid_fetch_result: VmalertFetchResult,
        failed_fetch_result: VmalertFetchResult,
    ) -> None:
        """Mixed results correctly count successes and failures."""
        artifact = build_rule_state_from_fetch_results(
            (valid_fetch_result, failed_fetch_result)
        )

        assert artifact.source_count == 2
        assert artifact.fetched_source_count == 1
        assert artifact.failed_source_count == 1

    def test_rules_response_includes_rule_groups(
        self, rules_fetch_result: VmalertFetchResult
    ) -> None:
        """Rules response results in rule_groups in artifact."""
        artifact = build_rule_state_from_fetch_results((rules_fetch_result,))

        assert len(artifact.rule_groups) >= 1


# --- write_vmalert_rule_state Tests ---


class TestWriteVmalertRuleState:
    """Tests for write_vmalert_rule_state()."""

    def test_writes_with_correct_filename(self, tmp_path: Path) -> None:
        """Writes artifact with <run_id>-vmalert-rule-state.json name."""
        artifact = VmalertRuleStateArtifact(
            source_count=0,
            fetched_source_count=0,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        path = write_vmalert_rule_state(tmp_path, artifact, "run-123")

        assert path.name == "run-123-vmalert-rule-state.json"
        assert path.exists()

    def test_raises_file_exists_error_on_retry(self, tmp_path: Path) -> None:
        """Raises FileExistsError if artifact already exists (immutability)."""
        artifact = VmalertRuleStateArtifact(
            source_count=0,
            fetched_source_count=0,
            failed_source_count=0,
            alerts=(),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        # First write succeeds
        write_vmalert_rule_state(tmp_path, artifact, "run-123")

        # Second write raises FileExistsError
        with pytest.raises(FileExistsError):
            write_vmalert_rule_state(tmp_path, artifact, "run-123")

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        """Writes valid JSON that can be parsed."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(
                VmalertAlertSignal(
                    alertname="Test",
                    state=AlertState.FIRING,
                ),
            ),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        path = write_vmalert_rule_state(tmp_path, artifact, "run-456")

        # Should be valid JSON
        data = json.loads(path.read_text())
        assert data["source_count"] == 1


# --- read_vmalert_rule_state Tests ---


class TestReadVmalertRuleState:
    """Tests for read_vmalert_rule_state()."""

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Returns None if file does not exist."""
        result = read_vmalert_rule_state(tmp_path / "missing.json")
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path) -> None:
        """Returns None for invalid JSON file."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json{")

        result = read_vmalert_rule_state(invalid_file)
        assert result is None

    def test_reads_valid_artifact(self, tmp_path: Path) -> None:
        """Reads and parses valid artifact."""
        artifact = VmalertRuleStateArtifact(
            source_count=1,
            fetched_source_count=1,
            failed_source_count=0,
            alerts=(
                VmalertAlertSignal(
                    alertname="Test",
                    state=AlertState.FIRING,
                ),
            ),
            rule_groups=(),
            fetch_errors=(),
            captured_at="2024-01-01T00:00:00Z",
        )

        # Write directly to test reading
        path = tmp_path / "test-vmalert-rule-state.json"
        path.write_text(json.dumps(artifact.to_dict()))

        result = read_vmalert_rule_state(path)
        assert result is not None
        assert result.source_count == 1
        assert len(result.alerts) == 1


# --- vmalert_rule_state_exists Tests ---


class TestVmalertRuleStateExists:
    """Tests for vmalert_rule_state_exists()."""

    def test_returns_true_for_existing_file(self, tmp_path: Path) -> None:
        """Returns True if artifact file exists."""
        # Create the file
        path = tmp_path / "run-123-vmalert-rule-state.json"
        path.write_text("{}")

        assert vmalert_rule_state_exists(tmp_path, "run-123") is True

    def test_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        """Returns False if artifact file does not exist."""
        assert vmalert_rule_state_exists(tmp_path, "nonexistent") is False


# --- collect_vmalert_rule_state Tests ---


class TestCollectVmalertRuleState:
    """Tests for collect_vmalert_rule_state()."""

    def test_skips_non_eligible_sources(self) -> None:
        """Skips sources not in eligible states."""
        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            VmalertSource,
            VmalertSourceInventory,
            VmalertSourceState,
        )

        inventory = VmalertSourceInventory()
        # Add a DEGRADED source (not eligible)
        inventory.add_source(
            VmalertSource(
                source_id="degraded",
                endpoint="http://degraded:8080",
                state=VmalertSourceState.DEGRADED,
            )
        )
        # Add a MISSING source (not eligible)
        inventory.add_source(
            VmalertSource(
                source_id="missing",
                endpoint="http://missing:8080",
                state=VmalertSourceState.MISSING,
            )
        )

        artifact = collect_vmalert_rule_state(inventory)

        # Should return empty artifact (no eligible sources)
        assert artifact.source_count == 0
        assert artifact.fetched_source_count == 0

    def test_returns_empty_artifact_for_empty_inventory(self) -> None:
        """Returns empty artifact for empty inventory."""
        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            VmalertSourceInventory,
        )

        inventory = VmalertSourceInventory()
        artifact = collect_vmalert_rule_state(inventory)

        assert artifact.source_count == 0

    def test_eligible_source_collection(
        self,
        valid_fetch_result: VmalertFetchResult,
    ) -> None:
        """Collects from eligible sources with fallback logic."""
        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            VmalertSource,
            VmalertSourceInventory,
            VmalertSourceState,
        )

        inventory = VmalertSourceInventory()
        inventory.add_source(
            VmalertSource(
                source_id="test",
                endpoint="http://test:8080",
                state=VmalertSourceState.DISCOVERED,
            )
        )

        # Mock fetch functions - alerts succeed
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_client.fetch_vmalert_alerts",
            return_value=valid_fetch_result,
        ):
            artifact = collect_vmalert_rule_state(inventory)

        # Should have collected from the source
        assert artifact.fetched_source_count == 1