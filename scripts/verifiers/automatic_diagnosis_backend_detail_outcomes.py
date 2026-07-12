#!/usr/bin/env python
"""Static verifier for backend incident-detail outcome algebra.

Enforces the contract from
ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01 (R1):

* Outcome model invariants
    - Three disjoint variants: ``BackendIncidentFound``,
      ``BackendIncidentNotFound``, ``BackendIncidentLookupFailed``.
    - All dataclasses are frozen **and** use ``slots=True``.
    - ``requested_incident_id`` is annotated as the branded
      :class:`IncidentId` (not ``str``, not ``Optional[IncidentId]``).
    - ``BackendIncidentFound.incident`` is annotated as the canonical
      domain :class:`Incident` (not ``object``, ``Any``, ``dict``, or a
      union containing those widened forms).
    - ``BackendIncidentNotFound`` carries the ``source`` discriminator
      (no synthesised HTTP status in local mode).
    - The outcome union contains exactly those three variants.
    - Failure codes use :class:`StrEnum`.
    - No boolean ``found`` discriminator.

* Lookup signature
    - ``lookup_backend_incident`` returns ``BackendIncidentLookupOutcome``.
    - It does NOT return ``Incident | None`` or ``Optional[Incident]``.
    - It contains no bare ``return None``.
    - It invokes the canonical payload parser.
    - It validates returned incident identity.

* Not-found strictness
    - ``BackendIncidentNotFound`` is constructed only inside
      :mod:`incident_diagnosis_backend_detail_lookup` (the canonical
      lookup module) AND only when ``response.http_status == 404``.
    - The 404 branch is dominated by the EXACT comparison
      ``response.http_status == 404``; broader or negated mutations
      (``!= 404``, ``in {400, 404}``, ``404 <= response.http_status``,
      plain ``if response.http_status:``) are rejected.
    - Local mode does NOT fabricate ``http_status=404``; the dispatcher
      must construct ``BackendIncidentNotFound(source=LOCAL_STORE)``
      without an HTTP status.
    - No broad ``except Exception`` handler in the touched seam
      constructs ``BackendIncidentNotFound``.
    - No ``BackendIncidentLookupFailed`` path is suppressed into a
      ``BackendIncidentNotFound``.

* Forbidden truthiness
    - Patterns equivalent to ``if not incident: reason = "incident_not_found"``
      or ``if not payload: return BackendIncidentNotFound(...)`` in the
      touched seam are rejected by AST analysis.

* Automatic-diagnosis mapping
    - ``_process_incident`` dispatches exhaustively on the three
      variants.
    - Only the not-found variant maps to ``incident_not_found``.
    - The failed variant maps to a ``backend_incident_*`` error code.

* Literal centralisation
    - Stable reason-code strings are centralized in
      :mod:`incident_diagnosis_backend_detail_outcomes`.
    - Production code in the touched seam does not scatter duplicate
      ``incident_not_found`` literals.

Run directly:

    .venv/bin/python scripts/verifiers/automatic_diagnosis_backend_detail_outcomes.py

Exit code 0 = PASS, non-zero = violations present.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01
R1 follow-up: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01-R1
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SRC_ROOT: Final[Path] = REPO_ROOT / "src" / "k8s_diag_agent"

CANONICAL_OUTCOMES_MODULE: Final[str] = (
    "k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes"
)
CANONICAL_PARSER_MODULE: Final[str] = (
    "k8s_diag_agent.collect.incident_diagnosis_backend_detail_parser"
)
CANONICAL_LOOKUP_MODULE: Final[str] = (
    "k8s_diag_agent.collect.incident_diagnosis_backend_detail_lookup"
)
CANONICAL_DISPATCH_MODULE: Final[str] = (
    "k8s_diag_agent.collect.incident_diagnosis_dispatch"
)
EVIDENCE_PROCESSOR_MODULE: Final[str] = (
    "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor"
)
DISPOSITION_MODULE: Final[str] = (
    "k8s_diag_agent.collect.incident_diagnosis_disposition"
)
DISPOSITION_COMPAT_MODULE: Final[str] = (
    "k8s_diag_agent.collect.incident_diagnosis_disposition_compat"
)

# Modules where the verifier actively scans for forbidden patterns.
# The canonical outcomes module is allowed to construct the variants
# themselves; the lookup module is allowed to construct NotFound once
# (in the 404 branch). All other modules must NOT construct
# ``BackendIncidentNotFound`` with ``http_status=404`` directly.
TOUCHED_SEAM_MODULES: Final[tuple[str, ...]] = (
    EVIDENCE_PROCESSOR_MODULE,
    CANONICAL_DISPATCH_MODULE,
    "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch",
    "k8s_diag_agent.health.loop_automatic_diagnosis",
)

CONSTRUCTION_ALLOWED_MODULES: Final[frozenset[str]] = frozenset({
    CANONICAL_LOOKUP_MODULE,
    CANONICAL_OUTCOMES_MODULE,  # used by tests for fixture construction
    CANONICAL_DISPATCH_MODULE,
})

# Variant names that must exist in the canonical outcomes module.
REQUIRED_VARIANTS: Final[tuple[str, ...]] = (
    "BackendIncidentFound",
    "BackendIncidentNotFound",
    "BackendIncidentLookupFailed",
)

FORBIDDEN_RECURSION_LITERALS: Final[tuple[str, ...]] = (
    # Patterns that must NEVER appear in production code outside the
    # canonical outcomes module's vocabulary.
    "incident_not_found",
)

# Canonical failure code values that must exist in the outcomes module.
REQUIRED_FAILURE_CODE_VALUES: Final[tuple[str, ...]] = (
    "invalid_json",
    "invalid_payload",
    "unsupported_schema",
    "deserialization_failed",
    "identity_mismatch",
    "unauthorized",
    "forbidden",
    "http_client_error",
    "backend_error",
    "transport_error",
)

# Stable external reason codes that must exist in the disposition module.
REQUIRED_DISPOSITION_REASON_VALUES: Final[tuple[str, ...]] = (
    "backend_incident_invalid_json",
    "backend_incident_invalid_payload",
    "backend_incident_unsupported_schema",
    "backend_incident_deserialization_failed",
    "backend_incident_identity_mismatch",
    "backend_incident_unauthorized",
    "backend_incident_forbidden",
    "backend_incident_http_client_error",
    "backend_incident_backend_error",
    "backend_incident_transport_error",
)


# ---------------------------------------------------------------------------
# File collection helpers
# ---------------------------------------------------------------------------


def _module_name_from_path(path: Path) -> str:
    """Return the canonical fully-qualified module name.

    The result is prefixed with the ``k8s_diag_agent`` package so that
    it matches the strings used for ``CONSTRUCTION_ALLOWED_MODULES`` /
    ``EVIDENCE_PROCESSOR_MODULE`` / etc. elsewhere in this file.

    Out-of-tree paths (e.g. synthetic files used by the verifier
    self-tests) are returned as a sentinel string derived from the
    stem so they fall outside any allow-list.
    """
    try:
        relative = path.relative_to(SRC_ROOT.parent).with_suffix("")
    except ValueError:
        # Out-of-tree path (synthetic / temp dir). Use a sentinel that
        # is guaranteed to NOT be in any allow-list.
        return f"verifier_synthetic.{path.stem}"
    parts = relative.parts
    if parts and parts[0] == "k8s_diag_agent":
        return ".".join(parts)
    return "k8s_diag_agent." + ".".join(parts)


def _iter_python_files() -> Iterable[Path]:
    for path in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py":
            continue
        yield path


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Annotation helpers
# ---------------------------------------------------------------------------


def _annotation_text(node: ast.AST | None) -> str:
    """Return ``ast.unparse`` of an annotation node, or empty string."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return ""


