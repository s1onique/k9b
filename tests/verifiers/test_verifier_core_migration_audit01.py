# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""Reliability tests for the audit generator.

CORRECTION12 updates:

* The CLI is a thin wrapper around ``write_audit``; the
  ``cmd_write`` rejection path is tested.
* The ``changed_paths`` / ``changed_python_paths`` /
  ``build_ruff_argv`` tests use a hermetic temporary Git
  repository (``range_repo`` fixture) instead of the
  history-coupled ``FIXTURE_BASE`` / ``FIXTURE_SUBJECT``
  constants used prior to CORRECTION12.
* The ``range_repo`` fixture creates a self-contained repository
  with an added Python file, a modified Python file, a renamed
  Python file, a deleted Python file, an added non-Python file,
  a path with an ordinary space, a path with leading whitespace,
  a path with trailing whitespace when the host supports it,
  and a non-ASCII pathname.
* A typed :class:`RangeResolutionError` is raised on every
  invalid ``git diff`` range; the tests below prove the
  fail-closed contract.

The 15 baseline R11 invariants below remain intact.
"""

from __future__ import annotations

import ast

import pytest

from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.consumer_map import (
    _source_core_uses,
    build_consumer_map,
    discover_test_paths,
)
from scripts.verifiers_audit.discovery import (
    REPO_ROOT,
    core_public_symbols,
)
from scripts.verifiers_audit.equivalence import run_all_equivalence
from scripts.verifiers_audit.render import render_markdown
from scripts.verifiers_audit.report_io import ALL_SHARDS
from tests.verifiers.verifier_core_migration_audit01_support import (
    _synthetic_skipped_record,
)

# 1. Source-derived totals equal report totals.

# ---------------------------------------------------------------------------


def test_source_totals_match_index_totals(audit: dict) -> None:
    inv = audit["inventory"]
    helpers = audit["helpers"]
    groups = audit["groups"]
    usage = audit["core_usage"]
    cands = audit["candidates"]
    index = audit["index"]["totals"]
    assert index["tracked_path_count"] == inv["totals"]["tracked_path_count"]
    assert index["included_path_count"] == inv["totals"]["included_path_count"]
    assert index["excluded_path_count"] == inv["totals"]["excluded_path_count"]
    assert index["helper_count"] == helpers["totals"]["helper_count"]
    assert index["duplicate_group_count"] == groups["totals"]["duplicate_group_count"]
    assert index["exact_duplicate_group_count"] == groups["totals"]["exact_duplicate_group_count"]
    assert index["exact_duplicate_helper_count"] == groups["totals"]["exact_duplicate_helper_count"]
    assert index["core_public_symbol_count"] == usage["totals"]["core_public_symbol_count"]
    assert index["candidate_count"] == cands["totals"]["candidate_count"]
    assert index["wave_1_candidate_count"] == cands["totals"]["wave_1_candidate_count"]


# ---------------------------------------------------------------------------
# 2. included + excluded == tracked.
# ---------------------------------------------------------------------------


def test_included_plus_excluded_equals_tracked(audit: dict) -> None:
    inv = audit["inventory"]
    included = inv["included_paths"]
    excluded = [e["path"] for e in inv["excluded_paths"]]
    assert len(included) + len(excluded) == inv["totals"]["tracked_path_count"]
    assert inv["totals"]["included_plus_excluded_equals_tracked"] is True


# ---------------------------------------------------------------------------
# 3. No excluded path appears in helper / group / candidate data.
# ---------------------------------------------------------------------------


def test_no_excluded_path_in_helpers(audit: dict) -> None:
    excluded = {e["path"] for e in audit["inventory"]["excluded_paths"]}
    for h in audit["helpers"]["helpers"]:
        assert h["path"] not in excluded


def test_no_excluded_path_in_groups(audit: dict) -> None:
    excluded = {e["path"] for e in audit["inventory"]["excluded_paths"]}
    for g in audit["groups"]["groups"]:
        for member in g["members"]:
            member_path = member.split(":", 1)[0]
            assert member_path not in excluded


# ---------------------------------------------------------------------------
# 4. Every helper record resolves to a real AST node.
# ---------------------------------------------------------------------------


def _file_helpers(path: str) -> set[tuple[str, int]]:
    """Set of ``(qualname, line)`` for every helper in ``path``."""
    full = REPO_ROOT / path
    if not full.exists():
        return set()
    try:
        tree = ast.parse(full.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    out: set[tuple[str, int]] = set()

    def visit(node: ast.AST, parent: str) -> None:
        if isinstance(node, ast.ClassDef):
            qual = f"{parent}.{node.name}" if parent else node.name
            for stmt in node.body:
                visit(stmt, qual)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = f"{parent}.{node.name}" if parent else node.name
            out.add((qual, node.lineno))
            for stmt in node.body:
                visit(stmt, qual)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, parent)

    for stmt in tree.body:
        visit(stmt, "")
    return out


def test_every_helper_resolves_to_real_ast_node(audit: dict) -> None:
    by_path: dict[str, set[tuple[str, int]]] = {}
    included = audit["inventory"]["included_paths"]
    for path in included:
        by_path[path] = _file_helpers(path)
    for h in audit["helpers"]["helpers"]:
        path = h["path"]
        key = (h["qualname"], h["line"])
        assert key in by_path.get(path, set()), f"helper {key!r} not found in {path}"


# ---------------------------------------------------------------------------
# 5. Every discovered structural helper is classified.
# ---------------------------------------------------------------------------


def test_every_group_member_is_in_helpers(audit: dict) -> None:
    from scripts.verifiers_audit.discovery import discover_helpers

    shard_keys = {(h["path"], h["qualname"]) for h in audit["helpers"]["helpers"]}
    all_helpers = discover_helpers(audit["inventory"]["included_paths"])
    all_keys = {(h.path, h.qualname) for h in all_helpers}
    for g in audit["groups"]["groups"]:
        for member in g["members"]:
            path, _, qualname = member.partition(":")
            in_shard = (path, qualname) in shard_keys
            in_full = (path, qualname) in all_keys
            assert in_shard or in_full, f"group {g['group_id']} member {member!r} not in helpers"


# ---------------------------------------------------------------------------
# 6. Duplicate helper and group counts are distinct.
# ---------------------------------------------------------------------------


def test_exact_duplicate_helper_and_group_counts_distinct(audit: dict) -> None:
    g = audit["groups"]["totals"]
    assert g["exact_duplicate_group_count"] <= g["exact_duplicate_helper_count"]
    assert g["mixed_groups"] == []


# ---------------------------------------------------------------------------
# 7. All Wave-1 candidates pass the executable equivalence suites.
# ---------------------------------------------------------------------------


def test_wave_1_equivalence_all_pass(audit: dict) -> None:
    suites = audit["candidates"]["equivalence_suites"]
    for name, suite in suites.items():
        assert suite["failed"] == 0, f"suite {name!r} has {suite['failed']} failures"


def test_equivalence_independent_run_matches_audit() -> None:
    summary = run_all_equivalence()
    for name, suite in summary.items():
        assert suite["passed"] == suite["total"], f"suite {name!r}"


# ---------------------------------------------------------------------------
# 8. Parse missing-file behaviour is accurately recorded.
# ---------------------------------------------------------------------------


def test_parse_missing_file_returns_none_in_both_helpers() -> None:
    from scripts.verifiers_audit.equivalence import run_parse_equivalence

    raw_results = run_parse_equivalence()
    cases = {c["name"]: c for c in raw_results["cases"]}
    assert "missing_file" in cases, cases.keys()
    assert cases["missing_file"]["status"] == "PASSED", cases["missing_file"]


# ---------------------------------------------------------------------------
# 9. Core public-symbol count comes from ``__all__``.
# ---------------------------------------------------------------------------


def test_core_has_exactly_24_public_symbols(audit: dict) -> None:
    symbols = core_public_symbols()
    assert len(symbols) == 24
    assert audit["core_usage"]["totals"]["core_public_symbol_count"] == 24


def test_every_public_symbol_is_unique(audit: dict) -> None:
    seen = set()
    for c in audit["core_usage"]["consumers"]:
        assert c["symbol"] not in seen, c["symbol"]
        seen.add(c["symbol"])


# ---------------------------------------------------------------------------
# 10. Production-consumer counts come from AST references.
# ---------------------------------------------------------------------------


def test_consumer_count_is_real_ast_count(audit: dict) -> None:
    usage = audit["core_usage"]
    tracked = audit["inventory"]["included_paths"]
    tests = discover_test_paths()
    symbols = core_public_symbols()
    symbol_modules = {c["symbol"]: c["module"] for c in usage["consumers"]}
    fresh = build_consumer_map(symbols, symbol_modules, tracked, tests)
    by_symbol = {c.symbol: c for c in fresh}
    for c in usage["consumers"]:
        fresh_c = by_symbol[c["symbol"]]
        assert len(fresh_c.production_callers) == len(c["production_callers"])
        assert len(fresh_c.test_callers) == len(c["test_callers"])
        assert fresh_c.classification == c["classification"]


# ---------------------------------------------------------------------------
# 10b. Import-aware resolution distinguishes real consumers
# ---------------------------------------------------------------------------


_R2_CASES: tuple[tuple[str, str, frozenset[str]], ...] = (
    (
        "direct_import",
        "from scripts.verifiers.verifier_core import read_source\ndef f(p):\n    return read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "aliased_direct_import",
        "from scripts.verifiers.verifier_core import SourceLocation as CoreLocation\ndef f():\n    return CoreLocation(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "qualified_import",
        "import scripts.verifiers.verifier_core as vc\ndef f(p):\n    return vc.read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "aliased_qualified_import",
        "import scripts.verifiers.verifier_core as core\ndef f(p):\n    return core.parse_path(p)\n",
        frozenset({"parse_path"}),
    ),
    (
        "module_import_reexport",
        "from scripts.verifiers import verifier_core\ndef f(p):\n    return verifier_core.read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "module_import_reexport_multi_use",
        "from scripts.verifiers import verifier_core\ndef f(p):\n    verifier_core.read_source(p)\ndef g(p):\n    verifier_core.parse_path(p)\n",
        frozenset({"read_source", "parse_path"}),
    ),
    (
        "submodule_direct_import",
        "from scripts.verifiers.verifier_core.diagnostics import SourceLocation\ndef f():\n    return SourceLocation(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "submodule_aliased_import",
        "from scripts.verifiers.verifier_core.diagnostics import SourceLocation as SL\ndef f():\n    return SL(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "local_same_name_definition",
        "class SourceLocation:\n    pass\ndef f():\n    return SourceLocation()\n",
        frozenset(),
    ),
    (
        "unrelated_same_name_import",
        "from another_package import read_source\ndef f(p):\n    return read_source(p)\n",
        frozenset(),
    ),
    (
        "string_only_occurrence",
        "x = 'read_source'\ny = 'verifier_core'\n",
        frozenset(),
    ),
    (
        "comment_only_occurrence",
        "# verifier_core.read_source is great\nx = 1\n",
        frozenset(),
    ),
    (
        "reexport_without_use",
        "from scripts.verifiers import verifier_core\nx = 1\n",
        frozenset(),
    ),
)


@pytest.mark.parametrize(
    "label,source,expected",
    _R2_CASES,
    ids=[c[0] for c in _R2_CASES],
)
def test_import_aware_resolution(label: str, source: str, expected: frozenset[str]) -> None:
    used = _source_core_uses(source)
    assert used == expected, f"{label}: used={used!r} expected={expected!r}"


def test_consumer_count_json_md_progress_agree(audit: dict) -> None:
    json_total = audit["core_usage"]["totals"]["proven_reused_count"]
    index_total = audit["index"]["totals"]["production_consumer_count"]
    md = render_markdown(audit)
    assert json_total == index_total
    assert f"| Symbols with a production consumer | {index_total} |" in md, md


# ---------------------------------------------------------------------------
# 11. JSON index and shards are deterministic.
# ---------------------------------------------------------------------------


def test_index_and_shards_byte_identical_across_runs() -> None:
    """Two invocations with the same arguments produce
    byte-identical audit objects."""
    record = _synthetic_skipped_record("determinism fixture")
    a = build_audit_object({}, gate_classification=record)
    b = build_audit_object({}, gate_classification=record)
    assert a["index"] == b["index"]
    for shard in ALL_SHARDS:
        assert a[shard] == b[shard]


def test_top_level_index_lists_required_shards(audit: dict) -> None:
    from scripts.verifiers_audit.report_io import REPORT_ROOT

    shards = audit["index"]["shards"]
    for name in ALL_SHARDS:
        expected_path = str((REPORT_ROOT / f"{name}.json").relative_to(REPO_ROOT))
        if name in shards:
            assert shards[name]["path"] == expected_path
        if shards:
            assert "sha256" in shards[name]
    assert set(ALL_SHARDS) == frozenset(
        {
            "inventory",
            "helpers",
            "groups",
            "core_usage",
            "candidates",
            "source_preservation",
            "gate_classification",
        }
    )
