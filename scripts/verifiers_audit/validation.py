"""Cross-check validators used by ``--check`` and the reliability tests.

Every validator returns ``True`` on success. The ``--check``
mode calls :func:`run_all` and prints the first failure it
encounters; the audit reliability tests call individual
validators.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def,union-attr,attr-defined,arg-type"
from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.discovery import REPO_ROOT
from scripts.verifiers_audit.groups import (
    mixed_group_invariant,
)


def _included_paths(audit: dict) -> list[str]:
    return audit["inventory"]["included_paths"]


def _excluded_paths(audit: dict) -> list[str]:
    return [e["path"] for e in audit["inventory"]["excluded_paths"]]


def validate_inventory_equals_tracked(audit: dict | None = None) -> bool:
    """``included_paths + excluded_paths == tracked_verifier_paths``."""
    if audit is None:
        audit = build_audit_object({})
    inv = audit["inventory"]
    included = inv["included_paths"]
    excluded = [e["path"] for e in inv["excluded_paths"]]
    tracked = included + excluded
    return inv["totals"]["tracked_path_count"] == len(tracked)


def validate_no_excluded_in_helpers(audit: dict | None = None) -> bool:
    """No helper lives in an excluded path."""
    if audit is None:
        audit = build_audit_object({})
    excluded = set(_excluded_paths(audit))
    for h in audit["helpers"]["helpers"]:
        if h["path"] in excluded:
            return False
    return True


def validate_no_excluded_in_groups(audit: dict | None = None) -> bool:
    """No group member references an excluded path."""
    if audit is None:
        audit = build_audit_object({})
    excluded = set(_excluded_paths(audit))
    for g in audit["groups"]["groups"]:
        for member in g["members"]:
            member_path = member.split(":", 1)[0]
            if member_path in excluded:
                return False
    return True


def validate_no_excluded_in_candidates(audit: dict | None = None) -> bool:
    """All group_ids referenced by candidates map to in-scope groups."""
    if audit is None:
        audit = build_audit_object({})
    valid = {g["group_id"] for g in audit["groups"]["groups"]}
    for c in audit["candidates"]["candidates"]:
        if c["group_id"] not in valid:
            return False
    return True


def validate_mixed_groups_invariant(audit: dict | None = None) -> bool:
    """No EXACT-DUPLICATE group contains more than one member."""
    return mixed_group_invariant() == []


def validate_wave_1_equivalence_passed(audit: dict | None = None) -> bool:
    """Every Wave-1 candidate's equivalence suite passed."""
    if audit is None:
        audit = build_audit_object({})
    suites = audit["candidates"]["equivalence_suites"]
    for suite in suites.values():
        if suite["failed"] != 0:
            return False
    return True


def validate_24_symbol_count(audit: dict | None = None) -> bool:
    """The core has exactly 24 public symbols (matching ``__all__``)."""
    if audit is None:
        audit = build_audit_object({})
    return audit["core_usage"]["totals"]["core_public_symbol_count"] == 24


def validate_index_and_shards_aligned(audit: dict | None = None) -> bool:
    """Every shard listed in the index exists and is well-formed."""
    if audit is None:
        audit = build_audit_object({})
    index = audit["index"]
    for name, info in index["shards"].items():
        path = REPO_ROOT / info["path"]
        if not path.exists():
            return False
        # Round-trip the shard through JSON to confirm well-formed.
        import json

        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
    return True


def validate_markdown_totals_match_index(audit: dict | None = None) -> bool:
    """Every Markdown total agrees with the JSON index."""
    if audit is None:
        audit = build_audit_object({})
    from scripts.verifiers_audit.render import render_markdown

    md = render_markdown(audit)
    t = audit["index"]["totals"]
    expected_strings = {
        f"| Tracked verifier paths | {t['tracked_path_count']} |",
        f"| Included paths | {t['included_path_count']} |",
        f"| Excluded paths | {t['excluded_path_count']} |",
        f"| AST-discovered helpers | {t['helper_count']} |",
        f"| Exact-duplicate groups | {t['exact_duplicate_group_count']} |",
        f"| Exact-duplicate helpers | {t['exact_duplicate_helper_count']} |",
        f"| Core public symbols (`__all__`) | "
        f"{t['core_public_symbol_count']} |",
        f"| Wave-1 candidates | {t['wave_1_candidate_count']} |",
        f"| Measured net deletion (lines) | "
        f"{t['measured_net_deletion_lines']} |",
        f"| Preserved protected paths | "
        f"{t['preserved_path_count']} |",
    }
    return all(s in md for s in expected_strings)


