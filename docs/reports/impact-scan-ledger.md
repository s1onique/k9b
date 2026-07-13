# Impact Scan Effectiveness Ledger

**Purpose:** Track whether the impact-scan discipline reduces surprise, scope drift, reviewer friction, and missed test targeting.

**Principles:**

- Impact scans are derived evidence, not source of truth.
- The ledger measures workflow usefulness, not static-analysis correctness.
- The goal is to reduce surprise, scope drift, reviewer friction, and missed tests.
- The ledger is optional retrospective evidence, not a mandatory blocker for every trivial edit.

## Entry Template

```markdown
### YYYY-MM-DD — <ACT title>

- Target:
- Impact scan required: yes/no
- Impact scan present: yes/no
- Script used: yes/no
- Manual refinement present: yes/no
- Planned files:
- Changed files:
- Unexpected changed files:
- Likely tests identified by script:
- Likely tests identified manually:
- Targeted tests run:
- Full gate run:
- Reviewer scope objection: yes/no
- Reviewer requested missing scan: yes/no
- Script usefulness: useful/noisy/misleading/not-used
- Did the scan reduce surprise: yes/no/mixed
- Notes:
```

## Ledger Fields Summary

| Field | What it measures |
|-------|------------------|
| Script usefulness | Whether the rg-based script was worth running |
| Did the scan reduce surprise | Core measurement: did the scan help? |
| Reviewer scope objection | Did the reviewer object to scope? |
| Unexpected changed files | Scope drift indicator |
| Targeted tests run | Test targeting effectiveness |
| Likely tests identified (script vs manual) | Script vs human refinement value |

## How to Judge After 5–10 ACTs

Across 5+ non-trivial ACTs, consider the discipline useful if:

- **>= 80%** of non-trivial edits include an impact map or explicit skip rationale.
- **<= 20%** have reviewer scope objections.
- **<= 20%** have unexpected changed files not explained in the close report.
- **>= 60%** list at least one useful targeted test before the full gate.
- **0** cases introduce DB/watcher/MCP/graph/AST/tree-sitter creep.

## Kill / Shrink Criterion

If the ledger shows the scan is mostly cargo cult, noisy, or not reducing surprise, shrink or remove the ceremony instead of making the tool heavier. Prefer evolution based on evidence over escalation of tooling complexity.

## Entries

### 2026-07-12 — ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 R4 close

