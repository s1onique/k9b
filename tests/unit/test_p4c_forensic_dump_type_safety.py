"""Regression tests for forensic dump functions tolerating non-Mapping inputs.

These tests verify that the forensic dump functions do not crash when receiving
malformed inputs (string, None, list, int, etc.) instead of dict/Mapping types.

Tests run with FORENSIC_DUMP_ENABLED=True to exercise the actual guarded code paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestDumpP4cOutcomeInputTypeSafety:
    """Tests for dump_p4c_outcome_input() type safety."""

    @pytest.mark.parametrize(
        "malformed_evidence",
        [None, [], "bad", 42, 3.14, True],
    )
    def test_dump_tolerates_non_mapping_evidence(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        malformed_evidence: object,
    ) -> None:
        """Regression: dump_p4c_outcome_input should not crash on non-Mapping evidence.

        This prevents "'str' object has no attribute 'get'" crash when evidence
        arrives as a string instead of dict.
        """
        # Force forensic dump mode on so we exercise the guarded code path
        monkeypatch.setenv("K9B_P4C_FORENSIC_DUMP", "1")

        from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (
            dump_p4c_outcome_input,
        )

        # Should not raise
        result = dump_p4c_outcome_input(
            artifact_dir=tmp_path,
            evidence=malformed_evidence,  # type: ignore[arg-type]
            incident_id="test-incident",
        )

        # Should return a dict (the provenance)
        assert isinstance(result, dict)
        # Fields should reflect empty mapping when input is non-Mapping
        assert result.get("fields_present") == []
        assert result.get("scheduling_evidence") is None

    def test_dump_with_valid_dict_evidence(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Verify dump works correctly with valid dict evidence."""
        monkeypatch.setenv("K9B_P4C_FORENSIC_DUMP", "1")

        from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (
            dump_p4c_outcome_input,
        )

        valid_evidence = {
            "incident_id": "test-incident",
            "pass_count": 2,
            "root_cause_summary": "Test summary",
        }

        result = dump_p4c_outcome_input(
            artifact_dir=tmp_path,
            evidence=valid_evidence,
            incident_id="test-incident",
        )

        assert isinstance(result, dict)
        assert "fields_present" in result


class TestDumpBackendIncidentDetailTypeSafety:
    """Tests for dump_backend_incident_detail_before_loop() type safety."""

    @pytest.mark.parametrize(
        "malformed_detail",
        [None, [], "bad", 42, 3.14, True],
    )
    def test_dump_tolerates_non_mapping_detail(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        malformed_detail: object,
    ) -> None:
        """Regression: dump_backend_incident_detail_before_loop should not crash.

        This prevents crashes when incident_detail arrives as non-Mapping type.
        """
        # Force forensic dump mode on so we exercise the guarded code path
        monkeypatch.setenv("K9B_P4C_FORENSIC_DUMP", "1")

        from scripts.k9b_otel_demo_lab_p4c_forensic_dump import (
            dump_backend_incident_detail_before_loop,
        )

        # Should not raise
        result = dump_backend_incident_detail_before_loop(
            artifact_dir=tmp_path,
            incident_detail=malformed_detail,  # type: ignore[arg-type]
            incident_id="test-incident",
        )

        # Should return a dict (the provenance)
        assert isinstance(result, dict)
        # Fields should reflect empty mapping when input is non-Mapping
        assert result.get("fields_present") == []

    def test_dump_with_valid_dict_detail(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Verify dump works correctly with valid dict detail."""
        monkeypatch.setenv("K9B_P4C_FORENSIC_DUMP", "1")

        from scripts.k9b_otel_demo_lab_p4c_forensic_dump import (
            dump_backend_incident_detail_before_loop,
        )

        valid_detail = {
            "automatic_diagnosis_review": {
                "run_id": "test-run-123",
            }
        }

        result = dump_backend_incident_detail_before_loop(
            artifact_dir=tmp_path,
            incident_detail=valid_detail,
            incident_id="test-incident",
        )

        assert isinstance(result, dict)
        assert "fields_present" in result


class TestDumpDiagnosisLoopPassTypeSafety:
    """Tests for dump_diagnosis_loop_pass() type safety."""

    @pytest.mark.parametrize(
        "malformed_response",
        [None, [], "bad", 42, 3.14, True],
    )
    def test_dump_tolerates_non_mapping_response_body(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        malformed_response: object,
    ) -> None:
        """Regression: dump_diagnosis_loop_pass should not crash on non-Mapping response_body.

        This prevents crashes when response_body arrives as non-Mapping type.
        """
        # Force forensic dump mode on so we exercise the guarded code path
        monkeypatch.setenv("K9B_P4C_FORENSIC_DUMP", "1")

        from scripts.k9b_otel_demo_lab_p4c_forensic_dump import (
            dump_diagnosis_loop_pass,
        )

        # Should not raise
        result = dump_diagnosis_loop_pass(
            artifact_dir=tmp_path,
            incident_id="test-incident",
            pass_num=1,
            request_body={},
            http_status=200,
            response_body=malformed_response,  # type: ignore[arg-type]
            loop_summary={},
            review_packet_metadata={},
        )

        # Should return a dict (the provenance)
        assert isinstance(result, dict)
        # Fields should reflect empty mapping when input is non-Mapping
        assert result.get("response_fields_present") == []

    def test_dump_with_valid_dict_response_body(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Verify dump works correctly with valid dict response_body."""
        monkeypatch.setenv("K9B_P4C_FORENSIC_DUMP", "1")

        from scripts.k9b_otel_demo_lab_p4c_forensic_dump import (
            dump_diagnosis_loop_pass,
        )

        valid_response = {
            "review_packet_path": "/tmp/review.json",
            "diagnosis": "Test diagnosis",
        }

        result = dump_diagnosis_loop_pass(
            artifact_dir=tmp_path,
            incident_id="test-incident",
            pass_num=1,
            request_body={},
            http_status=200,
            response_body=valid_response,
            loop_summary={},
            review_packet_metadata={},
        )

        assert isinstance(result, dict)
        assert "response_fields_present" in result
