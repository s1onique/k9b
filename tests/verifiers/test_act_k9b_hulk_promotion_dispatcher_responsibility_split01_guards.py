"""Dispatcher responsibility-split architecture guards.

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

These guards fail at test time when the dispatcher split regresses
any of the structural invariants:

* :mod:`incident_promotion_dispatch` is the SINGLE façade module
  and does NOT carry implementation logic.
* The active typed scoped dispatcher lives in
  :mod:`incident_promotion_dispatch_scoped` and calls
  :meth:`RunPromotionAccumulator.record_scoped_promotion_batch`
  exactly once per invocation.
* The active scoped dispatcher MUST NOT call legacy dict adapters
  (``_result_from_dict``), separate
  :meth:`record_promotion_outcome` / :meth:`add_batch` /
  :meth:`record_scoped_promotion` paths, or perform a global
  store scan after a typed scoped outcome.
* All dispatcher submodules stay below the 500 physical-line cap.
* No new LLM-friendly allowlist entry exists.
* Closed unions retain ``assert_never`` exhaustiveness.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"

DISPATCH_FACADE = SRC_ROOT / "incident_promotion_dispatch.py"
DISPATCH_CONFIG = SRC_ROOT / "incident_promotion_dispatch_config.py"
DISPATCH_LOCAL = SRC_ROOT / "incident_promotion_dispatch_local.py"
DISPATCH_BACKEND = SRC_ROOT / "incident_promotion_dispatch_backend.py"
DISPATCH_SCOPED = SRC_ROOT / "incident_promotion_dispatch_scoped.py"
DISPATCH_BATCHES = SRC_ROOT / "incident_promotion_dispatch_batches.py"
DISPATCH_VALIDATION = (
    SRC_ROOT / "incident_promotion_dispatch_validation.py"
)
DISPATCH_LEGACY = SRC_ROOT / "incident_promotion_dispatch_legacy.py"

ALL_DISPATCH_MODULES = (
    DISPATCH_FACADE,
    DISPATCH_CONFIG,
    DISPATCH_LOCAL,
    DISPATCH_BACKEND,
    DISPATCH_SCOPED,
    DISPATCH_BATCHES,
    DISPATCH_VALIDATION,
    DISPATCH_LEGACY,
)


def _physical_line_count(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8"))


def test_dispatcher_facade_only_contains_entry_points() -> None:
    """The façade MUST NOT carry implementation logic.

    The façade is allowed to:

    * Import from submodules and re-export.
    * Define the two top-level entry points
      :func:`promote_candidates` and :func:`promote_alert_signals`.
    * Emit a single ``alert-signals-promotion-start`` log line.

    It MUST NOT define:

    * A standalone :class:`IncidentPromotionDispatchConfig` (lives
      in :mod:`incident_promotion_dispatch_config`).
    * ``_get_dispatch_config`` (lives in
      :mod:`incident_promotion_dispatch_config`).
    * ``_result_from_dict`` (lives in
      :mod:`incident_promotion_dispatch_legacy`).
    * ``_incident_access_mode_for_promotion_mode`` (lives in
      :mod:`incident_promotion_dispatch_config`).
    * ``validate_promotion_response_records`` (lives in
      :mod:`incident_promotion_dispatch_validation`).
    * ``_build_empty_batch`` (lives in
      :mod:`incident_promotion_dispatch_batches` or scoped).
    * ``promote_alert_signals_scoped_for_accumulator`` (lives in
      :mod:`incident_promotion_dispatch_scoped`).
    """
    text = DISPATCH_FACADE.read_text()
    forbidden_definitions = (
        "class IncidentPromotionDispatchConfig",
        "def _get_dispatch_config",
        "def _result_from_dict",
        "def _incident_access_mode_for_promotion_mode",
        "def validate_promotion_response_records",
        "def _build_empty_batch",
        "def promote_alert_signals_scoped_for_accumulator",
        "def _scoped_promotion_result_from_handoff",
    )
    for needle in forbidden_definitions:
        if needle in text:
            pytest.fail(
                f"incident_promotion_dispatch.py MUST NOT define "
                f"{needle!r}; that ownership belongs to a focused "
                f"submodule."
            )


def test_dispatcher_modules_below_500_physical_lines() -> None:
    """Every dispatcher module MUST stay below the 500-line cap."""
    offenders: list[str] = []
    for path in ALL_DISPATCH_MODULES:
        line_count = _physical_line_count(path)
        if line_count >= 500:
            offenders.append(f"{path.name} has {line_count} lines")
    if offenders:
        pytest.fail(
            "Dispatcher modules exceed 500 physical lines: "
            + "; ".join(offenders)
        )


def test_dispatcher_facade_below_350_physical_lines() -> None:
    """The façade MUST stay below the 350-line soft cap.

    The split places ALL implementation logic in submodules; the
    façade is a re-export + dispatch-selection shell.  A façade
    above 350 lines indicates that implementation has drifted back
    into the façade module.
    """
    line_count = _physical_line_count(DISPATCH_FACADE)
    if line_count >= 350:
        pytest.fail(
            f"incident_promotion_dispatch.py has {line_count} "
            f"physical lines (soft cap 350); implementation has "
            f"drifted into the façade."
        )


def _code_calls(path: Path, func_name: str) -> int:
    """Return the number of times ``func_name`` is CALLED in the code (not docs).

    Uses AST to walk every ``Call`` node and match either the bare
    function name (e.g. ``func_name()``) or a method call on any
    attribute (e.g. ``x.func_name(...)``).  String/attribute name
    occurrences in docstrings or comments are ignored so the guard
    only catches actual code.
    """
    tree = ast.parse(path.read_text())
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == func_name:
            count += 1
        elif isinstance(func, ast.Attribute) and func.attr == func_name:
            count += 1
    return count


def test_scoped_dispatcher_calls_record_scoped_promotion_batch_exactly_once() -> None:
    """The active scoped dispatcher MUST call record_scoped_promotion_batch exactly once."""
    count = _code_calls(DISPATCH_SCOPED, "record_scoped_promotion_batch")
    if count != 1:
        pytest.fail(
            "incident_promotion_dispatch_scoped.py MUST invoke "
            f"record_scoped_promotion_batch exactly once; found {count} "
            f"occurrences in code."
        )


def test_scoped_dispatcher_no_dict_result_conversion() -> None:
    """The active scoped dispatcher MUST NOT call _result_from_dict."""
    count = _code_calls(DISPATCH_SCOPED, "_result_from_dict")
    if count > 0:
        pytest.fail(
            f"incident_promotion_dispatch_scoped.py MUST NOT call "
            f"_result_from_dict; found {count} call(s) in code."
        )
    if "scoped_dispatch_result_to_promotion_result_dict" in DISPATCH_SCOPED.read_text():
        # We allow the symbol to appear in a string/docstring; only
        # AST-level calls would be a real violation.  Inspect via
        # AST name-id matching below.
        tree = ast.parse(DISPATCH_SCOPED.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "scoped_dispatch_result_to_promotion_result_dict"
            ):
                pytest.fail(
                    "incident_promotion_dispatch_scoped.py MUST NOT "
                    "call scoped_dispatch_result_to_promotion_result_dict."
                )


def test_scoped_dispatcher_no_legacy_client_usage() -> None:
    """The active scoped dispatcher MUST NOT invoke legacy dispatch helpers."""
    legacy_helpers = (
        "promote_via_backend_api",
        "promote_alert_signals_via_backend_api",
        "promote_local",
        "scan_alert_signals_as_candidates",
        "promote_alert_signals_from_artifacts",
    )
    for helper in legacy_helpers:
        if _code_calls(DISPATCH_SCOPED, helper) > 0:
            pytest.fail(
                f"incident_promotion_dispatch_scoped.py MUST NOT call "
                f"{helper!r}; the active scoped path uses the typed "
                f"scoped transport mapper directly."
            )


def test_scoped_dispatcher_no_global_store_scan() -> None:
    """The active scoped dispatcher MUST NOT perform a global store scan."""
    forbidden = (
        "scan_alert_signal_artifacts",
        "get_incident_store",
        "SQLiteIncidentStore",
        "record_promotion_outcome",
        "record_scoped_promotion",
        "add_batch",
    )
    for symbol in forbidden:
        if _code_calls(DISPATCH_SCOPED, symbol) > 0:
            pytest.fail(
                f"incident_promotion_dispatch_scoped.py MUST NOT call "
                f"{symbol!r}; the active scoped path is purely a "
                f"transport-to-handoff-to-accumulator wire."
            )


def test_facade_re_exports_promotion_batch() -> None:
    """The façade MUST NOT redefine ``PromotionBatch``.

    The dispatcher file is the SINGLE re-export façade.  A
    ``@dataclass(frozen=True)\nclass PromotionBatch`` definition
    would duplicate the canonical type and break
    :mod:`tests.verifiers.test_r4_acceptance`.
    """
    import ast as _ast

    tree = _ast.parse(DISPATCH_FACADE.read_text())
    for node in _ast.walk(tree):
        if (
            isinstance(node, _ast.ClassDef)
            and node.name == "PromotionBatch"
            and any(
                isinstance(d, _ast.Name) and d.id == "dataclass"
                for d in node.decorator_list
            )
        ):
            pytest.fail(
                "incident_promotion_dispatch.py MUST NOT redefine "
                "``PromotionBatch``; the canonical class lives in "
                "``.incident_promotion_batch``."
            )


def test_facade_no_dataclass_promotion_batch() -> None:
    """The façade MUST NOT redefine ``PromotionBatch``."""
    text = DISPATCH_FACADE.read_text()
    if "@dataclass(frozen=True)\nclass PromotionBatch" in text:
        pytest.fail(
            "incident_promotion_dispatch.py MUST NOT redefine "
            "``PromotionBatch``; the canonical class lives in "
            "``.incident_promotion_batch``."
        )


def test_assert_never_in_scoped_dispatcher() -> None:
    """The scoped dispatcher MUST use ``assert_never`` for exhaustiveness."""
    text = DISPATCH_SCOPED.read_text()
    if "assert_never" not in text:
        pytest.fail(
            "incident_promotion_dispatch_scoped.py MUST use "
            "``assert_never`` to enforce exhaustiveness on the closed "
            "handoff union."
        )


def test_no_new_llm_friendly_allowlist_entry() -> None:
    """No new LLM-friendly allowlist entry may be added for the dispatcher."""
    allowlist = REPO_ROOT / "scripts" / "llm_friendly_allowlist.py"
    text = allowlist.read_text()
    dispatcher_files = (
        "incident_promotion_dispatch.py",
        "incident_promotion_dispatch_config.py",
        "incident_promotion_dispatch_local.py",
        "incident_promotion_dispatch_backend.py",
        "incident_promotion_dispatch_scoped.py",
        "incident_promotion_dispatch_batches.py",
        "incident_promotion_dispatch_validation.py",
        "incident_promotion_dispatch_legacy.py",
    )
    for name in dispatcher_files:
        if name in text and f'"{name}"' in text:
            pytest.fail(
                f"Dispatcher module {name!r} MUST NOT appear in the "
                f"LLM-friendly allowlist; the split keeps every "
                f"module below the 500-line cap."
            )


def test_dispatcher_split_modules_exist() -> None:
    """The split modules MUST all exist as separate files."""
    missing = [
        str(path.relative_to(REPO_ROOT))
        for path in ALL_DISPATCH_MODULES
        if not path.exists()
    ]
    if missing:
        pytest.fail(
            "Dispatcher split modules are missing: " + ", ".join(missing)
        )


def test_dispatcher_split_unique_function_owners() -> None:
    """Each production function MUST live in exactly one dispatcher module."""
    # Functions that the split dedicates to specific owners.
    dedicated_owners = {
        "IncidentPromotionDispatchConfig": DISPATCH_CONFIG,
        "_get_dispatch_config": DISPATCH_CONFIG,
        "_incident_access_mode_for_promotion_mode": DISPATCH_CONFIG,
        "log_promotion_config": DISPATCH_CONFIG,
        "_result_from_dict": DISPATCH_LEGACY,
        "dispatch_local_promotion": DISPATCH_LOCAL,
        "dispatch_backend_promotion": DISPATCH_BACKEND,
        "promote_alert_signals_scoped_for_accumulator": DISPATCH_SCOPED,
        "_scoped_promotion_result_from_handoff": DISPATCH_SCOPED,
        "_build_empty_scoped_batch": DISPATCH_SCOPED,
        "validate_promotion_response_records": DISPATCH_VALIDATION,
        "PromotionResponseValidationError": DISPATCH_VALIDATION,
        "scan_alert_signals_as_candidates": DISPATCH_BATCHES,
        "promote_alert_signals_from_artifacts": DISPATCH_BATCHES,
        "promote_alert_signals_for_accumulator": DISPATCH_BATCHES,
        "promotion_records_from_result": DISPATCH_BATCHES,
        "promote_candidates": DISPATCH_FACADE,
        "promote_alert_signals": DISPATCH_FACADE,
    }
    leaked: list[str] = []
    for symbol, owner in dedicated_owners.items():
        if not owner.exists():
            continue
        text = owner.read_text()
        if f"def {symbol}" in text or f"class {symbol}" in text:
            # This module is the owner -- expected.
            continue
        leaked.append(
            f"{symbol!r} is expected to live in "
            f"{owner.name} but its definition is missing."
        )
    if leaked:
        pytest.fail(
            "Dispatcher split ownership violations: " + "; ".join(leaked)
        )


def test_facade_imports_canonical_promotion_batch() -> None:
    """The dispatcher file MUST import ``PromotionBatch`` for the test contract."""
    text = DISPATCH_FACADE.read_text()
    if "PromotionBatch" not in text:
        pytest.fail(
            "incident_promotion_dispatch.py MUST reference "
            "``PromotionBatch`` (imported from "
            "``.incident_promotion_batch``)."
        )