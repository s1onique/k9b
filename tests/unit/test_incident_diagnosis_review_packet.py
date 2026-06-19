"""Unit tests for incident_diagnosis_review_packet module - schema and writing.

Tests cover:
- Packet writing with bounded metadata
- Schema version and artifact type
- Artifact references (filenames only)
- Safety metadata

These tests do NOT:
- Include raw artifact contents
- Include absolute paths
- Include forbidden action-control fields
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    REVIEW_PACKET_ARTIFACT_TYPE,
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SUFFIX,
    write_diagnosis_review_packet,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_external_dir():
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_case_file():
    """Provide a sample case file with suggested checks."""
    return {
        "schema_version": "1.0",
        "generated_at": "2026-06-19T08:00:00+00:00",
        "incident": {
            "incident_id": "test-incident-123",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
        },
        "suggested_checks": [
            {"check_id": "pod_logs", "title": "Check pod logs", "read_only": True},
            {"check_id": "pod_events", "title": "Check pod events", "read_only": True},
            {"check_id": "pod_describe", "title": "Describe pod", "read_only": True},
        ],
    }


@pytest.fixture
def sample_orchestrator_result():
    """Provide a sample orchestrator result."""
    return {
        "decision": "run_allowed_read_only_checks",
        "runner_result": {
            "checks_requested": 3,
            "checks_run": 3,
            "checks_skipped": 0,
            "checks_rejected": 0,
        },
        "artifact": {"artifact_path": "/some/path/run123-read-only-check-results.json", "written": True},
        "loop_pass_artifact": {"artifact_path": "/some/path/run123-diagnosis-loop-pass.json", "written": True},
    }


# =============================================================================
# Schema and Type Tests
# =============================================================================


class TestReviewPacketSchema:
    """Tests for review packet schema and type."""

    def test_schema_version_is_correct(self):
        """Prove schema version is correct."""
        assert REVIEW_PACKET_SCHEMA_VERSION == "1.0"

    def test_artifact_type_is_correct(self):
        """Prove artifact type is correct."""
        assert REVIEW_PACKET_ARTIFACT_TYPE == "diagnosis-loop-review-packet"

    def test_suffix_is_correct(self):
        """Prove suffix is correct."""
        assert REVIEW_PACKET_SUFFIX == "diagnosis-review-packet.json"


# =============================================================================
# Packet Writing Tests
# =============================================================================


class TestWriteDiagnosisReviewPacket:
    """Tests for write_diagnosis_review_packet function."""

    def test_packet_has_schema_version(self, temp_external_dir, sample_case_file, sample_orchestrator_result):
        """Prove packet has correct schema version."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3, checks_run=3, checks_skipped=0, checks_rejected=0,
            eligible=True, eligibility_reason="active_incident",
            case_file=sample_case_file, orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )
        packet = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
        assert packet["schema_version"] == "1.0"

    def test_packet_has_artifact_type(self, temp_external_dir, sample_case_file, sample_orchestrator_result):
        """Prove packet has correct artifact type."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3, checks_run=3, checks_skipped=0, checks_rejected=0,
            eligible=True, eligibility_reason="active_incident",
            case_file=sample_case_file, orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )
        packet = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
        assert packet["artifact_type"] == "diagnosis-loop-review-packet"

    def test_packet_has_incident_id(self, temp_external_dir, sample_case_file, sample_orchestrator_result):
        """Prove packet has incident_id."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident-456",
            collector_run_id="collector-1",
            run_id="auto-test-incident-456-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3, checks_run=3, checks_skipped=0, checks_rejected=0,
            eligible=True, eligibility_reason="active_incident",
            case_file=sample_case_file, orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )
        packet = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
        assert packet["incident_id"] == "test-incident-456"

    def test_packet_has_run_id(self, temp_external_dir, sample_case_file, sample_orchestrator_result):
        """Prove packet has run_id."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3, checks_run=3, checks_skipped=0, checks_rejected=0,
            eligible=True, eligibility_reason="active_incident",
            case_file=sample_case_file, orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )
        packet = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
        assert packet["run_id"] == "auto-test-incident-20260619-080000-abc123"

    def test_packet_has_automatic_true(self, temp_external_dir, sample_case_file, sample_orchestrator_result):
        """Prove packet has automatic=true."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3, checks_run=3, checks_skipped=0, checks_rejected=0,
            eligible=True, eligibility_reason="active_incident",
            case_file=sample_case_file, orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )
        packet = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
        assert packet["automatic"] is True

    def test_packet_has_read_only_true(self, temp_external_dir, sample_case_file, sample_orchestrator_result):
        """Prove packet has read_only=True."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3, checks_run=3, checks_skipped=0, checks_rejected=0,
            eligible=True, eligibility_reason="active_incident",
            case_file=sample_case_file, orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )
        packet = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
        assert packet["read_only"] is True

    def test_packet_has_allowed_actions_empty(self, temp_external_dir, sample_case_file, sample_orchestrator_result):
        """Prove packet has allowed_actions=[]."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3, checks_run=3, checks_skipped=0, checks_rejected=0,
            eligible=True, eligibility_reason="active_incident",
            case_file=sample_case_file, orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )
        packet = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
        assert packet["allowed_actions"] == []
