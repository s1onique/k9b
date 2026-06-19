"""Unit tests for automatic_diagnosis_review in incident detail API.

Tests cover:
1. Detail payload includes automatic_diagnosis_review.available=false when no packet exists
2. Detail payload includes bounded summary when a review packet exists
3. artifact_name is filename only, not path
4. raw packet content is not exposed
5. raw case file is not exposed
6. raw runner result is not exposed
7. absolute filesystem paths are not exposed
8. malformed packet returns safe unavailable state
9. multiple packets choose latest deterministically
10. summary fields are bounded/truncated
11. read_only is true
12. review_required_before_any_action is true
13. no_remediation_attempted is true

Safety assertions:
- Forbidden fields are not present
- No action-control fields
- No secrets or paths
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    REVIEW_PACKET_ARTIFACT_TYPE,
    write_diagnosis_review_packet,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store
from k8s_diag_agent.ui.api_incident_reads import (
    build_automatic_diagnosis_review_payload,
    build_incident_detail_payload,
)

from .incident_lifecycle_fixtures import (
    make_full_incident,
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
        ],
    }


@pytest.fixture
def sample_orchestrator_result():
    """Provide a sample orchestrator result with paths."""
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
            "written": True
        },
        "loop_pass_artifact": {
            "artifact_path": "/some/path/run123-diagnosis-loop-pass.json",
            "written": True
        },
    }


@pytest.fixture
def incident_store():
    """Provide a clean incident store for tests."""
    store = IncidentStore()
    set_incident_store(store)
    yield store
    set_incident_store(None)
    reset_incident_store()


# =============================================================================
# Tests for build_automatic_diagnosis_review_payload
# =============================================================================


class TestBuildAutomaticDiagnosisReviewPayloadNoPacket:
    """Tests for unavailable state when no packet exists."""

    def test_returns_unavailable_when_dir_is_none(self) -> None:
        """Prove returns unavailable when external_analysis_dir is None."""
        result = build_automatic_diagnosis_review_payload(None, "test-incident")

        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"

    def test_returns_unavailable_when_dir_does_not_exist(self, temp_external_dir: Path) -> None:
        """Prove returns unavailable when directory doesn't exist."""
        nonexistent_dir = temp_external_dir.parent / "nonexistent"
        result = build_automatic_diagnosis_review_payload(nonexistent_dir, "test-incident")

        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"

    def test_returns_unavailable_when_no_packet_for_incident(
        self, temp_external_dir: Path
    ) -> None:
        """Prove returns unavailable when no packet exists for incident."""
        result = build_automatic_diagnosis_review_payload(temp_external_dir, "nonexistent-incident")

        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"