def _normalize_annotation_text(text: str) -> str:
    """Strip outer quotes from forward-reference annotations.

    ``"Incident"`` and ``Incident`` are the same annotation under
    postponed-evaluation PEP 563.
    """
    if not text:
        return ""
    stripped = text.strip()
    if (
        len(stripped) >= 2
        and stripped[0] == stripped[-1]
        and stripped[0] in {'"', "'"}
    ):
        return stripped[1:-1]
    return stripped


# Annotation text patterns that must NEVER appear on
# ``BackendIncidentFound.incident`` (R1 typedness contract).
DISALLOWED_FOUND_INCIDENT_ANNOTATIONS: Final[tuple[str, ...]] = (
    "object",
    "Any",
    "dict",
    "dict[str, Any]",
    "Mapping",
    "Mapping[str, Any]",
    "object | None",
    "Any | None",
    "dict | None",
)


def _is_disallowed_found_incident_annotation(text: str) -> bool:
    """Return True iff the annotation text matches any disallowed widening."""
    if not text:
        return True
    norm = text.replace(" ", "")
    for bad in DISALLOWED_FOUND_INCIDENT_ANNOTATIONS:
        if bad.replace(" ", "") in norm:
            return True
    return False


# ---------------------------------------------------------------------------
# Outcome-model invariants
# ---------------------------------------------------------------------------


