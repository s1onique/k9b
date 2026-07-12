# Targeted digest

Generated at: 2026-07-12T20:33:00Z
Repo: /Users/chistyakov/Projects/SPbNIX/k9b
Mode: staged

## Manifest
files_changed=39
added_files=26
modified_files=13
renamed_files=0
deleted_files=0

M	docs/reports/impact-scan-ledger.md
A	scripts/verifiers/automatic_diagnosis_authority_seam01.py
A	scripts/verifiers/automatic_diagnosis_authority_seam01_checks.py
A	scripts/verifiers/automatic_diagnosis_authority_seam01_helpers.py
M	src/k8s_diag_agent/collect/incident_automatic_diagnosis_loop_artifacts.py
A	src/k8s_diag_agent/collect/incident_diagnosis_authority_run_summary.py
A	src/k8s_diag_agent/collect/incident_diagnosis_authority_seam.py
A	src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_backend.py
A	src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_local.py
A	src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_types.py
M	src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_config.py
M	src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_evidence_processor.py
M	src/k8s_diag_agent/collect/incident_lifecycle.py
M	src/k8s_diag_agent/collect/incident_lifecycle_serialization.py
M	src/k8s_diag_agent/collect/incident_snapshot_helpers.py
M	src/k8s_diag_agent/collect/incident_store_sqlite_context.py
M	src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle.py
A	src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle_idempotency.py
M	src/k8s_diag_agent/collect/incident_store_sqlite_migrations.py
M	src/k8s_diag_agent/collect/incident_store_sqlite_schema.py
A	src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_handler.py
A	src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_idempotency.py
M	src/k8s_diag_agent/ui/server_routes.py
A	tests/unit/authority_seam_support.py
A	tests/unit/test_automatic_diagnosis_authority_seam01.py
A	tests/unit/test_automatic_diagnosis_authority_seam01_dispatch.py
A	tests/unit/test_automatic_diagnosis_authority_seam01_endpoint.py
A	tests/unit/test_automatic_diagnosis_authority_seam01_processor.py
A	tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py
M	tests/unit/test_automatic_diagnosis_backend_promotion_regression.py
A	tests/unit/test_incident_diagnosis_authority_run_summary.py
A	tests/unit/test_incident_snapshot_serialization_isolation.py
A	tests/unit/test_incident_store_sqlite_lifecycle_idempotency.py
A	tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3.py
A	tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_apply.py
A	tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_events.py
A	tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py
A	tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4.py
A	tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4_concurrency.py

## Changed files
docs/reports/impact-scan-ledger.md  [tracked, staged present: yes, unstaged present: no]
scripts/verifiers/automatic_diagnosis_authority_seam01.py  [tracked, staged present: yes, unstaged present: no]
scripts/verifiers/automatic_diagnosis_authority_seam01_checks.py  [tracked, staged present: yes, unstaged present: no]
scripts/verifiers/automatic_diagnosis_authority_seam01_helpers.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_automatic_diagnosis_loop_artifacts.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_diagnosis_authority_run_summary.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_diagnosis_authority_seam.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_backend.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_local.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_types.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_config.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_evidence_processor.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_lifecycle.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_lifecycle_serialization.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_snapshot_helpers.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_store_sqlite_context.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle_idempotency.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_store_sqlite_migrations.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/collect/incident_store_sqlite_schema.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_handler.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_idempotency.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/ui/server_routes.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/authority_seam_support.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_automatic_diagnosis_authority_seam01.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_automatic_diagnosis_authority_seam01_dispatch.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_automatic_diagnosis_authority_seam01_endpoint.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_automatic_diagnosis_authority_seam01_processor.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_automatic_diagnosis_backend_promotion_regression.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_diagnosis_authority_run_summary.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_snapshot_serialization_isolation.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_store_sqlite_lifecycle_idempotency.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_apply.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_events.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4.py  [tracked, staged present: yes, unstaged present: no]
tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4_concurrency.py  [tracked, staged present: yes, unstaged present: no]

## Diff stat
 docs/reports/impact-scan-ledger.md                 |  57 +++
 .../automatic_diagnosis_authority_seam01.py        | 173 ++++++++
 .../automatic_diagnosis_authority_seam01_checks.py | 482 +++++++++++++++++++++
 ...automatic_diagnosis_authority_seam01_helpers.py | 202 +++++++++
 .../incident_automatic_diagnosis_loop_artifacts.py |   4 +
 .../incident_diagnosis_authority_run_summary.py    | 125 ++++++
 .../collect/incident_diagnosis_authority_seam.py   | 397 +++++++++++++++++
 .../incident_diagnosis_authority_seam_backend.py   | 251 +++++++++++
 .../incident_diagnosis_authority_seam_local.py     | 108 +++++
 .../incident_diagnosis_authority_seam_types.py     | 137 ++++++
 .../collect/incident_diagnosis_auto_loop_config.py | 169 +++++---
 ...ident_diagnosis_auto_loop_evidence_processor.py | 296 +++++++++++--
 src/k8s_diag_agent/collect/incident_lifecycle.py   |  10 +
 .../collect/incident_lifecycle_serialization.py    |  18 +
 .../collect/incident_snapshot_helpers.py           |  19 +-
 .../collect/incident_store_sqlite_context.py       | 366 +++++++++++++++-
 .../collect/incident_store_sqlite_lifecycle.py     |  39 +-
 .../incident_store_sqlite_lifecycle_idempotency.py | 103 +++++
 .../collect/incident_store_sqlite_migrations.py    |  24 +-
 .../collect/incident_store_sqlite_schema.py        |  61 ++-
 .../server_incident_diagnosis_lifecycle_handler.py | 280 ++++++++++++
 ...ver_incident_diagnosis_lifecycle_idempotency.py | 335 ++++++++++++++
 src/k8s_diag_agent/ui/server_routes.py             |  10 +
 tests/unit/authority_seam_support.py               | 243 +++++++++++
 .../test_automatic_diagnosis_authority_seam01.py   | 384 ++++++++++++++++
 ...utomatic_diagnosis_authority_seam01_dispatch.py | 327 ++++++++++++++
 ...utomatic_diagnosis_authority_seam01_endpoint.py | 262 +++++++++++
 ...tomatic_diagnosis_authority_seam01_processor.py | 391 +++++++++++++++++
 ...utomatic_diagnosis_authority_seam01_verifier.py | 272 ++++++++++++
 ...matic_diagnosis_backend_promotion_regression.py |  10 +-
 ...est_incident_diagnosis_authority_run_summary.py | 156 +++++++
 ...st_incident_snapshot_serialization_isolation.py | 316 ++++++++++++++
 ..._incident_store_sqlite_lifecycle_idempotency.py | 458 ++++++++++++++++++++
 ...cident_store_sqlite_lifecycle_idempotency_r3.py | 356 +++++++++++++++
 ..._store_sqlite_lifecycle_idempotency_r3_apply.py | 263 +++++++++++
 ...store_sqlite_lifecycle_idempotency_r3_events.py | 165 +++++++
 ...t_store_sqlite_lifecycle_idempotency_r3_seam.py | 176 ++++++++
 ...cident_store_sqlite_lifecycle_idempotency_r4.py | 280 ++++++++++++
 ..._sqlite_lifecycle_idempotency_r4_concurrency.py | 270 ++++++++++++
 39 files changed, 7888 insertions(+), 107 deletions(-)

## Diffs

=== docs/reports/impact-scan-ledger.md ===
diff --git a/docs/reports/impact-scan-ledger.md b/docs/reports/impact-scan-ledger.md
index 103b7f11..2058d70c 100644
--- a/docs/reports/impact-scan-ledger.md
+++ b/docs/reports/impact-scan-ledger.md
@@ -60,6 +60,62 @@ If the ledger shows the scan is mostly cargo cult, noisy, or not reducing surpri

 ## Entries

+### 2026-07-12 — ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 R4 close
+
+- Target: SQLite lifecycle idempotency — close R4-1, R4-2, R4-3, R4-4 blockers from the R3 review (cache authority defect, missing multi-process regressions, replay cache healing, typed `diagnosis_loop` projection boundary).
+- Impact scan required: yes
+- Impact scan present: yes
+- Script used: no (manual `git grep` + review-trace against the R4 findings)
+- Manual refinement present: yes
+- Planned files: 5 source (`incident_lifecycle.py`, `incident_lifecycle_serialization.py`, `incident_snapshot_helpers.py`, `incident_store_sqlite_context.py`, `incident_store_sqlite_lifecycle.py`), 2 new R4 test files split for size.
+- Changed files: 5 source, 2 new R4 test files (split to keep each under the 500-line LLM-friendly threshold).
+- Unexpected changed files: none beyond the planned set.
+- Likely tests identified by script: n/a (manual review).
+- Likely tests identified manually: existing `test_incident_store_sqlite_lifecycle_idempotency*.py` (R3 + base), canonical seam (`test_incident_store_sqlite_*`), `test_incident_diagnosis_authority_run_summary.py`, `test_automatic_diagnosis_backend_promotion_regression.py`.
+- Targeted tests run: focused pytest on the R3 + R4 + base lifecycle idempotency test files (28 tests); broader SQLite + automatic-diagnosis capability-seam suites (132 tests).
+- Full gate run: `./scripts/verify_all.sh --act-local` → PASS.
+- Reviewer scope objection: no (this ACT is the explicit R4 follow-up).
+- Reviewer requested missing scan: no.
+- Script usefulness: n/a.
+- Did the scan reduce surprise: yes — the R4 review named exactly four blockers; each was mapped to one production fix and one regression test.
+- Notes:
+  - **R4-1 (cache authority is the projection, not the cache)**: `SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently` now proves incident existence with a `SELECT 1 FROM incident_current WHERE incident_id = ?` inside the same `BEGIN IMMEDIATE` transaction. The process-local `self._cache` is no longer authoritative for the existence check, so a pre-opened store whose cache was loaded before another process promoted the incident correctly applies the lifecycle instead of returning `incident_not_found`.
+  - **R4-2a (pre-opened store regression)**: New `TestR4CacheAuthorityIsProjectionNotCache::test_lifecycle_apply_on_pre_opened_store_with_empty_cache` opens process B before process A promotes, runs the lifecycle through B, and asserts durable event/projection/idempotency state.
+  - **R4-2b (overlapping concurrent stores)**: New `TestR4OverlappingConcurrentStores::test_two_stores_contend_concurrently_for_lifecycle_apply` holds both stores open in two threads, joins both into a 3-party barrier (workers + main) and an explicit `go` event, then verifies exactly one thread applies and the other replays under contention. The R3 multi-process test only exercised sequential stores, so this is a genuinely new regression class.
+  - **R4-3 (replay refreshes the stale cache)**: Idempotent replay now calls `self._refresh_cache_from_projection(incident_id)` after the `BEGIN IMMEDIATE` commit so the cache observed by the replay handler reflects the durable projection row, not the stale pre-apply view. `TestR4ReplayRefreshesStaleCache::test_replay_on_pre_opened_store_heals_cache` proves the cache is populated and `store.get_incident()` returns the typed `diagnosis_loop` state on the replaying process.
+  - **R4-4 (typed `diagnosis_loop` projection boundary)**: `Incident.diagnosis_loop: dict[str, Any] | None` is now a typed dataclass field. The serializer (`incident_to_dict`/`incident_from_dict`) and the snapshot helper (`incident_snapshot_helpers.snapshot_incident`) round-trip it. `TestR4TypedDiagnosisLoopField::test_apply_hydrates_typed_diagnosis_loop_on_cached_incident` proves the field is populated on the returned Incident, the cached Incident, and the detail-endpoint read. The in-process `mark_diagnosis_loop_*_impl` methods also refresh the cache from the projection after `append_event` so they expose the typed state on the returned Incident.
+  - **R4-5 (staged tree)**: `git add -A && git diff --cached --check && git status --short` shows zero untracked files and zero unstaged ACT files. The 38-file diffstat is consistent with the R3 + R4 review scope; the four R3 test files plus the new R4 files plus all production sources plus all related support modules are staged.
+  - **Test file split**: 28 R3+R4 tests split across the existing R3 split files plus two new R4 files (`r4.py` core + `r4_concurrency.py` companion) to comply with the 500-line LLM-friendly threshold.
+  - **ACT-local fresh evidence**: gate ran after all changes were staged; output timestamp in the next digest will represent this tree.
+
+### 2026-07-12 — ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 R3 close
+
+- Target: SQLite lifecycle idempotency — close R3-1, R3-2, R3-3, R3-4, R3-5, R3-6 blockers from the R2 review.
+- Impact scan required: yes
+- Impact scan present: yes
+- Script used: no (manual `git grep` + `rg` against review findings)
+- Manual refinement present: yes
+- Planned files: 4 source (`incident_store_sqlite_schema.py`, `incident_store_sqlite_migrations.py`, `incident_store_sqlite_context.py`, `incident_store_sqlite_lifecycle_idempotency.py`), 1 driver test (`test_automatic_diagnosis_backend_promotion_regression.py`), 4 R3 test files.
+- Changed files: 6 source/test files (one R2 docstring-only side-effect), 1 unrelated pre-existing R2 test fix, 4 new R3 test files split for size.
+- Unexpected changed files: `tests/unit/test_automatic_diagnosis_backend_promotion_regression.py` — the R2 patch removed `check_incident_eligibility` from the processor module and replaced it with `evaluate_incident_eligibility` in `incident_diagnosis_authority_seam`, but the test still patched the old symbol. Confirmed pre-existing R2 regression by reverting R3 changes and re-running.
+- Likely tests identified by script: n/a (manual review).
+- Likely tests identified manually: existing `test_incident_store_sqlite_lifecycle_idempotency.py`, canonical seam (`test_incident_store_sqlite_*`), auto-diagnosis dispatch regression.
+- Targeted tests run: focused pytest on the R3 lifecycle idempotency test files (23 tests); broader SQLite + automatic_diagnosis suites (679 tests).
+- Full gate run: `./scripts/verify_all.sh --act-local` → PASS.
+- Reviewer scope objection: no.
+- Reviewer requested missing scan: no.
+- Script usefulness: n/a.
+- Did the scan reduce surprise: yes — review listed 10 required R3 tests and 6 specific blockers; both informed the implementation plan.
+- Notes:
+  - **Schema upgrade (R3-1)**: Bumped `SCHEMA_VERSION` 1 → 2 and added a v2 migration entry that re-applies the lifecycle idempotency table + the COALESCE-based UNIQUE index. v1 databases upgrade in place (covered by `test_v1_database_upgrades_to_v2_with_table_and_index`).
+  - **Capability seam (R3-4)**: Replaced the R2 module's direct `_write_lock`/`_connect()`/`_incidents`/`_snapshot_incident()` access with a thin adapter that delegates to the new canonical `SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently` method. The new method owns the full lookup → hash-chained event append → canonical projection → idempotency record sequence in one `BEGIN IMMEDIATE` transaction and refreshes the in-memory cache from the projection on commit.
+  - **Hash chain (R3-3)**: The R2 patch wrote empty `payload_sha256` / `previous_event_sha256` / `event_sha256` placeholders; the new canonical path uses `EventBuilder` so the appended event is a real hash-chained link that subsequent canonical events connect to.
+  - **NULL uniqueness (R3-5)**: Index now uses `COALESCE(diagnosis_run_id, '')` so NULL participates in uniqueness; lookups mirror the expression.
+  - **Rollback proof (R3-6)**: Idempotency insert is a separate module-level helper so tests can monkey-patch it to inject a fault and verify the event row, projection row, and cache all roll back together.
+  - **Test file split**: 14 R3 tests split across 4 files to comply with the 500-line LLM-friendly threshold; companion references are documented in each file's docstring.
+
+---
+
 ### 2026-06-05 — Planner data derivation extraction

 - **Change:** Extracted planner data derivation from `App.tsx` into `frontend/src/app/usePlannerDataProps.ts`.
@@ -178,4 +234,5 @@ If the ledger shows the scan is mostly cargo cult, noisy, or not reducing surpri

 ---

+
 *Add new entries at the top, below this separator.*

=== scripts/verifiers/automatic_diagnosis_authority_seam01.py ===
diff --git a/scripts/verifiers/automatic_diagnosis_authority_seam01.py b/scripts/verifiers/automatic_diagnosis_authority_seam01.py
new file mode 100644
index 00000000..783a7809
--- /dev/null
+++ b/scripts/verifiers/automatic_diagnosis_authority_seam01.py
@@ -0,0 +1,173 @@
+#!/usr/bin/env python
+"""Static verifier for ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.
+
+Enforces the contract that the automatic-diagnosis processor:
+
+1. Does NOT call ``check_incident_eligibility(incident_id=...)`` after it
+   has received a typed :class:`Incident` from
+   :class:`BackendIncidentFound`.
+2. Does NOT call ``get_incident_store()`` to re-resolve the incident
+   or to mutate lifecycle state.
+3. Does NOT call the local ``IncidentStore.mark_diagnosis_loop_*``
+   methods directly; all lifecycle writes must route through
+   :func:`record_diagnosis_loop_*`.
+4. Does NOT call the legacy nullable ``fetch_incident_for_diagnosis``.
+5. Handles the backend lookup through exhaustive
+   ``match`` on the three typed variants; never through truthiness or
+   ``None`` checks.
+6. Maps ``BackendIncidentLookupFailed`` to a bounded
+   ``backend_incident_*`` reason code, never to ``incident_not_found``.
+7. Does NOT introduce backend-to-local fallback when the backend
+   operation fails.
+8. Does NOT swallow lifecycle dispatch failures with an empty
+   ``except`` / ``pass`` block.
+
+And the aggregate-based eligibility evaluator:
+
+1. Accepts a typed ``incident: Incident`` parameter.
+2. Does NOT call ``get_incident_store()``.
+3. Does NOT call any incident backend client.
+4. Does NOT accept ``incident_id`` as its only incident input.
+
+To keep this entry-point module under the LLM-friendly 500-line limit,
+the implementation is split into two sibling modules:
+
+* :mod:`scripts.verifiers.automatic_diagnosis_authority_seam01_helpers` —
+  file-collection and AST helpers, plus the two reusable forbidden-pattern
+  detectors.
+* :mod:`scripts.verifiers.automatic_diagnosis_authority_seam01_checks` —
+  every per-claim ``check_*`` function and the seam-module symbol
+  collector.
+
+For backward compatibility with the existing self-test
+(``tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py``)
+the underscored helper and detector names that the self-test accesses
+via ``verifier._check_*`` / ``verifier._contains_*`` /
+``verifier._seam_available_names`` are re-exported below as module
+attributes.
+
+Run directly:
+
+    .venv/bin/python scripts/verifiers/automatic_diagnosis_authority_seam01.py
+
+Exit code 0 = PASS, non-zero = violations present.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+# isort: skip_file
+
+from __future__ import annotations
+
+import sys
+from pathlib import Path
+
+# The verifier is invoked both as a script (``python scripts/verifiers/
+# automatic_diagnosis_authority_seam01.py``) and via ``importlib.util
+# .spec_from_file_location`` from the self-test. Neither sets up a
+# parent package, so relative imports (``from . import ...``) fail.
+# Add the verifier directory to ``sys.path`` so the sibling modules
+# can be imported by absolute name. Idempotent: re-running the
+# verifier (e.g. from the self-test) does not duplicate the entry.
+_VERIFIER_DIR = str(Path(__file__).resolve().parent)
+if _VERIFIER_DIR not in sys.path:
+    sys.path.insert(0, _VERIFIER_DIR)
+
+# ruff: noqa: E402,F401
+# Re-export every helper / check under its legacy underscored name so
+# the self-test can access them via ``verifier._check_*`` /
+# ``verifier._contains_*`` / ``verifier._seam_available_names``.
+from automatic_diagnosis_authority_seam01_helpers import (  # noqa: F401
+    PROCESSOR_PATH,
+    contains_truthiness_to_not_found,
+    function_defs,
+    has_empty_except_pass,
+    parse_path,
+    read_text,
+)
+from automatic_diagnosis_authority_seam01_checks import (  # noqa: F401
+    check_evaluator_aggregate_signature,
+    check_evaluator_no_lookups,
+    check_processor_calls,
+    check_processor_dispatch,
+    check_processor_lookup_failed_not_incident_not_found,
+    check_processor_no_backend_to_local_fallback,
+    check_processor_no_swallowed_lifecycle,
+    check_processor_old_id_resolver,
+    check_processor_truthiness,
+    check_processor_uses_aggregate_eligibility,
+    check_seam_required_symbols,
+    seam_available_names,
+)
+
+# Backward-compat underscored aliases used by the self-test. They live
+# as plain module-attribute assignments so ruff's auto-fix cannot drop
+# them on a subsequent run.
+_contains_truthiness_to_not_found = contains_truthiness_to_not_found
+_function_defs = function_defs
+_has_empty_except_pass = has_empty_except_pass
+_parse = parse_path
+_read = read_text
+_check_processor_calls = check_processor_calls
+_check_processor_dispatch = check_processor_dispatch
+_check_processor_lookup_failed_not_incident_not_found = (
+    check_processor_lookup_failed_not_incident_not_found
+)
+_check_processor_no_backend_to_local_fallback = (
+    check_processor_no_backend_to_local_fallback
+)
+_check_processor_no_swallowed_lifecycle = check_processor_no_swallowed_lifecycle
+_check_processor_old_id_resolver = check_processor_old_id_resolver
+_check_processor_truthiness = check_processor_truthiness
+_check_processor_uses_aggregate_eligibility = (
+    check_processor_uses_aggregate_eligibility
+)
+_seam_available_names = seam_available_names
+
+
+def run_static_checks() -> list[str]:
+    """Run all ACT-specific static checks against the production code."""
+    violations: list[str] = []
+
+    processor_tree = parse_path(PROCESSOR_PATH)
+    if processor_tree is None:
+        violations.append(
+            "incident_diagnosis_auto_loop_evidence_processor.py: cannot read or parse"
+        )
+    else:
+        violations.extend(_check_processor_calls(processor_tree))
+        violations.extend(_check_processor_old_id_resolver(processor_tree))
+        violations.extend(_check_processor_uses_aggregate_eligibility(processor_tree))
+        violations.extend(_check_processor_dispatch(processor_tree))
+
+        violations.extend(_check_processor_no_backend_to_local_fallback(processor_tree))
+        violations.extend(_check_processor_no_swallowed_lifecycle(processor_tree))
+        violations.extend(_check_processor_truthiness())
+        violations.extend(_check_processor_lookup_failed_not_incident_not_found())
+
+    violations.extend(check_evaluator_aggregate_signature())
+    violations.extend(check_evaluator_no_lookups())
+    violations.extend(check_seam_required_symbols())
+
+    return violations
+
+
+def main(argv: list[str] | None = None) -> int:
+    """CLI entry point."""
+    violations = run_static_checks()
+    if violations:
+        print(
+            "ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 verifier "
+            "found violations:"
+        )
+        for v in violations:
+            print(f"- {v}")
+        return 1
+    print(
+        "ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 verifier: PASS"
+    )
+    return 0
+
+
+if __name__ == "__main__":
+    sys.exit(main(sys.argv[1:]))

=== scripts/verifiers/automatic_diagnosis_authority_seam01_checks.py ===
diff --git a/scripts/verifiers/automatic_diagnosis_authority_seam01_checks.py b/scripts/verifiers/automatic_diagnosis_authority_seam01_checks.py
new file mode 100644
index 00000000..53d8b003
--- /dev/null
+++ b/scripts/verifiers/automatic_diagnosis_authority_seam01_checks.py
@@ -0,0 +1,482 @@
+"""Per-check functions for the ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+verifier.
+
+Every function in this module takes a parsed :class:`ast.Module` (or,
+for the seam-check, reads its own file) and returns a list of
+human-readable violation strings. An empty list means the check
+passed. The verifier entry point
+(:mod:`scripts.verifiers.automatic_diagnosis_authority_seam01`)
+orchestrates the checks via :func:`run_static_checks` (which lives in
+the entry-point module so this file stays a flat collection of
+checks).
+
+Each tree-based check has a paired negative / positive fixture in
+``tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py``
+so the verifier is provably non-trivial rather than a green stamp.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+from __future__ import annotations
+
+import ast
+from typing import Final
+
+from automatic_diagnosis_authority_seam01_helpers import (  # noqa: F401
+    EVALUATOR_PATH,
+    PROCESSOR_PATH,
+    SEAM_PATH,
+    call_keyword,
+    called_names,
+    contains_truthiness_to_not_found,
+    function_defs,
+    has_empty_except_pass,
+    match_case_type,
+    parse_path,
+    read_text,
+)
+
+# Forbidden call names that the processor must not invoke. The presence
+# of these names inside ``_process_incident`` is a contract violation.
+FORBIDDEN_PROCESSOR_CALLS: Final[tuple[str, ...]] = (
+    "get_incident_store",
+    "fetch_incident_for_diagnosis",
+)
+
+
+# Forbidden call names that the aggregate evaluator must not invoke.
+FORBIDDEN_EVALUATOR_CALLS: Final[tuple[str, ...]] = (
+    "get_incident_store",
+    "fetch_backend_incident_for_diagnosis_typed",
+    "fetch_incident_for_diagnosis",
+)
+
+
+# Lifecycle mutation methods that the processor must NOT call directly.
+# All such writes must route through ``record_diagnosis_loop_*`` helpers.
+DIRECT_LIFECYCLE_METHODS: Final[tuple[str, ...]] = (
+    "mark_diagnosis_loop_started",
+    "mark_diagnosis_loop_failed",
+    "mark_diagnosis_loop_completed",
+)
+
+
+# Symbol names whose definition must remain in the canonical seam.
+REQUIRED_SEAM_SYMBOLS: Final[tuple[str, ...]] = (
+    "evaluate_incident_eligibility",
+    "check_incident_eligibility",
+    "record_diagnosis_loop_started",
+    "record_diagnosis_loop_failed",
+    "record_diagnosis_loop_completed",
+)
+
+
+# Variants the processor must dispatch on exhaustively.
+TYPED_LOOKUP_VARIANTS: Final[tuple[str, ...]] = (
+    "BackendIncidentFound",
+    "BackendIncidentNotFound",
+    "BackendIncidentLookupFailed",
+)
+
+
+# ---------------------------------------------------------------------------
+# Processor checks
+# ---------------------------------------------------------------------------
+
+
+def check_processor_calls(tree: ast.Module) -> list[str]:
+    """Reject any direct call to forbidden functions inside the processor."""
+    violations: list[str] = []
+    processor = function_defs(tree)
+    process_incident = processor.get("_process_incident")
+    if process_incident is None:
+        violations.append(
+            "incident_diagnosis_auto_loop_evidence_processor: "
+            "_process_incident function is missing"
+        )
+        return violations
+    for node in ast.walk(process_incident):
+        if not isinstance(node, ast.Call):
+            continue
+        names = called_names(node)
+        if not names:
+            continue
+        for forbidden in FORBIDDEN_PROCESSOR_CALLS:
+            if forbidden in names:
+                violations.append(
+                    "incident_diagnosis_auto_loop_evidence_processor: "
+                    f"_process_incident forbids call to {forbidden!r}"
+                )
+        for method in DIRECT_LIFECYCLE_METHODS:
+            if method in names:
+                violations.append(
+                    "incident_diagnosis_auto_loop_evidence_processor: "
+                    f"_process_incident forbids direct lifecycle call to {method!r}"
+                )
+    return violations
+
+
+def check_processor_old_id_resolver(tree: ast.Module) -> list[str]:
+    """Reject ``check_incident_eligibility(incident_id=...)`` in the processor.
+
+    The processor MUST use :func:`evaluate_incident_eligibility`
+    directly with the typed aggregate. The legacy ID-resolving
+    ``check_incident_eligibility`` is the local-store compat wrapper.
+    """
+    violations: list[str] = []
+    processor = function_defs(tree)
+    process_incident = processor.get("_process_incident")
+    if process_incident is None:
+        return violations
+    for node in ast.walk(process_incident):
+        if not isinstance(node, ast.Call):
+            continue
+        names = called_names(node)
+        if not names:
+            continue
+        if "check_incident_eligibility" in names:
+            incident_id_value = call_keyword(node, "incident_id")
+            if incident_id_value is not None:
+                violations.append(
+                    "incident_diagnosis_auto_loop_evidence_processor: "
+                    "_process_incident calls check_incident_eligibility with "
+                    "incident_id=…; it must call evaluate_incident_eligibility "
+                    "with the typed Incident aggregate instead."
+                )
+    return violations
+
+
+def check_processor_dispatch(tree: ast.Module) -> list[str]:
+    """Confirm the processor dispatches on all three typed variants."""
+    violations: list[str] = []
+    processor = function_defs(tree)
+    process_incident = processor.get("_process_incident")
+    if process_incident is None:
+        return violations
+    found_variants: set[str] = set()
+    case_type = match_case_type()
+    if case_type is None:  # pragma: no cover - defensive
+        return violations
+    for node in ast.walk(process_incident):
+        if not isinstance(node, case_type):
+            continue
+        pat = node.pattern
+        if isinstance(pat, ast.MatchClass):
+            if pat.cls is not None and isinstance(pat.cls, ast.Name):
+                if pat.cls.id in TYPED_LOOKUP_VARIANTS:
+                    found_variants.add(pat.cls.id)
+    missing = [v for v in TYPED_LOOKUP_VARIANTS if v not in found_variants]
+    if missing:
+        violations.append(
+            "incident_diagnosis_auto_loop_evidence_processor: "
+            "_process_incident must dispatch on all three typed variants; "
+            f"missing: {missing}"
+        )
+    return violations
+
+
+def check_processor_no_backend_to_local_fallback(tree: ast.Module) -> list[str]:
+    """Reject hidden backend-to-local fallback patterns.
+
+    The processor must not call the local ``IncidentStore`` methods
+    (already covered by FORBIDDEN_PROCESSOR_CALLS / DIRECT_LIFECYCLE_METHODS)
+    and must not call the local ``fetch_incident_local`` symbol either.
+    """
+    violations: list[str] = []
+    processor = function_defs(tree)
+    process_incident = processor.get("_process_incident")
+    if process_incident is None:
+        return violations
+    for node in ast.walk(process_incident):
+        if not isinstance(node, ast.Call):
+            continue
+        names = called_names(node)
+        if "fetch_incident_local" in names:
+            violations.append(
+                "incident_diagnosis_auto_loop_evidence_processor: "
+                "_process_incident must not fall back to fetch_incident_local"
+            )
+    return violations
+
+
+def check_processor_no_swallowed_lifecycle(tree: ast.Module) -> list[str]:
+    """Reject ``except: pass`` blocks around lifecycle-dispatch calls.
+
+    A bare ``except: pass`` that swallows a lifecycle-dispatch call
+    would silently treat persistence failures as success. The
+    contract only forbids this pattern when the swallowed body
+    contains a call to ``record_diagnosis_loop_*``; best-effort
+    review-packet writes that use ``except: pass`` for non-lifecycle
+    operations are out of scope and remain allowed.
+    """
+    processor = function_defs(tree)
+    process_incident = processor.get("_process_incident")
+    if process_incident is None:
+        return []
+    violations: list[str] = []
+    for node in ast.walk(process_incident):
+        if not isinstance(node, ast.Try):
+            continue
+        for handler in node.handlers:
+            if not (len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)):
+                continue
+            # Bare pass handler; the ACT forbids this around
+            # lifecycle-dispatch calls.
+            for sub in ast.walk(node):  # walk the WHOLE try, not just the handler
+                if not isinstance(sub, ast.Call):
+                    continue
+                names = called_names(sub)
+                if any(name in names for name in ("record_diagnosis_loop_started",
+                                                  "record_diagnosis_loop_failed",
+                                                  "record_diagnosis_loop_completed")):
+                    violations.append(
+                        "incident_diagnosis_auto_loop_evidence_processor: "
+                        "forbidden ``except ...: pass`` swallowing a lifecycle-dispatch call"
+                    )
+                    break
+    return violations
+
+
+def check_processor_truthiness() -> list[str]:
+    """Reject truthiness-to-``incident_not_found`` mutations."""
+    source = read_text(PROCESSOR_PATH)
+    if source is None:
+        return []
+    try:
+        tree = ast.parse(source, filename=str(PROCESSOR_PATH))
+    except SyntaxError:
+        return []
+    if contains_truthiness_to_not_found(tree):
+        return [
+            "incident_diagnosis_auto_loop_evidence_processor: "
+            "forbidden truthiness-to-incident_not_found mutation"
+        ]
+    return []
+
+
+def check_processor_lookup_failed_not_incident_not_found() -> list[str]:
+    """Reject ``BackendIncidentLookupFailed`` mapped to ``incident_not_found``.
+
+    The processor routes ``BackendIncidentLookupFailed`` through
+    ``_failure_result_from_outcome`` which uses the bounded reason
+    code mapping. A direct mapping to ``incident_not_found`` would
+    violate INV-03.
+    """
+    source = read_text(PROCESSOR_PATH)
+    if source is None:
+        return []
+    try:
+        tree = ast.parse(source, filename=str(PROCESSOR_PATH))
+    except SyntaxError:
+        return []
+    violations: list[str] = []
+    for node in ast.walk(tree):
+        if not isinstance(node, ast.Assign):
+            continue
+        if not isinstance(node.value, ast.Constant):
+            continue
+        if node.value.value != "incident_not_found":
+            continue
+        if not isinstance(node.targets[0], ast.Name):
+            continue
+        target_name = node.targets[0].id
+        if target_name in {"eligibility_reason"}:
+            # Only allowed in the not-found branch; we cannot walk parents,
+            # so we accept the broader invariant: the file MUST NOT assign
+            # ``eligibility_reason = "incident_not_found"`` outside a
+            # BackendIncidentNotFound match case. We approximate by
+            # disallowing it whenever the file has a BackendIncidentLookupFailed
+            # dispatch (the failure path uses the bounded code mapping).
+            violations.append(
+                "incident_diagnosis_auto_loop_evidence_processor: "
+                "forbidden mapping of failure path to ``incident_not_found``"
+            )
+    # Constructor keyword-argument form: the failure path must never be
+    # projected as ``AutoLoopIncidentResult(eligibility_reason=
+    # "incident_not_found")``. ``ast.Assign`` scanning alone misses this
+    # because the value appears as a call keyword, not an assignment.
+    for node in ast.walk(tree):
+        if not isinstance(node, ast.Call):
+            continue
+        for kw in node.keywords:
+            if (
+                kw.arg == "eligibility_reason"
+                and isinstance(kw.value, ast.Constant)
+                and kw.value.value == "incident_not_found"
+            ):
+                violations.append(
+                    "incident_diagnosis_auto_loop_evidence_processor: "
+                    "forbidden AutoLoopIncidentResult(eligibility_reason="
+                    "'incident_not_found') keyword mapping of the failure path"
+                )
+    return violations
+
+
+def check_processor_uses_aggregate_eligibility(tree: ast.Module) -> list[str]:
+    """Confirm the processor uses the aggregate-based eligibility evaluator.
+
+    The processor MUST call
+    ``evaluate_incident_eligibility(incident=incident_obj, ...)`` with the
+    typed :class:`Incident` aggregate; a positive presence check closes
+    the gap where the verifier only forbade the legacy resolver without
+    proving the correct call is made.
+    """
+    violations: list[str] = []
+    processor = function_defs(tree)
+    process_incident = processor.get("_process_incident")
+    if process_incident is None:
+        return violations
+    found = False
+    for node in ast.walk(process_incident):
+        if not isinstance(node, ast.Call):
+            continue
+        names = called_names(node)
+        if "evaluate_incident_eligibility" in names and (
+            call_keyword(node, "incident") is not None
+        ):
+            found = True
+            break
+    if not found:
+        violations.append(
+            "incident_diagnosis_auto_loop_evidence_processor: "
+            "_process_incident must call evaluate_incident_eligibility("
+            "incident=…) with the typed aggregate"
+        )
+    return violations
+
+
+# ---------------------------------------------------------------------------
+# Evaluator checks
+# ---------------------------------------------------------------------------
+
+
+def check_evaluator_aggregate_signature() -> list[str]:
+    """The aggregate evaluator must accept a typed ``Incident`` parameter."""
+    tree = parse_path(EVALUATOR_PATH)
+    if tree is None:
+        return [f"{EVALUATOR_PATH}: cannot read or parse"]
+    funcs = function_defs(tree)
+    evaluator = funcs.get("evaluate_incident_eligibility")
+    if evaluator is None:
+        return [
+            f"{EVALUATOR_PATH}: evaluate_incident_eligibility function "
+            "is missing"
+        ]
+    violations: list[str] = []
+    positional = list(evaluator.args.args)
+    kwonly = list(evaluator.args.kwonlyargs)
+    has_incident_kw: bool = False
+    for arg in positional + kwonly:
+        if arg.arg != "incident":
+            continue
+        has_incident_kw = True
+        if arg.annotation is None:
+            violations.append(
+                f"{EVALUATOR_PATH}: evaluate_incident_eligibility "
+                "parameter ``incident`` must be annotated"
+            )
+        else:
+            ann = ast.unparse(arg.annotation).strip().strip("'\"")
+            if ann != "Incident":
+                violations.append(
+                    f"{EVALUATOR_PATH}: evaluate_incident_eligibility "
+                    f"parameter ``incident`` must be annotated as Incident; "
+                    f"got {ann!r}"
+                )
+    if not has_incident_kw:
+        violations.append(
+            f"{EVALUATOR_PATH}: evaluate_incident_eligibility must accept "
+            "a typed ``incident: Incident`` parameter"
+        )
+    return violations
+
+
+def check_evaluator_no_lookups() -> list[str]:
+    """The aggregate evaluator must not call any incident resolver."""
+    tree = parse_path(EVALUATOR_PATH)
+    if tree is None:
+        return []
+    funcs = function_defs(tree)
+    evaluator = funcs.get("evaluate_incident_eligibility")
+    if evaluator is None:
+        return []
+    violations: list[str] = []
+    for node in ast.walk(evaluator):
+        if not isinstance(node, ast.Call):
+            continue
+        names = called_names(node)
+        if not names:
+            continue
+        for forbidden in FORBIDDEN_EVALUATOR_CALLS:
+            if forbidden in names:
+                violations.append(
+                    f"{EVALUATOR_PATH}: evaluate_incident_eligibility "
+                    f"forbids call to {forbidden!r}"
+                )
+    return violations
+
+
+# ---------------------------------------------------------------------------
+# Seam-module availability check
+# ---------------------------------------------------------------------------
+
+
+def seam_available_names(
+    tree: ast.Module,
+) -> tuple[set[str], set[str], set[str]]:
+    """Return ``(defined, imported, exported)`` names for the seam module."""
+    defined = set(function_defs(tree))
+    imported: set[str] = set()
+    exported: set[str] = set()
+    for node in tree.body:
+        if isinstance(node, ast.ImportFrom):
+            for alias in node.names:
+                imported.add(alias.asname or alias.name)
+        if isinstance(node, ast.Assign):
+            for tgt in node.targets:
+                if isinstance(tgt, ast.Name) and tgt.id == "__all__" and isinstance(
+                    node.value, ast.List | ast.Tuple
+                ):
+                    for elt in node.value.elts:
+                        if isinstance(elt, ast.Constant) and isinstance(
+                            elt.value, str
+                        ):
+                            exported.add(elt.value)
+    return defined, imported, exported
+
+
+def check_seam_required_symbols() -> list[str]:
+    """The seam module must expose the required public API.
+
+    Every symbol in :data:`REQUIRED_SEAM_SYMBOLS` must be reachable
+    through the seam (defined locally, imported/re-exported, or listed
+    in ``__all__``). The lifecycle-dispatch functions and the wire
+    request builder must additionally be *defined* in the seam module,
+    not merely re-exported.
+    """
+    tree = parse_path(SEAM_PATH)
+    if tree is None:
+        return [f"{SEAM_PATH}: cannot read or parse"]
+    defined, imported, exported = seam_available_names(tree)
+    available = defined | imported | exported
+    violations: list[str] = []
+    # Every REQUIRED_SEAM_SYMBOL must be reachable through the seam.
+    for name in REQUIRED_SEAM_SYMBOLS:
+        if name not in available:
+            violations.append(
+                f"{SEAM_PATH}: required seam symbol {name!r} is not "
+                "defined, imported, or exported by the seam module"
+            )
+    # Lifecycle-dispatch symbols MUST be defined locally in the seam.
+    for name in (
+        "record_diagnosis_loop_started",
+        "record_diagnosis_loop_failed",
+        "record_diagnosis_loop_completed",
+        "build_lifecycle_request",
+    ):
+        if name not in defined:
+            violations.append(
+                f"{SEAM_PATH}: required seam symbol {name!r} "
+                "must be defined in the seam module"
+            )
+    return violations

