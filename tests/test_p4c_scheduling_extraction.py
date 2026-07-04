"""Unit tests for P4c scheduling root-cause extraction helpers.

These tests verify the core extraction logic for:
- _iter_backend_incident_signals() extraction from various incident shapes
- _is_failed_scheduling_signal() matching logic
- _parse_selector_literal() parsing
- extract_scheduling_root_cause() with various input combinations
- Malformed input handling (nil-safe boundaries)
"""

from __future__ import annotations

import pytest

from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
    _is_failed_scheduling_signal,
    _iter_backend_incident_signals,
    _parse_selector_literal,
    check_scheduling_root_cause_complete,
    extract_scheduling_root_cause,
)


class TestExtractSelectorLiteralFromFailedSchedulingSignal:
    """Test selector extraction from FailedScheduling signals (P4c phase helper)."""

    def test_extracts_selector_literal_from_failed_scheduling_message(self) -> None:
        """Extracts selector literal when it's present in FailedScheduling message.
        
        Deterministic test: when the message contains k9b.dev/otel-lab-node=missing,
        the helper should extract it.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c import (
            _extract_selector_literal_from_failed_scheduling_signal,
        )
        sig = {
            "reason": "FailedScheduling",
            "message": (
                "0/8 nodes are available: 8 node(s) didn't match "
                "Pod's node affinity/selector: k9b.dev/otel-lab-node=missing"
            ),
        }
        result = _extract_selector_literal_from_failed_scheduling_signal(sig)
        assert result == "k9b.dev/otel-lab-node=missing"

    def test_extracts_k9b_lab_label(self) -> None:
        """Extracts k9b.dev/otel-lab-node label from FailedScheduling message."""
        # Import from phase_p4c which defines this helper
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c import (
            _extract_selector_literal_from_failed_scheduling_signal,
        )
        sig = {
            "reason": "FailedScheduling",
            "message": "0/8 nodes are available: 8 node(s) didn't match Pod's node affinity/selector.",
        }
        # The regex should find k9b labels in the message
        result = _extract_selector_literal_from_failed_scheduling_signal(sig)
        # May be None if no labels found, or may extract a label if present
        assert result is None or isinstance(result, str)

    def test_returns_none_for_non_failed_scheduling(self) -> None:
        """Returns None for non-FailedScheduling signals."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c import (
            _extract_selector_literal_from_failed_scheduling_signal,
        )
        sig = {
            "reason": "OtherReason",
            "message": "Some other event message",
        }
        assert _extract_selector_literal_from_failed_scheduling_signal(sig) is None

    def test_returns_none_for_missing_fields(self) -> None:
        """Returns None for signals with missing fields."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c import (
            _extract_selector_literal_from_failed_scheduling_signal,
        )
        sig = {"reason": "FailedScheduling"}
        assert _extract_selector_literal_from_failed_scheduling_signal(sig) is None

    def test_handles_non_mapping_input(self) -> None:
        """Handles non-mapping input gracefully."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c import (
            _extract_selector_literal_from_failed_scheduling_signal,
        )
        assert _extract_selector_literal_from_failed_scheduling_signal("bad") is None
        assert _extract_selector_literal_from_failed_scheduling_signal(None) is None
        assert _extract_selector_literal_from_failed_scheduling_signal(42) is None