- Target: SQLite lifecycle idempotency — close R4-1, R4-2, R4-3, R4-4 blockers from the R3 review (cache authority defect, missing multi-process regressions, replay cache healing, typed `diagnosis_loop` projection boundary).
- Impact scan required: yes
- Impact scan present: yes
- Script used: no (manual `git grep` + review-trace against the R4 findings)
- Manual refinement present: yes
- Planned files: 5 source (`incident_lifecycle.py`, `incident_lifecycle_serialization.py`, `incident_snapshot_helpers.py`, `incident_store_sqlite_context.py`, `incident_store_sqlite_lifecycle.py`), 2 new R4 test files split for size.
- Changed files: 5 source, 2 new R4 test files (split to keep each under the 500-line LLM-friendly threshold).
- Unexpected changed files: none beyond the planned set.
- Likely tests identified by script: n/a (manual review).
- Likely tests identified manually: existing `test_incident_store_sqlite_lifecycle_idempotency*.py` (R3 + base), canonical seam (`test_incident_store_sqlite_*`), `test_incident_diagnosis_authority_run_summary.py`, `test_automatic_diagnosis_backend_promotion_regression.py`.
- Targeted tests run: focused pytest on the R3 + R4 + base lifecycle idempotency test files (28 tests); broader SQLite + automatic-diagnosis capability-seam suites (132 tests).
- Full gate run: `./scripts/verify_all.sh --act-local` → PASS.
- Reviewer scope objection: no (this ACT is the explicit R4 follow-up).
- Reviewer requested missing scan: no.
- Script usefulness: n/a.
- Did the scan reduce surprise: yes — the R4 review named exactly four blockers; each was mapped to one production fix and one regression test.
- Notes:
  - **R4-1 (cache authority is the projection, not the cache)**: `SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently` now proves incident existence with a `SELECT 1 FROM incident_current WHERE incident_id = ?` inside the same `BEGIN IMMEDIATE` transaction. The process-local `self._cache` is no longer authoritative for the existence check, so a pre-opened store whose cache was loaded before another process promoted the incident correctly applies the lifecycle instead of returning `incident_not_found`.
  - **R4-2a (pre-opened store regression)**: New `TestR4CacheAuthorityIsProjectionNotCache::test_lifecycle_apply_on_pre_opened_store_with_empty_cache` opens process B before process A promotes, runs the lifecycle through B, and asserts durable event/projection/idempotency state.
  - **R4-2b (overlapping concurrent stores)**: New `TestR4OverlappingConcurrentStores::test_two_stores_contend_concurrently_for_lifecycle_apply` holds both stores open in two threads, joins both into a 3-party barrier (workers + main) and an explicit `go` event, then verifies exactly one thread applies and the other replays under contention. The R3 multi-process test only exercised sequential stores, so this is a genuinely new regression class.
  - **R4-3 (replay refreshes the stale cache)**: Idempotent replay now calls `self._refresh_cache_from_projection(incident_id)` after the `BEGIN IMMEDIATE` commit so the cache observed by the replay handler reflects the durable projection row, not the stale pre-apply view. `TestR4ReplayRefreshesStaleCache::test_replay_on_pre_opened_store_heals_cache` proves the cache is populated and `store.get_incident()` returns the typed `diagnosis_loop` state on the replaying process.
  - **R4-4 (typed `diagnosis_loop` projection boundary)**: `Incident.diagnosis_loop: dict[str, Any] | None` is now a typed dataclass field. The serializer (`incident_to_dict`/`incident_from_dict`) and the snapshot helper (`incident_snapshot_helpers.snapshot_incident`) round-trip it. `TestR4TypedDiagnosisLoopField::test_apply_hydrates_typed_diagnosis_loop_on_cached_incident` proves the field is populated on the returned Incident, the cached Incident, and the detail-endpoint read. The in-process `mark_diagnosis_loop_*_impl` methods also refresh the cache from the projection after `append_event` so they expose the typed state on the returned Incident.
  - **R4-5 (staged tree)**: `git add -A && git diff --cached --check && git status --short` shows zero untracked files and zero unstaged ACT files. The 38-file diffstat is consistent with the R3 + R4 review scope; the four R3 test files plus the new R4 files plus all production sources plus all related support modules are staged.
  - **Test file split**: 28 R3+R4 tests split across the existing R3 split files plus two new R4 files (`r4.py` core + `r4_concurrency.py` companion) to comply with the 500-line LLM-friendly threshold.
  - **ACT-local fresh evidence**: gate ran after all changes were staged; output timestamp in the next digest will represent this tree.

### 2026-07-12 — ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 R3 close

