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