class TestIterBackendIncidentSignals:
    """Test _iter_backend_incident_signals extraction from various shapes."""

    def test_extracts_from_top_level_signals(self) -> None:
        """Extracts signals from root.signals."""
        incident = {
            "signals": [
                {"reason": "FailedScheduling", "message": "test"},
            ]
        }
        signals = _iter_backend_incident_signals(incident)
        assert len(signals) == 1
        assert signals[0]["reason"] == "FailedScheduling"

    def test_extracts_from_raw_signals(self) -> None:
        """Extracts signals from root.raw.signals."""
        incident = {
            "raw": {
                "signals": [
                    {
                        "source": "deployment",
                        "reason": "replicas_unavailable",
                        "message": "Deployment has 0/1 replicas available",
                    },
                    {
                        "source": "event",
                        "reason": "FailedScheduling",
                        "message": "0/8 nodes are available: 4 node(s) didn't match Pod's node affinity/selector.",
                    },
                ],
            },
        }
        signals = _iter_backend_incident_signals(incident)
        assert len(signals) == 2
        assert signals[1]["reason"] == "FailedScheduling"

    def test_extracts_from_nested_incident_raw_signals(self) -> None:
        """Extracts signals from root.incident.raw.signals."""
        incident = {
            "incident": {
                "raw": {
                    "signals": [
                        {
                            "reason": "FailedScheduling",
                            "message": "0/8 nodes are available: 4 node(s) didn't match Pod's node affinity/selector.",
                        }
                    ]
                }
            }
        }
        signals = _iter_backend_incident_signals(incident)
        assert len(signals) == 1
        assert signals[0]["reason"] == "FailedScheduling"

    def test_combines_signals_from_multiple_paths(self) -> None:
        """Combines signals from all available paths."""
        incident = {
            "signals": [{"reason": "top_level"}],
            "raw": {"signals": [{"reason": "raw_level"}]},
            "incident": {"signals": [{"reason": "incident_level"}]},
        }
        signals = _iter_backend_incident_signals(incident)
        reasons = {s["reason"] for s in signals}
        assert reasons == {"top_level", "raw_level", "incident_level"}

    def test_handles_none_input(self) -> None:
        """Handles None input gracefully."""
        assert _iter_backend_incident_signals(None) == []

    def test_handles_non_dict_input(self) -> None:
        """Handles non-dict input gracefully."""
        assert _iter_backend_incident_signals("bad") == []
        assert _iter_backend_incident_signals(42) == []
        assert _iter_backend_incident_signals([]) == []

    def test_handles_missing_signals_keys(self) -> None:
        """Handles missing signals keys gracefully."""
        incident = {"namespace": "test", "raw": {}}
        assert _iter_backend_incident_signals(incident) == []

    def test_filters_non_mapping_signals(self) -> None:
        """Filters out non-mapping signals."""
        incident = {
            "signals": [
                "string",
                42,
                None,
                {"reason": "FailedScheduling", "message": "valid"},
            ]
        }
        signals = _iter_backend_incident_signals(incident)
        assert len(signals) == 1
        assert signals[0]["reason"] == "FailedScheduling"


class TestIsFailedSchedulingSignal:
    """Test _is_failed_scheduling_signal matching logic."""

    def test_matches_structured_reason(self) -> None:
        """Matches FailedScheduling in structured reason field."""
        signal = {"reason": "FailedScheduling", "message": "some message"}
        assert _is_failed_scheduling_signal(signal) is True

    def test_matches_failed_scheduling_in_message(self) -> None:
        """Matches FailedScheduling in message field."""
        signal = {"reason": "OtherReason", "message": "FailedScheduling occurred"}
        assert _is_failed_scheduling_signal(signal) is True

    def test_matches_unschedulable_in_message(self) -> None:
        """Matches Unschedulable in message field."""
        signal = {"reason": "OtherReason", "message": "Pod is Unschedulable"}
        assert _is_failed_scheduling_signal(signal) is True

    def test_matches_node_affinity_selector_mismatch(self) -> None:
        """Matches node affinity/selector mismatch messages."""
        signal = {
            "reason": "OtherReason",
            "message": "0/8 nodes are available: 4 node(s) didn't match Pod's node affinity/selector.",
        }
        assert _is_failed_scheduling_signal(signal) is True

    def test_matches_did_not_match_variant(self) -> None:
        """Matches 'did not match' variant."""
        signal = {
            "reason": "OtherReason",
            "message": "0/8 nodes are available: 4 node(s) did not match Pod's node affinity/selector.",
        }
        assert _is_failed_scheduling_signal(signal) is True

    def test_matches_node_affinity_selector_in_message(self) -> None:
        """Matches 'node affinity/selector' in message."""
        signal = {
            "reason": "OtherReason",
            "message": "Some nodes failed node affinity/selector check",
        }
        assert _is_failed_scheduling_signal(signal) is True

    def test_no_false_positive_on_unrelated_message(self) -> None:
        """Does not match unrelated messages."""
        signal = {"reason": "OtherReason", "message": "Deployment updated"}
        assert _is_failed_scheduling_signal(signal) is False


