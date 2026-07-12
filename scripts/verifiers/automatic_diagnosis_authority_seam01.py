#!/usr/bin/env python
"""Static verifier for ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.

Enforces the contract that the automatic-diagnosis processor:

1. Does NOT call ``check_incident_eligibility(incident_id=...)`` after it
   has received a typed :class:`Incident` from
   :class:`BackendIncidentFound`.
2. Does NOT call ``get_incident_store()`` to re-resolve the incident
   or to mutate lifecycle state.
3. Does NOT call the local ``IncidentStore.mark_diagnosis_loop_*``
   methods directly; all lifecycle writes must route through
   :func:`record_diagnosis_loop_*`.
4. Does NOT call the legacy nullable ``fetch_incident_for_diagnosis``.
5. Handles the backend lookup through exhaustive
   ``match`` on the three typed variants; never through truthiness or
   ``None`` checks.
6. Maps ``BackendIncidentLookupFailed`` to a bounded
   ``backend_incident_*`` reason code, never to ``incident_not_found``.
7. Does NOT introduce backend-to-local fallback when the backend
   operation fails.
8. Does NOT swallow lifecycle dispatch failures with an empty
   ``except`` / ``pass`` block.

And the aggregate-based eligibility evaluator:

1. Accepts a typed ``incident: Incident`` parameter.
2. Does NOT call ``get_incident_store()``.
3. Does NOT call any incident backend client.
4. Does NOT accept ``incident_id`` as its only incident input.

To keep this entry-point module under the LLM-friendly 500-line limit,
the implementation is split into two sibling modules:

* :mod:`scripts.verifiers.automatic_diagnosis_authority_seam01_helpers` —
  file-collection and AST helpers, plus the two reusable forbidden-pattern
  detectors.
* :mod:`scripts.verifiers.automatic_diagnosis_authority_seam01_checks` —
  every per-claim ``check_*`` function and the seam-module symbol
  collector.

For backward compatibility with the existing self-test
(``tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py``)
the underscored helper and detector names that the self-test accesses
via ``verifier._check_*`` / ``verifier._contains_*`` /
``verifier._seam_available_names`` are re-exported below as module
attributes.

Run directly:

    .venv/bin/python scripts/verifiers/automatic_diagnosis_authority_seam01.py

Exit code 0 = PASS, non-zero = violations present.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

# isort: skip_file

from __future__ import annotations

import sys
from pathlib import Path

# The verifier is invoked both as a script (``python scripts/verifiers/
# automatic_diagnosis_authority_seam01.py``) and via ``importlib.util
# .spec_from_file_location`` from the self-test. Neither sets up a
# parent package, so relative imports (``from . import ...``) fail.
# Add the verifier directory to ``sys.path`` so the sibling modules
# can be imported by absolute name. Idempotent: re-running the
# verifier (e.g. from the self-test) does not duplicate the entry.
_VERIFIER_DIR = str(Path(__file__).resolve().parent)
if _VERIFIER_DIR not in sys.path:
    sys.path.insert(0, _VERIFIER_DIR)

# ruff: noqa: E402,F401
# Re-export every helper / check under its legacy underscored name so
# the self-test can access them via ``verifier._check_*`` /
# ``verifier._contains_*`` / ``verifier._seam_available_names``.
from automatic_diagnosis_authority_seam01_helpers import (  # noqa: F401
    PROCESSOR_PATH,
    contains_truthiness_to_not_found,
    function_defs,
    has_empty_except_pass,
    parse_path,
    read_text,
)
from automatic_diagnosis_authority_seam01_checks import (  # noqa: F401
    check_evaluator_aggregate_signature,
    check_evaluator_no_lookups,
    check_processor_calls,
    check_processor_dispatch,
    check_processor_lookup_failed_not_incident_not_found,
    check_processor_no_backend_to_local_fallback,
    check_processor_no_swallowed_lifecycle,
    check_processor_old_id_resolver,
    check_processor_truthiness,
    check_processor_uses_aggregate_eligibility,
    check_seam_required_symbols,
    seam_available_names,
)

# Backward-compat underscored aliases used by the self-test. They live
# as plain module-attribute assignments so ruff's auto-fix cannot drop
# them on a subsequent run.
_contains_truthiness_to_not_found = contains_truthiness_to_not_found
_function_defs = function_defs
_has_empty_except_pass = has_empty_except_pass
_parse = parse_path
_read = read_text
_check_processor_calls = check_processor_calls
_check_processor_dispatch = check_processor_dispatch
_check_processor_lookup_failed_not_incident_not_found = (
    check_processor_lookup_failed_not_incident_not_found
)
_check_processor_no_backend_to_local_fallback = (
    check_processor_no_backend_to_local_fallback
)
_check_processor_no_swallowed_lifecycle = check_processor_no_swallowed_lifecycle
_check_processor_old_id_resolver = check_processor_old_id_resolver
_check_processor_truthiness = check_processor_truthiness
_check_processor_uses_aggregate_eligibility = (
    check_processor_uses_aggregate_eligibility
)
_seam_available_names = seam_available_names


def run_static_checks() -> list[str]:
    """Run all ACT-specific static checks against the production code."""
    violations: list[str] = []

    processor_tree = parse_path(PROCESSOR_PATH)
    if processor_tree is None:
        violations.append(
            "incident_diagnosis_auto_loop_evidence_processor.py: cannot read or parse"
        )
    else:
        violations.extend(_check_processor_calls(processor_tree))
        violations.extend(_check_processor_old_id_resolver(processor_tree))
        violations.extend(_check_processor_uses_aggregate_eligibility(processor_tree))
        violations.extend(_check_processor_dispatch(processor_tree))

        violations.extend(_check_processor_no_backend_to_local_fallback(processor_tree))
        violations.extend(_check_processor_no_swallowed_lifecycle(processor_tree))
        violations.extend(_check_processor_truthiness())
        violations.extend(_check_processor_lookup_failed_not_incident_not_found())

    violations.extend(check_evaluator_aggregate_signature())
    violations.extend(check_evaluator_no_lookups())
    violations.extend(check_seam_required_symbols())

    return violations


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    violations = run_static_checks()
    if violations:
        print(
            "ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 verifier "
            "found violations:"
        )
        for v in violations:
            print(f"- {v}")
        return 1
    print(
        "ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 verifier: PASS"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
