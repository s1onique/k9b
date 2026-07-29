"""Semantic tests for the strict wire result.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B.

Covers counter consistency, outcome reconciliation, source/canonical
identity rules, and record-outcome semantics.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.promotion_http_wire_decode import (
    PromotionHttpWireResult,
)
from k8s_diag_agent.collect.promotion_http_wire_types import (
    PromotionHttpWireValidationError,
    PromotionWireRecordOutcome,
)


def _records_payload(
    *,
    records: list[dict[str, Any]],
    opened_ids: list[str] = (),
    updated_ids: list[str] = (),
    canonical_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build a payload with explicit records and ID lists."""
    if canonical_ids is None:
        seen: list[str] = []
        for record in records:
            cid = record["canonical_incident_id"]
            if cid and cid not in seen:
                seen.append(cid)
        canonical_ids = seen
    return {
        "ok": True,
        "scanned": len(records),
        "firing": len(records),
        "opened_incidents": len(opened_ids),
        "updated_incidents": len(updated_ids),
        "skipped_duplicates": 0,
        "errors": 0,
        "error_messages": [],
        "opened_incident_ids": list(opened_ids),
        "updated_incident_ids": list(updated_ids),
        "canonical_incident_ids": list(canonical_ids),
        "promotion_records": list(records),
        "unique_candidate_count": len(records),
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
    }


class TestCounterConsistency:
    def test_firing_exceeds_scanned_raises(self) -> None:
        payload = _records_payload(
            records=[
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-001",
                    "promotion_outcome": "opened",
                }
            ],
            opened_ids=["canonical-inc-001"],
        )
        payload["firing"] = 5
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_opened_count_mismatch_raises(self) -> None:
        """opened_incidents must equal len(opened_incident_ids)."""
        # One opened record with one canonical ID but opened_incidents
        # claims 2.
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "opened",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-001"],
        )
        payload["opened_incidents"] = 2
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "opened_incidents" in str(exc_info.value)

    def test_updated_count_mismatch_raises(self) -> None:
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "updated",
            },
        ]
        payload = _records_payload(
            records=records,
            updated_ids=["canonical-inc-001"],
        )
        payload["updated_incidents"] = 2
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "updated_incidents" in str(exc_info.value)


class TestSourceIdentity:
    def test_duplicate_source_ids_raise(self) -> None:
        payload = _records_payload(
            records=[
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-001",
                    "promotion_outcome": "opened",
                },
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-002",
                    "promotion_outcome": "opened",
                },
            ],
            opened_ids=["canonical-inc-001", "canonical-inc-002"],
        )
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "source_candidate_id" in str(exc_info.value)


class TestCanonicalIdentityManyToOne:
    def test_multiple_records_share_one_canonical_id(self) -> None:
        """The 1-inserted / 28-identity-matched production case.

        29 distinct source signal IDs categorise against a single
        canonical incident. The strict decoder accepts this; the
        prior rule incorrectly rejected it.
        """
        records = [
            {
                "source_candidate_id": f"sig-{i:03d}",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": (
                    "opened" if i == 0 else "observation_refreshed"
                ),
            }
            for i in range(29)
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-001"],
        )
        result = PromotionHttpWireResult.from_payload(payload)
        canonical_ids = [
            record.canonical_incident_id for record in result.promotion_records
        ]
        assert canonical_ids.count("canonical-inc-001") == 29

    def test_34_signal_production_shape_with_many_to_one(self) -> None:
        """The 34-signal witness observed in production."""
        records = [
            {
                "source_candidate_id": f"sig-{i:03d}",
                "canonical_incident_id": (
                    "canonical-inc-001" if i < 2 else "canonical-inc-002"
                ),
                "promotion_outcome": (
                    "opened" if i < 2 else "observation_refreshed"
                ),
            }
            for i in range(34)
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-001", "canonical-inc-002"],
        )
        PromotionHttpWireResult.from_payload(payload)  # does not raise


class TestOkErrorConsistency:
    def test_ok_true_with_errors_raises(self) -> None:
        payload = _records_payload(
            records=[
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-001",
                    "promotion_outcome": "opened",
                }
            ],
            opened_ids=["canonical-inc-001"],
        )
        payload["errors"] = 1
        payload["error_messages"] = ["oops"]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_ok_true_with_messages_raises(self) -> None:
        payload = _records_payload(
            records=[
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-001",
                    "promotion_outcome": "opened",
                }
            ],
            opened_ids=["canonical-inc-001"],
        )
        payload["error_messages"] = ["non-empty"]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_ok_false_without_errors_raises(self) -> None:
        payload = _records_payload(
            records=[
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-001",
                    "promotion_outcome": "opened",
                }
            ],
            opened_ids=["canonical-inc-001"],
        )
        payload["ok"] = False
        payload["errors"] = 0
        payload["error_messages"] = []
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)


class TestRecordOutcomeReconciliation:
    def test_opened_record_requires_canonical_in_opened_ids(self) -> None:
        payload = _records_payload(
            records=[
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-001",
                    "promotion_outcome": "opened",
                }
            ],
            opened_ids=[],
        )
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_updated_record_requires_canonical_in_updated_ids(self) -> None:
        payload = _records_payload(
            records=[
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-001",
                    "promotion_outcome": "updated",
                }
            ],
            updated_ids=[],
        )
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)


class TestCanonicalUnion:
    def test_canonical_ids_must_match_record_unique_canonicals(self) -> None:
        payload = _records_payload(
            records=[
                {
                    "source_candidate_id": "sig-001",
                    "canonical_incident_id": "canonical-inc-001",
                    "promotion_outcome": "opened",
                },
                {
                    "source_candidate_id": "sig-002",
                    "canonical_incident_id": "canonical-inc-002",
                    "promotion_outcome": "observation_refreshed",
                },
            ],
            opened_ids=["canonical-inc-001"],
        )
        payload["canonical_incident_ids"] = ["canonical-inc-001"]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_canonical_ids_empty_for_zero_record_success(self) -> None:
        """Successful zero has no records, no canonical IDs.

        The request-binding layer (separate test file) covers the
        successful-zero case where records exist but open zero
        incidents. This module-level invariant accepts an empty
        ``promotion_records`` list with empty ID lists.
        """
        payload = _records_payload(
            records=[],
            opened_ids=[],
            updated_ids=[],
            canonical_ids=[],
        )
        payload["scanned"] = 0
        payload["firing"] = 0
        payload["unique_candidate_count"] = 0
        result = PromotionHttpWireResult.from_payload(payload)
        assert result.promotion_records == ()


class TestClosedRecordOutcome:
    def test_outcome_enum_has_expected_values(self) -> None:
        assert {member.value for member in PromotionWireRecordOutcome} == {
            "opened",
            "updated",
            "observation_refreshed",
            "unchanged",
        }
