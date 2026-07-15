"""Dispatcher→PromotionOutcome classifier.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 domain helper.

The promotion dispatcher returns a typed
:class:`IncidentPromotionResult` (or raises one of a small set of
typed exceptions). The orchestrator must convert that result into
a closed :class:`PromotionOutcome` variant so the diagnosis
selection downstream carries a typed outcome rather than
reconstructing one from counters.

Mappings, keyed by typed inputs (NOT by exception message text):

* Typed :class:`PromotionScopeError` /
  :class:`PromotionRequestValidationError` -> :class:`PromotionRejected`
  with the relevant rejection code (these are *pre-commit* scope /
  request-shape rejections whose contract guarantees no mutation).
* Typed :class:`PromotionDispatchError` (internal dispatch failure) ->
  :class:`PromotionCommitUnknown` (an internal error does NOT prove
  that no side effect committed).
* Typed :class:`PromotionTransportUncertain` /
  :class:`PromotionTransportTimeout` /
  :class:`PromotionTransportRefused` /
  :class:`PromotionProtocolError` -> :class:`PromotionCommitUnknown`
  with a reconciliation token derived from the request payload.
* Typed :class:`IncidentPromotionResult` -> success or rejection
  based on the dispatcher's authoritative ``ok`` boolean.
* Generic ``IncidentPromotionResult(ok=False)`` without explicit
  no-commit proof -> :class:`PromotionCommitUnknown` (an untyped
  ``ok=False`` does NOT prove that no side effect committed).
* ``ok=False`` with non-empty canonical IDs is a protocol
  violation: the dispatcher reports a failure while simultaneously
  asserting it produced canonical IDs. Treated as protocol error
  (``PromotionCommitUnknown``) so the operator can diagnose a
  dispatcher regression; not normalized into a plain rejection.
* :class:`Exception` (but NOT :class:`BaseException` -- the
  application MUST NOT catch :class:`KeyboardInterrupt`,
  :class:`SystemExit` or :class:`GeneratorExit`) -> commit
  unknown, with a typed reason derived from the typed exception
  class.
* Any other typed :class:`BaseException` propagates unchanged so
  process termination is not silently absorbed.

The classifier is the only authoritative source of
``promotion_may_have_committed``,
``diagnosis_handoff_available``,
``diagnosis_invoked`` and
``promotion_consistency_error_recorded`` projections in the
production seam. ``promotion_propagated_to_diagnosis`` is a
**separate** downstream flag set only after diagnosis actually
consumes the IDs -- the classifier never emits it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import cast

from ..incident_alert_promotion_contract import (
    PromotionScopeError,
)
from .incident_identity_hardening import PromotionRecord
from .incident_promotion_dispatch import (
    IncidentPromotionResult,
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

# Typed exceptions used by the classifier. ``PromotionScopeError``
# already lives in the contract module. ``PromotionResponseValidationError``
# already lives in the dispatch module. The remaining four are
# declared here because they are part of the classifier's typed
# contract surface and not yet produced by the dispatcher.


class PromotionRequestValidationError(ValueError):
    """Dispatcher raised a request-shape validation error."""


class PromotionDispatchError(RuntimeError):
    """Dispatcher raised an internal dispatch error.

    An internal dispatcher error does NOT prove that no side effect
    committed. The classifier therefore maps this exception to
    :class:`PromotionCommitUnknown` (with the
    :attr:`PromotionUncertaintyCode.AMBIGUOUS_RESPONSE` reason) so
    reconciliation is required.
    """


class PromotionTransportUncertain(RuntimeError):
    """Transport-layer could not determine commit status."""


class PromotionTransportTimeout(PromotionTransportUncertain):
    """Transport timeout -- commit status unknown."""


class PromotionTransportRefused(PromotionTransportUncertain):
    """Transport connection refused -- commit status unknown."""


class PromotionProtocolError(RuntimeError):
    """Dispatcher produced a malformed response that violates the contract."""


def _stable_fingerprint(payload: Mapping[str, object]) -> str:
    """Return a deterministic SHA256 fingerprint of a dict-shaped payload.

    Used to derive the reconciliation token's
    :attr:`request_fingerprint` when the dispatcher returns no
    response.
    """
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_reconciliation_token(
    *,
    run_id: str,
    requested_signal_ids: tuple[str, ...],
    requested_signal_payload: Mapping[str, object],
) -> PromotionReconciliationToken:
    fingerprint = _stable_fingerprint(
        {
            "run_id": run_id,
            "signal_ids": list(requested_signal_ids),
            "request": dict(requested_signal_payload),
        }
    )
    return PromotionReconciliationToken(
        request_id=fingerprint[:32],
        request_fingerprint=fingerprint,
    )


# Map typed rejection exceptions to bounded rejection codes. The only
# exceptions admitted here are *pre-commit* rejections whose contract
# guarantees no mutation:
#
# - :class:`PromotionScopeError` -- a signal id was not present in the
#   current-run scope. The dispatcher validates before doing anything.
# - :class:`PromotionRequestValidationError` -- request-shape
#   validation failed before any dispatch occurred.
#
# :class:`PromotionDispatchError` is intentionally NOT in this table:
# an internal dispatcher failure does NOT prove no commit happened.
# See :data:`_DISPATCH_ERROR_TO_CODE` for its commit-unknown mapping.
_REJECTION_TYPE_TO_CODE: tuple[tuple[type[Exception], PromotionRejectionCode], ...] = (
    (PromotionScopeError, PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION),
    (PromotionRequestValidationError, PromotionRejectionCode.MALFORMED_SIGNAL_IDS),
)

# ``PromotionDispatchError`` is an internal dispatcher error -- the
# dispatcher could not satisfy the request, but cannot prove that no
# side effect committed. The classifier therefore maps it to
# ``PromotionCommitUnknown`` with the bounded
# ``AMBIGUOUS_RESPONSE`` uncertainty code so reconciliation is
# required. The constant is intentionally a tuple of (type, code)
# pairs to keep the table shape consistent with the rejection /
# uncertainty tables below.
_DISPATCH_ERROR_TO_CODE: tuple[tuple[type[Exception], PromotionUncertaintyCode], ...] = (
    (PromotionDispatchError, PromotionUncertaintyCode.AMBIGUOUS_RESPONSE),
)

# Map typed transport-exception classes to bounded uncertainty codes.
_UNCERTAINTY_TYPE_TO_CODE: tuple[tuple[type[Exception], PromotionUncertaintyCode], ...] = (
    (PromotionTransportTimeout, PromotionUncertaintyCode.TRANSPORT_TIMEOUT),
    (PromotionTransportRefused, PromotionUncertaintyCode.TRANSPORT_REFUSED),
    (PromotionTransportUncertain, PromotionUncertaintyCode.AMBIGUOUS_RESPONSE),
    (PromotionProtocolError, PromotionUncertaintyCode.PROTOCOL_ERROR),
)


def _lookup_rejection_code(
    exc: Exception,
) -> PromotionRejectionCode | None:
    for source_type, code in _REJECTION_TYPE_TO_CODE:
        if isinstance(exc, source_type):
            return code
    return None


def _lookup_uncertainty_code(
    exc: Exception,
) -> PromotionUncertaintyCode | None:
    # The dispatcher-internal error table takes priority over the
    # generic transport-uncertainty table because it carries a more
    # specific reason code (``AMBIGUOUS_RESPONSE`` is the broader
    # fallback).
    for source_type, code in _DISPATCH_ERROR_TO_CODE:
        if isinstance(exc, source_type):
            return code
    for source_type, code in _UNCERTAINTY_TYPE_TO_CODE:
        if isinstance(exc, source_type):
            return code
    return None


def classify_promotion_dispatch_result(
    *,
    run_id: str,
    requested_signal_ids: tuple[str, ...],
    requested_signal_payload: Mapping[str, object],
    outcome: IncidentPromotionResult | Exception | None,
    authoritative_records: tuple[PromotionRecord, ...] | None = None,
) -> PromotionOutcome:
    """Convert a dispatcher outcome into a typed :class:`PromotionOutcome`.

    ``outcome`` is the typed :class:`IncidentPromotionResult` on
    success, a typed :class:`Exception` (NOT :class:`BaseException`)
    on rejection or transport uncertainty, or ``None`` to surface
    as :class:`PromotionCommitUnknown`.

    ``authoritative_records`` is the authoritative per-candidate
    ``PromotionRecord`` collection carried on the dispatch
    :class:`PromotionBatch`. When non-empty, the records win over
    whatever ``IncidentPromotionResult.promotion_records`` may
    carry; this is the production boundary that prevents the
    typed outcome from silently losing authoritative per-candidate
    data when only the batch envelope exposes it.

    Process-termination exceptions (``KeyboardInterrupt``,
    ``SystemExit``, ``GeneratorExit``) are re-raised BEFORE any
    side effect -- including reconciliation-token construction,
    JSON serialization, fingerprinting, logging, or normalization
    -- so a malformed payload cannot mask process termination.
    """
    # Process-termination exceptions (``KeyboardInterrupt``,
    # ``SystemExit``, ``GeneratorExit``) are NOT subclasses of
    # ``Exception``. The annotation above is a TYPE hint, not a
    # runtime gate. Re-raise BEFORE _build_reconciliation_token so
    # we never construct a fingerprint for a process we are about
    # to terminate. This guard MUST run first.
    if isinstance(outcome, BaseException) and not isinstance(
        outcome, Exception
    ):
        raise outcome

    token = _build_reconciliation_token(
        run_id=run_id,
        requested_signal_ids=requested_signal_ids,
        requested_signal_payload=requested_signal_payload,
    )

    if outcome is None:
        return PromotionCommitUnknown(
            run_id=run_id,
            reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=token,
            requested_signal_ids=tuple(requested_signal_ids),
        )

    # Typed rejection takes priority over typed uncertainty so the
    # code follows the dispatcher's "known not-committed" path.
    if isinstance(outcome, Exception):
        rejection_code = _lookup_rejection_code(outcome)
        if rejection_code is not None:
            return PromotionRejected(
                run_id=run_id,
                reason=rejection_code,
                rejected_signal_ids=tuple(requested_signal_ids),
            )
        uncertainty_code = _lookup_uncertainty_code(outcome)
        if uncertainty_code is not None:
            return PromotionCommitUnknown(
                run_id=run_id,
                reason=uncertainty_code,
                reconciliation_token=token,
                requested_signal_ids=tuple(requested_signal_ids),
            )
        # Any other typed application exception is treated as
        # commit-unknown. We do NOT match on message text; the
        # dispatcher's typed class is the only authority. The
        # bounded reason list is the closed enum; we map a free-form
        # application exception to ``AMBIGUOUS_RESPONSE`` to keep the
        # enum closed.
        return PromotionCommitUnknown(
            run_id=run_id,
            reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=token,
            requested_signal_ids=tuple(requested_signal_ids),
        )

    if not isinstance(outcome, IncidentPromotionResult):
        return PromotionCommitUnknown(
            run_id=run_id,
            reason=PromotionUncertaintyCode.PROTOCOL_ERROR,
            reconciliation_token=token,
            requested_signal_ids=tuple(requested_signal_ids),
        )

    # ``IncidentPromotionResult.ok`` is the dispatcher's authoritative
    # boolean. ``ok=False`` with non-empty canonical IDs is a
    # contract violation: the dispatcher reports a failure while
    # simultaneously asserting it produced canonical IDs. Treat as
    # protocol error so the operator can diagnose a dispatcher
    # regression; do not normalize into a plain rejection.
    canonical_attr = getattr(outcome, "canonical_incident_ids", ())
    canonical_ids = (
        tuple(canonical_attr())
        if callable(canonical_attr)
        else tuple(canonical_attr)
    )
    if not outcome.ok:
        if canonical_ids:
            return PromotionCommitUnknown(
                run_id=run_id,
                reason=PromotionUncertaintyCode.PROTOCOL_ERROR,
                reconciliation_token=token,
                requested_signal_ids=tuple(requested_signal_ids),
            )
        # Generic ``ok=False`` without an explicit no-commit proof is
        # commit-unknown. ``IncidentPromotionResult`` does not
        # distinguish "we proved nothing was committed" from "the
        # request never reached the backend", so the safe mapping is
        # commit-unknown. Reconciliation is required before any
        # diagnosis handoff may proceed.
        return PromotionCommitUnknown(
            run_id=run_id,
            reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=token,
            requested_signal_ids=tuple(requested_signal_ids),
        )

    actionable = _canonical_ids_from_result(outcome)
    # ``authoritative_records`` wins over
    # ``IncidentPromotionResult.promotion_records``: in production
    # the dispatcher batch is the only authoritative envelope and
    # the batch may carry records the bare ``IncidentPromotionResult``
    # does not (and vice versa in test stubs).
    if authoritative_records is not None:
        records = authoritative_records
    else:
        # Fallback: ``IncidentPromotionResult.promotion_records`` may not
        # be typed as ``PromotionRecord`` in test stubs, so we cast.
        records_attr: object = getattr(outcome, "records", ())
        if records_attr == ():
            records_attr = getattr(outcome, "promotion_records", ())
        records = tuple(cast("PromotionRecord", r) for r in records_attr)
    return PromotionSucceeded(
        run_id=run_id,
        requested_signal_ids=requested_signal_ids,
        records=records,
        diagnosis_incident_ids=actionable,
    )


def _canonical_ids_from_result(
    result: IncidentPromotionResult,
) -> tuple[str, ...]:
    """Return the canonical actionable IDs in deterministic order."""
    ids = tuple(
        str(value) for value in (result.actionable_incident_ids or ())
    )
    seen: set[str] = set()
    merged: list[str] = []
    for value in ids:
        if value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return tuple(merged)


def promotion_outcome_event_fields(
    outcome: PromotionOutcome,
) -> dict[str, object]:
    """Project a typed :class:`PromotionOutcome` into structured event fields.

    This is the canonical helper that converts the outcome variant
    into the low-cardinality fields a downstream health-run log
    expects. Every projection is sourced from the outcome variant;
    no field is reconstructed from dispatcher counts.

    Required fields:

    * ``promotion_outcome`` -- ``"succeeded"`` / ``"rejected"`` /
      ``"commit_unknown"``.
    * ``promotion_outcome_reason`` -- the bounded
      :class:`PromotionRejectionCode` or
      :class:`PromotionUncertaintyCode` for non-success variants;
      ``""`` for success.
    * ``promotion_may_have_committed`` -- projection of
      :func:`may_have_committed`.
    * ``diagnosis_handoff_available`` -- projection of
      :func:`propagation_available`. **Note**: this means the typed
      outcome permits diagnosis; it does NOT mean diagnosis has
      actually been invoked yet.
    * ``diagnosis_handoff_incident_count`` -- number of diagnosis
      IDs available for diagnosis consumption (``0`` for
      non-success variants).
    * ``diagnosis_invoked`` -- always ``False`` during the Item-3
      scope. Item 4 will set this when the typed outcome reaches
      the diagnosis collector.
    * ``promotion_consistency_error_recorded`` -- projection of
      :func:`consistency_error_recorded`.
    * ``promotion_outcome_available`` -- ``True`` iff the outcome
      has been classified.
    * ``reconciliation_required`` -- ``True`` only for
      :class:`PromotionCommitUnknown`.
    * ``requested_signal_count`` -- number of signal IDs in the
      original request payload.
    * ``canonical_incident_id_count`` -- number of authoritative
      canonical IDs available on the outcome. ``0`` for non-success
      variants.
    * ``promotion_record_count`` -- number of records the outcome
      carries. ``0`` for non-success variants.

    Raises:
        TypeError: if ``outcome`` is not a closed-union variant. The
            union is intended to be closed; an unknown object cannot
            be projected without fabricating a contradictory
            payload.
    """
    from .promotion_outcomes import (
        PromotionCommitUnknown,
        PromotionRejected,
        PromotionSucceeded,
        consistency_error_recorded,
        may_have_committed,
        propagation_available,
    )

    if isinstance(outcome, PromotionSucceeded):
        outcome_value = "succeeded"
        reason_value = ""
        canonical_count = len(outcome.diagnosis_incident_ids)
        record_count = len(outcome.records)
        requested_count = len(outcome.requested_signal_ids)
        handoff_count = canonical_count
    elif isinstance(outcome, PromotionRejected):
        outcome_value = "rejected"
        reason_value = outcome.reason.value
        canonical_count = 0
        record_count = 0
        requested_count = len(outcome.rejected_signal_ids)
        handoff_count = 0
    elif isinstance(outcome, PromotionCommitUnknown):
        outcome_value = "commit_unknown"
        reason_value = outcome.reason.value
        canonical_count = 0
        record_count = 0
        requested_count = len(outcome.requested_signal_ids)
        handoff_count = 0
    else:
        raise TypeError(
            "promotion_outcome_event_fields received a non-PromotionOutcome "
            f"value: {type(outcome).__name__!r}. The PromotionOutcome union "
            "is closed; an unsupported variant MUST NOT be projected."
        )

    return {
        "promotion_outcome": outcome_value,
        "promotion_outcome_reason": reason_value,
        "promotion_may_have_committed": may_have_committed(outcome),
        "diagnosis_handoff_available": propagation_available(outcome),
        "diagnosis_handoff_incident_count": handoff_count,
        "diagnosis_invoked": False,
        "promotion_consistency_error_recorded": (
            consistency_error_recorded(outcome)
        ),
        "promotion_outcome_available": True,
        "reconciliation_required": (
            isinstance(outcome, PromotionCommitUnknown)
        ),
        "requested_signal_count": requested_count,
        "canonical_incident_id_count": canonical_count,
        "promotion_record_count": record_count,
    }


__all__ = [
    "classify_promotion_dispatch_result",
    "promotion_outcome_event_fields",
    "PromotionDispatchError",
    "PromotionProtocolError",
    "PromotionRequestValidationError",
    "PromotionTransportRefused",
    "PromotionTransportTimeout",
    "PromotionTransportUncertain",
]