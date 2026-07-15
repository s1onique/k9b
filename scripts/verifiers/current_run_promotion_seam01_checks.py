"""Focused AST checks for the current-run promotion SEAM01 verifier."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


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
    """Attach a synthetic ``parent`` attribute to every AST child."""
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)


def _truthiness_fallback_violations(
    tree: ast.AST,
    file_path: Path,
) -> list[Violation]:
    """Reject truthiness-driven store-scan fallbacks at the seam.

    A guarded ``if canonical_ids: <dispatch>`` without an else branch is
    permitted because it can select explicit work without selecting a scan.
    """
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Name)
            and test.id.endswith("_ids")
            and node.orelse
        ):
            else_text = ast.unparse(
                ast.Module(body=list(node.orelse), type_ignores=[]),
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
                            "use a typed DiagnosisSelection variant."
                        ),
                    )
                )
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
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
                                "use a typed DiagnosisSelection variant."
                            ),
                        )
                    )
    return violations


def _is_in_legacy_mode_helper(node: ast.AST) -> bool:
    """Return whether ``node`` is inside a legacy mode projection helper."""
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
    """Reject ``"store_scan"`` strings used outside an explicit policy."""
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
        parent = getattr(node, "parent", None)
        if (
            isinstance(parent, ast.Assign)
            and len(parent.targets) == 1
            and isinstance(parent.targets[0], ast.Name)
            and parent.targets[0].id.startswith("INCIDENT_SELECTION_MODE_")
        ):
            continue
        if _is_in_legacy_mode_helper(node):
            continue
        violations.append(
            Violation(
                file_path=file_path,
                line_number=node.lineno,
                code="RAW_STORE_SCAN_STRING",
                message=(
                    'Raw "store_scan" string is forbidden outside the '
                    "DiagnosisSelection algebra; use "
                    "DiagnosisSelectionWithoutPromotion"
                ),
            )
        )
    return violations


def _explicit_truthy_scan_violations(
    tree: ast.AST,
    file_path: Path,
) -> list[Violation]:
    """Reject scan invocations not guarded by a typed selection check."""
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
            if func_name is None or func_name == "_store_scan_performed":
                continue
            if (
                "store_scan" in func_name
                or func_name.endswith("_scan")
                and "no" not in func_name
            ):
                guarded = _is_scan_invocation_guarded(node)
                if not guarded:
                    violations.append(
                        Violation(
                            file_path=file_path,
                            line_number=child.lineno,
                            code="UNGUARDED_SCAN_INVOCATION",
                            message=(
                                f"Call to {func_name!r} is not guarded by "
                                "an explicit DiagnosisSelection or "
                                "StoreScanPolicy check; store scans must "
                                "arise only through the explicit "
                                "non-promotion selection"
                            ),
                        )
                    )
    return violations


def _is_scan_invocation_guarded(if_node: ast.If) -> bool:
    """Return whether the ``If`` test refers to a typed selection."""
    allowed_types = (
        "DiagnosisSelectionWithoutPromotion",
        "DiagnosisSelectionFromPromotion",
        "DiagnosisSelectionUnavailable",
        "DiagnosisSelection",
        "StoreScanPolicy",
    )
    for child in ast.walk(if_node.test):
        if not (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "isinstance"
            and len(child.args) >= 2
        ):
            continue
        second = child.args[1]
        if isinstance(second, ast.Name) and second.id in allowed_types:
            return True
        if isinstance(second, ast.Attribute) and second.attr in allowed_types:
            return True
    return False


def _independent_outcome_boolean_violations(
    tree: ast.AST,
    file_path: Path,
) -> list[Violation]:
    """Reject assignments that independently set compatibility booleans."""
    canonical_surfaces = (
        "loop_alertmanager_snapshot_signals.py",
        "promotion_outcomes.py",
        "loop_automatic_diagnosis.py",
        "loop_runner_execute.py",
    )
    if file_path.name in canonical_surfaces:
        return []
    violations: list[Violation] = []
    compatibility_fields = (
        "promotion_may_have_committed",
        "promotion_propagated_to_diagnosis",
        "promotion_consistency_error_recorded",
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            target_name: str | None = None
            if isinstance(target, ast.Name):
                target_name = target.id
            elif isinstance(target, ast.Attribute):
                target_name = target.attr
            if target_name not in compatibility_fields:
                continue
            violations.append(
                Violation(
                    file_path=file_path,
                    line_number=node.lineno,
                    code="INDEPENDENT_BOOLEAN_ASSIGNMENT",
                    message=(
                        f"Field {target_name!r} is a derived projection "
                        "of PromotionOutcome; do not assign at arbitrary "
                        "call sites. Use the helpers in "
                        "collect/promotion_outcomes.py."
                    ),
                )
            )
    return violations


def _verify_file(path: Path) -> list[Violation]:
    """Parse one file and run checks in the established contract order."""
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
    _attach_parents(tree)
    violations: list[Violation] = []
    violations.extend(_truthiness_fallback_violations(tree, path))
    violations.extend(_store_scan_string_violations(tree, path))
    violations.extend(_explicit_truthy_scan_violations(tree, path))
    violations.extend(_independent_outcome_boolean_violations(tree, path))
    return violations
