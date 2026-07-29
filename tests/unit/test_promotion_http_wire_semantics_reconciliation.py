"""Aggregate-level reconciliation tests for the strict wire result.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B-CORRECTION01.

Companion to :mod:`test_promotion_http_wire_semantics` which
covers the basic decoder-level invariants (counters, source
identity, ok/errors, canonical union). This focused module
covers the higher-level reconciliation invariants introduced
by the correction:

* ``canonical_incident_ids`` is the stable first-occurrence
  unique sequence of record canonical IDs (order authoritative).
* ``opened_incident_ids`` and ``updated_incident_ids`` are
  bijective with their record outcomes (no phantom IDs, no
  unmatched records).
* The two ID lists MUST be disjoint.
* ``OBSERVATION_REFRESHED`` and ``UNCHANGED`` records
  contribute to ``canonical_incident_ids`` but NEVER to the
  opened/updated lists.
* Mixed fixtures with all four outcomes and many-to-one
  canonical references hold every aggregate projection.
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


class TestCanonicalOrderAuthority:
    """``canonical_incident_ids`` is the stable first-occurrence
    unique sequence of ``promotion_records[*].canonical_incident_id``.
    Set equality is insufficient -- order is authoritative.
    """

    def test_canonical_ids_wrong_order_raises(self) -> None:
        """Reordering the canonical list while records preserve the
        original order MUST be rejected.
        """
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "opened",
            },
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-B",
                "promotion_outcome": "observation_refreshed",
            },
            {
                "source_candidate_id": "sig-003",
                "canonical_incident_id": "canonical-inc-C",
                "promotion_outcome": "observation_refreshed",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-A"],
            # Order is B, A, C -- record order is A, B, C.
            canonical_ids=["canonical-inc-B", "canonical-inc-A", "canonical-inc-C"],
        )
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "canonical_incident_ids" in str(exc_info.value)

    def test_duplicate_canonical_aggregate_id_raises(self) -> None:
        """``canonical_incident_ids`` MUST NOT contain duplicates."""
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "opened",
            },
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-B",
                "promotion_outcome": "observation_refreshed",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-A"],
            # Duplicate canonical-inc-A in the aggregate list.
            canonical_ids=["canonical-inc-A", "canonical-inc-B", "canonical-inc-A"],
        )
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_canonical_ids_order_is_first_occurrence(self) -> None:
        """First-occurrence order is the contract, not sorted order."""
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "opened",
            },
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "observation_refreshed",
            },
            {
                "source_candidate_id": "sig-003",
                "canonical_incident_id": "canonical-inc-B",
                "promotion_outcome": "observation_refreshed",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-A"],
            canonical_ids=["canonical-inc-A", "canonical-inc-B"],
        )
        # First-occurrence of A then B; the second A is dropped.
        result = PromotionHttpWireResult.from_payload(payload)
        assert result.canonical_incident_ids == (
            "canonical-inc-A",
            "canonical-inc-B",
        )


class TestBidirectionalOpenedUpdatedReconciliation:
    """Every record outcome MUST be reflected in the corresponding
    ID list, and every ID in the lists MUST have a matching record.
    """

    def test_opened_id_without_opened_record_raises(self) -> None:
        """An ID in ``opened_incident_ids`` with no OPENED record
        referencing it MUST be rejected (no phantom opens).
        """
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "unchanged",
            },
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-B",
                "promotion_outcome": "unchanged",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-A"],
            updated_ids=[],
        )
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "opened_incident_ids" in str(exc_info.value)

    def test_updated_id_without_updated_record_raises(self) -> None:
        """An ID in ``updated_incident_ids`` with no UPDATED record
        referencing it MUST be rejected (no phantom updates).
        """
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "unchanged",
            },
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-B",
                "promotion_outcome": "unchanged",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=[],
            updated_ids=["canonical-inc-A"],
        )
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "updated_incident_ids" in str(exc_info.value)

    def test_opened_and_updated_overlap_raises(self) -> None:
        """The two ID lists MUST be disjoint (an atomic promotion
        request cannot both open and update the same canonical
        incident).
        """
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "opened",
            },
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "updated",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-A"],
            updated_ids=["canonical-inc-A"],
        )
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "disjoint" in str(exc_info.value)


class TestRefreshedUnchangedExclusion:
    """``OBSERVATION_REFRESHED`` and ``UNCHANGED`` records
    contribute to ``canonical_incident_ids`` but MUST NOT appear
    in ``opened_incident_ids`` or ``updated_incident_ids``.
    """

    def test_refreshed_record_excluded_from_opened_ids(self) -> None:
        """A refreshed record's canonical ID MUST NOT appear in
        ``opened_incident_ids``.
        """
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "observation_refreshed",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-A"],
        )
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "opened_incident_ids" in str(exc_info.value)

    def test_unchanged_record_excluded_from_updated_ids(self) -> None:
        """An unchanged record's canonical ID MUST NOT appear in
        ``updated_incident_ids``.
        """
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "unchanged",
            },
        ]
        payload = _records_payload(
            records=records,
            updated_ids=["canonical-inc-A"],
        )
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "updated_incident_ids" in str(exc_info.value)

    def test_refreshed_record_id_present_in_canonical_only(self) -> None:
        """Positive test: refreshed records contribute to
        ``canonical_incident_ids`` but to neither opened nor
        updated lists.
        """
        records = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "observation_refreshed",
            },
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-B",
                "promotion_outcome": "observation_refreshed",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=[],
            updated_ids=[],
            canonical_ids=["canonical-inc-A", "canonical-inc-B"],
        )
        result = PromotionHttpWireResult.from_payload(payload)
        assert result.canonical_incident_ids == (
            "canonical-inc-A",
            "canonical-inc-B",
        )
        assert result.opened_incident_ids == ()
        assert result.updated_incident_ids == ()


class TestMixedOutcomesManyToOne:
    """End-to-end mixed fixture: opened, updated, refreshed,
    unchanged, plus many-to-one canonical references.
    """

    def test_mixed_outcomes_with_many_to_one_canonical(self) -> None:
        records = [
            # sig-001 opens canonical-inc-A
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "opened",
            },
            # sig-002 updates canonical-inc-B
            {
                "source_candidate_id": "sig-002",
                "canonical_incident_id": "canonical-inc-B",
                "promotion_outcome": "updated",
            },
            # sig-003 refreshes canonical-inc-C
            {
                "source_candidate_id": "sig-003",
                "canonical_incident_id": "canonical-inc-C",
                "promotion_outcome": "observation_refreshed",
            },
            # sig-004 is unchanged against canonical-inc-D
            {
                "source_candidate_id": "sig-004",
                "canonical_incident_id": "canonical-inc-D",
                "promotion_outcome": "unchanged",
            },
            # sig-005 is unchanged against canonical-inc-A
            # (many-to-one: sig-001 already opened A, sig-005 is
            # a stale observation now identity-matched)
            {
                "source_candidate_id": "sig-005",
                "canonical_incident_id": "canonical-inc-A",
                "promotion_outcome": "unchanged",
            },
        ]
        payload = _records_payload(
            records=records,
            opened_ids=["canonical-inc-A"],
            updated_ids=["canonical-inc-B"],
            canonical_ids=[
                "canonical-inc-A",
                "canonical-inc-B",
                "canonical-inc-C",
                "canonical-inc-D",
            ],
        )
        result = PromotionHttpWireResult.from_payload(payload)
        assert result.canonical_incident_ids == (
            "canonical-inc-A",
            "canonical-inc-B",
            "canonical-inc-C",
            "canonical-inc-D",
        )
        assert result.opened_incident_ids == ("canonical-inc-A",)
        assert result.updated_incident_ids == ("canonical-inc-B",)
        # 5 source records; canonical aggregates to 4 unique IDs.
        assert len(result.promotion_records) == 5
        assert len(result.canonical_incident_ids) == 4
