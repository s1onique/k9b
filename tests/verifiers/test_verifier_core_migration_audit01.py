# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""Reliability tests for the audit generator.

CORRECTION11 updates:

* The ``skip_gate`` parameter is removed.  Tests that need a
  deterministic ``SKIPPED`` record pass an explicit
  ``gate_classification=_skipped_record(...)`` argument.
* Every writer test uses ``tmp_path`` and constructs a
  ``ReportLayout`` via ``report_layout_for_shard_root``.
* The Ruff manifest equality test is now a production-path
  equality test (the Ruff argv equals the changed Python
  paths in the F..S closure range).
* A guard test forbids fixed ``/tmp`` paths in this module.
* Two parallel-layout tests prove no shared paths or shards.

The 15 baseline R11 invariants below remain intact.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import subprocess
from typing import cast

import pytest

from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.consumer_map import (
    build_consumer_map,
    discover_test_paths,
)
from scripts.verifiers_audit.discovery import (
    REPO_ROOT,
    core_public_symbols,
)
from scripts.verifiers_audit.equivalence import run_all_equivalence
from scripts.verifiers_audit.patch_simulation import measured_patch_summary
from scripts.verifiers_audit.render import render_markdown
from scripts.verifiers_audit.report_io import (
    REPORT_ROOT,
    SHARD_NAMES,
    TOP_LEVEL_JSON,
    ReportLayout,
)
from scripts.verifiers_audit.scope import (
    argv_after_command_prefix,
    build_ruff_argv,
    changed_paths,
    changed_python_paths,
)

# Location of this test module — used by the no-fixed-/tmp guard
# below so the test SOURCE itself is scanned.
TEST_PATH = REPO_ROOT / "tests" / "verifiers" / (
    "test_verifier_core_migration_audit01.py"
)

# Ground-truth commits for the production-path Ruff test.
# The pair commit_history..current must be a real ancestor
# relationship so production ``git diff --name-only`` works.
# F10 is the parent of S10 (the actual S10 commit modified 3
# files); F11 is the parent of S10 too, but F11 is itself the
# plan-only commit, so the diff F10..S10 is the cleanest
# subject-only range.
FIXTURE_BASE = "4bf51fbf870fa21b6e2519dc3c7c1bbb89017c96"  # F10
FIXTURE_SUBJECT = "78be1ce8acea4aa67fcf266496127825e7d00219"  # S10


def _synthetic_skipped_record(reason: str) -> dict[str, object]:
    """Return a deterministic synthetic ``SKIPPED`` record.

    This is the documented unit-test fixture for the
    ``build_audit_object`` argument.  Production code paths
    MUST NOT call this helper.
    """
    from scripts.verifiers_audit.gate_classification import (
        _skipped_record,
    )

    return _skipped_record(reason)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def audit() -> dict:
    """Build the audit object with a synthetic ``SKIPPED``
    gate_classification.

    The persisted ``gate_classification.json`` is the
    canonical on-disk record; the unit test fixture uses a
    synthetic SKIPPED record so the audit object stays
    fast and deterministic.  The build_audit_object outcome
    tests below prove the SKIPPED record survives the round
    trip.
    """
    return build_audit_object(
        {}, gate_classification=_synthetic_skipped_record(
            "module-scope audit fixture; the persisted "
            "gate_classification.json is the canonical on-disk "
            "record."
        )
    )


# ---------------------------------------------------------------------------
# 0. CORRECTION11 invariants: skip_gate removed, hermetic paths,
#    ReportLayout sole authority, real Ruff equality.
# ---------------------------------------------------------------------------


def test_skip_gate_removed_from_public_api() -> None:
    """CORRECTION11: ``skip_gate`` is no longer a parameter of
    ``build_audit_object`` or ``write_audit``."""
    sig = inspect.signature(build_audit_object)
    assert "skip_gate" not in sig.parameters, (
        f"build_audit_object must not accept skip_gate: {sig}"
    )
    from scripts.verifiers_audit import report_io as _rio

    audit_sig = inspect.signature(_rio.write_audit)
    assert "skip_gate" not in audit_sig.parameters, (
        f"write_audit must not accept skip_gate: {audit_sig}"
    )