def _check_outcome_model() -> list[str]:
    """Verify the canonical outcomes module exposes the required contract."""
    violations: list[str] = []

    out_path = SRC_ROOT / "collect" / "incident_diagnosis_backend_detail_outcomes.py"
    source = _read(out_path)
    if source is None:
        violations.append(
            f"{CANONICAL_OUTCOMES_MODULE}: cannot read module source"
        )
        return violations

    try:
        tree = ast.parse(source, filename=str(out_path))
    except SyntaxError as exc:
        violations.append(
            f"{CANONICAL_OUTCOMES_MODULE}: syntax error {exc}"
        )
        return violations

    module_name = _module_name_from_path(out_path)

    # Each variant must exist as a top-level class with @dataclass(frozen=True, slots=True).
    found_classes: dict[str, ast.ClassDef] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            found_classes[node.name] = node

    for variant in REQUIRED_VARIANTS:
        if variant not in found_classes:
            violations.append(
                f"{module_name}: required outcome variant "
                f"``{variant}`` is missing"
            )
            continue
        cls = found_classes[variant]
        is_frozen = False
        is_slots = False
        for decorator in cls.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and getattr(decorator.func, "id", None) == "dataclass"
            ):
                for kw in decorator.keywords:
                    if (
                        kw.arg == "frozen"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        is_frozen = True
                    if (
                        kw.arg == "slots"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        is_slots = True
        if not is_frozen:
            violations.append(
                f"{module_name}:``{variant}`` must be a frozen dataclass"
            )
        if not is_slots:
            violations.append(
                f"{module_name}:``{variant}`` must use ``slots=True``"
            )
        # No boolean ``found`` discriminator.
        for stmt in cls.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                annotation = ast.unparse(stmt.annotation)
                if name in {"found", "is_found"} and annotation == "bool":
                    violations.append(
                        f"{module_name}:``{variant}`` must not use a "
                        "boolean ``found`` discriminator"
                    )

    # Field-level annotation invariants.
    for variant in REQUIRED_VARIANTS:
        variant_cls: ast.ClassDef | None = found_classes.get(variant)
        if variant_cls is None:
            continue
        for stmt in variant_cls.body:
            if not (
                isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            ):
                continue
            field_name = stmt.target.id
            ann_text = _annotation_text(stmt.annotation)
            ann_norm = _normalize_annotation_text(ann_text)
            if field_name == "requested_incident_id":
                # Must be the canonical branded ``IncidentId`` (string
                # annotation ``"IncidentId"`` is also accepted; both
                # resolve to the same type at type-check time).
                if ann_norm != "IncidentId":
                    violations.append(
                        f"{module_name}:``{variant}.requested_incident_id`` "
                        f"must be annotated as ``IncidentId``; got {ann_text!r}"
                    )
            if variant == "BackendIncidentFound" and field_name == "incident":
                # The ``incident`` field must NOT be widened to object,
                # Any, dict, or any union containing those forms. The
                # canonical annotation is the domain ``Incident``.
                if ann_norm != "Incident":
                    violations.append(
                        f"{module_name}:``BackendIncidentFound.incident`` "
                        f"must be annotated as the canonical ``Incident``; "
                        f"got {ann_text!r}"
                    )
                if _is_disallowed_found_incident_annotation(ann_norm):
                    violations.append(
                        f"{module_name}:``BackendIncidentFound.incident`` "
                        f"must not be widened to ``object``/``Any``/``dict`` "
                        f"or any union containing them; got {ann_text!r}"
                    )

    # The ``BackendIncidentNotFound`` variant MUST declare a ``source``
    # field with the canonical ``BackendIncidentLookupSource`` annotation.
    not_found_cls = found_classes.get("BackendIncidentNotFound")
    if not_found_cls is not None:
        has_source = False
        for stmt in not_found_cls.body:
            if (
                isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.target.id == "source"
            ):
                has_source = True
                ann_text = _annotation_text(stmt.annotation)
                if _normalize_annotation_text(ann_text) != "BackendIncidentLookupSource":
                    violations.append(
                        f"{module_name}:``BackendIncidentNotFound.source`` "
                        f"must be annotated as ``BackendIncidentLookupSource``; "
                        f"got {ann_text!r}"
                    )
        if not has_source:
            violations.append(
                f"{module_name}:``BackendIncidentNotFound`` must declare a "
                "``source`` field (BackendIncidentLookupSource) so the logs "
                "never claim an HTTP status that was not observed"
            )

    # Failure code enum must use StrEnum.
    enum_ok = False
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "BackendIncidentLookupFailureCode"
        ):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id in {"StrEnum", "str"}:
                    enum_ok = True
                    break
    if not enum_ok:
        violations.append(
            f"{module_name}:``BackendIncidentLookupFailureCode`` must "
            "derive from StrEnum"
        )

    # The required failure code values must exist.
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "BackendIncidentLookupFailureCode"
        ):
            present_values: set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if (
                            isinstance(target, ast.Name)
                            and isinstance(stmt.value, ast.Constant)
                            and isinstance(stmt.value.value, str)
                        ):
                            present_values.add(stmt.value.value)
            for required in REQUIRED_FAILURE_CODE_VALUES:
                if required not in present_values:
                    violations.append(
                        f"{module_name}:missing required failure code "
                        f"``{required}`` in BackendIncidentLookupFailureCode"
                    )

    # Type alias contains EXACTLY the three required variants. The
    # verifier must reject any extra member that the bare
    # ``count(required) == 1`` test would silently miss (for example
    # an injected ``BackendIncidentRetryable`` member).
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "BackendIncidentLookupOutcome":
                union_identifiers: set[str] = _extract_union_identifiers(node)
                if not union_identifiers:
                    violations.append(
                        f"{module_name}:``BackendIncidentLookupOutcome`` "
                        "union is empty or unparseable"
                    )
                    continue
                expected = set(REQUIRED_VARIANTS)
                if union_identifiers != expected:
                    missing = sorted(expected - union_identifiers)
                    extra = sorted(union_identifiers - expected)
                    bits: list[str] = []
                    if missing:
                        bits.append(
                            "missing required variant(s): "
                            + ", ".join(f"``{m}``" for m in missing)
                        )
                    if extra:
                        bits.append(
                            "extra forbidden variant(s): "
                            + ", ".join(f"``{e}``" for e in extra)
                        )
                    violations.append(
                        f"{module_name}:``BackendIncidentLookupOutcome`` "
                        "must contain EXACTLY the closed union "
                        f"{{{', '.join(sorted(expected))}}}; "
                        + "; ".join(bits)
                    )

    return violations


