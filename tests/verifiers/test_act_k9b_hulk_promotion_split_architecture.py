"""Bounded architecture guards for the hard-file promotion split."""
from __future__ import annotations

from pathlib import Path

from promotion_hulk_ast_support import find_functions, parse_source, physical_lines

ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_handlers.py"
PROMOTION = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_promotion_handlers.py"
CANDIDATES = ROOT / "src/k8s_diag_agent/ui/server_incident_internal_promotion_candidates.py"


def test_internal_handler_is_compatibility_facade_only() -> None:
    assert physical_lines(FACADE) < 150
    tree = parse_source(FACADE)
    assert not find_functions(tree, "handle_promote_alert_signals")
    assert not find_functions(tree, "handle_promote_candidates")


def test_promotion_handlers_have_one_implementation_owner() -> None:
    assert len(find_functions(parse_source(PROMOTION), "handle_promote_alert_signals")) == 1
    assert len(find_functions(parse_source(CANDIDATES), "handle_promote_candidates")) == 1
    assert not find_functions(parse_source(FACADE), "handle_promote_alert_signals")
    assert not find_functions(parse_source(FACADE), "handle_promote_candidates")


def test_replacement_modules_stay_below_hard_limit() -> None:
    assert physical_lines(FACADE) < 500
    assert physical_lines(PROMOTION) < 500
    assert physical_lines(CANDIDATES) < 500
    assert physical_lines(ROOT / "tests/verifiers/promotion_hulk_ast_support.py") < 300


def test_support_module_contains_no_test_definitions() -> None:
    tree = parse_source(ROOT / "tests/verifiers/promotion_hulk_ast_support.py")
    assert not [name for name in find_functions(tree, "test_*")]
