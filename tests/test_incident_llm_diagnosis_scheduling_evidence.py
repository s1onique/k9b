"""Tests for scheduling evidence extraction in LLM diagnosis.

These tests verify that scheduling failure evidence (FailedScheduling, Unschedulable,
nodeSelector issues) is explicitly extracted and included in the diagnosis prompt
for P4c scheduling scenario diagnosis.

Run with: python -m pytest tests/test_incident_llm_diagnosis_scheduling_evidence.py -v
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_llm_diagnosis import build_diagnosis_prompt
from k8s_diag_agent.collect.incident_scheduling_evidence import extract_scheduling_evidence


class TestExtractSchedulingEvidence:
    """Test scheduling evidence extraction from events."""

    def test_no_events_returns_none(self) -> None:
        """No events should return None."""
        result = extract_scheduling_evidence([])
        assert result is None

    def test_none_events_returns_none(self) -> None:
        """None events should return None."""
        result = extract_scheduling_evidence(None)
        assert result is None

    def test_non_scheduling_events_returns_none(self) -> None:
        """Non-scheduling events should return None."""
        events = [
            {"type": "Normal", "reason": "Created", "message": "Created container"},
            {"type": "Normal", "reason": "Started", "message": "Started container"},
        ]
        result = extract_scheduling_evidence(events)
        assert result is None

    def test_failed_scheduling_event_extracted(self) -> None:
        """FailedScheduling event should be extracted."""
        events = [
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "FailedScheduling: 0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector.",
                "involved_object_kind": "Pod",
                "involved_object_name": "shipping-abc123",
            },
        ]
        result = extract_scheduling_evidence(events)
        assert result is not None
        assert len(result) == 1
        assert result[0]["reason"] == "FailedScheduling"
        assert "FailedScheduling" in result[0]["message"]
        assert result[0]["involved_object_kind"] == "Pod"
        assert result[0]["involved_object_name"] == "shipping-abc123"

    def test_unschedulable_event_extracted(self) -> None:
        """Unschedulable event should be extracted."""
        events = [
            {
                "type": "Warning",
                "reason": "Unschedulable",
                "message": "Pod is unschedulable: no matching node found",
            },
        ]
        result = extract_scheduling_evidence(events)
        assert result is not None
        assert len(result) == 1
        assert "Unschedulable" in result[0]["reason"]

    def test_node_selector_in_message_extracted(self) -> None:
        """Event with nodeSelector in message should be extracted."""
        events = [
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "Pod couldn't schedule: nodeSelector k9b.dev/otel-lab-node=missing doesn't match any node",
                "involved_object_name": "shipping-xyz",
            },
        ]
        result = extract_scheduling_evidence(events)
        assert result is not None
        assert "k9b.dev/otel-lab-node" in result[0]["message"]
        assert "missing" in result[0]["message"]

    def test_node_selector_message_without_failed_scheduling_reason_extracted(self) -> None:
        """Event with nodeSelector in message but non-canonical reason should be extracted.

        Some Kubernetes distributions may report scheduling failures with reason
        not equal to FailedScheduling but still include nodeSelector in the message.
        """
        events = [
            {
                "type": "Warning",
                "reason": "SchedulingConstraint",
                "message": "nodeSelector k9b.dev/otel-lab-node=missing doesn't match any node",
                "involved_object_name": "shipping-xyz",
            },
        ]
        result = extract_scheduling_evidence(events)
        assert result is not None
        assert result[0]["reason"] == "SchedulingConstraint"
        assert "k9b.dev/otel-lab-node" in result[0]["message"]

    def test_multiple_scheduling_events_extracted(self) -> None:
        """Multiple scheduling events should be extracted."""
        events = [
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector.",
                "involved_object_name": "shipping-abc",
            },
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "0/1 nodes are available: 1 node(s) didn't satisfy nodeSelector.",
                "involved_object_name": "shipping-def",
            },
        ]
        result = extract_scheduling_evidence(events)
        assert result is not None
        assert len(result) == 2

    def test_warning_backoff_is_not_scheduling_evidence(self) -> None:
        """Warning events without scheduling markers should NOT be scheduling_evidence.

        scheduling_evidence is intentionally strict - only scheduling-related events
        qualify. Generic warnings (BackOff, ImagePullBackOff, etc.) are excluded
        because they are already covered by recent_events in the prompt.
        """
        events = [
            {
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting failed container",
            },
        ]
        result = extract_scheduling_evidence(events)
        assert result is None

    def test_bounded_to_10_events(self) -> None:
        """Events should be bounded to 10."""
        events = [
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": f"Event {i}",
            }
            for i in range(15)
        ]
        result = extract_scheduling_evidence(events)
        assert result is not None
        assert len(result) == 10

    def test_skips_non_dict_events(self) -> None:
        """Non-dict events should be skipped."""
        events = [
            None,
            {"type": "Warning", "reason": "FailedScheduling", "message": "test"},
            "not a dict",
        ]
        result = extract_scheduling_evidence(events)
        assert result is not None
        assert len(result) == 1


class TestBuildDiagnosisPromptSchedulingEvidence:
    """Test that scheduling evidence appears in the diagnosis prompt."""

    def test_scheduling_evidence_in_prompt(self) -> None:
        """Scheduling evidence should appear in the generated prompt."""
        case_file = {
            "incident": {
                "incident_id": "test-123",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
                "severity": "warning",
            },
            "events": [
                {
                    "type": "Warning",
                    "reason": "FailedScheduling",
                    "message": "0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector.",
                    "involved_object_kind": "Pod",
                    "involved_object_name": "shipping-abc123",
                },
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Verify scheduling evidence terms appear in prompt
        assert "FailedScheduling" in prompt
        assert "Unschedulable" in prompt.lower() or "unschedulable" in prompt.lower()
        assert "shipping" in prompt.lower()

    def test_p4c_root_cause_terms_in_prompt(self) -> None:
        """P4c root cause terms should appear in prompt for verification."""
        case_file = {
            "incident": {
                "incident_id": "test-456",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
                "severity": "warning",
            },
            "events": [
                {
                    "type": "Warning",
                    "reason": "FailedScheduling",
                    "message": "0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector. nodeSelector: k9b.dev/otel-lab-node=missing",
                    "involved_object_kind": "Pod",
                    "involved_object_name": "shipping-xyz",
                },
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # P4c required root cause terms
        assert "shipping" in prompt.lower()
        assert "nodeSelector" in prompt
        assert "FailedScheduling" in prompt
        assert "k9b.dev/otel-lab-node" in prompt
        assert "missing" in prompt.lower()

    def test_prompt_includes_scheduling_evidence_section(self) -> None:
        """Prompt should include scheduling_evidence in JSON."""
        case_file = {
            "incident": {
                "incident_id": "test-789",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
                "severity": "warning",
            },
            "events": [
                {
                    "type": "Warning",
                    "reason": "FailedScheduling",
                    "message": "0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector.",
                    "involved_object_kind": "Pod",
                    "involved_object_name": "shipping-abc",
                },
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Verify scheduling_evidence appears in the case file data section
        assert "scheduling_evidence" in prompt


class TestSchedulingEvidenceRegression:
    """Regression tests for P4c scheduling scenario.

    These tests verify that the diagnosis prompt includes all the evidence
    needed for P4c root cause validation:
    - shipping (deployment name)
    - nodeSelector (scheduling constraint type)
    - k9b.dev/otel-lab-node=missing (specific constraint)
    - FailedScheduling (event reason)
    - Unschedulable (scheduling state)
    - didn't match Pod's node affinity/selector (failure message)
    """

    def test_p4c_required_terms_all_present(self) -> None:
        """All P4c required root cause terms should be present."""
        case_file = {
            "incident": {
                "incident_id": "p4c-test-001",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
                "severity": "warning",
            },
            "events": [
                {
                    "type": "Warning",
                    "reason": "FailedScheduling",
                    "message": "0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector. nodeSelector: k9b.dev/otel-lab-node=missing",
                    "involved_object_kind": "Pod",
                    "involved_object_name": "shipping-abc",
                },
            ],
        }

        prompt = build_diagnosis_prompt(case_file)
        prompt_lower = prompt.lower()

        # P4c required root cause terms for validation
        # Check each term
        assert "shipping" in prompt_lower, "shipping not in prompt"
        assert "nodeselector" in prompt_lower, "nodeSelector not in prompt"
        assert "k9b.dev/otel-lab-node" in prompt_lower, "k9b.dev/otel-lab-node not in prompt"
        assert "missing" in prompt_lower, "missing not in prompt"
        assert "failedscheduling" in prompt_lower, "FailedScheduling not in prompt"

    def test_scheduling_evidence_includes_involved_object(self) -> None:
        """Scheduling evidence should include involved object details."""
        events = [
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "Pod scheduling failed due to nodeSelector constraint",
                "involved_object_kind": "Pod",
                "involved_object_name": "shipping-xyz-789",
            },
        ]

        result = extract_scheduling_evidence(events)
        assert result is not None
        assert len(result) == 1
        assert result[0]["involved_object_kind"] == "Pod"
        assert result[0]["involved_object_name"] == "shipping-xyz-789"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
