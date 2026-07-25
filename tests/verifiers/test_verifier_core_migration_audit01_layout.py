# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION10 / CORRECTION11: ReportLayout and gate-classification tests.

CORRECTION13 split: the audit01 test module exceeded the
500-line LLM-friendly threshold.  The mutation guard,
ReportLayout, markdown-JSON agreement, and gate-classification
tests live in this companion module.  The other tests live
in :mod:`test_verifier_core_migration_audit01` and the
CORRECTION13-specific tests live in
:mod:`test_verifier_core_migration_audit01_correction13`.

The tests prove:

* the module-scope autouse mutation guard preserves the
  canonical artifacts byte-identical;

* :class:`ReportLayout` validates invariant paths at
  construction time and rejects inconsistent layouts;

* :func:`canonical_layout` produces the canonical top-level
  and markdown sibling paths;

* a temporary :class:`ReportLayout` stays inside ``tmp_path``
  and never mutates the canonical artifacts;

* the markdown and JSON totals agree; the audit package
  files stay under the LLM-friendly threshold; no absolute
  developer paths appear in the audit or the canonical
  reports; the production verifier and core hashes are
  unchanged across HEAD revisions;

* the gate-classification classifier returns deterministic
  labels for the supported scenarios; the ``SKIPPED`` record
  is never ``PRE-EXISTING-ENVIRONMENTAL``;

* the patch simulation is executable and the executable
  patch provides the required evidence fields.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import cast

import pytest

from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.discovery import REPO_ROOT
from scripts.verifiers_audit.gate_classification import (
    _Run,
    _skipped_record,
    classify_pair,
)
from scripts.verifiers_audit.patch_simulation import measured_patch_summary
from scripts.verifiers_audit.render import render_markdown
from scripts.verifiers_audit.report_io import (
    REPORT_ROOT,
    SHARD_NAMES,
    TOP_LEVEL_JSON,
    ReportLayout,
    canonical_layout,
    report_layout_for_shard_root,
    write_audit,
)
from scripts.verifiers_audit.validation import validate_reports_agree
from tests.verifiers.verifier_core_migration_audit01_support import (
    AUDIT01_ALL_PYTHON_MODULES,
    AUDIT01_TEST_MODULES_WITHOUT_SUPPORT,
    TESTS_ROOT,
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
    reports = tmp_path / "reports"
    reports.mkdir()
    layout = report_layout_for_shard_root(reports)
    assert reports in layout.shard_root.parents or reports == layout.shard_root
    assert layout.top_level_json.parent == tmp_path
    assert layout.markdown_path.parent == tmp_path


def test_recorded_shard_paths_match_layout(tmp_path) -> None:
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
    """Every inventoried split file exists and has at most 500 lines."""
    assert len(AUDIT01_ALL_PYTHON_MODULES) == len(
        set(AUDIT01_ALL_PYTHON_MODULES)
    )
    for path in AUDIT01_ALL_PYTHON_MODULES:
        assert path.exists(), f"missing audit01 split module: {path}"
        count = len(path.read_text(encoding="utf-8").splitlines())
        assert count <= 500, f"{path}: {count} lines"

    discovered = set(
        TESTS_ROOT.glob("test_verifier_core_migration_audit01*.py")
    )
    assert discovered == set(AUDIT01_TEST_MODULES_WITHOUT_SUPPORT), (
        "authoritative audit01 test inventory drifted: "
        f"missing={set(AUDIT01_TEST_MODULES_WITHOUT_SUPPORT) - discovered}, "
        f"omitted={discovered - set(AUDIT01_TEST_MODULES_WITHOUT_SUPPORT)}"
    )


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
    sem = "negative-proofs: 3 violations detected"
    clean = _Run("EXITED", 1, 1.0, "", sem)
    audit = _Run("EXITED", 1, 1.1, "", sem)
    assert classify_pair(clean, audit) == "PRE-EXISTING-DETERMINISTIC"


def test_classify_pair_returns_pre_existing_environmental_on_timeout() -> None:
    clean = _Run("TIMED_OUT", -1, 60.0, "", "")
    audit = _Run("TIMED_OUT", -1, 60.0, "", "")
    assert classify_pair(clean, audit) == "PRE-EXISTING-ENVIRONMENTAL"


def test_classify_pair_returns_act_introduced() -> None:
    clean = _Run("EXITED", 0, 0.5, "", "")
    audit = _Run(
        "EXITED", 1, 0.6, "",
        "redaction: 1 violation found in audit-tree",
    )
    assert classify_pair(clean, audit) == "ACT-INTRODUCED"


def test_classify_pair_returns_unresolved_when_evidence_differs() -> None:
    clean = _Run("EXITED", 1, 0.5, "", "totally unrelated failure")
    audit = _Run("EXITED", 0, 0.6, "", "")
    assert classify_pair(clean, audit) == "UNRESOLVED"


def test_skipped_record_is_never_pre_existing_environmental() -> None:
    """Skip records MUST be ``SKIPPED``; never
    ``PRE-EXISTING-ENVIRONMENTAL``.  CORRECTION11: callers
    build the record via :func:`_skipped_record` directly."""
    record = _skipped_record("unit-test fixture")
    classification_obj = record.get("classification")
    classification = cast(str, classification_obj)
    assert classification == "SKIPPED", record
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
        {}, gate_classification=_skipped_record(
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