- Target: SQLite lifecycle idempotency — close R3-1, R3-2, R3-3, R3-4, R3-5, R3-6 blockers from the R2 review.
- Impact scan required: yes
- Impact scan present: yes
- Script used: no (manual `git grep` + `rg` against review findings)
- Manual refinement present: yes
- Planned files: 4 source (`incident_store_sqlite_schema.py`, `incident_store_sqlite_migrations.py`, `incident_store_sqlite_context.py`, `incident_store_sqlite_lifecycle_idempotency.py`), 1 driver test (`test_automatic_diagnosis_backend_promotion_regression.py`), 4 R3 test files.
- Changed files: 6 source/test files (one R2 docstring-only side-effect), 1 unrelated pre-existing R2 test fix, 4 new R3 test files split for size.
- Unexpected changed files: `tests/unit/test_automatic_diagnosis_backend_promotion_regression.py` — the R2 patch removed `check_incident_eligibility` from the processor module and replaced it with `evaluate_incident_eligibility` in `incident_diagnosis_authority_seam`, but the test still patched the old symbol. Confirmed pre-existing R2 regression by reverting R3 changes and re-running.
- Likely tests identified by script: n/a (manual review).
- Likely tests identified manually: existing `test_incident_store_sqlite_lifecycle_idempotency.py`, canonical seam (`test_incident_store_sqlite_*`), auto-diagnosis dispatch regression.
- Targeted tests run: focused pytest on the R3 lifecycle idempotency test files (23 tests); broader SQLite + automatic_diagnosis suites (679 tests).
- Full gate run: `./scripts/verify_all.sh --act-local` → PASS.
- Reviewer scope objection: no.
- Reviewer requested missing scan: no.
- Script usefulness: n/a.
- Did the scan reduce surprise: yes — review listed 10 required R3 tests and 6 specific blockers; both informed the implementation plan.
- Notes:
  - **Schema upgrade (R3-1)**: Bumped `SCHEMA_VERSION` 1 → 2 and added a v2 migration entry that re-applies the lifecycle idempotency table + the COALESCE-based UNIQUE index. v1 databases upgrade in place (covered by `test_v1_database_upgrades_to_v2_with_table_and_index`).
  - **Capability seam (R3-4)**: Replaced the R2 module's direct `_write_lock`/`_connect()`/`_incidents`/`_snapshot_incident()` access with a thin adapter that delegates to the new canonical `SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently` method. The new method owns the full lookup → hash-chained event append → canonical projection → idempotency record sequence in one `BEGIN IMMEDIATE` transaction and refreshes the in-memory cache from the projection on commit.
  - **Hash chain (R3-3)**: The R2 patch wrote empty `payload_sha256` / `previous_event_sha256` / `event_sha256` placeholders; the new canonical path uses `EventBuilder` so the appended event is a real hash-chained link that subsequent canonical events connect to.
  - **NULL uniqueness (R3-5)**: Index now uses `COALESCE(diagnosis_run_id, '')` so NULL participates in uniqueness; lookups mirror the expression.
  - **Rollback proof (R3-6)**: Idempotency insert is a separate module-level helper so tests can monkey-patch it to inject a fault and verify the event row, projection row, and cache all roll back together.
  - **Test file split**: 14 R3 tests split across 4 files to comply with the 500-line LLM-friendly threshold; companion references are documented in each file's docstring.

---

### 2026-06-05 — Planner data derivation extraction

- **Change:** Extracted planner data derivation from `App.tsx` into `frontend/src/app/usePlannerDataProps.ts`.
- **Impact map present:** Yes. ACT prompt identified planner availability, candidate counts, plan status, run plan candidates, discovery variant ordering, and discovered cluster derivation.
- **Scope drift:** `frontend/src/App.tsx` (modified), `frontend/src/app/usePlannerDataProps.ts` (new, 160 lines), `frontend/src/app/usePlannerDataProps.test.ts` (new, 34 tests).
- **Behavior risk:** Planner availability text, candidate count labels, status text, discovered clusters, and discovery variant counts/order must remain unchanged.
- **Targeted tests:** `usePlannerDataProps.test.ts` (34 tests), `app.test.tsx` (120 tests).
- **Result:** All 1544 tests passed. App.tsx reduced from 753 to 747 lines (-6). Build succeeds. Hook preserves all exact planner data derivation behavior.
- **Lesson:** No surprises; extraction stayed surgical. Hook preserves exact plan candidate counts (singular/plural), discovery variant counts, and discovered cluster derivation.

---

### 2026-06-05 — Queue filter handlers extraction

- **Change:** Extracted queue filter/reset handlers from `App.tsx` into `frontend/src/app/useQueueFilterHandlers.ts`.
- **Impact map present:** Yes. ACT prompt identified queue focus preset, filter reset, view reset, and persisted queue view clearing behavior.
- **Scope drift:** `frontend/src/App.tsx` (modified), `frontend/src/app/useQueueFilterHandlers.ts` (new, 114 lines).
- **Behavior risk:** Queue status/cluster filters, focus preset behavior, queue highlighted key reset, and persisted queue view clearing must remain unchanged.
- **Targeted tests:** Queue filter tests (3 files, 25 tests), App tests (10 files, 132 tests).
- **Result:** All tests passed. App.tsx reduced from 760 to 753 lines (-7). Hook preserves exact toggleQueueFocusPreset/resetQueueFilters/resetQueueView behavior.
- **Lesson:** No surprises; extraction stayed surgical. Hook preserves exact handler behavior including persisted queue view clearing.

---

### 2026-06-05 — ClusterDetailSection props extraction

