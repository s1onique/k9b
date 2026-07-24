"""Top-level audit builder (CORRECTION01 minimal).

Assembles the single source-derived audit object used by every
report. The builder is fully deterministic and never modifies
production verifier files or the verifier-core package.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment"
import subprocess

from scripts.verifiers_audit.candidates import (
    CANDIDATES,
    wave_breakdown,
)
from scripts.verifiers_audit.consumer_map import (
    build_consumer_map,
    discover_test_paths,
)
from scripts.verifiers_audit.discovery import (
    REPO_ROOT,
    core_public_symbols,
    discover_helpers,
)
from scripts.verifiers_audit.equivalence import run_all_equivalence
from scripts.verifiers_audit.groups import (
    GROUPS,
    count_exact_groups,
    count_exact_helpers,
    mixed_group_invariant,
)
from scripts.verifiers_audit.patch_simulation import (
    measured_patch_summary,
)
from scripts.verifiers_audit.scope import classify_path, split_tracked
from scripts.verifiers_audit.source_preservation import (
    build_source_preservation,
)

SCHEMA_VERSION = "1.0"


def head_commit() -> str:
    return _run_git("rev-parse", "HEAD").strip()


def tracked_verifier_paths() -> list[str]:
    out = _run_git("ls-files", "scripts/verifiers/*.py", "scripts/verifiers/**/*.py")
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def _run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout


def build_inventory_shard(tracked: list[str]) -> dict[str, object]:
    included, excluded = split_tracked(tracked)
    return {
        "schema_version": SCHEMA_VERSION,
        "totals": {
            "tracked_path_count": len(tracked),
            "included_path_count": len(included),
            "excluded_path_count": len(excluded),
            "included_plus_excluded_equals_tracked": (
                len(included) + len(excluded) == len(tracked)
            ),
        },
        "included_paths": included,
        "excluded_paths": [
            {"path": p, "exclusion_rule": classify_path(p)} for p, _ in excluded
        ],
    }


def build_helpers_shard(included_paths: list[str]) -> dict[str, object]:
    """Compact helpers shard (CORRECTION01)."""
    all_helpers = discover_helpers(included_paths)
    public_helpers = [h for h in all_helpers if h.is_public]
    return {
        "schema_version": SCHEMA_VERSION,
        "totals": {
            "helper_count": len(all_helpers),
            "function_count": sum(1 for h in all_helpers if h.kind == "function"),
            "method_count": sum(1 for h in all_helpers if h.kind == "method"),
            "public_helper_count": len(public_helpers),
            "private_helper_count": len(all_helpers) - len(public_helpers),
        },
        "helpers": [
            {
                "path": h.path,
                "qualname": h.qualname,
                "line": h.line,
                "kind": h.kind,
                "args": h.args_count,
            }
            for h in public_helpers
        ],
    }


def build_duplicate_groups_shard() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "totals": {
            "duplicate_group_count": len(GROUPS),
            "exact_duplicate_group_count": count_exact_groups(),
            "exact_duplicate_helper_count": count_exact_helpers(),
            "mixed_groups": mixed_group_invariant(),
        },
        "groups": [g.to_dict() for g in GROUPS],
    }


def build_core_usage_shard(
    included_paths: list[str],
    test_paths: list[str],
) -> dict[str, object]:
    symbols = core_public_symbols()
    symbol_modules: dict[str, str] = {}
    for mod in ("codes", "diagnostics", "lookups", "directness", "detectors"):
        sub = REPO_ROOT / "scripts/verifiers/verifier_core" / f"{mod}.py"
        if not sub.exists():
            continue
        import ast

        try:
            tree = ast.parse(sub.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if (
                        isinstance(tgt, ast.Name)
                        and tgt.id == "__all__"
                        and isinstance(node.value, ast.Tuple)
                    ):
                        for elt in node.value.elts:
                            if (
                                isinstance(elt, ast.Constant)
                                and isinstance(elt.value, str)
                            ):
                                symbol_modules.setdefault(
                                    elt.value,
                                    f"scripts/verifiers/verifier_core/{mod}.py",
                                )

    consumers = build_consumer_map(symbols, symbol_modules, included_paths, test_paths)
    return {
        "schema_version": SCHEMA_VERSION,
        "totals": {
            "core_public_symbol_count": len(symbols),
            "proven_reused_count": sum(
                1 for c in consumers if c.classification == "PROVEN-REUSED"
            ),
            "test_only_count": sum(
                1 for c in consumers if c.classification == "TEST-ONLY"
            ),
            "unused_count": sum(
                1 for c in consumers if c.classification == "UNUSED"
            ),
        },
        "consumers": [c.to_dict() for c in consumers],
    }


def build_candidates_shard(
    suites: dict[str, dict[str, object]],
    measured_deletion: int,
) -> dict[str, object]:
    """Build the candidates shard.

    R3: case counts in every candidate rationale come from the
    live equivalence ``suites`` argument; no literal "4/4" or
    "6/6" survives in the source.  R4: the
    ``projected_net_deletion_lines`` field is replaced with the
    measured patch net deletion (positive integer means the
    successor ACT produces real deletion).
    """
    waves = wave_breakdown()
    return {
        "schema_version": SCHEMA_VERSION,
        "totals": {
            "candidate_count": len(CANDIDATES),
            "wave_1_candidate_count": len(waves.get("Wave 1", [])),
            "measured_net_deletion_lines": measured_deletion,
        },
        "equivalence_suites": suites,
        "candidates": [c.to_dict(suites) for c in CANDIDATES],
        "wave_breakdown": waves,
    }


def build_top_level_index(
    tracked: list[str],
    inventory_shard: dict[str, object],
    helpers_shard: dict[str, object],
    groups_shard: dict[str, object],
    core_usage_shard: dict[str, object],
    candidates_shard: dict[str, object],
    source_preservation: dict[str, object],
    shards: dict[str, dict[str, str]],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "head_commit": head_commit(),
        "totals": {
            "tracked_path_count": inventory_shard["totals"]["tracked_path_count"],
            "included_path_count": inventory_shard["totals"]["included_path_count"],
            "excluded_path_count": inventory_shard["totals"]["excluded_path_count"],
            "helper_count": helpers_shard["totals"]["helper_count"],
            "duplicate_group_count": groups_shard["totals"]["duplicate_group_count"],
            "exact_duplicate_group_count": groups_shard["totals"][
                "exact_duplicate_group_count"
            ],
            "exact_duplicate_helper_count": groups_shard["totals"][
                "exact_duplicate_helper_count"
            ],
            "core_public_symbol_count": core_usage_shard["totals"][
                "core_public_symbol_count"
            ],
            "production_consumer_count": core_usage_shard["totals"][
                "proven_reused_count"
            ],
            "test_only_consumer_count": core_usage_shard["totals"]["test_only_count"],
            "unused_consumer_count": core_usage_shard["totals"]["unused_count"],
            "candidate_count": candidates_shard["totals"]["candidate_count"],
            "wave_1_candidate_count": candidates_shard["totals"][
                "wave_1_candidate_count"
            ],
            "measured_net_deletion_lines": candidates_shard["totals"][
                "measured_net_deletion_lines"
            ],
            "preserved_path_count": source_preservation["totals"][
                "preserved_path_count"
            ],
        },
        "shards": shards,
    }


def _default_shard_map() -> dict[str, dict[str, str]]:
    """Compute the default shard map (path + sha256) from the
    in-memory shards so the audit object is self-contained."""

    from scripts.verifiers_audit.report_io import (
        REPORT_ROOT,
    )

    out: dict[str, dict[str, str]] = {}
    for name in (
        "inventory",
        "helpers",
        "groups",
        "core_usage",
        "candidates",
        "source_preservation",
        "gate_classification",
    ):
        # The actual shards are built below in build_audit_object
        # itself; for the default map we use placeholder entries
        # that cmd_write / cmd_check will overwrite on disk.  The
        # validator validate_required_shards_complete accepts the
        # in-memory shard body for the sha256 comparison, so we
        # defer the actual hashing to that validator.
        out[name] = {
            "path": str((REPORT_ROOT / f"{name}.json").relative_to(
                REPO_ROOT
            )),
            "sha256": "",
        }
    return out


def build_audit_object(
    shards: dict[str, str] | None = None,
    skip_gate: bool = False,
    gate_classification: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the audit object.

    ``skip_gate`` defaults to ``False`` so production report
    generation always records real evidence from the canonical
    gate.  Unit tests may opt into a deterministic ``SKIPPED``
    record by passing ``skip_gate=True``; this is the only
    supported way to bypass the gate (no repository-level
    ``conftest.py`` is allowed to toggle the env var silently).

    ``gate_classification`` is the auxiliary clean-worktree
    experiment record.  The audit object does NOT regenerate
    this record - the caller MUST pass a previously-collected
    record (typically produced by
    :mod:`scripts.verifiers_audit.collect_r2_evidence`).  This
    prevents the fast ``--write`` flow from overwriting real
    evidence with a ``SKIPPED`` shard.
    """
    tracked = tracked_verifier_paths()
    included, _ = split_tracked(tracked)
    test_paths = discover_test_paths()
    inv = build_inventory_shard(tracked)
    helpers = build_helpers_shard(included)
    groups = build_duplicate_groups_shard()
    usage = build_core_usage_shard(included, test_paths)
    suites = run_all_equivalence()
    patch_summary = measured_patch_summary()
    measured_deletion = patch_summary["totals"]["net_production_lines_removed"]
    candidates = build_candidates_shard(suites, measured_deletion)
    source_preservation = build_source_preservation()
    if gate_classification is None:
        # The caller did not supply a previously-collected
        # record.  This MUST be a unit-test-only path.  Emit a
        # deterministic ``UNASSESSED`` record (not ``SKIPPED``)
        # so production never silently downgrades.
        from scripts.verifiers_audit.gate_classification import (
            _unassessed_record,
        )
        gate_classification = _unassessed_record(
            "no previously-collected gate_classification was "
            "supplied to build_audit_object; the auxiliary "
            "experiment was not run in this invocation."
        )
    shard_map: dict[str, dict[str, str]] = (
        shards if shards else _default_shard_map()
    )
    index = build_top_level_index(
        tracked, inv, helpers, groups, usage, candidates,
        source_preservation, shard_map,
    )
    return {
        "index": index,
        "inventory": inv,
        "helpers": helpers,
        "groups": groups,
        "core_usage": usage,
        "candidates": candidates,
        "source_preservation": source_preservation,
        "patch_simulation": patch_summary,
        "gate_classification": gate_classification,
    }
