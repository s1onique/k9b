"""Transport-to-PromotionOutcome mapping for the closed HTTP union.

ACT-K9B-HULK-PROMOTION-AMBIGUOUS-RESPONSE-TRANSPORT-TRUTH01-LOCAL-CONTRACT01.

This module exhaustively maps the closed
``PromotionHttpTransportOutcome`` union onto the typed
``PromotionOutcome`` family so a known HTTP shape produces a known
typed outcome. ``AMBIGUOUS_RESPONSE`` is no longer used for a known
shape; it is reserved for the invariant-violation fallback only.

Mapping contract:

* ``PromotionHttpSucceeded(valid_result)`` -> ``PromotionSucceeded``
* ``PromotionHttpAccepted`` / ``NoContent`` / ``InvalidJson`` /
  ``InvalidSchema`` / ``TransportFailureAfterSend`` /
  ``ResponseTruncated`` -> ``PromotionCommitUnknown`` with
  ``may_have_committed=True`` (post-send uncertainty).
* ``PromotionHttpRejected`` -> ``PromotionRejected``
  (``may_have_committed=False``).
* ``PromotionHttpTransportFailureBeforeSend`` -> ``PromotionRejected``
  (``may_have_committed=False``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .incident_identity_hardening import PromotionRecord
from .incident_promotion_dispatch import IncidentPromotionResult
from .promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpRejected,
    PromotionHttpResponseTruncated,
    PromotionHttpSucceeded,
    PromotionHttpTransportFailureAfterSend,
    PromotionHttpTransportFailureBeforeSend,
    PromotionHttpTransportOutcome,
    PromotionHttpTransportReasonCode,
    may_have_committed_from_transport,
)
from .promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionOutcome,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)


@dataclass(frozen=True, slots=True)
class TransportPromotionProjection:
    """Result of mapping a typed transport outcome onto ``PromotionOutcome``.

    ``incident_promotion_result`` is the dispatcher-shaped result
    the prior correction cycle consumes; ``promotion_outcome`` is the
    typed outcome the selection handoff consumes; ``may_have_committed``
    is the closed projection.
    """

    incident_promotion_result: IncidentPromotionResult
    promotion_outcome: PromotionOutcome
    may_have_committed: bool


def _stable_fingerprint(*parts: object) -> str:
    """Return a deterministic fingerprint for the reconciliation token."""
    import hashlib

    encoded = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_reconciliation_token(request_id: str) -> PromotionReconciliationToken:
    """Build a bounded reconciliation token from the request_id."""
    return PromotionReconciliationToken(
        request_id=request_id[:32] or "unknown-request",
        request_fingerprint=_stable_fingerprint(request_id),
    )


def _records_from_payload(payload: object) -> tuple[PromotionRecord, ...]:
    """Convert a typed wire payload into ``PromotionRecord`` instances.

    The mapping preserves backward compatibility with the dispatcher's
    authoritative per-candidate record shape.
    """
    if not isinstance(payload, dict):
        return ()
    records_raw = payload.get("promotion_records", ()) or ()
    if not isinstance(records_raw, (list, tuple)):
        return ()
    records: list[PromotionRecord] = []
    for entry in records_raw:
        if not isinstance(entry, dict):
            continue
        records.append(
            PromotionRecord(
                source_candidate_id=str(entry.get("source_candidate_id", "")),
                canonical_incident_id=entry.get("canonical_incident_id"),
                promotion_outcome=str(entry.get("promotion_outcome", "opened")),
            )
        )
    return tuple(records)


def _ids_from_payload(payload: object) -> tuple[str, ...]:
    """Extract canonical incident IDs from a typed wire payload."""
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("canonical_incident_ids")
    if not isinstance(raw, (list, tuple)):
        # Fallback: open + update lists.
        opened = payload.get("opened_incident_ids") or ()
        updated = payload.get("updated_incident_ids") or ()
        raw = (*opened, *updated)
    return tuple(str(value) for value in raw)


def _scanned_from_payload(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    raw = payload.get("scanned")
    if isinstance(raw, int):
        return raw
    return 0


def _record_to_dict(record: object) -> dict[str, str | None]:
    """Convert a ``PromotionRecord``-like to the dispatcher dict shape."""
    return {
        "source_candidate_id": str(getattr(record, "source_candidate_id", "")),
        "canonical_incident_id": str(
            getattr(record, "canonical_incident_id", "") or ""
        )
        or None,
        "promotion_outcome": str(getattr(record, "promotion_outcome", "opened")),
    }


def _failure_dispatch_result(
    *,
    observation_error_message: str,
) -> IncidentPromotionResult:
    """Build a bounded dispatcher-shaped failure result."""
    return IncidentPromotionResult(
        ok=False,
        scanned=0,
        firing=0,
        opened_incidents=0,
        updated_incidents=0,
        skipped_duplicates=0,
        errors=1,
        error_messages=(observation_error_message,),
        promotion_records=(),
        promotion_mode="backend-api",
        unique_candidate_count=0,
        promotion_scan_scope="internal_api_alert_signals:scoped",
        incident_access_mode="backend",
    )


def map_promotion_http_transport_to_outcome(
    transport: PromotionHttpTransportOutcome,
    *,
    requested_signal_ids: tuple[str, ...] = (),
) -> TransportPromotionProjection:
    """Exhaustively map a typed HTTP outcome onto ``PromotionOutcome``.

    The mapping is deterministic and exhaustive over the closed
    transport union. Any new variant MUST be added here AND in
    :func:`may_have_committed_from_transport`.
    """
    may_have_committed = may_have_committed_from_transport(transport)

    if isinstance(transport, PromotionHttpSucceeded):
        payload = transport.raw_payload
        records = _records_from_payload(payload)
        record_dicts = tuple(_record_to_dict(record) for record in records)
        ids = _ids_from_payload(payload)
        promotion_outcome: PromotionOutcome = PromotionSucceeded(
            run_id=transport.observation.request_id,
            requested_signal_ids=requested_signal_ids,
            records=records,
            diagnosis_incident_ids=ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=IncidentPromotionResult(
                ok=True,
                scanned=_scanned_from_payload(payload),
                firing=_scanned_from_payload(payload),
                opened_incidents=len(_opened_ids_from_payload(payload)),
                updated_incidents=len(_updated_ids_from_payload(payload)),
                skipped_duplicates=int(payload.get("skipped_duplicates", 0))
                if isinstance(payload, dict)
                else 0,
                errors=0,
                error_messages=(),
                promotion_records=record_dicts,
                promotion_mode="backend-api",
                unique_candidate_count=len(requested_signal_ids),
                promotion_scan_scope="internal_api_alert_signals:scoped",
                incident_access_mode="backend",
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=may_have_committed,
        )

    if isinstance(transport, PromotionHttpAccepted):
        promotion_outcome = PromotionCommitUnknown(
            run_id=transport.observation.request_id,
            reason=PromotionUncertaintyCode.HTTP_ACCEPTED_WITHOUT_RESULT,
            reconciliation_token=_stable_reconciliation_token(
                transport.observation.request_id
            ),
            requested_signal_ids=requested_signal_ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=_failure_dispatch_result(
                observation_error_message="HTTP_ACCEPTED_WITHOUT_RESULT"
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=True,
        )

    if isinstance(transport, PromotionHttpNoContent):
        promotion_outcome = PromotionCommitUnknown(
            run_id=transport.observation.request_id,
            reason=PromotionUncertaintyCode.HTTP_NO_CONTENT_AFTER_SEND,
            reconciliation_token=_stable_reconciliation_token(
                transport.observation.request_id
            ),
            requested_signal_ids=requested_signal_ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=_failure_dispatch_result(
                observation_error_message="HTTP_NO_CONTENT_AFTER_SEND"
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=True,
        )

    if isinstance(transport, PromotionHttpInvalidJson):
        promotion_outcome = PromotionCommitUnknown(
            run_id=transport.observation.request_id,
            reason=PromotionUncertaintyCode.HTTP_INVALID_JSON,
            reconciliation_token=_stable_reconciliation_token(
                transport.observation.request_id
            ),
            requested_signal_ids=requested_signal_ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=_failure_dispatch_result(
                observation_error_message="HTTP_INVALID_JSON"
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=True,
        )

    if isinstance(transport, PromotionHttpInvalidSchema):
        promotion_outcome = PromotionCommitUnknown(
            run_id=transport.observation.request_id,
            reason=PromotionUncertaintyCode.HTTP_INVALID_SCHEMA,
            reconciliation_token=_stable_reconciliation_token(
                transport.observation.request_id
            ),
            requested_signal_ids=requested_signal_ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=_failure_dispatch_result(
                observation_error_message="HTTP_INVALID_SCHEMA"
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=True,
        )

    if isinstance(transport, PromotionHttpTransportFailureAfterSend):
        promotion_outcome = PromotionCommitUnknown(
            run_id=transport.observation.request_id,
            reason=PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND
            if transport.reason_code
            == PromotionHttpTransportReasonCode.HTTP_READ_TIMEOUT_AFTER_SEND
            else PromotionUncertaintyCode.HTTP_CONNECTION_LOST_AFTER_SEND,
            reconciliation_token=_stable_reconciliation_token(
                transport.observation.request_id
            ),
            requested_signal_ids=requested_signal_ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=_failure_dispatch_result(
                observation_error_message=transport.reason_code.value
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=True,
        )

    if isinstance(transport, PromotionHttpResponseTruncated):
        promotion_outcome = PromotionCommitUnknown(
            run_id=transport.observation.request_id,
            reason=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            reconciliation_token=_stable_reconciliation_token(
                transport.observation.request_id
            ),
            requested_signal_ids=requested_signal_ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=_failure_dispatch_result(
                observation_error_message="HTTP_RESPONSE_TRUNCATED"
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=True,
        )

    if isinstance(transport, PromotionHttpRejected):
        promotion_outcome = PromotionRejected(
            run_id=transport.observation.request_id,
            reason=PromotionRejectionCode.UNKNOWN,
            rejected_signal_ids=requested_signal_ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=_failure_dispatch_result(
                observation_error_message=transport.body_excerpt or "rejected"
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=False,
        )

    if isinstance(transport, PromotionHttpTransportFailureBeforeSend):
        promotion_outcome = PromotionRejected(
            run_id=transport.observation.request_id,
            reason=PromotionRejectionCode.UNKNOWN,
            rejected_signal_ids=requested_signal_ids,
        )
        return TransportPromotionProjection(
            incident_promotion_result=_failure_dispatch_result(
                observation_error_message=transport.reason_code.value
            ),
            promotion_outcome=promotion_outcome,
            may_have_committed=False,
        )

    # Exhaustive: the closed union above covers every known variant.
    raise TypeError(
        "map_promotion_http_transport_to_outcome received an unhandled "
        f"variant: {type(transport).__name__!r}"
    )


def _opened_ids_from_payload(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("opened_incident_ids") or ()
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(value) for value in raw)


def _updated_ids_from_payload(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("updated_incident_ids") or ()
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(value) for value in raw)