- **Change:** Extracted ClusterDetailSection prop wiring from `App.tsx` into `frontend/src/app/useAppClusterDetailSectionProps.ts`. The hook delegates to `useAppClusterPlanProps` and combines it with direct JSX props.
- **Impact map present:** Yes. ACT prompt identified ClusterDetailSection JSX block (14 props) and clusterPlanProps hook call (14 args) as candidates for consolidation.
- **Scope drift:** `frontend/src/App.tsx` (modified), `frontend/src/app/useAppClusterDetailSectionProps.ts` (new, 128 lines).
- **Behavior risk:** Cluster detail display, cluster selection, tab switching, cluster detail expansion, artifact links, and next-check plan section must remain unchanged.
- **Targeted tests:** `app.test.tsx` (120 tests), cluster detail tests, fleet table tests, demo-shell regression tests.
- **Result:** All 1493 tests passed. App.tsx reduced from 798 to 794 lines (-4). Build succeeds. Hook delegates to existing useAppClusterPlanProps, preserving all behavior.
- **Lesson:** Small but meaningful extraction; the hook overhead is minimal relative to the prop block size. The hook delegates to existing code rather than duplicating logic.

---

### 2026-06-05 — Recent runs panel props extraction

- **Change:** Extracted RecentRunsPanel prop wiring from `App.tsx` into `frontend/src/app/useAppRecentRunsPanelProps.ts`.
- **Impact map present:** Yes. ACT prompt identified run selection, selected-run status, pagination, and batch execution prop wiring.
- **Scope drift:** `frontend/src/App.tsx` (modified), `frontend/src/app/useAppRecentRunsPanelProps.ts` (new, 117 lines).
- **Behavior risk:** Recent run selection, selected-run pagination, RunControl fetch ownership, batch execution button state, and selected-run error/status rendering must remain unchanged.
- **Targeted tests:** `app.test.tsx` (120 tests), recent-runs execution status tests, recent-runs execute button tests, demo-shell regression tests.
- **Result:** All 1422 tests passed. App.tsx reduced from 821 to 800 lines (-21). Removed dead code: NotificationHistoryTable, VmalertDiscoveryPanel, VmalertAlertStatePanel imports; computePageForRunId, highlightExecutionEntry, isLoading, isError, orphanedApprovals, planArtifactLink, outcomeSummary, autoRefreshSelectValue, autoRefreshStatusText, recommendedArtifacts variables.
- **Lesson:** No surprises; extraction stayed surgical. Hook preserves exact RecentRunsPanel lifecycle including stale-while-refresh derivation.

---

### 2026-06-04 — App header props extraction

- **Change:** Extracted App header derived props from `App.tsx` into `frontend/src/app/useAppHeaderProps.ts`.
- **Impact map present:** Yes. ACT prompt identified run identity (headerRunId, headerRunLabel, headerRunTimestamp), freshness (runFresh, runAgeMinutes), latest/past semantics (latestRunRecency, runRecency, isSelectedRunLatest), auto-refresh (autoRefreshInterval, handleAutoRefreshChange), refresh handlers, clickLatest, demo shell realContext dependencies (headerRunTimestamp, runFresh, runAgeMinutes).
- **Scope drift:** `frontend/src/App.tsx` (modified), `frontend/src/app/useAppHeaderProps.ts` (new, 154 lines).
- **Behavior risk:** Header run identity, freshness labels, latest/past badge, refresh/auto-refresh controls, and demo shell `runCapturedAt`/`isFresh` metadata must remain unchanged.
- **Targeted tests:** `app.test.tsx`, demo-shell tests (10 files, 131 tests).
- **Result:** All 1422 tests passed. App.tsx reduced from 837 to 827 lines. New hook is 154 lines. Removed `showLatestJump`, `useRunHeaderModel` import, and direct AppHeader prop construction from App.tsx. Fixed double demo-shell hook call bug (called hook once, combined header props in App.tsx).
- **Lesson:** Hook preserves exact header/freshness/demo metadata behavior. Demo shell now shares single demo-shell state between AppHeader and overlay.

---

### 2026-06-04 — Batch execution handler extraction

