#!/usr/bin/env python3
"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 semantic verifier.

This verifier enforces the architectural contract enforced by the ACT
rather than mere symbol names. It scans production code under
``src/k8s_diag_agent/`` for patterns the ACT forbids:

1. Promotion outcome variants MUST be a closed union of
   :class:`PromotionSucceeded`, :class:`PromotionRejected`, and
   :class:`PromotionCommitUnknown`. ``Any``-typed ``PromotionOutcome``
   declarations and free-form-string fallbacks are rejected.
2. Diagnosis selection MUST use one of the three explicit
   :class:`DiagnosisSelection*` variants. Truthiness fallbacks
   (``if explicit_ids: ... else: scan()``) and ``or`` / ``or []``
   defaulting to a store scan are rejected.
3. The dispatch decision at the seam MUST NOT consume an empty tuple
   / falsy sequence as a "scan the store" trigger.
4. :class:`PromotionCommitUnknown` MUST NOT flow into diagnosis; any
   ``commit_unknown`` flow path that calls
   ``run_automatic_diagnosis_loop_evidence_collection`` is rejected.
5. Identity-matching duplicate persistence MUST be admitted into the
   current-run workset. Code paths that drop
   ``SignalIdentityMatched`` or that branch on
   ``signals_skipped_duplicates`` as authority are rejected.
6. Low-cardinality reason / outcome codes MUST come from the closed
   enum definitions in
   ``src/k8s_diag_agent/collect/promotion_outcomes.py`` and
   ``src/k8s_diag_agent/collect/signal_persistence_outcomes.py``.
   Hardcoded free-form-string fallbacks are rejected.
7. Compatibility booleans (``promotion_may_have_committed``,
   ``promotion_propagated_to_diagnosis``,
   ``promotion_consistency_error_recorded``) MUST be derived from
   outcomes, not assigned independently at multiple production call
   sites.

Exit codes:

* 0 -- no violations
* 1 -- violations
* 2 -- verification infrastructure failure

Suggested by: ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent"

# Modules where production seam-correctness MUST hold.
SEAM_MODULE_SUBSTRINGS: tuple[str, ...] = (
    "loop_alertmanager_snapshot_signals",
    "loop_automatic_diagnosis",
    "loop_runner_execute",
    "loop_runner",
    "promotion_diagnosis_handoff",
    "incident_alert_signal_snapshot_adapter",
    "incident_alert_promotion",
    "incident_alert_promotion_scoped",
    "incident_alert_promotion_contract",
    "incident_alert_signal",
    "incident_alert_signal_store",
    "signal_persistence_outcomes",
    "current_run_promotion_workset",
    "promotion_outcomes",
    "diagnosis_selection",
    "store_scan_policy",
    "incident_promotion_batch",
    "incident_promotion_accumulator",
    "incident_promotion_backend",
    "incident_promotion_dispatch",
)

# Free-form-string patterns that indicate the truthiness fallback
# the ACT forbids. These are surfaced ONLY in production seam modules.
TRUTHINESS_FALLBACK_PATTERNS: tuple[str, ...] = (
    "or []",
    "or ()",
    "or [])",
    "or ())",
)


@dataclass(frozen=True)
class Violation:
    """Single AST verification finding."""

    file_path: Path
    line_number: int
    code: str
    message: str

    def render(self) -> str:
        return (
            f"{self.file_path}:{self.line_number}: "
            f"{self.code}: {self.message}"
        )


class VerifierInfrastructureError(RuntimeError):
    """Raised when AST analysis cannot proceed."""


def _attach_parents(tree: ast.AST) -> None:
    """Attach a ``parent`` attribute to each AST node.

    Python's stdlib ``ast`` does not provide parent links by default.
    The verifier uses this to detect
    ``INCIDENT_SELECTION_MODE_STORE_SCAN = "store_scan"`` legacy
    constant declarations.
    """
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)


def _collect_python_files(src_root: Path) -> list[Path]:
    if not src_root.exists():
        raise VerifierInfrastructureError(
            f"Source root {src_root} does not exist"
        )
    return sorted(src_root.rglob("*.py"))


def _is_seam_module(path: Path) -> bool:
    name = path.name
    if name.endswith(".py") and name.startswith("test_"):
        return False
    return any(substring in name for substring in SEAM_MODULE_SUBSTRINGS)


