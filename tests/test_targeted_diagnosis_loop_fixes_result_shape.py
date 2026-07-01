"""Regression tests for targeted diagnosis result shape fix.

Tests the _extract_incident_result_from_collector function which handles
the P4c bug where AutoLoopIncidentResult was incorrectly treated as having
an incident_results attribute (which only AutoLoopCollectorResult has).

Bug: The handler called:
    result.incident_results.get(incident_id)
But collect_automatic_diagnosis_evidence() returns AutoLoopIncidentResult directly,
which does NOT have incident_results. This caused AttributeError at runtime.

Fix: _extract_incident_result_from_collector() uses hasattr() to check.
"""

from __future__ import annotations


class TestTargetedDiagnosisResultShape:
    """Tests for handler result shape handling."""

    def test_result_shape_contract(self) -> None:
        """Regression test: AutoLoopIncidentResult must NOT access .incident_results.

        The P4c bug was that the handler called:
            result.incident_results.get(incident_id)

        But collect_automatic_diagnosis_evidence() returns AutoLoopIncidentResult directly,
        which does NOT have incident_results. This caused AttributeError at runtime.

        The fix is _extract_incident_result_from_collector() which uses hasattr() to check.
        This test verifies the function correctly handles AutoLoopIncidentResult without
        crashing.
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
            AutoLoopIncidentResult,
        )
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _extract_incident_result_from_collector,
        )

        # Create a direct AutoLoopIncidentResult (not wrapped in collector result)
        incident_result = AutoLoopIncidentResult(
            incident_id="test-incident-789",
            eligible=True,
            eligibility_reason="",
            run_id="auto-test-incident-789-20240101",
            review_packet_name="auto-test-incident-789-0-diagnosis-review-packet.json",
            checks_requested=3,
            checks_run=3,
            checks_rejected=0,
        )

        # The bug would crash here with: AttributeError: 'AutoLoopIncidentResult' has no 'incident_results'
        # The fix handles this gracefully via hasattr() check
        extracted = _extract_incident_result_from_collector(
            result=incident_result,  # type: ignore - intentional: testing both types
            incident_id="test-incident-789",
        )

        # Verify the result was returned correctly
        assert extracted is not None
        assert extracted.incident_id == "test-incident-789"
        assert extracted.review_packet_name == "auto-test-incident-789-0-diagnosis-review-packet.json"
