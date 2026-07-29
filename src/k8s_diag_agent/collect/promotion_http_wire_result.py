"""Compatibility façade for the strict wire result authority.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B.

The implementation of the strict wire result was split into four
modules:

* :mod:`promotion_http_wire_types` -- closed enums and the
  ``PromotionHttpWireValidationError`` exception.
* :mod:`promotion_http_wire_decode` -- the
  ``PromotionWireRecord`` and ``PromotionHttpWireResult`` dataclasses
  with their strict validators.
* :mod:`promotion_http_wire_binding` -- the
  ``BoundPromotionHttpWireResult`` request-binding dataclass.

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
]
