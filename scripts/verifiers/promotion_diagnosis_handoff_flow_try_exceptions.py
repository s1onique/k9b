"""Compatibility shim for SEAM01 promotion-diagnosis handoff verifier.

After ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01 the canonical boolean
predicates live in
:mod:`promotion_diagnosis_handoff_flow_exception_paths`.  This module is
retained as a thin re-export so older call sites that import
``_stmt_may_raise`` or ``_may_raise`` from here keep working.

The verifier no longer uses these predicates to choose handler-entry
environments; handler-entry environments come from
:func:`promotion_diagnosis_handoff_flow_exception_paths.capture_exception_envs`.
The predicates are kept only as non-authoritative filters inside the
loop-aware try-processing helpers.

Suggested by: ACT-K9B-SEAM01-PRECISE-EXCEPTION-FLOW01
"""

from __future__ import annotations

from promotion_diagnosis_handoff_flow_exception_paths import (
    _may_raise_expr as _may_raise,
)
from promotion_diagnosis_handoff_flow_exception_paths import (
    _stmt_may_raise,
)

__all__ = ["_may_raise", "_stmt_may_raise"]