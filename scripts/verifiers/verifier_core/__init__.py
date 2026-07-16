"""Structural Python AST primitives shared by static verifiers.

This package is the typed, policy-free verifier core mandated by
``ACT-K9B-LLM-FRIENDLY-VERIFIER-CANONICAL-SYNTAX-CORE01``.

The package was deliberately narrowed in CORRECTION05: every
public symbol now has a real (non-test) consumer. The earlier
canonical-syntax subcode vocabulary (23 ``SUB_*`` constants,
``CODE_CANONICAL``, ``EXPECTED_PUBLIC_API``, ``all_subcodes()``)
and the ``SOURCE_LINE_DIRECTNESS_BOUND`` /
``enforce_directness_bound`` / ``Diagnostic`` /
``format_violation`` / ``sort_diagnostics`` /
``unique_top_level_function`` helpers have been removed because
the production R20 verifier does not consume any of them.

Package layout (each module is small, policy-free, and bounded):

* :mod:`.codes` -- :func:`read_source`, :func:`parse_path`,
  :func:`parse_strict`, and :class:`VerInfrastructureError`
  (the broken-verifier signal).
* :mod:`.diagnostics` -- :class:`SourceLocation` and
  :func:`location_of`.
* :mod:`.lookups` -- :func:`top_level_function`,
  :func:`function_body_statements`, :func:`parse_function_body`.
* :mod:`.directness` -- :func:`is_direct_name`,
  :func:`is_simple_load`, :func:`direct_name_from_load`,
  :func:`single_direct_name_call`, :func:`is_direct_name_call`,
  :func:`kwargs_dict`, :func:`is_direct_call_to`.
* :mod:`.detectors` -- :func:`statement_value`,
  :func:`detect_partial_application`,
  :func:`detect_dynamic_getattr`, :func:`detect_star_expansion`,
  :func:`detect_nested_defs`, :func:`detect_lambdas`,
  :func:`detect_nested_compound_under`,
  :func:`is_callable_collection_literal`.

The core is policy-free, deliberately narrow, and structurally
bounded. It must NOT grow call-graph, alias-flow, closure,
fixed-point, or value-tracking primitives.

See ``docs/doctrine/verifier-canonical-syntax.md`` for the
production grammar the canonical R20 verifier recognises.
"""

from __future__ import annotations

# Re-export every public symbol so `from scripts.verifiers import
# verifier_core` and `core.<NAME>` work without exposing module
# structure.
from .codes import (
    VerInfrastructureError,
    parse_path,
    parse_strict,
    read_source,
)
from .detectors import (
    detect_dynamic_getattr,
    detect_lambdas,
    detect_nested_compound_under,
    detect_nested_defs,
    detect_partial_application,
    detect_star_expansion,
    is_callable_collection_literal,
    statement_value,
)
from .diagnostics import (
    SourceLocation,
    location_of,
)
from .directness import (
    direct_name_from_load,
    is_direct_call_to,
    is_direct_name,
    is_direct_name_call,
    is_simple_load,
    kwargs_dict,
    single_direct_name_call,
)
from .lookups import (
    function_body_statements,
    parse_function_body,
    top_level_function,
)

__all__ = (
    # Codes (AST parsing + VerInfrastructureError)
    "VerInfrastructureError",
    "read_source",
    "parse_path",
    "parse_strict",
    # Diagnostics (source location)
    "SourceLocation",
    "location_of",
    # Lookups
    "top_level_function",
    "function_body_statements",
    "parse_function_body",
    # Directness
    "is_direct_name",
    "is_simple_load",
    "direct_name_from_load",
    "single_direct_name_call",
    "is_direct_name_call",
    "kwargs_dict",
    "is_direct_call_to",
    # Detectors
    "statement_value",
    "detect_partial_application",
    "detect_dynamic_getattr",
    "detect_star_expansion",
    "detect_nested_defs",
    "detect_lambdas",
    "detect_nested_compound_under",
    "is_callable_collection_literal",
)
