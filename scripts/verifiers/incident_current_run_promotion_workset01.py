#!/usr/bin/env python3
"""Static verifier for ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01.

This verifier proves the post-ACT invariants remain in place by inspecting
the production tree. Every detector (``check_*``) returns a list of human
readable violation strings; an empty list means the invariant holds.

The verifier is exercised both as a script (``python
scripts/verifiers/incident_current_run_promotion_workset01.py``) and via
``importlib.util.spec_from_file_location`` from the self-tests
(``tests/verifiers/test_incident_current_run_promotion_workset01.py``).
Each detector has a paired negative fixture in the self-test that proves
the detector is non-trivial: replacing the production sentinel detected
by the detector with the fixture pattern MUST cause this verifier to emit
at least one violation.

Implementation note. Each detector takes a parsed :class:`ast.Module` and
the file path it came from. Most detectors combine an AST pattern match
(forbid a sentinel) with a textual substring check for the positive
sentinel. The detectors never depend on whitespace, formatting, or code
beyond the sentinels documented above.

Suggested by: ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
SRC_ROOT: Path = REPO_ROOT / "src" / "k8s_diag_agent"

INGESTION_PATH: Final[Path] = (
    SRC_ROOT / "health" / "loop_alertmanager_snapshot_signals.py"
)
SCOPED_PROMOTION_PATH: Final[Path] = (
    SRC_ROOT / "incident_alert_promotion_scoped.py"
)
HANDLER_PATH: Final[Path] = (
    SRC_ROOT / "ui" / "server_incident_internal_handlers.py"
)
BACKEND_ADAPTER_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_promotion_backend.py"
)
SCHEDULER_CLIENT_PATH: Final[Path] = (
    SRC_ROOT / "ui" / "server_incident_internal_fetch.py"
)
CONTRACT_PATH: Final[Path] = (
    SRC_ROOT / "incident_alert_promotion_contract.py"
)
ADAPTER_PATH: Final[Path] = SRC_ROOT / "incident_alert_signal_snapshot_adapter.py"
PROCESSOR_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_evidence_processor.py"
)
BATCH_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_batch.py"
)
BUDGET_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_diagnosis_review_packet_budget.py"
)
COLLECTOR_PATH: Final[Path] = (
    SRC_ROOT
    / "collect"
    / "incident_diagnosis_auto_loop_evidence_collection.py"
)
ELIGIBILITY_PATH: Final[Path] = (
    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_config.py"
)


# ---------------------------------------------------------------------------
# AST / text helpers
# ---------------------------------------------------------------------------


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None


def _function_def(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _class_def(tree: ast.Module, name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _contains_call_to_any(node: ast.AST, name: str) -> bool:
    """Walk any :class:`ast.AST` node looking for a ``Call`` by name.

    Accepts both :class:`ast.Module` and any concrete node
    (:class:`ast.FunctionDef`, :class:`ast.ClassDef`, etc.) so the same
    helper can be used inside ``check_*`` detectors without an extra
    ``_function_def`` round-trip.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name:
            return True
    return False


def _contains_call_to(tree: ast.AST, name: str) -> bool:
    """Backward-compatible wrapper around :func:`_contains_call_to_any`.

    Accepts any :class:`ast.AST` node (module, function, class) so
    detectors can pass a narrower subtree directly without mypy
    flagging a ``FunctionDef`` / ``ClassDef`` argument as incompatible
    with the legacy ``ast.Module`` annotation.
    """
    return _contains_call_to_any(tree, name)


