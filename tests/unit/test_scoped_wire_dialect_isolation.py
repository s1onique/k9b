"""Dialect isolation tests: scoped and legacy dialects must not cross.

ACT-K9B-HULK-PROMOTION-SCOPED-WIRE-DIALECT-CONVERGENCE01.

Proves:

* a valid camelCase scoped payload is accepted by
  :meth:`IncidentPromotionResult.from_wire_dict`;
* a valid camelCase scoped payload is rejected by
  :meth:`PromotionHttpWireResult.from_payload` (the legacy
  snake_case decoder);
* a valid legacy ``PromotionResponse`` payload is accepted by
  :meth:`PromotionHttpWireResult.from_payload`;
* a valid legacy ``PromotionResponse`` payload is rejected by
  :meth:`IncidentPromotionResult.from_wire_dict` (the scoped
  camelCase decoder);
* the camelCase scoped payload is never routed through the
  legacy ``_coerce_promotion_response`` helper.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.promotion_http_wire_decode import (
    PromotionHttpWireResult,
)
from k8s_diag_agent.collect.promotion_http_wire_types import (
    PromotionHttpWireValidationError,
)
from k8s_diag_agent.incident_alert_promotion_contract import (
    IncidentPromotionResult,
    PromotionScopeError,
)
from k8s_diag_agent.ui.server_incident_internal_models import (
    PromotionResponse,
)


def _scoped_payload() -> dict[str, Any]:
    """Build a valid camelCase scoped response payload.

    Mirrors the wire format emitted by
    :meth:`IncidentPromotionResult.to_wire_dict` for the canonical
    producer of the active scoped endpoint
    ``/api/internal/incidents/promote-alert-signals``.
    """
    return {
        "runId": "run-001",
        "sourceIdentity": "source-A",
        "scannedSignalIds": ["sig-A", "sig-B"],
        "openedIncidentIds": ["inc-001"],
        "materiallyChangedIncidentIds": [],
        "observationRefreshedIncidentIds": ["inc-002"],
        "unchangedIncidentIds": [],
        "skippedSignalIds": [],
        "failures": [],
        "actionableIncidentIds": ["inc-001"],
    }


def _legacy_payload() -> dict[str, Any]:
    """Build a valid snake_case legacy ``PromotionResponse`` payload.

    Mirrors the wire format emitted by the legacy
    ``/api/internal/incidents/promote-candidates`` endpoint.
    """
    return {
        "ok": True,
        "scanned": 1,
        "firing": 1,
        "opened_incidents": 1,
        "updated_incidents": 0,
        "skipped_duplicates": 0,
        "errors": 0,
        "error_messages": [],
        "opened_incident_ids": ["canonical-inc-001"],
        "updated_incident_ids": [],
        "canonical_incident_ids": ["canonical-inc-001"],
        "promotion_records": [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "opened",
            }
        ],
        "unique_candidate_count": 1,
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
    }


class TestScopedPayloadAcceptedByScopedDecoder:
    def test_camelcase_payload_accepted_by_incident_promotion_result(self) -> None:
        payload = _scoped_payload()
        result = IncidentPromotionResult.from_wire_dict(payload)
        assert result.run_id == "run-001"
        assert result.source_identity == "source-A"
        assert result.actionable_incident_ids == ("inc-001",)


class TestScopedPayloadRejectedByLegacyDecoder:
    def test_camelcase_payload_rejected_by_promotion_http_wire_result(self) -> None:
        """Routing a valid camelCase scoped payload through the
        legacy snake_case decoder MUST fail closed: the legacy
        decoder requires ``ok``, ``scanned``, ``firing``, etc.,
        none of which appear on the scoped wire.
        """
        payload = _scoped_payload()
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        # The legacy decoder reports a missing required field;
        # the exact field name is an implementation detail but the
        # diagnostic must originate from the legacy validator.
        assert "missing required field" in str(exc_info.value)


class TestLegacyPayloadAcceptedByLegacyDecoder:
    def test_snake_case_payload_accepted_by_promotion_http_wire_result(self) -> None:
        """The legacy strict decoder accepts the strict snake_case
        payload (with ``canonical_incident_ids``).
        """
        payload = _legacy_payload()
        result = PromotionHttpWireResult.from_payload(payload)
        assert result.ok is True
        assert result.scanned == 1
        assert len(result.promotion_records) == 1

    def test_snake_case_payload_accepted_by_promotion_response_dataclass(self) -> None:
        """The legacy ``PromotionResponse`` dataclass accepts the
        basic legacy shape (no ``canonical_incident_ids``).
        """
        # ``PromotionResponse`` does not declare
        # ``canonical_incident_ids``; drop that key for the
        # legacy dataclass acceptance test.
        payload = {
            key: value
            for key, value in _legacy_payload().items()
            if key != "canonical_incident_ids"
        }
        typed = PromotionResponse(**payload)
        assert typed.ok is True
        assert typed.scanned == 1


class TestLegacyPayloadRejectedByScopedDecoder:
    def test_snake_case_payload_rejected_by_incident_promotion_result(self) -> None:
        """Routing a valid legacy ``PromotionResponse`` payload
        through the scoped camelCase decoder MUST fail closed:
        the scoped decoder accepts only the canonical
        ``runId`` / ``sourceIdentity`` / ``scannedSignalIds`` /
        ``openedIncidentIds`` ... keys; the legacy ``ok`` /
        ``scanned`` / ``promotion_records`` keys are unknown.
        """
        payload = _legacy_payload()
        with pytest.raises(PromotionScopeError) as exc_info:
            IncidentPromotionResult.from_wire_dict(payload)
        assert "unsupported" in str(exc_info.value).lower()


class TestScopedPayloadNeverRoutedThroughLegacyCoercion:
    def test_scoped_payload_rejected_by_legacy_coercion(self) -> None:
        """The legacy ``_coerce_promotion_response`` helper only
        accepts dict or ``PromotionResponse``; a valid camelCase
        scoped payload must NOT slip through it as a successful
        promotion. The helper constructs a ``PromotionResponse``
        and passes the dict through; if the dict has the camelCase
        keys (not the snake_case keys ``PromotionResponse``
        expects), the ``PromotionResponse(**value)`` constructor
        raises ``TypeError`` for the unknown kwargs.
        """
        from k8s_diag_agent.collect.incident_promotion_backend import (
            _coerce_promotion_response,
        )

        payload = _scoped_payload()
        # The helper accepts a dict, but the dict has camelCase
        # keys that ``PromotionResponse.__init__`` does not
        # accept. Constructing the dataclass fails with
        # ``TypeError`` for the unknown kwargs; this proves the
        # helper cannot silently accept a scoped payload.
        with pytest.raises(TypeError):
            _coerce_promotion_response(payload)


class TestScopingKeySetIsDisjoint:
    """The set of keys expected by each decoder is disjoint.

    Adding any new key to one side MUST NOT make the other side
    accept the same payload. This guards the future-proofing of
    the dialect split.
    """

    def test_scoped_keys_exclude_all_legacy_keys(self) -> None:
        scoped_payload = _scoped_payload()
        legacy_keys = set(_legacy_payload().keys())
        scoped_keys = set(scoped_payload.keys())
        # The two payload surfaces share zero keys.
        assert scoped_keys.isdisjoint(legacy_keys), (
            "scoped/legacy payload keys overlap; the dialect split "
            "must keep the two surfaces disjoint"
        )