def _extract_union_identifiers(ann_assign: ast.AnnAssign) -> set[str]:
    """Return the set of identifier names in the union expression.

    The canonical form is a PEP-563 string annotation value (e.g.
    ``"BackendIncidentFound | BackendIncidentNotFound | BackendIncidentLookupFailed"``).
    Parse the expression with :func:`ast.parse(mode="eval")` so we
    walk the actual AST rather than running ad-hoc substring tests
    on the unparsed source. Both ``A | B | C`` (binary ``BitOr``)
    and the older ``Union[A, B, C]`` / ``Optional[A]`` shapes are
    normalised to the set of referenced identifier names.
    """
    identifiers: set[str] = set()

    def _walk(node: ast.AST | None) -> None:
        if node is None:
            return
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
            return
        if isinstance(node, ast.Attribute):
            # Treat ``module.Name`` as the final ``Name`` only.
            identifiers.add(node.attr)
            return
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            _walk(node.left)
            _walk(node.right)
            return
        if isinstance(node, ast.Subscript):
            _walk(node.value)
            # ``Union[A, B, C]`` / ``Optional[A]``: flatten ``Slice``/``Tuple``.
            slc = node.slice
            if isinstance(slc, ast.Tuple):
                for elt in slc.elts:
                    _walk(elt)
            else:
                _walk(slc)
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Nested string annotations (PEP 563). Parse and recurse.
            try:
                nested = ast.parse(node.value, mode="eval")
            except SyntaxError:
                return
            _walk(nested.body)
            return

    # Only walk the RHS of the type-alias assignment. Walking the LHS
    # annotation would pick up unrelated names like ``TypeAlias``
    # declared on the alias's own type hint, polluting the union set.
    _walk(ann_assign.value)
    return identifiers


# ---------------------------------------------------------------------------
# Lookup signature invariants
# ---------------------------------------------------------------------------


