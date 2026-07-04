"""Regression fixture from failing OTel live lab log.

This test proves that extract_scheduling_root_cause() produces complete
scheduling evidence when:

1. backend_incident_detail.raw.signals contains three FailedScheduling entries
   from the forensic dump (the exact shape from the failing live lab)
2. selector literal comes from P3c evidence (k9b.dev/otel-lab-node=missing)
3. The result satisfies the P4c acceptance criteria:
   - matching_signals > 0
   - selector_literal == k9b.dev/otel-lab-node=missing
   - failed_scheduling == True
   - scheduling_evidence completeness == True

This is the PRIMARY regression test for the gap between ACT-local passing
P4c extraction tests and the live OTel demo lab still logging:
  matching_signals=0 / selector_literal=None

Hypothesis: The extractor implementation is already correct, but the live lab
is either running stale code/image or passing a different backend_incident_detail /
selector literal into extract_scheduling_root_cause() than the forensic dump shows.

This fixture tests the EXACT input shape from the failing live log to prove
the extractor handles it correctly.

Run with:
    python -m pytest tests/test_p4c_scheduling_evidence_failing_live_log.py -v
"""

from __future__ import annotations

from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
    check_scheduling_root_cause_complete,
    extract_scheduling_root_cause,
)


class TestP4cLiveLabFailingLogRegression:
    """Regression tests from the failing OTel live lab log.

    The failing live lab showed:
    - matching_signals=0
    - selector_literal=None
    - backend_incident_detail=present (from P3c extraction)

    This test uses the EXACT input shape from the forensic dump to prove
    the extractor handles it correctly.
    """

    def test_extracts_from_exact_failing_live_log_backend_shape(self) -> None:
        """Test extract_scheduling_root_cause with EXACT forensic dump backend shape.

        This is the exact backend_incident_detail shape from the failing live log.
        The forensic dump showed:
        - backend_incident_detail was present
        - raw.signals contained FailedScheduling events
        - But matching_signals=0 and selector_literal=None in the output

        This test proves the extractor handles this exact shape.
        """
        # EXACT shape from failing live log forensic dump
        backend_incident_detail = {
            "incident_id": "otel-demo-deployment-shipping-deployment_unavailable",
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
                            "0/1 nodes are available: 1 node(s) didn't match "
                            "Pod node selector (k9b.dev/otel-lab-node)."
                        ),
                    },
                    {
                        "source": "event",
                        "reason": "FailedScheduling",
                        "message": (
                            "0/1 nodes are available: 1 node(s) didn't match "
                            "Pod node affinity/selector (k9b.dev/otel-lab-node)."
                        ),
                    },
                    {
                        "source": "event",
                        "reason": "FailedScheduling",
                        "message": (
                            "0/1 nodes are available: 1 node(s) had taint, "
                            "that the pod didn't tolerate (k9b.dev/otel-lab-node)."
                        ),
                    },
                ],
            },
        }

        # P3c selector literal (from detection evidence)
        selector_literal = "k9b.dev/otel-lab-node=missing"

        # Run extraction
        evidence = extract_scheduling_root_cause(
            incident={},
            backend_incident_detail=backend_incident_detail,
            detection_evidence_selector_literal=selector_literal,
        )

        # ACCEPTANCE CRITERIA from task requirements:
        # matching_signals > 0
        # selector_literal == k9b.dev/otel-lab-node=missing
        # failed_scheduling == true
        # scheduling_evidence completeness == true

        # 1. selector_literal must equal k9b.dev/otel-lab-node=missing
        assert evidence.selector_literal == "k9b.dev/otel-lab-node=missing", (
            f"selector_literal must be k9b.dev/otel-lab-node=missing, got {evidence.selector_literal}"
        )

        # 2. failed_scheduling must be True
        assert evidence.failed_scheduling is True, (
            f"failed_scheduling must be True, got {evidence.failed_scheduling}"
        )

        # 3. selector_key and selector_value must be extracted
        assert evidence.selector_key == "k9b.dev/otel-lab-node", (
            f"selector_key must be k9b.dev/otel-lab-node, got {evidence.selector_key}"
        )
        assert evidence.selector_value == "missing", (
            f"selector_value must be missing, got {evidence.selector_value}"
        )

        # 4. scheduling_evidence completeness must be True
        assert check_scheduling_root_cause_complete(evidence) is True, (
            f"scheduling_evidence must be complete, got {evidence}"
        )

        # 5. root_cause_summary must contain required terms
        summary_lower = evidence.root_cause_summary.lower()
        assert "shipping" in summary_lower, (
            f"root_cause_summary must contain 'shipping', got {evidence.root_cause_summary}"
        )
        assert "k9b.dev/otel-lab-node" in summary_lower, (
            f"root_cause_summary must contain 'k9b.dev/otel-lab-node', got {evidence.root_cause_summary}"
        )

    def test_backend_signals_count_as_matching_signals(self) -> None:
        """Prove backend raw.signals FailedScheduling events are counted.

        The failing log showed matching_signals=0, suggesting the backend
        FailedScheduling events weren't being counted. This test proves
        they ARE counted as matching signals.
        """
        from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
            _is_failed_scheduling_signal,
            _iter_backend_incident_signals,
        )

        backend_incident_detail = {
            "raw": {
                "signals": [
                    {
                        "source": "deployment",
                        "reason": "replicas_unavailable",
                        "message": "Deployment shipping has 0/1 replicas available",
                    },
                    {
                        "source": "event",
                        "reason": "FailedScheduling",
                        "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector (k9b.dev/otel-lab-node).",
                    },
                ],
            },
        }

        # Extract signals from backend
        signals = _iter_backend_incident_signals(backend_incident_detail)
        assert len(signals) == 2, f"Expected 2 signals, got {len(signals)}"

        # Count matching signals
        matching_signals = [s for s in signals if _is_failed_scheduling_signal(s)]

        # ACCEPTANCE CRITERIA: matching_signals > 0
        assert len(matching_signals) > 0, (
            f"matching_signals must be > 0, got {len(matching_signals)}"
        )
        assert len(matching_signals) == 1, (
            f"Expected 1 FailedScheduling signal, got {len(matching_signals)}"
        )
        assert matching_signals[0]["reason"] == "FailedScheduling"

    def test_selector_from_detection_only_without_selector_in_message(self) -> None:
        """Test selector comes from detection_evidence when event has no selector key.

        Kubernetes scheduler event text may report generic affinity/selector mismatch
        without echoing custom key (e.g., "0/8 nodes are available: ... 4 node(s)
        didn't match Pod's node affinity/selector"). The selector must come from
        detection_evidence_selector_literal in this case.
        """
        # EXACT shape: generic affinity/selector mismatch with NO selector key in message
        backend_incident_detail = {
            "incident_id": "otel-demo-deployment-shipping-deployment_unavailable",
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
                        # Generic scheduler message WITHOUT k9b.dev/otel-lab-node
                        "message": (
                            "0/8 nodes are available: 4 node(s) didn't match "
                            "Pod's node affinity/selector."
                        ),
                    },
                ],
            },
        }

        # P3c selector literal (from detection evidence - the ONLY source)
        selector_literal = "k9b.dev/otel-lab-node=missing"

        # Run extraction
        evidence = extract_scheduling_root_cause(
            incident={},
            backend_incident_detail=backend_incident_detail,
            detection_evidence_selector_literal=selector_literal,
        )

        # Selector must come from detection_evidence_selector_literal
        # even though event message has no explicit selector key
        assert evidence.selector_literal == "k9b.dev/otel-lab-node=missing", (
            f"selector_literal must be k9b.dev/otel-lab-node=missing (from detection), got {evidence.selector_literal}"
        )
        assert evidence.selector_key == "k9b.dev/otel-lab-node", (
            f"selector_key must be k9b.dev/otel-lab-node (from detection), got {evidence.selector_key}"
        )
        assert evidence.selector_value == "missing", (
            f"selector_value must be missing, got {evidence.selector_value}"
        )

        # Scheduling evidence must still be found from backend
        assert evidence.failed_scheduling is True, (
            f"failed_scheduling must be True (from backend), got {evidence.failed_scheduling}"
        )

        # Completeness must pass with selector from detection
        assert check_scheduling_root_cause_complete(evidence) is True, (
            f"scheduling_evidence must be complete with detection selector, got {evidence}"
        )

    def test_complete_regression_scenario(self) -> None:
        """Full regression scenario from failing live log.

        This test simulates the EXACT call-site behavior from the failing
        live lab to prove the extractor produces the correct output.
        """
        # EXACT detection_evidence from P3c (simplified)
        detection_evidence = {
            "incident_id": "otel-demo-deployment-shipping-deployment_unavailable",
            "target_namespace": "otel-demo",
            "selector_key": "k9b.dev/otel-lab-node",
            "selector_value": "missing",
            "matching_signals": [
                {
                    "reason": "FailedScheduling",
                    "source": "event",
                    "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector (k9b.dev/otel-lab-node).",
                }
            ],
        }

        # Build selector_literal from detection_evidence (as P3c does)
        selector_literal = detection_evidence.get("selector_literal") or (
            f"{detection_evidence.get('selector_key')}={detection_evidence.get('selector_value')}"
            if detection_evidence.get("selector_key") and detection_evidence.get("selector_value")
            else None
        )
        assert selector_literal == "k9b.dev/otel-lab-node=missing"

        # EXACT backend_incident_detail shape from forensic dump
        backend_incident_detail = {
            "incident_id": "otel-demo-deployment-shipping-deployment_unavailable",
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
                        "message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector (k9b.dev/otel-lab-node).",
                    },
                    {
                        "source": "event",
                        "reason": "FailedScheduling",
                        "message": "0/1 nodes are available: 1 node(s) didn't match Pod node affinity/selector (k9b.dev/otel-lab-node).",
                    },
                    {
                        "source": "event",
                        "reason": "FailedScheduling",
                        "message": "0/1 nodes are available: 1 node(s) had taint, that the pod didn't tolerate (k9b.dev/otel-lab-node).",
                    },
                ],
            },
        }

        # EXACT incident_for_extraction from the phase.py code
        matching_signals_raw = detection_evidence.get("matching_signals", [])
        incident_for_extraction = {
            "namespace": detection_evidence.get("target_namespace", "otel-demo"),
            "object_kind": "deployment",
            "object_name": "shipping",
            "signals": matching_signals_raw,
        }

        # Call extract_scheduling_root_cause with EXACT parameters
        evidence = extract_scheduling_root_cause(
            incident=incident_for_extraction,
            case_file={"events": matching_signals_raw},
            backend_incident_detail=backend_incident_detail,
            detection_evidence_selector_literal=selector_literal,
        )

        # ACCEPTANCE CRITERIA from task requirements
        # matching_signals > 0
        from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
            _is_failed_scheduling_signal,
            _iter_backend_incident_signals,
        )

        all_signals = [
            *incident_for_extraction.get("signals", []),
            *_iter_backend_incident_signals(backend_incident_detail),
        ]
        matching_signals_count = len([s for s in all_signals if isinstance(s, dict) and _is_failed_scheduling_signal(s)])
        assert matching_signals_count > 0, f"matching_signals must be > 0, got {matching_signals_count}"

        # selector_literal == k9b.dev/otel-lab-node=missing
        assert evidence.selector_literal == "k9b.dev/otel-lab-node=missing", (
            f"selector_literal must be k9b.dev/otel-lab-node=missing, got {evidence.selector_literal}"
        )

        # failed_scheduling == true
        assert evidence.failed_scheduling is True, (
            f"failed_scheduling must be True, got {evidence.failed_scheduling}"
        )

        # scheduling_evidence completeness == true
        assert check_scheduling_root_cause_complete(evidence) is True, (
            f"scheduling_evidence must be complete, got evidence={evidence}"
        )