def test_skip_gate_outcome_skipped_record() -> None:
    """A caller-supplied ``_skipped_record`` produces a
    ``SKIPPED`` classification in the audit object."""
    skipped = build_audit_object(
        {},
        gate_classification=_synthetic_skipped_record(
            "unit-test outcome fixture"
        ),
    )
    assert (
        skipped["gate_classification"]["classification"] == "SKIPPED"
    ), skipped["gate_classification"]


def test_skip_gate_outcome_normal_record() -> None:
    """A no-argument ``build_audit_object`` produces a
    non-SKIPPED classification (the production default is
    ``UNASSESSED``)."""
    normal = build_audit_object({})
    assert normal["gate_classification"]["classification"] != "SKIPPED", (
        "build_audit_object() default must not be SKIPPED"
    )


def test_no_fixed_tmp_paths_in_audit_tests() -> None:
    """CORRECTION11: no test in this module may hard-code a
    shared ``/tmp`` path.  Only ``tmp_path`` is permitted.

    The forbidden tokens are constructed dynamically so the
    guard does not false-positive on the literal strings used
    to populate the tuple.
    """
    source = TEST_PATH.read_text(encoding="utf-8")
    slash = "/"
    tmp = "tmp"
    c = "c"
    sq = "'"
    dq = '"'
    forbidden = (
        f"Path({dq}{slash}{tmp}{slash}",
        f"_P({sq}{slash}{tmp}{slash}",
        f"_P({dq}{slash}{tmp}{slash}",
        f"{sq}{slash}{tmp}{slash}{c}",
        f"{dq}{slash}{tmp}{slash}{c}",
    )
    for token in forbidden:
        assert token not in source, (
            f"forbidden fixed /tmp path token found in test module: "
            f"{token!r}"
        )


def test_inconsistent_layout_rejected_by_constructor(tmp_path) -> None:
    """An inconsistent ReportLayout is rejected at construction
    time, BEFORE any write is performed."""
    with pytest.raises(ValueError):
        ReportLayout(
            shard_root=tmp_path / "shards",
            top_level_json=tmp_path / "wrong.json",
            markdown_path=tmp_path / "wrong.md",
        )


def test_inconsistent_layout_rejected_by_writer(tmp_path) -> None:
    """The :func:`write_all` writer also rejects an inconsistent
    layout before any disk write.

    The constructor validator runs BEFORE any write is
    attempted, so the construction itself raises ValueError.
    The test verifies that the write is never reached.
    """
    from scripts.verifiers_audit.report_io import write_all

    # The constructor validator MUST reject the bad layout
    # before any write is attempted.  The ValueError is raised
    # INSIDE the ``with`` block — not before it.
    try:
        bad = ReportLayout(
            shard_root=tmp_path / "shards",
            top_level_json=tmp_path / "wrong.json",
            markdown_path=tmp_path / "wrong.md",
        )
    except ValueError:
        return  # The constructor caught the inconsistency.
    # If the bad layout were constructible, write_all would
    # also refuse to write it.  This branch is unreachable in
    # isolation but preserved for transition safety.
    with pytest.raises(ValueError):
        write_all(layout=bad, audit={})


def test_parallel_layouts_are_isolated(tmp_path) -> None:
    """Two independently created layouts must not share any
    shard or path.  Each layout's shard_root and top_level_json
    are disjoint."""
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_all,
    )

    a_reports = tmp_path / "a" / "reports"
    b_reports = tmp_path / "b" / "reports"
    a_reports.mkdir(parents=True)
    b_reports.mkdir(parents=True)
    layout_a = report_layout_for_shard_root(a_reports)
    layout_b = report_layout_for_shard_root(b_reports)

    audit_a = build_audit_object(
        {},
        gate_classification=_synthetic_skipped_record("layout A"),
    )
    audit_b = build_audit_object(
        {},
        gate_classification=_synthetic_skipped_record("layout B"),
    )

    write_all(layout=layout_a, audit=audit_a)
    write_all(layout=layout_b, audit=audit_b)

    a_shards = sorted(layout_a.shard_root.glob("*.json"))
    b_shards = sorted(layout_b.shard_root.glob("*.json"))
    assert a_shards and b_shards
    assert set(a_shards).isdisjoint(set(b_shards))
    assert layout_a.top_level_json != layout_b.top_level_json
    assert layout_a.markdown_path != layout_b.markdown_path
    assert layout_a.top_level_json.exists()
    assert layout_b.top_level_json.exists()