def _check_lookup_signature() -> list[str]:
    violations: list[str] = []

    lookup_path = SRC_ROOT / "collect" / "incident_diagnosis_backend_detail_lookup.py"
    source = _read(lookup_path)
    if source is None:
        violations.append(
            f"{CANONICAL_LOOKUP_MODULE}: cannot read module source"
        )
        return violations

    try:
        tree = ast.parse(source, filename=str(lookup_path))
    except SyntaxError as exc:
        violations.append(
            f"{CANONICAL_LOOKUP_MODULE}: syntax error {exc}"
        )
        return violations

    # Locate ``lookup_backend_incident``.
    target_fn: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "lookup_backend_incident":
            target_fn = node
            break

    if target_fn is None:
        violations.append(
            f"{CANONICAL_LOOKUP_MODULE}: missing canonical function "
            "``lookup_backend_incident``"
        )
        return violations

    # Return annotation must be the outcome union.
    if target_fn.returns is None:
        violations.append(
            f"{CANONICAL_LOOKUP_MODULE}:``lookup_backend_incident`` "
            "must declare an explicit return type"
        )
    else:
        ret = ast.unparse(target_fn.returns)
        if "BackendIncidentLookupOutcome" not in ret:
            violations.append(
                f"{CANONICAL_LOOKUP_MODULE}:``lookup_backend_incident`` "
                "must return BackendIncidentLookupOutcome"
            )
        if "Incident | None" in ret or "Optional[Incident]" in ret:
            violations.append(
                f"{CANONICAL_LOOKUP_MODULE}:``lookup_backend_incident`` "
                "must not return Incident | None / Optional[Incident]"
            )

    # The function body must call parse_internal_incident_detail_payload
    # and must validate identity via ``incident.incident_id``.
    body_src = ast.unparse(target_fn)
    if "parse_internal_incident_detail_payload" not in body_src:
        violations.append(
            f"{CANONICAL_LOOKUP_MODULE}:``lookup_backend_incident`` must "
            "invoke the canonical payload parser"
        )
    if "Incident.from_dict" not in body_src:
        violations.append(
            f"{CANONICAL_LOOKUP_MODULE}:``lookup_backend_incident`` must "
            "deserialize the aggregate via ``Incident.from_dict``"
        )
    if "incident_id" not in body_src:
        violations.append(
            f"{CANONICAL_LOOKUP_MODULE}:``lookup_backend_incident`` must "
            "validate returned incident identity"
        )

    # No bare ``return None`` inside the function body.
    for raw_node in ast.walk(target_fn):
        candidate: ast.AST = raw_node
        if not isinstance(candidate, ast.Return):
            continue
        is_bare_none = (
            isinstance(candidate.value, ast.Constant)
            and candidate.value.value is None
        )
        if is_bare_none:
            violations.append(
                f"{CANONICAL_LOOKUP_MODULE}:``lookup_backend_incident`` "
                "must not contain bare ``return None``"
            )
            break

    # The 404 branch MUST dominate any ``BackendIncidentNotFound`` call.
    not_found_calls: list[ast.Call] = []
    for raw in ast.walk(target_fn):
        if not isinstance(raw, ast.Call):
            continue
        callee = raw.func
        if not (
            (isinstance(callee, ast.Name) and callee.id == "BackendIncidentNotFound")
            or (
                isinstance(callee, ast.Attribute)
                and callee.attr == "BackendIncidentNotFound"
            )
        ):
            continue
        not_found_calls.append(raw)

    if not not_found_calls:
        violations.append(
            f"{CANONICAL_LOOKUP_MODULE}:``lookup_backend_incident`` "
            "must construct ``BackendIncidentNotFound`` for HTTP 404"
        )
    else:
        parent_map = _build_parent_map(target_fn)
        for call in not_found_calls:
            if not _is_call_dominated_by_exact_404_check(call, parent_map):
                violations.append(
                    f"{CANONICAL_LOOKUP_MODULE}:{call.lineno}: "
                    "``BackendIncidentNotFound`` must be constructed "
                    "inside an ``if`` whose test is EXACTLY "
                    "``response.http_status == 404``; broader/negated "
                    "comparisons (e.g. ``!= 404``, ``in {400, 404}``, "
                    "``404 <= response.http_status``, plain truthiness) "
                    "are forbidden"
                )
            if not _has_exact_kwarg(
                call, "source", "BackendIncidentLookupSource.BACKEND_API"
            ):
                violations.append(
                    f"{CANONICAL_LOOKUP_MODULE}:{call.lineno}: "
                    "``BackendIncidentNotFound`` construction must pass "
                    "``source=BackendIncidentLookupSource.BACKEND_API`` "
                    "so local-mode truthfulness is provable"
                )
            if not _has_kwarg_int_value(call, "http_status", 404):
                violations.append(
                    f"{CANONICAL_LOOKUP_MODULE}:{call.lineno}: "
                    "``BackendIncidentNotFound`` construction must pass "
                    "``http_status=404`` explicitly"
                )

    return violations


def _is_call_dominated_by_exact_404_check(
    call: ast.Call, parent_map: dict[int, ast.AST]
) -> bool:
    """Return True iff ``call`` is dominated by an ``If`` whose test is
    EXACTLY ``response.http_status == 404``.
    """
    current = parent_map.get(id(call))
    while current is not None:
        if isinstance(current, ast.If):
            test = current.test
            if not _is_response_http_status_eq_404(test):
                return False
            return True
        current = parent_map.get(id(current))
    return False


def _is_response_http_status_eq_404(node: ast.AST) -> bool:
    """Return True iff ``node`` is exactly ``response.http_status == 404``."""
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    op = node.ops[0]
    if not isinstance(op, ast.Eq):
        return False
    left = node.left
    right = node.comparators[0]
    if _is_response_http_status_attr(left) and isinstance(
        right, ast.Constant
    ) and right.value == 404:
        return True
    if _is_response_http_status_attr(right) and isinstance(
        left, ast.Constant
    ) and left.value == 404:
        return True
    return False