def _contains_text(tree: ast.Module, needle: str) -> bool:
    """Match a substring against string constants AND identifier attributes."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if needle in node.value:
                return True
        if isinstance(node, ast.Attribute) and node.attr == needle:
            return True
    return False


def _function_uses_call(tree: ast.Module, fn_name: str, call_name: str) -> bool:
    fn = _function_def(tree, fn_name)
    if fn is None:
        return False
    return _contains_call_to_any(fn, call_name)


def _function_uses_call_with_kwarg(
    tree: ast.Module, fn_name: str, call_name: str, kwarg_name: str
) -> bool:
    fn = _function_def(tree, fn_name)
    if fn is None:
        return False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id != call_name:
            continue
        if isinstance(func, ast.Attribute) and func.attr != call_name:
            continue
        for kw in node.keywords:
            if kw.arg == kwarg_name:
                return True
    return False


def _function_uses_kwarg(
    tree: ast.Module, fn_name: str, kwarg_name: str
) -> bool:
    fn = _function_def(tree, fn_name)
    if fn is None:
        return False
    for arg in fn.args.args:
        if arg.arg == kwarg_name:
            return True
    for arg in getattr(fn.args, "kwonlyargs", []):
        if arg.arg == kwarg_name:
            return True
    return False


# ---------------------------------------------------------------------------
# Ingestion detectors
# ---------------------------------------------------------------------------


def check_ingestion_uses_scoped_promotion(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    violations: list[str] = []
    if _contains_call_to(tree, "promote_alert_signals_for_accumulator"):
        violations.append(
            "ingestion uses promote_alert_signals_for_accumulator; "
            "must call promote_alert_signals_scoped_for_accumulator"
        )
    if not _contains_call_to(tree, "promote_alert_signals_scoped_for_accumulator"):
        violations.append(
            "ingestion does not call promote_alert_signals_scoped_for_accumulator"
        )
    return violations


def check_ingestion_forbids_global_scan_fallback(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if _contains_call_to(tree, "scan_alert_signals_as_candidates"):
        return [
            "ingestion calls scan_alert_signals_as_candidates "
            "(global scan fallback)"
        ]
    return []


def check_ingestion_logs_explicit_current_run_scope(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _contains_text(tree, "explicit_current_run_signal_ids"):
        return [
            "ingestion does not log promotion_scope="
            "explicit_current_run_signal_ids"
        ]
    return []


def check_ingestion_uses_artifact_identity(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "str":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Attribute) and arg.attr == "signal_id":
                violations.append(
                    "ingestion uses str(<...>.signal_id); "
                    "must use persisted.artifact_identity"
                )
    if not _contains_text(tree, "artifact_identity"):
        violations.append(
            "ingestion does not reference persisted.artifact_identity"
        )
    return violations


def check_ingestion_stable_deduplicates_artifact_workset(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "dict"
            and func.attr == "fromkeys"
        ):
            return []
        if isinstance(func, ast.Name) and func.id == "list":
            inner = node.args[0] if node.args else None
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and isinstance(inner.func.value, ast.Name)
                and inner.func.value.id == "dict"
                and inner.func.attr == "fromkeys"
            ):
                return []
    return ["ingestion does not stable-deduplicate via dict.fromkeys(...)"]


# ---------------------------------------------------------------------------
# Scoped promotion detectors
# ---------------------------------------------------------------------------


def check_scoped_promotion_handles_empty_scope(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "empty"
            and isinstance(func.value, ast.Name)
            and func.value.id == "IncidentPromotionResult"
        ):
            return []
    return [
        "scoped promotion does not short-circuit on empty "
        "request.signal_ids"
    ]


def check_scoped_promotion_owns_actionable_projection(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    fn = _function_def(tree, "promote_scoped_alert_signals")
    if fn is None:
        return ["scoped promotion: promote_scoped_alert_signals missing"]
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "IncidentPromotionResult":
            return []
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "IncidentPromotionResult"
            and func.attr in ("empty", "from_wire_dict")
        ):
            return []
    return [
        "scoped promotion does not construct "
        "IncidentPromotionResult (no actionable projection)"
    ]


# ---------------------------------------------------------------------------
# Handler / backend client / backend adapter detectors
# ---------------------------------------------------------------------------


def check_handler_rejects_missing_scope(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "from_dict"
            and isinstance(func.value, ast.Name)
            and func.value.id == "PromoteAlertSignalsRequest"
        ):
            violations.append(
                "handler uses PromoteAlertSignalsRequest.from_dict; "
                "must call parse_promote_alert_signals_request"
            )
    if not _contains_call_to(tree, "parse_promote_alert_signals_request"):
        violations.append(
            "handler does not call parse_promote_alert_signals_request"
        )
    return violations


def check_handler_uses_scoped_promotion_call(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _contains_call_to(tree, "promote_scoped_alert_signals"):
        return ["handler does not call promote_scoped_alert_signals"]
    return []


def check_backend_client_exposes_scoped_call(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    cls = _class_def(tree, "SchedulerClient")
    if cls is None:
        return ["backend client: SchedulerClient missing"]
    for node in cls.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            in (
                "promote_alert_signals_scoped",
                "promote_alert_signals_scoped_for_accumulator",
            )
        ):
            return []
    return ["SchedulerClient missing promote_alert_signals_scoped method"]


def check_backend_adapter_parses_camel_case_wire(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if _function_def(tree, "_response_to_promotion_result") is not None:
        for call_name in ("from_wire_dict", "IncidentPromotionResult"):
            if _contains_call_to(tree, call_name):
                return []
    for needle in ("scannedSignalIds", "openedIncidentIds"):
        if _contains_text(tree, needle):
            return []
    return [
        "backend adapter does not parse camelCase wire field "
        "'scannedSignalIds'"
    ]


# ---------------------------------------------------------------------------
# Contract / adapter detectors
# ---------------------------------------------------------------------------


def check_contract_exposes_wire_parser(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    cls = _class_def(tree, "IncidentPromotionResult")
    if cls is None:
        return ["contract: IncidentPromotionResult missing"]
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "from_wire_dict"
        for node in cls.body
    ):
        return ["IncidentPromotionResult missing from_wire_dict"]
    if not _contains_text(tree, "scannedSignalIds"):
        return [
            "IncidentPromotionResult does not surface scannedSignalIds "
            "on the wire"
        ]
    return []


def check_persist_alert_signals_returns_artifact_identity(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _contains_call_to(tree, "PersistedAlertSignal"):
        return [
            "persist_alert_signals does not construct PersistedAlertSignal"
        ]
    return []


# ---------------------------------------------------------------------------
# Processor / batch detectors
# ---------------------------------------------------------------------------


def check_processor_records_successful_writes_only(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    fn = _function_def(tree, "_process_incident")
    if fn is None:
        return ["processor: _process_incident missing"]
    violations: list[str] = []
    for outer in ast.walk(fn):
        if isinstance(outer, ast.Try):
            for handler_node in outer.finalbody:
                for descendant in ast.walk(handler_node):
                    if (
                        isinstance(descendant, ast.Call)
                        and isinstance(descendant.func, ast.Attribute)
                        and descendant.func.attr == "record_successful_write"
                    ):
                        violations.append(
                            "processor records budget inside a finally "
                            "block (consumes even on failed write)"
                        )
    if not _contains_call_to(fn, "record_successful_write"):
        violations.append(
            "processor never calls record_successful_write on a "
            "successful packet write"
        )
    return violations


def check_processor_checks_budget_before_packet_write(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _function_uses_call(
        tree, "_process_incident", "can_attempt"
    ):
        return [
            "processor never calls budget.can_attempt() before "
            "write_diagnosis_review_packet"
        ]
    return []


def check_processor_uses_budget_for_eligibility(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _function_uses_call_with_kwarg(
        tree,
        "_process_incident",
        "evaluate_incident_eligibility",
        "review_packet_budget",
    ):
        return [
            "processor does not forward review_packet_budget to "
            "evaluate_incident_eligibility"
        ]
    return []


def check_batch_forwards_budget_to_processor(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    if not _function_uses_call_with_kwarg(
        tree,
        "process_incident_batch",
        "_process_incident",
        "review_packet_budget",
    ):
        return [
            "process_incident_batch does not forward "
            "review_packet_budget to _process_incident"
        ]
    return []


# ---------------------------------------------------------------------------
# Budget / collector / eligibility detectors
# ---------------------------------------------------------------------------


def check_budget_keyed_by_collector_run_identity(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    cls = _class_def(tree, "ReviewPacketCreationBudget")
    if cls is None:
        return ["budget: ReviewPacketCreationBudget missing"]
    for node in cls.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "__init__"
            and any(
                arg.arg == "collector_run_id" for arg in node.args.args
            )
        ):
            return []
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "collector_run_id"
        ):
            return []
    return [
        "ReviewPacketCreationBudget is not keyed by collector_run_id"
    ]


def check_budget_reconstruction_filters_by_exact_collector_id(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    violations: list[str] = []
    if _contains_text(tree, "review_packet_artifacts"):
        violations.append(
            "budget reconstruction uses forbidden source label "
            "'review_packet_artifacts'"
        )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "startswith":
            continue
        if not node.args or not isinstance(node.args[0], ast.Attribute):
            continue
        if node.args[0].attr in ("run_id", "collector_run_id"):
            violations.append(
                "budget reconstruction uses filename-prefix matching "
                f"({node.args[0].attr}.startswith(...))"
            )
    return violations


def check_collector_instantiates_review_packet_budget(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    fn = _function_def(
        tree, "run_automatic_diagnosis_loop_evidence_collection"
    )
    if fn is None:
        return ["collector: entry function missing"]
    if not _contains_call_to(fn, "ReviewPacketCreationBudget"):
        return [
            "collector does not instantiate ReviewPacketCreationBudget"
        ]
    return []


def check_eligibility_bypasses_historical_count_when_budget_present(
    tree: ast.Module, path: Path
) -> list[str]:
    del path
    fn = _function_def(tree, "evaluate_incident_eligibility")
    if fn is None:
        return ["eligibility: evaluate_incident_eligibility missing"]
    if not _function_uses_kwarg(
        tree, "evaluate_incident_eligibility", "review_packet_budget"
    ):
        return [
            "evaluate_incident_eligibility does not accept "
            "review_packet_budget"
        ]
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in (
            "rglob",
            "glob",
            "listdir",
            "scandir",
        ):
            return [
                "evaluate_incident_eligibility consults the "
                "filesystem directly even when "
                "review_packet_budget is supplied"
            ]
        if isinstance(func, ast.Name) and func.id in (
            "_count_files",
            "count_files",
            "_count_artifacts",
            "count_artifacts",
        ):
            return [
                "evaluate_incident_eligibility consults the "
                "filesystem directly even when "
                "review_packet_budget is supplied"
            ]
    return []


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _check(
    tree: ast.Module | None, path: Path, check: object, label: str
) -> list[str]:
    if tree is None:
        return [f"{label}: cannot parse {path}"]
    return [
        f"{label}: {v}" for v in check(tree, path)  # type: ignore[operator]
    ]


def run_static_checks() -> list[str]:
    """Run every detector against the production tree."""
    files: list[tuple[str, Path, object]] = [
        ("ingestion", INGESTION_PATH, check_ingestion_uses_scoped_promotion),
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_forbids_global_scan_fallback,
        ),
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_logs_explicit_current_run_scope,
        ),
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_uses_artifact_identity,
        ),
        (
            "ingestion",
            INGESTION_PATH,
            check_ingestion_stable_deduplicates_artifact_workset,
        ),
        (
            "scoped_promotion",
            SCOPED_PROMOTION_PATH,
            check_scoped_promotion_handles_empty_scope,
        ),
        (
            "scoped_promotion",
            SCOPED_PROMOTION_PATH,
            check_scoped_promotion_owns_actionable_projection,
        ),
        (
            "handler",
            HANDLER_PATH,
            check_handler_rejects_missing_scope,
        ),
        (
            "handler",
            HANDLER_PATH,
            check_handler_uses_scoped_promotion_call,
        ),
        (
            "backend_client",
            SCHEDULER_CLIENT_PATH,
            check_backend_client_exposes_scoped_call,
        ),
        (
            "backend_adapter",
            BACKEND_ADAPTER_PATH,
            check_backend_adapter_parses_camel_case_wire,
        ),
        ("contract", CONTRACT_PATH, check_contract_exposes_wire_parser),
        (
            "adapter",
            ADAPTER_PATH,
            check_persist_alert_signals_returns_artifact_identity,
        ),
        (
            "processor",
            PROCESSOR_PATH,
            check_processor_records_successful_writes_only,
        ),
        (
            "processor",
            PROCESSOR_PATH,
            check_processor_checks_budget_before_packet_write,
        ),
        (
            "processor",
            PROCESSOR_PATH,
            check_processor_uses_budget_for_eligibility,
        ),
        ("batch", BATCH_PATH, check_batch_forwards_budget_to_processor),
        ("budget", BUDGET_PATH, check_budget_keyed_by_collector_run_identity),
        (
            "budget",
            BUDGET_PATH,
            check_budget_reconstruction_filters_by_exact_collector_id,
        ),
        (
            "collector",
            COLLECTOR_PATH,
            check_collector_instantiates_review_packet_budget,
        ),
        (
            "eligibility",
            ELIGIBILITY_PATH,
            check_eligibility_bypasses_historical_count_when_budget_present,
        ),
    ]
    violations: list[str] = []
    for label, path, check in files:
        tree = _parse(path)
        violations.extend(_check(tree, path, check, label))
    return violations


def main(argv: list[str]) -> int:
    del argv  # CLI flags intentionally unused
    violations = run_static_checks()
    if violations:
        for violation in violations:
            print(violation)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