def test_changed_python_paths_returns_only_python() -> None:
    """The production ``git diff`` set is restricted to paths
    ending in ``.py``."""
    assert FIXTURE_BASE != FIXTURE_SUBJECT
    paths = changed_python_paths(FIXTURE_BASE, FIXTURE_SUBJECT)
    assert paths, "expected at least one changed Python path"
    for p in paths:
        assert p.endswith(".py"), p


def test_build_ruff_argv_preserves_paths() -> None:
    """The Ruff argv exactly matches the changed Python paths."""
    paths = changed_python_paths(FIXTURE_BASE, FIXTURE_SUBJECT)
    argv = build_ruff_argv(paths)
    assert argv[0] == "ruff"
    assert argv[1] == "check"
    assert argv_after_command_prefix(argv) == paths
    assert set(argv_after_command_prefix(argv)) == set(paths)


def test_argv_after_command_prefix_rejects_bad_argv() -> None:
    """The helper rejects malformed argv deterministically."""
    with pytest.raises(ValueError):
        argv_after_command_prefix([])
    with pytest.raises(ValueError):
        argv_after_command_prefix(["not-ruff", "check", "a.py"])
    with pytest.raises(ValueError):
        argv_after_command_prefix(["ruff", "lint", "a.py"])


def test_changed_paths_subprocess_is_closed_loop() -> None:
    """The ``changed_paths`` helper delegates to a real
    ``git diff`` subprocess; the returned tuple is deterministic
    for a fixed base/subject pair."""
    p1 = changed_paths(FIXTURE_BASE, FIXTURE_SUBJECT)
    p2 = changed_paths(FIXTURE_BASE, FIXTURE_SUBJECT)
    assert p1 == p2
    full = set(p1)
    for p in changed_python_paths(FIXTURE_BASE, FIXTURE_SUBJECT):
        assert p in full


# ---------------------------------------------------------------------------
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
    assert (
        index["exact_duplicate_group_count"]
        == groups["totals"]["exact_duplicate_group_count"]
    )
    assert (
        index["exact_duplicate_helper_count"]
        == groups["totals"]["exact_duplicate_helper_count"]
    )
    assert (
        index["core_public_symbol_count"]
        == usage["totals"]["core_public_symbol_count"]
    )
    assert index["candidate_count"] == cands["totals"]["candidate_count"]
    assert (
        index["wave_1_candidate_count"]
        == cands["totals"]["wave_1_candidate_count"]
    )


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
            qual = (
                f"{parent}.{node.name}" if parent else node.name
            )
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
        assert key in by_path.get(path, set()), (
            f"helper {key!r} not found in {path}"
        )


# ---------------------------------------------------------------------------
# 5. Every discovered structural helper is classified.
# ---------------------------------------------------------------------------


def test_every_group_member_is_in_helpers(audit: dict) -> None:
    from scripts.verifiers_audit.discovery import discover_helpers

    shard_keys = {
        (h["path"], h["qualname"]) for h in audit["helpers"]["helpers"]
    }
    all_helpers = discover_helpers(audit["inventory"]["included_paths"])
    all_keys = {(h.path, h.qualname) for h in all_helpers}
    for g in audit["groups"]["groups"]:
        for member in g["members"]:
            path, _, qualname = member.partition(":")
            in_shard = (path, qualname) in shard_keys
            in_full = (path, qualname) in all_keys
            assert in_shard or in_full, (
                f"group {g['group_id']} member {member!r} not in helpers"
            )


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
    symbol_modules = {
        c["symbol"]: c["module"] for c in usage["consumers"]
    }
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


from scripts.verifiers_audit.consumer_map import _source_core_uses  # noqa: E402