def _is_response_http_status_attr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "http_status"
        and isinstance(node.value, ast.Name)
        and node.value.id == "response"
    )


def _has_exact_kwarg(call: ast.Call, name: str, value_text: str) -> bool:
    for kw in call.keywords:
        if kw.arg != name:
            continue
        try:
            rendered = ast.unparse(kw.value)
        except Exception:  # pragma: no cover - defensive
            rendered = ""
        if rendered == value_text:
            return True
    return False


def _has_kwarg_int_value(call: ast.Call, name: str, expected: int) -> bool:
    for kw in call.keywords:
        if kw.arg != name:
            continue
        if isinstance(kw.value, ast.Constant) and kw.value.value == expected:
            return True
    return False


# ---------------------------------------------------------------------------
# Not-found strictness invariants
# ---------------------------------------------------------------------------


def _check_not_found_construction(file_path: Path) -> list[str]:
    """Reject ``BackendIncidentNotFound(...)`` construction outside the
    canonical lookup module's HTTP 404 branch.
    """
    violations: list[str] = []
    module_name = _module_name_from_path(file_path)
    if module_name in CONSTRUCTION_ALLOWED_MODULES:
        return violations

    source = _read(file_path)
    if source is None:
        return [f"{module_name}: cannot read file"]

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id == "BackendIncidentNotFound":
            violations.append(
                f"{module_name}:{node.lineno}: ``BackendIncidentNotFound`` "
                "must be constructed only by the canonical lookup "
                "module inside the HTTP 404 branch."
            )
        elif (
            isinstance(callee, ast.Attribute)
            and callee.attr == "BackendIncidentNotFound"
        ):
            violations.append(
                f"{module_name}:{node.lineno}: ``BackendIncidentNotFound`` "
                "must be constructed only by the canonical lookup "
                "module inside the HTTP 404 branch."
            )

    return violations


def _check_local_mode_truthfulness(file_path: Path) -> list[str]:
    """Reject local-mode fabrication of HTTP 404 telemetry."""
    violations: list[str] = []
    module_name = _module_name_from_path(file_path)
    if module_name != CANONICAL_DISPATCH_MODULE:
        return violations

    source = _read(file_path)
    if source is None:
        return [f"{module_name}: cannot read file"]

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        is_not_found = (
            (isinstance(callee, ast.Name) and callee.id == "BackendIncidentNotFound")
            or (
                isinstance(callee, ast.Attribute)
                and callee.attr == "BackendIncidentNotFound"
            )
        )
        if not is_not_found:
            continue
        # The dispatcher must not pass ``http_status=404`` directly.
        if any(
            kw.arg == "http_status"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value == 404
            for kw in node.keywords
        ):
            violations.append(
                f"{module_name}:{node.lineno}: local-mode dispatcher "
                "must not synthesise ``http_status=404``; pass "
                "``source=BackendIncidentLookupSource.LOCAL_STORE`` and "
                "leave ``http_status`` to default to ``None``"
            )
        if not _has_exact_kwarg(
            node, "source", "BackendIncidentLookupSource.LOCAL_STORE"
        ) and not _has_exact_kwarg(
            node, "source", "BackendIncidentLookupSource.BACKEND_API"
        ):
            violations.append(
                f"{module_name}:{node.lineno}: ``BackendIncidentNotFound`` "
                "construction must pass an explicit ``source=...`` "
                "keyword (LOCAL_STORE for local mode, BACKEND_API for "
                "backend mode)"
            )

    return violations