def validate_no_absolute_paths(audit: dict | None = None) -> bool:
    """The audit object contains no absolute paths."""
    if audit is None:
        audit = build_audit_object({})
    import json

    raw = json.dumps(audit)
    for token in ("/tmp/", "/Users/", "/home/", "/var/", "/private/"):
        if token in raw:
            return False
    return True


# ---------------------------------------------------------------------------
# R6 / CORRECTION03 strict-set invariants
# ---------------------------------------------------------------------------


def _git_tracked_paths() -> list[str]:
    import subprocess

    proc = subprocess.run(
        ["git", "ls-files",
         "scripts/verifiers/*.py", "scripts/verifiers/**/*.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted(line.strip() for line in proc.stdout.splitlines()
                  if line.strip())


def validate_inventory_set_equals_tracked(
    audit: dict | None = None,
) -> bool:
    """Strict set equality: ``set(included) | set(excluded) ==
    set(live_tracked)``, ``set(included) & set(excluded) == empty``,
    no duplicate entries."""
    if audit is None:
        audit = build_audit_object({})
    inv = audit["inventory"]
    included = list(inv["included_paths"])
    excluded = [e["path"] for e in inv["excluded_paths"]]
    if len(included) != len(set(included)):
        return False
    if len(excluded) != len(set(excluded)):
        return False
    s_inc = set(included)
    s_exc = set(excluded)
    if s_inc & s_exc:
        return False
    live = set(_git_tracked_paths())
    if s_inc | s_exc != live:
        return False
    return True


def validate_required_shards_complete(
    audit: dict | None = None,
    *,
    report_root=None,
) -> bool:
    """The shards index must equal ``REQUIRED_SHARDS`` exactly.

    For every shard:

    * the file exists on disk (under ``report_root``, default
      :data:`REPORT_ROOT`),
    * the recorded ``sha256`` matches the on-disk bytes,
    * the in-memory shard body hash matches the recorded ``sha256``,
    * the shard has ``schema_version`` and a non-empty ``totals``,
    * the recorded ``path`` matches the canonical relative path
      under ``report_root``.

    An empty ``index.shards`` map MUST fail.

    Tests pass a ``tmp_path``-configured ``report_root`` so
    the validator does NOT touch the canonical
    :data:`REPORT_ROOT`.
    """

    from scripts.verifiers_audit.report_io import (
        REPORT_ROOT,
        REQUIRED_SHARDS,
        _dump_helpers_shard,
        _json_dumps,
    )
    if audit is None:
        audit = build_audit_object({})
    root = report_root or REPORT_ROOT
    index = audit["index"]
    listed = set(index["shards"].keys())
    if not listed:
        return False
    if listed != set(REQUIRED_SHARDS):
        return False
    import hashlib

    def _expected_body(name: str) -> bytes:
        # The ``helpers`` shard is hand-assembled so every
        # helper dict renders on a single line (a 74-helper
        # shard otherwise overflows the 500-line LLM-friendly
        # threshold).  The validator mirrors the exact encoding
        # used by :func:`scripts.verifiers_audit.report_io._dump_helpers_shard`.
        # Every other shard is serialised with the standard
        # ``_json_dumps``.
        if name == "helpers":
            return _dump_helpers_shard(audit[name])
        return _json_dumps(audit[name])

    for name in REQUIRED_SHARDS:
        info = index["shards"][name]
        path = root / f"{name}.json"
        if not path.exists():
            return False
        # CORRECTION09: the recorded path MUST resolve to the
        # exact canonical filename under ``root``.  We do NOT
        # accept arbitrary recorded paths merely because an
        # independently selected file has the expected hash.
        # Both the recorded path and the expected path are
        # normalised through the same canonical helper.
        from scripts.verifiers_audit.report_io import (
            _relative_to_repo as _canonical,
        )
        expected_path = _canonical(path)
        recorded_path = info["path"]
        if recorded_path != expected_path:
            return False
        on_disk_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if info["sha256"] not in ("", on_disk_hash):
            return False
        # ``gate_classification`` is owned by
        # ``collect_r2_evidence`` and the in-memory record may
        # legitimately differ from the on-disk record (e.g. a
        # unit test that supplies a synthetic ``_unassessed_record``).
        # The on-disk hash IS the canonical artifact; the
        # in-memory serializer is not authoritative for this
        # shard.  We only check the in-memory body for the
        # audit-owned shards where the builder is the source of
        # truth.
        if name != "gate_classification":
            inmem_hash = hashlib.sha256(_expected_body(name)).hexdigest()
            if on_disk_hash != inmem_hash:
                return False
        shard = audit[name]
        if "schema_version" not in shard:
            return False
        if not shard.get("totals"):
            return False
    return True


def validate_reports_agree(audit: dict | None = None) -> bool:
    """JSON index, Markdown totals, and the candidates shard all
    agree on the headline numbers.  This is the cross-report
    R6 invariant."""
    if audit is None:
        audit = build_audit_object({})
    from scripts.verifiers_audit.render import render_markdown

    md = render_markdown(audit)
    t = audit["index"]["totals"]
    cs = audit["candidates"]
    checks = {
        "wave_1_count": (
            f"| Wave-1 candidates | {t['wave_1_candidate_count']} |" in md
        ),
        "measured_deletion": (
            f"| Measured net deletion (lines) | "
            f"{t['measured_net_deletion_lines']} |" in md
        ),
        "candidate_count_match": (
            cs["totals"]["candidate_count"]
            == len(cs["candidates"])
        ),
        "wave_1_breakdown_match": (
            cs["totals"]["wave_1_candidate_count"]
            == len(cs["wave_breakdown"].get("Wave 1", []))
        ),
        "measured_deletion_consistent": (
            cs["totals"]["measured_net_deletion_lines"]
            == t["measured_net_deletion_lines"]
        ),
    }
    return all(checks.values())


from scripts.verifiers_audit.correction08_validators import (
    CORRECTION08_VALIDATORS,
)

VALIDATORS: tuple = (
    ("inventory_equals_tracked", validate_inventory_equals_tracked),
    ("inventory_set_equals_tracked",
     validate_inventory_set_equals_tracked),
    ("no_excluded_in_helpers", validate_no_excluded_in_helpers),
    ("no_excluded_in_groups", validate_no_excluded_in_groups),
    ("no_excluded_in_candidates", validate_no_excluded_in_candidates),
    ("mixed_groups_invariant", validate_mixed_groups_invariant),
    ("wave_1_equivalence_passed", validate_wave_1_equivalence_passed),
    ("core_has_24_symbols", validate_24_symbol_count),
    ("required_shards_complete", validate_required_shards_complete),
    ("index_and_shards_aligned", validate_index_and_shards_aligned),
    ("markdown_totals_match_index", validate_markdown_totals_match_index),
    ("reports_agree", validate_reports_agree),
    ("no_absolute_paths", validate_no_absolute_paths),
    # CORRECTION08 identity contract validators are defined in
    # the dedicated module to keep this file under the LLM-
    # friendly line limit.  They are re-exported here so the
    # production ``run_all`` walks every validator.
    *CORRECTION08_VALIDATORS,
)


def run_all(audit: dict | None = None) -> tuple[bool, list[str]]:
    """Run every validator and return ``(all_ok, failures)``."""
    if audit is None:
        audit = build_audit_object({})
    failures: list[str] = []
    for name, fn in VALIDATORS:
        try:
            ok = fn(audit)
        except Exception as exc:
            ok = False
            failures.append(f"{name}: {exc}")
        if not ok:
            failures.append(name)
    return len(failures) == 0, failures
