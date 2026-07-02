"""Tests for log_diagnosis_result() - outcome-aware rendering."""

from __future__ import annotations

import io
from unittest.mock import patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import log_diagnosis_result


class TestLogDiagnosisResultTerminalSuccess:
    """Tests for terminal single-pass success logging."""

    def test_terminal_single_pass_success_logs_passed(self) -> None:
        """Terminal single-pass success logs PASSED, not FAILED."""
        captured = io.StringIO()

        evidence = {
            "incident_id": "test-incident",
            "p4c_outcome": {
                "success": True,
                "mode": "terminal_single_pass",
                "pass_count": 1,
                "pass_run_ids": ["run-123"],
                "review_artifact_paths": ["/artifacts/review/test.json"],
                "terminal_decision": "stop_no_checks_proposed",
                "read_only_constraints_satisfied": True,
                "root_cause_evidence_satisfied": True,
                "root_cause_evidence_reason": None,
                "failure_reasons": [],
            },
            "validation_success": True,
        }
        term_checks = {"mentions_shipping": False}

        with patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_render.log", lambda msg: print(msg, file=captured)):
            log_diagnosis_result(True, evidence, term_checks)

        output = captured.getvalue()
        assert "P4c diagnosis PASSED" in output
        assert "terminal single-pass" in output.lower()
        assert "P4c diagnosis FAILED" not in output

    def test_terminal_single_pass_success_no_failure_reasons(self) -> None:
        """Terminal single-pass success shows 'Failure reason: none'."""
        captured = io.StringIO()

        evidence = {
            "incident_id": "test-incident",
            "p4c_outcome": {
                "success": True,
                "mode": "terminal_single_pass",
                "pass_count": 1,
                "pass_run_ids": ["run-123"],
                "review_artifact_paths": [],
                "failure_reasons": [],
            },
            "validation_success": True,
            # Stale legacy value should be ignored
            "failure_reason": "insufficient_passes: 1 < 2",
        }
        term_checks = {"mentions_shipping": False}

        with patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_render.log", lambda msg: print(msg, file=captured)):
            log_diagnosis_result(True, evidence, term_checks)

        output = captured.getvalue()
        assert "Failure reason: none" in output
        assert "insufficient_passes" not in output


class TestLogDiagnosisResultTerminalFailure:
    """Tests for terminal single-pass failure logging."""

    def test_terminal_single_pass_failure_logs_failed(self) -> None:
        """Terminal single-pass failure logs FAILED."""
        captured = io.StringIO()

        evidence = {
            "incident_id": "test-incident",
            "p4c_outcome": {
                "success": False,
                "mode": "terminal_single_pass",
                "pass_count": 1,
                "pass_run_ids": [],
                "review_artifact_paths": [],
                "failure_reasons": ["missing_review_artifact_reference"],
            },
            "validation_success": False,
        }
        term_checks = {"mentions_shipping": False}

        with patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_render.log", lambda msg: print(msg, file=captured)):
            log_diagnosis_result(False, evidence, term_checks)

        output = captured.getvalue()
        assert "P4c diagnosis FAILED" in output
        assert "terminal single-pass" in output.lower()
        assert "P4c diagnosis PASSED" not in output

    def test_terminal_single_pass_failure_shows_normalized_reasons(self) -> None:
        """Terminal single-pass failure shows normalized failure reasons."""
        captured = io.StringIO()

        evidence = {
            "incident_id": "test-incident",
            "p4c_outcome": {
                "success": False,
                "mode": "terminal_single_pass",
                "pass_count": 1,
                "pass_run_ids": [],
                "review_artifact_paths": [],
                "failure_reasons": ["terminal_decision_missing", "missing_review_artifact_reference"],
            },
            "validation_success": False,
        }
        term_checks = {"mentions_shipping": False}

        with patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_render.log", lambda msg: print(msg, file=captured)):
            log_diagnosis_result(False, evidence, term_checks)

        output = captured.getvalue()
        assert "terminal_decision_missing" in output
        assert "missing_review_artifact_reference" in output


class TestLogDiagnosisResultMultipass:
    """Tests for multipass mode logging."""

    def test_multipass_success_logs_passed(self) -> None:
        """Multipass success logs PASSED."""
        captured = io.StringIO()

        evidence = {
            "incident_id": "test-incident",
            "p4c_outcome": {
                "success": True,
                "mode": "multipass",
                "pass_count": 2,
                "pass_run_ids": ["run-1", "run-2"],
                "review_artifact_paths": [],
                "failure_reasons": [],
            },
            "validation_success": True,
        }
        term_checks = {"mentions_shipping": True}

        with patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_render.log", lambda msg: print(msg, file=captured)):
            log_diagnosis_result(True, evidence, term_checks)

        output = captured.getvalue()
        assert "P4c diagnosis PASSED" in output
        assert "multipass" in output

    def test_multipass_failure_logs_failed(self) -> None:
        """Multipass failure logs FAILED."""
        captured = io.StringIO()

        evidence = {
            "incident_id": "test-incident",
            "p4c_outcome": {
                "success": False,
                "mode": "multipass",
                "pass_count": 1,
                "pass_run_ids": [],
                "review_artifact_paths": [],
                "failure_reasons": ["insufficient_passes: 1 < 2"],
            },
            "validation_success": False,
        }
        term_checks = {"mentions_shipping": False}

        with patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_render.log", lambda msg: print(msg, file=captured)):
            log_diagnosis_result(False, evidence, term_checks)

        output = captured.getvalue()
        assert "P4c diagnosis FAILED" in output
        assert "insufficient_passes" in output


class TestLogDiagnosisResultLegacy:
    """Tests for legacy path (no p4c_outcome)."""

    def test_legacy_path_uses_evidence_fields(self) -> None:
        """Legacy path uses evidence fields without p4c_outcome."""
        captured = io.StringIO()

        evidence = {
            "incident_id": "test-incident",
            "validation_success": True,
            "pass_count": 2,
            "pass_run_ids": ["run-1"],
            "failure_reason": None,
            # No p4c_outcome
        }
        term_checks = {"mentions_shipping": True}

        with patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_render.log", lambda msg: print(msg, file=captured)):
            log_diagnosis_result(True, evidence, term_checks)

        output = captured.getvalue()
        assert "P4c diagnosis PASSED" not in output  # Legacy path doesn't use this
        assert "Success: True" in output