class TestP4cExtractorSignature:
    """Test that extract_scheduling_root_cause has the required signature.

    The live lab may be running stale code. This test proves the current
    signature has the required parameters.
    """

    def test_has_backend_incident_detail_parameter(self) -> None:
        """Verify extract_scheduling_root_cause has backend_incident_detail parameter."""
        import inspect

        sig = inspect.signature(extract_scheduling_root_cause)
        params = list(sig.parameters.keys())
        assert "backend_incident_detail" in params, (
            f"extract_scheduling_root_cause must have backend_incident_detail parameter, "
            f"got parameters: {params}"
        )

    def test_has_detection_evidence_selector_literal_parameter(self) -> None:
        """Verify extract_scheduling_root_cause has detection_evidence_selector_literal parameter."""
        import inspect

        sig = inspect.signature(extract_scheduling_root_cause)
        params = list(sig.parameters.keys())
        assert "detection_evidence_selector_literal" in params, (
            f"extract_scheduling_root_cause must have detection_evidence_selector_literal parameter, "
            f"got parameters: {params}"
        )

    def test_signature_includes_both_parameters(self) -> None:
        """Verify extract_scheduling_root_cause has both required parameters."""
        import inspect

        sig = inspect.signature(extract_scheduling_root_cause)
        params = set(sig.parameters.keys())
        required = {"backend_incident_detail", "detection_evidence_selector_literal"}
        missing = required - params
        assert not missing, (
            f"extract_scheduling_root_cause is missing required parameters: {missing}, "
            f"got parameters: {params}"
        )