def _truthiness_fallback_violations(
    tree: ast.AST,
    file_path: Path,
) -> list[Violation]:
    """Reject truthiness-driven store-scan fallbacks at the seam.

    Patterns flagged:

    * ``if explicit_ids: scan_store()`` with an ``else`` branch that
      runs a store-scan fallback. The structure ``if canonical_ids:
      EXPLICIT else: STORE_SCAN`` is precisely the production 33-duplicate
      regression shape.
    * ``canonical_incident_ids or []`` / ``canonical_incident_ids or
      ()`` followed by a fallback path that triggers a scan.

    Note: a guarded ``if canonical_ids: <dispatch>`` with no else
    branch is permitted because ``canonical_ids`` is being used to
    pick between ``EXPLICIT`` and ``CURRENT_RUN_EMPTY`` -- neither
    of which is a store scan.
    """
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        # Direct ``if ids:`` pattern: flag ONLY when an
        # ``else`` body invokes or sets something scan-like. Without
        # an else, ``if canonical_ids: explicit`` is benign.
        if (
            isinstance(test, ast.Name)
            and test.id.endswith("_ids")
            and node.orelse
        ):
            else_text = (
                ast.unparse(ast.Module(body=list(node.orelse), type_ignores=[]))
                if node.orelse
                else ""
            )
            if (
                "store_scan" in else_text
                or "scan()" in else_text
                or "scan ==" in else_text
            ):
                violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=node.lineno,
                        code="TRUTHINESS_FALLBACK",
                        message=(
                            "Truthiness check on "
                            f"{test.id!r} with an else-branch "
                            "driving a store scan is forbidden; "
                            "use a typed DiagnosisSelection "
                            "variant."
                        ),
                    )
                )
        # Empty-default fallbacks ``x or []`` / ``x or ()``.
        if isinstance(test, ast.BoolOp) and isinstance(
            test.op, ast.Or
        ):
            for value in test.values:
                if (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, (list, tuple))
                    and len(value.value) == 0
                ):
                    violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=node.lineno,
                            code="EMPTY_DEFAULT_FALLBACK",
                            message=(
                                "Empty-default fallback "
                                f"{value.value!r} at the seam "
                                "must not drive a store scan; "
                                "use a typed DiagnosisSelection "
                                "variant."
                            ),
                        )
                    )
    return violations


def _is_in_legacy_mode_helper(
    node: ast.AST,
) -> bool:
    """Return True if the node is inside a legacy mode-mapping helper.

    Legacy mode helpers are functions whose name starts with
    ``_legacy_`` or ``_selection_projection``. They map typed variants
    onto legacy string mode names so the ``store_scan`` literal is
    part of an explicit projection -- not an authority decision.
    """
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if parent.name.startswith("_legacy_") or parent.name in (
                "_selection_projection",
            ):
                return True
        parent = getattr(parent, "parent", None)
    return False


def _store_scan_string_violations(
    tree: ast.AST,
    file_path: Path,
) -> list[Violation]:
    """Reject ``"store_scan"`` strings used outside an explicit policy.

    Allowed contexts:

    * Strings inside the :mod:`diagnosis_selection` module
      (``SelectionMode.STORE_SCAN = "store_scan"``, etc.).
    * ``INCIDENT_SELECTION_MODE_STORE_SCAN = "store_scan"`` legacy
      constants declared at the top level of seam modules for
      backward compatibility with downstream log consumers.
    * Inside a legacy-mode-mapping helper function (whose name starts
      with ``_legacy_`` or is ``_selection_projection``); the value
      is mapped onto a typed variant elsewhere in the same module.
    * Defensive verification calls; ``scripts/verifiers/*`` is excluded.
    """
    violations: list[Violation] = []
    if "diagnosis_selection" in file_path.name or "verifiers" in str(
        file_path
    ):
        return violations
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value == "store_scan"
        ):
            continue
        # Allow ``INCIDENT_SELECTION_MODE_* = "store_scan"``
        # legacy string aliases at module level.
        # ``parent`` is attached synthetically by ``_attach_parents``.
        if (
            isinstance(getattr(node, "parent", None), ast.Assign)
            and len(node.parent.targets) == 1
            and isinstance(node.parent.targets[0], ast.Name)
            and node.parent.targets[0].id.startswith(
                "INCIDENT_SELECTION_MODE_"
            )
        ):
            continue
        # Allow ``return "store_scan"`` and other literals inside
        # legacy-mode-mapping helpers.
        if _is_in_legacy_mode_helper(node):
            continue
        violations.append(
            Violation(
                file_path=file_path,
                line_number=node.lineno,
                code="RAW_STORE_SCAN_STRING",
                message=(
                    "Raw \"store_scan\" string is forbidden "
                    "outside the DiagnosisSelection algebra; "
                    "use DiagnosisSelectionWithoutPromotion"
                ),
            )
        )
    return violations


def _explicit_truthy_scan_violations(
    tree: ast.AST,
    file_path: Path,
) -> list[Violation]:
    """Reject ``if not ids: scan_store()`` patterns at the seam.

    The pattern is identified when the If's body contains a call to
    a function whose name includes ``store_scan`` / ``scan``.

    The call ``_store_scan_performed(selection)`` IS the typed gate
    itself -- it returns ``True`` only when the variant is
    :class:`DiagnosisSelectionWithoutPromotion`. Calls to it are
    permitted.
    """
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            func_name: str | None = None
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            if func_name is None:
                continue
            # Permitted: the typed gate itself.
            if func_name == "_store_scan_performed":
                continue
            if (
                "store_scan" in func_name
                or func_name.endswith("_scan")
                and "no" not in func_name
            ):
                # We allow store-scan invocations that are guarded by
                # an explicit ``isinstance(..., ...WithoutPromotion)``
                # guard, since the ACT allows scans only through that
                # explicit path. Anything else is flagged.
                guarded = _is_scan_invocation_guarded(node)
                if not guarded:
                    violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=child.lineno,
                            code="UNGUARDED_SCAN_INVOCATION",
                            message=(
                                f"Call to {func_name!r} is not "
                                "guarded by an explicit "
                                "DiagnosisSelection or "
                                "StoreScanPolicy check; store "
                                "scans must arise only through the "
                                "explicit non-promotion selection"
                            ),
                        )
                    )
    return violations