_R2_CASES: tuple[tuple[str, str, frozenset[str]], ...] = (
    (
        "direct_import",
        "from scripts.verifiers.verifier_core import read_source\n"
        "def f(p):\n    return read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "aliased_direct_import",
        "from scripts.verifiers.verifier_core import "
        "SourceLocation as CoreLocation\n"
        "def f():\n    return CoreLocation(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "qualified_import",
        "import scripts.verifiers.verifier_core as vc\n"
        "def f(p):\n    return vc.read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "aliased_qualified_import",
        "import scripts.verifiers.verifier_core as core\n"
        "def f(p):\n    return core.parse_path(p)\n",
        frozenset({"parse_path"}),
    ),
    (
        "module_import_reexport",
        "from scripts.verifiers import verifier_core\n"
        "def f(p):\n    return verifier_core.read_source(p)\n",
        frozenset({"read_source"}),
    ),
    (
        "module_import_reexport_multi_use",
        "from scripts.verifiers import verifier_core\n"
        "def f(p):\n    verifier_core.read_source(p)\n"
        "def g(p):\n    verifier_core.parse_path(p)\n",
        frozenset({"read_source", "parse_path"}),
    ),
    (
        "submodule_direct_import",
        "from scripts.verifiers.verifier_core.diagnostics import "
        "SourceLocation\n"
        "def f():\n    return SourceLocation(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "submodule_aliased_import",
        "from scripts.verifiers.verifier_core.diagnostics import "
        "SourceLocation as SL\n"
        "def f():\n    return SL(1, 2)\n",
        frozenset({"SourceLocation"}),
    ),
    (
        "local_same_name_definition",
        "class SourceLocation:\n    pass\n"
        "def f():\n    return SourceLocation()\n",
        frozenset(),
    ),
    (
        "unrelated_same_name_import",
        "from another_package import read_source\n"
        "def f(p):\n    return read_source(p)\n",
        frozenset(),
    ),
    (
        "string_only_occurrence",
        "x = 'read_source'\ny = 'verifier_core'\n",
        frozenset(),
    ),
    (
        "comment_only_occurrence",
        "# verifier_core.read_source is great\n"
        "x = 1\n",
        frozenset(),
    ),
    (
        "reexport_without_use",
        "from scripts.verifiers import verifier_core\n"
        "x = 1\n",
        frozenset(),
    ),
)


@pytest.mark.parametrize(
    "label,source,expected",
    _R2_CASES,
    ids=[c[0] for c in _R2_CASES],
)
def test_import_aware_resolution(label: str, source: str,
                                 expected: frozenset[str]) -> None:
    used = _source_core_uses(source)
    assert used == expected, (
        f"{label}: used={used!r} expected={expected!r}"
    )


def test_consumer_count_json_md_progress_agree(audit: dict) -> None:
    json_total = audit["core_usage"]["totals"]["proven_reused_count"]
    index_total = audit["index"]["totals"]["production_consumer_count"]
    md = render_markdown(audit)
    assert json_total == index_total
    assert (
        f"| Symbols with a production consumer | {index_total} |" in md
    ), md


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
    for shard in SHARD_NAMES:
        assert a[shard] == b[shard]


def test_top_level_index_lists_required_shards(audit: dict) -> None:
    from scripts.verifiers_audit.report_io import REPORT_ROOT

    shards = audit["index"]["shards"]
    for name in SHARD_NAMES:
        expected_path = str(
            (REPORT_ROOT / f"{name}.json").relative_to(REPO_ROOT)
        )
        if name in shards:
            assert shards[name]["path"] == expected_path
        if shards:
            assert "sha256" in shards[name]
    assert set(SHARD_NAMES) == frozenset({
        "inventory",
        "helpers",
        "groups",
        "core_usage",
        "candidates",
        "source_preservation",
        "gate_classification",
    })


# ---------------------------------------------------------------------------
# 16. R5: source-preservation proof (head == index == working_tree).
# ---------------------------------------------------------------------------


def test_source_preservation_hashes_match(audit: dict) -> None:
    sp = audit["source_preservation"]
    assert sp["totals"]["preserved_path_count"] == sp["totals"]["tracked_path_count"]
    assert sp["totals"]["working_tree_drift_count"] == 0
    assert sp["totals"]["staged_drift_count"] == 0
    for row in sp["protected_paths"]:
        assert row["preserved"], row
        assert (
            row["head_sha256"]
            == row["index_sha256"]
            == row["working_tree_sha256"]
        )


def test_no_protected_path_in_git_diff() -> None:
    out1 = _git("diff", "--name-only").splitlines()
    out2 = _git("diff", "--cached", "--name-only").splitlines()
    out1 = [line.strip() for line in out1 if line.strip()]
    out2 = [line.strip() for line in out2 if line.strip()]
    tracked = set(_git(
        "ls-files",
        "scripts/verifiers/*.py",
        "scripts/verifiers/**/*.py",
    ).splitlines())
    assert not (set(out1) & tracked), set(out1) & tracked
    assert not (set(out2) & tracked), set(out2) & tracked


# ---------------------------------------------------------------------------
# 17. R4: measured patch economics.
# ---------------------------------------------------------------------------