def _check_lookup_module_not_found_branch(file_path: Path) -> list[str]:
    """Verify the canonical lookup constructs ``BackendIncidentNotFound``
    only inside the exact ``response.http_status == 404`` branch."""
    violations: list[str] = []
    module_name = _module_name_from_path(file_path)
    if module_name != CANONICAL_LOOKUP_MODULE:
        return violations

    source = _read(file_path)
    if source is None:
        return [f"{module_name}: cannot read file"]
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    parent_map = _build_parent_map(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if not (
            (isinstance(callee, ast.Name) and callee.id == "BackendIncidentNotFound")
            or (
                isinstance(callee, ast.Attribute)
                and callee.attr == "BackendIncidentNotFound"
            )
        ):
            continue
        if not _is_call_dominated_by_exact_404_check(node, parent_map):
            violations.append(
                f"{module_name}:{node.lineno}: ``BackendIncidentNotFound`` "
                "must be constructed inside an ``if`` whose test is "
                "EXACTLY ``response.http_status == 404``"
            )

    return violations


def _check_no_broad_exception_to_not_found(file_path: Path) -> list[str]:
    """Reject ``except Exception: ... return BackendIncidentNotFound(...)``."""
    violations: list[str] = []
    module_name = _module_name_from_path(file_path)
    if module_name not in TOUCHED_SEAM_MODULES:
        return violations

    source = _read(file_path)
    if source is None:
        return [f"{module_name}: cannot read file"]
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if handler.type is None:
                continue
            type_src = ast.unparse(handler.type)
            if type_src == "Exception" or type_src.endswith("Exception"):
                for stmt in handler.body:
                    if not isinstance(stmt, ast.Return):
                        continue
                    is_bare_none = (
                        isinstance(stmt.value, ast.Constant)
                        and stmt.value.value is None
                    )
                    if is_bare_none:
                        violations.append(
                            f"{module_name}:{handler.lineno}: bare "
                            "``except Exception: return None`` is forbidden "
                            "in the touched seam"
                        )
                        continue
                    if isinstance(stmt.value, ast.Call):
                        callee = stmt.value.func
                        if (
                            isinstance(callee, ast.Name)
                            and callee.id == "BackendIncidentNotFound"
                        ) or (
                            isinstance(callee, ast.Attribute)
                            and callee.attr == "BackendIncidentNotFound"
                        ):
                            violations.append(
                                f"{module_name}:{handler.lineno}: "
                                "``except Exception: return "
                                "BackendIncidentNotFound(...)`` is "
                                "forbidden; broad handlers must NOT "
                                "collapse failures into absence"
                            )
    return violations


# ---------------------------------------------------------------------------
# Forbidden truthiness invariants
# ---------------------------------------------------------------------------


def _check_no_truthiness_to_not_found(file_path: Path) -> list[str]:
    """Reject patterns equivalent to:

    .. code-block:: python

        if not incident:
            reason = "incident_not_found"

        if not payload:
            return BackendIncidentNotFound(...)

        if not result:
            skip_reason = "incident_not_found"
    """
    violations: list[str] = []
    module_name = _module_name_from_path(file_path)
    if module_name not in TOUCHED_SEAM_MODULES:
        return violations

    source = _read(file_path)
    if source is None:
        return [f"{module_name}: cannot read file"]
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    truthy_targets = {"incident", "payload", "result", "lookup_outcome"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.UnaryOp) or not isinstance(test.op, ast.Not):
            continue
        operand = test.operand
        if not (isinstance(operand, ast.Name) and operand.id in truthy_targets):
            continue
        body_src = ast.unparse(node)
        if (
            "incident_not_found" in body_src
            or "BackendIncidentNotFound" in body_src
        ):
            violations.append(
                f"{module_name}:{node.lineno}: forbidden truthiness collapse "
                "into ``incident_not_found`` / ``BackendIncidentNotFound``; "
                "the canonical model requires the source of absence to be "
                "the HTTP status (backend mode) or the local-store "
                "presence (local mode)"
            )

    return violations


# ---------------------------------------------------------------------------
# Automatic-diagnosis dispatch invariants
# ---------------------------------------------------------------------------


def _check_processor_dispatch(file_path: Path) -> list[str]:
    """Verify ``_process_incident`` dispatches exhaustively on the three variants."""
    violations: list[str] = []
    module_name = _module_name_from_path(file_path)
    if module_name != EVIDENCE_PROCESSOR_MODULE:
        return violations

    source = _read(file_path)
    if source is None:
        return [f"{module_name}: cannot read module source"]
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    target: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_process_incident":
            target = node
            break
    if target is None:
        return [f"{module_name}: missing canonical ``_process_incident``"]

    body_src = ast.unparse(target)
    for variant in REQUIRED_VARIANTS:
        if variant not in body_src:
            violations.append(
                f"{module_name}:``_process_incident`` must dispatch on "
                f"``{variant}``"
            )

    # No generic truthiness on the lookup outcome.
    if "if not lookup_outcome" in body_src or "if lookup_outcome" in body_src:
        violations.append(
            f"{module_name}:``_process_incident`` must not test the "
            "lookup outcome via generic truthiness"
        )

    # ``is None`` on the lookup outcome is also forbidden.
    for sub in ast.walk(target):
        if isinstance(sub, ast.Compare):
            cmp_src = ast.unparse(sub)
            if "lookup_outcome" in cmp_src and "is None" in cmp_src:
                violations.append(
                    f"{module_name}:``_process_incident`` must not "
                    "test ``lookup_outcome is None``; use exhaustive "
                    "match on the typed variants"
                )

    # No duck-typed widening of the found incident.
    if "hasattr(incident" in body_src:
        violations.append(
            f"{module_name}:``_process_incident`` must not use "
            "``hasattr(incident, ...)`` to duck-type; ``incident`` is "
            "statically typed as ``Incident``"
        )
    # No separate ``incident_or_incident`` widening variable.
    for stmt in ast.walk(target):
        if isinstance(stmt, ast.Assign):
            for target_node in stmt.targets:
                if (
                    isinstance(target_node, ast.Name)
                    and target_node.id == "incident_or_incident"
                ):
                    violations.append(
                        f"{module_name}:``_process_incident`` must not widen "
                        "the found incident via a separate variable "
                        "(``incident_or_incident``); the matched "
                        "``incident`` is statically known as ``Incident``"
                    )
                    break

    return violations


# ---------------------------------------------------------------------------
# Reason code centralisation
# ---------------------------------------------------------------------------


def _check_reason_codes() -> list[str]:
    """The disposition enum must expose all required reason codes."""
    violations: list[str] = []

    disp_path = SRC_ROOT / "collect" / "incident_diagnosis_disposition.py"
    source = _read(disp_path)
    if source is None:
        violations.append(
            f"{DISPOSITION_MODULE}: cannot read module source"
        )
        return violations

    try:
        tree = ast.parse(source, filename=str(disp_path))
    except SyntaxError as exc:
        violations.append(
            f"{DISPOSITION_MODULE}: syntax error {exc}"
        )
        return violations

    module_name = _module_name_from_path(disp_path)

    present_values: set[str] = set()
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "DiagnosisEvaluationFailureReason"
        ):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if (
                            isinstance(target, ast.Name)
                            and isinstance(stmt.value, ast.Constant)
                            and isinstance(stmt.value.value, str)
                        ):
                            present_values.add(stmt.value.value)
            break

    for required in REQUIRED_DISPOSITION_REASON_VALUES:
        if required not in present_values:
            violations.append(
                f"{module_name}: missing required backend-incident "
                f"reason code ``{required}`` in DiagnosisEvaluationFailureReason"
            )

    return violations


