# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION04 / R4-R6: source-preservation, measured patch
economics, and R6 strict-set equality tests.

CORRECTION13 split: the audit01 test module exceeded the
500-line LLM-friendly threshold.  The R-suite tests live in
this companion module.  The other tests live in
:mod:`test_verifier_core_migration_audit01` and the
CORRECTION13-specific tests live in
:mod:`test_verifier_core_migration_audit01_correction13`.

The tests prove:

* source-preservation proof: every protected path is
  byte-equal between HEAD, the index, and the working tree;
* measured patch economics: the patch simulation yields
  positive net production lines removed;
* equivalence case status: every equivalence case has a
  ``status`` field; the Wave-1 rationale is sourced from the
  live equivalence suite;
* strict set equality and cross-report agreement: the
  inventory set equals the tracked set; the required shards
  are complete; reports_agree validates cross-shard
  agreement.
"""

from __future__ import annotations

import json

from scripts.verifiers_audit.discovery import REPO_ROOT
from scripts.verifiers_audit.validation import (
    validate_inventory_set_equals_tracked,
)

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
        assert row["head_sha256"] == row["index_sha256"] == row["working_tree_sha256"]


def test_no_protected_path_in_git_diff() -> None:
    import subprocess

    out1 = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    out2 = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    out1 = [line.strip() for line in out1 if line.strip()]
    out2 = [line.strip() for line in out2 if line.strip()]
    ls_proc = subprocess.run(
        [
            "git",
            "ls-files",
            "scripts/verifiers/*.py",
            "scripts/verifiers/**/*.py",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    tracked = set(ls_proc.stdout.splitlines())
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
    assert audit["index"]["totals"]["measured_net_deletion_lines"] == totals["net_production_lines_removed"]


def test_measured_patch_diff_sums_correctly(audit: dict) -> None:
    t = audit["patch_simulation"]["totals"]
    assert t["net_production_lines_removed"] == t["production_lines_removed"] - t["production_lines_added"]


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
        expected = f"{suite['passed']}/{suite['total']} equivalence cases pass ({suite['skipped']} skipped)"
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
        _STATUS_PASSED,
        _STATUS_SKIPPED,
    }


# ---------------------------------------------------------------------------
# 19. R6: strict set equality and cross-report agreement.
# ---------------------------------------------------------------------------


def test_inventory_set_equals_tracked(audit: dict) -> None:
    assert validate_inventory_set_equals_tracked(audit)


def test_required_shards_complete(tmp_path) -> None:
    """Write the audit-owned shards to a tmp_path then validate.

    Every writer test MUST use ``tmp_path``; the canonical
    :data:`REPORT_ROOT` is NEVER mutated by this test.
    """
    from scripts.verifiers_audit.builder import build_audit_object
    from scripts.verifiers_audit.gate_classification import (
        _skipped_record,
    )
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
    skipped = _skipped_record("test_required_shards_complete synthetic fixture; the canonical repository gate is recorded in .factory/gate-summary.json.")
    fresh = build_audit_object({}, gate_classification=skipped)
    (reports / "gate_classification.json").write_text(
        json.dumps(skipped, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    write_all(layout=layout, audit=fresh)
    assert validate_required_shards_complete(fresh, report_root=reports)
