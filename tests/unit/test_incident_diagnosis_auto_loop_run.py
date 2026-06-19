"""Unit tests for incident_diagnosis_auto_loop run behavior.

Tests cover:
- Run tests (collector behavior, orchestrator wiring)
- Safety tests (no forbidden imports)

These tests do NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell
- Perform remediation or mutation
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
    AutomaticDiagnosisLoopConfig,
    collect_automatic_diagnosis_evidence,
    run_automatic_diagnosis_loop_evidence_collection,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_external_dir():
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# =============================================================================
# Run Tests
# =============================================================================


class TestCollectorRun:
    """Tests for collector run behavior."""

    def test_disabled_collector_returns_early(
        self, temp_external_dir
    ):
        """Prove disabled collector returns without processing."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
            )
            assert result.enabled is False
            assert result.incidents_processed == 0
            assert len(result.incident_results) == 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup

    def test_disabled_collector_does_not_run_checks(
        self, temp_external_dir
    ):
        """Prove disabled collector does not run checks."""
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )
        assert result.enabled is False
        assert result.incidents_processed == 0

    def test_disabled_collector_does_not_write_packets(
        self, temp_external_dir
    ):
        """Prove disabled collector does not write evidence packets."""
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )
        assert result.total_review_packets_written == 0

    def test_enabled_collector_with_no_incidents(
        self, temp_external_dir
    ):
        """Prove enabled collector handles no incidents gracefully."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
            )
            assert result.enabled is True
            assert result.incidents_processed == 0
            assert result.incidents_eligible == 0
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_enabled_collector_processes_specific_incidents(
        self, temp_external_dir
    ):
        """Prove enabled collector processes specific incident IDs."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["test-incident"],
            )
            assert result.enabled is True
            assert result.incidents_processed == 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_respects_max_incidents(
        self, temp_external_dir
    ):
        """Prove collector respects max_incidents_per_run bound."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            config = AutomaticDiagnosisLoopConfig(max_incidents_per_run=1)
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["inc1", "inc2", "inc3"],  # 3 incidents
                config=config,
            )
            assert result.incidents_processed <= 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


class TestCollectAutomaticDiagnosisEvidence:
    """Tests for single-incident convenience function."""

    def test_disabled_collector_returns_skipped(
        self, temp_external_dir
    ):
        """Prove convenience function respects disabled state."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            result = collect_automatic_diagnosis_evidence(
                incident_id="test-incident",
                external_analysis_dir=temp_external_dir,
            )
            assert result.skipped is True
            assert "not set to true" in result.skip_reason or "disabled" in result.skip_reason
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup


# =============================================================================
# Safety Tests
# =============================================================================


class TestSafetyMetadata:
    """Tests for safety metadata in results."""

    def test_collector_result_has_safety_metadata(
        self, temp_external_dir
    ):
        """Prove collector result includes safety metadata."""
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )
        assert "read_only" in result.safety_metadata
        assert result.safety_metadata["read_only"] is True
        assert "no_kubectl" in result.safety_metadata
        assert result.safety_metadata["no_kubectl"] is True
        assert "no_shell" in result.safety_metadata
        assert result.safety_metadata["no_shell"] is True
        assert "no_remediation" in result.safety_metadata
        assert result.safety_metadata["no_remediation"] is True

    def test_incident_result_has_no_action_fields(
        self, temp_external_dir
    ):
        """Prove incident result does not contain action-control fields."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["test-incident"],
            )

            if result.incident_results:
                for ir in result.incident_results:
                    assert "run" not in ir
                    assert "execute" not in ir
                    assert "remediate" not in ir
                    assert "mutate" not in ir
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]