=== scripts/verifiers/automatic_diagnosis_authority_seam01_helpers.py ===
diff --git a/scripts/verifiers/automatic_diagnosis_authority_seam01_helpers.py b/scripts/verifiers/automatic_diagnosis_authority_seam01_helpers.py
new file mode 100644
index 00000000..0596ce16
--- /dev/null
+++ b/scripts/verifiers/automatic_diagnosis_authority_seam01_helpers.py
@@ -0,0 +1,202 @@
+"""AST and file helpers for the ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+verifier.
+
+This module owns:
+
+* File-collection primitives (``_read``, ``_parse``, ``_iter_python_files``)
+  used by the verifier to discover source files under ``src/``.
+* Pure AST helpers (``_function_defs``, ``_called_names``,
+  ``_call_keyword``, ``_match_case_type``) that translate a parsed
+  :class:`ast.Module` into the minimal structures the individual checks
+  need.
+* Forbidden-pattern detectors that operate on any AST tree and are
+  reusable across multiple checks
+  (``_contains_truthiness_to_not_found``, ``_has_empty_except_pass``).
+
+The verifier entry point
+(:mod:`scripts.verifiers.automatic_diagnosis_authority_seam01`)
+re-exports every public helper so the self-tests can access them via
+the verifier module attribute. The per-file-size check is split between
+this helpers module and the per-check checks module to keep both files
+within the LLM-friendly 500-line limit.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+from __future__ import annotations
+
+import ast
+from collections.abc import Iterable
+from pathlib import Path
+
+# Repo-rooted paths reused by both this helpers module and the checks
+# module. They are duplicated here (not imported from the verifier
+# entry point) so the helpers module is self-contained and the cyclic
+# import graph stays acyclic.
+REPO_ROOT: Path = Path(__file__).resolve().parents[2]
+SRC_ROOT: Path = REPO_ROOT / "src" / "k8s_diag_agent"
+
+PROCESSOR_PATH: Path = (
+    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_evidence_processor.py"
+)
+EVALUATOR_PATH: Path = (
+    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_config.py"
+)
+SEAM_PATH: Path = (
+    SRC_ROOT / "collect" / "incident_diagnosis_authority_seam.py"
+)
+# Backward-compat alias for self-tests and existing call sites.
+ELIGIBILITY_PATH: Path = EVALUATOR_PATH
+
+
+def read_text(path: Path) -> str | None:
+    """Read a UTF-8 text file, returning ``None`` on OS errors."""
+    try:
+        return path.read_text(encoding="utf-8")
+    except OSError:
+        return None
+
+
+def parse_path(path: Path) -> ast.Module | None:
+    """Read and parse a Python file; return ``None`` on any error."""
+    source = read_text(path)
+    if source is None:
+        return None
+    try:
+        return ast.parse(source, filename=str(path))
+    except SyntaxError:
+        return None
+
+
+def iter_python_files() -> Iterable[Path]:
+    """Yield every non-``__init__`` Python file under ``src/``."""
+    for path in SRC_ROOT.rglob("*.py"):
+        if "__pycache__" in path.parts:
+            continue
+        if path.name == "__init__.py":
+            continue
+        yield path
+
+
+def function_defs(tree: ast.Module) -> dict[str, ast.FunctionDef]:
+    """Return a name→FunctionDef map for top-level function definitions."""
+    out: dict[str, ast.FunctionDef] = {}
+    for node in tree.body:
+        if isinstance(node, ast.FunctionDef):
+            out[node.name] = node
+    return out
+
+
+def called_names(node: ast.Call) -> list[str]:
+    """Return the dotted-name call identifier list for a Call node.
+
+    For ``a.b.c()`` we return ``["a", "b", "c"]``. For bare ``foo()``
+    we return ``["foo"]``. Side-effect-only calls return an empty
+    list so we never false-positive on attribute references used as
+    function arguments.
+    """
+    func = node.func
+    parts: list[str] = []
+    cur: ast.AST = func
+    while isinstance(cur, ast.Attribute):
+        parts.append(cur.attr)
+        cur = cur.value
+    if isinstance(cur, ast.Name):
+        parts.append(cur.id)
+        parts.reverse()
+        return parts
+    return []
+
+
+def call_keyword(call: ast.Call, keyword: str) -> ast.AST | None:
+    """Return the AST node passed as ``keyword=...`` to a call, or ``None``."""
+    for kw in call.keywords:
+        if kw.arg == keyword:
+            return kw.value
+    return None
+
+
+def match_case_type() -> type | None:
+    """Return the AST node type for ``match ... case`` patterns.
+
+    Python 3.10–3.13 expose :class:`ast.MatchCase`; Python 3.14
+    renamed the class to the lowercase :func:`ast.match_case` form.
+    """
+    return getattr(ast, "MatchCase", None) or getattr(ast, "match_case", None)
+
+
+def contains_truthiness_to_not_found(tree: ast.AST) -> bool:
+    """Return True if any ``if not X: ... reason="incident_not_found"`` appears.
+
+    The forbidden pattern collapses HTTP 200 + valid JSON into
+    ``incident_not_found`` via a truthiness check; the verifier must
+    reject it.
+    """
+
+    class _Visitor(ast.NodeVisitor):
+        def __init__(self) -> None:
+            self.found: bool = False
+
+        def visit_If(self, node: ast.If) -> None:  # noqa: D401
+            if self.found:
+                return
+            if not isinstance(node.test, ast.UnaryOp) or not isinstance(
+                node.test.op, ast.Not
+            ):
+                self.generic_visit(node)
+                return
+            for stmt in node.body:
+                for sub in ast.walk(stmt):
+                    if (
+                        isinstance(sub, ast.Assign)
+                        and isinstance(sub.value, ast.Constant)
+                        and sub.value.value == "incident_not_found"
+                    ):
+                        self.found = True
+                        return
+                    if (
+                        isinstance(sub, ast.AnnAssign)
+                        and isinstance(sub.value, ast.Constant)
+                        and sub.value.value == "incident_not_found"
+                    ):
+                        self.found = True
+                        return
+                    # Constructor keyword-argument form, e.g.
+                    # ``AutoLoopIncidentResult(eligibility_reason="incident_not_found")``.
+                    if isinstance(sub, ast.Call):
+                        for kw in sub.keywords:
+                            if (
+                                isinstance(kw.value, ast.Constant)
+                                and kw.value.value == "incident_not_found"
+                            ):
+                                self.found = True
+                                return
+            self.generic_visit(node)
+
+    v = _Visitor()
+    v.visit(tree)
+    return v.found
+
+
+def has_empty_except_pass(tree: ast.AST) -> bool:
+    """Return True if any ``except ...: pass`` (with no body) appears."""
+
+    class _Visitor(ast.NodeVisitor):
+        def __init__(self) -> None:
+            self.found: bool = False
+
+        def visit_Try(self, node: ast.Try) -> None:  # noqa: D401
+
+            if not self.found:
+                for handler in node.handlers:
+                    if (
+                        len(handler.body) == 1
+                        and isinstance(handler.body[0], ast.Pass)
+                    ):
+                        self.found = True
+                        break
+            self.generic_visit(node)
+
+    v = _Visitor()
+    v.visit(tree)
+    return v.found

=== src/k8s_diag_agent/collect/incident_automatic_diagnosis_loop_artifacts.py ===
diff --git a/src/k8s_diag_agent/collect/incident_automatic_diagnosis_loop_artifacts.py b/src/k8s_diag_agent/collect/incident_automatic_diagnosis_loop_artifacts.py
index 69d2c374..c85a35ec 100644
--- a/src/k8s_diag_agent/collect/incident_automatic_diagnosis_loop_artifacts.py
+++ b/src/k8s_diag_agent/collect/incident_automatic_diagnosis_loop_artifacts.py
@@ -214,9 +214,11 @@ def write_summary_artifact(
     incidents_ineligible: int = 0,
     incidents_with_errors: int = 0,
     eligibility_schema_version: int = 2,
+    authority_run_summary: dict[str, Any] | None = None,
 ) -> dict[str, Any]:
     """Write loop summary artifact.

+
     Args:
         artifact_dir: Directory for automatic-diagnosis artifacts
         run_id: Health run identity (from scheduler)
@@ -265,9 +267,11 @@ def write_summary_artifact(
         "skip_reasons": dict(skip_reasons or {}),
         "ineligible_reasons": dict(ineligible_reasons or {}),
         "error_reasons": dict(error_reasons or {}),
+        "authority_run_summary": dict(authority_run_summary or {}),
         "incident_results": incident_results,
     }

+
     try:
         path.write_text(json.dumps(artifact, indent=2, default=str))
         _logger.info(

=== src/k8s_diag_agent/collect/incident_diagnosis_authority_run_summary.py ===
diff --git a/src/k8s_diag_agent/collect/incident_diagnosis_authority_run_summary.py b/src/k8s_diag_agent/collect/incident_diagnosis_authority_run_summary.py
new file mode 100644
index 00000000..81d85f9d
--- /dev/null
+++ b/src/k8s_diag_agent/collect/incident_diagnosis_authority_run_summary.py
@@ -0,0 +1,125 @@
+"""Authority run-summary accounting for the automatic-diagnosis loop.
+
+This module derives the ACT-required per-run counters from the
+per-incident results the batch loop already produces:
+
+* ``backend_lookup_outcomes`` — how each incident's authority lookup
+  resolved (``found`` / ``not_found`` / ``lookup_failed``).
+* ``eligibility_outcomes`` — the eligibility decision keyed by reason
+  (``eligible`` when the incident was eligible, otherwise the bounded
+  ineligibility reason).
+* ``lifecycle_write_outcomes`` — how the lifecycle write resolved
+  (``applied`` / ``start_failed`` / ``completion_failed`` /
+  ``recording_failed`` / ``not_applicable``).
+* ``backend_found_then_incident_not_found`` — the split-authority
+  regression counter: a backend-found incident that nonetheless
+  produced an ``incident_not_found`` disposition. Post-fix this must
+  stay ``0``; a non-zero value is a direct signal that the closed
+  defect has reappeared.
+
+The accounting is a pure fold over result mappings so it is fully
+deterministic and testable without a running loop.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R1)
+"""
+
+from __future__ import annotations
+
+from collections.abc import Iterable, Mapping
+from dataclasses import dataclass, field
+from typing import Any
+
+__all__ = [
+    "AuthorityRunSummary",
+    "summarize_incident_results",
+]
+
+
+def _incr(counter: dict[str, int], key: str) -> None:
+    counter[key] = counter.get(key, 0) + 1
+
+
+@dataclass(slots=True)
+class AuthorityRunSummary:
+    """Bounded per-run accounting for the authority seam."""
+
+    backend_lookup_outcomes: dict[str, int] = field(default_factory=dict)
+    eligibility_outcomes: dict[str, int] = field(default_factory=dict)
+    lifecycle_write_outcomes: dict[str, int] = field(default_factory=dict)
+    backend_found_then_incident_not_found: int = 0
+
+    def record(self, result: Mapping[str, Any]) -> None:
+        """Fold a single per-incident result into the running counters."""
+        eligibility_reason = str(result.get("eligibility_reason") or "")
+        skip_reason = str(result.get("skip_reason") or "")
+        error = str(result.get("error") or "")
+        eligible = bool(result.get("eligible"))
+        skipped = bool(result.get("skipped"))
+
+        lookup = _classify_backend_lookup(eligibility_reason, skip_reason)
+        _incr(self.backend_lookup_outcomes, lookup)
+
+        _incr(
+            self.eligibility_outcomes,
+            "eligible" if eligible else (eligibility_reason or "unknown"),
+        )
+
+        _incr(
+            self.lifecycle_write_outcomes,
+            _classify_lifecycle_write(error, eligible=eligible, skipped=skipped),
+        )
+
+        # Split-authority regression: a backend-found incident must
+        # never collapse to ``incident_not_found``.
+        if lookup == "found" and (
+            eligibility_reason == "incident_not_found"
+            or "incident_not_found" in skip_reason
+        ):
+            self.backend_found_then_incident_not_found += 1
+
+    def to_dict(self) -> dict[str, Any]:
+        return {
+            "backend_lookup_outcomes": dict(self.backend_lookup_outcomes),
+            "eligibility_outcomes": dict(self.eligibility_outcomes),
+            "lifecycle_write_outcomes": dict(self.lifecycle_write_outcomes),
+            "backend_found_then_incident_not_found": (
+                self.backend_found_then_incident_not_found
+            ),
+        }
+
+
+def _classify_backend_lookup(eligibility_reason: str, skip_reason: str) -> str:
+    """Classify the authority lookup outcome for a per-incident result."""
+    if eligibility_reason == "not_found" and "incident_not_found" in skip_reason:
+        return "not_found"
+    if eligibility_reason.startswith("backend_incident_"):
+        return "lookup_failed"
+    return "found"
+
+
+def _classify_lifecycle_write(
+    error: str,
+    *,
+    eligible: bool,
+    skipped: bool,
+) -> str:
+    """Classify the lifecycle-write outcome from the result's error field."""
+    if "diagnosis_lifecycle_start_failed" in error:
+        return "start_failed"
+    if "diagnosis_lifecycle_completion_failed" in error:
+        return "completion_failed"
+    if "lifecycle_recording_error" in error:
+        return "recording_failed"
+    if eligible and not skipped and not error:
+        return "applied"
+    return "not_applicable"
+
+
+def summarize_incident_results(
+    results: Iterable[Mapping[str, Any]],
+) -> AuthorityRunSummary:
+    """Fold per-incident result mappings into an :class:`AuthorityRunSummary`."""
+    summary = AuthorityRunSummary()
+    for result in results:
+        summary.record(result)
+    return summary

=== src/k8s_diag_agent/collect/incident_diagnosis_authority_seam.py ===
diff --git a/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam.py b/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam.py
new file mode 100644
index 00000000..448aee90
--- /dev/null
+++ b/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam.py
@@ -0,0 +1,397 @@
+"""Authority seam for automatic-diagnosis incident reads and lifecycle writes.
+
+This module owns the **single** typed boundary that the automatic-diagnosis
+processor crosses when it needs to record diagnosis-loop lifecycle
+transitions (``started`` / ``failed`` / ``completed``) through the
+configured incident authority (local in-memory store, or backend
+internal API).
+
+The aggregate eligibility evaluator (:func:`evaluate_incident_eligibility`)
+and the local-store compatibility wrapper (:func:`check_incident_eligibility`)
+are defined in :mod:`incident_diagnosis_auto_loop_config` and re-exported
+here for callers that want the canonical API through this seam.
+
+The split-authority defect closed by
+``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` is anchored in this
+seam:
+
+* The previous code re-resolved the backend-fetched incident through
+  the **local** ``get_incident_store()`` for eligibility evaluation,
+  producing ``not_eligible: incident_not_found`` on the scheduler even
+  though the backend had returned HTTP 200 with a valid canonical
+  incident. The aggregate evaluator accepts a typed
+  :class:`Incident` and does not call any incident resolver.
+* The previous code also routed diagnosis-lifecycle writes through the
+  local store even in backend mode. The lifecycle seam below resolves
+  the same dispatch configuration the incident-detail lookup uses, and
+  routes writes accordingly.
+
+To keep this module at a maintainable size, the implementation is
+split across four sibling modules:
+
+* :mod:`incident_diagnosis_authority_seam_types` — closed vocabulary,
+  bounded typed outcomes, schema-version constant.
+* :mod:`incident_diagnosis_authority_seam_local` — local-mode writer.
+* :mod:`incident_diagnosis_authority_seam_backend` — backend-mode HTTP
+  transport + response translator.
+
+This seam module is the only public entry point; callers MUST NOT
+import from the sibling modules directly.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+from __future__ import annotations
+
+import logging
+import os
+from dataclasses import dataclass, field
+from datetime import UTC, datetime
+from typing import Any
+
+from .incident_diagnosis_authority_seam_types import (
+    LIFECYCLE_SCHEMA_VERSION,
+    LifecycleDispatchMode,
+    LifecycleTransition,
+    LifecycleWriteApplied,
+    LifecycleWriteFailed,
+    LifecycleWriteOutcome,
+    LifecycleWriteRejected,
+    LifecycleWriteSkipped,
+)
+from .incident_diagnosis_auto_loop_config import (
+    check_incident_eligibility,
+    evaluate_incident_eligibility,
+)
+from .incident_diagnosis_dispatch_contracts import (
+    ENV_BACKEND_URL,
+    ENV_INTERNAL_API_TOKEN,
+    ENV_PROCESS_ROLE,
+    ENV_PROMOTION_MODE,
+    ENV_STORE_BACKEND,
+    MODE_BACKEND_API,
+    IncidentDiagnosisDispatchConfig,
+)
+
+_logger = logging.getLogger(__name__)
+
+
+__all__ = [
+    "LifecycleTransition",
+    "LifecycleDispatchMode",
+    "LifecycleWriteOutcome",
+    "LifecycleWriteApplied",
+    "LifecycleWriteRejected",
+    "LifecycleWriteFailed",
+    "LifecycleWriteSkipped",
+    "evaluate_incident_eligibility",
+    "check_incident_eligibility",
+    "record_diagnosis_loop_started",
+    "record_diagnosis_loop_failed",
+    "record_diagnosis_loop_completed",
+    "build_lifecycle_request",
+]
+
+
+# ---------------------------------------------------------------------------
+# Lifecycle authority seam
+# ---------------------------------------------------------------------------
+
+
+def _resolve_lifecycle_dispatch_mode() -> LifecycleDispatchMode:
+    """Resolve the lifecycle dispatch mode from the same env config the
+    incident-detail dispatcher uses.
+
+    Keeping the resolution in lock-step with
+    :mod:`incident_diagnosis_dispatch_contracts` is critical: a
+    scheduler that performs backend-mode incident reads MUST also
+    perform backend-mode lifecycle writes, otherwise it silently
+    diverges from the configured authority and writes to a
+    non-authoritative store.
+    """
+    config = IncidentDiagnosisDispatchConfig(
+        mode=os.environ.get(ENV_PROMOTION_MODE, "auto").lower(),  # type: ignore[arg-type]
+        backend_url=os.environ.get(ENV_BACKEND_URL),
+        internal_api_token=os.environ.get(ENV_INTERNAL_API_TOKEN),
+        store_backend=os.environ.get(ENV_STORE_BACKEND, "memory").lower(),
+        process_role=os.environ.get(ENV_PROCESS_ROLE, "").lower(),
+    )
+    resolved = config.resolved_mode()
+    if resolved == MODE_BACKEND_API:
+        return LifecycleDispatchMode.BACKEND
+    return LifecycleDispatchMode.LOCAL
+
+
+def _now_iso() -> str:
+    return datetime.now(UTC).isoformat()
+
+
+@dataclass(frozen=True, slots=True)
+class _LifecycleRequest:
+    """Internal wire-shape for the backend lifecycle endpoint."""
+
+    schema_version: int
+    incident_id: str
+    transition: LifecycleTransition
+    collector_run_id: str
+    diagnosis_run_id: str | None
+    occurred_at: str
+    payload: dict[str, Any] = field(default_factory=dict)
+
+    def to_dict(self) -> dict[str, Any]:
+        body: dict[str, Any] = {
+            "schemaVersion": self.schema_version,
+            "incidentId": self.incident_id,
+            "transition": self.transition.value,
+            "collectorRunId": self.collector_run_id,
+            "occurredAt": self.occurred_at,
+            "payload": dict(self.payload),
+        }
+        if self.diagnosis_run_id is not None:
+            body["diagnosisRunId"] = self.diagnosis_run_id
+        return body
+
+
+def build_lifecycle_request(
+    *,
+    incident_id: str,
+    transition: LifecycleTransition,
+    collector_run_id: str,
+    diagnosis_run_id: str | None,
+    payload: dict[str, Any] | None = None,
+) -> _LifecycleRequest:
+    """Construct the canonical lifecycle wire-payload.
+
+    Centralises the schema-version and field-naming contract so the
+    scheduler client and the backend handler cannot drift.
+    """
+    return _LifecycleRequest(
+        schema_version=LIFECYCLE_SCHEMA_VERSION,
+        incident_id=str(incident_id),
+        transition=transition,
+        collector_run_id=str(collector_run_id),
+        diagnosis_run_id=(
+            str(diagnosis_run_id) if diagnosis_run_id is not None else None
+        ),
+        occurred_at=_now_iso(),
+        payload=dict(payload or {}),
+    )
+
+
+# ---------------------------------------------------------------------------
+# Public lifecycle authority API
+# ---------------------------------------------------------------------------
+
+
+def _dispatch_lifecycle(
+    *,
+    transition: LifecycleTransition,
+    incident_id: str,
+    run_id: str,
+    collector_run_id: str,
+    payload: dict[str, Any],
+) -> LifecycleWriteOutcome:
+    """Resolve the dispatch mode and apply the transition.
+
+    The local- and backend-mode writers are imported lazily to avoid a
+    circular import: each writer imports :func:`build_lifecycle_request`
+    from this seam module, so this module cannot import them at
+    top-level. The dispatch call only happens at runtime, by which time
+    the seam module is fully initialised.
+    """
+    # Lazy imports to break the circular cycle between this seam module
+    # and its sibling writers.
+    from .incident_diagnosis_authority_seam_backend import (
+        _record_lifecycle_backend,
+    )
+    from .incident_diagnosis_authority_seam_local import (
+        _record_lifecycle_local,
+    )
+
+    mode = _resolve_lifecycle_dispatch_mode()
+    if mode == LifecycleDispatchMode.LOCAL:
+        return _record_lifecycle_local(
+            transition=transition,
+            incident_id=incident_id,
+            run_id=run_id,
+            collector_run_id=collector_run_id,
+            payload=payload,
+        )
+    return _record_lifecycle_backend(
+        transition=transition,
+        incident_id=incident_id,
+        run_id=run_id,
+        collector_run_id=collector_run_id,
+        payload=payload,
+    )
+
+
+def _emit_lifecycle_event(
+    *,
+    outcome: LifecycleWriteOutcome,
+    collector_run_id: str,
+    diagnosis_run_id: str,
+    incident_access_mode: str,
+) -> None:
+    """Emit a structured INFO-level event for the lifecycle write.
+
+    Events:
+        automatic-diagnosis-lifecycle-transition-applied
+        automatic-diagnosis-lifecycle-transition-rejected
+        automatic-diagnosis-lifecycle-transition-failed
+        automatic-diagnosis-lifecycle-transition-skipped
+    """
+    if isinstance(outcome, LifecycleWriteApplied):
+        event = "automatic-diagnosis-lifecycle-transition-applied"
+        extra: dict[str, Any] = {
+            "event": event,
+            "incident_id": outcome.incident_id,
+            "collector_run_id": collector_run_id,
+            "diagnosis_run_id": diagnosis_run_id,
+            "transition": outcome.transition.value,
+            "incident_access_mode": incident_access_mode,
+            "http_status": outcome.http_status,
+            "idempotent_replay": outcome.idempotent_replay,
+            "applied": True,
+        }
+        if outcome.detail is not None:
+            extra["detail"] = outcome.detail
+        _logger.info("lifecycle transition applied", extra=extra)
+        return
+
+    if isinstance(outcome, LifecycleWriteRejected):
+        event = "automatic-diagnosis-lifecycle-transition-rejected"
+        extra = {
+            "event": event,
+            "incident_id": outcome.incident_id,
+            "collector_run_id": collector_run_id,
+            "diagnosis_run_id": diagnosis_run_id,
+            "transition": outcome.transition.value,
+            "incident_access_mode": incident_access_mode,
+            "http_status": outcome.http_status,
+            "failure_code": outcome.reason_code,
+            "applied": False,
+        }
+        if outcome.detail is not None:
+            extra["detail"] = outcome.detail
+        _logger.info("lifecycle transition rejected", extra=extra)
+        return
+
+    if isinstance(outcome, LifecycleWriteFailed):
+        event = "automatic-diagnosis-lifecycle-transition-failed"
+        extra = {
+            "event": event,
+            "incident_id": outcome.incident_id,
+            "collector_run_id": collector_run_id,
+            "diagnosis_run_id": diagnosis_run_id,
+            "transition": outcome.transition.value,
+            "incident_access_mode": incident_access_mode,
+            "http_status": outcome.http_status,
+            "failure_code": outcome.reason_code,
+            "applied": False,
+        }
+        if outcome.exception_type is not None:
+            extra["exception_type"] = outcome.exception_type
+        if outcome.detail is not None:
+            extra["detail"] = outcome.detail
+        _logger.warning("lifecycle transition failed", extra=extra)
+        return
+
+    if isinstance(outcome, LifecycleWriteSkipped):
+        event = "automatic-diagnosis-lifecycle-transition-skipped"
+        extra = {
+            "event": event,
+            "incident_id": outcome.incident_id,
+            "collector_run_id": collector_run_id,
+            "diagnosis_run_id": diagnosis_run_id,
+            "transition": outcome.transition.value,
+            "incident_access_mode": incident_access_mode,
+            "applied": False,
+            "reason": outcome.reason,
+        }
+        _logger.info("lifecycle transition skipped", extra=extra)
+        return
+
+
+def record_diagnosis_loop_started(
+    *,
+    incident_id: str,
+    run_id: str,
+    collector_run_id: str,
+) -> LifecycleWriteOutcome:
+    """Record that the automatic-diagnosis loop started for an incident."""
+    outcome = _dispatch_lifecycle(
+        transition=LifecycleTransition.STARTED,
+        incident_id=incident_id,
+        run_id=run_id,
+        collector_run_id=collector_run_id,
+        payload={},
+    )
+    _emit_lifecycle_event(
+        outcome=outcome,
+        collector_run_id=collector_run_id,
+        diagnosis_run_id=run_id,
+        incident_access_mode=_resolve_lifecycle_dispatch_mode().value,
+    )
+    return outcome
+
+
+def record_diagnosis_loop_failed(
+    *,
+    incident_id: str,
+    run_id: str,
+    collector_run_id: str,
+    unavailable_reason: str,
+) -> LifecycleWriteOutcome:
+    """Record that the automatic-diagnosis loop failed for an incident."""
+    outcome = _dispatch_lifecycle(
+        transition=LifecycleTransition.FAILED,
+        incident_id=incident_id,
+        run_id=run_id,
+        collector_run_id=collector_run_id,
+        payload={"unavailable_reason": str(unavailable_reason)},
+    )
+    _emit_lifecycle_event(
+        outcome=outcome,
+        collector_run_id=collector_run_id,
+        diagnosis_run_id=run_id,
+        incident_access_mode=_resolve_lifecycle_dispatch_mode().value,
+    )
+    return outcome
+
+
+def record_diagnosis_loop_completed(
+    *,
+    incident_id: str,
+    run_id: str,
+    collector_run_id: str,
+    review_packet_name: str | None = None,
+    checks_requested: int = 0,
+    checks_run: int = 0,
+    checks_rejected: int = 0,
+    decision: str | None = None,
+) -> LifecycleWriteOutcome:
+    """Record that the automatic-diagnosis loop completed for an incident."""
+    payload: dict[str, Any] = {
+        "checks_requested": int(checks_requested),
+        "checks_run": int(checks_run),
+        "checks_rejected": int(checks_rejected),
+    }
+    if review_packet_name is not None:
+        payload["review_packet_name"] = str(review_packet_name)
+    if decision is not None:
+        payload["decision"] = str(decision)
+    outcome = _dispatch_lifecycle(
+        transition=LifecycleTransition.COMPLETED,
+        incident_id=incident_id,
+        run_id=run_id,
+        collector_run_id=collector_run_id,
+        payload=payload,
+    )
+    _emit_lifecycle_event(
+        outcome=outcome,
+        collector_run_id=collector_run_id,
+        diagnosis_run_id=run_id,
+        incident_access_mode=_resolve_lifecycle_dispatch_mode().value,
+    )
+    return outcome

=== src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_backend.py ===
diff --git a/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_backend.py b/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_backend.py
new file mode 100644
index 00000000..96ef1949
--- /dev/null
+++ b/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_backend.py
@@ -0,0 +1,251 @@
+"""Backend-mode lifecycle writer for the automatic-diagnosis authority seam.
+
+This module owns the ``backend`` half of the lifecycle dispatch split:
+it builds the canonical lifecycle wire-request, performs the
+authenticated HTTP POST against the configured backend internal API,
+and translates the response into a typed :class:`LifecycleWriteOutcome`.
+
+The seam module (:mod:`incident_diagnosis_authority_seam`) is the only
+public entry point; callers MUST NOT import from this file directly.
+
+Failure translation is exhaustive:
+
+* 200 + ``applied=true`` → ``LifecycleWriteApplied``
+* 200 + ``applied=false`` → ``LifecycleWriteRejected`` (with the bounded code)
+* 404 → ``LifecycleWriteFailed`` (``incident_not_found``) so the
+  scheduler never collapses it to the eligibility-level reason.
+* 409 (conflict) → ``LifecycleWriteRejected`` (``transition_replay_mismatch``).
+* 4xx (other) → ``LifecycleWriteRejected``
+* 5xx → ``LifecycleWriteFailed`` (``backend_error``)
+* 1xx / 2xx-other / 3xx → ``LifecycleWriteFailed`` (``transport_error``)
+
+Transport errors (timeout, URL error, OS error) NEVER fall back to the
+local store; the scheduler must observe the failure.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+from __future__ import annotations
+
+import os
+import urllib.error
+import urllib.request
+from typing import Any
+
+from .incident_diagnosis_authority_seam import build_lifecycle_request
+from .incident_diagnosis_authority_seam_types import (
+    LifecycleTransition,
+    LifecycleWriteApplied,
+    LifecycleWriteFailed,
+    LifecycleWriteOutcome,
+    LifecycleWriteRejected,
+)
+from .incident_diagnosis_dispatch_contracts import (
+    ENV_BACKEND_URL,
+    ENV_INTERNAL_API_TOKEN,
+)
+
+
+def _encode_lifecycle_body(request: Any) -> bytes:
+    import json
+
+    return json.dumps(request.to_dict()).encode("utf-8")
+
+
+def _translate_lifecycle_response(
+    *,
+    transition: LifecycleTransition,
+    incident_id: str,
+    http_status: int,
+    body_bytes: bytes,
+) -> LifecycleWriteOutcome:
+    """Translate a backend HTTP response into a typed write outcome.
+
+    The translation is exhaustive over the bounded contract; see the
+    module docstring for the full mapping table.
+    """
+    import json
+
+    decoded: dict[str, Any] | None = None
+    if body_bytes:
+        try:
+            parsed = json.loads(body_bytes.decode("utf-8"))
+            if isinstance(parsed, dict):
+                decoded = parsed
+        except (json.JSONDecodeError, UnicodeDecodeError):
+            decoded = None
+
+    if http_status == 200 and decoded is not None:
+        if bool(decoded.get("applied", False)) is True:
+            return LifecycleWriteApplied(
+                transition=transition,
+                incident_id=incident_id,
+                idempotent_replay=bool(decoded.get("idempotentReplay", False)),
+                http_status=http_status,
+                detail=(
+                    str(decoded.get("detail"))
+                    if decoded.get("detail") is not None
+                    else "applied via backend"
+                ),
+            )
+        # 200 with explicit applied=false: treat as rejected so the
+        # scheduler does not assume success.
+        return LifecycleWriteRejected(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code=str(decoded.get("reasonCode") or "backend_rejected"),
+            http_status=http_status,
+            detail=(
+                str(decoded.get("message"))
+                if decoded.get("message") is not None
+                else None
+            ),
+        )
+
+    if http_status == 404:
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="incident_not_found",
+            http_status=http_status,
+            detail="backend reported 404 for the incident",
+        )
+
+    if 400 <= http_status < 500:
+        reason_code = "request_rejected"
+        detail: str | None = None
+        if decoded is not None:
+            reason_code = str(
+                decoded.get("reasonCode")
+                or decoded.get("errorCode")
+                or "request_rejected"
+            )
+            detail = (
+                str(decoded.get("message"))
+                if decoded.get("message") is not None
+                else None
+            )
+        return LifecycleWriteRejected(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code=reason_code,
+            http_status=http_status,
+            detail=detail,
+        )
+
+    if http_status >= 500:
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="backend_error",
+            http_status=http_status,
+            detail=(
+                str(decoded.get("message"))
+                if decoded is not None and decoded.get("message") is not None
+                else None
+            ),
+        )
+
+    # 1xx / 2xx other than 200 / 3xx: treat as transport anomaly.
+    return LifecycleWriteFailed(
+        transition=transition,
+        incident_id=incident_id,
+        reason_code="transport_error",
+        http_status=http_status,
+        detail=f"unexpected HTTP status {http_status}",
+    )
+
+
+def _record_lifecycle_backend(
+    *,
+    transition: LifecycleTransition,
+    incident_id: str,
+    run_id: str,
+    collector_run_id: str,
+    payload: dict[str, Any],
+) -> LifecycleWriteOutcome:
+    """POST a lifecycle transition to the backend internal API.
+
+    Returns a typed :class:`LifecycleWriteOutcome`. NEVER falls back
+    to the local store on failure.
+    """
+    backend_url = os.environ.get(ENV_BACKEND_URL, "").rstrip("/")
+    token = os.environ.get(ENV_INTERNAL_API_TOKEN)
+    if not backend_url:
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="backend_url_not_configured",
+            detail="K9B_BACKEND_INTERNAL_URL is not set in scheduler env",
+        )
+    if not token:
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="missing_internal_token",
+            detail="K9B_INTERNAL_API_TOKEN is not set in scheduler env",
+        )
+
+    request = build_lifecycle_request(
+        incident_id=incident_id,
+        transition=transition,
+        collector_run_id=collector_run_id,
+        diagnosis_run_id=run_id,
+        payload=payload,
+    )
+    url = f"{backend_url}/api/internal/incidents/diagnosis-loop-transition"
+    body = _encode_lifecycle_body(request)
+    headers = {
+        "Content-Type": "application/json",
+        "Authorization": f"Bearer {token}",
+    }
+    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
+    try:
+        with urllib.request.urlopen(req, timeout=30.0) as resp:
+            status = int(resp.status)
+            raw = resp.read()
+            return _translate_lifecycle_response(
+                transition=transition,
+                incident_id=incident_id,
+                http_status=status,
+                body_bytes=raw,
+            )
+    except urllib.error.HTTPError as exc:
+        try:
+            raw = exc.read()
+        except Exception:  # noqa: BLE001 - defensive
+            raw = b""
+        return _translate_lifecycle_response(
+            transition=transition,
+            incident_id=incident_id,
+            http_status=int(exc.code),
+            body_bytes=raw,
+        )
+    except TimeoutError:
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="transport_error",
+            detail="request to backend timed out",
+            exception_type="TimeoutError",
+        )
+    except urllib.error.URLError as exc:
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="transport_error",
+            detail=f"backend URL error: {exc.reason!r}",
+            exception_type=(
+                type(exc.reason).__name__
+                if getattr(exc, "reason", None) is not None
+                else "URLError"
+            ),
+        )
+    except OSError as exc:
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="transport_error",
+            detail=f"backend connection error: {exc}",
+            exception_type=type(exc).__name__,
+        )

