"""ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 parser tests.

This module contains the strict response/request parsing matrix tests for
the incident current-run promotion ACT.

Test coverage (8 strict parser negative cases):
1. Empty string in scanned IDs is rejected.
2. Whitespace-only in opened IDs is rejected.
3. Whitespace in actionable IDs is rejected.
4. Oversized unsafe ID is rejected.
5. Unsafe character in IDs is rejected.
6. Malformed failure signalId is rejected.
7. Malformed runId is rejected.
8. Overlong source identity is rejected.
9. Minimal payload with only required fields succeeds.

ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01
"""

from __future__ import annotations

import pytest


class TestResponseParserRejectsMalformedIds:
    """``IncidentPromotionResult.from_wire_dict`` must reject malformed IDs.

    The R3 closure claim that every wire ID array is strictly
    validated requires these negative proofs. Empty, whitespace,
    oversized, and unsafe identifiers must all fail closed rather
    than slip through into a typed result.
    """

    _PAYLOAD_BASE: dict[str, object] = {
        "runId": "auto-run-20260101",
        "sourceIdentity": "http://alertmanager:9093",
    }

    def test_empty_string_in_scanned_ids_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload: dict[str, object] = dict(self._PAYLOAD_BASE)
        payload["scannedSignalIds"] = [""]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_whitespace_only_in_opened_ids_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["openedIncidentIds"] = ["\n"]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_whitespace_in_actionable_ids_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["openedIncidentIds"] = ["id-1"]
        payload["materiallyChangedIncidentIds"] = []
        payload["actionableIncidentIds"] = ["\n"]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_oversized_unsafe_id_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            MAX_ID_LENGTH,
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["scannedSignalIds"] = ["a" * (MAX_ID_LENGTH + 1)]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_unsafe_character_in_ids_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["openedIncidentIds"] = ["bad id with spaces"]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_malformed_failure_signal_id_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["failures"] = [
            {"signalId": "\n", "reasonCode": "x"}
        ]
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_malformed_run_id_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["runId"] = ""  # empty
        with pytest.raises(PromotionScopeError):
            IncidentPromotionResult.from_wire_dict(payload)

    def test_minimal_payload_with_only_required_fields_succeeds(self) -> None:
        """R3.4: payload with only ``runId`` + ``sourceIdentity`` parses.

        Omitted optional arrays (``scannedSignalIds``, ``skippedSignalIds``,
        the four incident ID lists, ``failures``, ``actionableIncidentIds``)
        MUST default to empty tuples; the typed result reports all
        counts at zero and an empty failure list. The previous bug
        used ``payload.get("failures", ()) or ()`` so a missing
        ``failures`` field was rejected with ``failures must be an
        array`` even though every other optional array was correctly
        defaulted to ``()``.
        """
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
        )

        payload: dict[str, object] = {
            "runId": "auto-run-20260101",
            "sourceIdentity": "http://alertmanager:9093",
        }
        result = IncidentPromotionResult.from_wire_dict(payload)
        # Identity and run-id are propagated verbatim.
        assert str(result.run_id) == "auto-run-20260101"
        assert result.source_identity == "http://alertmanager:9093"
        # All optional arrays defaulted to empty tuples.
        assert list(result.scanned_signal_ids) == []
        assert list(result.skipped_signal_ids) == []
        assert list(result.opened_incident_ids) == []
        assert list(result.materially_changed_incident_ids) == []
        assert list(result.observation_refreshed_incident_ids) == []
        assert list(result.unchanged_incident_ids) == []
        assert list(result.failures) == []
        # All counts at zero.
        assert result.scanned_signal_count == 0
        assert result.opened_incident_count == 0
        assert result.materially_changed_incident_count == 0
        assert result.observation_refreshed_incident_count == 0
        assert result.unchanged_incident_count == 0
        # The actionable projection is the stable unique union of
        # opened + materially-changed; with both empty, it is empty.
        assert list(result.actionable_incident_ids) == []

    def test_overlong_source_identity_is_rejected(self) -> None:
        from k8s_diag_agent.incident_alert_promotion_contract import (
            MAX_SOURCE_IDENTITY_LENGTH,
            IncidentPromotionResult,
            PromotionScopeError,
        )

        payload = dict(self._PAYLOAD_BASE)
        payload["sourceIdentity"] = "a" * (MAX_SOURCE_IDENTITY_LENGTH + 1)
        with pytest.raises(PromotionScopeError):  # noqa: E501
            IncidentPromotionResult.from_wire_dict(payload)
