"""Tests for automatic diagnosis review handoff endpoint.

Tests the read-only handoff endpoint for automatic diagnosis review packets.
Verifies safety constraints, availability states, and content validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from k8s_diag_agent.ui.api_incident_reads_handoff import (
    MAX_HANDOFF_CONTENT_LENGTH,
    _validate_handoff_content,
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
def sample_review_packet():
    """Create a sample review packet dict."""
    return {
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


@pytest.fixture
def write_review_packet(external_analysis_dir, sample_review_packet):
    """Write a sample review packet to the external-analysis directory."""
    packet_name = f"{sample_review_packet['run_id']}-diagnosis-review-packet.json"
    packet_path = external_analysis_dir / packet_name
    packet_data = {
        "schema_version": "1.0",
        "artifact_type": "diagnosis-loop-review-packet",
        "incident_id": "incident-123",
        "automatic": True,
        "read_only": True,
        **sample_review_packet,
    }
    packet_path.write_text(json.dumps(packet_data), encoding="utf-8")
    return packet_path


# =============================================================================
# Tests: build_automatic_diagnosis_review_handoff_payload
# =============================================================================


class TestBuildHandoffPayload:
    """Tests for build_automatic_diagnosis_review_handoff_payload."""

    def test_returns_unavailable_when_dir_is_none(self):
        """Returns unavailable when external_analysis_dir is None."""
        result = build_automatic_diagnosis_review_handoff_payload(None, "incident-123")
        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"

    def test_returns_unavailable_when_no_packet_exists(
        self, external_analysis_dir
    ):
        """Returns unavailable when no packet exists for incident."""
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "nonexistent-incident"
        )
        assert result["available"] is False
        assert result["unavailable_reason"] == "no_review_packet"

    def test_returns_available_with_handoff_fields(
        self, external_analysis_dir, write_review_packet
    ):
        """Returns available=True with handoff fields when packet exists."""
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["available"] is True
        assert result["incident_id"] == "incident-123"
        assert result["artifact_type"] == "diagnosis-loop-review-packet"
        assert result["format"] == "markdown"
        assert "content" in result
        assert result["read_only"] is True
        assert result["review_required_before_any_action"] is True
        assert result["no_remediation_attempted"] is True

    def test_artifact_name_is_filename_only(
        self, external_analysis_dir, write_review_packet
    ):
        """artifact_name is filename only, no path."""
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert result["artifact_name"] is not None
        # Should not contain path separators
        assert "/" not in result["artifact_name"]
        assert "\\" not in result["artifact_name"]
        # Should end with .json
        assert result["artifact_name"].endswith(".json")

    def test_content_includes_read_only_language(
        self, external_analysis_dir, write_review_packet
    ):
        """Content includes read-only/review-required/no-remediation language."""
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        content = result["content"]
        assert "read-only evidence" in content.lower() or "read only evidence" in content.lower()
        assert "review is required" in content.lower()
        assert "no remediation" in content.lower()

    def test_content_includes_decision_and_counts(
        self, external_analysis_dir, write_review_packet
    ):
        """Content includes decision and check counts."""
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        content = result["content"]
        assert "run_allowed_read_only_checks" in content
        assert "Requested: 3" in content
        assert "Run: 2" in content
        assert "Rejected: 1" in content

    def test_content_is_bounded(
        self, external_analysis_dir, sample_review_packet
    ):
        """Content is bounded to MAX_HANDOFF_CONTENT_LENGTH."""
        # Create a very large packet
        large_decision = "x" * (MAX_HANDOFF_CONTENT_LENGTH + 1000)
        sample_review_packet["loop_result"]["decision"] = large_decision
        packet_name = f"{sample_review_packet['run_id']}-diagnosis-review-packet.json"
        packet_path = external_analysis_dir / packet_name
        packet_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            **sample_review_packet,
        }
        packet_path.write_text(json.dumps(packet_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert len(result["content"]) <= MAX_HANDOFF_CONTENT_LENGTH

    def test_content_sha256_is_present(
        self, external_analysis_dir, write_review_packet
    ):
        """content_sha256 is present and bounded."""
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        assert "content_sha256" in result
        assert len(result["content_sha256"]) <= 64  # SHA256 hex length

    def test_multiple_packets_chooses_latest_deterministically(
        self, external_analysis_dir, sample_review_packet
    ):
        """Multiple packets choose the latest deterministically."""
        # Write older packet
        old_packet = sample_review_packet.copy()
        old_packet["run_id"] = "auto-incident-123-20260618080000"
        old_packet_name = f"{old_packet['run_id']}-diagnosis-review-packet.json"
        old_path = external_analysis_dir / old_packet_name
        old_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            "loop_result": {
                "decision": "old_decision",
                "checks_requested": 1,
                "checks_run": 1,
                "checks_rejected": 0,
            },
            "generated_at": "2026-06-18T08:00:00+00:00",
            "eligibility": {
                "eligible": True,
                "reason": "old_reason",
            },
        }
        old_path.write_text(json.dumps(old_data), encoding="utf-8")

        # Write newer packet
        new_packet = sample_review_packet.copy()
        new_packet["run_id"] = "auto-incident-123-20260619090000"
        new_packet_name = f"{new_packet['run_id']}-diagnosis-review-packet.json"
        new_path = external_analysis_dir / new_packet_name
        new_data = {
            "schema_version": "1.0",
            "artifact_type": "diagnosis-loop-review-packet",
            "incident_id": "incident-123",
            **new_packet,
        }
        new_path.write_text(json.dumps(new_data), encoding="utf-8")

        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, "incident-123"
        )
        # Should pick the newer packet (20260619 > 20260618)
        assert result["run_id"] == "auto-incident-123-20260619090000"
        assert "new_decision" not in result["content"]  # Should not have new packet
        # Actually new packet has the old sample decision since we copied


# =============================================================================
# Tests: _validate_handoff_content
# =============================================================================


class TestValidateHandoffContent:
    """Tests for _validate_handoff_content.

    The validation uses specific patterns to avoid false positives.
    For example, "authorization" alone is allowed (it appears in legitimate
    review instructions like "Do not infer authorization to mutate..."),
    but "authorization: " (a header) is forbidden.
    """

    def test_returns_true_for_safe_content(self):
        """Returns True for content without forbidden terms."""
        safe_content = """
        # Automatic diagnosis review packet

        Incident: incident-123
        Decision: run_allowed_read_only_checks

        This is read-only evidence.
        Review is required before any action.
        Do not infer authorization to mutate the cluster.
        """
        assert _validate_handoff_content(safe_content) is True

    def test_returns_true_for_authorization_in_natural_language(self):
        """Returns True for 'authorization' in natural language context."""
        content = "Do not infer authorization to mutate the cluster."
        assert _validate_handoff_content(content) is True

    def test_returns_true_for_token_in_natural_language(self):
        """Returns True for 'token' alone in natural language context."""
        content = "The word token appears in this sentence."
        assert _validate_handoff_content(content) is True

    def test_returns_true_for_delete_in_natural_language(self):
        """Returns True for 'delete' alone in natural language context."""
        content = "Delete this message after reading."
        assert _validate_handoff_content(content) is True

    def test_returns_true_for_shell_in_natural_language(self):
        """Returns True for 'shell' alone in natural language context."""
        content = "The shell of the pod looks healthy."
        assert _validate_handoff_content(content) is True

    def test_returns_true_for_subprocess_in_natural_language(self):
        """Returns True for 'subprocess' alone in natural language."""
        content = "A subprocess of the main process was created."
        assert _validate_handoff_content(content) is True

    def test_returns_false_for_forbidden_term_raw_case_file(self):
        """Returns False if raw_case_file is present."""
        content = "This contains raw_case_file information."
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_forbidden_term_runner_result(self):
        """Returns False if runner_result is present (with underscore)."""
        content = "Runner_result was: success"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_forbidden_term_selected_checks(self):
        """Returns False if selected_checks is present (with underscore)."""
        content = "Selected_checks: check1, check2"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_forbidden_term_artifact_path(self):
        """Returns False if artifact_path is present (with underscore)."""
        content = "artifact_path: /path/to/artifact.json"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_forbidden_term_absolute_path(self):
        """Returns False if absolute_path is present (with underscore)."""
        content = "absolute_path was used for file access."
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_kubeconfig(self):
        """Returns False if kubeconfig is present."""
        content = "The kubeconfig was used for authentication."
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_bearer_token(self):
        """Returns False if bearer token is present."""
        content = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_auth_token(self):
        """Returns False if auth_token is present."""
        content = "auth_token=abc123"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_authorization_header(self):
        """Returns False if authorization header is present."""
        content = "Authorization: Bearer token123"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_api_key(self):
        """Returns False if api_key value is present."""
        content = "The api_key was stored securely."
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_kubectl_apply(self):
        """Returns False if kubectl apply is present."""
        content = "kubectl apply -f deployment.yaml"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_kubectl_delete(self):
        """Returns False if kubectl delete is present."""
        content = "kubectl delete pod my-pod"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_kubectl_patch(self):
        """Returns False if kubectl patch is present."""
        content = "kubectl patch deployment my-deploy"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_kubectl_scale(self):
        """Returns False if kubectl scale is present."""
        content = "kubectl scale deployment my-deploy --replicas=3"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_remediate(self):
        """Returns False if remediate is present."""
        content = "remediate the issue immediately."
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_rollout_restart(self):
        """Returns False if rollout restart is present."""
        content = "rollout restart deployment my-deploy"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_helm_install(self):
        """Returns False if helm install is present."""
        content = "helm install my-release my-chart"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_helm_upgrade(self):
        """Returns False if helm upgrade is present."""
        content = "helm upgrade my-release my-chart"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_secret_value(self):
        """Returns False if secret value pattern is present."""
        content = "field:secret_value_here"
        assert _validate_handoff_content(content) is False

    def test_returns_false_for_password_value(self):
        """Returns False if password= pattern is present."""
        content = "password=mypassword123"
        assert _validate_handoff_content(content) is False

    def test_case_insensitive_matching(self):
        """Forbidden term matching is case-insensitive."""
        assert _validate_handoff_content("KUBECONFIG file") is False
        assert _validate_handoff_content("KUBECTL APPLY -f config.yaml") is False
        assert _validate_handoff_content("REMEDIATE the issue") is False
