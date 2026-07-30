"""Compatibility façade for the **legacy** snake_case wire result authority.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B-CORRECTION01.
ACT-K9B-HULK-PROMOTION-SCOPED-WIRE-DIALECT-CONVERGENCE01.

DIALECT OWNERSHIP -- LEGACY/ADMIN
----------------------------------

This façade re-exports the legacy snake_case
``/api/internal/incidents/promote-candidates`` ``PromotionResponse``
dialect. The active scoped endpoint
``/api/internal/incidents/promote-alert-signals`` returns the
canonical camelCase ``IncidentPromotionResult`` contract declared
in :mod:`k8s_diag_agent.incident_alert_promotion_contract` and
is re-exported via :mod:`k8s_diag_agent.incident_alert_promotion_binding`.
Do not import the legacy snake_case types from this façade into the
scoped scheduler client.

The implementation of the strict wire result is split into five
focused modules:

* :mod:`promotion_http_wire_types` -- closed enums and the
  :class:`PromotionHttpWireValidationError` exception.
* :mod:`promotion_http_wire_decode` -- the
  :class:`PromotionWireRecord` and :class:`PromotionHttpWireResult`
  dataclasses with their strict validators.
* :mod:`promotion_http_wire_semantics` -- shared result-level
  invariant validation and identifier-tuple helpers
  (:func:`validate_identifier_tuple`, :func:`stable_unique`,
  :func:`decode_identifier_tuple`,
  :func:`record_opened_canonical_ids`,
  :func:`record_updated_canonical_ids`,
  :func:`catch_enum_decode`,
  :func:`validate_result_invariants`).
* :mod:`promotion_http_wire_binding` -- the
  :class:`BoundPromotionHttpWireResult` request-binding dataclass.

This façade exists only for backward compatibility with existing
imports. New code MUST import from the focused modules above.
"""

from __future__ import annotations

from .promotion_http_wire_binding import BoundPromotionHttpWireResult
from .promotion_http_wire_decode import (
    _REQUIRED_WIRE_FIELDS,
    PromotionHttpWireResult,
    PromotionWireRecord,
)
from .promotion_http_wire_semantics import (
    catch_enum_decode,
    decode_identifier_tuple,
    record_opened_canonical_ids,
    record_updated_canonical_ids,
    stable_unique,
    validate_identifier_tuple,
    validate_result_invariants,
)
from .promotion_http_wire_types import (
    PromotionHttpWireValidationError,
    PromotionWireIncidentAccessMode,
    PromotionWireRecordOutcome,
    PromotionWireScanScope,
)

__all__ = [
    "BoundPromotionHttpWireResult",
    "PromotionHttpWireResult",
    "PromotionHttpWireValidationError",
    "PromotionWireIncidentAccessMode",
    "PromotionWireRecord",
    "PromotionWireRecordOutcome",
    "PromotionWireScanScope",
    "_REQUIRED_WIRE_FIELDS",
    "catch_enum_decode",
    "decode_identifier_tuple",
    "record_opened_canonical_ids",
    "record_updated_canonical_ids",
    "stable_unique",
    "validate_identifier_tuple",
    "validate_result_invariants",
]