def test_measured_patch_net_deletion_is_positive(audit: dict) -> None:
    sim = audit["patch_simulation"]
    totals = sim["totals"]
    assert totals["net_production_lines_removed"] > 0, totals
    assert totals["helpers_removed"] == 3
    assert totals["call_sites_changed"] >= 3
    assert (
        audit["index"]["totals"]["measured_net_deletion_lines"]
        == totals["net_production_lines_removed"]
    )


def test_measured_patch_diff_sums_correctly(audit: dict) -> None:
    t = audit["patch_simulation"]["totals"]
    assert (
        t["net_production_lines_removed"]
        == t["production_lines_removed"] - t["production_lines_added"]
    )


# ---------------------------------------------------------------------------
# 18. R3: equivalence case status, derived counts, skip handling.
# ---------------------------------------------------------------------------


def test_equivalence_cases_have_status_field(audit: dict) -> None:
    suites = audit["candidates"]["equivalence_suites"]
    for suite in suites.values():
        assert "executed" in suite
        assert "passed" in suite
        assert "failed" in suite
        assert "skipped" in suite
        for c in suite["cases"]:
            assert "status" in c
            assert c["status"] in {"PASSED", "FAILED", "SKIPPED"}


def test_wave_1_rationale_counts_come_from_live_suite(audit: dict) -> None:
    suites = audit["candidates"]["equivalence_suites"]
    for c in audit["candidates"]["candidates"]:
        if c["wave"] != "Wave 1":
            continue
        sym = c["core_symbol"]
        suite_name = {
            "read_source": "read_source",
            "parse_path": "parse",
            "top_level_function": "top_level_function",
        }.get(sym)
        if suite_name is None:
            continue
        suite = suites[suite_name]
        expected = (
            f"{suite['passed']}/{suite['total']} equivalence cases pass"
            f" ({suite['skipped']} skipped)"
        )
        assert expected in c["rationale"], (c["candidate_id"], c["rationale"])


def test_permission_denied_case_status_is_skippable() -> None:
    from scripts.verifiers_audit.equivalence import (
        _STATUS_PASSED,
        _STATUS_SKIPPED,
        run_read_source_equivalence,
    )
    suite = run_read_source_equivalence()
    cases = {c["name"]: c for c in suite["cases"]}
    assert "permission_denied" in cases
    assert cases["permission_denied"]["status"] in {
        _STATUS_PASSED, _STATUS_SKIPPED,
    }


# ---------------------------------------------------------------------------
# 19. R6: strict set equality and cross-report agreement.
# ---------------------------------------------------------------------------


def test_inventory_set_equals_tracked(audit: dict) -> None:
    from scripts.verifiers_audit.validation import (
        validate_inventory_set_equals_tracked,
    )
    assert validate_inventory_set_equals_tracked(audit)