- **Change:** Extracted batch execution state and handler logic from `App.tsx` into `frontend/src/app/useAppBatchExecutionHandlers.ts`.
- **Impact map present:** Yes. ACT prompt identified executingBatchRunId, batchExecutionError, handleBatchExecution, runBatchExecution API, and poll/retrySelectedRun interactions.
- **Scope drift:** No unexpected files. Changed `frontend/src/App.tsx` and added `frontend/src/app/useAppBatchExecutionHandlers.ts`.
- **Behavior risk:** Batch execution must preserve run ID loading state, error keying, API payload, and post-execution refresh/poll behavior.
- **Targeted tests:** `app.test.tsx` (120 tests), `recent-runs-execution-status-regression.test.tsx` (12 tests), `recent-runs-execute-button.test.tsx` (6 tests), `recent-runs-navigation-sync.test.tsx` (4 tests).
- **Result:** All 142 tests passed. App.tsx reduced from 863 to 837 lines. New hook is 122 lines. Removed stale `runBatchExecution` import and `useState` from App.tsx imports.
- **Lesson:** No surprises; extraction stayed surgical. Hook preserves exact batch execution lifecycle including API call, poll, retrySelectedRun, and error handling.

---

### 2026-06-04 — Cluster selection handler extraction

- **Change:** Extracted cluster selection / cluster detail expansion handlers from `App.tsx` into `frontend/src/app/useAppClusterSelectionHandlers.ts`.
- **Impact map present:** Yes. ACT prompt identified fleet selection, cluster detail expansion, row highlighting, and focusClusterForNextChecks interactions.
- **Scope drift:** No unexpected files. Changed `frontend/src/App.tsx` and added `frontend/src/app/useAppClusterSelectionHandlers.ts`.
- **Behavior risk:** Cluster row selection, keyboard selection, cluster detail expansion, highlighted row timing, and focus-to-cluster behavior must remain unchanged.
- **Targeted tests:** `app.test.tsx`, fleet table tests, ClusterDetailSection tests, cluster navigation tests, demo-shell smoke.
- **Result:** All 70 test files (1422 tests) passed. App.tsx reduced from 866 to 863 lines. New hook is 60 lines.
- **Lesson:** No surprises; extraction stayed surgical. Hook preserves exact delegation behavior.

---

### 2026-06-04 — Run selection handler extraction

- **Change:** Extracted `handleRunSelectionViaRunControl` from `App.tsx` into `frontend/src/app/useAppRunSelectionHandlers.ts`.
- **Impact map present:** Partial. The ACT prompt described impacted behavior, but the impact-scan ledger was not updated before close.
- **Scope drift:** No unexpected files. Changed `frontend/src/App.tsx` and added `frontend/src/app/useAppRunSelectionHandlers.ts`.
- **Behavior risk:** Run-selection causal chain must remain `runControlSelectRun(runId)` followed by `navigateToPageContainingRun(runId)`.
- **Targeted tests:** `app.test.tsx`, recent-runs navigation sync, selected-run pagination sync, run-control app fetch ownership.
- **Result:** Focused tests passed; TypeScript issue was reported as pre-existing if encountered.
- **Lesson:** Handler extractions affecting UI navigation must update this ledger or include an explicit skip rationale in the close report.

---

### 2026-06-04 — Trial impact scan on App.tsx/component split workflow

- Target: `frontend/src/App.tsx`
- Impact scan required: yes
- Impact scan present: yes
- Script used: yes
- Manual refinement present: yes
- Planned files: 1
- Changed files: 1
- Unexpected changed files: 0
- Likely tests identified by script: 0
- Likely tests identified manually: `app.test.tsx`, `advisory-lower-sections.test.tsx`
- Targeted tests run: `npm run test:ui -- --testNamePattern "App"`
- Full gate run: no
- Reviewer scope objection: no
- Reviewer requested missing scan: no
- Script usefulness: noisy
- Did the scan reduce surprise: mixed
- Notes: Script confirmed the target but was weak for broad target name `App`; manual refinement found relevant tests and narrowed the edit to dead comments only. The final diff stayed surgical.

---


*Add new entries at the top, below this separator.*

### 2026-07-13 — ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 close

