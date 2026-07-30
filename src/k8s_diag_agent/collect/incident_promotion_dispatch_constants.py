"""Cycle-free access-mode and promotion-mode constants.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
CORRECTION05-STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

The dispatcher module
(:mod:`k8s_diag_agent.collect.incident_promotion_dispatch`) imports
the typed accumulator host
(:class:`k8s_diag_agent.collect.RunPromotionAccumulator`) so the
split atomic recorder modules cannot import the dispatcher without
closing an import cycle. This small module owns the two literal
constants used by both sides:

* :data:`INCIDENT_ACCESS_MODE_BACKEND` -- the bounded backend
  access-mode string the dispatcher publishes to every batch.
* :data:`MODE_BACKEND_API` -- the bounded ``backend-api`` mode
  string the dispatcher stamps on every batch.

Both sides import these constants from this module so the literal
strings live in one cycle-free location. A future drift between
the dispatcher's published value and the validator's check fails
my-py on both sides simultaneously.
"""

from __future__ import annotations

from typing import Literal

INCIDENT_ACCESS_MODE_LOCAL: Literal["local"] = "local"
INCIDENT_ACCESS_MODE_BACKEND: Literal["backend"] = "backend"

MODE_LOCAL: Literal["local"] = "local"
MODE_BACKEND_API: Literal["backend-api"] = "backend-api"
MODE_AUTO: Literal["auto"] = "auto"


__all__ = [
    "INCIDENT_ACCESS_MODE_BACKEND",
    "INCIDENT_ACCESS_MODE_LOCAL",
    "MODE_AUTO",
    "MODE_BACKEND_API",
    "MODE_LOCAL",
]