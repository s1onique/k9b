"""Unit tests for incident_scheduling_root_cause module.

Tests the deterministic extraction of scheduling root-cause evidence
for P4c diagnosis validation.
"""

from __future__ import annotations

from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
    SchedulingRootCauseEvidence,
    check_scheduling_root_cause_complete,
    extract_scheduling_root_cause,
)


class TestSchedulingRootCauseEvidence:
    """Tests for SchedulingRootCauseEvidence dataclass."""

    def test_to_dict_returns_all_fields(self) -> None:
        """Verify to_dict() includes all evidence fields."""
        evidence = SchedulingRootCauseEvidence(
            namespace="otel-demo",
            workload_kind="Deployment",
            workload_name="shipping",
            selector_key="k9b.dev/otel-lab-node",
            selector_value="missing",
            selector_literal="k9b.dev/otel-lab-node=missing",
            failed_scheduling=True,
            unschedulable=True,
            scheduler_message="0/1 nodes are available: 1 node(s) didn't match Pod node selector.",
            matching_nodes=(),
            root_cause_summary="Deployment/shipping FailedScheduling Unschedulable nodeSelector k9b.dev/otel-lab-node=missing no matching node",
        )

        d = evidence.to_dict()
        assert d["namespace"] == "otel-demo"
        assert d["workload_kind"] == "Deployment"
        assert d["workload_name"] == "shipping"
        assert d["selector_key"] == "k9b.dev/otel-lab-node"
        assert d["selector_value"] == "missing"
        assert d["selector_literal"] == "k9b.dev/otel-lab-node=missing"
        assert d["failed_scheduling"] is True
        assert d["unschedulable"] is True
        assert d["scheduler_message"] is not None
        assert "no matching node" in d["root_cause_summary"]


class TestExtractSchedulingRootCause:
    """Tests for extract_scheduling_root_cause function."""

    def test_extracts_from_incident_with_scheduling_signals(self) -> None:
        """Verify extraction finds scheduling evidence in signals with explicit lab marker."""
        incident = {
            "namespace": "otel-demo",
            "object_kind": "deployment",
            "object_name": "shipping",
            "signals": [
                {"reason": "FailedScheduling", "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector (k9b.dev/otel-lab-node)."},
                {"reason": "PodPending", "message": "Pod is pending scheduling"},
            ],
        }

        evidence = extract_scheduling_root_cause(incident)

        assert evidence.namespace == "otel-demo"
        assert evidence.workload_kind == "Deployment"
        assert evidence.workload_name == "shipping"
        assert evidence.failed_scheduling is True
        assert evidence.selector_key == "k9b.dev/otel-lab-node"
        assert evidence.selector_value == "missing"
        assert evidence.selector_literal == "k9b.dev/otel-lab-node=missing"

    def test_extracts_from_case_file_events(self) -> None:
        """Verify extraction finds scheduling evidence in case file events with explicit lab marker."""
        incident = {
            "namespace": "otel-demo",
            "object_kind": "deployment",
            "object_name": "shipping",
            "signals": [],
        }
        case_file = {
            "events": [
                {
                    "reason": "FailedScheduling",
                    "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector (k9b.dev/otel-lab-node).",
                },
            ],
        }

        evidence = extract_scheduling_root_cause(incident, case_file)

        assert evidence.failed_scheduling is True
        assert evidence.scheduler_message is not None
        assert evidence.selector_key == "k9b.dev/otel-lab-node"

    def test_uses_defaults_when_incident_missing(self) -> None:
        """Verify defaults are used when incident has minimal data."""
        incident: dict = {}

        evidence = extract_scheduling_root_cause(incident)

        assert evidence.namespace == "otel-demo"
        assert evidence.workload_name == "shipping"
        assert evidence.workload_kind == "Deployment"

    def test_root_cause_summary_contains_required_p4c_terms(self) -> None:
        """Verify root_cause_summary contains all terms needed for P4c validation."""
        incident = {
            "namespace": "otel-demo",
            "object_kind": "deployment",
            "object_name": "shipping",
            "signals": [
                {"reason": "FailedScheduling", "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector (k9b.dev/otel-lab-node)."},
            ],
        }

        evidence = extract_scheduling_root_cause(incident)

        summary = evidence.root_cause_summary.lower()
        # Required P4c terms
        assert "shipping" in summary
        assert "nodeselector" in summary
        assert "k9b.dev/otel-lab-node" in summary
        # Scheduling failure indicator
        assert evidence.failed_scheduling is True

    def test_does_not_mutate_input_incident(self) -> None:
        """Verify the function doesn't mutate the input incident dict."""
        incident = {
            "namespace": "otel-demo",
            "object_kind": "deployment",
            "object_name": "shipping",
            "signals": [],
        }
        original_keys = set(incident.keys())

        extract_scheduling_root_cause(incident)

        assert set(incident.keys()) == original_keys


