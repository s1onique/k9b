#!/usr/bin/env python3
"""Tests for check_persisted_diagnosis_contract.py"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_persisted_diagnosis_contract import (
    build_bounded_summary,
    check_diagnosis_persisted,
    check_for_secrets,
    check_provider_status,
    load_incident_json,
)


class TestCheckDiagnosisPersisted:
    """Tests for check_diagnosis_persisted function."""

    def test_passes_with_available_review(self) -> None:
        """Passes when automatic_diagnosis_review.available is True."""
        incident = {
            "incident_id": "test-incident-123",
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_name": "diagnosis-review-packet.json",
                "decision": "completed",
            },
            "automatic_diagnosis_loop_summary": {
                "status": "completed",
            },
        }
        is_persisted, failure_class, findings = check_diagnosis_persisted(incident)
        assert is_persisted is True
        assert failure_class == ""
        assert any("diagnosis_persisted" in f for f in findings)

    def test_passes_with_completed_loop_status(self) -> None:
        """Passes when loop summary status is completed even if review not available."""
        incident = {
            "incident_id": "test-incident-123",
            "automatic_diagnosis_review": {
                "available": False,
            },
            "automatic_diagnosis_loop_summary": {
                "status": "completed",
            },
        }
        is_persisted, failure_class, findings = check_diagnosis_persisted(incident)
        assert is_persisted is True

    def test_fails_when_not_persisted(self) -> None:
        """Fails when diagnosis is not persisted."""
        incident = {
            "incident_id": "test-incident-123",
            "automatic_diagnosis_review": {
                "available": False,
            },
            "automatic_diagnosis_loop_summary": {
                "status": "not_run",
            },
        }
        is_persisted, failure_class, findings = check_diagnosis_persisted(incident)
        assert is_persisted is False
        assert failure_class == "diagnosis_not_persisted"

    def test_fails_with_empty_payload_when_available(self) -> None:
        """Fails when available=True but no artifact_name or decision."""
        incident = {
            "incident_id": "test-incident-123",
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_name": "",
                "decision": "",
            },
            "automatic_diagnosis_loop_summary": {
                "status": "completed",
            },
        }
        is_persisted, failure_class, findings = check_diagnosis_persisted(incident)
        assert is_persisted is False
        assert failure_class == "diagnosis_payload_empty"

    def test_fails_with_unbounded_payload(self) -> None:
        """Fails when artifact_name exceeds max length."""
        incident = {
            "incident_id": "test-incident-123",
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_name": "x" * 300,  # Exceeds 240 char limit
                "decision": "completed",
            },
            "automatic_diagnosis_loop_summary": {
                "status": "completed",
            },
        }
        is_persisted, failure_class, findings = check_diagnosis_persisted(incident)
        assert is_persisted is False
        assert failure_class == "diagnosis_payload_unbounded"


class TestCheckProviderStatus:
    """Tests for check_provider_status function."""

    def test_passes_when_no_provider_fields(self) -> None:
        """Passes when no provider fields present (provider disabled)."""
        incident = {
            "incident_id": "test-incident-123",
        }
        is_ok, failure_class, findings = check_provider_status(incident)
        assert is_ok is True
        assert failure_class == ""

    def test_passes_when_provider_configured_true(self) -> None:
        """Passes when provider_configured is True."""
        incident = {
            "incident_id": "test-incident-123",
            "provider_configured": True,
        }
        is_ok, failure_class, findings = check_provider_status(incident)
        assert is_ok is True

    def test_fails_when_provider_not_configured(self) -> None:
        """Fails when provider_configured is False."""
        incident = {
            "incident_id": "test-incident-123",
            "provider_configured": False,
        }
        is_ok, failure_class, findings = check_provider_status(incident)
        assert is_ok is False
        assert failure_class == "provider_not_configured"

    def test_requires_invocation_when_flag_set(self) -> None:
        """Fails when require_provider_invoked=True but provider not invoked."""
        incident = {
            "incident_id": "test-incident-123",
            "provider_configured": True,
            "provider_invocation_attempted": False,
        }
        is_ok, failure_class, findings = check_provider_status(incident, require_provider_invoked=True)
        assert is_ok is False
        assert failure_class == "provider_not_invoked"

    def test_passes_when_invoked_and_required(self) -> None:
        """Passes when provider invoked and require_provider_invoked=True."""
        incident = {
            "incident_id": "test-incident-123",
            "provider_configured": True,
            "provider_invocation_attempted": True,
        }
        is_ok, failure_class, findings = check_provider_status(incident, require_provider_invoked=True)
        assert is_ok is True

    def test_requires_provider_fields_when_invocation_required(self) -> None:
        """Fails when require_provider_invoked=True but no provider fields present."""
        incident = {"incident_id": "test-incident-123"}
        is_ok, failure_class, findings = check_provider_status(
            incident,
            require_provider_invoked=True,
        )
        assert is_ok is False
        assert failure_class == "provider_status_missing"


class TestCheckForSecrets:
    """Tests for check_for_secrets function."""

    def test_detects_bearer_token(self) -> None:
        """Detects bearer tokens in content."""
        content = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        findings = check_for_secrets(content)
        assert any("Bearer token" in f for f in findings)

    def test_detects_openai_api_key(self) -> None:
        """Detects OpenAI API keys."""
        content = "sk-1234567890abcdefghijklmnopqrstuvwxyz123456"
        findings = check_for_secrets(content)
        assert any("OpenAI API key" in f for f in findings)

    def test_detects_internal_ip(self) -> None:
        """Detects internal IPs."""
        content = "Connected to 10.0.0.1:8080"
        findings = check_for_secrets(content)
        assert any("10.x.x.x" in f for f in findings)

    def test_no_findings_for_safe_content(self) -> None:
        """No findings for safe content."""
        content = "This is a normal log message without secrets"
        findings = check_for_secrets(content)
        assert len(findings) == 0


class TestLoadIncidentJson:
    """Tests for load_incident_json function."""

    def test_loads_valid_json(self) -> None:
        """Loads valid JSON incident."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"incident_id": "test-123"}, f)
            f.flush()
            path = Path(f.name)

        try:
            incident, error = load_incident_json(path)
            assert incident is not None
            assert incident["incident_id"] == "test-123"
            assert error == ""
        finally:
            path.unlink()

    def test_handles_invalid_json(self) -> None:
        """Handles invalid JSON gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {")
            f.flush()
            path = Path(f.name)

        try:
            incident, error = load_incident_json(path)
            assert incident is None
            assert "invalid_incident_json" in error
        finally:
            path.unlink()


class TestBuildBoundedSummary:
    """Tests for build_bounded_summary function."""

    def test_passes_summary(self) -> None:
        """Builds pass summary correctly."""
        summary = build_bounded_summary(
            incident_id="test-123",
            diagnosis_persisted=True,
            provider_configured=True,
            provider_invoked=True,
            auto_review_available=True,
            loop_status="completed",
            http_status=200,
        )
        assert "PASSED" in summary
        assert "test-123" in summary
        assert "Diagnosis persisted: True" in summary

    def test_failure_summary(self) -> None:
        """Builds failure summary correctly."""
        summary = build_bounded_summary(
            incident_id="test-123",
            diagnosis_persisted=False,
            provider_configured=None,
            provider_invoked=None,
            auto_review_available=False,
            loop_status="not_run",
            http_status=200,
            failure_class="diagnosis_not_persisted",
        )
        assert "FAILED" in summary
        assert "diagnosis_not_persisted" in summary
        assert "Diagnosis persisted: False" in summary


class TestMainIntegration:
    """Integration tests for main entry point."""

    def test_main_fails_closed_when_incident_contains_secret(self, tmp_path: Path) -> None:
        """Fails with artifact_verification_failed when incident contains secrets."""
        # Import main function from the module
        import importlib.util
        module_path = Path(__file__).parent.parent / "scripts" / "check_persisted_diagnosis_contract.py"
        spec = importlib.util.spec_from_file_location("check_persisted_diagnosis_contract", module_path)
        if spec is None or spec.loader is None:
            pytest.fail(f"Could not load module spec for {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        main = module.main

        incident_path = tmp_path / "incident.json"
        output_dir = tmp_path / "out"

        # Write incident with valid diagnosis but leaked API key
        incident_path.write_text(json.dumps({
            "incident_id": "test-incident-123",
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_name": "diagnosis-review-packet.json",
                "decision": "completed",
            },
            "automatic_diagnosis_loop_summary": {
                "status": "completed",
            },
            "provider_configured": True,
            "provider_invocation_attempted": True,
            # Leaked secret in the incident
            "leaked_api_key": "sk-1234567890abcdefghijklmnopqrstuvwxyz123456",
        }))

        # Call main with the test incident
        old_argv = sys.argv
        try:
            sys.argv = [
                "check_persisted_diagnosis_contract.py",
                "--incident-json", str(incident_path),
                "--output-dir", str(output_dir),
            ]
            rc = main()
        finally:
            sys.argv = old_argv

        # Should fail
        assert rc == 1

        # Result JSON should be failed
        result_path = output_dir / "persisted-diagnosis-result.json"
        assert result_path.exists()
        result = json.loads(result_path.read_text())
        assert result["passed"] is False
        assert result["failure_class"] == "artifact_verification_failed"
        # Should have secret findings recorded
        assert result.get("secret_findings") is not None
        assert len(result["secret_findings"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