=== src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_local.py ===
diff --git a/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_local.py b/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_local.py
new file mode 100644
index 00000000..e03a0d8a
--- /dev/null
+++ b/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_local.py
@@ -0,0 +1,108 @@
+"""Local-mode lifecycle writer for the automatic-diagnosis authority seam.
+
+This module owns the ``local`` half of the lifecycle dispatch split: it
+calls the in-process :class:`IncidentStore` directly when the scheduler
+resolves ``LifecycleDispatchMode.LOCAL``. The backend-mode half lives in
+:mod:`incident_diagnosis_authority_seam_backend` and is selected when
+the dispatcher resolves ``LifecycleDispatchMode.BACKEND``.
+
+The seam module (:mod:`incident_diagnosis_authority_seam`) is the only
+public entry point; callers MUST NOT import from this file directly.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+from __future__ import annotations
+
+from typing import Any
+
+from .incident_diagnosis_authority_seam_types import (
+    LifecycleTransition,
+    LifecycleWriteApplied,
+    LifecycleWriteFailed,
+    LifecycleWriteOutcome,
+)
+from .incident_store_provider import get_incident_store
+
+
+def _record_lifecycle_local(
+    *,
+    transition: LifecycleTransition,
+    incident_id: str,
+    run_id: str,
+    collector_run_id: str,
+    payload: dict[str, Any],
+) -> LifecycleWriteOutcome:
+    """Apply a lifecycle transition through the local incident store.
+
+    The local store returns ``None`` when the incident is absent, which
+    we surface as :class:`LifecycleWriteFailed` with the canonical
+    ``incident_not_found`` reason so the scheduler can distinguish it
+    from generic persistence failures.
+    """
+    store = get_incident_store()
+    try:
+        if transition == LifecycleTransition.STARTED:
+            updated = store.mark_diagnosis_loop_started(
+                incident_id=incident_id,
+                run_id=run_id,
+                collector_run_id=collector_run_id,
+            )
+        elif transition == LifecycleTransition.FAILED:
+            updated = store.mark_diagnosis_loop_failed(
+                incident_id=incident_id,
+                run_id=run_id,
+                collector_run_id=collector_run_id,
+                unavailable_reason=str(payload.get("unavailable_reason", "")) or None,
+            )
+        elif transition == LifecycleTransition.COMPLETED:
+            updated = store.mark_diagnosis_loop_completed(
+                incident_id=incident_id,
+                run_id=run_id,
+                collector_run_id=collector_run_id,
+                review_packet_name=(
+                    str(payload["review_packet_name"])
+                    if payload.get("review_packet_name") is not None
+                    else None
+                ),
+                checks_requested=int(payload.get("checks_requested", 0) or 0),
+                checks_run=int(payload.get("checks_run", 0) or 0),
+                checks_rejected=int(payload.get("checks_rejected", 0) or 0),
+                decision=(
+                    str(payload["decision"])
+                    if payload.get("decision") is not None
+                    else None
+                ),
+            )
+        else:  # pragma: no cover - exhaustiveness guard
+            return LifecycleWriteFailed(
+                transition=transition,
+                incident_id=incident_id,
+                reason_code="unsupported_transition",
+                detail=f"unsupported transition: {transition!r}",
+            )
+    except Exception as exc:  # noqa: BLE001 - boundary translation
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="local_persistence_failed",
+            detail=f"local store raised {type(exc).__name__}: {exc}",
+            exception_type=type(exc).__name__,
+        )
+
+    if updated is None:
+        return LifecycleWriteFailed(
+            transition=transition,
+            incident_id=incident_id,
+            reason_code="incident_not_found",
+            detail=(
+                f"local store has no incident for {incident_id!r}"
+            ),
+        )
+    return LifecycleWriteApplied(
+        transition=transition,
+        incident_id=incident_id,
+        idempotent_replay=False,
+        http_status=None,
+        detail="applied via local store",
+    )

=== src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_types.py ===
diff --git a/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_types.py b/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_types.py
new file mode 100644
index 00000000..46b8a296
--- /dev/null
+++ b/src/k8s_diag_agent/collect/incident_diagnosis_authority_seam_types.py
@@ -0,0 +1,137 @@
+"""Shared types for the automatic-diagnosis authority seam.
+
+This module exists to break the circular import between the seam
+(:mod:`incident_diagnosis_authority_seam`), the local-mode writer
+(:mod:`incident_diagnosis_authority_seam_local`), and the backend-mode
+writer (:mod:`incident_diagnosis_authority_seam_backend`).
+
+It owns the closed vocabulary (:class:`LifecycleTransition`,
+:class:`LifecycleDispatchMode`), the bounded typed write outcomes
+(:class:`LifecycleWriteApplied` / :class:`LifecycleWriteRejected` /
+:class:`LifecycleWriteFailed` / :class:`LifecycleWriteSkipped`), the
+:class:`LifecycleWriteOutcome` union, and the wire-schema version
+constant.
+
+Callers MUST import the public types from the seam module
+(:mod:`incident_diagnosis_authority_seam`), which re-exports them. The
+sibling dispatch modules import directly from this types module to
+avoid a circular import cycle.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+from enum import StrEnum
+from typing import Final, Literal, TypeAlias
+
+# Lifecycle-transition request/response schema version. The backend
+# internal endpoint and the scheduler client MUST agree on this value.
+# A request carrying an unsupported schema version is rejected by the
+# backend handler with HTTP 400 (unsupported request schema), which the
+# response translator maps to ``LifecycleWriteRejected``. This 400
+# contract is canonical across server behavior, client translation,
+# documentation, and tests.
+LIFECYCLE_SCHEMA_VERSION: Final[int] = 1
+
+
+class LifecycleTransition(StrEnum):
+    """Closed vocabulary of automatic-diagnosis lifecycle transitions.
+
+    The backend internal lifecycle endpoint, the scheduler-side client,
+    and the aggregate store delegate ALL route through this enum so the
+    transition string is never authored as a free literal at any call
+    site.
+    """
+
+    STARTED = "started"
+    FAILED = "failed"
+    COMPLETED = "completed"
+
+
+class LifecycleDispatchMode(StrEnum):
+    """The active dispatch mode for lifecycle writes.
+
+    Mirrors the incident-detail dispatch mode so a single configuration
+    resolution drives both reads and writes.
+    """
+
+    LOCAL = "local"
+    BACKEND = "backend"
+
+
+@dataclass(frozen=True, slots=True)
+class LifecycleWriteApplied:
+    """The authority applied the requested lifecycle transition.
+
+    For backend mode ``idempotent_replay`` is set when the backend
+    recognised a previously-applied identical transition and did not
+    duplicate any side effects. ``http_status`` is set to the observed
+    response status for backend mode and is ``None`` for local mode.
+    """
+    transition: LifecycleTransition
+    incident_id: str
+    applied: Literal[True] = True
+    idempotent_replay: bool = False
+    http_status: int | None = None
+    detail: str | None = None
+
+
+@dataclass(frozen=True, slots=True)
+class LifecycleWriteRejected:
+    """The authority rejected the transition with a bounded reason.
+
+    A ``LifecycleWriteRejected`` is the typed equivalent of HTTP 4xx
+    responses that are NOT ``404`` (which is mapped to
+    ``LifecycleWriteFailed``). The scheduler MUST surface this without
+    silent fallback to local storage.
+    """
+    transition: LifecycleTransition
+    incident_id: str
+    reason_code: str
+    applied: Literal[False] = False
+    http_status: int | None = None
+    detail: str | None = None
+
+
+@dataclass(frozen=True, slots=True)
+class LifecycleWriteFailed:
+    """The lifecycle write failed for a non-business reason.
+
+    Covers transport errors, 5xx responses, 404 (incident not found in
+    the backend store), and authentication failures. The scheduler MUST
+    NOT silently fall back to local storage when this outcome is
+    returned; the operator must observe the failure.
+    """
+    transition: LifecycleTransition
+    incident_id: str
+    reason_code: str
+    applied: Literal[False] = False
+    http_status: int | None = None
+    detail: str | None = None
+    exception_type: str | None = None
+
+
+@dataclass(frozen=True, slots=True)
+class LifecycleWriteSkipped:
+    """The lifecycle write was deliberately skipped (e.g. local mode has no
+    authoritative backend store, or the resolver refused to dispatch).
+
+    This is the ONLY outcome that does not imply a transport or backend
+    failure. It is used to make ``Authority-aware dispatch refused to
+    operate in this mode`` explicit so the scheduler can decide whether
+    the missing write is acceptable.
+    """
+    transition: LifecycleTransition
+    incident_id: str
+    reason: str
+    applied: Literal[False] = False
+
+
+LifecycleWriteOutcome: TypeAlias = (
+    LifecycleWriteApplied
+    | LifecycleWriteRejected
+    | LifecycleWriteFailed
+    | LifecycleWriteSkipped
+)

=== src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_config.py ===
diff --git a/src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_config.py b/src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_config.py
index 15e0ba70..bf244004 100644
--- a/src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_config.py
+++ b/src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_config.py
@@ -2,11 +2,23 @@

 This module provides:
 - AutomaticDiagnosisLoopConfig dataclass with hard budget bounds
-- EligibilityResult dataclass for eligibility checks
-- check_incident_eligibility() function
+- EligibilityResult / DiagnosisBudgetDiagnostic dataclasses
+- :func:`evaluate_incident_eligibility` (aggregate-based; lookup-free)
+- :func:`check_incident_eligibility` (local-store compatibility wrapper)
+
+The aggregate evaluator accepts a typed :class:`Incident` aggregate
+and never re-resolves the incident through the local store; the
+compat wrapper exists only for local-mode callers and tests.
+
+ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 added the aggregate
+entry point so the scheduler-side processor can pass the typed
+``Incident`` from a successful :class:`BackendIncidentFound` directly
+to :func:`evaluate_incident_eligibility` without a second incident
+lookup.

 The gate functions (is_automatic_diagnosis_loop_enabled, etc.)
-have been moved to incident_diagnosis_loop_gate.py for better organization.
+have been moved to incident_diagnosis_loop_gate.py for better
+organization.
 """

 from __future__ import annotations
@@ -19,13 +31,14 @@ from .incident_lifecycle import IncidentStatus
 from .incident_store_provider import get_incident_store

 if TYPE_CHECKING:
-    pass
+    from .incident_lifecycle import Incident

 __all__ = [
     "AutomaticDiagnosisLoopConfig",
     "DiagnosisBudgetDiagnostic",
     "EligibilityResult",
     "check_incident_eligibility",
+    "evaluate_incident_eligibility",
     "_ACTIVE_STATUSES",
     "_TERMINAL_STATUSES",
     # Re-export gate functions for backwards compatibility
@@ -203,38 +216,75 @@ class EligibilityResult:
         return "; ".join(lines)


-def check_incident_eligibility(
+
+
+def _count_automatic_review_packets(
+    *,
     incident_id: str,
+    external_analysis_dir: Path | None,
+) -> int:
+    """Count existing automatic review-packet artifacts for an incident.
+
+    The heuristic is intentionally filesystem-based: it never reaches
+    the incident store, never reaches a backend, and never accepts a
+    bare ``incident_id`` without the matching aggregate context already
+    known to the caller.
+    """
+    if external_analysis_dir is None or not external_analysis_dir.exists():
+        return 0
+    prefix = f"auto-{incident_id}-"
+    suffix = "-diagnosis-review-packet.json"
+    count = 0
+    try:
+        for path in external_analysis_dir.rglob("*"):
+            try:
+                if path.is_file() and path.name.startswith(prefix) and path.name.endswith(suffix):
+                    count += 1
+            except OSError:
+                continue
+    except OSError:
+        return count
+    return count
+
+
+def evaluate_incident_eligibility(
+    *,
+    incident: Incident,
     config: AutomaticDiagnosisLoopConfig,
     external_analysis_dir: Path | None = None,
 ) -> EligibilityResult:
-    """Check if an incident is eligible for automatic diagnosis loop.
+    """Evaluate automatic-diagnosis eligibility from a typed incident aggregate.
+
+    The evaluator is **lookup-free**: it accepts a typed
+    :class:`Incident` and never resolves the incident from the store,
+    never calls a backend detail client, and never accepts an
+    ``incident_id`` as its only incident input. Filesystem inspection
+    for existing review-packet artifacts and budget accounting is
+    permitted where the budget lookup is required.

-    Conservative eligibility model:
-    - Must be in active status (OPEN, COLLECTING_EVIDENCE, INVESTIGATING)
-    - Must not be in terminal status (SUPPRESSED, DUPLICATE, RESOLVED, READY_FOR_REVIEW)
-    - Must have suggested_checks OR enough context for stop-path packet
-    - Must not have exceeded automatic loop budget
+    Production callers reach this function with the incident aggregate
+    returned from :class:`BackendIncidentFound` so the same typed
+    snapshot drives both domain eligibility and downstream case-file
+    construction.

     Args:
-        incident_id: The incident ID to check
-        config: Collector configuration with budget limits
-        external_analysis_dir: Optional path to check for existing review packets
+        incident: The canonical :class:`Incident` aggregate to evaluate.
+            The supplied ``incident_id`` field is the authoritative
+            identity for diagnostics and budget counts.
+        config: Collector configuration with budget limits.
+        external_analysis_dir: Optional path used to count existing
+            automatic review packets for the per-incident budget.

     Returns:
-        EligibilityResult with eligible flag, reason, and budget diagnostics
+        :class:`EligibilityResult` with the same closed vocabulary the
+        legacy ``check_incident_eligibility`` used, so existing
+        ``AutoLoopIncidentResult`` projection still works.
     """
-    store = get_incident_store()
-    incident = store.get_incident(incident_id)
-
-    if incident is None:
-        return EligibilityResult(
-            eligible=False,
-            incident_id=incident_id,
-            reason="incident_not_found",
-        )
+    incident_id = str(incident.incident_id)

