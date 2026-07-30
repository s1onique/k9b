"""Binding tests for the strict wire result.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B.

``BoundPromotionHttpWireResult`` enforces exact request coverage
in ``__post_init__``. An unbound instance cannot exist. These
tests cover basic happy-path and failure-path binding.

The additional binding invariants introduced by the correction
(success-only binding, request-counter binding, successful zero)
live in :mod:`test_promotion_http_wire_binding_invariants`.
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


def _valid_payload(
    source_ids: tuple[str, ...] = ("sig-001",),
    canonical_id: str = "canonical-inc-001",
) -> dict[str, Any]:
    """Build a valid payload covering exactly ``source_ids``."""
    records = [
        {
            "source_candidate_id": source_id,
            "canonical_incident_id": canonical_id,
            "promotion_outcome": "opened",
        }
        for source_id in source_ids
    ]
    return {
        "ok": True,
        "scanned": len(source_ids),
        "firing": len(source_ids),
        "opened_incidents": 1,
        "updated_incidents": 0,
        "skipped_duplicates": 0,
        "errors": 0,
        "error_messages": [],
        "opened_incident_ids": [canonical_id],
        "updated_incident_ids": [],
        "canonical_incident_ids": [canonical_id],
        "promotion_records": records,
        "unique_candidate_count": len(source_ids),
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
    }


def _bind(payload: dict[str, Any], requested: tuple[str, ...]) -> BoundPromotionHttpWireResult:
    """Bind a validated payload to its request."""
    return BoundPromotionHttpWireResult(
        result=PromotionHttpWireResult.from_payload(payload),
        requested_signal_ids=requested,
    )


class TestExactOneToOneBinding:
    def test_valid_one_to_one_binding(self) -> None:
        payload = _valid_payload(source_ids=("sig-001",))
        bound = _bind(payload, ("sig-001",))
        assert bound.requested_signal_count == 1
        assert bound.categorised_source_ids() == ("sig-001",)

    def test_valid_one_to_one_with_multiple_records(self) -> None:
        payload = _valid_payload(
            source_ids=("sig-001", "sig-002", "sig-003"),
        )
        bound = _bind(payload, ("sig-001", "sig-002", "sig-003"))
        assert bound.categorised_source_ids() == ("sig-001", "sig-002", "sig-003")


class TestManyToOneCanonicalBinding:
    def test_29_signal_one_opened_28_identity_matched(self) -> None:
        """Production-shaped 1-inserted / 28-identity-matched binding.

        29 distinct source signal IDs categorise against a single
        canonical incident. The bound instance exists with no
        follow-up validation step.
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
        bound = _bind(payload, requested)
        assert bound.categorised_source_ids() == requested
        assert bound.result.canonical_incident_ids == ("canonical-inc-001",)

    def test_34_signal_production_shape(self) -> None:
        """Bijective opened reconciliation across 34 signals.

        Records 0-1 open ``canonical-inc-001``; record 2 opens
        ``canonical-inc-002``; records 3..33 are
        ``observation_refreshed`` against ``canonical-inc-002``.
        The first three records collectively populate
        ``opened_incident_ids`` and ``canonical_incident_ids``
        in first-occurrence order.
        """
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
        bound = _bind(payload, requested)
        assert bound.categorised_source_ids() == requested
        assert bound.result.opened_incident_ids == (
            "canonical-inc-001",
            "canonical-inc-002",
        )
        assert bound.result.canonical_incident_ids == (
            "canonical-inc-001",
            "canonical-inc-002",
        )


class TestSuccessfulZeroWithFullCategorisation:
    def test_successful_zero_categorises_every_request(self) -> None:
        """Successful zero means every request has a categorisation
        record; ``diagnosis_incident_ids`` may be empty.
        """
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
        bound = _bind(payload, requested)
        assert bound.categorised_source_ids() == requested
        assert bound.result.opened_incident_ids == ()


class TestBindingFailures:
    def test_duplicate_requested_signals_raise(self) -> None:
        payload = _valid_payload()
        with pytest.raises(PromotionHttpWireValidationError):
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=("sig-001", "sig-001"),
            )

    def test_missing_requested_signal_raises(self) -> None:
        payload = _valid_payload()
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=(),
            )
        # The request-counter matched check now fires first: an
        # empty request cannot satisfy ``scanned == len(request)``
        # when the payload reports scanned=1.
        assert "scanned" in str(exc_info.value).lower()
        assert "request count" in str(exc_info.value).lower()

    def test_extra_unrequested_record_raises(self) -> None:
        payload = _valid_payload(source_ids=("sig-001", "sig-extra"))
        with pytest.raises(PromotionHttpWireValidationError):
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=("sig-001",),
            )

    def test_empty_requested_signal_id_raises(self) -> None:
        payload = _valid_payload()
        with pytest.raises(PromotionHttpWireValidationError):
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=("",),
            )

    def test_non_string_requested_signal_raises(self) -> None:
        payload = _valid_payload()
        with pytest.raises(PromotionHttpWireValidationError):
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=(123,),  # type: ignore[arg-type]
            )


class TestNonStringRequestedIDs:
    def test_non_string_requested_signal_id_raises(self) -> None:
        payload = _valid_payload()
        with pytest.raises(PromotionHttpWireValidationError):
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=("sig-001", 123),  # type: ignore[arg-type]
            )

    def test_empty_requested_signal_id_raises(self) -> None:
        payload = _valid_payload()
        with pytest.raises(PromotionHttpWireValidationError):
            BoundPromotionHttpWireResult(
                result=PromotionHttpWireResult.from_payload(payload),
                requested_signal_ids=("",),
            )