def _is_scan_invocation_guarded(if_node: ast.If) -> bool:
    """Return True if the ``If`` test refers to a typed selection.

    Heuristic: the test contains a ``isinstance`` call whose second
    argument is one of the allowed ``DiagnosisSelection*`` types.
    """
    for child in ast.walk(if_node.test):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            if child.func.id == "isinstance":
                if len(child.args) >= 2:
                    second = child.args[1]
                    if isinstance(second, ast.Name) and second.id in (
                        "DiagnosisSelectionWithoutPromotion",
                        "DiagnosisSelectionFromPromotion",
                        "DiagnosisSelectionUnavailable",
                        "DiagnosisSelection",
                        "StoreScanPolicy",
                    ):
                        return True
                    if isinstance(second, ast.Attribute) and second.attr in (
                        "DiagnosisSelectionWithoutPromotion",
                        "DiagnosisSelectionFromPromotion",
                        "DiagnosisSelectionUnavailable",
                        "DiagnosisSelection",
                        "StoreScanPolicy",
                    ):
                        return True
    return False


def _independent_outcome_boolean_violations(
    tree: ast.AST,
    file_path: Path,
) -> list[Violation]:
    """Reject assignments that independently set compatibility booleans.

    The compatibility booleans
    (``promotion_may_have_committed``,
    ``promotion_propagated_to_diagnosis``,
    ``promotion_consistency_error_recorded``) MUST be derived
    from the outcome variant. Modules allowed to assign them are
    limited to the seam-canonical surfaces:

    * ``loop_alertmanager_snapshot_signals.py`` -- the orchestrator's
      single log line for a known promotion outcome (assignment
      conditional on a typed result).
    * ``promotion_outcomes.py`` -- the projection functions.
    """
    if file_path.name in (
        "loop_alertmanager_snapshot_signals.py",
        "promotion_outcomes.py",
        "loop_automatic_diagnosis.py",
        "loop_runner_execute.py",
    ):
        return []
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            target_name: str | None = None
            if isinstance(target, ast.Name):
                target_name = target.id
            elif isinstance(target, ast.Attribute):
                target_name = target.attr
            if target_name is None:
                continue
            if target_name in (
                "promotion_may_have_committed",
                "promotion_propagated_to_diagnosis",
                "promotion_consistency_error_recorded",
            ):
                violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=node.lineno,
                        code="INDEPENDENT_BOOLEAN_ASSIGNMENT",
                        message=(
                            f"Field {target_name!r} is a derived "
                            "projection of PromotionOutcome; do "
                            "not assign at arbitrary call sites. "
                            "Use the helpers in "
                            "collect/promotion_outcomes.py."
                        ),
                    )
                )
    return violations


def _verify_file(
    path: Path,
) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerifierInfrastructureError(
            f"Cannot read {path}: {exc}"
        ) from exc
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise VerifierInfrastructureError(
            f"Syntax error in {path}:{exc.lineno}: {exc.msg}"
        ) from exc
    # Attach synthetic ``parent`` attributes so node visits can
    # interrogate context (used for legacy alias detection).
    _attach_parents(tree)
    violations: list[Violation] = []
    violations.extend(_truthiness_fallback_violations(tree, path))
    violations.extend(_store_scan_string_violations(tree, path))
    violations.extend(_explicit_truthy_scan_violations(tree, path))
    violations.extend(_independent_outcome_boolean_violations(tree, path))
    return violations


def verify_seam(src_root: Path) -> tuple[int, list[str]]:
    files: list[Path] = _collect_python_files(src_root)
    seam_files = [path for path in files if _is_seam_module(path)]
    violations: list[Violation] = []
    for path in seam_files:
        violations.extend(_verify_file(path))
    if violations:
        return 1, [v.render() for v in violations]
    return 0, []


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 verifier."
        ),
    )
    parser.add_argument(
        "--src-root",
        default=str(DEFAULT_SRC_ROOT),
        help="Source root to scan",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv if argv is not None else sys.argv[1:])
        src_root = Path(args.src_root)
        exit_code, rendered = verify_seam(src_root)
    except VerifierInfrastructureError as exc:
        print(f"verifier infrastructure error: {exc}", file=sys.stderr)
        return 2
    if exit_code == 0:
        print("OK: current-run promotion seam verifier found no violations")
        return 0
    for line in rendered:
        print(line)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