-    # Check status
+    # Status checks. SUPPRESSED / DUPLICATE / RESOLVED / READY_FOR_REVIEW
+    # remain terminal and emit the legacy ``terminal_status_<value>``
+    # reason so the existing skip-reason accounting is preserved.
     status = incident.status
     if status in _TERMINAL_STATUSES:
         return EligibilityResult(
@@ -243,7 +293,6 @@ def check_incident_eligibility(
             reason=f"terminal_status_{status.value}",
             status=status.value,
         )
-
     if status not in _ACTIVE_STATUSES:
         return EligibilityResult(
             eligible=False,
@@ -252,34 +301,21 @@ def check_incident_eligibility(
             status=status.value,
         )

-    # Check for suggested checks (required for meaningful evidence collection)
-    # If no suggested checks, we can still write a stop-path packet
-    suggested_checks = getattr(incident, "signals", [])  # Fallback check
+    # Suggested-checks presence: keep the legacy behaviour, sourced
+    # from the aggregate's signal list (the canonical heuristic before
+    # the ACT).
+    suggested_checks = list(getattr(incident, "signals", []) or [])
     has_suggested_checks = len(suggested_checks) > 0

-    # Check automatic loop budget by counting existing review packets
-    # CRITICAL: Use rglob to match artifacts in NESTED paths (e.g., phase4-diagnosis/).
-    # This ensures parity with lab reset helper which also uses rglob.
-    # Bug fix: Previously used iterdir() which only checked top-level,
-    # causing backend to miss nested review packets written by P4c.
-    auto_pass_count = 0
-    if external_analysis_dir is not None and external_analysis_dir.exists():
-        # Count existing automatic review packets for this incident
-        # Pattern: auto-{incident_id}-*-diagnosis-review-packet.json
-        # Use rglob to find in nested dirs (e.g., phase4-diagnosis/p4c-.../)
-        prefix = f"auto-{incident_id}-"
-        suffix = "-diagnosis-review-packet.json"
-        try:
-            for path in external_analysis_dir.rglob("*"):
-                if path.is_file() and path.name.startswith(prefix) and path.name.endswith(suffix):
-                    auto_pass_count += 1
-        except OSError:
-            pass  # Ignore filesystem errors during budget check
+    # Per-incident budget: count existing automatic review packets.
+    auto_pass_count = _count_automatic_review_packets(
+        incident_id=incident_id,
+        external_analysis_dir=external_analysis_dir,
+    )

-    # Build budget diagnostics for the response
     budget_limit = config.max_passes_per_incident
     budget_remaining = max(0, budget_limit - auto_pass_count)
-    budget_diagnostics = (
+    budget_diagnostics: tuple[DiagnosisBudgetDiagnostic, ...] = (
         DiagnosisBudgetDiagnostic(
             name="review_packet_budget",
             used=auto_pass_count,
@@ -311,3 +347,38 @@ def check_incident_eligibility(
         auto_pass_count=auto_pass_count,
         budget_diagnostics=budget_diagnostics,
     )
+
+
+def check_incident_eligibility(
+    *,
+    incident_id: str,
+    config: AutomaticDiagnosisLoopConfig,
+    external_analysis_dir: Path | None = None,
+) -> EligibilityResult:
+    """Resolve an incident from the local store and delegate to the evaluator.
+
+    Compatibility wrapper. ``_process_incident()`` MUST NOT call this
+    function after it has already received a typed :class:`Incident`
+    from :class:`BackendIncidentFound`; the scheduler-side processor
+    must use :func:`evaluate_incident_eligibility` directly with the
+    aggregate.
+
+    This wrapper is retained only for local-mode callers and tests
+    that exercise the legacy ID-based path. Authority selection
+    belongs in the dispatch layer; this wrapper does NOT call any
+    backend HTTP client and does NOT attempt to choose between
+    authorities.
+    """
+    store = get_incident_store()
+    incident = store.get_incident(incident_id)
+    if incident is None:
+        return EligibilityResult(
+            eligible=False,
+            incident_id=incident_id,
+            reason="incident_not_found",
+        )
+    return evaluate_incident_eligibility(
+        incident=incident,
+        config=config,
+        external_analysis_dir=external_analysis_dir,
+    )

=== src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_evidence_processor.py ===
diff --git a/src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_evidence_processor.py b/src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_evidence_processor.py
index e36a046f..0f3afb94 100644
--- a/src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_evidence_processor.py
+++ b/src/k8s_diag_agent/collect/incident_diagnosis_auto_loop_evidence_processor.py
@@ -14,7 +14,29 @@ A successful HTTP 200 response cannot be converted into
 ``BackendIncidentNotFound`` by any parser/schema/deserialization/
 identity failure in this seam.

+Authority flow (ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01):
+
+    typed authority lookup
+        ↓
+    BackendIncidentFound
+        ↓
+    identity validation (branded id matches request)
+        ↓
+    evaluate_incident_eligibility(incident=incident_obj, ...)  [no second lookup]
+        ↓
+    case-file construction from the same aggregate
+        ↓
+    diagnosis execution
+        ↓
+    record_diagnosis_loop_{started,failed,completed}(...)  [authority seam]
+
+The processor NEVER reaches ``get_incident_store()`` to re-resolve
+the incident or to record a lifecycle transition. Lifecycle writes
+route through :mod:`incident_diagnosis_authority_seam` which resolves
+the same dispatch configuration the lookup uses.
+
 Suggested by: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01
+R1 follow-up: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
 """

 from __future__ import annotations
@@ -31,10 +53,18 @@ from .incident_automatic_diagnosis_loop import (
     run_automatic_diagnosis_hypothesis_loop,
 )
 from .incident_case_file import build_incident_case_file
-from .incident_diagnosis_auto_loop_config import (
-    AutomaticDiagnosisLoopConfig,
-    check_incident_eligibility,
+from .incident_diagnosis_authority_seam import (
+    LifecycleWriteApplied,
+    LifecycleWriteFailed,
+    LifecycleWriteOutcome,
+    LifecycleWriteRejected,
+    LifecycleWriteSkipped,
+    evaluate_incident_eligibility,
+    record_diagnosis_loop_completed,
+    record_diagnosis_loop_failed,
+    record_diagnosis_loop_started,
 )
+from .incident_diagnosis_auto_loop_config import AutomaticDiagnosisLoopConfig
 from .incident_diagnosis_auto_loop_models import AutoLoopIncidentResult
 from .incident_diagnosis_backend_detail_outcomes import (
     BackendIncidentFound,
@@ -52,8 +82,6 @@ from .incident_diagnosis_loop_runtime import run_policy_enforced_loop_pass
 from .incident_diagnosis_review_packet import write_diagnosis_review_packet
 from .incident_lifecycle import Incident
 from .incident_read_only_check_artifacts import is_safe_run_id
-from .incident_store import IncidentStore
-from .incident_store_provider import get_incident_store

 _logger = logging.getLogger(__name__)

@@ -116,6 +144,34 @@ def _failure_result_from_outcome(
     )


+def _emit_eligibility_evaluated_event(
+    *,
+    incident_id: str,
+    incident_source: str,
+    eligible: bool,
+    reason_code: str,
+) -> None:
+    """Emit a bounded eligibility-evaluated event after the lookup seam."""
+    _logger.info(
+        "automatic-diagnosis-incident-eligibility-evaluated",
+        extra={
+            "event": "automatic-diagnosis-incident-eligibility-evaluated",
+            "incident_id": incident_id,
+            "incident_source": incident_source,
+            "eligible": eligible,
+            "reason_code": reason_code,
+        },
+    )
+
+
+def _lifecycle_outcome_is_failure(outcome: LifecycleWriteOutcome) -> bool:
+    """Return True for any non-Applied lifecycle outcome (excluding Skipped)."""
+    return isinstance(
+        outcome,
+        (LifecycleWriteFailed, LifecycleWriteRejected),
+    )
+
+
 def _process_incident(
     incident_id: str,
     external_analysis_dir: Path,
@@ -128,18 +184,28 @@ def _process_incident(
     The backend incident-detail lookup runs through the canonical
     :func:`fetch_backend_incident_for_diagnosis_typed` helper, which
     returns a typed :class:`BackendIncidentLookupOutcome`. The three
-    variants are dispatched exhaustively: a HTTP 404 yields
-    ``BackendIncidentNotFound`` (-> skipped ``incident_not_found``),
-    any other failure yields ``BackendIncidentLookupFailed`` (-> error
-    with the mapped stable reason code), and a successful HTTP 200
-    canonical payload yields ``BackendIncidentFound`` (continuing into
-    domain eligibility).
-
-    Crucially, the success/failure classification is anchored on the
-    HTTP status, not on whether the parser produced an incident object;
-    this prevents the historical regression where HTTP 200 + valid JSON
-    was being mapped to ``incident_not_found`` because a downstream
-    parser exception was silently absorbed into ``None``.
+    variants are dispatched exhaustively:
+
+    * ``BackendIncidentNotFound`` → skipped with
+      ``skip_reason="incident_not_found"`` and
+      ``eligibility_reason="not_found"``.
+    * ``BackendIncidentLookupFailed`` → error with the mapped stable
+      reason code; never maps to ``incident_not_found``.
+    * ``BackendIncidentFound(incident=incident)`` → identity check
+      against the requested ID, then the aggregate-based
+      :func:`evaluate_incident_eligibility` (no second incident
+      lookup), then case-file construction from the same aggregate,
+      then authority-routed lifecycle writes.
+
+    Crucially:
+
+    * the eligibility evaluator is invoked with the supplied
+      ``Incident`` aggregate; ``get_incident_store()`` is NOT called
+      between ``BackendIncidentFound`` and the eligibility decision;
+    * lifecycle transitions are routed through
+      :func:`record_diagnosis_loop_*`; the local
+      ``IncidentStore.mark_diagnosis_loop_*`` methods are NOT called
+      from this function.
     """
     branded = IncidentId(incident_id)
     lookup_outcome = fetch_backend_incident_for_diagnosis_typed(branded)
@@ -168,36 +234,63 @@ def _process_incident(
         case BackendIncidentLookupFailed():
             return _failure_result_from_outcome(incident_id, lookup_outcome)
         case BackendIncidentFound(incident=incident):
-            _logger.debug(
+            _logger.info(
                 "automatic-diagnosis-backend-incident-found",
                 extra={
                     "event": "automatic-diagnosis-backend-incident-found",
                     "incident_id": incident_id,
+                    "requested_incident_id": incident_id,
                     "http_status": lookup_outcome.http_status,
                     "payload_schema_version": lookup_outcome.payload_schema_version,
                     "payload_type": lookup_outcome.payload_type,
                 },
             )
-            # ``incident`` is statically known to be ``Incident`` here
-            # (the canonical domain aggregate). We call ``.to_dict()``
-            # directly; there is no duck-typing fallback or ``Any``
-            # widening. The downstream path consumes the dict for the
-            # hypothesis loop, but the case file builder still takes
-            # the typed ``Incident`` so it can keep its typed
-            # invariants.
             incident_obj: Incident = incident
+            incident_source = lookup_outcome.source.value
+
+    # INV-01: identity invariant. The aggregate's incident_id MUST
+    # match the requested branded ID. A mismatch becomes a typed
+    # lookup/content failure (we surface it as an evaluation failure,
+    # not an ``incident_not_found``) and we never silently fall back
+    # to the local store.
+    if str(incident_obj.incident_id) != str(branded):
+        mismatch_detail = (
+            f"backend returned incident_id {str(incident_obj.incident_id)!r} "
+            f"but the request was for {str(branded)!r}"
+        )
+        _logger.warning(
+            "automatic-diagnosis-incident-identity-mismatch",
+            extra={
+                "event": "automatic-diagnosis-incident-identity-mismatch",
+                "incident_id": incident_id,
+                "returned_incident_id": str(incident_obj.incident_id),
+                "reason_code": "identity_mismatch",
+                "detail": mismatch_detail,
+            },
+        )
+        return AutoLoopIncidentResult(
+            incident_id=incident_id,
+            eligible=False,
+            eligibility_reason="backend_incident_identity_mismatch",
+            error=mismatch_detail,
+        )

-    # Normalize to dict for downstream processing.
-    incident_dict: dict[str, Any] = incident_obj.to_dict()
-
-    store: IncidentStore = get_incident_store()
-
-    eligibility = check_incident_eligibility(
-        incident_id=incident_id,
+    # INV-02: aggregate-based eligibility evaluation. The supplied
+    # incident is the authoritative snapshot; we do NOT re-resolve
+    # through ``get_incident_store()`` here.
+    eligibility = evaluate_incident_eligibility(
+        incident=incident_obj,
         config=config,
         external_analysis_dir=external_analysis_dir,
     )

+    _emit_eligibility_evaluated_event(
+        incident_id=incident_id,
+        incident_source=incident_source,
+        eligible=eligibility.eligible,
+        reason_code=eligibility.reason,
+    )
+
     if not eligibility.eligible:
         return AutoLoopIncidentResult(
             incident_id=incident_id,
@@ -211,12 +304,26 @@ def _process_incident(
     run_id = f"auto-{incident_id}-{now.strftime('%Y%m%d%H%M%S')}"

     if not is_safe_run_id(run_id):
-        store.mark_diagnosis_loop_failed(
+        # INV-08: lifecycle failure must not be swallowed. We record
+        # the ``failed`` transition through the seam and surface the
+        # outcome to the caller.
+        lifecycle = record_diagnosis_loop_failed(
             incident_id=incident_id,
             run_id=run_id,
             collector_run_id=collector_run_id,
             unavailable_reason="unsafe_run_id",
         )
+        if isinstance(lifecycle, LifecycleWriteFailed):
+            return AutoLoopIncidentResult(
+                incident_id=incident_id,
+                eligible=True,
+                eligibility_reason=eligibility.reason,
+                run_id=run_id,
+                error=(
+                    f"Unsafe run_id generated: {run_id} "
+                    f"(lifecycle start failed: {lifecycle.reason_code})"
+                ),
+            )
         return AutoLoopIncidentResult(
             incident_id=incident_id,
             eligible=True,
@@ -225,11 +332,24 @@ def _process_incident(
             error=f"Unsafe run_id generated: {run_id}",
         )

-    store.mark_diagnosis_loop_started(
+    # INV-05/INV-08: lifecycle writes are routed through the authority
+    # seam. If the start write fails the diagnosis execution MUST NOT
+    # begin; we return an unsuccessful result with the bounded
+    # reason code.
+    started_outcome = record_diagnosis_loop_started(
         incident_id=incident_id,
         run_id=run_id,
         collector_run_id=collector_run_id,
     )
+    if not isinstance(started_outcome, LifecycleWriteApplied):
+        failure_code = _lifecycle_failure_code(started_outcome)
+        return AutoLoopIncidentResult(
+            incident_id=incident_id,
+            eligible=True,
+            eligibility_reason=eligibility.reason,
+            run_id=run_id,
+            error=f"diagnosis_lifecycle_start_failed: {failure_code}",
+        )

     # Build case file using the original Incident object
     try:
@@ -238,8 +358,11 @@ def _process_incident(
             external_analysis_dir=external_analysis_dir,
             incident=incident_obj,
         )
-    except (OSError, ValueError, KeyError):
-        store.mark_diagnosis_loop_failed(
+    except (OSError, ValueError, KeyError) as exc:
+        # INV-08: keep the original failure primary and attach the
+        # lifecycle-recording diagnostics when the ``failed`` write
+        # itself did not land.
+        lifecycle_outcome = _record_failure_with_original(
             incident_id=incident_id,
             run_id=run_id,
             collector_run_id=collector_run_id,
@@ -250,11 +373,14 @@ def _process_incident(
             eligible=True,
             eligibility_reason=eligibility.reason,
             run_id=run_id,
-            error="Failed to build case file",
+            error=_augment_error_with_lifecycle(
+                f"Failed to build case file: {type(exc).__name__}",
+                lifecycle_outcome,
+            ),
         )

     if case_file is None:
-        store.mark_diagnosis_loop_failed(
+        lifecycle_outcome = _record_failure_with_original(
             incident_id=incident_id,
             run_id=run_id,
             collector_run_id=collector_run_id,
@@ -265,9 +391,12 @@ def _process_incident(
             eligible=True,
             eligibility_reason=eligibility.reason,
             run_id=run_id,
-            error="Case file is None",
+            error=_augment_error_with_lifecycle(
+                "Case file is None", lifecycle_outcome
+            ),
         )

+
     # Run hypothesis burst multipass loop
     hypothesis_loop_result: dict[str, Any] | None = None
     try:
@@ -280,7 +409,7 @@ def _process_incident(
         )

         loop_result = run_automatic_diagnosis_hypothesis_loop(
-            incident=incident_dict,
+            incident=incident_obj.to_dict(),
             case_file=case_file,
             external_analysis_dir=external_analysis_dir,
             run_id=run_id,
@@ -312,8 +441,8 @@ def _process_incident(
             run_id=run_id,
             now=now,
         )
-    except (ValueError, RuntimeError, KeyError):
-        store.mark_diagnosis_loop_failed(
+    except (ValueError, RuntimeError, KeyError) as exc:
+        lifecycle_outcome = _record_failure_with_original(
             incident_id=incident_id,
             run_id=run_id,
             collector_run_id=collector_run_id,
@@ -324,9 +453,13 @@ def _process_incident(
             eligible=True,
             eligibility_reason=eligibility.reason,
             run_id=run_id,
-            error="Orchestrator error",
+            error=_augment_error_with_lifecycle(
+                f"orchestrator error: {type(exc).__name__}",
+                lifecycle_outcome,
+            ),
         )

+
     decision = str(orchestrator_result.get("decision", ""))
     runner_result = orchestrator_result.get("runner_result")
     artifact = orchestrator_result.get("artifact")
@@ -380,7 +513,7 @@ def _process_incident(
         except (OSError, ValueError):
             pass

-    store.mark_diagnosis_loop_completed(
+    completed_outcome = record_diagnosis_loop_completed(
         incident_id=incident_id,
         run_id=run_id,
         collector_run_id=collector_run_id,
@@ -402,7 +535,7 @@ def _process_incident(
         and loop_pass_artifact.get("written", False)
     )

-    return AutoLoopIncidentResult(
+    result = AutoLoopIncidentResult(
         incident_id=incident_id,
         eligible=True,
         eligibility_reason=eligibility.reason,
@@ -418,6 +551,69 @@ def _process_incident(
         loop_pass_artifact_written=loop_pass_artifact_written,
         hypothesis_loop_result=hypothesis_loop_result,
     )
+    if not isinstance(completed_outcome, LifecycleWriteApplied):
+        result.error = (
+            f"diagnosis_lifecycle_completion_failed: "
+            f"{_lifecycle_failure_code(completed_outcome)}"
+        )
+    return result
+
+
+def _lifecycle_failure_code(outcome: LifecycleWriteOutcome) -> str:
+    """Extract a stable reason code from any non-Applied lifecycle outcome."""
+    if isinstance(outcome, LifecycleWriteFailed):
+        return outcome.reason_code
+    if isinstance(outcome, LifecycleWriteRejected):
+        return outcome.reason_code
+    if isinstance(outcome, LifecycleWriteSkipped):
+        return f"skipped:{outcome.reason}"
+    return "unknown"
+
+
+def _augment_error_with_lifecycle(
+    base_error: str,
+    lifecycle_outcome: LifecycleWriteOutcome,
+) -> str:
+    """Keep the original failure primary and attach lifecycle diagnostics.
+
+    INV-08: when recording the ``failed`` transition itself did not
+    land (e.g. the backend returned 5xx), the per-incident result must
+    surface both the original failure and the lifecycle-persistence
+    diagnostics rather than discarding the latter into logs only.
+
+    Example produced shape::
+
+        Failed to build case file: KeyError; \
+lifecycle_recording_error=backend_error; http_status=500
+    """
+    if isinstance(lifecycle_outcome, LifecycleWriteApplied | LifecycleWriteSkipped):
+        return base_error
+    parts = [base_error, f"lifecycle_recording_error={lifecycle_outcome.reason_code}"]
+    http_status = getattr(lifecycle_outcome, "http_status", None)
+    if http_status is not None:
+        parts.append(f"http_status={http_status}")
+    return "; ".join(parts)
+
+
+def _record_failure_with_original(
+    *,
+    incident_id: str,
+    run_id: str,
+    collector_run_id: str,
+    unavailable_reason: str,
+) -> LifecycleWriteOutcome:
+    """Record a ``failed`` transition through the authority seam.
+
+
+    Returns the underlying outcome so callers can attach lifecycle
+    persistence diagnostics to the per-incident result when needed.
+    """
+    return record_diagnosis_loop_failed(
+        incident_id=incident_id,
+        run_id=run_id,
+        collector_run_id=collector_run_id,
+        unavailable_reason=unavailable_reason,
+    )


 def _build_minimal_diagnosis_report(
@@ -479,10 +675,18 @@ def _write_loop_summary(
 ) -> dict[str, Any]:
     """Write loop summary artifact."""
     from .incident_automatic_diagnosis_loop import write_summary_artifact as _write_summary_artifact
+    from .incident_diagnosis_authority_run_summary import (
+        summarize_incident_results,
+    )

     artifact_dir = external_analysis_dir / "automatic-diagnosis"
     effective_run_id = run_id if run_id else f"collector-{collector_run_id}"

+    # Authority run-summary accounting (backend lookup / eligibility /
+    # lifecycle-write outcomes + the split-authority regression counter)
+    # derived deterministically from the per-incident results.
+    authority_run_summary = summarize_incident_results(incident_results).to_dict()
+
     return _write_summary_artifact(
         artifact_dir=artifact_dir,
         run_id=effective_run_id,
@@ -502,9 +706,11 @@ def _write_loop_summary(
         incidents_ineligible=incidents_ineligible,
         incidents_with_errors=incidents_with_errors,
         eligibility_schema_version=eligibility_schema_version,
+        authority_run_summary=authority_run_summary,
     )


+
 __all__ = [
     "_process_incident",
     "_build_minimal_diagnosis_report",

=== src/k8s_diag_agent/collect/incident_lifecycle.py ===
diff --git a/src/k8s_diag_agent/collect/incident_lifecycle.py b/src/k8s_diag_agent/collect/incident_lifecycle.py
index e7507b46..09177c60 100644
--- a/src/k8s_diag_agent/collect/incident_lifecycle.py
+++ b/src/k8s_diag_agent/collect/incident_lifecycle.py
@@ -87,6 +87,16 @@ class Incident:
     signal_count: int = 0
     evidence_count: int = 0
     events: list[IncidentEvent] = field(default_factory=list)
+    # Typed diagnosis-loop lifecycle state (R4-4 contract).
+    #
+    # The ``diagnosis_loop`` projection field is written by the canonical
+    # SQLite event writer whenever a ``DIAGNOSIS_LOOP_STARTED`` /
+    # ``DIAGNOSIS_LOOP_COMPLETED`` / ``DIAGNOSIS_LOOP_FAILED`` event is
+    # appended. Storing it on the typed dataclass (instead of relying on
+    # raw JSON passthrough) lets the in-memory cache round-trip the
+    # lifecycle state through ``Incident.from_dict`` so ``store.get_incident``
+    # and detail-page reads expose it without dropping projection data.
+    diagnosis_loop: dict[str, Any] | None = None
     suppressed_reason: str | None = None
     duplicate_of: str | None = None
     resolved_at: datetime | None = None

=== src/k8s_diag_agent/collect/incident_lifecycle_serialization.py ===
diff --git a/src/k8s_diag_agent/collect/incident_lifecycle_serialization.py b/src/k8s_diag_agent/collect/incident_lifecycle_serialization.py
index faa079ce..4cbf5924 100644
--- a/src/k8s_diag_agent/collect/incident_lifecycle_serialization.py
+++ b/src/k8s_diag_agent/collect/incident_lifecycle_serialization.py
@@ -14,6 +14,7 @@ Hard constraints enforced:

 from __future__ import annotations

+from copy import deepcopy
 from datetime import UTC, datetime
 from typing import TYPE_CHECKING, Any

@@ -75,6 +76,18 @@ def incident_to_dict(incident: Any) -> dict[str, Any]:
         "signal_count": incident.signal_count,
         "evidence_count": incident.evidence_count,
         "events": [incident_event_to_dict(e) for e in incident.events],
+        # R4-4: typed diagnosis-loop lifecycle state round-trip.
+        # The field is owned by the SQLite projection; the dataclass
+        # carries it so cache/detail reads can expose it without
+        # dropping projection data.
+        # R5-1: deep-copy the projection dict so mutations on the
+        # serialized payload cannot reach back into the source
+        # aggregate and bypass the canonical event writer.
+        "diagnosis_loop": (
+            deepcopy(incident.diagnosis_loop)
+            if incident.diagnosis_loop is not None
+            else None
+        ),
         "suppressed_reason": incident.suppressed_reason,
         "duplicate_of": incident.duplicate_of,
         "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
@@ -234,6 +247,11 @@ def incident_from_dict(data: dict[str, Any]) -> Any:
         signal_count=data.get("signal_count", len(signals)),
         evidence_count=data.get("evidence_count", len(evidence_links)),
         events=events,
+        # R4-4: typed diagnosis-loop lifecycle state round-trip.
+        # The projection stores ``diagnosis_loop`` as a JSON-compatible
+        # dict; we accept it as-is so the canonical event writer's
+        # projection state can be reconstructed on the typed dataclass.
+        diagnosis_loop=data.get("diagnosis_loop"),
         suppressed_reason=data.get("suppressed_reason"),
         duplicate_of=data.get("duplicate_of"),
         resolved_at=_parse_dt(data.get("resolved_at")),

=== src/k8s_diag_agent/collect/incident_snapshot_helpers.py ===
diff --git a/src/k8s_diag_agent/collect/incident_snapshot_helpers.py b/src/k8s_diag_agent/collect/incident_snapshot_helpers.py
index ddc88920..c04d97f7 100644
--- a/src/k8s_diag_agent/collect/incident_snapshot_helpers.py
+++ b/src/k8s_diag_agent/collect/incident_snapshot_helpers.py
@@ -6,6 +6,7 @@ Extracted from incident_store.py to keep file sizes below LLM-friendly threshold

 from __future__ import annotations

+from copy import deepcopy
 from typing import TYPE_CHECKING

 if TYPE_CHECKING:
@@ -15,7 +16,13 @@ if TYPE_CHECKING:
 def snapshot_incident(incident: Incident) -> Incident:
     """Create a snapshot copy of an incident.

-    This ensures internal mutable lists are not exposed.
+    This ensures internal mutable state is not exposed.
+    ``diagnosis_loop`` is deep-copied because it is a
+    ``dict[str, Any]`` projection field that may legitimately
+    contain nested mutable structures; aliasing would allow
+    callers to bypass the canonical event store and mutate
+    the cached aggregate without a hash-chain entry.
+
     Extracted from IncidentStore to reduce file sizes.
     """
     from .incident_lifecycle import Incident
@@ -40,6 +47,16 @@ def snapshot_incident(incident: Incident) -> Incident:
         signal_count=incident.signal_count,
         evidence_count=incident.evidence_count,
         events=list(incident.events),
+        # R4-4: round-trip the typed diagnosis-loop projection state
+        # so detail reads and snapshots expose lifecycle data.
+        # R5-1: deep-copy the projection dict so mutations on the
+        # returned snapshot cannot reach back into the cached
+        # aggregate and bypass the canonical event writer.
+        diagnosis_loop=(
+            deepcopy(incident.diagnosis_loop)
+            if incident.diagnosis_loop is not None
+            else None
+        ),
         suppressed_reason=incident.suppressed_reason,
         duplicate_of=incident.duplicate_of,
         resolved_at=incident.resolved_at,

=== src/k8s_diag_agent/collect/incident_store_sqlite_context.py ===
diff --git a/src/k8s_diag_agent/collect/incident_store_sqlite_context.py b/src/k8s_diag_agent/collect/incident_store_sqlite_context.py
index 69c3b9a9..37e846e0 100644
--- a/src/k8s_diag_agent/collect/incident_store_sqlite_context.py
+++ b/src/k8s_diag_agent/collect/incident_store_sqlite_context.py
@@ -23,7 +23,9 @@ Usage:

 from __future__ import annotations

-from datetime import datetime
+import json
+import sqlite3
+from datetime import UTC, datetime
 from typing import TYPE_CHECKING, Any

 from .incident_lifecycle import Incident
@@ -308,6 +310,220 @@ class SQLiteWriteContext:
         self._ensure_open()
         return _rebuild(self._conn)

+    # -------------------------------------------------------------------------
+    # Diagnosis-loop Lifecycle Authority (R3 canonical atomic operation)
+    # -------------------------------------------------------------------------
+
+    def apply_diagnosis_lifecycle_idempotently(
+        self,
+        *,
+        transition: str,
+        incident_id: str,
+        run_id: str | None,
+        collector_run_id: str,
+        diagnosis_run_id: str | None,
+        fingerprint: str,
+        occurred_at: datetime,
+        payload: dict[str, Any],
+    ) -> dict[str, Any]:
+        """Atomically apply a diagnosis-loop lifecycle transition.
+
+        R3 canonical path for the internal
+        ``diagnosis-loop-transition`` endpoint. This method owns the
+        full ``lookup → hash-chained event append → canonical
+        projection update → idempotency record insert`` sequence in
+        one ``BEGIN IMMEDIATE`` transaction, then commits and
+        refreshes the in-memory cache from the canonical projector.
+
+        Returns one of:
+
+        * ``{"outcome": "applied", "idempotent_replay": False,
+            "incident": Incident | None}``
+        * ``{"outcome": "applied", "idempotent_replay": True}``
+        * ``{"outcome": "replay_mismatch"}``
+        * ``{"outcome": "incident_not_found"}``
+
+        The caller is responsible for translating any raised
+        exception into the ``persistence_failed`` outcome.
+
+        Raises:
+            ContextClosedError: If the context has been closed.
+            ValueError: If ``transition`` is not one of
+                ``started`` / ``failed`` / ``completed``.
+            sqlite3.DatabaseError: On any SQL failure (the
+                transaction is rolled back before the exception
+                propagates).
+        """
+        self._ensure_open()
+        from .incident_store_sqlite_events_writer import (
+            EventAppendSpec,
+            _append_event_in_transaction,
+        )
+
+        if transition not in _DIAGNOSIS_LIFECYCLE_EVENT_TYPE:
+            raise ValueError(f"unsupported transition: {transition!r}")
+        event_type = _DIAGNOSIS_LIFECYCLE_EVENT_TYPE[transition]
+
+        event_payload = _build_diagnosis_lifecycle_payload(
+            transition=transition,
+            run_id=run_id,
+            collector_run_id=collector_run_id,
+            payload=payload,
+        )
+
+        cursor = self._conn.cursor()
+        cursor.execute("BEGIN IMMEDIATE")
+        try:
+            # 1. Idempotency lookup BEFORE applying the transition.
+            existing_fp, _applied_at = _select_lifecycle_idempotency_row(
+                cursor,
+                incident_id=incident_id,
+                transition=transition,
+                collector_run_id=collector_run_id,
+                diagnosis_run_id=diagnosis_run_id,
+            )
+            if existing_fp is not None:
+                if existing_fp != fingerprint:
+                    self._conn.rollback()
+                    return {"outcome": "replay_mismatch"}
+                # Commit the (empty) write transaction before refreshing
+                # the cache so the local view matches the durable state
+                # observed by any other process that runs against the
+                # same database file.
+                self._conn.commit()
+                # R4-3: idempotent replay must heal this process's
+                # in-memory cache so a stale local view cannot overrule
+                # the canonical projection. ``BEGIN IMMEDIATE`` only
+                # serializes writers across processes; it cannot make
+                # ``self._cache`` authoritative. Refresh from the
+                # projection row that the previous apply already
+                # wrote so this process sees the same lifecycle state
+                # as the durable record.
+                self._refresh_cache_from_projection(incident_id)
+                return {"outcome": "applied", "idempotent_replay": True}
+
+            # 2. Confirm the incident exists in the canonical
+            #    projection, NOT in the process-local cache.
+            #
+            #    R4-1 contract: ``self._cache`` is a per-process
+            #    Python dict; it cannot prove absence across
+            #    processes. A request landing on a store whose cache
+            #    was loaded before another process promoted the
+            #    incident would otherwise short-circuit to
+            #    ``incident_not_found`` and leave the durable
+            #    projection untouched, silently dropping the
+            #    lifecycle request.
+            #
+            #    ``SELECT 1`` against ``incident_current`` runs in
+            #    the same ``BEGIN IMMEDIATE`` transaction so the
+            #    existence check observes the same write-time view
+            #    as the event/projection/idempotency writes that
+            #    follow.
+            cursor.execute(
+                """
+                SELECT 1
+                FROM incident_current
+                WHERE incident_id = ?
+                """,
+                (incident_id,),
+            )
+            if cursor.fetchone() is None:
+                self._conn.rollback()
+                return {"outcome": "incident_not_found"}
+
+            # 3. Append the canonical event with the hash chain.
+            #    ``_append_event_in_transaction`` does NOT open its
+            #    own ``BEGIN IMMEDIATE``; it reuses our cursor so
+            #    the event insert + projection update commit
+            #    atomically with the idempotency record below.
+            _append_event_in_transaction(
+                cursor,
+                EventAppendSpec(
+                    incident_id=incident_id,
+                    event_type=event_type,
+                    actor=IncidentEventActor.SYSTEM,
+                    payload=event_payload,
+                    occurred_at=occurred_at,
+                ),
+            )
+
+            # 4. Insert the idempotency record. A fault here MUST
+            #    roll back the event insert above. The helper is a
+            #    module-level function so the rollback-on-idempotency
+            #    failure test can patch it cleanly.
+            _insert_lifecycle_idempotency_row(
+                cursor,
+                incident_id=incident_id,
+                transition=transition,
+                collector_run_id=collector_run_id,
+                diagnosis_run_id=diagnosis_run_id,
+                fingerprint=fingerprint,
+                occurred_at=occurred_at,
+            )
+
+            # 5. Commit. After this point the event + projection +
+            #    idempotency row are durable.
+            self._conn.commit()
+        except Exception:
+            try:
+                self._conn.rollback()
+            except sqlite3.Error:
+                pass
+            raise
+
+        # 6. Refresh the in-memory cache from the canonical
+        #    projector row. The previous lifecycle write methods
+        #    refreshed the cache directly, but the new canonical
+        #    path lets the projector (the source of truth for the
+        #    cache) own the update so the in-memory aggregate and
+        #    the on-disk ``incident_current`` row cannot diverge.
+        self._refresh_cache_from_projection(incident_id)
+
+        return {
+            "outcome": "applied",
+            "idempotent_replay": False,
+            "incident": self._cache.get(incident_id),
+        }
+
+    def _refresh_cache_from_projection(self, incident_id: str) -> None:
+        """Reload the in-memory cache entry from ``incident_current``.
+
+        Called after the canonical lifecycle apply commits so the
+        cache reflects the projection row that the canonical event
+        writer just updated. This keeps the cache authoritative
+        without requiring the caller to manually rebuild the
+        aggregate.
+
+        Raises:
+            ContextClosedError: If the context has been closed.
+        """
+        self._ensure_open()
+        cursor = self._conn.execute(
+            """
+            SELECT current_state_json, last_event_seq
+            FROM incident_current
+            WHERE incident_id = ?
+            """,
+            (incident_id,),
+        )
+        row = cursor.fetchone()
+        if row is None:
+            # No projection row means the event writer did not
+            # insert one (which would be a bug elsewhere). Leave
+            # the cache untouched.
+            return
+        current_json = row[0]
+        try:
+            state = json.loads(current_json) if current_json else {}
+        except (TypeError, ValueError):
+            _logger.warning(
+                "Failed to deserialize incident_current JSON for %s",
+                incident_id,
+            )
+            return
+        incident = self._store._state_to_incident(state)
+        self._cache[incident_id] = incident
+
     # -------------------------------------------------------------------------
     # Context Lifetime
     # -------------------------------------------------------------------------
@@ -418,9 +634,157 @@ class SQLiteReadContext:
         return self._closed


+# =============================================================================
+# Canonical Lifecycle Idempotency Helpers
+# =============================================================================
+
+
+# Mapping from the diagnosis-loop-transition endpoint ``transition``
+# string to the canonical event type used by the events writer. The
+# mapping is intentionally module-level so the lookup is identical for
+# in-memory and SQLite-backed stores.
+_DIAGNOSIS_LIFECYCLE_EVENT_TYPE: dict[str, IncidentEventType] = {
+    "started": IncidentEventType.DIAGNOSIS_LOOP_STARTED,
+    "failed": IncidentEventType.DIAGNOSIS_LOOP_FAILED,
+    "completed": IncidentEventType.DIAGNOSIS_LOOP_COMPLETED,
+}
+
+
+def _build_diagnosis_lifecycle_payload(
+    *,
+    transition: str,
+    run_id: str | None,
+    collector_run_id: str | None,
+    payload: dict[str, Any],
+) -> dict[str, Any]:
+    """Project the diagnosis-loop request payload onto the canonical event payload.
+
+    The shape mirrors the helpers in
+    :mod:`incident_store_sqlite_lifecycle` so events appended through
+    the lifecycle idempotency path are indistinguishable from events
+    appended through the in-process lifecycle methods. That is what
+    keeps the canonical projector
+    (:func:`incident_store_sqlite_projection.apply_event_to_state`)
+    working without an environment-specific branch.
+    """
+    if transition == "started":
+        return {
+            "run_id": run_id or "",
+            "collector_run_id": collector_run_id or "",
+        }
+    if transition == "failed":
+        return {
+            "run_id": run_id or "",
+            "collector_run_id": collector_run_id or "",
+            "unavailable_reason": payload.get("unavailable_reason") or None,
+        }
+    if transition == "completed":
+        return {
+            "run_id": run_id or "",
+            "collector_run_id": collector_run_id or "",
+            "review_packet_name": (
+                str(payload["review_packet_name"])
+                if payload.get("review_packet_name") is not None
+                else None
+            ),
+            "checks_requested": int(payload.get("checks_requested", 0) or 0),
+            "checks_run": int(payload.get("checks_run", 0) or 0),
+            "checks_rejected": int(payload.get("checks_rejected", 0) or 0),
+            "decision": (
+                str(payload["decision"])
+                if payload.get("decision") is not None
+                else None
+            ),
+        }
+    raise ValueError(f"unsupported transition: {transition!r}")
+
+
+def _select_lifecycle_idempotency_row(
+    cursor: sqlite3.Cursor,
+    *,
+    incident_id: str,
+    transition: str,
+    collector_run_id: str,
+    diagnosis_run_id: str | None,
+) -> tuple[str | None, str | None]:
+    """Return ``(fingerprint, applied_at)`` for the key, or ``(None, None)``.
+
+    The lookup uses ``COALESCE(diagnosis_run_id, '') = ?`` so the
+    comparison matches the unique index expression (see
+    :data:`incident_store_sqlite_schema.CREATE_LIFECYCLE_IDEMPOTENCY_INDICES`).
+    Without that, a row whose ``diagnosis_run_id`` is NULL would never
+    be matched and the index would still treat NULL as distinct.
+    """
+    cursor.execute(
+        """
+        SELECT fingerprint, applied_at
+        FROM lifecycle_idempotency
+        WHERE incident_id = ?
+          AND transition = ?
+          AND collector_run_id = ?
+          AND COALESCE(diagnosis_run_id, '') = ?
+        """,
+        (
+            incident_id,
+            transition,
+            collector_run_id,
+            diagnosis_run_id or "",
+        ),
+    )
+    row = cursor.fetchone()
+    if row is None:
+        return (None, None)
+    return (str(row[0]), str(row[1]))
+
+
+def _insert_lifecycle_idempotency_row(
+    cursor: sqlite3.Cursor,
+    *,
+    incident_id: str,
+    transition: str,
+    collector_run_id: str,
+    diagnosis_run_id: str | None,
+    fingerprint: str,
+    occurred_at: datetime,
+) -> None:
+    """Insert one idempotency row inside an existing transaction cursor.
+
+    No ``BEGIN`` / ``COMMIT`` is performed here. The caller owns the
+    transaction. A unique-index conflict is surfaced as
+    ``sqlite3.IntegrityError``; the caller catches it and translates
+    it into the bounded ``replay_mismatch`` outcome when the
+    fingerprint differs.
+
+    This helper is a separate function (rather than inlined inside
+    :meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`)
+    so the rollback-on-idempotency-failure test can inject a fault
+    here without monkey-patching the connection layer.
+    """
+    cursor.execute(
+        """
+        INSERT INTO lifecycle_idempotency (
+            incident_id, transition, collector_run_id, diagnosis_run_id,
+            fingerprint, occurred_at, applied_at
+        ) VALUES (?, ?, ?, ?, ?, ?, ?)
+        """,
+        (
+            incident_id,
+            transition,
+            collector_run_id,
+            diagnosis_run_id,
+            fingerprint,
+            occurred_at.isoformat(),
+            datetime.now(UTC).isoformat(),
+        ),
+    )
+
+
+
+
 __all__ = [
     "SQLiteWriteContext",
     "SQLiteReadContext",
     "ContextClosedError",
     "ContextNotOpenError",
+    # apply_diagnosis_lifecycle_idempotently is a method on SQLiteWriteContext.
 ]

=== src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle.py ===
diff --git a/src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle.py b/src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle.py
index a5789f9d..386bff3d 100644
--- a/src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle.py
+++ b/src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle.py
@@ -400,6 +400,13 @@ def mark_diagnosis_loop_started_impl(
     """Mark diagnosis loop started.

     Thread safety: Uses store._write_context() for thread-safe writes.
+
+    R4-4: After ``append_event`` writes the canonical projection
+    row, refresh the in-memory cache from that row so the returned
+    Incident snapshot carries the typed ``diagnosis_loop`` field
+    rather than the stale pre-apply cache value. The projector is
+    the source of truth for the cache; ``append_event`` only writes
+    to ``incident_current`` and ``incident_events``.
     """
     with store._write_context() as ctx:
         incident = ctx.get_cached_incident(incident_id)
@@ -419,7 +426,13 @@ def mark_diagnosis_loop_started_impl(
             occurred_at=datetime.now(UTC),
         )

-        return ctx.snapshot_incident(incident)
+        # Refresh from the canonical projection so the returned
+        # Incident exposes the typed ``diagnosis_loop`` state.
+        ctx._refresh_cache_from_projection(incident_id)
+        refreshed = ctx.get_cached_incident(incident_id)
+        if refreshed is None:
+            return ctx.snapshot_incident(incident)
+        return ctx.snapshot_incident(refreshed)


 def mark_diagnosis_loop_completed_impl(
@@ -436,6 +449,10 @@ def mark_diagnosis_loop_completed_impl(
     """Mark diagnosis loop completed.

     Thread safety: Uses store._write_context() for thread-safe writes.
+
+    R4-4: refresh the cache from the canonical projection after
+    ``append_event`` so the returned Incident carries the typed
+    ``diagnosis_loop`` field.
     """
     with store._write_context() as ctx:
         incident = ctx.get_cached_incident(incident_id)
@@ -460,7 +477,13 @@ def mark_diagnosis_loop_completed_impl(
             occurred_at=datetime.now(UTC),
         )

-        return ctx.snapshot_incident(incident)
+        # Refresh from the canonical projection so the returned
+        # Incident exposes the typed ``diagnosis_loop`` state.
+        ctx._refresh_cache_from_projection(incident_id)
+        refreshed = ctx.get_cached_incident(incident_id)
+        if refreshed is None:
+            return ctx.snapshot_incident(incident)
+        return ctx.snapshot_incident(refreshed)


 def mark_diagnosis_loop_failed_impl(
@@ -473,6 +496,10 @@ def mark_diagnosis_loop_failed_impl(
     """Mark diagnosis loop failed.

     Thread safety: Uses store._write_context() for thread-safe writes.
+
+    R4-4: refresh the cache from the canonical projection after
+    ``append_event`` so the returned Incident carries the typed
+    ``diagnosis_loop`` field.
     """
     with store._write_context() as ctx:
         incident = ctx.get_cached_incident(incident_id)
@@ -493,7 +520,13 @@ def mark_diagnosis_loop_failed_impl(
             occurred_at=datetime.now(UTC),
         )

-        return ctx.snapshot_incident(incident)
+        # Refresh from the canonical projection so the returned
+        # Incident exposes the typed ``diagnosis_loop`` state.
+        ctx._refresh_cache_from_projection(incident_id)
+        refreshed = ctx.get_cached_incident(incident_id)
+        if refreshed is None:
+            return ctx.snapshot_incident(incident)
+        return ctx.snapshot_incident(refreshed)


 __all__ = [

=== src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle_idempotency.py ===
diff --git a/src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle_idempotency.py b/src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle_idempotency.py
new file mode 100644
index 00000000..ea0caf43
--- /dev/null
+++ b/src/k8s_diag_agent/collect/incident_store_sqlite_lifecycle_idempotency.py
@@ -0,0 +1,103 @@
+"""SQLite-backed adapter for the diagnosis-loop lifecycle idempotency contract.
+
+R3 ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01: this module is
+now a thin adapter. The durable critical section lives on
+:class:`k8s_diag_agent.collect.incident_store_sqlite_context.SQLiteWriteContext`
+as :meth:`apply_diagnosis_lifecycle_idempotently`. That single canonical
+method owns:
+
+* ``BEGIN IMMEDIATE`` writer serialization,
+* the idempotency lookup,
+* the canonical hash-chained event append,
+* the canonical ``incident_current`` projection update,
+* the idempotency record insert,
+* the commit,
+* the in-memory cache refresh.
+
+This module only:
+
+1. Resolves ``diagnosis_run_id`` from the request payload,
+2. Opens the store's write context (in-process lock + connection),
+3. Delegates to the canonical context method,
+4. Translates any raised exception into the bounded
+   ``persistence_failed`` outcome that the upper layer (HTTP
+   handler / dispatch) expects.
+
+It MUST NOT reach into ``store._write_lock``, ``store._connect()``,
+``store._incidents``, ``store._snapshot_incident()``, or
+``store._state_to_incident()`` directly. All authority flows through
+the canonical write context so the hash chain, projection, and cache
+cannot drift.
+"""
+
+from __future__ import annotations
+
+import logging
+from datetime import datetime
+from typing import TYPE_CHECKING, Any
+
+if TYPE_CHECKING:
+    from .incident_store_sqlite import SQLiteIncidentStore
+
+_logger = logging.getLogger(__name__)
+
+
+def apply_lifecycle_transition_atomic(
+    store: SQLiteIncidentStore,
+    *,
+    transition: str,
+    incident_id: str,
+    run_id: str | None,
+    collector_run_id: str,
+    fingerprint: str,
+    occurred_at: datetime,
+    payload: dict[str, Any],
+) -> dict[str, Any]:
+    """Apply a lifecycle transition atomically with the idempotency record.
+
+    Returns one of:
+
+    * ``{"outcome": "applied", "idempotent_replay": False,
+        "incident": Incident | None}``
+    * ``{"outcome": "applied", "idempotent_replay": True}``
+    * ``{"outcome": "replay_mismatch"}``
+    * ``{"outcome": "incident_not_found"}``
+    * ``{"outcome": "persistence_failed",
+        "exception_type": str, "detail": str}``
+
+    Implementation note: the canonical path is owned by
+    :meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`.
+    This function is the SQLite entry point for the upper-layer
+    ``apply_transition_idempotently`` dispatch in
+    :mod:`k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_idempotency`.
+    """
+    diagnosis_run_id_raw = payload.get("diagnosis_run_id")
+    diagnosis_run_id: str | None = (
+        diagnosis_run_id_raw if isinstance(diagnosis_run_id_raw, str) else None
+    )
+    if diagnosis_run_id is None:
+        diagnosis_run_id = run_id
+
+    try:
+        with store._write_context() as ctx:
+            return ctx.apply_diagnosis_lifecycle_idempotently(
+                transition=transition,
+                incident_id=incident_id,
+                run_id=run_id,
+                collector_run_id=collector_run_id,
+                diagnosis_run_id=diagnosis_run_id,
+                fingerprint=fingerprint,
+                occurred_at=occurred_at,
+                payload=dict(payload),
+            )
+    except Exception as exc:  # noqa: BLE001 - boundary translation
+        return {
+            "outcome": "persistence_failed",
+            "exception_type": type(exc).__name__,
+            "detail": f"sqlite store raised {type(exc).__name__}: {exc}",
+        }
+
+
+__all__ = [
+    "apply_lifecycle_transition_atomic",
+]
\ No newline at end of file

=== src/k8s_diag_agent/collect/incident_store_sqlite_migrations.py ===
diff --git a/src/k8s_diag_agent/collect/incident_store_sqlite_migrations.py b/src/k8s_diag_agent/collect/incident_store_sqlite_migrations.py
index 607e808c..f9de053c 100644
--- a/src/k8s_diag_agent/collect/incident_store_sqlite_migrations.py
+++ b/src/k8s_diag_agent/collect/incident_store_sqlite_migrations.py
@@ -19,6 +19,8 @@ from datetime import UTC, datetime
 from typing import Any

 from .incident_store_sqlite_schema import (
+    CREATE_LIFECYCLE_IDEMPOTENCY,
+    CREATE_LIFECYCLE_IDEMPOTENCY_INDICES,
     SCHEMA_VERSION,
     get_schema_sql,
 )
@@ -28,11 +30,25 @@ from .incident_store_sqlite_schema import (
 _logger = logging.getLogger(__name__)


-# Migration definitions - each tuple is (version, upgrade_sql_list)
-# version 1 is the initial schema (defined in schema module)
+# Migration definitions - each tuple is (version, upgrade_sql_list).
+#
+# Version 1: Initial schema (created by ``get_schema_sql()``).
+# Version 2: Adds the ``lifecycle_idempotency`` table + UNIQUE index so
+# existing v1 production databases can be upgraded in place. Without
+# this entry, a v1 database would crash on the first
+# ``diagnosis-loop-transition`` request with
+# ``sqlite3.OperationalError: no such table: lifecycle_idempotency``.
+#
+# The SQL uses ``IF NOT EXISTS`` so applying it on a fresh database
+# (which already has the table from ``get_schema_sql()``) is a no-op.
 MIGRATIONS: list[tuple[int, list[str]]] = [
-    # Version 1: Initial schema (created by get_schema_sql())
-    # No additional migrations needed at this time
+    (
+        2,
+        [
+            CREATE_LIFECYCLE_IDEMPOTENCY,
+            CREATE_LIFECYCLE_IDEMPOTENCY_INDICES,
+        ],
+    ),
 ]



=== src/k8s_diag_agent/collect/incident_store_sqlite_schema.py ===
diff --git a/src/k8s_diag_agent/collect/incident_store_sqlite_schema.py b/src/k8s_diag_agent/collect/incident_store_sqlite_schema.py
index 486e46b0..c125dc27 100644
--- a/src/k8s_diag_agent/collect/incident_store_sqlite_schema.py
+++ b/src/k8s_diag_agent/collect/incident_store_sqlite_schema.py
@@ -20,7 +20,15 @@ from typing import Any
 # Schema Version
 # =============================================================================

-SCHEMA_VERSION = 1
+# Schema version 2 introduced the ``lifecycle_idempotency`` table +
+# UNIQUE index for the internal ``diagnosis-loop-transition`` endpoint.
+#
+# The version bump is required because the production backend can ship
+# with an existing v1 database that does NOT have the table. The
+# :mod:`incident_store_sqlite_migrations` module applies the v2 upgrade
+# to bring the database forward so the durable critical section does
+# not crash on the first lifecycle request after the upgrade.
+SCHEMA_VERSION = 2

 # =============================================================================
 # SQL Statements
@@ -110,6 +118,55 @@ CREATE INDEX IF NOT EXISTS idx_incident_current_active_diagnosis_scan
     WHERE status IN ('open', 'collecting_evidence', 'investigating', 'ready_for_review');
 """

+# Lifecycle idempotency registry: durable dedupe across processes and restarts.
+#
+# Each row records one accepted (key, fingerprint) pair for the
+# internal ``diagnosis-loop-transition`` endpoint. The composite
+# UNIQUE index makes ``INSERT OR IGNORE`` the canonical atomic
+# ``check-then-insert`` primitive: if the row already exists, the
+# mutation MUST NOT run; if it does not, the mutation AND the row
+# insert MUST land in the same ``BEGIN IMMEDIATE`` transaction so
+# crash-restart and multi-process replay converge on a single
+# observable transition.
+#
+# The table is intentionally append-only. Same-key/different-fingerprint
+# replays are surfaced as 409 by application code, never by mutating
+# the existing record.
+CREATE_LIFECYCLE_IDEMPOTENCY = """
+CREATE TABLE IF NOT EXISTS lifecycle_idempotency (
+    id INTEGER PRIMARY KEY AUTOINCREMENT,
+    incident_id TEXT NOT NULL,
+    transition TEXT NOT NULL,
+    collector_run_id TEXT NOT NULL,
+    diagnosis_run_id TEXT,
+    fingerprint TEXT NOT NULL,
+    occurred_at TEXT NOT NULL,
+    applied_at TEXT NOT NULL
+);
+"""
+
+# R3-5: SQLite treats NULL as distinct in UNIQUE constraints, so the
+# bare index ``(..., diagnosis_run_id)`` would allow two otherwise
+# identical rows with ``diagnosis_run_id IS NULL`` to coexist. We use
+# ``COALESCE(diagnosis_run_id, '')`` in the index expression so the
+# NULL value still participates in the uniqueness check, while keeping
+# the column itself nullable for callers that legitimately do not
+# have a run id.
+#
+# Application lookups MUST mirror the index expression
+# (``COALESCE(diagnosis_run_id, '') = ?``) so the comparison matches
+# the indexed key. The ``incident_store_sqlite_context`` module owns
+# the canonical lookup and uses this exact comparison.
+CREATE_LIFECYCLE_IDEMPOTENCY_INDICES = """
+CREATE UNIQUE INDEX IF NOT EXISTS idx_lifecycle_idempotency_key
+    ON lifecycle_idempotency(
+        incident_id,
+        transition,
+        collector_run_id,
+        COALESCE(diagnosis_run_id, '')
+    );
+"""
+
 # Append-only enforcement triggers
 CREATE_TRIGGERS = """
 -- Prevent UPDATE on incident_events (append-only)
@@ -134,6 +191,8 @@ INIT_STATEMENTS = [
     CREATE_EVENTS_INDICES,
     CREATE_INCIDENT_CURRENT,
     CREATE_CURRENT_INDICES,
+    CREATE_LIFECYCLE_IDEMPOTENCY,
+    CREATE_LIFECYCLE_IDEMPOTENCY_INDICES,
     CREATE_TRIGGERS,
 ]


=== src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_handler.py ===
diff --git a/src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_handler.py b/src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_handler.py
new file mode 100644
index 00000000..8474d977
--- /dev/null
+++ b/src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_handler.py
@@ -0,0 +1,280 @@
+"""Internal API handler for the diagnosis-loop lifecycle transition endpoint.
+
+The handler applies a bounded diagnosis-loop lifecycle transition
+(``started`` / ``failed`` / ``completed``) to the **backend-owned**
+incident store. The scheduler calls this endpoint over the existing
+internal-API bearer-token channel instead of writing the local
+``IncidentStore`` directly when running in ``backend-api`` mode.
+
+The atomic, idempotent apply-and-record critical section lives in
+:mod:`server_incident_diagnosis_lifecycle_idempotency`; this module is
+the thin HTTP boundary: auth, request parsing, bounded validation, and
+response shaping.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.
+"""
+
+from __future__ import annotations
+
+import json
+import logging
+from datetime import UTC, datetime
+from typing import Any
+
+from .server_incident_diagnosis_lifecycle_idempotency import (
+    apply_transition_idempotently,
+)
+from .server_incident_internal_auth import _validate_internal_token
+
+_logger = logging.getLogger(__name__)
+
+# Lifecycle request/response schema version. Must match the
+# ``LIFECYCLE_SCHEMA_VERSION`` value in
+# ``incident_diagnosis_authority_seam``. Requests carrying a different
+# schema version are rejected with HTTP 400 (unsupported request
+# schema) and a bounded validation message; this contract is aligned
+# with the scheduler-side client translation and the endpoint tests.
+LIFECYCLE_SCHEMA_VERSION: int = 1
+
+# Supported transition values. Keep this list in lock-step with the
+# ``LifecycleTransition`` enum on the scheduler side.
+SUPPORTED_TRANSITIONS: frozenset[str] = frozenset({
+    "started",
+    "failed",
+    "completed",
+})
+
+
+def _send_json(handler: Any, payload: dict[str, Any], status_code: int) -> None:
+    """Emit a JSON response without leaking request bodies or auth tokens."""
+    handler._send_json(payload, status_code)
+
+
+def _read_request_body(handler: Any) -> dict[str, Any] | None:
+    """Parse the JSON request body; return None on malformed input."""
+    try:
+        length = int(handler.headers.get("Content-Length", 0))
+    except (TypeError, ValueError):
+        _send_json(
+            handler,
+            {"error": "Bad Request", "message": "missing Content-Length"},
+            400,
+        )
+        return None
+    if length < 0:
+        _send_json(
+            handler,
+            {"error": "Bad Request", "message": "negative Content-Length"},
+            400,
+        )
+        return None
+    try:
+        raw = handler.rfile.read(length) if length > 0 else b""
+    except OSError as exc:
+        _send_json(
+            handler,
+            {"error": "Bad Request", "message": f"failed to read body: {exc}"},
+            400,
+        )
+        return None
+    if not raw:
+        _send_json(
+            handler,
+            {"error": "Bad Request", "message": "empty request body"},
+            400,
+        )
+        return None
+    try:
+        decoded = json.loads(raw.decode("utf-8"))
+    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
+        _send_json(
+            handler,
+            {
+                "error": "Bad Request",
+                "message": f"invalid JSON: {exc}",
+            },
+            400,
+        )
+        return None
+    if not isinstance(decoded, dict):
+        _send_json(
+            handler,
+            {
+                "error": "Bad Request",
+                "message": "request body must be a JSON object",
+            },
+            400,
+        )
+        return None
+    return decoded
+
+
+def _validate_payload(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
+    """Return ``(normalized, error_message)`` for a parsed request body.
+
+    All field names are intentionally read from the wire-side camelCase
+    to keep the contract aligned with the scheduler-side client. The
+    server-side types and IDs are branded at the boundary.
+    """
+    schema_version = data.get("schemaVersion")
+    if schema_version != LIFECYCLE_SCHEMA_VERSION:
+        return (
+            None,
+            f"unsupported schemaVersion {schema_version!r}; expected {LIFECYCLE_SCHEMA_VERSION}",
+        )
+    incident_id = data.get("incidentId")
+    if not isinstance(incident_id, str) or not incident_id:
+        return (None, "incidentId is required and must be a non-empty string")
+    transition = data.get("transition")
+    if transition not in SUPPORTED_TRANSITIONS:
+        return (
+            None,
+            f"transition must be one of {sorted(SUPPORTED_TRANSITIONS)}; got {transition!r}",
+        )
+    collector_run_id = data.get("collectorRunId")
+    if not isinstance(collector_run_id, str) or not collector_run_id:
+        return (None, "collectorRunId is required and must be a non-empty string")
+    diagnosis_run_id = data.get("diagnosisRunId")
+    if diagnosis_run_id is not None and not isinstance(diagnosis_run_id, str):
+        return (None, "diagnosisRunId must be a string when present")
+    if isinstance(diagnosis_run_id, str) and not diagnosis_run_id:
+        # An empty string is treated as absent; the canonical key uses None.
+        diagnosis_run_id = None
+    occurred_at_str = data.get("occurredAt")
+    if not isinstance(occurred_at_str, str) or not occurred_at_str:
+        return (None, "occurredAt is required and must be an ISO-8601 string")
+    payload = data.get("payload")
+    if payload is None:
+        payload = {}
+    if not isinstance(payload, dict):
+        return (None, "payload must be a JSON object when present")
+    try:
+        occurred_at = datetime.fromisoformat(occurred_at_str)
+    except ValueError:
+        return (None, f"occurredAt is not a valid ISO-8601 timestamp: {occurred_at_str!r}")
+    if occurred_at.tzinfo is None:
+        # Reject naive timestamps; identity is the contract.
+        return (None, "occurredAt must include a timezone offset")
+
+    normalized = {
+        "schemaVersion": int(schema_version),
+        "incidentId": str(incident_id),
+        "transition": str(transition),
+        "collectorRunId": str(collector_run_id),
+        "diagnosisRunId": (
+            str(diagnosis_run_id) if diagnosis_run_id is not None else None
+        ),
+        "occurredAt": occurred_at.astimezone(UTC).isoformat(),
+        "payload": dict(payload),
+    }
+    return (normalized, None)
+
+
+def handle_diagnosis_loop_transition(handler: Any) -> None:
+    """Handle POST /api/internal/incidents/diagnosis-loop-transition.
+
+    The endpoint accepts a single bounded request and applies it to the
+    backend-owned incident store. Idempotent deliveries collapse to a
+    single observable transition; conflicting replays (same key,
+    different payload) are rejected with HTTP 409 and a stable reason
+    code.
+    """
+    if not _validate_internal_token(handler):
+        _send_json(
+            handler,
+            {
+                "error": "Unauthorized",
+                "message": "Valid internal API token required",
+            },
+            401,
+        )
+        return
+
+    raw = _read_request_body(handler)
+    if raw is None:
+        return
+
+    normalized, error_message = _validate_payload(raw)
+    if error_message is not None or normalized is None:
+        _send_json(
+            handler,
+            {"error": "Bad Request", "message": error_message or "invalid request"},
+            400,
+        )
+        return
+
+    applied = apply_transition_idempotently(
+        transition=normalized["transition"],
+        incident_id=normalized["incidentId"],
+        collector_run_id=normalized["collectorRunId"],
+        diagnosis_run_id=normalized["diagnosisRunId"],
+        occurred_at=datetime.fromisoformat(normalized["occurredAt"]),
+        payload=normalized["payload"],
+    )
+
+    if applied["outcome"] == "incident_not_found":
+        _send_json(
+            handler,
+            {
+                "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
+                "type": "incident-diagnosis-loop-transition-result",
+                "applied": False,
+                "reasonCode": "incident_not_found",
+                "incidentId": normalized["incidentId"],
+                "transition": normalized["transition"],
+            },
+            404,
+        )
+        return
+
+    if applied["outcome"] == "replay_mismatch":
+        _send_json(
+            handler,
+            {
+                "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
+                "type": "incident-diagnosis-loop-transition-result",
+                "applied": False,
+                "reasonCode": "transition_replay_mismatch",
+                "incidentId": normalized["incidentId"],
+                "transition": normalized["transition"],
+            },
+            409,
+        )
+        return
+
+    if applied["outcome"] == "persistence_failed":
+        _send_json(
+            handler,
+            {
+                "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
+                "type": "incident-diagnosis-loop-transition-result",
+                "applied": False,
+                "reasonCode": "persistence_failed",
+                "exceptionType": applied.get("exception_type", "Unknown"),
+                "incidentId": normalized["incidentId"],
+                "transition": normalized["transition"],
+            },
+            500,
+        )
+        return
+
+    # applied or idempotent_replay
+    _send_json(
+        handler,
+        {
+            "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
+            "type": "incident-diagnosis-loop-transition-result",
+            "applied": True,
+            "idempotentReplay": bool(applied.get("idempotent_replay", False)),
+            "incidentId": normalized["incidentId"],
+            "transition": normalized["transition"],
+        },
+        200,
+    )
+
+
+__all__ = [
+    "LIFECYCLE_SCHEMA_VERSION",
+    "SUPPORTED_TRANSITIONS",
+    "handle_diagnosis_loop_transition",
+]

=== src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_idempotency.py ===
diff --git a/src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_idempotency.py b/src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_idempotency.py
new file mode 100644
index 00000000..50c8b7dd
--- /dev/null
+++ b/src/k8s_diag_agent/ui/server_incident_diagnosis_lifecycle_idempotency.py
@@ -0,0 +1,335 @@
+"""Atomic, idempotent application of diagnosis-loop lifecycle transitions.
+
+This module owns the authoritative critical section for the internal
+diagnosis-loop lifecycle endpoint. It is deliberately separated from the
+HTTP request/response handler so the idempotency + concurrency contract
+lives in one focused place:
+
+    begin authoritative critical section (per-store lock)
+        ↓
+    look up idempotency key
+        ├─ same key + same fingerprint → return stored result (replay)
+        ├─ same key + different fingerprint → conflict
+        └─ absent → apply transition
+                     persist idempotency record (atomic, non-swallowed)
+        ↓
+    commit / release lock
+
+The idempotency lookup happens **before** the transition is applied,
+the whole operation runs under a lock so two concurrent deliveries
+cannot both apply, a canonical payload fingerprint is stored and
+compared so a same-key/different-payload request is rejected, and the
+idempotency record is written as part of the same critical section as
+the mutation (it is never swallowed as best-effort).
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R1)
+"""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import logging
+import threading
+from datetime import datetime
+from typing import TYPE_CHECKING, Any, cast
+from weakref import WeakKeyDictionary
+
+if TYPE_CHECKING:
+    from ..collect.incident_store_sqlite import SQLiteIncidentStore
+
+_logger = logging.getLogger(__name__)
+
+
+# Same-process lock for the in-memory fallback path. The
+# SQLite-backed critical section lives in
+# :mod:`incident_store_sqlite_lifecycle_idempotency` and serializes
+# across processes via ``BEGIN IMMEDIATE`` instead of this lock;
+# this lock only guards the in-process ``IncidentStore`` path used
+# in tests.
+_IDEMPOTENCY_LOCK = threading.RLock()
+
+# In-memory idempotency registry, keyed to the store instance so
+# each store gets its own clean slate. SQLite-backed stores do NOT
+# use this registry; they delegate to
+# :func:`apply_lifecycle_transition_atomic` which persists the
+# record inside the same transaction as the mutation.
+_STORE_REGISTRIES: WeakKeyDictionary[Any, dict[tuple[Any, ...], dict[str, Any]]] = (
+    WeakKeyDictionary()
+)
+
+
+def _registry_for(store: Any) -> dict[tuple[Any, ...], dict[str, Any]]:
+    """Return the in-memory idempotency registry bound to ``store``.
+
+    Used only for non-SQLite stores (tests). The registry lives and
+    dies with the store instance. Stores that cannot be weakly
+    referenced fall back to an instance attribute so the record
+    still shares the store's lifetime.
+    """
+    try:
+        reg = _STORE_REGISTRIES.get(store)
+        if reg is None:
+            reg = {}
+            _STORE_REGISTRIES[store] = reg
+        return reg
+    except TypeError:
+        reg = getattr(store, "_diag_lifecycle_idempotency", None)
+        if reg is None:
+            reg = {}
+            store._diag_lifecycle_idempotency = reg
+        return reg
+
+
+def _idempotency_key(
+    *,
+    incident_id: str,
+    transition: str,
+    collector_run_id: str,
+    diagnosis_run_id: str | None,
+) -> tuple[Any, ...]:
+    return (incident_id, transition, collector_run_id, diagnosis_run_id)
+
+
+def _payload_fingerprint(payload: dict[str, Any]) -> str:
+    """Compute a canonical fingerprint over the request payload.
+
+    The fingerprint intentionally excludes the delivery timestamp
+    (``occurredAt``) and the identity fields already captured by the
+    idempotency key. It captures the semantic payload (review packet
+    name, check counts, decision, unavailable reason, ...) so a repeat
+    delivery that reuses the identity but changes the payload is
+    detected as a conflict rather than collapsed as a replay.
+    """
+    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
+    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
+
+
+def _is_sqlite_store(store: Any) -> bool:
+    """Return True when ``store`` is a SQLite-backed incident store.
+
+    Detection is by class identity (not duck typing) so a misnamed
+    subclass does not accidentally pick up the SQLite critical
+    section.
+    """
+    from ..collect.incident_store_sqlite import SQLiteIncidentStore
+
+    return isinstance(store, SQLiteIncidentStore)
+
+
+def _apply_transition_to_store(
+    *,
+    store: Any,
+    transition: str,
+    incident_id: str,
+    collector_run_id: str,
+    diagnosis_run_id: str | None,
+    payload: dict[str, Any],
+) -> Any:
+    """Apply the bounded transition to the backend-owned store.
+
+    Returns the updated incident (or ``None`` when the incident is
+    absent). Raises on persistence failure; the caller translates the
+    exception into a ``persistence_failed`` outcome.
+    """
+    run_id = diagnosis_run_id or ""
+    if transition == "started":
+        return store.mark_diagnosis_loop_started(
+            incident_id=incident_id,
+            run_id=run_id,
+            collector_run_id=collector_run_id,
+        )
+    if transition == "failed":
+        return store.mark_diagnosis_loop_failed(
+            incident_id=incident_id,
+            run_id=run_id,
+            collector_run_id=collector_run_id,
+            unavailable_reason=str(payload.get("unavailable_reason", "")) or None,
+        )
+    if transition == "completed":
+        return store.mark_diagnosis_loop_completed(
+            incident_id=incident_id,
+            run_id=run_id,
+            collector_run_id=collector_run_id,
+            review_packet_name=(
+                str(payload["review_packet_name"])
+                if payload.get("review_packet_name") is not None
+                else None
+            ),
+            checks_requested=int(payload.get("checks_requested", 0) or 0),
+            checks_run=int(payload.get("checks_run", 0) or 0),
+            checks_rejected=int(payload.get("checks_rejected", 0) or 0),
+            decision=(
+                str(payload["decision"])
+                if payload.get("decision") is not None
+                else None
+            ),
+        )
+    raise ValueError(f"unsupported transition: {transition!r}")
+
+
+def apply_transition_idempotently(
+    *,
+    transition: str,
+    incident_id: str,
+    collector_run_id: str,
+    diagnosis_run_id: str | None,
+    occurred_at: datetime,
+    payload: dict[str, Any],
+) -> dict[str, Any]:
+    """Apply the transition idempotently to the canonical backend store.
+
+    The complete lookup → apply → record sequence runs under
+    ``_IDEMPOTENCY_LOCK`` so concurrent duplicate deliveries cannot
+    both apply the transition. Returns a ``result`` dict with one of:
+
+    * ``{"outcome": "applied", "idempotent_replay": bool}``
+    * ``{"outcome": "replay_mismatch"}``          (same key, different payload)
+    * ``{"outcome": "incident_not_found"}``
+    * ``{"outcome": "persistence_failed", "exception_type": str, "detail": str}``
+    """
+    from ..collect.incident_store_provider import get_incident_store
+
+    store = get_incident_store()
+    fingerprint = _payload_fingerprint(payload)
+
+    # SQLite-backed stores get the durable critical section: the
+    # mutation AND the idempotency record are written inside the same
+    # ``BEGIN IMMEDIATE`` transaction, so two concurrent backend
+    # processes serialize on the database and the result survives a
+    # crash-restart. This is what makes restart-durable and
+    # multi-process idempotency hold.
+    if _is_sqlite_store(store):
+        from ..collect.incident_store_sqlite_lifecycle_idempotency import (
+            apply_lifecycle_transition_atomic,
+        )
+
+        return apply_lifecycle_transition_atomic(
+            store=cast("SQLiteIncidentStore", store),
+            transition=transition,
+            incident_id=incident_id,
+            run_id=diagnosis_run_id,
+            collector_run_id=collector_run_id,
+            fingerprint=fingerprint,
+            occurred_at=occurred_at,
+            payload=dict(payload),
+        )
+
+    # In-memory / test-only path: same-process lock + per-store
+    # registry. This path is intentionally process-local because the
+    # in-memory store has no shared durable state.
+    key = _idempotency_key(
+        incident_id=incident_id,
+        transition=transition,
+        collector_run_id=collector_run_id,
+        diagnosis_run_id=diagnosis_run_id,
+    )
+    with _IDEMPOTENCY_LOCK:
+        registry = _registry_for(store)
+
+        # 1. Idempotency lookup BEFORE applying the transition.
+        existing = registry.get(key)
+        if existing is not None:
+            if existing.get("fingerprint") != fingerprint:
+                # Same idempotency key, different payload → conflict.
+                return {"outcome": "replay_mismatch"}
+            # Same key + same fingerprint → return the prior outcome
+            # without reapplying the transition.
+            return {"outcome": "applied", "idempotent_replay": True}
+
+        # 2. Absent key → apply the transition.
+        try:
+            updated = _apply_transition_to_store(
+                store=store,
+                transition=transition,
+                incident_id=incident_id,
+                collector_run_id=collector_run_id,
+                diagnosis_run_id=diagnosis_run_id,
+                payload=payload,
+            )
+        except Exception as exc:  # noqa: BLE001 - boundary translation
+            return {
+                "outcome": "persistence_failed",
+                "exception_type": type(exc).__name__,
+                "detail": f"store raised {type(exc).__name__}: {exc}",
+            }
+
+        if updated is None:
+            # Incident absent: do NOT record an idempotency marker so a
+            # later delivery (after the incident exists) can apply.
+            return {"outcome": "incident_not_found"}
+
+        # 3. Persist the idempotency record as part of the same critical
+        #    section as the mutation. This assignment is in-memory and
+        #    cannot silently fail; the record is therefore durable for
+        #    the lifetime of the backend-owned store and atomic with the
+        #    applied transition. It is NOT best-effort.
+        registry[key] = {
+            "fingerprint": fingerprint,
+            "occurred_at": occurred_at.isoformat(),
+            "applied": True,
+        }
+
+        return {"outcome": "applied", "idempotent_replay": False}
+
+
+def _project_lifecycle_event(
+    *,
+    store: Any,
+    incident_id: str,
+    transition: str,
+    collector_run_id: str,
+    diagnosis_run_id: str | None,
+    occurred_at: datetime,
+    payload: dict[str, Any],
+) -> None:
+    """Project an observability-only lifecycle event onto the incident.
+
+    Unlike the idempotency record (which is authoritative and never
+    swallowed), this projection is best-effort and only runs on stores
+    that support ``append_event``.
+    """
+    append_event = getattr(store, "append_event", None)
+    if append_event is None:
+        return
+    try:
+        from ..collect.incident_events import (
+            IncidentEvent,
+            IncidentEventActor,
+            IncidentEventType,
+            make_event_id,
+        )
+
+        incident = store.get_incident(incident_id)
+        if incident is None:
+            return
+        if transition == "completed":
+            event_type = IncidentEventType.REVIEW_PACKET_GENERATED
+        else:
+            event_type = IncidentEventType.STATUS_CHANGED
+        event = IncidentEvent(
+            event_id=make_event_id(incident_id, transition, occurred_at),
+            incident_id=incident_id,
+            event_type=event_type,
+            actor=IncidentEventActor.SYSTEM,
+            occurred_at=occurred_at,
+            message=f"diagnosis-loop {transition}",
+            data={
+                "transition": transition,
+                "collector_run_id": collector_run_id,
+                "diagnosis_run_id": diagnosis_run_id,
+                "payload": dict(payload),
+            },
+        )
+        append_event(incident_id, event)
+    except Exception:  # noqa: BLE001 - projection is observability-only
+        _logger.debug(
+            "lifecycle event projection failed",
+            exc_info=True,
+            extra={"incident_id": incident_id, "transition": transition},
+        )
+
+
+__all__ = [
+    "apply_transition_idempotently",
+]

=== src/k8s_diag_agent/ui/server_routes.py ===
diff --git a/src/k8s_diag_agent/ui/server_routes.py b/src/k8s_diag_agent/ui/server_routes.py
index 9e04a721..fc445883 100644
--- a/src/k8s_diag_agent/ui/server_routes.py
+++ b/src/k8s_diag_agent/ui/server_routes.py
@@ -179,6 +179,7 @@ _INTERNAL_AUTH_EXEMPT_ROUTES: frozenset[str] = frozenset({
     "/api/internal/incidents/promote-candidates",
     "/api/internal/incidents",
     "/api/internal/incidents/list",
+    "/api/internal/incidents/diagnosis-loop-transition",
 })

 # Internal API route patterns (for dynamic paths like /api/internal/incidents/{id})
@@ -271,6 +272,9 @@ def _dispatch_post_route(handler: HealthUIRequestHandler, route: str) -> None:
     from .server_batch_execution import handle_run_batch_next_check_execution
     from .server_feedback import handle_alertmanager_relevance_feedback, handle_usefulness_feedback
     from .server_incident import handle_incident_snapshot_api
+    from .server_incident_diagnosis_lifecycle_handler import (
+        handle_diagnosis_loop_transition,
+    )
     from .server_incident_internal import (
         handle_promote_alert_signals,
         handle_promote_candidates,
@@ -317,6 +321,12 @@ def _dispatch_post_route(handler: HealthUIRequestHandler, route: str) -> None:
         handle_promote_candidates(handler)
         return

+    # Internal: Diagnosis-loop lifecycle transition (started/failed/completed)
+    # POST /api/internal/incidents/diagnosis-loop-transition
+    if route == "/api/internal/incidents/diagnosis-loop-transition":
+        handle_diagnosis_loop_transition(handler)
+        return
+
     # Incident diagnosis loop one-pass
     # POST /api/incidents/{incident_id}/diagnosis-loop/one-pass
     incident_dl_match = _INCIDENT_DIAGNOSIS_LOOP_PATTERN.match(route)

=== tests/unit/authority_seam_support.py ===
diff --git a/tests/unit/authority_seam_support.py b/tests/unit/authority_seam_support.py
new file mode 100644
index 00000000..f9fe078b
--- /dev/null
+++ b/tests/unit/authority_seam_support.py
@@ -0,0 +1,243 @@
+"""Shared helpers for the ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+test modules.
+
+This module is intentionally *not* a ``test_*`` file, so pytest does not
+collect it directly. It hosts the fixtures, canonical builders, and
+minimal handler stand-ins shared between:
+
+* ``test_automatic_diagnosis_authority_seam01.py`` (aggregate evaluator
+  + processor regressions), and
+* ``test_automatic_diagnosis_authority_seam01_endpoint.py`` (lifecycle
+  endpoint + backend dispatch + idempotency/concurrency).
+
+Splitting keeps each test file under the LLM-friendly size threshold
+while sharing a single source of truth for the fixtures.
+"""
+
+from __future__ import annotations
+
+import io
+import json
+import threading
+from collections.abc import Callable, Iterable
+from datetime import UTC, datetime
+from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
+from typing import Any, NoReturn
+
+import pytest
+
+from k8s_diag_agent.collect.incident_diagnosis_backend_detail_parser import (
+    SUPPORTED_PAYLOAD_TYPE,
+    SUPPORTED_SCHEMA_VERSION,
+)
+from k8s_diag_agent.collect.incident_lifecycle import (
+    Incident,
+    IncidentStatus,
+)
+from k8s_diag_agent.collect.incident_store_provider import (
+    set_incident_store,
+)
+
+
+@pytest.fixture(autouse=True)
+def reset_env(monkeypatch: pytest.MonkeyPatch) -> Iterable[None]:
+    """Reset the incident store and env vars between tests.
+
+    Imported (and thereby auto-registered) by each test module.
+    """
+    set_incident_store(None)
+    for var in (
+        "K9B_INCIDENT_PROMOTION_MODE",
+        "K9B_BACKEND_INTERNAL_URL",
+        "K9B_INTERNAL_API_TOKEN",
+        "K9B_INCIDENT_STORE_BACKEND",
+        "K9B_PROCESS_ROLE",
+    ):
+        monkeypatch.delenv(var, raising=False)
+    yield
+    set_incident_store(None)
+
+
+def canonical_incident(
+    incident_id: str = "incident-abc",
+    status: IncidentStatus = IncidentStatus.OPEN,
+) -> Incident:
+    """Build a canonical :class:`Incident` aggregate."""
+    now = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+    return Incident(
+        incident_id=incident_id,
+        source_candidate_id="candidate-xyz",
+        namespace="default",
+        object_kind="Pod",
+        object_name="nginx-pod",
+        raw_object_kind="Pod",
+        candidate_class="health",
+        severity="warning",
+        status=status,
+        first_observed_at=now,
+        last_observed_at=now,
+        signal_count=1,
+        evidence_count=0,
+    )
+
+
+def canonical_payload(incident_id: str = "incident-abc") -> dict[str, Any]:
+    return {
+        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
+        "payload_type": SUPPORTED_PAYLOAD_TYPE,
+        "incident": {
+            "incident_id": incident_id,
+            "source_candidate_id": "candidate-xyz",
+            "namespace": "default",
+            "object_kind": "Pod",
+            "object_name": "nginx-pod",
+            "class": "health",
+            "severity": "warning",
+            "status": IncidentStatus.OPEN.value,
+            "first_observed_at": "2026-07-12T10:00:00+00:00",
+            "last_observed_at": "2026-07-12T10:30:00+00:00",
+            "signal_count": 1,
+            "evidence_count": 0,
+        },
+    }
+
+
+def encode(payload: dict[str, Any]) -> bytes:
+    return json.dumps(payload).encode("utf-8")
+
+
+def never_called(**kwargs: Any) -> Any:  # pragma: no cover - helper
+    raise AssertionError("lifecycle failure should not be reached")
+
+
+class StubEligibility:
+    """Stub eligibility result used by the processor regression tests."""
+
+    def __init__(self, *, eligible: bool, reason: str) -> None:
+        self.eligible = eligible
+        self.reason = reason
+        self.budget_diagnostics: tuple[Any, ...] = ()
+        self.status: str | None = None
+        self.has_suggested_checks: bool = False
+        self.auto_pass_count: int = 0
+
+
+class StubHandler:
+    """Mimics the BaseHTTPRequestHandler surface used by the handler."""
+
+    def __init__(self, payload: dict[str, Any] | None = None, status: int = 200) -> None:
+        self._payload = payload or {}
+        self._status = status
+        self.sent: list[tuple[dict[str, Any], int]] = []
+        self.headers: dict[str, str] = {}
+
+    def _send_json(self, payload: dict[str, Any], status: int) -> None:
+        self.sent.append((payload, status))
+
+
+class BuildHandler:
+    """Minimal stand-in for ``HealthUIRequestHandler`` used by the
+    lifecycle handler. Implements only the surface the handler actually
+    calls: ``headers`` (mapping), ``rfile.read()``, ``_send_json()``."""
+
+    def __init__(
+        self,
+        headers: dict[str, str] | None = None,
+        body: bytes | None = None,
+    ) -> None:
+        self.headers = headers or {}
+        self._body = body or b""
+        # The production handler reads the request body via
+        # ``handler.rfile.read(length)``; back it with a BytesIO so the
+        # endpoint tests exercise the real request-parsing path.
+        self.rfile = io.BytesIO(self._body)
+        self.sent: list[tuple[dict[str, Any], int]] = []
+
+    def _send_json(self, payload: dict[str, Any], status: int) -> None:
+        self.sent.append((payload, status))
+
+
+class RecordingHandler(BaseHTTPRequestHandler):
+    """Minimal HTTP handler that records lifecycle requests.
+
+    When no explicit ``response_body`` override is configured, the
+    handler models a backend that collapses idempotent deliveries: the
+    first delivery for a given identity key reports
+    ``idempotentReplay=false`` and subsequent identical deliveries
+    report ``idempotentReplay=true``. This lets the client-side tests
+    prove they surface backend-reported idempotency.
+    """
+
+    recorded: list[dict[str, Any]] = []
+    status: int = 200
+    response_body: dict[str, Any] | None = None
+    _seen_keys: set[tuple[Any, ...]] = set()
+
+    def log_message(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
+        return
+
+    def do_POST(self) -> None:  # noqa: N802 - HTTP verb
+        length = int(self.headers.get("Content-Length", 0))
+        raw = self.rfile.read(length) if length else b""
+        try:
+            body = json.loads(raw.decode("utf-8"))
+        except Exception:
+            body = {}
+        RecordingHandler.recorded.append(
+            {
+                "path": self.path,
+                "headers": dict(self.headers.items()),
+                "body": body,
+            }
+        )
+        if RecordingHandler.response_body is not None:
+            response = dict(RecordingHandler.response_body)
+        else:
+            key = (
+                body.get("incidentId"),
+                body.get("transition"),
+                body.get("collectorRunId"),
+                body.get("diagnosisRunId"),
+            )
+            replay = key in RecordingHandler._seen_keys
+            RecordingHandler._seen_keys.add(key)
+            response = {
+                "schemaVersion": 1,
+                "applied": True,
+                "idempotentReplay": replay,
+            }
+        body_bytes = json.dumps(response).encode("utf-8")
+        self.send_response(RecordingHandler.status)
+        self.send_header("Content-Type", "application/json")
+        self.send_header("Content-Length", str(len(body_bytes)))
+        self.end_headers()
+        self.wfile.write(body_bytes)
+
+
+def start_backend_server(
+    *,
+    response_status: int = 200,
+    response_body: dict[str, Any] | None = None,
+) -> tuple[ThreadingHTTPServer, str, Callable[[], None]]:
+    """Spin up a localhost HTTP server with a recording handler."""
+    RecordingHandler.recorded.clear()
+    RecordingHandler.status = response_status
+    RecordingHandler.response_body = response_body
+    RecordingHandler._seen_keys = set()
+    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
+    thread = threading.Thread(target=server.serve_forever, daemon=True)
+    thread.start()
+    port = server.server_address[1]
+    base_url = f"http://127.0.0.1:{port}"
+
+    def shutdown() -> None:
+        server.shutdown()
+        server.server_close()
+
+    return server, base_url, shutdown
+
+
+def forbidden_lookup(*args: object, **kwargs: object) -> NoReturn:
+    raise AssertionError(
+        "aggregate evaluator performed an incident lookup (forbidden)"
+    )

=== tests/unit/test_automatic_diagnosis_authority_seam01.py ===
diff --git a/tests/unit/test_automatic_diagnosis_authority_seam01.py b/tests/unit/test_automatic_diagnosis_authority_seam01.py
new file mode 100644
index 00000000..9137bea4
--- /dev/null
+++ b/tests/unit/test_automatic_diagnosis_authority_seam01.py
@@ -0,0 +1,384 @@
+"""Unit tests for ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.
+
+Aggregate-based eligibility, backend not-found / payload-failure
+regressions, single-fetch, local-mode compatibility, and the lifecycle
+outcome contract. The processor regressions live in
+``test_automatic_diagnosis_authority_seam01_processor.py`` and the
+lifecycle endpoint / backend dispatch / idempotency tests live in
+``test_automatic_diagnosis_authority_seam01_endpoint.py``. Verifier
+self-tests live in ``test_automatic_diagnosis_authority_seam01_verifier.py``.
+
+The split-authority defect closed by this ACT was: a backend-fetched
+incident was re-resolved through the **local** incident store for
+eligibility, producing ``not_eligible: incident_not_found`` even though
+the backend returned HTTP 200 with a valid canonical incident.
+"""
+
+from __future__ import annotations
+
+from datetime import UTC, datetime
+from pathlib import Path
+from typing import Any, NoReturn
+
+import pytest
+
+from k8s_diag_agent.collect import (
+    incident_diagnosis_authority_seam as seam_module,
+)
+from k8s_diag_agent.collect.incident_diagnosis_authority_seam import (
+    LIFECYCLE_SCHEMA_VERSION,
+    LifecycleTransition,
+    LifecycleWriteApplied,
+    build_lifecycle_request,
+    check_incident_eligibility,
+    evaluate_incident_eligibility,
+    record_diagnosis_loop_started,
+)
+from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
+    AutomaticDiagnosisLoopConfig,
+)
+from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
+    BackendIncidentFound,
+    BackendIncidentLookupFailed,
+    BackendIncidentLookupFailureCode,
+    BackendIncidentLookupSource,
+    BackendIncidentNotFound,
+)
+from k8s_diag_agent.collect.incident_diagnosis_backend_detail_parser import (
+    SUPPORTED_PAYLOAD_TYPE,
+    SUPPORTED_SCHEMA_VERSION,
+)
+from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
+from k8s_diag_agent.collect.incident_store import IncidentStore
+from k8s_diag_agent.collect.incident_store_provider import set_incident_store
+from k8s_diag_agent.domain.incident_lifecycle import IncidentId
+from k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_handler import (
+    SUPPORTED_TRANSITIONS as HANDLER_SUPPORTED_TRANSITIONS,
+)
+from tests.unit.authority_seam_support import (
+    StubEligibility,
+    canonical_incident,
+    encode,
+    reset_env,
+)
+
+__all__ = ["reset_env"]  # re-export the autouse fixture for collection
+
+
+class TestAggregateEvaluator:
+    def test_eligible_incident_is_evaluated_without_store_access(
+        self, tmp_path: Path
+    ) -> None:
+        config = AutomaticDiagnosisLoopConfig()
+        incident = canonical_incident("incident-eligible")
+        for name in (
+            "get_incident_store",
+            "fetch_backend_incident_for_diagnosis_typed",
+            "fetch_incident_for_diagnosis",
+        ):
+            assert not hasattr(seam_module, name) or callable(
+                getattr(seam_module, name)
+            )
+        result = evaluate_incident_eligibility(incident=incident, config=config)
+        assert result.eligible is True
+        assert result.incident_id == "incident-eligible"
+        assert result.reason == "active_incident_with_suggested_checks"
+        assert result.budget_diagnostics[0].exhausted is False
+
+    def test_terminal_status_returns_terminal_reason(self) -> None:
+        config = AutomaticDiagnosisLoopConfig()
+        incident = canonical_incident("incident-resolved", IncidentStatus.RESOLVED)
+        result = evaluate_incident_eligibility(incident=incident, config=config)
+        assert result.eligible is False
+        assert result.reason == "terminal_status_resolved"
+        assert result.status == "resolved"
+
+    def test_inactive_status_returns_inactive_reason(self) -> None:
+        config = AutomaticDiagnosisLoopConfig()
+        incident = canonical_incident("incident-rfr", IncidentStatus.READY_FOR_REVIEW)
+        result = evaluate_incident_eligibility(incident=incident, config=config)
+        assert result.eligible is False
+        assert result.reason == "terminal_status_ready_for_review"
+
+    def test_suppressed_incident_ineligible(self) -> None:
+        config = AutomaticDiagnosisLoopConfig()
+        incident = canonical_incident("incident-sup", IncidentStatus.SUPPRESSED)
+        result = evaluate_incident_eligibility(incident=incident, config=config)
+        assert result.eligible is False
+        assert "terminal" in result.reason
+
+    def test_duplicate_incident_ineligible(self) -> None:
+        config = AutomaticDiagnosisLoopConfig()
+        incident = canonical_incident("incident-dup", IncidentStatus.DUPLICATE)
+        result = evaluate_incident_eligibility(incident=incident, config=config)
+        assert result.eligible is False
+        assert "terminal" in result.reason
+
+    def test_budget_exhaustion_preserves_policy(self, tmp_path: Path) -> None:
+        config = AutomaticDiagnosisLoopConfig(max_passes_per_incident=1)
+        (tmp_path / "auto-incident-budget-20260101120000-diagnosis-review-packet.json").write_text("{}")
+        incident = canonical_incident("incident-budget")
+        result = evaluate_incident_eligibility(
+            incident=incident, config=config, external_analysis_dir=tmp_path
+        )
+        assert result.eligible is False
+        assert result.reason == "budget_exhausted"
+        assert result.budget_diagnostics[0].exhausted is True
+
+    def test_evaluator_does_not_call_get_incident_store(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        # The aggregate evaluator lives in
+        # ``incident_diagnosis_auto_loop_config``; ensure it does NOT
+        # delegate to ``get_incident_store`` by patching the symbol on
+        # the config module. ``seam_module`` no longer references the
+        # store directly because the local-mode writer was extracted
+        # into a sibling module.
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_config as config_module,
+        )
+
+        def boom(*args: object, **kwargs: object) -> NoReturn:
+            raise AssertionError("get_incident_store was called")
+
+        monkeypatch.setattr(config_module, "get_incident_store", boom)
+        config = AutomaticDiagnosisLoopConfig()
+        incident = canonical_incident("incident-no-lookup")
+        result = evaluate_incident_eligibility(incident=incident, config=config)
+        assert result.eligible is True
+
+    def test_supplied_incident_id_is_identity_in_diagnostics(self) -> None:
+        config = AutomaticDiagnosisLoopConfig()
+        incident = canonical_incident("incident-identity")
+        result = evaluate_incident_eligibility(incident=incident, config=config)
+        assert result.incident_id == "incident-identity"
+
+    def test_local_compat_wrapper_delegates_to_evaluator(self) -> None:
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-local")
+        store._incidents[incident.incident_id] = incident
+        result = check_incident_eligibility(
+            incident_id="incident-local", config=AutomaticDiagnosisLoopConfig()
+        )
+        assert result.eligible is True
+
+    def test_local_compat_wrapper_returns_not_found(self) -> None:
+        set_incident_store(IncidentStore())
+        result = check_incident_eligibility(
+            incident_id="missing", config=AutomaticDiagnosisLoopConfig()
+        )
+        assert result.eligible is False
+        assert result.reason == "incident_not_found"
+
+
+class TestBackendNotFound:
+    def test_404_emits_skipped_not_found(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+
+        def fake_typed(incident_id: IncidentId) -> BackendIncidentNotFound:
+            return BackendIncidentNotFound(
+                requested_incident_id=incident_id,
+                source=BackendIncidentLookupSource.BACKEND_API,
+                http_status=404,
+            )
+
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            fake_typed,
+        )
+        result = processor_module._process_incident(
+            incident_id="missing-incident",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC),
+        )
+        assert result.eligible is False
+        assert result.skip_reason == "incident_not_found"
+        assert result.eligibility_reason == "not_found"
+        assert result.skipped is True
+
+
+class TestBackendPayloadFailures:
+    @pytest.mark.parametrize(
+        "body,expected_code",
+        [
+            (b"", BackendIncidentLookupFailureCode.INVALID_JSON),
+            (b"{not valid json", BackendIncidentLookupFailureCode.INVALID_JSON),
+            (
+                encode({"schema_version": "1", "payload_type": "wrong"}),
+                BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
+            ),
+            (
+                encode({
+                    "schema_version": "999",
+                    "payload_type": SUPPORTED_PAYLOAD_TYPE,
+                    "incident": {"incident_id": "x"},
+                }),
+                BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA,
+            ),
+        ],
+    )
+    def test_malformed_200_never_maps_to_not_found(
+        self,
+        tmp_path: Path,
+        monkeypatch: pytest.MonkeyPatch,
+        body: bytes,
+        expected_code: BackendIncidentLookupFailureCode,
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+
+        def fake_typed(incident_id: IncidentId) -> BackendIncidentLookupFailed:
+            return BackendIncidentLookupFailed(
+                requested_incident_id=incident_id,
+                failure_code=expected_code,
+                detail="synthetic",
+                http_status=200,
+            )
+
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            fake_typed,
+        )
+        result = processor_module._process_incident(
+            incident_id="incident-abc",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC),
+        )
+        assert result.eligible is False
+        assert result.eligibility_reason != "not_found"
+        assert "incident_not_found" not in (result.skip_reason or "")
+        assert "backend_incident_" in result.eligibility_reason
+
+
+class TestSingleFetch:
+    def test_one_processed_incident_means_one_detail_get(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+
+        call_count = {"detail_gets": 0}
+        canonical = canonical_incident("incident-abc")
+
+        def fake_typed(incident_id: IncidentId) -> BackendIncidentFound:
+            call_count["detail_gets"] += 1
+            return BackendIncidentFound(
+                requested_incident_id=incident_id,
+                incident=canonical,
+                source=BackendIncidentLookupSource.BACKEND_API,
+                http_status=200,
+                payload_schema_version=SUPPORTED_SCHEMA_VERSION,
+                payload_type=SUPPORTED_PAYLOAD_TYPE,
+            )
+
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            fake_typed,
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "evaluate_incident_eligibility",
+            lambda **kwargs: StubEligibility(
+                eligible=True, reason="active_incident_with_suggested_checks"
+            ),
+        )
+        processor_module._process_incident(
+            incident_id="incident-abc",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC),
+        )
+        assert call_count["detail_gets"] == 1
+
+
+class TestLocalModeCompatibility:
+    def test_local_found_delegates_to_aggregate_evaluator(self) -> None:
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-local")
+        store._incidents[incident.incident_id] = incident
+        result = check_incident_eligibility(
+            incident_id="incident-local", config=AutomaticDiagnosisLoopConfig()
+        )
+        assert result.eligible is True
+        assert result.reason == "active_incident_with_suggested_checks"
+
+    def test_local_absence_yields_incident_not_found(self) -> None:
+        set_incident_store(IncidentStore())
+        result = check_incident_eligibility(
+            incident_id="missing", config=AutomaticDiagnosisLoopConfig()
+        )
+        assert result.eligible is False
+        assert result.reason == "incident_not_found"
+
+    def test_local_mode_lifecycle_via_local_store(self) -> None:
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-local-lifecycle")
+        store._incidents[incident.incident_id] = incident
+        outcome = record_diagnosis_loop_started(
+            incident_id="incident-local-lifecycle",
+            run_id="run-1",
+            collector_run_id="collector-1",
+        )
+        assert isinstance(outcome, LifecycleWriteApplied)
+        assert outcome.http_status is None  # local mode
+
+    def test_local_mode_no_backend_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
+        def must_not_be_called(*args: Any, **kwargs: Any) -> NoReturn:
+            raise AssertionError("backend HTTP must not be called in local mode")
+
+        # The backend-mode HTTP transport lives in the seam_backend
+        # sibling module; patch its ``urllib.request.urlopen`` symbol.
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_authority_seam_backend as seam_backend_module,
+        )
+
+        monkeypatch.setattr(
+            seam_backend_module.urllib.request, "urlopen", must_not_be_called
+        )
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-local")
+        store._incidents[incident.incident_id] = incident
+        outcome = record_diagnosis_loop_started(
+            incident_id="incident-local", run_id="r", collector_run_id="c"
+        )
+        assert isinstance(outcome, LifecycleWriteApplied)
+
+
+class TestLifecycleOutcomeContract:
+    def test_lifecycle_request_shape(self) -> None:
+        request = build_lifecycle_request(
+            incident_id="incident-x",
+            transition=LifecycleTransition.STARTED,
+            collector_run_id="collector-x",
+            diagnosis_run_id="run-x",
+            payload={"key": "value"},
+        )
+        body = request.to_dict()
+        assert body["schemaVersion"] == LIFECYCLE_SCHEMA_VERSION
+        assert body["incidentId"] == "incident-x"
+        assert body["transition"] == "started"
+        assert body["collectorRunId"] == "collector-x"
+        assert body["diagnosisRunId"] == "run-x"
+        assert body["payload"] == {"key": "value"}
+
+    def test_supported_transitions_match_handler(self) -> None:
+        for transition in LifecycleTransition:
+            assert transition.value in HANDLER_SUPPORTED_TRANSITIONS

=== tests/unit/test_automatic_diagnosis_authority_seam01_dispatch.py ===
diff --git a/tests/unit/test_automatic_diagnosis_authority_seam01_dispatch.py b/tests/unit/test_automatic_diagnosis_authority_seam01_dispatch.py
new file mode 100644
index 00000000..c2025cc8
--- /dev/null
+++ b/tests/unit/test_automatic_diagnosis_authority_seam01_dispatch.py
@@ -0,0 +1,327 @@
+"""Scheduler-side backend dispatch + idempotency tests for
+ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.
+
+Covers:
+
+* ``record_diagnosis_loop_*`` in backend mode — authenticated HTTP POST
+  against an in-process ``ThreadingHTTPServer``-based stub backend.
+* Failure translation: 404 → ``incident_not_found``, 5xx →
+  ``backend_error``, transport errors must NOT fall back to the local
+  store.
+* Idempotency: repeated deliveries collapse into one apply plus N-1
+  replays; concurrent overlapping deliveries apply exactly once;
+  same-key+different-payload → 409 conflict.
+
+The lifecycle HTTP endpoint tests live in
+``test_automatic_diagnosis_authority_seam01_endpoint.py``. Shared
+helpers live in ``tests/unit/authority_seam_support.py``.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+from __future__ import annotations
+
+import socket
+import threading
+from typing import Any
+
+import pytest
+
+from k8s_diag_agent.collect.incident_diagnosis_authority_seam import (
+    LifecycleWriteApplied,
+    LifecycleWriteFailed,
+    LifecycleWriteRejected,
+    record_diagnosis_loop_completed,
+    record_diagnosis_loop_failed,
+    record_diagnosis_loop_started,
+)
+from k8s_diag_agent.collect.incident_store import IncidentStore
+from k8s_diag_agent.collect.incident_store_provider import set_incident_store
+from tests.unit.authority_seam_support import (
+    RecordingHandler,
+    canonical_incident,
+    reset_env,
+    start_backend_server,
+)
+
+__all__ = ["reset_env"]
+
+
+class TestBackendModeDispatch:
+    def test_backend_mode_lifecycle_calls_internal_api(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        _server, base_url, shutdown = start_backend_server()
+        try:
+            monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
+            monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
+            monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
+            monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
+            monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
+            outcome = record_diagnosis_loop_started(
+                incident_id="incident-backend",
+                run_id="run-x",
+                collector_run_id="collector-x",
+            )
+            assert isinstance(outcome, LifecycleWriteApplied)
+            assert outcome.http_status == 200
+            assert outcome.idempotent_replay is False
+            assert RecordingHandler.recorded, "no request recorded"
+            req = RecordingHandler.recorded[-1]
+            assert req["path"] == "/api/internal/incidents/diagnosis-loop-transition"
+            assert "Bearer test-token" in req["headers"].get("Authorization", "")
+            body = req["body"]
+            assert body["schemaVersion"] == 1
+            assert body["incidentId"] == "incident-backend"
+            assert body["transition"] == "started"
+            assert body["diagnosisRunId"] == "run-x"
+        finally:
+            shutdown()
+
+    def test_backend_mode_lifecycle_404_returns_incident_not_found(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        _server, base_url, shutdown = start_backend_server(
+            response_status=404,
+            response_body={
+                "schemaVersion": 1,
+                "applied": False,
+                "reasonCode": "incident_not_found",
+            },
+        )
+        try:
+            monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
+            monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
+            monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
+            monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
+            monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
+            outcome = record_diagnosis_loop_completed(
+                incident_id="incident-missing",
+                run_id="run-x",
+                collector_run_id="collector-x",
+            )
+            assert isinstance(outcome, LifecycleWriteFailed)
+            assert outcome.reason_code == "incident_not_found"
+        finally:
+            shutdown()
+
+    def test_backend_mode_5xx_returns_backend_error(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        _server, base_url, shutdown = start_backend_server(
+            response_status=500,
+            response_body={"schemaVersion": 1, "message": "boom"},
+        )
+        try:
+            monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
+            monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
+            monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
+            monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
+            monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
+            outcome = record_diagnosis_loop_failed(
+                incident_id="incident-1",
+                run_id="run-1",
+                collector_run_id="collector-1",
+                unavailable_reason="case_file_error",
+            )
+            assert isinstance(outcome, LifecycleWriteFailed)
+            assert outcome.reason_code == "backend_error"
+        finally:
+            shutdown()
+
+    def test_backend_mode_transport_error_does_not_fall_back(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        """Backend transport failure must NOT fall back to the local store."""
+        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
+        sock.bind(("127.0.0.1", 0))
+        port = sock.getsockname()[1]
+        sock.close()
+        base_url = f"http://127.0.0.1:{port}"
+
+        store = IncidentStore()
+        set_incident_store(store)
+        store._incidents["incident-1"] = canonical_incident("incident-1")
+
+        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
+        monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
+        monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
+        monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
+        monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
+
+        outcome = record_diagnosis_loop_started(
+            incident_id="incident-1",
+            run_id="run-1",
+            collector_run_id="collector-1",
+        )
+        assert isinstance(outcome, (LifecycleWriteFailed, LifecycleWriteRejected))
+
+    def test_backend_mode_missing_token_returns_failure(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
+        monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", "http://127.0.0.1:1")
+        monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
+        monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
+        outcome = record_diagnosis_loop_started(
+            incident_id="incident-1", run_id="r", collector_run_id="c"
+        )
+        assert isinstance(outcome, LifecycleWriteFailed)
+        assert outcome.reason_code == "missing_internal_token"
+
+
+class TestIdempotency:
+    def test_repeated_lifecycle_deliveries_collapse(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        _server, base_url, shutdown = start_backend_server()
+        try:
+            monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
+            monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
+            monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
+            monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
+            monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
+            seen: list[bool] = []
+            for _ in range(3):
+                outcome = record_diagnosis_loop_started(
+                    incident_id="incident-rep",
+                    run_id="run-1",
+                    collector_run_id="collector-1",
+                )
+                assert isinstance(outcome, LifecycleWriteApplied)
+                seen.append(outcome.idempotent_replay)
+            assert seen.count(False) == 1
+            assert seen.count(True) == 2
+        finally:
+            shutdown()
+
+    def test_concurrent_duplicate_deliveries_apply_once(self) -> None:
+        """Overlapping identical deliveries must not both apply.
+
+        ``ThreadingHTTPServer`` dispatches requests on separate threads,
+        so this fires overlapping deliveries directly against the
+        handler and asserts exactly one fresh apply plus N-1 idempotent
+        replays and no conflict.
+        """
+        import os as _os
+
+        from k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_handler import (
+            handle_diagnosis_loop_transition,
+        )
+        from tests.unit.authority_seam_support import BuildHandler, encode
+
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-concurrent")
+        store._incidents[incident.incident_id] = incident
+        _os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        _os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        try:
+            body = encode({
+                "schemaVersion": 1,
+                "incidentId": "incident-concurrent",
+                "transition": "started",
+                "collectorRunId": "collector-1",
+                "diagnosisRunId": "run-conc",
+                "occurredAt": "2026-07-12T10:00:00+00:00",
+                "payload": {},
+            })
+            n = 8
+            results: list[tuple[dict[str, Any], int]] = []
+            results_lock = threading.Lock()
+            barrier = threading.Barrier(n)
+
+            def deliver() -> None:
+                handler = BuildHandler(
+                    headers={
+                        "Authorization": "Bearer test-token",
+                        "Content-Length": str(len(body)),
+                    },
+                    body=body,
+                )
+                barrier.wait()
+                handle_diagnosis_loop_transition(handler)
+                with results_lock:
+                    results.append(handler.sent[-1])
+
+            threads = [threading.Thread(target=deliver) for _ in range(n)]
+            for t in threads:
+                t.start()
+            for t in threads:
+                t.join()
+
+            assert len(results) == n
+            assert all(status == 200 for _, status in results)
+            replays = [payload["idempotentReplay"] for payload, _ in results]
+            assert replays.count(False) == 1
+            assert replays.count(True) == n - 1
+        finally:
+            _os.environ.pop("K9B_INTERNAL_API_TOKEN", None)
+            _os.environ.pop("K9B_INCIDENT_STORE_BACKEND", None)
+
+    def test_same_key_different_payload_conflicts(self) -> None:
+        """Same idempotency key + different payload → 409 conflict."""
+        import os as _os
+
+        from k8s_diag_agent.collect.incident_store_provider import (
+            set_incident_store,
+        )
+        from k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_handler import (
+            handle_diagnosis_loop_transition,
+        )
+        from tests.unit.authority_seam_support import BuildHandler, encode
+
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-conflict")
+        store._incidents[incident.incident_id] = incident
+        _os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        _os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        try:
+            def _completed_body(review_packet_name: str) -> bytes:
+                return encode({
+                    "schemaVersion": 1,
+                    "incidentId": "incident-conflict",
+                    "transition": "completed",
+                    "collectorRunId": "collector-1",
+                    "diagnosisRunId": "run-conf",
+                    "occurredAt": "2026-07-12T10:00:00+00:00",
+                    "payload": {
+                        "review_packet_name": review_packet_name,
+                        "checks_requested": 1,
+                        "checks_run": 1,
+                        "checks_rejected": 0,
+                        "decision": "stop_root_cause_found",
+                    },
+                })
+
+            first_body = _completed_body("review-a.json")
+            first = BuildHandler(
+                headers={
+                    "Authorization": "Bearer test-token",
+                    "Content-Length": str(len(first_body)),
+                },
+                body=first_body,
+            )
+            handle_diagnosis_loop_transition(first)
+            body1, status1 = first.sent[-1]
+            assert status1 == 200
+            assert body1["applied"] is True
+            assert body1["idempotentReplay"] is False
+
+            second_body = _completed_body("review-b.json")
+            second = BuildHandler(
+                headers={
+                    "Authorization": "Bearer test-token",
+                    "Content-Length": str(len(second_body)),
+                },
+                body=second_body,
+            )
+            handle_diagnosis_loop_transition(second)
+            body2, status2 = second.sent[-1]
+            assert status2 == 409
+            assert body2["applied"] is False
+            assert body2["reasonCode"] == "transition_replay_mismatch"
+        finally:
+            _os.environ.pop("K9B_INTERNAL_API_TOKEN", None)
+            _os.environ.pop("K9B_INCIDENT_STORE_BACKEND", None)

=== tests/unit/test_automatic_diagnosis_authority_seam01_endpoint.py ===
diff --git a/tests/unit/test_automatic_diagnosis_authority_seam01_endpoint.py b/tests/unit/test_automatic_diagnosis_authority_seam01_endpoint.py
new file mode 100644
index 00000000..44b5ecdf
--- /dev/null
+++ b/tests/unit/test_automatic_diagnosis_authority_seam01_endpoint.py
@@ -0,0 +1,262 @@
+"""Lifecycle HTTP endpoint tests for
+ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.
+
+Covers the internal diagnosis-loop-transition endpoint
+(``handle_diagnosis_loop_transition``) and the in-process idempotency
+contract. The scheduler-side backend dispatch tests
+(``record_diagnosis_loop_*`` against an in-process HTTP backend) and
+the higher-level idempotency tests live in
+``test_automatic_diagnosis_authority_seam01_dispatch.py``. Shared
+helpers live in ``tests/unit/authority_seam_support.py``.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
+"""
+
+from __future__ import annotations
+
+import os
+
+from k8s_diag_agent.collect.incident_store import IncidentStore
+from k8s_diag_agent.collect.incident_store_provider import set_incident_store
+from k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_handler import (
+    handle_diagnosis_loop_transition,
+)
+from tests.unit.authority_seam_support import (
+    BuildHandler,
+    StubHandler,
+    canonical_incident,
+    encode,
+    reset_env,
+)
+
+__all__ = ["reset_env"]
+
+
+class TestLifecycleEndpoint:
+    def test_missing_token_returns_401(self) -> None:
+        handler = StubHandler()
+        handler.headers = {"Content-Length": "0"}
+        os.environ.pop("K9B_INTERNAL_API_TOKEN", None)
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
+        real = BuildHandler(headers={"Content-Length": "0"})
+        from k8s_diag_agent.ui import server_incident_internal_auth
+
+        valid = server_incident_internal_auth._validate_internal_token(real)
+        assert valid is False
+        os.environ.pop("K9B_INCIDENT_STORE_BACKEND", None)
+
+    def test_handler_applies_started_transition(self) -> None:
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-lifecycle")
+        store._incidents[incident.incident_id] = incident
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = encode({
+            "schemaVersion": 1,
+            "incidentId": "incident-lifecycle",
+            "transition": "started",
+            "collectorRunId": "collector-1",
+            "occurredAt": "2026-07-12T10:00:00+00:00",
+            "payload": {},
+        })
+        real = BuildHandler(
+            headers={
+                "Authorization": "Bearer test-token",
+                "Content-Length": str(len(body)),
+            },
+            body=body,
+        )
+        handle_diagnosis_loop_transition(real)
+        assert real.sent, "handler did not send a response"
+        body_out, status = real.sent[-1]
+        assert status == 200
+        assert body_out["applied"] is True
+        assert body_out["idempotentReplay"] is False
+
+    def test_handler_applies_failed_transition(self) -> None:
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-failed")
+        store._incidents[incident.incident_id] = incident
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = encode({
+            "schemaVersion": 1,
+            "incidentId": "incident-failed",
+            "transition": "failed",
+            "collectorRunId": "collector-1",
+            "occurredAt": "2026-07-12T10:00:00+00:00",
+            "payload": {"unavailable_reason": "case_file_error"},
+        })
+        real = BuildHandler(
+            headers={
+                "Authorization": "Bearer test-token",
+                "Content-Length": str(len(body)),
+            },
+            body=body,
+        )
+        handle_diagnosis_loop_transition(real)
+        body_out, status = real.sent[-1]
+        assert status == 200
+        assert body_out["applied"] is True
+
+    def test_handler_applies_completed_transition(self) -> None:
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-completed")
+        store._incidents[incident.incident_id] = incident
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = encode({
+            "schemaVersion": 1,
+            "incidentId": "incident-completed",
+            "transition": "completed",
+            "collectorRunId": "collector-1",
+            "occurredAt": "2026-07-12T10:00:00+00:00",
+            "payload": {
+                "review_packet_name": "review.json",
+                "checks_requested": 4,
+                "checks_run": 3,
+                "checks_rejected": 1,
+                "decision": "stop_root_cause_found",
+            },
+        })
+        real = BuildHandler(
+            headers={
+                "Authorization": "Bearer test-token",
+                "Content-Length": str(len(body)),
+            },
+            body=body,
+        )
+        handle_diagnosis_loop_transition(real)
+        body_out, status = real.sent[-1]
+        assert status == 200
+        assert body_out["applied"] is True
+
+    def test_idempotent_replay_returns_true(self) -> None:
+        store = IncidentStore()
+        set_incident_store(store)
+        incident = canonical_incident("incident-replay")
+        store._incidents[incident.incident_id] = incident
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = encode({
+            "schemaVersion": 1,
+            "incidentId": "incident-replay",
+            "transition": "started",
+            "collectorRunId": "collector-1",
+            "diagnosisRunId": "run-replay",
+            "occurredAt": "2026-07-12T10:00:00+00:00",
+            "payload": {},
+        })
+        first = BuildHandler(
+            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
+            body=body,
+        )
+        handle_diagnosis_loop_transition(first)
+        body1, status1 = first.sent[-1]
+        assert status1 == 200
+        assert body1["idempotentReplay"] is False
+        second = BuildHandler(
+            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
+            body=body,
+        )
+        handle_diagnosis_loop_transition(second)
+        body2, status2 = second.sent[-1]
+        assert status2 == 200
+        assert body2["idempotentReplay"] is True
+
+    def test_unknown_transition_returns_400(self) -> None:
+        set_incident_store(IncidentStore())
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = encode({
+            "schemaVersion": 1,
+            "incidentId": "incident-bad",
+            "transition": "wat",
+            "collectorRunId": "c",
+            "occurredAt": "2026-07-12T10:00:00+00:00",
+        })
+        handler = BuildHandler(
+            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
+            body=body,
+        )
+        handle_diagnosis_loop_transition(handler)
+        body_out, status = handler.sent[-1]
+        assert status == 400
+        assert "transition" in body_out.get("message", "").lower()
+
+    def test_unsupported_schema_version_returns_400(self) -> None:
+        set_incident_store(IncidentStore())
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = encode({
+            "schemaVersion": 99,
+            "incidentId": "x",
+            "transition": "started",
+            "collectorRunId": "c",
+            "occurredAt": "2026-07-12T10:00:00+00:00",
+        })
+        handler = BuildHandler(
+            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
+            body=body,
+        )
+        handle_diagnosis_loop_transition(handler)
+        body_out, status = handler.sent[-1]
+        assert status == 400
+        assert "schema" in body_out.get("message", "").lower()
+
+    def test_malformed_json_returns_400(self) -> None:
+        set_incident_store(IncidentStore())
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = b"{not valid json"
+        handler = BuildHandler(
+            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
+            body=body,
+        )
+        handle_diagnosis_loop_transition(handler)
+        body_out, status = handler.sent[-1]
+        assert status == 400
+        assert "json" in body_out.get("message", "").lower()
+
+    def test_unknown_incident_returns_404(self) -> None:
+        set_incident_store(IncidentStore())
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = encode({
+            "schemaVersion": 1,
+            "incidentId": "incident-missing",
+            "transition": "started",
+            "collectorRunId": "c",
+            "occurredAt": "2026-07-12T10:00:00+00:00",
+        })
+        handler = BuildHandler(
+            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
+            body=body,
+        )
+        handle_diagnosis_loop_transition(handler)
+        body_out, status = handler.sent[-1]
+        assert status == 404
+        assert body_out["reasonCode"] == "incident_not_found"
+
+    def test_invalid_run_id_returns_400(self) -> None:
+        set_incident_store(IncidentStore())
+        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
+        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
+        body = encode({
+            "schemaVersion": 1,
+            "incidentId": "incident-1",
+            "transition": "started",
+            "collectorRunId": "",
+            "occurredAt": "2026-07-12T10:00:00+00:00",
+        })
+        handler = BuildHandler(
+            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
+            body=body,
+        )
+        handle_diagnosis_loop_transition(handler)
+        body_out, status = handler.sent[-1]
+        assert status == 400
+        assert "collectorrunid" in body_out.get("message", "").replace(" ", "").lower()

=== tests/unit/test_automatic_diagnosis_authority_seam01_processor.py ===
diff --git a/tests/unit/test_automatic_diagnosis_authority_seam01_processor.py b/tests/unit/test_automatic_diagnosis_authority_seam01_processor.py
new file mode 100644
index 00000000..7e58a583
--- /dev/null
+++ b/tests/unit/test_automatic_diagnosis_authority_seam01_processor.py
@@ -0,0 +1,391 @@
+"""Processor regressions for ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.
+
+Covers ``_process_incident`` behaviour for the ``BackendIncidentFound``
+path: aggregate-based eligibility (no second store read), identity
+mismatch handling, lifecycle-failure surfacing, and the exact
+production-shape regression. Shared helpers live in
+``authority_seam_support``.
+"""
+
+from __future__ import annotations
+
+from datetime import UTC, datetime
+from pathlib import Path
+from typing import Any
+
+import pytest
+
+from k8s_diag_agent.collect.incident_diagnosis_authority_seam import (
+    LifecycleTransition,
+    LifecycleWriteApplied,
+    LifecycleWriteFailed,
+)
+from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
+    AutomaticDiagnosisLoopConfig,
+)
+from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
+    BackendIncidentFound,
+    BackendIncidentLookupSource,
+)
+from k8s_diag_agent.collect.incident_diagnosis_backend_detail_parser import (
+    SUPPORTED_PAYLOAD_TYPE,
+    SUPPORTED_SCHEMA_VERSION,
+)
+from k8s_diag_agent.collect.incident_store import IncidentStore
+from k8s_diag_agent.collect.incident_store_provider import set_incident_store
+from k8s_diag_agent.domain.incident_lifecycle import IncidentId
+from tests.unit.authority_seam_support import (
+    StubEligibility,
+    canonical_incident,
+    never_called,
+    reset_env,
+)
+
+__all__ = ["reset_env"]  # re-export the autouse fixture for collection
+
+_NOW = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+
+
+def _found(incident_id: IncidentId, incident: Any) -> BackendIncidentFound:
+    return BackendIncidentFound(
+        requested_incident_id=incident_id,
+        incident=incident,
+        source=BackendIncidentLookupSource.BACKEND_API,
+        http_status=200,
+        payload_schema_version=SUPPORTED_SCHEMA_VERSION,
+        payload_type=SUPPORTED_PAYLOAD_TYPE,
+    )
+
+
+def _stub_hypothesis_result() -> Any:
+    from k8s_diag_agent.collect.incident_automatic_diagnosis_loop_state import (
+        HypothesisLoopResult,
+    )
+
+    return HypothesisLoopResult(
+        total_passes_completed=0,
+        total_checks_executed=0,
+        hypothesis_burst_written=False,
+    )
+
+
+def _stub_pass(**kwargs: Any) -> dict[str, Any]:
+    return {
+        "decision": "stop_no_checks_proposed",
+        "runner_result": {"checks_requested": 0, "checks_run": 0},
+        "artifact": None,
+        "loop_pass_artifact": None,
+    }
+
+
+class TestBackendFoundProcessor:
+    def test_processor_passes_aggregate_to_evaluator(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+
+        captured: dict[str, Any] = {}
+
+        def fake_evaluate(**kwargs: Any) -> Any:
+            captured["incident"] = kwargs.get("incident")
+            return StubEligibility(
+                eligible=True, reason="active_incident_with_suggested_checks"
+            )
+
+        canonical = canonical_incident("incident-abc")
+        monkeypatch.setattr(processor_module, "evaluate_incident_eligibility", fake_evaluate)
+        monkeypatch.setattr(
+            processor_module,
+            "record_diagnosis_loop_started",
+            lambda **kwargs: LifecycleWriteApplied(
+                transition=LifecycleTransition.STARTED,
+                incident_id=kwargs["incident_id"],
+            ),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "record_diagnosis_loop_completed",
+            lambda **kwargs: LifecycleWriteApplied(
+                transition=LifecycleTransition.COMPLETED,
+                incident_id=kwargs["incident_id"],
+            ),
+        )
+        monkeypatch.setattr(processor_module, "record_diagnosis_loop_failed", never_called)
+        monkeypatch.setattr(
+            processor_module,
+            "build_incident_case_file",
+            lambda **kwargs: {"generated_at": "2026-07-12T10:00:00Z", "suggested_checks": []},
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "run_automatic_diagnosis_hypothesis_loop",
+            lambda *args, **kwargs: _stub_hypothesis_result(),
+        )
+        monkeypatch.setattr(
+            processor_module, "run_policy_enforced_loop_pass", lambda **kwargs: _stub_pass()
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            lambda incident_id: _found(incident_id, canonical),
+        )
+
+        result = processor_module._process_incident(
+            incident_id="incident-abc",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=_NOW,
+        )
+        assert captured.get("incident") is canonical
+        assert result.error is None or "incident_not_found" not in str(result.error)
+        assert result.eligible is True
+
+    def test_no_local_store_read_before_eligibility(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+        from k8s_diag_agent.collect import (
+            incident_store_provider as provider_module,
+        )
+
+        seen_get_store: list[bool] = []
+        original_get_store = provider_module.get_incident_store
+
+        def tracking_get_store() -> IncidentStore:
+            seen_get_store.append(True)
+            return original_get_store()
+
+        monkeypatch.setattr(provider_module, "get_incident_store", tracking_get_store)
+        # The processor must not re-import get_incident_store.
+        assert not hasattr(processor_module, "get_incident_store")
+
+        canonical = canonical_incident("incident-abc")
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            lambda incident_id: _found(incident_id, canonical),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "evaluate_incident_eligibility",
+            lambda **kwargs: StubEligibility(
+                eligible=True, reason="active_incident_with_suggested_checks"
+            ),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "record_diagnosis_loop_started",
+            lambda **kwargs: LifecycleWriteApplied(
+                transition=LifecycleTransition.STARTED,
+                incident_id=kwargs["incident_id"],
+            ),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "record_diagnosis_loop_completed",
+            lambda **kwargs: LifecycleWriteApplied(
+                transition=LifecycleTransition.COMPLETED,
+                incident_id=kwargs["incident_id"],
+            ),
+        )
+        monkeypatch.setattr(processor_module, "record_diagnosis_loop_failed", never_called)
+        monkeypatch.setattr(
+            processor_module,
+            "build_incident_case_file",
+            lambda **kwargs: {"generated_at": "x", "suggested_checks": []},
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "run_automatic_diagnosis_hypothesis_loop",
+            lambda *args, **kwargs: _stub_hypothesis_result(),
+        )
+        monkeypatch.setattr(
+            processor_module, "run_policy_enforced_loop_pass", lambda **kwargs: _stub_pass()
+        )
+
+        result = processor_module._process_incident(
+            incident_id="incident-abc",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=_NOW,
+        )
+        assert result.eligible is True
+        assert result.error is None or "incident_not_found" not in str(result.error)
+        assert seen_get_store == []
+
+    def test_identity_mismatch_surfaces_as_typed_failure(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+
+        mismatched = canonical_incident("incident-OTHER")
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            lambda incident_id: _found(incident_id, mismatched),
+        )
+        result = processor_module._process_incident(
+            incident_id="incident-abc",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=_NOW,
+        )
+        assert result.eligible is False
+        assert result.eligibility_reason == "backend_incident_identity_mismatch"
+        assert result.error is not None
+        assert "incident-OTHER" in result.error
+        assert "incident-abc" in result.error
+
+
+class TestProcessorLifecycleFailures:
+    def test_start_failure_prevents_diagnosis(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+
+        canonical = canonical_incident("incident-start-fail")
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            lambda incident_id: _found(incident_id, canonical),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "evaluate_incident_eligibility",
+            lambda **kwargs: StubEligibility(
+                eligible=True, reason="active_incident_with_suggested_checks"
+            ),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "record_diagnosis_loop_started",
+            lambda **kwargs: LifecycleWriteFailed(
+                transition=LifecycleTransition.STARTED,
+                incident_id=kwargs["incident_id"],
+                reason_code="backend_url_not_configured",
+            ),
+        )
+        monkeypatch.setattr(processor_module, "record_diagnosis_loop_completed", never_called)
+        monkeypatch.setattr(processor_module, "record_diagnosis_loop_failed", never_called)
+
+        result = processor_module._process_incident(
+            incident_id="incident-start-fail",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=_NOW,
+        )
+        assert result.eligible is True
+        assert result.error is not None
+        assert "diagnosis_lifecycle_start_failed" in result.error
+        assert "backend_url_not_configured" in result.error
+
+    def test_completion_failure_does_not_claim_success(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+
+        canonical = canonical_incident("incident-completion-fail")
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            lambda incident_id: _found(incident_id, canonical),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "evaluate_incident_eligibility",
+            lambda **kwargs: StubEligibility(
+                eligible=True, reason="active_incident_with_suggested_checks"
+            ),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "record_diagnosis_loop_started",
+            lambda **kwargs: LifecycleWriteApplied(
+                transition=LifecycleTransition.STARTED,
+                incident_id=kwargs["incident_id"],
+            ),
+        )
+        monkeypatch.setattr(processor_module, "record_diagnosis_loop_failed", never_called)
+        monkeypatch.setattr(
+            processor_module,
+            "record_diagnosis_loop_completed",
+            lambda **kwargs: LifecycleWriteFailed(
+                transition=LifecycleTransition.COMPLETED,
+                incident_id=kwargs["incident_id"],
+                reason_code="backend_error",
+            ),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "build_incident_case_file",
+            lambda **kwargs: {"generated_at": "x", "suggested_checks": []},
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "run_automatic_diagnosis_hypothesis_loop",
+            lambda *args, **kwargs: _stub_hypothesis_result(),
+        )
+        monkeypatch.setattr(
+            processor_module, "run_policy_enforced_loop_pass", lambda **kwargs: _stub_pass()
+        )
+
+        result = processor_module._process_incident(
+            incident_id="incident-completion-fail",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=_NOW,
+        )
+        assert result.error is not None
+        assert "diagnosis_lifecycle_completion_failed" in result.error
+        assert "backend_error" in result.error
+
+
+class TestProductionShapeRegression:
+    def test_production_sequence_does_not_emit_incident_not_found(
+        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.collect import (
+            incident_diagnosis_auto_loop_evidence_processor as processor_module,
+        )
+
+        canonical = canonical_incident("incident-prod-shape")
+        monkeypatch.setattr(
+            processor_module,
+            "fetch_backend_incident_for_diagnosis_typed",
+            lambda incident_id: _found(incident_id, canonical),
+        )
+        monkeypatch.setattr(
+            processor_module,
+            "evaluate_incident_eligibility",
+            lambda **kwargs: StubEligibility(
+                eligible=True, reason="active_incident_with_suggested_checks"
+            ),
+        )
+        # Local store is empty (production shape).
+        set_incident_store(IncidentStore())
+
+        result = processor_module._process_incident(
+            incident_id="incident-prod-shape",
+            external_analysis_dir=tmp_path,
+            config=AutomaticDiagnosisLoopConfig(),
+            collector_run_id="collector-test",
+            now=_NOW,
+        )
+        assert result.eligibility_reason != "not_found"
+        assert (result.skip_reason or "") != "not_eligible: incident_not_found"
+        assert result.eligible is True

=== tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py ===
diff --git a/tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py b/tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py
new file mode 100644
index 00000000..0f9affdc
--- /dev/null
+++ b/tests/unit/test_automatic_diagnosis_authority_seam01_verifier.py
@@ -0,0 +1,272 @@
+"""Self-tests for the ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 verifier.
+
+The static verifier lives at
+``scripts/verifiers/automatic_diagnosis_authority_seam01.py``. These
+self-tests prove that:
+
+* the verifier PASSES against the current (fixed) production code
+  (``run_static_checks() == []`` and ``main() == 0``);
+* each forbidden form is actually detected — a verifier PASS is only
+  meaningful if the negative fixtures fail as designed.
+
+Every check that operates on an AST tree is exercised with a paired
+negative fixture (must produce a violation) and positive fixture (must
+not). This closes R1-8/R1-9: the verifier is no longer a green stamp
+with untested detectors.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R1)
+"""
+
+from __future__ import annotations
+
+import ast
+import importlib.util
+from pathlib import Path
+from types import ModuleType
+
+import pytest
+
+_VERIFIER_PATH = (
+    Path(__file__).resolve().parents[2]
+    / "scripts"
+    / "verifiers"
+    / "automatic_diagnosis_authority_seam01.py"
+)
+
+
+def _load_verifier() -> ModuleType:
+    spec = importlib.util.spec_from_file_location(
+        "adas01_verifier", _VERIFIER_PATH
+    )
+    assert spec is not None and spec.loader is not None
+    module = importlib.util.module_from_spec(spec)
+    spec.loader.exec_module(module)
+    return module
+
+
+verifier = _load_verifier()
+
+
+def _module(src: str) -> ast.Module:
+    return ast.parse(src)
+
+
+# ---------------------------------------------------------------------------
+# Production PASS: the verifier must accept the current fixed code.
+# ---------------------------------------------------------------------------
+
+
+class TestProductionPasses:
+    def test_run_static_checks_is_clean(self) -> None:
+        violations = verifier.run_static_checks()
+        assert violations == [], f"unexpected violations: {violations}"
+
+    def test_main_returns_zero(self) -> None:
+        assert verifier.main([]) == 0
+
+
+# ---------------------------------------------------------------------------
+# Negative + positive fixtures for the tree-based checks.
+# ---------------------------------------------------------------------------
+
+
+class TestForbiddenProcessorCalls:
+    def test_get_incident_store_is_rejected(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    store = get_incident_store()\n"
+        )
+        assert verifier._check_processor_calls(tree)
+
+    def test_direct_lifecycle_method_is_rejected(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    store.mark_diagnosis_loop_started(incident_id=i)\n"
+        )
+        assert verifier._check_processor_calls(tree)
+
+    def test_clean_processor_has_no_forbidden_calls(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    record_diagnosis_loop_started(incident_id=i)\n"
+        )
+        assert verifier._check_processor_calls(tree) == []
+
+
+class TestOldIdResolver:
+    def test_check_incident_eligibility_by_id_is_rejected(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    check_incident_eligibility(incident_id=x, config=c)\n"
+        )
+        assert verifier._check_processor_old_id_resolver(tree)
+
+    def test_aggregate_call_is_allowed(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    evaluate_incident_eligibility(incident=obj, config=c)\n"
+        )
+        assert verifier._check_processor_old_id_resolver(tree) == []
+
+
+class TestUsesAggregateEligibility:
+    def test_missing_aggregate_call_is_rejected(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    x = 1\n"
+        )
+        assert verifier._check_processor_uses_aggregate_eligibility(tree)
+
+    def test_present_aggregate_call_passes(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    evaluate_incident_eligibility(incident=obj, config=c)\n"
+        )
+        assert verifier._check_processor_uses_aggregate_eligibility(tree) == []
+
+    def test_call_without_incident_kw_is_rejected(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    evaluate_incident_eligibility(config=c)\n"
+        )
+        assert verifier._check_processor_uses_aggregate_eligibility(tree)
+
+
+class TestDispatchExhaustiveness:
+    def test_missing_variant_is_rejected(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    match outcome:\n"
+            "        case BackendIncidentFound():\n"
+            "            pass\n"
+        )
+        assert verifier._check_processor_dispatch(tree)
+
+    def test_all_three_variants_pass(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    match outcome:\n"
+            "        case BackendIncidentNotFound():\n"
+            "            pass\n"
+            "        case BackendIncidentLookupFailed():\n"
+            "            pass\n"
+            "        case BackendIncidentFound():\n"
+            "            pass\n"
+        )
+        assert verifier._check_processor_dispatch(tree) == []
+
+
+class TestNoBackendToLocalFallback:
+    def test_fetch_incident_local_is_rejected(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    fetch_incident_local(incident_id=i)\n"
+        )
+        assert verifier._check_processor_no_backend_to_local_fallback(tree)
+
+    def test_clean_processor_passes(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    record_diagnosis_loop_started(incident_id=i)\n"
+        )
+        assert verifier._check_processor_no_backend_to_local_fallback(tree) == []
+
+
+class TestNoSwallowedLifecycle:
+    def test_except_pass_around_lifecycle_is_rejected(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    try:\n"
+            "        record_diagnosis_loop_started(incident_id=i)\n"
+            "    except Exception:\n"
+            "        pass\n"
+        )
+        assert verifier._check_processor_no_swallowed_lifecycle(tree)
+
+    def test_except_pass_around_non_lifecycle_is_allowed(self) -> None:
+        tree = _module(
+            "def _process_incident():\n"
+            "    try:\n"
+            "        write_review_packet()\n"
+            "    except Exception:\n"
+            "        pass\n"
+        )
+        assert verifier._check_processor_no_swallowed_lifecycle(tree) == []
+
+
+class TestTruthinessToNotFound:
+    def test_assignment_form_is_detected(self) -> None:
+        tree = _module(
+            "if not incident:\n"
+            "    reason = 'incident_not_found'\n"
+        )
+        assert verifier._contains_truthiness_to_not_found(tree) is True
+
+    def test_constructor_keyword_form_is_detected(self) -> None:
+        tree = _module(
+            "if not incident:\n"
+            "    return AutoLoopIncidentResult("
+            "eligibility_reason='incident_not_found')\n"
+        )
+        assert verifier._contains_truthiness_to_not_found(tree) is True
+
+    def test_clean_branch_is_not_flagged(self) -> None:
+        tree = _module(
+            "if not incident:\n"
+            "    reason = 'ok'\n"
+        )
+        assert verifier._contains_truthiness_to_not_found(tree) is False
+
+
+class TestEmptyExceptPass:
+    def test_bare_except_pass_is_detected(self) -> None:
+        tree = _module(
+            "try:\n"
+            "    foo()\n"
+            "except Exception:\n"
+            "    pass\n"
+        )
+        assert verifier._has_empty_except_pass(tree) is True
+
+    def test_handled_except_is_not_flagged(self) -> None:
+        tree = _module(
+            "try:\n"
+            "    foo()\n"
+            "except Exception:\n"
+            "    handle()\n"
+        )
+        assert verifier._has_empty_except_pass(tree) is False
+
+
+class TestSeamAvailableNames:
+    def test_defined_imported_exported_are_collected(self) -> None:
+        tree = _module(
+            "from x import record_diagnosis_loop_started\n"
+            "__all__ = ['evaluate_incident_eligibility']\n"
+            "def build_lifecycle_request():\n"
+            "    pass\n"
+        )
+        defined, imported, exported = verifier._seam_available_names(tree)
+        assert "build_lifecycle_request" in defined
+        assert "record_diagnosis_loop_started" in imported
+        assert "evaluate_incident_eligibility" in exported
+
+
+class TestFailureKeywordMapping:
+    """The production check reads the real processor; a fixture proves the
+    call-keyword detector recognises the forbidden projection form."""
+
+    def test_call_keyword_failure_mapping_is_detected_via_truthiness(self) -> None:
+        # The failure-path detector shares the call-keyword recognition
+        # with the truthiness detector; a synthetic ``if not`` guard
+        # exercises the same ``eligibility_reason='incident_not_found'``
+        # keyword form the failure-path check forbids.
+        tree = _module(
+            "if not ok:\n"
+            "    AutoLoopIncidentResult(eligibility_reason='incident_not_found')\n"
+        )
+        assert verifier._contains_truthiness_to_not_found(tree) is True
+
+
+if __name__ == "__main__":  # pragma: no cover - convenience
+    raise SystemExit(pytest.main([__file__, "-q"]))

=== tests/unit/test_automatic_diagnosis_backend_promotion_regression.py ===
diff --git a/tests/unit/test_automatic_diagnosis_backend_promotion_regression.py b/tests/unit/test_automatic_diagnosis_backend_promotion_regression.py
index 1ed767ed..3cef147c 100644
--- a/tests/unit/test_automatic_diagnosis_backend_promotion_regression.py
+++ b/tests/unit/test_automatic_diagnosis_backend_promotion_regression.py
@@ -166,15 +166,19 @@ class TestPromotionToDiagnosisRegression:

         eligibility_stub_calls: list[str] = []

-        def fake_check_incident_eligibility(**kwargs: Any) -> Any:
+        def fake_evaluate_incident_eligibility(**kwargs: Any) -> Any:
             eligibility_stub_calls.append(kwargs["incident_id"])
             return _StubEligibility(eligible=True, reason="active_incident_with_suggested_checks")

+        # R1 follow-up: the processor now calls
+        # ``evaluate_incident_eligibility`` (the canonical
+        # eligibility evaluator). The monkeypatch target must
+        # match the symbol the processor actually invokes.
         monkeypatch.setattr(
             "k8s_diag_agent.collect."
             "incident_diagnosis_auto_loop_evidence_processor."
-            "check_incident_eligibility",
-            fake_check_incident_eligibility,
+            "evaluate_incident_eligibility",
+            fake_evaluate_incident_eligibility,
         )

         # Inject a fake ``BackendIncidentClient`` via the typed lookup

=== tests/unit/test_incident_diagnosis_authority_run_summary.py ===
diff --git a/tests/unit/test_incident_diagnosis_authority_run_summary.py b/tests/unit/test_incident_diagnosis_authority_run_summary.py
new file mode 100644
index 00000000..faaa52ed
--- /dev/null
+++ b/tests/unit/test_incident_diagnosis_authority_run_summary.py
@@ -0,0 +1,156 @@
+"""Unit tests for the authority run-summary accounting.
+
+Covers the ACT-required per-run counters
+(``backend_lookup_outcomes`` / ``eligibility_outcomes`` /
+``lifecycle_write_outcomes`` / ``backend_found_then_incident_not_found``)
+derived from per-incident result mappings.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R1)
+"""
+
+from __future__ import annotations
+
+from k8s_diag_agent.collect.incident_diagnosis_authority_run_summary import (
+    AuthorityRunSummary,
+    summarize_incident_results,
+)
+
+
+def test_backend_not_found_is_counted() -> None:
+    results = [
+        {
+            "eligible": False,
+            "eligibility_reason": "not_found",
+            "skipped": True,
+            "skip_reason": "incident_not_found",
+        }
+    ]
+    summary = summarize_incident_results(results)
+    assert summary.backend_lookup_outcomes == {"not_found": 1}
+    assert summary.backend_found_then_incident_not_found == 0
+
+
+def test_backend_lookup_failed_is_counted() -> None:
+    results = [
+        {
+            "eligible": False,
+            "eligibility_reason": "backend_incident_invalid_payload",
+            "error": "synthetic",
+        }
+    ]
+    summary = summarize_incident_results(results)
+    assert summary.backend_lookup_outcomes == {"lookup_failed": 1}
+    assert summary.backend_found_then_incident_not_found == 0
+
+
+def test_eligible_processed_incident_is_applied() -> None:
+    results = [
+        {
+            "eligible": True,
+            "eligibility_reason": "active_incident_with_suggested_checks",
+            "skipped": False,
+            "error": None,
+        }
+    ]
+    summary = summarize_incident_results(results)
+    assert summary.backend_lookup_outcomes == {"found": 1}
+    assert summary.eligibility_outcomes == {"eligible": 1}
+    assert summary.lifecycle_write_outcomes == {"applied": 1}
+
+
+def test_ineligible_incident_reason_is_keyed() -> None:
+    results = [
+        {
+            "eligible": False,
+            "eligibility_reason": "budget_exhausted",
+            "skipped": True,
+            "skip_reason": "not_eligible: budget_exhausted",
+        }
+    ]
+    summary = summarize_incident_results(results)
+    assert summary.eligibility_outcomes == {"budget_exhausted": 1}
+    # A budget-exhausted incident is a backend-found incident (it was
+    # resolved) but was not processed → lifecycle not applicable.
+    assert summary.backend_lookup_outcomes == {"found": 1}
+    assert summary.lifecycle_write_outcomes == {"not_applicable": 1}
+    assert summary.backend_found_then_incident_not_found == 0
+
+
+def test_lifecycle_start_and_completion_failures_are_distinguished() -> None:
+    results = [
+        {
+            "eligible": True,
+            "eligibility_reason": "active_incident_with_suggested_checks",
+            "error": "diagnosis_lifecycle_start_failed: backend_url_not_configured",
+        },
+        {
+            "eligible": True,
+            "eligibility_reason": "active_incident_with_suggested_checks",
+            "error": "diagnosis_lifecycle_completion_failed: backend_error",
+        },
+        {
+            "eligible": True,
+            "eligibility_reason": "active_incident_with_suggested_checks",
+            "error": "Failed to build case file: KeyError; "
+            "lifecycle_recording_error=backend_error; http_status=500",
+        },
+    ]
+    summary = summarize_incident_results(results)
+    assert summary.lifecycle_write_outcomes == {
+        "start_failed": 1,
+        "completion_failed": 1,
+        "recording_failed": 1,
+    }
+
+
+def test_split_authority_regression_is_flagged() -> None:
+    # The legacy defect: backend-found incident collapsed to
+    # incident_not_found (eligibility_reason == "incident_not_found").
+    results = [
+        {
+            "eligible": False,
+            "eligibility_reason": "incident_not_found",
+            "skipped": True,
+            "skip_reason": "not_eligible: incident_not_found",
+        }
+    ]
+    summary = summarize_incident_results(results)
+    assert summary.backend_lookup_outcomes == {"found": 1}
+    assert summary.backend_found_then_incident_not_found == 1
+
+
+def test_to_dict_shape_has_required_fields() -> None:
+    summary = AuthorityRunSummary()
+    payload = summary.to_dict()
+    assert set(payload.keys()) == {
+        "backend_lookup_outcomes",
+        "eligibility_outcomes",
+        "lifecycle_write_outcomes",
+        "backend_found_then_incident_not_found",
+    }
+    assert payload["backend_found_then_incident_not_found"] == 0
+
+
+def test_mixed_run_aggregates_counts() -> None:
+    results = [
+        {"eligible": True, "eligibility_reason": "active", "error": None},
+        {"eligible": True, "eligibility_reason": "active", "error": None},
+        {
+            "eligible": False,
+            "eligibility_reason": "not_found",
+            "skipped": True,
+            "skip_reason": "incident_not_found",
+        },
+        {
+            "eligible": False,
+            "eligibility_reason": "backend_incident_unsupported_schema",
+        },
+    ]
+    summary = summarize_incident_results(results)
+    assert summary.backend_lookup_outcomes == {
+        "found": 2,
+        "not_found": 1,
+        "lookup_failed": 1,
+    }
+    assert summary.eligibility_outcomes["eligible"] == 2
+    assert summary.backend_found_then_incident_not_found == 0

=== tests/unit/test_incident_snapshot_serialization_isolation.py ===
diff --git a/tests/unit/test_incident_snapshot_serialization_isolation.py b/tests/unit/test_incident_snapshot_serialization_isolation.py
new file mode 100644
index 00000000..854a13d0
--- /dev/null
+++ b/tests/unit/test_incident_snapshot_serialization_isolation.py
@@ -0,0 +1,316 @@
+"""R5 regression tests: snapshot and serialization isolation for ``diagnosis_loop``.
+
+Closes R5-1 from the
+``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:
+
+* ``snapshot_incident`` must deep-copy the ``diagnosis_loop`` projection
+  field so mutations on the returned snapshot cannot reach back into
+  the cached aggregate and bypass the canonical event writer.
+* ``incident_to_dict`` (and therefore ``Incident.to_dict()``) must
+  deep-copy the ``diagnosis_loop`` projection field for the same
+  reason.
+* The deep copy must also break aliasing on nested mutable structures,
+  not just the top-level dict (the field is declared ``dict[str, Any]``
+  and may legally contain nested dicts/lists).
+
+The pre-R5 code passed the same dictionary reference through both
+boundaries, which allowed the following event-store authority bypass:
+
+    read snapshot
+        ↓
+    mutate returned diagnosis_loop dictionary
+        ↓
+    cached aggregate changes
+        ↓
+    no canonical event
+    no projection update
+    no hash-chain entry
+
+These tests prove that mutations on the returned snapshot/payload are
+isolated from the source aggregate and from any nested mutable state.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R5)
+"""
+
+from __future__ import annotations
+
+import shutil
+import sqlite3
+import tempfile
+import unittest
+from datetime import UTC, datetime
+from pathlib import Path
+
+from k8s_diag_agent.collect.incident_lifecycle import (
+    Incident,
+    IncidentStatus,
+)
+from k8s_diag_agent.collect.incident_lifecycle_serialization import (
+    incident_to_dict,
+)
+from k8s_diag_agent.collect.incident_snapshot_helpers import snapshot_incident
+from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
+from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
+    apply_lifecycle_transition_atomic,
+)
+
+
+def _make_incident_with_diagnosis_loop(
+    incident_id: str = "default-pod-isolation-pod-crash_loop",
+    *,
+    diagnosis_loop: dict | None = None,
+) -> Incident:
+    """Build an Incident with a populated ``diagnosis_loop`` projection."""
+    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+    return Incident(
+        incident_id=incident_id,
+        source_candidate_id="test-candidate",
+        namespace="default",
+        object_kind="Pod",
+        object_name="isolation-pod",
+        raw_object_kind=None,
+        candidate_class="crash_loop",
+        severity="error",
+        status=IncidentStatus.OPEN,
+        first_observed_at=now,
+        last_observed_at=now,
+        diagnosis_loop=diagnosis_loop,
+    )
+
+
+# =============================================================================
+# R5-1: snapshot_incident must deep-copy diagnosis_loop
+# =============================================================================
+
+
+class TestR5SnapshotIsolation(unittest.TestCase):
+    """R5-1: ``snapshot_incident`` must isolate the cached aggregate."""
+
+    def test_snapshot_diagnosis_loop_does_not_alias_cache(self) -> None:
+        """Mutating the snapshot's diagnosis_loop must NOT mutate the cache."""
+        cached = _make_incident_with_diagnosis_loop(
+            diagnosis_loop={"status": "completed"},
+        )
+
+        snapshot = snapshot_incident(cached)
+
+        # Mutate the returned snapshot.
+        self.assertIsNotNone(snapshot.diagnosis_loop)
+        snapshot.diagnosis_loop["status"] = "tampered"
+
+        # The cached aggregate must remain unchanged.
+        self.assertIsNotNone(cached.diagnosis_loop)
+        self.assertEqual(
+            cached.diagnosis_loop["status"],
+            "completed",
+            "snapshot must not alias the cached aggregate's diagnosis_loop",
+        )
+
+    def test_snapshot_diagnosis_loop_nested_mutation_is_isolated(self) -> None:
+        """The deep copy must also break aliasing on nested mutable state.
+
+        A shallow ``dict(...)`` would NOT be sufficient: the field is
+        declared ``dict[str, Any]`` and may legitimately contain nested
+        dicts and lists. This test proves we use ``deepcopy``, not just
+        a shallow copy.
+        """
+        nested = {"checks": [{"name": "check-a"}, {"name": "check-b"}]}
+        cached = _make_incident_with_diagnosis_loop(
+            diagnosis_loop={
+                "status": "running",
+                "run_state": nested,
+            },
+        )
+
+        snapshot = snapshot_incident(cached)
+
+        # Mutate the nested structure on the snapshot.
+        self.assertIsNotNone(snapshot.diagnosis_loop)
+        snapshot.diagnosis_loop["run_state"]["checks"][0]["name"] = "tampered"
+
+        # The nested state on the cached aggregate must be unchanged.
+        self.assertIsNotNone(cached.diagnosis_loop)
+        self.assertEqual(
+            cached.diagnosis_loop["run_state"]["checks"][0]["name"],
+            "check-a",
+            "snapshot must deep-copy nested mutable state, not just the top-level dict",
+        )
+
+    def test_snapshot_diagnosis_loop_none_passes_through(self) -> None:
+        """A None diagnosis_loop must remain None (no spurious empty dict)."""
+        cached = _make_incident_with_diagnosis_loop(diagnosis_loop=None)
+        snapshot = snapshot_incident(cached)
+        self.assertIsNone(snapshot.diagnosis_loop)
+
+
+# =============================================================================
+# R5-1: incident_to_dict must deep-copy diagnosis_loop
+# =============================================================================
+
+
+class TestR5SerializationIsolation(unittest.TestCase):
+    """R5-1: ``incident_to_dict`` must isolate the source aggregate."""
+
+    def test_to_dict_diagnosis_loop_does_not_alias_incident(self) -> None:
+        """Mutating the payload's diagnosis_loop must NOT mutate the incident."""
+        incident = _make_incident_with_diagnosis_loop(
+            diagnosis_loop={"status": "completed"},
+        )
+
+        payload = incident_to_dict(incident)
+
+        # Mutate the serialized payload.
+        self.assertIsNotNone(payload["diagnosis_loop"])
+        payload["diagnosis_loop"]["status"] = "tampered"
+
+        # The source aggregate must remain unchanged.
+        self.assertIsNotNone(incident.diagnosis_loop)
+        self.assertEqual(
+            incident.diagnosis_loop["status"],
+            "completed",
+            "to_dict payload must not alias the incident's diagnosis_loop",
+        )
+
+    def test_to_dict_diagnosis_loop_nested_mutation_is_isolated(self) -> None:
+        """The deep copy must also break aliasing on nested mutable state."""
+        incident = _make_incident_with_diagnosis_loop(
+            diagnosis_loop={
+                "status": "running",
+                "run_state": {"checks": [{"name": "check-a"}]},
+            },
+        )
+
+        payload = incident_to_dict(incident)
+
+        # Mutate the nested structure on the payload.
+        self.assertIsNotNone(payload["diagnosis_loop"])
+        payload["diagnosis_loop"]["run_state"]["checks"][0]["name"] = "tampered"
+
+        # The nested state on the source aggregate must be unchanged.
+        self.assertIsNotNone(incident.diagnosis_loop)
+        self.assertEqual(
+            incident.diagnosis_loop["run_state"]["checks"][0]["name"],
+            "check-a",
+            "to_dict must deep-copy nested mutable state, not just the top-level dict",
+        )
+
+    def test_to_dict_diagnosis_loop_none_passes_through(self) -> None:
+        """A None diagnosis_loop must serialize as None."""
+        incident = _make_incident_with_diagnosis_loop(diagnosis_loop=None)
+        payload = incident_to_dict(incident)
+        self.assertIsNone(payload["diagnosis_loop"])
+
+    def test_incident_to_dict_dataclass_aliases_helper(self) -> None:
+        """``Incident.to_dict`` routes through ``incident_to_dict`` and inherits isolation."""
+        incident = _make_incident_with_diagnosis_loop(
+            diagnosis_loop={"status": "completed"},
+        )
+        payload = incident.to_dict()
+        payload["diagnosis_loop"]["status"] = "tampered"
+        self.assertEqual(
+            incident.diagnosis_loop["status"],
+            "completed",
+            "Incident.to_dict must inherit isolation from incident_to_dict",
+        )
+
+
+# =============================================================================
+# R5-1: integration with the canonical SQLite lifecycle apply path
+# =============================================================================
+
+
+class TestR5StoreAndSnapshotIsolation(unittest.TestCase):
+    """R5-1: the cached store aggregate is the canonical authority.
+
+    These tests combine the snapshot helper with the canonical SQLite
+    lifecycle-apply path so we prove the end-to-end invariant:
+    mutating the snapshot returned by ``store.get_incident`` cannot
+    mutate the cache that backs the canonical event writer.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def _populate(self, store: SQLiteIncidentStore) -> str:
+        from tests.unit.incident_store_sqlite_seam_helpers import make_candidate
+
+        candidate = make_candidate(name="r5-isolation-pod")
+        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+        incidents = store.promote_candidates([candidate], observed_at)
+        return str(incidents[0].incident_id)
+
+    def test_store_get_incident_diagnosis_loop_is_isolated_from_cache(self) -> None:
+        """``store.get_incident`` returns a snapshot; mutating it must not
+        mutate ``store._incidents``.
+        """
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = self._populate(store)
+
+        result = apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-r5-isolation",
+            collector_run_id="collector-r5-isolation",
+            fingerprint="fp-r5-isolation",
+            occurred_at=datetime(2026, 7, 12, 11, 0, 0, tzinfo=UTC),
+            payload={
+                "review_packet_name": "r5-review.json",
+                "checks_requested": 1,
+                "checks_run": 1,
+                "checks_rejected": 0,
+                "decision": "stop_root_cause_found",
+            },
+        )
+        self.assertEqual(result["outcome"], "applied")
+
+        # 1. The cached aggregate carries the typed field.
+        cached = store._incidents[incident_id]
+        self.assertIsNotNone(cached.diagnosis_loop)
+        self.assertEqual(cached.diagnosis_loop.get("status"), "completed")
+
+        # 2. ``store.get_incident`` returns a snapshot copy.
+        detail = store.get_incident(incident_id)
+        self.assertIsNotNone(detail)
+        self.assertIsNotNone(detail.diagnosis_loop)
+        detail.diagnosis_loop["status"] = "tampered"
+
+        # 3. The cached aggregate must NOT have been mutated.
+        cached_after = store._incidents[incident_id]
+        self.assertIsNotNone(cached_after.diagnosis_loop)
+        self.assertEqual(
+            cached_after.diagnosis_loop["status"],
+            "completed",
+            "store.get_incident must return an isolated snapshot, not a reference",
+        )
+
+        # 4. The durable projection must NOT have been mutated.
+        with sqlite3.connect(str(self._db_path)) as conn:
+            (projection_json,) = conn.execute(
+                "SELECT current_state_json FROM incident_current "
+                "WHERE incident_id = ?",
+                (incident_id,),
+            ).fetchone()
+        import json as _json
+
+        projection = _json.loads(projection_json)
+        self.assertEqual(
+            projection["diagnosis_loop"]["status"],
+            "completed",
+            "durable projection must not be mutated by snapshot consumer",
+        )
+
+
+__all__ = [
+    "TestR5SnapshotIsolation",
+    "TestR5SerializationIsolation",
+    "TestR5StoreAndSnapshotIsolation",
+]
+
+
+if __name__ == "__main__":
+    unittest.main()
\ No newline at end of file

=== tests/unit/test_incident_store_sqlite_lifecycle_idempotency.py ===
diff --git a/tests/unit/test_incident_store_sqlite_lifecycle_idempotency.py b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency.py
new file mode 100644
index 00000000..d962085e
--- /dev/null
+++ b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency.py
@@ -0,0 +1,458 @@
+"""Regression tests for SQLite atomic lifecycle idempotency.
+
+These tests close the R2 failures from
+``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01``:
+
+* **Restart-durable idempotency** — closing and reopening the SQLite
+  store preserves the idempotency record so a retried delivery
+  collapses to a replay instead of double-applying.
+* **Multi-process idempotency** — two separate SQLiteIncidentStore
+  instances (each opening its own connection / process) serialize
+  on ``BEGIN IMMEDIATE`` so the lookup→apply→record cycle never
+  runs the mutation twice.
+* **SQLite atomic mutation + idempotency commit** — the mutation
+  (``incident_events`` insert) and the idempotency record insert
+  (``lifecycle_idempotency`` insert) land in the same transaction
+  and either both commit or neither does.
+
+The HTTP / endpoint dispatch path is exercised separately in
+``tests/unit/test_automatic_diagnosis_authority_seam01_endpoint.py``
+and ``tests/unit/test_automatic_diagnosis_authority_seam01_dispatch.py``.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R2)
+"""
+
+from __future__ import annotations
+
+import shutil
+import tempfile
+from datetime import UTC, datetime
+from pathlib import Path
+from typing import Any
+from unittest import TestCase
+
+from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
+from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
+    apply_lifecycle_transition_atomic,
+)
+
+from .incident_store_sqlite_seam_helpers import make_candidate
+
+_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+
+
+def _populate(store: SQLiteIncidentStore) -> str:
+    """Create one incident and return its id."""
+    candidate = make_candidate(name="diag-loop-test-pod")
+    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+    incidents = store.promote_candidates([candidate], observed_at)
+    return str(incidents[0].incident_id)
+
+
+def _payload_completed(review_packet_name: str = "review.json") -> dict[str, Any]:
+    return {
+        "review_packet_name": review_packet_name,
+        "checks_requested": 1,
+        "checks_run": 1,
+        "checks_rejected": 0,
+        "decision": "stop_root_cause_found",
+    }
+
+
+class TestSQLiteLifecycleIdempotencyAtomic(TestCase):
+    """The atomic apply path: one transaction, three outcomes."""
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_first_apply_returns_applied_with_replay_false(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        fingerprint = "fp-completed-001"
+        result = apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-1",
+            collector_run_id="collector-1",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(result["outcome"], "applied")
+        self.assertFalse(result["idempotent_replay"])
+        self.assertIsNotNone(result.get("incident"))
+
+    def test_replay_with_same_fingerprint_returns_replay_true(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        fingerprint = "fp-completed-002"
+        first = apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-1",
+            collector_run_id="collector-1",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(first["outcome"], "applied")
+
+        second = apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-1",
+            collector_run_id="collector-1",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(second["outcome"], "applied")
+        self.assertTrue(second["idempotent_replay"])
+
+    def test_same_key_different_fingerprint_returns_replay_mismatch(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        first = apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-1",
+            collector_run_id="collector-1",
+            fingerprint="fp-a",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed("review-a.json"),
+        )
+        self.assertEqual(first["outcome"], "applied")
+
+        second = apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-1",
+            collector_run_id="collector-1",
+            fingerprint="fp-b",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed("review-b.json"),
+        )
+        self.assertEqual(second["outcome"], "replay_mismatch")
+
+    def test_unknown_incident_returns_incident_not_found(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        # No population; the incident id is absent.
+        result = apply_lifecycle_transition_atomic(
+            store,
+            transition="started",
+            incident_id="missing-incident",
+            run_id="run-1",
+            collector_run_id="collector-1",
+            fingerprint="fp-missing",
+            occurred_at=_OCCURRED_AT,
+            payload={},
+        )
+        self.assertEqual(result["outcome"], "incident_not_found")
+
+
+class TestSQLiteLifecycleIdempotencyRestartDurable(TestCase):
+    """Idempotency record survives closing and reopening the store."""
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_record_survives_store_close_and_reopen(self) -> None:
+        # 1. Open store, populate, apply one transition.
+        first_store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(first_store)
+        fingerprint = "fp-restart"
+        first = apply_lifecycle_transition_atomic(
+            first_store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-restart",
+            collector_run_id="collector-restart",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(first["outcome"], "applied")
+        self.assertFalse(first["idempotent_replay"])
+        # Simulate a backend restart by discarding the in-memory
+        # store instance. The SQLite file on disk still has the
+        # idempotency record.
+        del first_store
+
+        # 2. Open a brand-new store instance against the same file.
+        second_store = SQLiteIncidentStore(self._db_path)
+
+        # 3. Re-deliver the exact same transition. The durable
+        # idempotency record must cause a replay, NOT a fresh apply.
+        second = apply_lifecycle_transition_atomic(
+            second_store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-restart",
+            collector_run_id="collector-restart",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(second["outcome"], "applied")
+        self.assertTrue(
+            second["idempotent_replay"],
+            "second process should collapse to replay after restart",
+        )
+
+
+class TestSQLiteLifecycleIdempotencyMultiProcess(TestCase):
+    """Two independent store instances simulate two backend processes.
+
+    The in-process ``_write_lock`` does not protect across processes;
+    the SQLite ``BEGIN IMMEDIATE`` does. We prove the contract by
+    opening two stores against the same SQLite file and asserting
+    that exactly one apply + one replay happen even though the two
+    stores never share a Python lock.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_two_stores_one_apply_one_replay(self) -> None:
+        # Process A opens the database, populates an incident, and
+        # applies the lifecycle transition. Process B opens the
+        # same file independently and replays the transition.
+        process_a = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(process_a)
+        fingerprint = "fp-multi-process"
+
+        a_result = apply_lifecycle_transition_atomic(
+            process_a,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-mp",
+            collector_run_id="collector-mp",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(a_result["outcome"], "applied")
+        self.assertFalse(a_result["idempotent_replay"])
+
+        # Process B starts "fresh": different in-memory cache, no
+        # Python-level shared state with process A.
+        process_b = SQLiteIncidentStore(self._db_path)
+        b_result = apply_lifecycle_transition_atomic(
+            process_b,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-mp",
+            collector_run_id="collector-mp",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(b_result["outcome"], "applied")
+        self.assertTrue(
+            b_result["idempotent_replay"],
+            "Process B should observe the durable idempotency record",
+        )
+
+        # Cross-process event count must be exactly one applied
+        # transition. Two ``append_event`` calls would be visible
+        # here; exactly one means the mutation ran once.
+        #
+        # The event_type string follows the canonical
+        # ``IncidentEventType`` enum value
+        # (``incident.diagnosis_loop_completed``). The R3 patch
+        # routes the lifecycle apply through the canonical event
+        # writer so this column value is the same as for events
+        # appended via ``mark_diagnosis_loop_completed_impl``.
+        with process_b._connect() as conn:
+            cursor = conn.execute(
+                "SELECT COUNT(*) FROM incident_events "
+                "WHERE incident_id = ? "
+                "AND event_type = 'incident.diagnosis_loop_completed'",
+                (incident_id,),
+            )
+            (count,) = cursor.fetchone()
+        self.assertEqual(
+            count,
+            1,
+            "exactly one incident.diagnosis_loop_completed event must exist across both processes",
+        )
+
+        # Idempotency row count must be exactly one (no double-write).
+        with process_b._connect() as conn:
+            cursor = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency "
+                "WHERE incident_id = ? AND transition = 'completed'",
+                (incident_id,),
+            )
+            (idem_count,) = cursor.fetchone()
+        self.assertEqual(
+            idem_count,
+            1,
+            "exactly one idempotency record must exist across both processes",
+        )
+
+
+class TestSQLiteLifecycleIdempotencyAtomicity(TestCase):
+    """The mutation and the idempotency record land in one transaction."""
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_event_and_idempotency_record_both_present(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-atomic",
+            collector_run_id="collector-atomic",
+            fingerprint="fp-atomic",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+
+        # Canonical ``IncidentEventType`` value:
+        # ``incident.diagnosis_loop_completed``.
+        with store._connect() as conn:
+            ev_count = conn.execute(
+                "SELECT COUNT(*) FROM incident_events "
+                "WHERE incident_id = ? "
+                "AND event_type = 'incident.diagnosis_loop_completed'",
+                (incident_id,),
+            ).fetchone()[0]
+            idem_count = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency "
+                "WHERE incident_id = ? AND transition = 'completed'",
+                (incident_id,),
+            ).fetchone()[0]
+        self.assertEqual(ev_count, 1)
+        self.assertEqual(idem_count, 1)
+
+    def test_incident_not_found_writes_no_event_and_no_record(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        result = apply_lifecycle_transition_atomic(
+            store,
+            transition="started",
+            incident_id="never-existed",
+            run_id="run-x",
+            collector_run_id="collector-x",
+            fingerprint="fp-x",
+            occurred_at=_OCCURRED_AT,
+            payload={},
+        )
+        self.assertEqual(result["outcome"], "incident_not_found")
+
+        with store._connect() as conn:
+            ev_count = conn.execute(
+                "SELECT COUNT(*) FROM incident_events",
+            ).fetchone()[0]
+            idem_count = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency",
+            ).fetchone()[0]
+        self.assertEqual(ev_count, 0)
+        self.assertEqual(idem_count, 0)
+
+
+class TestSQLiteLifecycleIdempotencyConcurrency(TestCase):
+    """Concurrent in-process apply calls collapse to one apply + N-1 replays.
+
+    The store's in-process ``_write_lock`` still gates Python-level
+    access; the test proves that overlap from many threads produces
+    the same observable idempotency contract as the single-process
+    path.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_concurrent_threads_one_apply_n_minus_one_replays(self) -> None:
+        import threading
+
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        fingerprint = "fp-concurrent"
+        payload = _payload_completed()
+
+        n = 8
+        results: list[dict[str, Any]] = []
+        results_lock = threading.Lock()
+        barrier = threading.Barrier(n)
+
+        def deliver() -> None:
+            barrier.wait()
+            r = apply_lifecycle_transition_atomic(
+                store,
+                transition="completed",
+                incident_id=incident_id,
+                run_id="run-conc",
+                collector_run_id="collector-conc",
+                fingerprint=fingerprint,
+                occurred_at=_OCCURRED_AT,
+                payload=payload,
+            )
+            with results_lock:
+                results.append(r)
+
+        threads = [threading.Thread(target=deliver) for _ in range(n)]
+        for t in threads:
+            t.start()
+        for t in threads:
+            t.join()
+
+        outcomes = [r["outcome"] for r in results]
+        self.assertTrue(all(o == "applied" for o in outcomes))
+        replays = [r["idempotent_replay"] for r in results]
+        self.assertEqual(replays.count(False), 1)
+        self.assertEqual(replays.count(True), n - 1)
+
+        # Canonical ``IncidentEventType`` value:
+        # ``incident.diagnosis_loop_completed``.
+        with store._connect() as conn:
+            ev_count = conn.execute(
+                "SELECT COUNT(*) FROM incident_events "
+                "WHERE incident_id = ? "
+                "AND event_type = 'incident.diagnosis_loop_completed'",
+                (incident_id,),
+            ).fetchone()[0]
+            idem_count = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency "
+                "WHERE incident_id = ? AND transition = 'completed'",
+                (incident_id,),
+            ).fetchone()[0]
+        self.assertEqual(ev_count, 1)
+        self.assertEqual(idem_count, 1)
+
+
+__all__ = [
+    "TestSQLiteLifecycleIdempotencyAtomic",
+    "TestSQLiteLifecycleIdempotencyRestartDurable",
+    "TestSQLiteLifecycleIdempotencyMultiProcess",
+    "TestSQLiteLifecycleIdempotencyAtomicity",
+    "TestSQLiteLifecycleIdempotencyConcurrency",
+]
\ No newline at end of file

=== tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3.py ===
diff --git a/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3.py b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3.py
new file mode 100644
index 00000000..a0d68720
--- /dev/null
+++ b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3.py
@@ -0,0 +1,356 @@
+"""R3 regression tests for SQLite lifecycle idempotency (core).
+
+Closes R3-1, R3-5, R3-6 blockers from the
+``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:
+
+* **R3-1** — existing v1 production databases must upgrade in
+  place so the lifecycle endpoint does not crash with
+  ``no such table: lifecycle_idempotency``.
+* **R3-5** — the UNIQUE index must still enforce uniqueness when
+  ``diagnosis_run_id`` is ``NULL``.
+* **R3-6** — a fault injected between event append and idempotency
+  insert must roll back the event, projection, and cache.
+
+Companion files split for LLM-friendly size limits:
+
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3_apply.py``
+  — R3-2 lifecycle-applies projection/cache updates.
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3_events.py``
+  — R3-3 hash-chain tests.
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py``
+  — R3-4 capability-seam tests.
+
+The tests rely on the canonical
+:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`
+path that the R2 module now delegates to.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R3)
+"""
+
+from __future__ import annotations
+
+import shutil
+import sqlite3
+import tempfile
+from datetime import UTC, datetime
+from pathlib import Path
+from typing import Any
+from unittest import TestCase
+
+from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
+from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
+    apply_lifecycle_transition_atomic,
+)
+
+from .incident_store_sqlite_seam_helpers import make_candidate
+
+_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+
+
+def _populate(store: SQLiteIncidentStore) -> str:
+    """Create one incident and return its id."""
+    candidate = make_candidate(name="diag-loop-test-pod")
+    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+    incidents = store.promote_candidates([candidate], observed_at)
+    return str(incidents[0].incident_id)
+
+
+def _payload_completed(review_packet_name: str = "review.json") -> dict[str, Any]:
+    return {
+        "review_packet_name": review_packet_name,
+        "checks_requested": 1,
+        "checks_run": 1,
+        "checks_rejected": 0,
+        "decision": "stop_root_cause_found",
+    }
+
+
+class TestR3SchemaUpgrade(TestCase):
+    """R3-1: Existing v1 databases upgrade in place to v2.
+
+    Builds a genuine v1 schema (no ``lifecycle_idempotency`` table),
+    records ``SCHEMA_VERSION = 1`` in ``schema_migrations``, then
+    reopens the file with the new code and asserts that the table
+    + index are installed and that ``schema_migrations`` is bumped
+    to ``2``.
+    """
+
+    def test_v1_database_upgrades_to_v2_with_table_and_index(self) -> None:
+        temp_dir = tempfile.mkdtemp()
+        db_path = Path(temp_dir) / "v1_production.sqlite3"
+        try:
+            from k8s_diag_agent.collect import (
+                incident_store_sqlite_schema as schema_module,
+            )
+
+            v1_init_statements = [
+                schema_module.CREATE_SCHEMA_MIGRATIONS,
+                schema_module.CREATE_INCIDENT_EVENTS,
+                schema_module.CREATE_EVENTS_INDICES,
+                schema_module.CREATE_INCIDENT_CURRENT,
+                schema_module.CREATE_CURRENT_INDICES,
+                schema_module.CREATE_TRIGGERS,
+            ]
+            with sqlite3.connect(str(db_path)) as conn:
+                for stmt in v1_init_statements:
+                    conn.executescript(stmt)
+                conn.execute(
+                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
+                    (1, "2025-01-01T00:00:00+00:00"),
+                )
+                conn.commit()
+                tables = {
+                    row[0] for row in conn.execute(
+                        "SELECT name FROM sqlite_master WHERE type='table'"
+                    ).fetchall()
+                }
+            self.assertNotIn(
+                "lifecycle_idempotency",
+                tables,
+                "v1-shaped database must not have lifecycle_idempotency yet",
+            )
+
+            # Reopen the database with the new code. ``run_migrations``
+            # sees ``current_version = 1 < SCHEMA_VERSION = 2`` and
+            # applies the v2 upgrade (CREATE TABLE IF NOT EXISTS
+            # lifecycle_idempotency + the COALESCE-based UNIQUE
+            # index).
+            SQLiteIncidentStore(db_path)
+
+            with sqlite3.connect(str(db_path)) as conn:
+                tables_after = {
+                    row[0] for row in conn.execute(
+                        "SELECT name FROM sqlite_master WHERE type='table'"
+                    ).fetchall()
+                }
+                indexes_after = {
+                    row[0] for row in conn.execute(
+                        "SELECT name FROM sqlite_master WHERE type='index'"
+                    ).fetchall()
+                }
+                recorded_version = conn.execute(
+                    "SELECT MAX(version) FROM schema_migrations"
+                ).fetchone()[0]
+
+            self.assertIn(
+                "lifecycle_idempotency",
+                tables_after,
+                "lifecycle_idempotency table must be added by the v2 upgrade",
+            )
+            self.assertIn(
+                "idx_lifecycle_idempotency_key",
+                indexes_after,
+                "lifecycle_idempotency unique index must be added by the v2 upgrade",
+            )
+            self.assertGreaterEqual(int(recorded_version), 2)
+        finally:
+            shutil.rmtree(temp_dir, ignore_errors=True)
+
+
+class TestR3Rollback(TestCase):
+    """R3-6: Fault between event append and idempotency insert must
+    roll back the event, projection, and cache.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_idempotency_insert_failure_rolls_back_everything(self) -> None:
+        from unittest import mock
+
+        from k8s_diag_agent.collect import (
+            incident_store_sqlite_context as context_module,
+        )
+
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+
+        with store._connect() as conn:
+            ev_count_before = conn.execute(
+                "SELECT COUNT(*) FROM incident_events"
+            ).fetchone()[0]
+            idem_count_before = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency"
+            ).fetchone()[0]
+            projection_before = conn.execute(
+                "SELECT current_state_json FROM incident_current "
+                "WHERE incident_id = ?",
+                (incident_id,),
+            ).fetchone()[0]
+        cache_before = (
+            store._incidents[incident_id].to_dict()
+            if incident_id in store._incidents
+            else None
+        )
+
+        def _failing_insert(*args: Any, **kwargs: Any) -> None:
+            raise sqlite3.OperationalError(
+                "injected fault: idempotency insert"
+            )
+
+        with mock.patch.object(
+            context_module,
+            "_insert_lifecycle_idempotency_row",
+            side_effect=_failing_insert,
+        ):
+            result = apply_lifecycle_transition_atomic(
+                store,
+                transition="completed",
+                incident_id=incident_id,
+                run_id="run-rb",
+                collector_run_id="collector-rb",
+                fingerprint="fp-rb",
+                occurred_at=_OCCURRED_AT,
+                payload=_payload_completed(),
+            )
+
+        self.assertEqual(result["outcome"], "persistence_failed")
+        self.assertIn("idempotency", result.get("detail", ""))
+
+        with store._connect() as conn:
+            ev_count_after = conn.execute(
+                "SELECT COUNT(*) FROM incident_events"
+            ).fetchone()[0]
+            idem_count_after = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency"
+            ).fetchone()[0]
+            projection_after = conn.execute(
+                "SELECT current_state_json FROM incident_current "
+                "WHERE incident_id = ?",
+                (incident_id,),
+            ).fetchone()[0]
+        self.assertEqual(
+            ev_count_after,
+            ev_count_before,
+            "event row must be rolled back when idempotency insert fails",
+        )
+        self.assertEqual(
+            idem_count_after,
+            idem_count_before,
+            "idempotency row must not be present",
+        )
+        self.assertEqual(
+            projection_after,
+            projection_before,
+            "incident_current projection must be unchanged",
+        )
+
+        cache_after = (
+            store._incidents[incident_id].to_dict()
+            if incident_id in store._incidents
+            else None
+        )
+        self.assertEqual(cache_after, cache_before)
+
+
+class TestR3MultiProcessRegression(TestCase):
+    """R3 cross-check: the canonical path preserves the multi-process
+    one-apply-one-replay contract.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_two_stores_one_apply_one_replay_through_canonical_path(self) -> None:
+        process_a = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(process_a)
+        fingerprint = "fp-mp-r3"
+
+        a_result = apply_lifecycle_transition_atomic(
+            process_a,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-mp-r3",
+            collector_run_id="collector-mp-r3",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(a_result["outcome"], "applied")
+        self.assertFalse(a_result["idempotent_replay"])
+
+        process_b = SQLiteIncidentStore(self._db_path)
+        b_result = apply_lifecycle_transition_atomic(
+            process_b,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-mp-r3",
+            collector_run_id="collector-mp-r3",
+            fingerprint=fingerprint,
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(b_result["outcome"], "applied")
+        self.assertTrue(b_result["idempotent_replay"])
+
+        with process_b._connect() as conn:
+            (event_count,) = conn.execute(
+                "SELECT COUNT(*) FROM incident_events "
+                "WHERE incident_id = ? "
+                "AND event_type = 'incident.diagnosis_loop_completed'",
+                (incident_id,),
+            ).fetchone()
+            (idem_count,) = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency "
+                "WHERE incident_id = ? AND transition = 'completed'",
+                (incident_id,),
+            ).fetchone()
+        self.assertEqual(event_count, 1)
+        self.assertEqual(idem_count, 1)
+
+
+class TestR3SchemaUniqueness(TestCase):
+    """R3-5: NULL ``diagnosis_run_id`` must still participate in the
+    UNIQUE constraint. The COALESCE expression in the index makes
+    NULL compare equal to ``''``.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_duplicate_null_diagnosis_run_id_is_rejected(self) -> None:
+        SQLiteIncidentStore(self._db_path)
+        with sqlite3.connect(str(self._db_path)) as conn:
+            conn.execute(
+                """
+                INSERT INTO lifecycle_idempotency (
+                    incident_id, transition, collector_run_id,
+                    diagnosis_run_id, fingerprint, occurred_at, applied_at
+                ) VALUES (?, ?, ?, NULL, 'fp-1',
+                          '2026-01-01T00:00:00+00:00',
+                          '2026-01-01T00:00:00+00:00')
+                """,
+                ("inc-1", "started", "collector-1"),
+            )
+            with self.assertRaises(sqlite3.IntegrityError):
+                conn.execute(
+                    """
+                    INSERT INTO lifecycle_idempotency (
+                        incident_id, transition, collector_run_id,
+                        diagnosis_run_id, fingerprint, occurred_at, applied_at
+                    ) VALUES (?, ?, ?, NULL, 'fp-2',
+                              '2026-01-01T00:00:00+00:00',
+                              '2026-01-01T00:00:00+00:00')
+                    """,
+                    ("inc-1", "started", "collector-1"),
+                )
+
+
+__all__ = [
+    "TestR3SchemaUpgrade",
+    "TestR3Rollback",
+    "TestR3MultiProcessRegression",
+    "TestR3SchemaUniqueness",
+]

=== tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_apply.py ===
diff --git a/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_apply.py b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_apply.py
new file mode 100644
index 00000000..4af95cbf
--- /dev/null
+++ b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_apply.py
@@ -0,0 +1,263 @@
+"""R3 regression tests for SQLite lifecycle idempotency (apply path).
+
+Closes R3-2 from the
+``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:
+
+* **R3-2** — ``started`` / ``failed`` / ``completed`` must
+  immediately update the canonical projection atomically, and
+  the state must survive close + reopen.
+
+Companion files:
+
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3.py`` — R3-1,
+  R3-5, R3-6, multi-process.
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3_events.py``
+  — R3-3 hash chain.
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py``
+  — R3-4 capability seam.
+
+The tests rely on the canonical
+:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`
+path that the R2 module now delegates to.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R3)
+"""
+
+from __future__ import annotations
+
+import json
+import shutil
+import tempfile
+from datetime import UTC, datetime
+from pathlib import Path
+from typing import Any, cast
+from unittest import TestCase
+
+from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
+from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
+    apply_lifecycle_transition_atomic,
+)
+
+from .incident_store_sqlite_seam_helpers import make_candidate
+
+_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+
+
+def _populate(store: SQLiteIncidentStore) -> str:
+    """Create one incident and return its id."""
+    candidate = make_candidate(name="diag-loop-test-pod")
+    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+    incidents = store.promote_candidates([candidate], observed_at)
+    return str(incidents[0].incident_id)
+
+
+def _payload_completed(review_packet_name: str = "review.json") -> dict[str, Any]:
+    return {
+        "review_packet_name": review_packet_name,
+        "checks_requested": 1,
+        "checks_run": 1,
+        "checks_rejected": 0,
+        "decision": "stop_root_cause_found",
+    }
+
+
+def _payload_started() -> dict[str, Any]:
+    return {}
+
+
+def _payload_failed() -> dict[str, Any]:
+    return {"unavailable_reason": "captures-unavailable"}
+
+
+def _read_projection_state(
+    store: SQLiteIncidentStore, incident_id: str
+) -> dict[str, Any]:
+    """Return the parsed ``current_state_json`` for an incident.
+
+    Returns an empty dict if no projection row exists so callers
+    can ``.get("diagnosis_loop")`` without a None check.
+    """
+    with store._connect() as conn:
+        row = conn.execute(
+            "SELECT current_state_json FROM incident_current "
+            "WHERE incident_id = ?",
+            (incident_id,),
+        ).fetchone()
+    if row is None or row[0] is None:
+        return {}
+    return cast(dict[str, Any], json.loads(row[0]))
+
+
+def _require_diag_loop(
+    store: SQLiteIncidentStore, incident_id: str
+) -> dict[str, Any]:
+    """Return the ``diagnosis_loop`` block from the projection row.
+
+    The canonical lifecycle apply mutates ``incident_current`` in
+    the same transaction as the event insert + idempotency record
+    insert. The ``diagnosis_loop`` block lives in
+    ``current_state_json`` because the in-memory ``Incident`` model
+    does not (yet) carry it as a typed attribute. Reading the
+    projection is the canonical way to verify the canonical path
+    actually wrote the lifecycle state.
+    """
+    state = _read_projection_state(store, incident_id)
+    diag_loop = state.get("diagnosis_loop")
+    assert diag_loop is not None, (
+        f"projection row for {incident_id!r} must include "
+        f"diagnosis_loop block; got {state!r}"
+    )
+    return cast(dict[str, Any], diag_loop)
+
+
+class TestR3LifecycleAppliesUpdateCacheAndProjection(TestCase):
+    """R3-2: ``started`` / ``failed`` / ``completed`` must update
+    the canonical projection atomically, and the state must
+    survive close + reopen.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_started_immediately_updates_projection(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        apply_lifecycle_transition_atomic(
+            store,
+            transition="started",
+            incident_id=incident_id,
+            run_id="run-started",
+            collector_run_id="collector-started",
+            fingerprint="fp-started",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_started(),
+        )
+
+        diag_loop = _require_diag_loop(store, incident_id)
+        self.assertEqual(diag_loop["status"], "running")
+        self.assertEqual(diag_loop["run_id"], "run-started")
+        self.assertEqual(diag_loop["collector_run_id"], "collector-started")
+
+    def test_failed_immediately_updates_projection(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        apply_lifecycle_transition_atomic(
+            store,
+            transition="failed",
+            incident_id=incident_id,
+            run_id="run-failed",
+            collector_run_id="collector-failed",
+            fingerprint="fp-failed",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_failed(),
+        )
+
+        diag_loop = _require_diag_loop(store, incident_id)
+        self.assertEqual(diag_loop["status"], "failed")
+        self.assertEqual(diag_loop["run_id"], "run-failed")
+        self.assertEqual(
+            diag_loop["unavailable_reason"], "captures-unavailable"
+        )
+
+    def test_completed_immediately_updates_projection(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-completed",
+            collector_run_id="collector-completed",
+            fingerprint="fp-completed",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+
+        diag_loop = _require_diag_loop(store, incident_id)
+        self.assertEqual(diag_loop["status"], "completed")
+        self.assertEqual(diag_loop["review_packet_name"], "review.json")
+        self.assertEqual(diag_loop["checks_run"], 1)
+        self.assertEqual(diag_loop["decision"], "stop_root_cause_found")
+
+    def test_state_survives_close_and_reopen(self) -> None:
+        first_store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(first_store)
+        apply_lifecycle_transition_atomic(
+            first_store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-persist",
+            collector_run_id="collector-persist",
+            fingerprint="fp-persist",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed("review-persist.json"),
+        )
+        del first_store
+
+        second_store = SQLiteIncidentStore(self._db_path)
+        diag_loop = _require_diag_loop(second_store, incident_id)
+        self.assertEqual(diag_loop["status"], "completed")
+        self.assertEqual(diag_loop["review_packet_name"], "review-persist.json")
+
+    def test_incident_current_advances_atomically(self) -> None:
+        """R3-2: ``current_state_json`` and ``last_event_seq`` both
+        advance in the same transaction.
+        """
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+
+        with store._connect() as conn:
+            row_before = conn.execute(
+                "SELECT current_state_json, last_event_seq "
+                "FROM incident_current WHERE incident_id = ?",
+                (incident_id,),
+            ).fetchone()
+        last_event_seq_before = int(row_before[1])
+
+        apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-adv",
+            collector_run_id="collector-adv",
+            fingerprint="fp-adv",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+
+        with store._connect() as conn:
+            row_after = conn.execute(
+                "SELECT current_state_json, last_event_seq "
+                "FROM incident_current WHERE incident_id = ?",
+                (incident_id,),
+            ).fetchone()
+            diag_event = conn.execute(
+                "SELECT event_seq FROM incident_events "
+                "WHERE incident_id = ? "
+                "AND event_type = 'incident.diagnosis_loop_completed'",
+                (incident_id,),
+            ).fetchone()
+        last_event_seq_after = int(row_after[1])
+        current_state = cast(dict[str, Any], json.loads(row_after[0]))
+
+        self.assertEqual(
+            last_event_seq_after,
+            int(diag_event[0]),
+            "incident_current.last_event_seq must equal the new event's event_seq",
+        )
+        self.assertGreater(
+            last_event_seq_after,
+            last_event_seq_before,
+            "last_event_seq must advance after a lifecycle apply",
+        )
+        self.assertIn("diagnosis_loop", current_state)
+        self.assertEqual(current_state["diagnosis_loop"]["status"], "completed")
+
+
+__all__ = [
+    "TestR3LifecycleAppliesUpdateCacheAndProjection",
+]
\ No newline at end of file

=== tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_events.py ===
diff --git a/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_events.py b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_events.py
new file mode 100644
index 00000000..a01cb1b4
--- /dev/null
+++ b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_events.py
@@ -0,0 +1,165 @@
+"""R3 regression tests for SQLite lifecycle idempotency (events).
+
+Closes R3-3 from the
+``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:
+
+* **R3-3** — the canonical event append must use the hash chain.
+  The full event chain must pass ``verify_hash_chain`` and a
+  subsequent canonical event must still link correctly.
+
+Companion files:
+
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3.py`` — R3-1,
+  R3-2, R3-5, R3-6.
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py`` —
+  R3-4 capability seam.
+
+The tests rely on the canonical
+:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`
+path that the R2 module now delegates to.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R3)
+"""
+
+from __future__ import annotations
+
+import shutil
+import tempfile
+from datetime import UTC, datetime
+from pathlib import Path
+from unittest import TestCase
+
+from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
+from k8s_diag_agent.collect.incident_store_sqlite_events import (
+    IncidentEventActor,
+    IncidentEventType,
+    verify_hash_chain,
+)
+from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
+    apply_lifecycle_transition_atomic,
+)
+
+from .incident_store_sqlite_seam_helpers import make_candidate
+
+_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+
+
+def _populate(store: SQLiteIncidentStore) -> str:
+    """Create one incident and return its id."""
+    candidate = make_candidate(name="diag-loop-test-pod")
+    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+    incidents = store.promote_candidates([candidate], observed_at)
+    return str(incidents[0].incident_id)
+
+
+def _payload_completed() -> dict[str, object]:
+    return {
+        "review_packet_name": "review.json",
+        "checks_requested": 1,
+        "checks_run": 1,
+        "checks_rejected": 0,
+        "decision": "stop_root_cause_found",
+    }
+
+
+class TestR3HashChain(TestCase):
+    """R3-3: The canonical event writer must produce valid hash
+    chains. A subsequent canonical event must still link correctly.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_full_chain_passes_verify_hash_chain(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-hash",
+            collector_run_id="collector-hash",
+            fingerprint="fp-hash",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+
+        events = store.get_incident_events(incident_id, limit=1000)
+        events_sorted = sorted(events, key=lambda e: e.aggregate_version)
+        self.assertTrue(
+            verify_hash_chain(events_sorted),
+            "complete incident event chain must pass verify_hash_chain",
+        )
+
+    def test_lifecycle_event_has_real_sha256(self) -> None:
+        """R3-3: ``payload_sha256``, ``previous_event_sha256``, and
+        ``event_sha256`` are real hashes, NOT the empty placeholders
+        the R2 patch emitted.
+        """
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-sha",
+            collector_run_id="collector-sha",
+            fingerprint="fp-sha",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        with store._connect() as conn:
+            row = conn.execute(
+                "SELECT event_id, payload_sha256, previous_event_sha256, "
+                "event_sha256 FROM incident_events "
+                "WHERE incident_id = ? "
+                "AND event_type = 'incident.diagnosis_loop_completed'",
+                (incident_id,),
+            ).fetchone()
+        self.assertNotEqual(row[1], "")
+        self.assertNotEqual(row[2], "")
+        self.assertNotEqual(row[3], "")
+
+    def test_normal_canonical_event_after_lifecycle_links_correctly(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+        apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-link",
+            collector_run_id="collector-link",
+            fingerprint="fp-link",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+
+        follow_up_at = datetime(2026, 7, 12, 11, 0, 0, tzinfo=UTC)
+        with store._write_context() as ctx:
+            stored = ctx.append_event(
+                incident_id=incident_id,
+                event_type=IncidentEventType.SIGNAL_OBSERVED,
+                actor=IncidentEventActor.SYSTEM,
+                payload={
+                    "last_observed_at": follow_up_at.isoformat(),
+                    "signal_count": 2,
+                    "signals": [],
+                },
+                occurred_at=follow_up_at,
+            )
+        self.assertIsNotNone(stored.event_sha256)
+        self.assertNotEqual(stored.event_sha256, "")
+        self.assertNotEqual(stored.payload_sha256, "")
+
+        events = store.get_incident_events(incident_id, limit=1000)
+        sorted_events = sorted(events, key=lambda e: e.aggregate_version)
+        self.assertTrue(verify_hash_chain(sorted_events))
+
+
+__all__ = [
+    "TestR3HashChain",
+]
\ No newline at end of file

=== tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py ===
diff --git a/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py
new file mode 100644
index 00000000..e940a339
--- /dev/null
+++ b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r3_seam.py
@@ -0,0 +1,176 @@
+"""R3 regression tests for SQLite lifecycle idempotency (capability seam).
+
+Closes R3-4 from the
+``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:
+
+* **R3-4** — the implementation must use the canonical write
+  context, not raw ``store._write_lock`` / ``store._connect()`` /
+  ``store._incidents`` / ``store._snapshot_incident()`` access.
+
+Companion files:
+
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3.py`` — R3-1,
+  R3-2, R3-5, R3-6.
+* ``test_incident_store_sqlite_lifecycle_idempotency_r3_events.py``
+  — R3-3 hash chain.
+
+The tests rely on the canonical
+:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`
+path that the R2 module now delegates to.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R3)
+"""
+
+from __future__ import annotations
+
+import ast
+import shutil
+import tempfile
+from datetime import UTC, datetime
+from pathlib import Path
+from typing import Any
+from unittest import TestCase, mock
+
+from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
+from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
+    apply_lifecycle_transition_atomic,
+)
+
+from .incident_store_sqlite_seam_helpers import make_candidate
+
+_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+
+
+def _populate(store: SQLiteIncidentStore) -> str:
+    """Create one incident and return its id."""
+    candidate = make_candidate(name="diag-loop-test-pod")
+    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+    incidents = store.promote_candidates([candidate], observed_at)
+    return str(incidents[0].incident_id)
+
+
+def _payload_completed() -> dict[str, object]:
+    return {
+        "review_packet_name": "review.json",
+        "checks_requested": 1,
+        "checks_run": 1,
+        "checks_rejected": 0,
+        "decision": "stop_root_cause_found",
+    }
+
+
+class TestR3CapabilitySeam(TestCase):
+    """R3-4: The lifecycle apply must go through
+    ``SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently``.
+    No raw ``_write_lock`` / ``_connect`` / ``_incidents`` /
+    ``_snapshot_incident`` access from outside the seam.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_apply_uses_canonical_write_context_method(self) -> None:
+        from k8s_diag_agent.collect import (
+            incident_store_sqlite_context as context_module,
+        )
+
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+
+        captured = {"called": False}
+
+        def _spy_apply(self: Any, *args: Any, **kwargs: Any) -> Any:
+            captured["called"] = True
+            return _original_apply(self, *args, **kwargs)
+
+        _original_apply = (
+            context_module.SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently
+        )
+
+        with mock.patch.object(
+            context_module.SQLiteWriteContext,
+            "apply_diagnosis_lifecycle_idempotently",
+            _spy_apply,
+        ):
+            apply_lifecycle_transition_atomic(
+                store,
+                transition="completed",
+                incident_id=incident_id,
+                run_id="run-seam",
+                collector_run_id="collector-seam",
+                fingerprint="fp-seam",
+                occurred_at=_OCCURRED_AT,
+                payload=_payload_completed(),
+            )
+
+        self.assertTrue(
+            captured["called"],
+            "apply_lifecycle_transition_atomic must invoke the canonical context method",
+        )
+
+    def test_adapter_module_does_not_reach_into_private_store_state(self) -> None:
+        """Static AST check: the adapter module must not call
+        ``store._write_lock``, ``store._connect(...)``,
+        ``store._incidents``, ``store._snapshot_incident(...)``, or
+        ``store._state_to_incident(...)``. The check inspects the
+        parsed AST (not the docstring) so module documentation
+        that mentions these names for context does NOT count as a
+        violation.
+        """
+        from k8s_diag_agent.collect import (
+            incident_store_sqlite_lifecycle_idempotency as adapter,
+        )
+
+        source = Path(adapter.__file__).read_text(encoding="utf-8")
+        tree = ast.parse(source)
+
+        forbidden_attrs = (
+            "_write_lock",
+            "_incidents",
+            "_snapshot_incident",
+            "_state_to_incident",
+        )
+        forbidden_calls = ("_connect",)
+        violations: list[str] = []
+
+        def _walk(node: ast.AST) -> None:
+            for child in ast.iter_child_nodes(node):
+                # Detect ``store._connect(...)`` calls.
+                if (
+                    isinstance(child, ast.Call)
+                    and isinstance(child.func, ast.Attribute)
+                    and child.func.attr in forbidden_calls
+                    and isinstance(child.func.value, ast.Name)
+                    and child.func.value.id == "store"
+                ):
+                    violations.append(
+                        f"call store.{child.func.attr}(...) at line {child.lineno}"
+                    )
+                # Detect ``store._write_lock`` etc. attribute reads.
+                if (
+                    isinstance(child, ast.Attribute)
+                    and child.attr in forbidden_attrs
+                    and isinstance(child.value, ast.Name)
+                    and child.value.id == "store"
+                ):
+                    violations.append(
+                        f"access store.{child.attr} at line {child.lineno}"
+                    )
+                _walk(child)
+
+        _walk(tree)
+        self.assertEqual(
+            violations,
+            [],
+            "adapter must not reach into private store members: "
+            + "; ".join(violations),
+        )
+
+
+__all__ = [
+    "TestR3CapabilitySeam",
+]
\ No newline at end of file

=== tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4.py ===
diff --git a/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4.py b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4.py
new file mode 100644
index 00000000..60594af6
--- /dev/null
+++ b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4.py
@@ -0,0 +1,280 @@
+"""R4 regression tests for SQLite lifecycle idempotency (cache authority).
+
+Companion to ``test_incident_store_sqlite_lifecycle_idempotency_r4_concurrency``.
+Split to keep both files under the LLM-friendly 500-line limit.
+
+Closes R4-1, R4-2a, R4-4 blockers from the
+``ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01`` review:
+
+* **R4-1** — the canonical ``apply_diagnosis_lifecycle_idempotently``
+  path must prove incident existence against the durable
+  ``incident_current`` projection inside the ``BEGIN IMMEDIATE``
+  transaction. The process-local cache is a per-process Python dict
+  and cannot prove absence across processes.
+
+* **R4-2a** — pre-opened store regression. Process B's cache is
+  loaded before process A promotes the incident. The lifecycle
+  request landing on B must still apply (not be classified
+  ``incident_not_found``) because the projection row exists.
+
+* **R4-4** — the typed ``Incident.diagnosis_loop`` field carries the
+  projection's lifecycle state through
+  :meth:`SQLiteIncidentStore.get_incident` after a successful apply,
+  so cache/detail reads expose the lifecycle state rather than
+  dropping it.
+
+The canonical path under test is
+:meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently` /
+:func:`k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency.apply_lifecycle_transition_atomic`.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R4)
+"""
+
+from __future__ import annotations
+
+import shutil
+import sqlite3
+import tempfile
+from datetime import UTC, datetime
+from pathlib import Path
+from typing import Any
+from unittest import TestCase
+
+from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
+from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
+    apply_lifecycle_transition_atomic,
+)
+
+from .incident_store_sqlite_seam_helpers import make_candidate
+
+_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+
+
+def _populate(store: SQLiteIncidentStore) -> str:
+    """Create one incident and return its id."""
+    candidate = make_candidate(name="r4-diag-loop-test-pod")
+    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+    incidents = store.promote_candidates([candidate], observed_at)
+    return str(incidents[0].incident_id)
+
+
+def _payload_completed(review_packet_name: str = "review.json") -> dict[str, Any]:
+    return {
+        "review_packet_name": review_packet_name,
+        "checks_requested": 1,
+        "checks_run": 1,
+        "checks_rejected": 0,
+        "decision": "stop_root_cause_found",
+    }
+
+
+# =============================================================================
+# R4-1 + R4-2a: Pre-opened store cache defect
+# =============================================================================
+
+
+class TestR4CacheAuthorityIsProjectionNotCache(TestCase):
+    """R4-1 / R4-2a: process B's cache must not be authoritative.
+
+    The previous canonical path used ``self._cache.get(incident_id)``
+    as the existence check. In a multi-process deployment, B's cache
+    is loaded at process start from the projection; if A promotes an
+    incident after B opens, B's cache does not contain it. The old
+    code short-circuited to ``incident_not_found`` and dropped the
+    lifecycle request silently.
+
+    This test opens B BEFORE A promotes, runs the lifecycle request
+    through B, and asserts the durable state was written.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_lifecycle_apply_on_pre_opened_store_with_empty_cache(self) -> None:
+        # 1. Process B opens the store before the incident exists
+        #    on disk. Its cache is empty.
+        process_b = SQLiteIncidentStore(self._db_path)
+        self.assertEqual(
+            len(process_b._incidents),
+            0,
+            "precondition: B's cache must be empty",
+        )
+
+        # 2. Process A promotes the incident. A's cache is updated;
+        #    B's cache is NOT (separate process-local dict).
+        process_a = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(process_a)
+        self.assertIn(incident_id, process_a._incidents)
+        self.assertNotIn(
+            incident_id,
+            process_b._incidents,
+            "precondition: B's cache must still be empty after A promotes",
+        )
+
+        # 3. The lifecycle request lands on process B. Under the old
+        #    code, B's ``self._cache.get(incident_id)`` returned None
+        #    and the apply short-circuited to ``incident_not_found``.
+        #    Under the R4 fix, B queries ``incident_current`` inside
+        #    the transaction and finds the row.
+        result = apply_lifecycle_transition_atomic(
+            process_b,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-r4-pre-open",
+            collector_run_id="collector-r4-pre-open",
+            fingerprint="fp-r4-pre-open",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+
+        self.assertEqual(
+            result["outcome"],
+            "applied",
+            "pre-opened store must apply the lifecycle transition by querying "
+            "incident_current, not its stale cache",
+        )
+        self.assertFalse(result["idempotent_replay"])
+
+        # 4. Durable state was written.
+        with process_b._connect() as conn:
+            (event_count,) = conn.execute(
+                "SELECT COUNT(*) FROM incident_events "
+                "WHERE incident_id = ? "
+                "AND event_type = 'incident.diagnosis_loop_completed'",
+                (incident_id,),
+            ).fetchone()
+            (idem_count,) = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency "
+                "WHERE incident_id = ? AND transition = 'completed'",
+                (incident_id,),
+            ).fetchone()
+            projection = conn.execute(
+                "SELECT current_state_json FROM incident_current "
+                "WHERE incident_id = ?",
+                (incident_id,),
+            ).fetchone()
+        self.assertEqual(event_count, 1)
+        self.assertEqual(idem_count, 1)
+        self.assertIsNotNone(projection)
+        self.assertIn(
+            "diagnosis_loop",
+            projection[0],
+            "incident_current must carry the diagnosis_loop projection",
+        )
+
+    def test_lifecycle_apply_on_unknown_incident_returns_not_found(self) -> None:
+        """The SQL existence check must still reject truly absent incidents.
+
+        If the projection row is absent, the canonical path MUST roll
+        back and return ``incident_not_found``. This guards against
+        accidentally accepting any incident_id by relying on the
+        database query instead of the cache.
+        """
+        store = SQLiteIncidentStore(self._db_path)
+        result = apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id="default-pod-does-not-exist-crash_loop",
+            run_id="run-r4-missing",
+            collector_run_id="collector-r4-missing",
+            fingerprint="fp-r4-missing",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(result["outcome"], "incident_not_found")
+
+        # No durable rows were written.
+        with sqlite3.connect(str(self._db_path)) as conn:
+            (ev,) = conn.execute(
+                "SELECT COUNT(*) FROM incident_events"
+            ).fetchone()
+            (idem,) = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency"
+            ).fetchone()
+        self.assertEqual(ev, 0)
+        self.assertEqual(idem, 0)
+
+
+# =============================================================================
+# R4-4: Typed diagnosis_loop field is exposed on the cache
+# =============================================================================
+
+
+class TestR4TypedDiagnosisLoopField(TestCase):
+    """R4-4: ``Incident.diagnosis_loop`` carries the lifecycle state.
+
+    The R3 close report claimed "the cache is refreshed from the
+    projector". The dataclass did NOT have a typed ``diagnosis_loop``
+    field, so the cache reconstructed through ``_state_to_incident``
+    dropped the projection's lifecycle state. This test asserts that
+    the typed field IS populated on the cached Incident AND on the
+    detail-endpoint read after a canonical apply.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_apply_hydrates_typed_diagnosis_loop_on_cached_incident(self) -> None:
+        store = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(store)
+
+        # Pre-apply: typed field is None.
+        self.assertIsNone(store._incidents[incident_id].diagnosis_loop)
+
+        result = apply_lifecycle_transition_atomic(
+            store,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-r4-typed",
+            collector_run_id="collector-r4-typed",
+            fingerprint="fp-r4-typed",
+            occurred_at=_OCCURRED_AT,
+            payload={
+                "review_packet_name": "r4-review.json",
+                "checks_requested": 3,
+                "checks_run": 3,
+                "checks_rejected": 0,
+                "decision": "stop_root_cause_found",
+            },
+        )
+        self.assertEqual(result["outcome"], "applied")
+
+        # 1. The returned Incident carries the typed field.
+        returned = result["incident"]
+        self.assertIsNotNone(returned)
+        self.assertIsNotNone(returned.diagnosis_loop)
+        self.assertEqual(returned.diagnosis_loop.get("status"), "completed")
+        self.assertEqual(
+            returned.diagnosis_loop.get("review_packet_name"),
+            "r4-review.json",
+        )
+
+        # 2. The cached Incident (read via the public API) carries it.
+        cached = store._incidents[incident_id]
+        self.assertIsNotNone(cached.diagnosis_loop)
+        self.assertEqual(cached.diagnosis_loop.get("status"), "completed")
+
+        # 3. The detail-endpoint read (``store.get_incident``) carries it.
+        detail = store.get_incident(incident_id)
+        self.assertIsNotNone(detail)
+        self.assertIsNotNone(detail.diagnosis_loop)
+        self.assertEqual(detail.diagnosis_loop.get("status"), "completed")
+
+        # 4. Round-trip: ``to_dict`` -> ``from_dict`` preserves it.
+        rebuilt = store._state_to_incident(cached.to_dict())
+        self.assertIsNotNone(rebuilt.diagnosis_loop)
+        self.assertEqual(rebuilt.diagnosis_loop.get("status"), "completed")
+
+
+__all__ = [
+    "TestR4CacheAuthorityIsProjectionNotCache",
+    "TestR4TypedDiagnosisLoopField",
+]
\ No newline at end of file

=== tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4_concurrency.py ===
diff --git a/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4_concurrency.py b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4_concurrency.py
new file mode 100644
index 00000000..39c9201a
--- /dev/null
+++ b/tests/unit/test_incident_store_sqlite_lifecycle_idempotency_r4_concurrency.py
@@ -0,0 +1,270 @@
+"""R4 regression tests for SQLite lifecycle idempotency (concurrency).
+
+Companion to ``test_incident_store_sqlite_lifecycle_idempotency_r4``.
+Split out to keep both files under the LLM-friendly 500-line limit.
+
+Covers:
+
+* **R4-2b** — overlapping concurrent stores. Two independent stores
+  held open by two threads must serialize through ``BEGIN IMMEDIATE``
+  so the canonical ``one apply + one replay`` contract holds even
+  when both writers reach the canonical method simultaneously.
+
+* **R4-3** — idempotent replay on a process with a stale cache must
+  heal that cache so the next read of the cached ``Incident``
+  reflects the durable lifecycle state, not the stale pre-apply
+  view.
+
+Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R4)
+"""
+
+from __future__ import annotations
+
+import shutil
+import sqlite3
+import tempfile
+import threading
+from datetime import UTC, datetime
+from pathlib import Path
+from typing import Any
+from unittest import TestCase
+
+from k8s_diag_agent.collect.incident_store_sqlite import SQLiteIncidentStore
+from k8s_diag_agent.collect.incident_store_sqlite_lifecycle_idempotency import (
+    apply_lifecycle_transition_atomic,
+)
+
+from .incident_store_sqlite_seam_helpers import make_candidate
+
+# Local copies of the small test fixtures used by the core R4 file.
+# We duplicate them here to avoid importing underscore-prefixed
+# helpers across files (and to keep the concurrency file
+# self-contained for tooling that introspects it).
+_OCCURRED_AT = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
+
+
+def _populate(store: SQLiteIncidentStore) -> str:
+    """Create one incident and return its id."""
+    candidate = make_candidate(name="r4-diag-loop-test-pod")
+    observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
+    incidents = store.promote_candidates([candidate], observed_at)
+    return str(incidents[0].incident_id)
+
+
+def _payload_completed(review_packet_name: str = "review.json") -> dict[str, Any]:
+    return {
+        "review_packet_name": review_packet_name,
+        "checks_requested": 1,
+        "checks_run": 1,
+        "checks_rejected": 0,
+        "decision": "stop_root_cause_found",
+    }
+
+# =============================================================================
+# R4-3: Replay refreshes the stale cache
+# =============================================================================
+
+
+class TestR4ReplayRefreshesStaleCache(TestCase):
+    """R4-3: idempotent replay must heal the local cache.
+
+    When process A applies the original lifecycle and process B
+    (whose cache is empty or stale) handles the retry, B's
+    ``self._cache`` must reflect the durable projection row after
+    the replay returns. The previous code committed the empty write
+    transaction and returned ``{"outcome": "applied",
+    "idempotent_replay": True}`` without refreshing the cache, so B
+    could read a stale view of the incident for the rest of its
+    lifetime.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_replay_on_pre_opened_store_heals_cache(self) -> None:
+        # 1. B opens before the incident exists.
+        process_b = SQLiteIncidentStore(self._db_path)
+
+        # 2. A promotes the incident and applies the lifecycle.
+        process_a = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(process_a)
+
+        a_result = apply_lifecycle_transition_atomic(
+            process_a,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-r4-replay",
+            collector_run_id="collector-r4-replay",
+            fingerprint="fp-r4-replay",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(a_result["outcome"], "applied")
+        self.assertFalse(a_result["idempotent_replay"])
+
+        # 3. B is still empty. The replay lands on B.
+        self.assertNotIn(incident_id, process_b._incidents)
+
+        b_result = apply_lifecycle_transition_atomic(
+            process_b,
+            transition="completed",
+            incident_id=incident_id,
+            run_id="run-r4-replay",
+            collector_run_id="collector-r4-replay",
+            fingerprint="fp-r4-replay",
+            occurred_at=_OCCURRED_AT,
+            payload=_payload_completed(),
+        )
+        self.assertEqual(b_result["outcome"], "applied")
+        self.assertTrue(b_result["idempotent_replay"])
+
+        # 4. R4-3: B's cache MUST now contain the incident with the
+        #    typed ``diagnosis_loop`` state hydrated from the
+        #    projection.
+        self.assertIn(
+            incident_id,
+            process_b._incidents,
+            "replay must heal B's cache by refreshing from the projection",
+        )
+        b_cached = process_b._incidents[incident_id]
+        self.assertIsNotNone(
+            b_cached.diagnosis_loop,
+            "replay must hydrate the typed diagnosis_loop field on B's cache",
+        )
+        self.assertEqual(
+            b_cached.diagnosis_loop.get("status"),
+            "completed",
+        )
+
+        # 5. Detail endpoint must also expose the same state.
+        b_get = process_b.get_incident(incident_id)
+        self.assertIsNotNone(b_get)
+        self.assertIsNotNone(b_get.diagnosis_loop)
+        self.assertEqual(b_get.diagnosis_loop.get("status"), "completed")
+
+
+# =============================================================================
+# R4-2b: Overlapping concurrent stores (barrier-based contention)
+# =============================================================================
+
+
+class TestR4OverlappingConcurrentStores(TestCase):
+    """R4-2b: two stores held open by two threads contend concurrently.
+
+    The existing R3 multi-process test opens the second store AFTER
+    the first one writes, so it cannot expose ordering problems. This
+    test holds BOTH stores open simultaneously, points both at the
+    same database, has both threads enter the canonical write context,
+    and verifies that exactly one applies while the other replays.
+
+    The 3-party barrier ensures both writers AND the main thread
+    release together, so both workers reach the critical section
+    simultaneously and ``BEGIN IMMEDIATE`` serialization is exercised
+    rather than coincidental sequential writes.
+    """
+
+    def setUp(self) -> None:
+        self._temp_dir = tempfile.mkdtemp()
+        self._db_path = Path(self._temp_dir) / "test_incidents.sqlite3"
+
+    def tearDown(self) -> None:
+        shutil.rmtree(self._temp_dir, ignore_errors=True)
+
+    def test_two_stores_contend_concurrently_for_lifecycle_apply(self) -> None:
+        # Single incident populated before the contended apply.
+        primer = SQLiteIncidentStore(self._db_path)
+        incident_id = _populate(primer)
+
+        # Two stores opened in parallel, both pointing at the same DB.
+        store_a = SQLiteIncidentStore(self._db_path)
+        store_b = SQLiteIncidentStore(self._db_path)
+
+        # Same fingerprint on both threads so the second one to commit
+        # MUST classify as ``idempotent_replay``. A mismatch would
+        # yield ``replay_mismatch``.
+        fingerprint = "fp-r4-concurrent"
+
+        # 3-party barrier so the main thread also waits alongside the
+        # workers; otherwise the barrier would break because only 2
+        # worker parties are required.
+        barrier = threading.Barrier(3)
+        go = threading.Event()
+
+        results: dict[str, dict[str, Any]] = {}
+        errors: dict[str, BaseException] = {}
+
+        def _worker(name: str, store: SQLiteIncidentStore) -> None:
+            try:
+                # Both threads pause here until the main thread
+                # joins the barrier, ensuring they reach the
+                # canonical write context within microseconds of
+                # each other.
+                barrier.wait(timeout=10.0)
+                go.wait(timeout=10.0)
+                results[name] = apply_lifecycle_transition_atomic(
+                    store,
+                    transition="completed",
+                    incident_id=incident_id,
+                    run_id="run-r4-concurrent",
+                    collector_run_id="collector-r4-concurrent",
+                    fingerprint=fingerprint,
+                    occurred_at=_OCCURRED_AT,
+                    payload=_payload_completed(),
+                )
+            except BaseException as exc:  # noqa: BLE001
+                errors[name] = exc
+
+        thread_a = threading.Thread(
+            target=_worker, args=("a", store_a), name="r4-store-a"
+        )
+        thread_b = threading.Thread(
+            target=_worker, args=("b", store_b), name="r4-store-b"
+        )
+        thread_a.start()
+        thread_b.start()
+        # Main thread participates in the barrier so all three
+        # parties release together; this guarantees both workers
+        # are inside the critical section before we set ``go``.
+        barrier.wait(timeout=10.0)
+        go.set()
+        thread_a.join(timeout=15.0)
+        thread_b.join(timeout=15.0)
+
+        self.assertFalse(errors, f"workers raised: {errors}")
+        self.assertEqual(set(results), {"a", "b"})
+
+        outcomes = sorted(
+            (r["outcome"], r.get("idempotent_replay", False))
+            for r in results.values()
+        )
+        self.assertEqual(
+            outcomes,
+            [("applied", False), ("applied", True)],
+            "exactly one thread must apply and exactly one must replay",
+        )
+
+        # Durable state: one event row, one idempotency row.
+        with sqlite3.connect(str(self._db_path)) as conn:
+            (event_count,) = conn.execute(
+                "SELECT COUNT(*) FROM incident_events "
+                "WHERE incident_id = ? "
+                "AND event_type = 'incident.diagnosis_loop_completed'",
+                (incident_id,),
+            ).fetchone()
+            (idem_count,) = conn.execute(
+                "SELECT COUNT(*) FROM lifecycle_idempotency "
+                "WHERE incident_id = ? AND transition = 'completed'",
+                (incident_id,),
+            ).fetchone()
+        self.assertEqual(event_count, 1)
+        self.assertEqual(idem_count, 1)
+
+
+__all__ = [
+    "TestR4ReplayRefreshesStaleCache",
+    "TestR4OverlappingConcurrentStores",
+]

## Workflow anchors