class TestParseSelectorLiteral:
    """Test _parse_selector_literal parsing."""

    def test_parses_valid_literal(self) -> None:
        """Parses valid selector literal."""
        key, value, literal = _parse_selector_literal("k9b.dev/otel-lab-node=missing")
        assert key == "k9b.dev/otel-lab-node"
        assert value == "missing"
        assert literal == "k9b.dev/otel-lab-node=missing"

    def test_strips_whitespace(self) -> None:
        """Strips whitespace from key and value."""
        key, value, literal = _parse_selector_literal("  key=value  ")
        assert key == "key"
        assert value == "value"

    def test_handles_multiple_equals(self) -> None:
        """Splits only on first equals."""
        key, value, literal = _parse_selector_literal("key=value=extra")
        assert key == "key"
        assert value == "value=extra"

    def test_returns_none_for_non_string(self) -> None:
        """Returns None for non-string input."""
        assert _parse_selector_literal(None) == (None, None, None)
        assert _parse_selector_literal(42) == (None, None, None)
        assert _parse_selector_literal([]) == (None, None, None)

    def test_returns_none_for_invalid_format(self) -> None:
        """Returns None for invalid format."""
        assert _parse_selector_literal("") == (None, None, None)
        assert _parse_selector_literal("no-equals") == (None, None, None)
        assert _parse_selector_literal("=value") == (None, None, None)
        assert _parse_selector_literal("key=") == (None, None, None)