class TestCheckSchedulingRootCauseComplete:
    """Tests for check_scheduling_root_cause_complete function."""

    def test_complete_evidence_passes(self) -> None:
        """Verify complete evidence satisfies P4c requirements."""
        evidence = SchedulingRootCauseEvidence(
            workload_name="shipping",
            selector_key="k9b.dev/otel-lab-node",
            failed_scheduling=True,
            root_cause_summary="Deployment/shipping FailedScheduling nodeSelector k9b.dev/otel-lab-node=missing no matching node",
        )

        assert check_scheduling_root_cause_complete(evidence) is True


class TestIncidentObjectBoundary:
    """Tests for dict/object boundary handling in extract_scheduling_root_cause."""

    def test_accepts_object_with_attributes(self) -> None:
        """Verify extract_scheduling_root_cause accepts object with attributes."""
        # Simulate an Incident object with attributes
        class MockIncident:
            def __init__(self) -> None:
                self.namespace = "otel-demo"
                self.object_kind = "deployment"
                self.object_name = "shipping"
                self.signals = [
                    {"reason": "FailedScheduling", "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector (k9b.dev/otel-lab-node)."},
                ]

        incident = MockIncident()

        evidence = extract_scheduling_root_cause(incident)

        assert evidence.namespace == "otel-demo"
        assert evidence.workload_kind == "Deployment"
        assert evidence.workload_name == "shipping"
        assert evidence.failed_scheduling is True
        assert "k9b.dev/otel-lab-node" in evidence.root_cause_summary

    def test_generic_scheduling_does_not_infer_lab_selector(self) -> None:
        """Verify generic scheduling failure does NOT infer lab-specific selector.
        
        This prevents false positives where a generic scheduling failure
        is promoted to the exact P4c lab root cause.
        """
        incident = {
            "namespace": "default",
            "object_kind": "deployment",
            "object_name": "api",
            "signals": [
                {"reason": "FailedScheduling", "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector."},
            ],
        }

        evidence = extract_scheduling_root_cause(incident)

        # Should have scheduling failure indicator
        assert evidence.failed_scheduling is True
        # But should NOT infer the lab-specific selector
        assert evidence.selector_key is None
        assert "k9b.dev/otel-lab-node" not in (evidence.root_cause_summary or "")

    def test_non_shipping_workload_does_not_infer_lab_selector(self) -> None:
        """Verify non-shipping workload does NOT get lab-specific selector.
        
        Only known P4c lab scenarios (shipping in otel-demo) should get
        the lab selector inference.
        """
        incident = {
            "namespace": "otel-demo",
            "object_kind": "deployment",
            "object_name": "api",
            "signals": [
                {"reason": "FailedScheduling", "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector."},
            ],
        }

        evidence = extract_scheduling_root_cause(incident)

        # Should have scheduling failure
        assert evidence.failed_scheduling is True
        # But should NOT infer the lab selector for non-shipping workloads
        assert evidence.selector_key is None

    def test_shipping_with_explicit_lab_marker_gets_selector(self) -> None:
        """Verify shipping in otel-demo with explicit lab marker gets selector."""
        incident = {
            "namespace": "otel-demo",
            "object_kind": "deployment",
            "object_name": "shipping",
            "signals": [
                {"reason": "FailedScheduling", "message": "k9b.dev/otel-lab-node=missing: 1 node(s) didn't match Pod node selector."},
            ],
        }

        evidence = extract_scheduling_root_cause(incident)

        # Should have scheduling failure AND lab selector
        assert evidence.failed_scheduling is True
        assert evidence.selector_key == "k9b.dev/otel-lab-node"
        assert evidence.selector_value == "missing"

    def test_empty_summary_fails(self) -> None:
        """Verify empty root_cause_summary fails validation."""
        evidence = SchedulingRootCauseEvidence(
            workload_name="shipping",
            selector_key="k9b.dev/otel-lab-node",
            failed_scheduling=True,
            root_cause_summary="",
        )

        assert check_scheduling_root_cause_complete(evidence) is False

    def test_missing_workload_name_fails(self) -> None:
        """Verify missing workload name fails validation."""
        evidence = SchedulingRootCauseEvidence(
            workload_name="api",
            selector_key="k9b.dev/otel-lab-node",
            failed_scheduling=True,
            root_cause_summary="Deployment/api nodeSelector k9b.dev/otel-lab-node=missing",
        )

        assert check_scheduling_root_cause_complete(evidence) is False

    def test_missing_selector_key_fails(self) -> None:
        """Verify missing selector key fails validation."""
        evidence = SchedulingRootCauseEvidence(
            workload_name="shipping",
            selector_key=None,
            failed_scheduling=True,
            root_cause_summary="Deployment/shipping scheduling failure",
        )

        assert check_scheduling_root_cause_complete(evidence) is False

    def test_missing_scheduling_failure_indicator_fails(self) -> None:
        """Verify missing scheduling failure indicator fails validation."""
        evidence = SchedulingRootCauseEvidence(
            workload_name="shipping",
            selector_key="k9b.dev/otel-lab-node",
            failed_scheduling=False,
            unschedulable=False,
            root_cause_summary="Deployment/shipping nodeSelector k9b.dev/otel-lab-node=missing",
        )

        assert check_scheduling_root_cause_complete(evidence) is False

    def test_unschedulable_indicator_accepted(self) -> None:
        """Verify unschedulable state is accepted as scheduling failure."""
        evidence = SchedulingRootCauseEvidence(
            workload_name="shipping",
            selector_key="k9b.dev/otel-lab-node",
            failed_scheduling=False,
            unschedulable=True,
            root_cause_summary="Deployment/shipping Unschedulable nodeSelector k9b.dev/otel-lab-node=missing",
        )

        assert check_scheduling_root_cause_complete(evidence) is True

    def test_missing_selector_value_fails(self) -> None:
        """Verify missing selector value fails validation."""
        evidence = SchedulingRootCauseEvidence(
            workload_name="shipping",
            selector_key="k9b.dev/otel-lab-node",
            selector_value=None,
            failed_scheduling=True,
            root_cause_summary="Deployment/shipping FailedScheduling nodeSelector k9b.dev/otel-lab-node no matching node",
        )

        assert check_scheduling_root_cause_complete(evidence) is False

    def test_wrong_selector_value_fails(self) -> None:
        """Verify wrong selector value fails validation."""
        evidence = SchedulingRootCauseEvidence(
            workload_name="shipping",
            selector_key="k9b.dev/otel-lab-node",
            selector_value="present",
            failed_scheduling=True,
            root_cause_summary="Deployment/shipping FailedScheduling nodeSelector k9b.dev/otel-lab-node=present no matching node",
        )

        assert check_scheduling_root_cause_complete(evidence) is False