- Target: Eliminate global incident churn and diagnosis starvation in backend-owned incident mode.
- Impact scan required: yes
- Impact scan present: yes
- Script used: no (manual `git grep` against the production tree)
- Manual refinement present: yes
- Planned files: ~14 production + ~6 test + ~3 verifier + ~3 docs
- Changed files: see commit
- Unexpected changed files: none
- Likely tests identified manually: scoped promotion unit + budget unit + scheduler-client unit + scoped handler unit + scoped promotion integration
- Targeted tests run: focused pytest on the **71 R3+R3.2-targeted tests** (`tests/verifiers/test_incident_current_run_promotion_workset01.py` 27 + `tests/unit/test_act_k9b_collector_local_review_packet_budget01.py` 15 + `tests/unit/test_act_k9b_incident_current_run_promotion_workset01.py` 13 + `tests/integration/test_act_k9b_incident_current_run_promotion_workset01_e2e.py` 14 = 69, plus 2 cross-suite e2e regression paths inside the budget suite).
- Full gate run: `scripts/verify_all.py --act-local` → **PASS** (17 checks / 0 failed); targeted pytest on the focused suite = **71 passed**.
- **R3.2 negative + regression tests added** (9 cases): ``TestResponseParserRejectsMalformedIds`` (8 negative cases: empty/whitespace/oversized/unsafe/failure.signalId/empty runId/oversized sourceIdentity/actionable whitespace) + ``TestBackendLoggingCardinalities`` (1 cardinality regression asserting the audit event carries explicit signal counts even when categories collapse to 1 incident).
- **R3.3 fix applied**: ``_parse_id_list`` now returns the typed list correctly (was rejecting missing field with ``()`` tuple default as non-list) and the failure loop applies ``_is_safe_id`` to every entry; the malformed-failure test now fails for the *correct* reason (``failure.signalId is malformed``) rather than via a side-effect at the missing-field default.
- Reviewer scope objection: no
- Reviewer requested missing scan: no
- Script usefulness: n/a
- Did the scan reduce surprise: yes — confirmed the new ``/api/internal/incidents/promote-alert-signals`` endpoint, the scheduler backend client, and the new typed contract were consistent across all production call sites
- Notes:
  - **Promotion result contract**: ``PromoteAlertSignalsRequest`` and ``IncidentPromotionResult`` live in ``incident_alert_promotion_contract.py``; the canonical ``actionable_incident_ids`` projection is owned by the result dataclass and consumed by the diagnosis handoff (``_derive_automatic_diagnosis_inputs``).
  - **Scheduler ingestion path**: ``loop_alertmanager_snapshot_signals._ingest_alert_signals`` now calls ``promote_alert_signals_scoped_for_accumulator`` exclusively; the legacy global-scan dispatcher remains only for the manual ``/promote-candidates`` admin path.
  - **Scheduler backend client**: ``SchedulerClient.promote_alert_signals_scoped`` posts the typed ``runId`` / ``sourceIdentity`` / ``signalIds`` payload and returns the new camelCase ``actionableIncidentIds`` projection.
  - **Backend handler**: ``server_incident_internal_handlers.handle_promote_alert_signals`` now uses the typed ``parse_promote_alert_signals_request`` parser and ``promote_scoped_alert_signals``; fail-closed on missing/malformed/cross-source scope.
  - **Collector-local budget**: ``ReviewPacketCreationBudget`` is keyed by ``AutomaticDiagnosisCollectorRunId``; ``record_successful_write`` is the only consumption point; reconstruction filters by exact collector_run_id, not filename, prefix, or health-run id.
  - **Processor wiring**: ``_process_incident`` consults ``budget.can_attempt()`` before ``write_diagnosis_review_packet`` and only charges the budget after a successful write; pre-exhausted budget produces a ``not_eligible: review_packet_budget_exhausted`` skip.
  - **Verifier + self-tests**: ``scripts/verifiers/incident_current_run_promotion_workset01.py`` runs 21 detectors across 11 production modules and is exercised by ``tests/verifiers/test_incident_current_run_promotion_workset01.py`` (27 paired positive/negative self-tests). Wired into ``act_local_verification.py`` as a noarg check.
  - **End-to-end regression**: ``tests/integration/test_act_k9b_incident_current_run_promotion_workset01_e2e.py`` reproduces the production failure (75 historical + 1 current-run) and proves only 1 actionable incident is returned, 75 historical incidents remain untouched, and the budget starts at zero usage.
