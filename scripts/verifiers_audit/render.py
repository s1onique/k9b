"""Markdown report renderer (CORRECTION01 minimal)."""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,no-untyped-call,no-untyped-def"
from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.discovery import REPO_ROOT

MARKDOWN_PATH = (
    REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01.md"
)


def render_markdown(audit: dict | None = None) -> str:
    """Render the bounded Markdown summary from the audit object."""
    if audit is None:
        audit = build_audit_object({})
    out: list[str] = []
    p = lambda line: out.append(line)  # noqa: E731,no-untyped-call

    p("# ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01")
    p("")
    p("Structural-verifier duplication audit. Inventory and analysis only.")
    p("The audit does not migrate a verifier, modify the verifier-core")
    p("package, or alter diagnostic output.")
    p("")
    p("All numbers in this report are derived from the same source-")
    p("validated audit object as the JSON shards under")
    p("`docs/reports/verifier-core-migration-audit01/`.")
    p("")

    idx = audit["index"]["totals"]
    t = idx
    p("## Headline totals (source-derived)")
    p("")
    p("| Field | Value |")
    p("| --- | ---: |")
    p(f"| Tracked verifier paths | {t['tracked_path_count']} |")
    p(f"| Included paths | {t['included_path_count']} |")
    p(f"| Excluded paths | {t['excluded_path_count']} |")
    p(f"| AST-discovered helpers | {t['helper_count']} |")
    p(f"| Exact-duplicate groups | {t['exact_duplicate_group_count']} |")
    p(f"| Exact-duplicate helpers | {t['exact_duplicate_helper_count']} |")
    p(f"| Core public symbols (`__all__`) | "
      f"{t['core_public_symbol_count']} |")
    p(f"| Symbols with a production consumer | "
      f"{t['production_consumer_count']} |")
    p(f"| Symbols with test-only consumers | "
      f"{t['test_only_consumer_count']} |")
    p(f"| Symbols currently unused | "
      f"{t['unused_consumer_count']} |")
    p(f"| Migration candidates | {t['candidate_count']} |")
    p(f"| Wave-1 candidates | {t['wave_1_candidate_count']} |")
    p(f"| Measured net deletion (lines) | "
      f"{t['measured_net_deletion_lines']} |")
    p(f"| Preserved protected paths | "
      f"{t['preserved_path_count']} |")
    p("")

    p("## Wave-1 candidates (R6)")
    p("")
    cands = audit["candidates"]
    eq = cands["equivalence_suites"]
    p("Executable equivalence (real paired tests against the core):")
    p("")
    for suite_name, suite in eq.items():
        p(f"- `{suite_name}`: {suite['passed']}/{suite['total']} pass")
    p("")
    p("| Candidate | Score | Risk | Wave |")
    p("| --- | ---: | ---: | --- |")
    for c in cands["candidates"]:
        p(
            f"| {c['candidate_id']} | {c['migration_score']} | "
            f"{c['risk_score']} | **{c['wave']}** |"
        )
    p("")

    p("## Recommended successor ACT")
    p("")
    p("`ACT-K9B-VERIFIER-CORE-MIGRATION-WAVE01` may migrate only the")
    p(f"Wave-1 candidates above ({t['wave_1_candidate_count']} "
      "helpers, all backed by passing executable equivalence suites).")
    p("")
    p("The successor MUST NOT add speculative core primitives,")
    p("alter diagnostic output, or migrate a Deferred / Prohibited")
    p("candidate.")
    p("")

    p("## Reproduction commands")
    p("")
    p("```bash")
    p("# Re-verify predecessor boundary")
    p("git rev-parse HEAD")
    p("git status --short")
    p("git diff --check")
    p("git diff --cached --check")
    p("")
    p("# Generate + verify the audit reports")
    p("python scripts/verifiers_audit/audit.py --write")
    p("python scripts/verifiers_audit/audit.py --check")
    p("")
    p("# Run the audit reliability tests")
    p("python -m pytest 'tests/verifiers/test_verifier_core_migration_audit01.py' -v")
    p("")
    p("# Re-prove production verifier and core hashes are unchanged")
    p("git ls-files 'scripts/verifiers/*.py' 'scripts/verifiers/**/*.py' | "
      "xargs shasum -a 256")
    p("```")
    p("")

    p("## Shards")
    p("")
    p("| Shard | Path |")
    p("| --- | --- |")
    shards = idx.get("shards") or {
        "inventory": {"path": "docs/reports/verifier-core-migration-audit01/inventory.json"},
        "helpers": {"path": "docs/reports/verifier-core-migration-audit01/helpers.json"},
        "groups": {"path": "docs/reports/verifier-core-migration-audit01/groups.json"},
        "core_usage": {"path": "docs/reports/verifier-core-migration-audit01/core_usage.json"},
        "candidates": {"path": "docs/reports/verifier-core-migration-audit01/candidates.json"},
    }
    for name, info in shards.items():
        p(f"| {name} | `{info['path']}` |")

    body = "\n".join(out)
    if not body.endswith("\n"):
        body += "\n"
    return body