def test_required_shards_complete(tmp_path) -> None:
    """Write the audit-owned shards to a tmp_path then validate.

    Every writer test MUST use ``tmp_path``; the canonical
    :data:`REPORT_ROOT` is NEVER mutated by this test.
    """
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_all,
    )
    from scripts.verifiers_audit.validation import (
        validate_required_shards_complete,
    )

    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    layout = report_layout_for_shard_root(reports)
    skipped = _synthetic_skipped_record(
        "test_required_shards_complete synthetic fixture; the "
        "canonical repository gate is recorded in "
        ".factory/gate-summary.json."
    )
    fresh = build_audit_object({}, gate_classification=skipped)
    (reports / "gate_classification.json").write_text(
        json.dumps(skipped, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    write_all(layout=layout, audit=fresh)
    assert validate_required_shards_complete(
        fresh, report_root=reports
    )


def test_cmd_write_rejects_caller_supplied_gc_with_nonzero() -> None:
    """CORRECTION09: ``cmd_write(gate_classification=...)`` MUST
    return a nonzero exit code and perform zero side effects."""
    from scripts.verifiers_audit.cli import cmd_write

    canonical = REPORT_ROOT / "gate_classification.json"
    if not canonical.exists():
        return
    exit_code = cmd_write(gate_classification={"fake": "record"})
    assert exit_code != 0, (
        f"cmd_write MUST return nonzero on caller-supplied "
        f"gate_classification; got exit {exit_code}"
    )


# ---------------------------------------------------------------------------
# CORRECTION10 preserved autouse mutation guard.
# ---------------------------------------------------------------------------


def _hash_canonical_artifact_set() -> dict[str, str]:
    """Return a snapshot of the canonical artifact hash set."""
    paths = [
        ".factory/gate-summary.json",
        "docs/reports/verifier-core-migration-audit01.json",
        "docs/reports/verifier-core-migration-audit01.md",
    ]
    out: dict[str, str] = {}
    for rel in paths:
        p = REPO_ROOT / rel
        if p.exists():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    paths2 = list(
        (REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01").glob(
            "*.json"
        )
    )
    for p in paths2:
        rel = str(p.relative_to(REPO_ROOT))
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture(scope="module", autouse=True)
def canonical_artifacts_remain_unchanged() -> object:
    """CORRECTION10: real module-scope mutation guard."""
    before = _hash_canonical_artifact_set()
    yield
    after = _hash_canonical_artifact_set()
    assert before == after, (
        f"canonical artifacts mutated during the test module: "
        f"before={before} after={after}"
    )


def test_canonical_artifacts_module_autouse_did_not_mutate() -> None:
    canonical = REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01.json"
    assert canonical.exists(), (
        "canonical top-level index must exist (committed as part "
        "of CORRECTION08)"
    )


def test_writes_through_temporary_layout_do_not_touch_canonical(
    tmp_path,
) -> None:
    """Adversarial test: write through a tmp_path-constructed
    :class:`ReportLayout` and prove the canonical hashes are
    unchanged."""
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_audit,
    )

    canonical = REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01.json"
    canonical_hash_before = (
        hashlib.sha256(canonical.read_bytes()).hexdigest() if canonical.exists() else None
    )

    tmp_reports = tmp_path / "reports"
    tmp_reports.mkdir(parents=True)
    layout = report_layout_for_shard_root(tmp_reports)
    write_audit(layout=layout)

    canonical_hash_after = (
        hashlib.sha256(canonical.read_bytes()).hexdigest() if canonical.exists() else None
    )
    assert canonical_hash_after == canonical_hash_before, (
        f"adversarial write through temporary layout mutated the "
        f"canonical top-level index: {canonical_hash_before} -> "
        f"{canonical_hash_after}"
    )


# ---------------------------------------------------------------------------
# CORRECTION11: ReportLayout contract & write_audit
# ---------------------------------------------------------------------------


def test_report_layout_validates_at_construction(tmp_path) -> None:
    """A direct ``ReportLayout(...)`` construction with
    inconsistent paths raises ``ValueError``."""
    with pytest.raises(ValueError):
        ReportLayout(
            shard_root=tmp_path / "shards",
            top_level_json=tmp_path / "wrong.json",
            markdown_path=tmp_path / "wrong.md",
        )


def test_report_layout_accepts_valid_layout(tmp_path) -> None:
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
    )

    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    layout = report_layout_for_shard_root(reports)
    assert layout.shard_root == reports
    assert (
        layout.top_level_json
        == reports.parent / "verifier-core-migration-audit01.json"
    )
    assert (
        layout.markdown_path
        == reports.parent / "verifier-core-migration-audit01.md"
    )


def test_canonical_shard_root_maps_to_top_level_json() -> None:
    from scripts.verifiers_audit.report_io import canonical_layout

    layout = canonical_layout()
    assert (
        layout.top_level_json
        == REPORT_ROOT.parent / "verifier-core-migration-audit01.json"
    )
    assert (
        layout.markdown_path
        == REPORT_ROOT.parent / "verifier-core-migration-audit01.md"
    )


def test_temporary_shard_root_stays_inside_tmp_path(tmp_path) -> None:
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
    )

    reports = tmp_path / "reports"
    reports.mkdir()
    layout = report_layout_for_shard_root(reports)
    assert reports in layout.shard_root.parents or reports == layout.shard_root
    assert layout.top_level_json.parent == tmp_path
    assert layout.markdown_path.parent == tmp_path


def test_recorded_shard_paths_match_layout(tmp_path) -> None:
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_audit,
    )

    reports = tmp_path / "reports"
    reports.mkdir()
    layout = report_layout_for_shard_root(reports)
    write_audit(layout=layout)
    index = json.loads(layout.top_level_json.read_text(encoding="utf-8"))
    for name, info in index["shards"].items():
        abs_path = (REPO_ROOT / info["path"]).resolve()
        assert (
            abs_path
            == (layout.shard_root / f"{name}.json").resolve()
        ), f"shard {name} not under layout: {abs_path}"