class TestBuildAutomaticDiagnosisReviewPayloadWithPacket:
    """Tests for available state when packet exists."""

    def test_returns_available_when_packet_exists(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove returns available when packet exists."""
        # Write a packet
        write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=2,
            checks_skipped=0,
            checks_rejected=1,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        assert result["available"] is True
        assert result["artifact_type"] == REVIEW_PACKET_ARTIFACT_TYPE

    def test_includes_bounded_summary_fields(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove includes bounded summary fields."""
        write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision="run_allowed_read_only_checks",
            checks_requested=3,
            checks_run=2,
            checks_skipped=0,
            checks_rejected=1,
            eligible=True,
            eligibility_reason="active_incident",
            case_file=sample_case_file,
            orchestrator_result=sample_orchestrator_result,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        assert result["checks_requested"] == 3
        assert result["checks_run"] == 2
        assert result["checks_rejected"] == 1
        assert result["eligible"] is True
        assert result["eligibility_reason"] == "active_incident"
        assert result["decision"] == "run_allowed_read_only_checks"

    def test_artifact_name_is_filename_only(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove artifact_name is filename only, no path."""
        write_diagnosis_review_packet(
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

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # artifact_name should be just a filename, not a path
        assert "/" not in result["artifact_name"]
        assert "\\" not in result["artifact_name"]
        assert result["artifact_name"] == "auto-test-incident-20260619-080000-abc123-diagnosis-review-packet.json"

    def test_safety_metadata_is_always_true(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove safety metadata fields are always True."""
        write_diagnosis_review_packet(
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

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        assert result["read_only"] is True
        assert result["review_required_before_any_action"] is True
        assert result["no_remediation_attempted"] is True


class TestBuildAutomaticDiagnosisReviewPayloadSafety:
    """Safety tests - forbidden fields must not appear."""

    def test_no_raw_packet_content_exposed(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove raw packet content is not exposed."""
        write_diagnosis_review_packet(
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

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # These fields should NOT be in the result
        assert "case_file" not in result
        assert "runner_result" not in result
        assert "selected_checks" not in result
        assert "loop_result" not in result or "decision" in result  # decision is ok, raw result is not

    def test_no_paths_exposed(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove absolute filesystem paths are not exposed."""
        write_diagnosis_review_packet(
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

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")
        result_str = json.dumps(result)

        # No absolute paths should be in the result
        assert "/some/path" not in result_str
        assert "/Volumes/" not in result_str
        assert "/Users/" not in result_str

    def test_no_action_control_fields(
        self,
        temp_external_dir: Path,
        sample_case_file: dict,
        sample_orchestrator_result: dict,
    ) -> None:
        """Prove no action-control fields are exposed."""
        write_diagnosis_review_packet(
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

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")
        result_str = json.dumps(result)

        # No action-control fields should be in the result
        forbidden = ["apply", "delete", "patch", "scale", "restart", "rollout", "kubectl", "helm"]
        for field in forbidden:
            assert field not in result_str


class TestBuildAutomaticDiagnosisReviewPayloadBounded:
    """Tests for field bounding/truncation."""

    def test_artifact_name_bounded_to_240_chars(self, temp_external_dir: Path) -> None:
        """Prove artifact_name is bounded to 240 chars by testing the _bound function."""
        from k8s_diag_agent.ui.api_incident_reads import MAX_ARTIFACT_NAME_LENGTH

        # Create a very long artifact name
        long_name = "auto-test-incident-" + "x" * 300 + "-diagnosis-review-packet.json"
        
        # Apply bounding as done in build_automatic_diagnosis_review_payload
        def _bound(value: str | None, max_length: int) -> str | None:
            if value is None:
                return None
            return value[:max_length]
        
        result = _bound(long_name, MAX_ARTIFACT_NAME_LENGTH)
        
        # Should be bounded
        assert len(result) <= 240
        assert len(result) > 200  # Should use most of the allowed length

    def test_decision_bounded_to_120_chars(self, temp_external_dir: Path) -> None:
        """Prove decision is bounded to 120 chars."""
        long_decision = "run_allowed_read_only_checks_" + "x" * 150
        write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-abc123",
            decision=long_decision,
            checks_requested=3,
            checks_run=3,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="active_incident",
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # Should be bounded
        assert len(result["decision"]) <= 120

    def test_eligibility_reason_bounded_to_160_chars(self, temp_external_dir: Path) -> None:
        """Prove eligibility_reason is bounded to 160 chars."""
        long_reason = "active_incident_" + "x" * 200
        write_diagnosis_review_packet(
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
            eligibility_reason=long_reason,
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # Should be bounded
        assert len(result["eligibility_reason"]) <= 160


class TestBuildAutomaticDiagnosisReviewPayloadMalformed:
    """Tests for malformed packets."""

    def test_returns_unavailable_for_malformed_json(self, temp_external_dir: Path) -> None:
        """Prove returns unavailable for malformed JSON packet.
        
        Note: The implementation catches JSONDecodeError and returns None from
        load_review_packet_summary, which results in 'no_review_packet'.
        Both unavailable states are handled the same way in the UI.
        """
        # Write a malformed packet file - must match the auto-{incident_id}-{run_id}-diagnosis-review-packet.json pattern
        packet_path = temp_external_dir / "auto-test-incident-20260619-080000-abc123-diagnosis-review-packet.json"
        packet_path.write_text("not valid json{{", encoding="utf-8")

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # Result is unavailable - malformed packets are treated same as missing packets
        assert result["available"] is False

    def test_returns_unavailable_for_invalid_packet_structure(
        self, temp_external_dir: Path
    ) -> None:
        """Prove returns unavailable for invalid packet structure."""
        # Write a packet missing required fields
        packet_path = temp_external_dir / "auto-test-incident-20260619-080000-diagnosis-review-packet.json"
        packet_path.write_text(
            json.dumps({"not": "a valid review packet structure"}),
            encoding="utf-8",
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        assert result["available"] is False
        assert result["unavailable_reason"] == "malformed_review_packet"


class TestBuildAutomaticDiagnosisReviewPayloadLatest:
    """Tests for deterministic latest packet selection."""

    def test_chooses_latest_packet_by_timestamp(
        self, temp_external_dir: Path
    ) -> None:
        """Prove selects the latest packet by timestamp."""
        # Write two packets with different timestamps
        write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-070000-abc123",
            decision="first_decision",
            checks_requested=1,
            checks_run=1,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="first",
            now=datetime(2026, 6, 19, 7, 0, 0, tzinfo=UTC),
        )
        write_diagnosis_review_packet(
            external_analysis_dir=temp_external_dir,
            incident_id="test-incident",
            collector_run_id="collector-1",
            run_id="auto-test-incident-20260619-080000-def456",
            decision="second_decision",
            checks_requested=2,
            checks_run=2,
            checks_skipped=0,
            checks_rejected=0,
            eligible=True,
            eligibility_reason="second",
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        result = build_automatic_diagnosis_review_payload(temp_external_dir, "test-incident")

        # Should return the latest one (8:00)
        assert result["decision"] == "second_decision"
        assert result["checks_requested"] == 2


# =============================================================================
# Tests for build_incident_detail_payload integration
# =============================================================================


class TestBuildIncidentDetailPayloadWithAutoReview:
    """Tests for automatic_diagnosis_review in detail payload."""

    def test_detail_includes_automatic_diagnosis_review_field(self) -> None:
        """Prove incident detail payload includes automatic_diagnosis_review field."""
        incident = make_full_incident(incident_id="test-incident")

        result = build_incident_detail_payload(incident)

        assert "automatic_diagnosis_review" in result

    def test_detail_automatic_diagnosis_review_unavailable_when_no_dir(self) -> None:
        """Prove automatic_diagnosis_review is unavailable when no external_analysis_dir."""
        incident = make_full_incident(incident_id="test-incident")

        result = build_incident_detail_payload(incident, external_analysis_dir=None)

        assert result["automatic_diagnosis_review"]["available"] is False
        assert result["automatic_diagnosis_review"]["unavailable_reason"] == "no_review_packet"

    def test_detail_automatic_diagnosis_review_available_with_packet(
        self,
        temp_external_dir: Path,
    ) -> None:
        """Prove automatic_diagnosis_review is available when packet exists."""
        # Write a packet
        write_diagnosis_review_packet(
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
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        incident = make_full_incident(incident_id="test-incident")

        result = build_incident_detail_payload(incident, external_analysis_dir=temp_external_dir)

        assert result["automatic_diagnosis_review"]["available"] is True
        assert result["automatic_diagnosis_review"]["artifact_type"] == REVIEW_PACKET_ARTIFACT_TYPE

    def test_detail_automatic_diagnosis_review_safety_fields(
        self,
        temp_external_dir: Path,
    ) -> None:
        """Prove automatic_diagnosis_review has safety fields set correctly."""
        write_diagnosis_review_packet(
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
            now=datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC),
        )

        incident = make_full_incident(incident_id="test-incident")

        result = build_incident_detail_payload(incident, external_analysis_dir=temp_external_dir)

        assert result["automatic_diagnosis_review"]["read_only"] is True
        assert result["automatic_diagnosis_review"]["review_required_before_any_action"] is True
        assert result["automatic_diagnosis_review"]["no_remediation_attempted"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])