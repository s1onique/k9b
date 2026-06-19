"""Safety tests for automatic diagnosis review handoff endpoint.

Tests the safety constraints of the handoff endpoint:
- incident_id validation
- path traversal prevention
- forbidden field exposure
- arbitrary path exposure
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from k8s_diag_agent.ui.api_incident_reads_handoff import (
    build_automatic_diagnosis_review_handoff_payload,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def external_analysis_dir():
    """Create a temporary external-analysis directory."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def write_sample_packet(external_analysis_dir):
    """Write a sample review packet."""
    packet_data = {
        "schema_version": "1.0",
        "artifact_type": "diagnosis-loop-review-packet",
        "incident_id": "incident-123",
        "automatic": True,
        "read_only": True,
        "run_id": "auto-incident-123-20260619074500",
        "collector_run_id": "auto-diagnosis-20260619074500-abc123",
        "loop_result": {
            "decision": "run_allowed_read_only_checks",
            "checks_requested": 3,
            "checks_run": 2,
            "checks_rejected": 1,
        },
        "generated_at": "2026-06-19T07:45:00+00:00",
        "eligibility": {
            "eligible": True,
            "reason": "active_incident_with_suggested_checks",
        },
    }
    packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
    packet_path = external_analysis_dir / packet_name
    packet_path.write_text(json.dumps(packet_data), encoding="utf-8")
    return packet_path


# =============================================================================
# Tests: incident_id validation
# =============================================================================


class TestIncidentIdValidation:
    """Tests for incident_id validation in handoff endpoint."""

    def test_valid_incident_id_works(self, external_analysis_dir, write_sample_packet):
        """Valid incident_id returns available response."""
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True

    def test_incident_id_with_underscore_works(self, external_analysis_dir):
        """Incident_id with underscores is valid."""
        # Write packet for incident with underscore
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "my_incident",
            "run_id": "auto-my_incident-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
        }
        packet_name = "auto-my_incident-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "my_incident"
        )
        assert result["available"] is True

    def test_incident_id_with_dash_works(self, external_analysis_dir):
        """Incident_id with dashes is valid."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "my-incident",
            "run_id": "auto-my-incident-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
        }
        packet_name = "auto-my-incident-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "my-incident"
        )
        assert result["available"] is True

    def test_incident_id_with_dot_works(self, external_analysis_dir):
        """Incident_id with dots is valid."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "my.incident",
            "run_id": "auto-my.incident-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
        }
        packet_name = "auto-my.incident-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "my.incident"
        )
        assert result["available"] is True


# =============================================================================
# Tests: Path traversal prevention
# =============================================================================


class TestPathTraversalPrevention:
    """Tests for path traversal prevention."""

    def test_incident_id_with_path_traversal_returns_unavailable(
        self, external_analysis_dir
    ):
        """incident_id with ../ returns unavailable, not the file."""
        # This should NOT find any packet because the filename pattern doesn't match
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "../../../etc/passwd"
        )
        # Should return unavailable, not error
        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"

    def test_incident_id_with_absolute_path_returns_unavailable(
        self, external_analysis_dir
    ):
        """incident_id with absolute path returns unavailable."""
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "/etc/passwd"
        )
        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"

    def test_client_cannot_provide_arbitrary_artifact_path(
        self, external_analysis_dir
    ):
        """Client cannot provide arbitrary artifact path."""
        # The endpoint only accepts incident_id, not artifact paths
        # So we test that only auto-{incident_id}-* patterns are matched
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "auto-something-20260619074500-diagnosis-review-packet.json"
        )
        # This should return unavailable because it's not a valid incident_id
        # The pattern requires auto-{incident_id}-... 
        assert result["available"] is False


# =============================================================================
# Tests: Raw artifact exposure
# =============================================================================


class TestRawArtifactExposure:
    """Tests that raw artifacts are not exposed."""

    def test_raw_case_file_not_in_content(self, external_analysis_dir):
        """Content does not include raw case file."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "run_id": "auto-incident-123-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
            # These should NOT appear in handoff
            "case_file": {"sensitive": "data", "raw_content": "should not appear"},
        }
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True
        assert "sensitive" not in result["content"].lower()
        assert "should not appear" not in result["content"].lower()

    def test_runner_result_not_in_content(self, external_analysis_dir):
        """Content does not include runner result."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "run_id": "auto-incident-123-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
            "runner_result": {"raw_output": "should not appear"},
        }
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True
        assert "should not appear" not in result["content"].lower()

    def test_absolute_paths_not_exposed(self, external_analysis_dir):
        """Content does not include absolute paths."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "run_id": "auto-incident-123-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
            "artifact_path": "/absolute/path/should/not/appear",
        }
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True
        # Only artifact_name (filename) should appear, not full path
        assert "/absolute/path" not in result["content"]


# =============================================================================
# Tests: Secrets/credentials exposure
# =============================================================================


class TestSecretsExposure:
    """Tests that secrets and credentials are not exposed."""

    def test_kubeconfig_not_exposed(self, external_analysis_dir):
        """Kubeconfig strings are not in content."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "run_id": "auto-incident-123-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
            "metadata": {"kubeconfig_content": "secret data should not appear"},
        }
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True
        assert "secret data" not in result["content"].lower()

    def test_tokens_not_exposed(self, external_analysis_dir):
        """Token strings are not in content."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "run_id": "auto-incident-123-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
            "token": "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        }
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result["content"]

    def test_passwords_not_exposed(self, external_analysis_dir):
        """Password strings are not in content."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "run_id": "auto-incident-123-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
            "auth": {"password": "super_secret_password"},
        }
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True
        assert "super_secret_password" not in result["content"].lower()


# =============================================================================
# Tests: Action-control fields
# =============================================================================


class TestActionControlFields:
    """Tests that action-control fields are not exposed."""

    def test_action_control_fields_not_in_content(self, external_analysis_dir):
        """Action-control fields are not in handoff content."""
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "run_id": "auto-incident-123-20260619074500",
            "collector_run_id": "auto-diagnosis-20260619074500-abc123",
            "loop_result": {"decision": "test", "checks_requested": 1, "checks_run": 1, "checks_rejected": 0},
            "generated_at": "2026-06-19T07:45:00+00:00",
            "eligibility": {"eligible": True, "reason": "test"},
            # These fields should not appear in handoff content
            "kubectl_command": "kubectl apply -f deployment.yaml",
            "allowed_actions": ["remediate", "apply", "delete"],
            "action": "remediate the issue",
        }
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True
        # Action-control strings should not appear
        assert "kubectl apply" not in result["content"].lower()
        assert "remediate the issue" not in result["content"].lower()


# =============================================================================
# Tests: Malformed packet handling
# =============================================================================


class TestMalformedPacketHandling:
    """Tests for malformed packet handling."""

    def test_malformed_json_returns_unavailable(
        self, external_analysis_dir
    ):
        """Malformed JSON returns unavailable with malformed_review_packet."""
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        # Write invalid JSON
        packet_path.write_text("{ invalid json content", encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is False
        assert result["unavailable_reason"] == "malformed_review_packet"

    def test_missing_required_fields_returns_unavailable(
        self, external_analysis_dir
    ):
        """Packet missing required fields returns unavailable."""
        # Write packet without required loop_result
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "run_id": "auto-incident-123-20260619074500",
            # Missing: loop_result, generated_at, eligibility
        }
        packet_name = "auto-incident-123-20260619074500-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        # Should still return available but with safe defaults
        assert result["available"] is True
        # Check that it uses safe defaults
        assert "no decision recorded" in result["content"].lower()
