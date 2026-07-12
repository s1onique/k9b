"""Per-check functions for the ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
verifier.

Every function in this module takes a parsed :class:`ast.Module` (or,
for the seam-check, reads its own file) and returns a list of
human-readable violation strings. An empty list means the check
passed. The verifier entry point
(:mod:`scripts.verifiers.automatic_diagnosis_authority_seam01`)
orchestrates the checks via :func:`run_static_checks` (which lives in
the entry-point module so this file stays a flat collection of
checks).

Each tree-based check has a paired negative / positive fixture in
``tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py``
so the verifier is provably non-trivial rather than a green stamp.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

import ast
from typing import Final

from automatic_diagnosis_authority_seam01_helpers import (  # noqa: F401
    EVALUATOR_PATH,
    PROCESSOR_PATH,
    SEAM_PATH,
    call_keyword,
    called_names,
    contains_truthiness_to_not_found,
    function_defs,
    has_empty_except_pass,
    match_case_type,
    parse_path,
    read_text,
)

# Forbidden call names that the processor must not invoke. The presence
# of these names inside ``_process_incident`` is a contract violation.
FORBIDDEN_PROCESSOR_CALLS: Final[tuple[str, ...]] = (
    "get_incident_store",
    "fetch_incident_for_diagnosis",
)


# Forbidden call names that the aggregate evaluator must not invoke.
FORBIDDEN_EVALUATOR_CALLS: Final[tuple[str, ...]] = (
    "get_incident_store",
    "fetch_backend_incident_for_diagnosis_typed",
    "fetch_incident_for_diagnosis",
)


# Lifecycle mutation methods that the processor must NOT call directly.
# All such writes must route through ``record_diagnosis_loop_*`` helpers.
DIRECT_LIFECYCLE_METHODS: Final[tuple[str, ...]] = (
    "mark_diagnosis_loop_started",
    "mark_diagnosis_loop_failed",
    "mark_diagnosis_loop_completed",
)


# Symbol names whose definition must remain in the canonical seam.
REQUIRED_SEAM_SYMBOLS: Final[tuple[str, ...]] = (
    "evaluate_incident_eligibility",
    "check_incident_eligibility",
    "record_diagnosis_loop_started",
    "record_diagnosis_loop_failed",
    "record_diagnosis_loop_completed",
)


# Variants the processor must dispatch on exhaustively.
TYPED_LOOKUP_VARIANTS: Final[tuple[str, ...]] = (
    "BackendIncidentFound",
    "BackendIncidentNotFound",
    "BackendIncidentLookupFailed",
)


# ---------------------------------------------------------------------------
# Processor checks
# ---------------------------------------------------------------------------


def check_processor_calls(tree: ast.Module) -> list[str]:
    """Reject any direct call to forbidden functions inside the processor."""
    violations: list[str] = []
    processor = function_defs(tree)
    process_incident = processor.get("_process_incident")
    if process_incident is None:
        violations.append(
            "incident_diagnosis_auto_loop_evidence_processor: "
            "_process_incident function is missing"
        )
        return violations
    for node in ast.walk(process_incident):
        if not isinstance(node, ast.Call):
            continue
        names = called_names(node)
        if not names:
            continue
        for forbidden in FORBIDDEN_PROCESSOR_CALLS:
            if forbidden in names:
                violations.append(
                    "incident_diagnosis_auto_loop_evidence_processor: "
                    f"_process_incident forbids call to {forbidden!r}"
                )
        for method in DIRECT_LIFECYCLE_METHODS:
            if method in names:
                violations.append(
                    "incident_diagnosis_auto_loop_evidence_processor: "
                    f"_process_incident forbids direct lifecycle call to {method!r}"
                )
    return violations


def check_processor_old_id_resolver(tree: ast.Module) -> list[str]:
    """Reject ``check_incident_eligibility(incident_id=...)`` in the processor.

    The processor MUST use :func:`evaluate_incident_eligibility`
    directly with the typed aggregate. The legacy ID-resolving
    ``check_incident_eligibility`` is the local-store compat wrapper.
    """
    violations: list[str] = []
    processor = function_defs(tree)
    process_incident = processor.get("_process_incident")
    if process_incident is None:
        return violations
    for node in ast.walk(process_incident):
        if not isinstance(node, ast.Call):
            continue
        names = called_names(node)
        if not names:
            continue
        if "check_incident_eligibility" in names:
            incident_id_value = call_keyword(node, "incident_id")
            if incident_id_value is not None:
                violations.append(
                    "incident_diagnosis_auto_loop_evidence_processor: "
                    "_process_incident calls check_incident_eligibility with "
                    "incident_id=…; it must call evaluate_incident_eligibility "
                    "with the typed Incident aggregate instead."
                )
    return violations


def check_processor_dispatch(tree: ast.Module) -> list[str]:
    """Confirm the processor dispatches on all three typed variants."""
    violations: list[str] = []
    processor = function_defs(tree)
    process_incident = processor.get("_process_incident")
    if process_incident is None:
        return violations
    found_variants: set[str] = set()
    case_type = match_case_type()
    if case_type is None:  # pragma: no cover - defensive
        return violations
    for node in ast.walk(process_incident):
        if not isinstance(node, case_type):
            continue
        pat = node.pattern
        if isinstance(pat, ast.MatchClass):
            if pat.cls is not None and isinstance(pat.cls, ast.Name):
                if pat.cls.id in TYPED_LOOKUP_VARIANTS:
                    found_variants.add(pat.cls.id)
    missing = [v for v in TYPED_LOOKUP_VARIANTS if v not in found_variants]
    if missing:
        violations.append(
            "incident_diagnosis_auto_loop_evidence_processor: "
            "_process_incident must dispatch on all three typed variants; "
            f"missing: {missing}"
        )
    return violations


def check_processor_no_backend_to_local_fallback(tree: ast.Module) -> list[str]:
    """Reject hidden backend-to-local fallback patterns.

    The processor must not call the local ``IncidentStore`` methods
    (already covered by FORBIDDEN_PROCESSOR_CALLS / DIRECT_LIFECYCLE_METHODS)
    and must not call the local ``fetch_incident_local`` symbol either.
    """
    violations: list[str] = []
    processor = function_defs(tree)
    process_incident = processor.get("_process_incident")
    if process_incident is None:
        return violations
    for node in ast.walk(process_incident):
        if not isinstance(node, ast.Call):
            continue
        names = called_names(node)
        if "fetch_incident_local" in names:
            violations.append(
                "incident_diagnosis_auto_loop_evidence_processor: "
                "_process_incident must not fall back to fetch_incident_local"
            )
    return violations


def check_processor_no_swallowed_lifecycle(tree: ast.Module) -> list[str]:
    """Reject ``except: pass`` blocks around lifecycle-dispatch calls.

    A bare ``except: pass`` that swallows a lifecycle-dispatch call
    would silently treat persistence failures as success. The
    contract only forbids this pattern when the swallowed body
    contains a call to ``record_diagnosis_loop_*``; best-effort
    review-packet writes that use ``except: pass`` for non-lifecycle
    operations are out of scope and remain allowed.
    """
    processor = function_defs(tree)
    process_incident = processor.get("_process_incident")
    if process_incident is None:
        return []
    violations: list[str] = []
    for node in ast.walk(process_incident):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if not (len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)):
                continue
            # Bare pass handler; the ACT forbids this around
            # lifecycle-dispatch calls.
            for sub in ast.walk(node):  # walk the WHOLE try, not just the handler
                if not isinstance(sub, ast.Call):
                    continue
                names = called_names(sub)
                if any(name in names for name in ("record_diagnosis_loop_started",
                                                  "record_diagnosis_loop_failed",
                                                  "record_diagnosis_loop_completed")):
                    violations.append(
                        "incident_diagnosis_auto_loop_evidence_processor: "
                        "forbidden ``except ...: pass`` swallowing a lifecycle-dispatch call"
                    )
                    break
    return violations


def check_processor_truthiness() -> list[str]:
    """Reject truthiness-to-``incident_not_found`` mutations."""
    source = read_text(PROCESSOR_PATH)
    if source is None:
        return []
    try:
        tree = ast.parse(source, filename=str(PROCESSOR_PATH))
    except SyntaxError:
        return []
    if contains_truthiness_to_not_found(tree):
        return [
            "incident_diagnosis_auto_loop_evidence_processor: "
            "forbidden truthiness-to-incident_not_found mutation"
        ]
    return []


def check_processor_lookup_failed_not_incident_not_found() -> list[str]:
    """Reject ``BackendIncidentLookupFailed`` mapped to ``incident_not_found``.

    The processor routes ``BackendIncidentLookupFailed`` through
    ``_failure_result_from_outcome`` which uses the bounded reason
    code mapping. A direct mapping to ``incident_not_found`` would
    violate INV-03.
    """
    source = read_text(PROCESSOR_PATH)
    if source is None:
        return []
    try:
        tree = ast.parse(source, filename=str(PROCESSOR_PATH))
    except SyntaxError:
        return []
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant):
            continue
        if node.value.value != "incident_not_found":
            continue
        if not isinstance(node.targets[0], ast.Name):
            continue
        target_name = node.targets[0].id
        if target_name in {"eligibility_reason"}:
            # Only allowed in the not-found branch; we cannot walk parents,
            # so we accept the broader invariant: the file MUST NOT assign
            # ``eligibility_reason = "incident_not_found"`` outside a
            # BackendIncidentNotFound match case. We approximate by
            # disallowing it whenever the file has a BackendIncidentLookupFailed
            # dispatch (the failure path uses the bounded code mapping).
            violations.append(
                "incident_diagnosis_auto_loop_evidence_processor: "
                "forbidden mapping of failure path to ``incident_not_found``"
            )
    # Constructor keyword-argument form: the failure path must never be
    # projected as ``AutoLoopIncidentResult(eligibility_reason=
    # "incident_not_found")``. ``ast.Assign`` scanning alone misses this
    # because the value appears as a call keyword, not an assignment.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if (
                kw.arg == "eligibility_reason"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == "incident_not_found"
            ):
                violations.append(
                    "incident_diagnosis_auto_loop_evidence_processor: "
                    "forbidden AutoLoopIncidentResult(eligibility_reason="
                    "'incident_not_found') keyword mapping of the failure path"
                )
    return violations


def check_processor_uses_aggregate_eligibility(tree: ast.Module) -> list[str]:
    """Confirm the processor uses the aggregate-based eligibility evaluator.

    The processor MUST call
    ``evaluate_incident_eligibility(incident=incident_obj, ...)`` with the
    typed :class:`Incident` aggregate; a positive presence check closes
    the gap where the verifier only forbade the legacy resolver without
    proving the correct call is made.
    """
    violations: list[str] = []
    processor = function_defs(tree)
    process_incident = processor.get("_process_incident")
    if process_incident is None:
        return violations
    found = False
    for node in ast.walk(process_incident):
        if not isinstance(node, ast.Call):
            continue
        names = called_names(node)
        if "evaluate_incident_eligibility" in names and (
            call_keyword(node, "incident") is not None
        ):
            found = True
            break
    if not found:
        violations.append(
            "incident_diagnosis_auto_loop_evidence_processor: "
            "_process_incident must call evaluate_incident_eligibility("
            "incident=…) with the typed aggregate"
        )
    return violations


# ---------------------------------------------------------------------------
# Evaluator checks
# ---------------------------------------------------------------------------


def check_evaluator_aggregate_signature() -> list[str]:
    """The aggregate evaluator must accept a typed ``Incident`` parameter."""
    tree = parse_path(EVALUATOR_PATH)
    if tree is None:
        return [f"{EVALUATOR_PATH}: cannot read or parse"]
    funcs = function_defs(tree)
    evaluator = funcs.get("evaluate_incident_eligibility")
    if evaluator is None:
        return [
            f"{EVALUATOR_PATH}: evaluate_incident_eligibility function "
            "is missing"
        ]
    violations: list[str] = []
    positional = list(evaluator.args.args)
    kwonly = list(evaluator.args.kwonlyargs)
    has_incident_kw: bool = False
    for arg in positional + kwonly:
        if arg.arg != "incident":
            continue
        has_incident_kw = True
        if arg.annotation is None:
            violations.append(
                f"{EVALUATOR_PATH}: evaluate_incident_eligibility "
                "parameter ``incident`` must be annotated"
            )
        else:
            ann = ast.unparse(arg.annotation).strip().strip("'\"")
            if ann != "Incident":
                violations.append(
                    f"{EVALUATOR_PATH}: evaluate_incident_eligibility "
                    f"parameter ``incident`` must be annotated as Incident; "
                    f"got {ann!r}"
                )
    if not has_incident_kw:
        violations.append(
            f"{EVALUATOR_PATH}: evaluate_incident_eligibility must accept "
            "a typed ``incident: Incident`` parameter"
        )
    return violations


def check_evaluator_no_lookups() -> list[str]:
    """The aggregate evaluator must not call any incident resolver."""
    tree = parse_path(EVALUATOR_PATH)
    if tree is None:
        return []
    funcs = function_defs(tree)
    evaluator = funcs.get("evaluate_incident_eligibility")
    if evaluator is None:
        return []
    violations: list[str] = []
    for node in ast.walk(evaluator):
        if not isinstance(node, ast.Call):
            continue
        names = called_names(node)
        if not names:
            continue
        for forbidden in FORBIDDEN_EVALUATOR_CALLS:
            if forbidden in names:
                violations.append(
                    f"{EVALUATOR_PATH}: evaluate_incident_eligibility "
                    f"forbids call to {forbidden!r}"
                )
    return violations


# ---------------------------------------------------------------------------
# Seam-module availability check
# ---------------------------------------------------------------------------


def seam_available_names(
    tree: ast.Module,
) -> tuple[set[str], set[str], set[str]]:
    """Return ``(defined, imported, exported)`` names for the seam module."""
    defined = set(function_defs(tree))
    imported: set[str] = set()
    exported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "__all__" and isinstance(
                    node.value, ast.List | ast.Tuple
                ):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(
                            elt.value, str
                        ):
                            exported.add(elt.value)
    return defined, imported, exported


def check_seam_required_symbols() -> list[str]:
    """The seam module must expose the required public API.

    Every symbol in :data:`REQUIRED_SEAM_SYMBOLS` must be reachable
    through the seam (defined locally, imported/re-exported, or listed
    in ``__all__``). The lifecycle-dispatch functions and the wire
    request builder must additionally be *defined* in the seam module,
    not merely re-exported.
    """
    tree = parse_path(SEAM_PATH)
    if tree is None:
        return [f"{SEAM_PATH}: cannot read or parse"]
    defined, imported, exported = seam_available_names(tree)
    available = defined | imported | exported
    violations: list[str] = []
    # Every REQUIRED_SEAM_SYMBOL must be reachable through the seam.
    for name in REQUIRED_SEAM_SYMBOLS:
        if name not in available:
            violations.append(
                f"{SEAM_PATH}: required seam symbol {name!r} is not "
                "defined, imported, or exported by the seam module"
            )
    # Lifecycle-dispatch symbols MUST be defined locally in the seam.
    for name in (
        "record_diagnosis_loop_started",
        "record_diagnosis_loop_failed",
        "record_diagnosis_loop_completed",
        "build_lifecycle_request",
    ):
        if name not in defined:
            violations.append(
                f"{SEAM_PATH}: required seam symbol {name!r} "
                "must be defined in the seam module"
            )
    return violations
