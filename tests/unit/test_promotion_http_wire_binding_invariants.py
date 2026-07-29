"""Request-binding invariants tests.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B-CORRECTION01.

Companion to :mod:`test_promotion_http_wire_binding` which
covers basic happy-path and failure-path binding tests.
This focused module covers the additional binding invariants
introduced by the correction:

* **Success-only binding** -- a backend rejection
  (``ok=False``) MUST enter a different typed disposition;
  completeness of records is irrelevant.
* **Request-counter binding** -- ``scanned``,
  ``unique_candidate_count``, and ``len(promotion_records)``
  MUST all equal ``len(requested_signal_ids)``. Negative tests
  exercise each counter at both production fixtures
  (29-signal and 34-signal).
* **Successful zero** -- every-request categorised with empty
  ``opened``/``updated`` still binds.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.promotion_http_wire_binding import (
    BoundPromotionHttpWireResult,
)
from k8s_diag_agent.collect.promotion_http_wire_decode import (
    PromotionHttpWireResult,
)
from k8s_diag_agent.collect.promotion_http_wire_types import (
    PromotionHttpWireValidationError,
)


class TestSuccessOnlyBinding:
    """The bound type is success-only.

    A backend rejection (``ok=False``) MUST enter a different
    typed disposition and is never permitted here -- even when
    the wire payload carries the complete set of categorisation
    records.
    """

    def test_ok_false_cannot_bind_even_with_complete_records(self) -> None:
        requested = ("sig-001",)
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "opened",
            }
        ]
        payload = {
            "ok": False,
            "scanned": 1,
            "firing": 1,
            "opened_incidents": 1,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 1,
            "error_messages": ["upstream rejected"],
            "opened_incident_ids": ["canonical-inc-001"],
            "updated_incident_ids": [],
            "canonical_incident_ids": ["canonical-inc-001"],
            "promotion_records": records,
            "unique_candidate_count": 1,
            "promotion_scan_scope": "internal_api_alert_signals:scoped",
            "incident_access_mode": "backend",
        }
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=requested,
            )
        assert "ok=True" in str(exc_info.value)

    def test_ok_false_cannot_bind_29_signal_fixture(self) -> None:
        """The 29-signal many-to-one fixture with ``ok=False`` MUST
        still not bind -- completeness of records is irrelevant.
        """
        requested = tuple(f"sig-{i:03d}" for i in range(29))
        records = [
            {
                "source_candidate_id": source_id,
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": (
                    "opened" if i == 0 else "observation_refreshed"
                ),
            }
            for i, source_id in enumerate(requested)
        ]
        payload = {
            "ok": False,
            "scanned": 29,
            "firing": 29,
            "opened_incidents": 1,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 1,
            "error_messages": ["backend rejected"],
            "opened_incident_ids": ["canonical-inc-001"],
            "updated_incident_ids": [],
            "canonical_incident_ids": ["canonical-inc-001"],
            "promotion_records": records,
            "unique_candidate_count": 29,
            "promotion_scan_scope": "internal_api_alert_signals:scoped",
            "incident_access_mode": "backend",
        }
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=requested,
            )
        assert "ok=True" in str(exc_info.value)

    def test_malformed_transport_response_cannot_bind(self) -> None:
        """A non-mapping transport response (or anything else that
        fails ``from_payload``) MUST NOT yield a bound instance.
        """
        with pytest.raises(PromotionHttpWireValidationError):
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(
                    "not a mapping"
                ),  # type: ignore[arg-type]
                requested_signal_ids=("sig-001",),
            )


class TestRequestCounterBinding:
    """The bound type is request-counter matched.

    ``scanned``, ``unique_candidate_count``, and
    ``len(promotion_records)`` MUST all equal
    ``len(requested_signal_ids)``. Negative tests for each
    counter at both production fixtures.
    """

    def _29_signal_payload(self) -> tuple[dict[str, Any], tuple[str, ...]]:
        requested = tuple(f"sig-{i:03d}" for i in range(29))
        records = [
            {
                "source_candidate_id": source_id,
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": (
                    "opened" if i == 0 else "observation_refreshed"
                ),
            }
            for i, source_id in enumerate(requested)
        ]
        payload = {
            "ok": True,
            "scanned": 29,
            "firing": 29,
            "opened_incidents": 1,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 0,
            "error_messages": [],
            "opened_incident_ids": ["canonical-inc-001"],
            "updated_incident_ids": [],
            "canonical_incident_ids": ["canonical-inc-001"],
            "promotion_records": records,
            "unique_candidate_count": 29,
            "promotion_scan_scope": "internal_api_alert_signals:scoped",
            "incident_access_mode": "backend",
        }
        return payload, requested

    def _34_signal_payload(self) -> tuple[dict[str, Any], tuple[str, ...]]:
        requested = tuple(f"sig-{i:03d}" for i in range(34))
        records = [
            {
                "source_candidate_id": source_id,
                "canonical_incident_id": (
                    "canonical-inc-001" if i < 2 else "canonical-inc-002"
                ),
                "promotion_outcome": (
                    "opened" if i < 3 else "observation_refreshed"
                ),
            }
            for i, source_id in enumerate(requested)
        ]
        payload = {
            "ok": True,
            "scanned": 34,
            "firing": 34,
            "opened_incidents": 2,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 0,
            "error_messages": [],
            "opened_incident_ids": [
                "canonical-inc-001",
                "canonical-inc-002",
            ],
            "updated_incident_ids": [],
            "canonical_incident_ids": [
                "canonical-inc-001",
                "canonical-inc-002",
            ],
            "promotion_records": records,
            "unique_candidate_count": 34,
            "promotion_scan_scope": "internal_api_alert_signals:scoped",
            "incident_access_mode": "backend",
        }
        return payload, requested

    # ---- 29-signal fixture ---------------------------------------

    def test_scanned_mismatch_29_signal(self) -> None:
        payload, requested = self._29_signal_payload()
        # Reduce scanned but keep firing <= scanned so the
        # decoder invariant ``firing <= scanned`` does not fire
        # first. We need to test the *binding* counter check.
        payload["scanned"] = 10
        payload["firing"] = 10
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=requested,
            )
        assert "scanned" in str(exc_info.value)
        assert "request count" in str(exc_info.value)

    def test_unique_candidate_count_mismatch_29_signal(self) -> None:
        payload, requested = self._29_signal_payload()
        payload["unique_candidate_count"] = 500  # wrong vs requested=29
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=requested,
            )
        assert "unique_candidate_count" in str(exc_info.value)

    def test_record_count_mismatch_29_signal(self) -> None:
        """Reduce the records list to a wrong count. The record-count
        check fires first; coverage is rejected after.
        """
        payload, requested = self._29_signal_payload()
        # Drop the last 27 records. The counter check fires first.
        payload["promotion_records"] = payload["promotion_records"][:2]
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=requested,
            )
        # Either the record-count check or the coverage check may
        # fire first depending on which invariant is evaluated
        # sooner; both reject the mismatch.
        assert (
            "promotion_records count" in str(exc_info.value)
            or "cover" in str(exc_info.value).lower()
        )

    # ---- 34-signal fixture ---------------------------------------

    def test_scanned_mismatch_34_signal(self) -> None:
        payload, requested = self._34_signal_payload()
        # Reduce scanned but keep firing <= scanned so the
        # decoder invariant ``firing <= scanned`` does not fire
        # first. We need to test the *binding* counter check.
        payload["scanned"] = 10
        payload["firing"] = 10
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=requested,
            )
        assert "scanned" in str(exc_info.value)
        assert "request count" in str(exc_info.value)

    def test_unique_candidate_count_mismatch_34_signal(self) -> None:
        payload, requested = self._34_signal_payload()
        payload["unique_candidate_count"] = 500  # wrong vs requested=34
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=requested,
            )
        assert "unique_candidate_count" in str(exc_info.value)

    def test_record_count_mismatch_34_signal(self) -> None:
        payload, requested = self._34_signal_payload()
        # Drop records beyond the first 3. Counter check fires first.
        payload["promotion_records"] = payload["promotion_records"][:3]
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=requested,
            )
        assert (
            "promotion_records count" in str(exc_info.value)
            or "cover" in str(exc_info.value).lower()
        )

    # ---- Positive baseline ---------------------------------------

    def test_29_signal_request_counter_match(self) -> None:
        payload, requested = self._29_signal_payload()
        bound = BoundPromotionHttpWireResult(
            result=PromotionHttpWireResult.from_payload(payload),
            requested_signal_ids=requested,
        )
        assert bound.result.scanned == 29
        assert bound.result.unique_candidate_count == 29
        assert len(bound.result.promotion_records) == 29
        assert bound.requested_signal_count == 29

    def test_34_signal_request_counter_match(self) -> None:
        payload, requested = self._34_signal_payload()
        bound = BoundPromotionHttpWireResult(
            result=PromotionHttpWireResult.from_payload(payload),
            requested_signal_ids=requested,
        )
        assert bound.result.scanned == 34
        assert bound.result.unique_candidate_count == 34
        assert len(bound.result.promotion_records) == 34
        assert bound.requested_signal_count == 34


class TestSuccessfulZeroBinding:
    """Successful zero (every request categorised; ``opened`` and
    ``updated`` empty) MUST still bind.
    """

    def test_successful_zero_binds_with_request_counter_match(self) -> None:
        requested = ("sig-001", "sig-002")
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-existing-A",
                "promotion_outcome": "unchanged",
            },
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-existing-B",
                "promotion_outcome": "unchanged",
            },
        ]
        payload = {
            "ok": True,
            "scanned": 2,
            "firing": 2,
            "opened_incidents": 0,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 0,
            "error_messages": [],
            "opened_incident_ids": [],
            "updated_incident_ids": [],
            "canonical_incident_ids": [
                "canonical-inc-existing-A",
                "canonical-inc-existing-B",
            ],
            "promotion_records": records,
            "unique_candidate_count": 2,
            "promotion_scan_scope": "internal_api_alert_signals:scoped",
            "incident_access_mode": "backend",
        }
        bound = BoundPromotionHttpWireResult(
            result=PromotionHttpWireResult.from_payload(payload),
            requested_signal_ids=requested,
        )
        assert bound.result.scanned == 2
        assert bound.result.unique_candidate_count == 2
        assert len(bound.result.promotion_records) == 2
        assert bound.result.opened_incident_ids == ()
        assert bound.result.updated_incident_ids == ()