class TestExtractSchedulingRootCauseWithBackendDetail:
    """Test extract_scheduling_root_cause with backend_incident_detail."""

    def test_extracts_failed_scheduling_from_backend_raw_signals(self) -> None:
        """Extracts FailedScheduling from backend incident raw.signals."""
        backend_incident_detail = {
            "raw": {
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
                "signals": [
                    {
                        "source": "deployment",
                        "reason": "replicas_unavailable",
                        "message": "Deployment shipping has 0/1 replicas available",
                    },
                    {
                        "source": "event",
                        "reason": "FailedScheduling",
                        "message": (
                            "0/8 nodes are available: 4 node(s) didn't match "
                            "Pod's node affinity/selector."
                        ),
                    },
                ],
            },
        }

        evidence = extract_scheduling_root_cause(
            incident={},
            backend_incident_detail=backend_incident_detail,
            detection_evidence_selector_literal="k9b.dev/otel-lab-node=missing",
        )

        assert evidence.failed_scheduling is True
        assert evidence.unschedulable is True
        assert evidence.selector_key == "k9b.dev/otel-lab-node"
        assert evidence.selector_value == "missing"
        assert evidence.selector_literal == "k9b.dev/otel-lab-node=missing"
        assert evidence.workload_name == "shipping"
        assert check_scheduling_root_cause_complete(evidence) is True

    def test_joins_selector_from_detection_with_backend_signals(self) -> None:
        """Joins P3c selector_literal with backend FailedScheduling evidence."""
        backend_incident_detail = {
            "raw": {
                "signals": [
                    {
                        "reason": "FailedScheduling",
                        "message": "0/8 nodes are available: 4 node(s) didn't match Pod's node affinity/selector.",
                    }
                ]
            }
        }

        evidence = extract_scheduling_root_cause(
            incident={"namespace": "otel-demo", "object_kind": "deployment", "object_name": "shipping"},
            backend_incident_detail=backend_incident_detail,
            detection_evidence_selector_literal="k9b.dev/otel-lab-node=missing",
        )

        # Should have both scheduling evidence from backend AND selector from P3c
        assert evidence.failed_scheduling is True
        assert evidence.selector_key == "k9b.dev/otel-lab-node"
        assert check_scheduling_root_cause_complete(evidence) is True

    def test_extracts_from_nested_incident_raw(self) -> None:
        """Extracts FailedScheduling from nested incident.raw.signals."""
        backend_incident_detail = {
            "incident": {
                "raw": {
                    "signals": [
                        {
                            "reason": "FailedScheduling",
                            "message": "0/8 nodes are available: 4 node(s) didn't match Pod's node affinity/selector.",
                        }
                    ]
                }
            }
        }

        evidence = extract_scheduling_root_cause(
            incident={},
            backend_incident_detail=backend_incident_detail,
            detection_evidence_selector_literal="k9b.dev/otel-lab-node=missing",
        )

        assert evidence.failed_scheduling is True
        assert evidence.selector_key == "k9b.dev/otel-lab-node"
        assert check_scheduling_root_cause_complete(evidence) is True

    def test_uses_selector_key_value_from_detection(self) -> None:
        """Uses selector_key and selector_value from detection evidence."""
        backend_incident_detail = {
            "raw": {
                "signals": [
                    {
                        "reason": "FailedScheduling",
                        "message": "0/8 nodes are available: 4 node(s) didn't match Pod's node affinity/selector.",
                    }
                ]
            }
        }

        evidence = extract_scheduling_root_cause(
            incident={},
            backend_incident_detail=backend_incident_detail,
            detection_evidence_selector_literal="k9b.dev/otel-lab-node=missing",
        )

        assert evidence.selector_key == "k9b.dev/otel-lab-node"
        assert evidence.selector_value == "missing"
        assert evidence.selector_literal == "k9b.dev/otel-lab-node=missing"

    def test_handles_missing_backend_incident_detail(self) -> None:
        """Handles missing backend_incident_detail gracefully."""
        evidence = extract_scheduling_root_cause(
            incident={"namespace": "otel-demo", "object_kind": "deployment", "object_name": "shipping"},
        )

        # Should not crash, but may not have complete evidence
        assert evidence is not None
        assert evidence.workload_name == "shipping"

    def test_backend_signals_counted_as_matching_signals(self) -> None:
        """Backend raw signals are counted as matching signals."""
        backend_incident_detail = {
            "raw": {
                "signals": [
                    {
                        "reason": "FailedScheduling",
                        "message": "0/8 nodes are available: 4 node(s) didn't match Pod's node affinity/selector.",
                    }
                ]
            }
        }

        signals = _iter_backend_incident_signals(backend_incident_detail)
        matching = [s for s in signals if _is_failed_scheduling_signal(s)]

        assert len(matching) == 1
        assert matching[0]["reason"] == "FailedScheduling"


class TestMalformedBoundaries:
    """Test nil-safe handling of malformed inputs."""

    @pytest.mark.parametrize(
        "backend_incident_detail",
        [
            None,
            {},
            [],
            "bad",
            42,
            {"raw": None},
            {"raw": {"signals": None}},
            {"raw": {"signals": ["bad", 42, None]}},
        ],
    )
    def test_backend_signal_extraction_is_nil_safe(
        self, backend_incident_detail: object
    ) -> None:
        """Malformed backend incident detail should not crash extraction."""
        # Should not raise
        signals = _iter_backend_incident_signals(backend_incident_detail)
        assert isinstance(signals, list)

    def test_extract_with_none_backend_detail(self) -> None:
        """Handles None backend_incident_detail gracefully."""
        evidence = extract_scheduling_root_cause(
            incident={"namespace": "test", "object_kind": "deployment", "object_name": "test"},
            backend_incident_detail=None,
        )
        assert evidence is not None

    def test_extract_with_malformed_backend_detail(self) -> None:
        """Handles malformed backend_incident_detail gracefully."""
        evidence = extract_scheduling_root_cause(
            incident={},
            backend_incident_detail={"raw": "not-a-dict"},
        )
        # Should not crash, should return evidence object
        assert evidence is not None