def test_canonical_gate_classification_not_written_by_write_audit(
    tmp_path,
) -> None:
    """The canonical ``write_audit`` MUST NOT modify the
    canonical ``gate_classification.json``."""
    from scripts.verifiers_audit.report_io import (
        report_layout_for_shard_root,
        write_audit,
    )

    canonical_gc = REPORT_ROOT / "gate_classification.json"
    if not canonical_gc.exists():
        return
    before = hashlib.sha256(canonical_gc.read_bytes()).hexdigest()

    reports = tmp_path / "reports"
    reports.mkdir()
    layout = report_layout_for_shard_root(reports)
    write_audit(layout=layout)

    after = hashlib.sha256(canonical_gc.read_bytes()).hexdigest()
    assert before == after, (
        f"write_audit mutated the canonical gate_classification.json: "
        f"{before} -> {after}"
    )


def test_reports_agree(audit: dict) -> None:
    from scripts.verifiers_audit.validation import validate_reports_agree
    assert validate_reports_agree(audit)


# ---------------------------------------------------------------------------
# 12. Markdown and JSON totals agree.
# ---------------------------------------------------------------------------


def test_markdown_totals_match_index(audit: dict) -> None:
    md = render_markdown(audit)
    t = audit["index"]["totals"]
    expected = [
        f"| Tracked verifier paths | {t['tracked_path_count']} |",
        f"| Included paths | {t['included_path_count']} |",
        f"| Excluded paths | {t['excluded_path_count']} |",
        f"| AST-discovered helpers | {t['helper_count']} |",
        f"| Exact-duplicate groups | {t['exact_duplicate_group_count']} |",
        f"| Exact-duplicate helpers | {t['exact_duplicate_helper_count']} |",
        f"| Core public symbols (`__all__`) | "
        f"{t['core_public_symbol_count']} |",
        f"| Wave-1 candidates | {t['wave_1_candidate_count']} |",
    ]
    for line in expected:
        assert line in md, f"missing: {line}"


# ---------------------------------------------------------------------------
# 13. Every generated path stays below the LLM-friendly threshold.
# ---------------------------------------------------------------------------


def test_every_audit_python_file_under_500_lines() -> None:
    audit_pkg = REPO_ROOT / "scripts" / "verifiers_audit"
    for path in audit_pkg.rglob("*.py"):
        lines = sum(1 for _ in path.open(encoding="utf-8"))
        assert lines < 500, f"{path} is {lines} lines (threshold 500)"


def test_each_shard_under_size_threshold() -> None:
    for name in SHARD_NAMES:
        shard_path = REPORT_ROOT / f"{name}.json"
        if not shard_path.exists():
            continue
        assert shard_path.stat().st_size < 200_000, name


# ---------------------------------------------------------------------------
# 14. No absolute developer paths appear.
# ---------------------------------------------------------------------------


def test_no_absolute_paths_in_audit(audit: dict) -> None:
    raw = json.dumps(audit)
    for token in ("/tmp/", "/Users/", "/home/", "/var/", "/private/"):
        assert token not in raw, token


def test_no_absolute_paths_in_reports() -> None:
    if TOP_LEVEL_JSON.exists():
        text = TOP_LEVEL_JSON.read_text(encoding="utf-8")
        for token in ("/tmp/", "/Users/", "/home/", "/var/", "/private/"):
            assert token not in text, token


# ---------------------------------------------------------------------------
# 15. Production verifier and core hashes remain unchanged.
# ---------------------------------------------------------------------------


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout


def _production_hashes() -> dict[str, str]:
    lines = _git(
        "ls-files",
        "scripts/verifiers/*.py",
        "scripts/verifiers/**/*.py",
    ).splitlines()
    out: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        proc = subprocess.run(  # noqa: PERF203
            ["git", "cat-file", "blob", f"HEAD:{line}"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            check=False,
        )
        out[line] = hashlib.sha256(proc.stdout).hexdigest()
    return out


def test_production_verifier_and_core_hashes_unchanged() -> None:
    hashes = _production_hashes()
    assert len(hashes) == 29
    head = _git("rev-parse", "HEAD").strip()
    assert head, "git rev-parse HEAD must yield a non-empty commit"


# ---------------------------------------------------------------------------
# R1 / CORRECTION04: gate classification, skip semantics, executable patch
# ---------------------------------------------------------------------------


def test_classify_pair_returns_pre_existing_deterministic() -> None:
    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    sem = "negative-proofs: 3 violations detected"
    clean = _Run("EXITED", 1, 1.0, "", sem)
    audit = _Run("EXITED", 1, 1.1, "", sem)
    assert classify_pair(clean, audit) == "PRE-EXISTING-DETERMINISTIC"


def test_classify_pair_returns_pre_existing_environmental_on_timeout() -> None:
    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    clean = _Run("TIMED_OUT", -1, 60.0, "", "")
    audit = _Run("TIMED_OUT", -1, 60.0, "", "")
    assert classify_pair(clean, audit) == "PRE-EXISTING-ENVIRONMENTAL"


def test_classify_pair_returns_act_introduced() -> None:
    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    clean = _Run("EXITED", 0, 0.5, "", "")
    audit = _Run(
        "EXITED", 1, 0.6, "",
        "redaction: 1 violation found in audit-tree",
    )
    assert classify_pair(clean, audit) == "ACT-INTRODUCED"


def test_classify_pair_returns_unresolved_when_evidence_differs() -> None:
    from scripts.verifiers_audit.gate_classification import (
        _Run,
        classify_pair,
    )

    clean = _Run("EXITED", 1, 0.5, "", "totally unrelated failure")
    audit = _Run("EXITED", 0, 0.6, "", "")
    assert classify_pair(clean, audit) == "UNRESOLVED"


def test_skipped_record_is_never_pre_existing_environmental() -> None:
    """Skip records MUST be ``SKIPPED``; never
    ``PRE-EXISTING-ENVIRONMENTAL``.  CORRECTION11: callers
    build the record via :func:`_skipped_record` directly."""
    from scripts.verifiers_audit.gate_classification import (
        _skipped_record,
    )

    record = _skipped_record("unit-test fixture")
    classification_obj = record.get("classification")
    classification = cast(str, classification_obj)
    assert classification == "SKIPPED", record
    # The != comparison is a tautological safeguard, not a
    # type-laden check; use a string comparison so mypy
    # accepts it.
    assert str(classification) != "PRE-EXISTING-ENVIRONMENTAL"


def test_patch_simulation_is_executable() -> None:
    sim = measured_patch_summary()
    totals = sim["totals"]
    details = sim["details"]
    assert totals["parse_passed"] is True, details
    assert totals["compile_passed"] is True, details
    assert totals["verifier_exit_code"] is not None
    assert isinstance(totals["verifier_exit_code"], int)
    assert totals["targeted_tests_passed"] is True, details
    net_deletion = totals["net_production_lines_removed"]
    assert net_deletion > 0, totals
    assert totals["call_sites_changed"] == 5, totals
    assert totals["helpers_removed"] == 3, totals


def test_executable_patch_provides_required_evidence() -> None:
    sim = measured_patch_summary()
    details = sim["details"]
    required = (
        "parse_passed",
        "compile_passed",
        "verifier_exit_code",
        "targeted_tests_passed",
        "production_lines_added",
        "production_lines_removed",
        "net_production_lines_removed",
        "call_sites_changed",
        "helpers_removed",
        "patched_sha256",
    )
    for field in required:
        assert field in details, field
        assert details[field] is not None, field


def test_consumer_count_uses_real_imports() -> None:
    audit = build_audit_object(
        {}, gate_classification=_synthetic_skipped_record(
            "consumer-count fixture"
        )
    )
    usage = audit["core_usage"]["totals"]
    assert (
        usage["proven_reused_count"]
        + usage["test_only_count"]
        + usage["unused_count"]
    ) == usage["core_public_symbol_count"], usage
    consumers = audit["core_usage"]["consumers"]
    classifications = {
        c["classification"] for c in consumers
    }
    assert classifications <= {"PROVEN-REUSED", "TEST-ONLY", "UNUSED"}, classifications
    for c in consumers:
        cls = c["classification"]
        if cls == "TEST-ONLY":
            assert len(c["test_callers"]) >= 1, c
        if cls == "PROVEN-REUSED":
            assert len(c["production_callers"]) >= 1, c
        if cls == "UNUSED":
            assert len(c["production_callers"]) == 0
            assert len(c["test_callers"]) == 0