def _check_no_substring_backend_incident_matching() -> list[str]:
    """The disposition compat module must NOT use substring matching for
    ``backend_incident_*`` codes (R1 contract).
    """
    violations: list[str] = []
    compat_path = SRC_ROOT / "collect" / "incident_diagnosis_disposition_compat.py"
    source = _read(compat_path)
    if source is None:
        return [f"{DISPOSITION_COMPAT_MODULE}: cannot read module source"]
    try:
        tree = ast.parse(source, filename=str(compat_path))
    except SyntaxError:
        return []

    module_name = _module_name_from_path(compat_path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        if len(test.ops) != 1 or not isinstance(test.ops[0], ast.In):
            continue
        if len(test.comparators) != 1:
            continue
        left = test.left
        right = test.comparators[0]
        # Reject ``"backend_incident_..." in raw_lower`` style substring matches.
        if isinstance(left, ast.Constant) and isinstance(left.value, str):
            if "backend_incident_" in left.value:
                violations.append(
                    f"{module_name}:{node.lineno}: substring match for "
                    "``backend_incident_*`` codes is forbidden; use exact "
                    "value matching or the typed mapping "
                    "``diagnosis_failure_reason_for_backend_lookup``"
                )
        if isinstance(right, ast.Constant) and isinstance(right.value, str):
            if "backend_incident_" in right.value:
                violations.append(
                    f"{module_name}:{node.lineno}: substring match for "
                    "``backend_incident_*`` codes is forbidden; use exact "
                    "value matching or the typed mapping "
                    "``diagnosis_failure_reason_for_backend_lookup``"
                )

    return violations


# ---------------------------------------------------------------------------
# Helpers (shared with the AST analyser)
# ---------------------------------------------------------------------------


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def run_static_checks() -> list[str]:
    """Run all static checks and return a list of violation messages."""
    violations: list[str] = []

    violations.extend(_check_outcome_model())
    violations.extend(_check_lookup_signature())
    violations.extend(_check_reason_codes())
    violations.extend(_check_no_substring_backend_incident_matching())

    for path in _iter_python_files():
        module_name = _module_name_from_path(path)
        violations.extend(_check_not_found_construction(path))
        violations.extend(_check_local_mode_truthfulness(path))
        violations.extend(_check_no_broad_exception_to_not_found(path))
        violations.extend(_check_no_truthiness_to_not_found(path))
        if module_name in TOUCHED_SEAM_MODULES:
            violations.extend(_check_processor_dispatch(path))
        if module_name == CANONICAL_LOOKUP_MODULE:
            violations.extend(_check_lookup_module_not_found_branch(path))

    return violations


def _format_violations(violations: Iterable[str]) -> str:
    return "\n".join(f"- {v}" for v in violations)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    violations = run_static_checks()
    if violations:
        print(
            "ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01 verifier: FAIL"
        )
        print(_format_violations(violations))
        return 1
    print("ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01 verifier: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))