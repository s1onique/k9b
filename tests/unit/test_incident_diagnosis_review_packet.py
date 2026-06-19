"""Unit tests for incident_diagnosis_review_packet module.

Tests cover:
- Packet writing with bounded metadata
- Schema version and artifact type
- Selected checks extraction
- Artifact references (filenames only)
- Safety metadata
- Lookup functions

These tests do NOT:
- Include raw artifact contents
- Include absolute paths
- Include forbidden action-control fields
- Include secrets or stack traces
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
    AutomaticDiagnosisLoopConfig,
)
from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    REVIEW_PACKET_ARTIFACT_TYPE,
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SUFFIX,
    find_latest_review_packet,
    load_review_packet_summary,
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
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
            },
            {
                "check_id": "pod_events",
                "title": "Check pod events",
                "read_only": True,
            },
            {
                "check_id": "pod_describe",
                "title": "Describe pod",
                "read_only": True,
            },
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
        "artifact": {
            "artifact_path": "/some/path/run123-read-only-check-results.json",
            "written": True,
        },
        "loop_pass_artifact": {
            "artifact_path": "/some/path/run123-diagnosis-loop-pass.json",
            "written": True,
        },
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

    def test_packet_has_schema_version(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has correct schema version."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        # Read the written packet
        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert packet["schema_version"] == "1.0"

    def test_packet_has_artifact_type(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has correct artifact type."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert packet["artifact_type"] == "diagnosis-loop-review-packet"

    def test_packet_has_incident_id(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has incident_id."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident-456",
            collector_run_id="collector-1",
            run_id="auto-test-incident-456-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert packet["incident_id"] == "test-incident-456"

    def test_packet_has_run_id(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has run_id."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert packet["run_id"] == "auto-test-incident-20260619-080000-abc123"

    def test_packet_has_automatic_true(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has automatic=true."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert packet["automatic"] is True

    def test_packet_has_read_only_true(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has read_only=True."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert packet["read_only"] is True

    def test_packet_has_allowed_actions_empty(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has allowed_actions=[]."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert packet["allowed_actions"] == []

    def test_packet_has_loop_result(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has loop_result with counts."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=5,
            checks_run=3,
            checks_skipped=1,
            checks_rejected=1,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert "loop_result" in packet
        assert packet["loop_result"]["decision"] == "run_allowed_read_only_checks"
        assert packet["loop_result"]["checks_requested"] == 5
        assert packet["loop_result"]["checks_run"] == 3
        assert packet["loop_result"]["checks_skipped"] == 1
        assert packet["loop_result"]["checks_rejected"] == 1

    def test_packet_has_budget(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has budget metadata."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            config=AutomaticDiagnosisLoopConfig(),
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert "budget" in packet
        assert packet["budget"]["max_passes_per_incident"] == 1
        assert packet["budget"]["max_checks_per_pass"] == 5
        assert packet["budget"]["pass_index"] == 1

    def test_packet_has_safety_metadata(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has comprehensive safety metadata."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert "safety_metadata" in packet
        assert packet["safety_metadata"]["read_only"] is True
        assert packet["safety_metadata"]["allowed_actions"] == []
        assert packet["safety_metadata"]["no_kubernetes_mutation"] is True
        assert packet["safety_metadata"]["no_shell"] is True
        assert packet["safety_metadata"]["no_subprocess"] is True
        assert packet["safety_metadata"]["no_kubectl"] is True
        assert packet["safety_metadata"]["no_remediation"] is True

    def test_packet_has_review_guidance(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet has review guidance."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert "review_guidance" in packet
        assert packet["review_guidance"]["intended_reviewer"] == "operator_or_chatgpt"
        assert packet["review_guidance"]["review_required_before_any_action"] is True

    def test_packet_references_artifact_names_only(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet contains only artifact filenames, not full paths."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert "artifacts" in packet

        # Check read_only_check_results - should have name only
        assert packet["artifacts"]["read_only_check_results"]["written"] is True
        name = packet["artifacts"]["read_only_check_results"]["name"]
        assert name is not None
        assert "/" not in name  # Should not contain path separators
        assert "abc123" not in name  # Should not contain run_id in unexpected way

        # Check diagnosis_loop_pass - should have name only
        assert packet["artifacts"]["diagnosis_loop_pass"]["written"] is True
        name = packet["artifacts"]["diagnosis_loop_pass"]["name"]
        assert name is not None
        assert "/" not in name

    def test_packet_no_absolute_paths(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet does not contain absolute filesystem paths."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet_str = packet_path.read_text(encoding="utf-8")

        # Should not contain absolute paths
        assert "/some/path" not in packet_str
        assert "/tmp/" not in packet_str or "temp" not in packet_str.lower()

    def test_packet_no_forbidden_action_fields(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet does not contain forbidden action-control fields."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet_str = packet_path.read_text(encoding="utf-8")

        # Should not contain forbidden fields as keys
        forbidden_fields = ["run", "execute", "remediate", "mutate", "kubectl", "helm"]
        for field in forbidden_fields:
            # Check for field as key (with quotes)
            assert f'"{field}"' not in packet_str

    def test_packet_json_serializable(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet is valid JSON and can be parsed."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet_str = packet_path.read_text(encoding="utf-8")

        # Should not raise
        packet = json.loads(packet_str)
        assert isinstance(packet, dict)

    def test_packet_return_metadata(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove function returns correct metadata."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        assert result["written"] is True
        assert result["run_id"] == "auto-test-incident-20260619-080000-abc123"
        assert result["incident_id"] == "test-incident"
        assert result["schema_version"] == "1.0"
        assert result["artifact_type"] == "diagnosis-loop-review-packet"
        assert result["name"] == "auto-test-incident-20260619-080000-abc123-diagnosis-review-packet.json"


class TestSelectedChecksExtraction:
    """Tests for selected checks extraction from case file."""

    def test_extracts_bounded_checks(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove packet contains bounded selected checks."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert "selected_checks" in packet
        checks = packet["selected_checks"]
        assert isinstance(checks, list)
        assert len(checks) <= 5  # Bounded

    def test_checks_have_required_fields(
        self, temp_external_dir, sample_case_file, sample_orchestrator_result
    ):
        """Prove selected checks have required fields."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        for check in packet["selected_checks"]:
            assert "check_id" in check
            assert "title" in check
            assert "source" in check
            assert check["source"] == "automatic_suggested_check"

    def test_handles_empty_case_file(self, temp_external_dir):
        """Prove function handles empty case file gracefully."""
        result = write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=0,
            checks_run=0,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=None,
            orchestrator_result=None,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        packet_path = Path(result["artifact_path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))

        assert "selected_checks" in packet
        assert packet["selected_checks"] == []


# =============================================================================
# Lookup Tests
# =============================================================================


class TestFindLatestReviewPacket:
    """Tests for find_latest_review_packet function."""

    def test_returns_none_for_nonexistent_dir(self, temp_external_dir):
        """Prove function returns None for nonexistent directory."""
        result = find_latest_review_packet(temp_external_dir / "nonexistent", "test-incident")
        assert result is None

    def test_returns_none_for_no_packets(self, temp_external_dir):
        """Prove function returns None when no packets exist."""
        result = find_latest_review_packet(temp_external_dir, "test-incident")
        assert result is None

    def test_finds_existing_packet(self, temp_external_dir):
        """Prove function finds existing packet for incident."""
        # Write a test packet
        run_id = "auto-test-incident-20260619-080000-abc123"
        packet_path = temp_external_dir / f"{run_id}-diagnosis-review-packet.json"
        packet_path.write_text('{"schema_version": "1.0"}', encoding="utf-8")

        result = find_latest_review_packet(temp_external_dir, "test-incident")

        assert result is not None
        assert result["incident_id"] == "test-incident"
        assert result["name"] == f"{run_id}-diagnosis-review-packet.json"


class TestLoadReviewPacketSummary:
    """Tests for load_review_packet_summary function."""

    def test_returns_none_for_no_packets(self, temp_external_dir):
        """Prove function returns None when no packets exist."""
        result = load_review_packet_summary(temp_external_dir, "test-incident")
        assert result is None

    def test_loads_bounded_summary(self, temp_external_dir):
        """Prove function loads bounded summary fields."""
        # Write a test packet
        run_id = "auto-test-incident-20260619-080000-abc123"
        packet_path = temp_external_dir / f"{run_id}-diagnosis-review-packet.json"

        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "test-incident",
            "run_id": run_id,
            "collector_run_id": "collector-1",
            "generated_at": "2026-06-19T08:00:00+00:00",
            "eligibility": {
                "eligible": True,
                "reason": "active_incident",
            },
            "loop_result": {
                "decision": "run_allowed_read_only_checks",
                "checks_requested": 3,
                "checks_run": 3,
                "checks_skipped": 0,
                "checks_rejected": 0,
            },
        }
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = load_review_packet_summary(temp_external_dir, "test-incident")

        assert result is not None
        assert result["incident_id"] == "test-incident"
        assert result["run_id"] == run_id
        assert result["decision"] == "run_allowed_read_only_checks"
        assert result["checks_requested"] == 3
        assert result["checks_run"] == 3
        assert result["eligible"] is True
        assert result["eligibility_reason"] == "active_incident"

    def test_summary_does_not_include_raw_contents(self, temp_external_dir):
        """Prove summary does not include raw case file or runner results."""
        # Write a test packet with raw contents
        run_id = "auto-test-incident-20260619-080000-abc123"
        packet_path = temp_external_dir / f"{run_id}-diagnosis-review-packet.json"

        packet_data = {
            "schema_version": "1.0",
            "incident_id": "test-incident",
            "run_id": run_id,
            "collector_run_id": "collector-1",
            "generated_at": "2026-06-19T08:00:00+00:00",
            "eligibility": {
                "eligible": True,
                "reason": "active_incident",
            },
            "loop_result": {
                "decision": "run_allowed_read_only_checks",
                "checks_requested": 3,
                "checks_run": 3,
                "checks_skipped": 0,
                "checks_rejected": 0,
            },
            "raw_case_file": {"secret_data": "should_not_appear"},
            "runner_result": {"secret_result": "should_not_appear"},
        }
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = load_review_packet_summary(temp_external_dir, "test-incident")

        assert result is not None
        # Summary should only have expected fields
        assert "raw_case_file" not in result
        assert "runner_result" not in result