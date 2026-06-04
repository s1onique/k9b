# App.tsx Source Map — Remaining Ownership Analysis

**Generated:** 2026-06-05  
**Status:** ACT 1 Completed — `findExecutionHistoryEntry` extraction

---

## Current line count

| File | Lines | Change |
|------|------:|-------:|
| `frontend/src/App.tsx` (before) | 794 | — |
| `frontend/src/App.tsx` (after) | 760 | **-34** |

---

## Remaining Sections

| Lines | Section | Responsibility | Classification |
|-------|---------|----------------|----------------|
| 1-62 | App imports | Type re-exports, utility re-exports, persistence keys | ✓ Well organized |
| 63-160 | Compatibility exports | Backward compatibility exports for tests | ✓ Stable |
| 169-185 | `useRunControl` call | RunControl owns selected-run causal chain | ✓ Extracted |
| 194-226 | `useRunSelection` call | Pagination/filter/navigation helpers | ✓ Extracted |
| 231-239 | Auto-refresh timer | App-level refresh coordination via poll() | ✓ Kept inline |
| 250-270 | `useAppData` call | Fleet, proposals, cluster detail, refresh | ✓ Extracted |
| 276-300 | `useUIState` call | UI state (tabs, filters, highlights) | ✓ Extracted |
| 306-330 | `useQueueState` call | Queue filtering/sorting/grouping | ✓ Extracted |
| **333-335** | **executionHistory derivation** | **State pass-through to hooks** | **Keep inline** |
| **336** | **Batch execution handlers** | **5-line prop wiring** | **Acceptable** |
| **338** | **Run selection handlers** | **3-line prop wiring** | **Acceptable** |
| **340** | **Cluster selection handlers** | **5-line prop wiring** | **Acceptable** |
| 342-353 | `useAppNavigationHighlights` call | Navigation highlight coordination | ✓ Extracted |
| 355-368 | `useAppManualExecutionHandlers` call | Manual execution state/handlers | ✓ Extracted |
| 370-380 | `refresh` callback | App-level refresh wrapper coordination | ✓ Kept inline |
| 382-391 | `useApprovalFlowController` call | Elm-ish approval state machine | ✓ Extracted |
| **393-394** | **`buildPromotionKey` helper** | **2-line string interpolation** | **Keep inline** |
| **396-399** | **`toggleIncidentExpansion`** | **State handler (incident expansion)** | **Keep inline** |
| **401** | **queueExplanation derivation** | **3-line data pass-through** | **Keep inline** |
| **403-409** | **Queue filter handlers** | **`toggleQueueFocusPreset`, `resetQueueFilters`, `resetQueueView`** | **CANDIDATE** |
| 411-423 | `useAppHeaderProps` call | Header freshness, stats | ✓ Extracted |
| 425-433 | `useAppDemoShellOverlayProps` call | Demo shell state (called once) | ✓ Extracted |
| 438-459 | `useAppClusterDetailSectionProps` call | Cluster detail prop construction | Prop-wiring ~22 lines |
| **461-490** | **Planner data derivation** | **Plan candidates, clusters, variants** | **CANDIDATE** |
| 492-499 | `useAppClusterFocusHandler` call | Cluster focus coordination | ✓ Extracted |
| 501-528 | `useAppRunSummaryProps` call | Run summary prop construction | Prop-wiring ~28 lines |
| 530-581 | `useAppQueuePanelProps` call | Queue panel prop construction | Prop-wiring ~52 lines |
| 583-594 | `useAppProposalSectionProps` call | Proposal section props | ✓ Extracted |
| 596-607 | `useAppWorkNextChecksLaneProps` call | Work lane props | ✓ Extracted |
| 609-633 | `useAppRecentRunsPanelProps` call | Recent runs props | ✓ Extracted |
| 635-652 | `useAppDiagnosePanelsProps` call | Diagnose panels props | ✓ Extracted |
| 654-760 | JSX render + export | Component rendering | ✓ No extraction possible |

---

## Extraction Candidates

| Candidate | Type | Est. Net Reduction | Risk | Tests | Recommendation |
|-----------|------|-------------------:|------|-------|----------------|
| `findExecutionHistoryEntry` (L336-368) | **Utility extraction (DCE)** | ~30 lines → **✓ DONE** | Low | 18 unit tests | **COMPLETED** |
| Queue filter handlers (L403-409) | **State seam** | ~20 lines | Low | Verify queue reset | **ACCEPT** — creates `useQueueFilterHandlers` |
| Planner data derivation (L461-490) | **Derived data seam** | ~16 lines | Low | Verify plan data | **ACCEPT** — creates `usePlannerDataProps` |
| `useAppQueuePanelProps` args | Prop-wiring | ~52 lines | Low | Existing tests | **DEFER** — prop-passing overhead not worth it |
| `useAppRunSummaryProps` args | Prop-wiring | ~28 lines | Low | Existing tests | **DEFER** — same as above |
| `useAppClusterDetailSectionProps` args | Prop-wiring | ~22 lines | Low | Existing tests | **DEFER** — same as above |

---

## Rejected Candidates

| Candidate | Reason for Rejection |
|-----------|---------------------|
| `VmAlertPanels` prop wrapper | Would increase App.tsx (import/hook-call overhead > prop lines saved) |
| `AppFleetSection` prop wrapper | Counterproductive — increases App.tsx line count |
| `AppRunSummarySection` args | Prop-wiring only, <10 net lines, hook already exists |
| Small handler wrappers (batch, run selection, cluster selection) | <10 net lines, already extracted to stable hooks |

---

## Recommended Next ACTs

### ACT 2: Extract queue filter handlers to `useQueueFilterHandlers`

- **Expected reduction:** ~20 lines (760 → ~740)
- **Risk:** Low — state wiring already stable
- **Tests needed:** Verify queue filter reset, focus preset, and view reset behavior unchanged
- **Seam type:** Behavior/state ownership — creates queue filter seam

### ACT 3: Extract planner data derivation to `usePlannerDataProps`

- **Expected reduction:** ~16 lines (740 → ~724)
- **Risk:** Low — derived data only
- **Tests needed:** Verify plan candidate counts, cluster lists, variant counts unchanged
- **Seam type:** Derived data seam — separates planner data computation from prop wiring

### ACT 4: (Deferred) Prop-wiring consolidation

- **Status:** Deferred — all prop-wiring candidates are <10 net lines after extraction overhead
- **Rationale:** Decision rule: "Prop-wiring extraction must reduce App.tsx by at least 10 net lines"
- **May revisit** when more state seams become available

---

## Verified Extraction: `findExecutionHistoryEntry`

### Files Changed

| File | Change |
|------|--------|
| `frontend/src/app/findExecutionHistoryEntry.ts` | **Created** — pure utility function |
| `frontend/src/App.tsx` | **Modified** — removed 33-line inline function, added import with wrapper |
| `frontend/src/app/findExecutionHistoryEntry.test.ts` | **Created** — 18 unit tests |

### Test Results

```
 Test Files  74 passed (74)
      Tests  1510 passed (1510)
   Duration  18.59s
```

### Verification

| Check | Status |
|-------|--------|
| No code behavior changes | ✓ Confirmed |
| `useAppDemoShellOverlayProps` called exactly once | ✓ Confirmed (line 425) |
| 10+ net line reduction for DCE extraction | ✓ 34 lines saved |
| All frontend tests pass | ✓ 1510 tests |
| Utility function is pure (testable) | ✓ 18 unit tests |

---

## Impact Scan Ledger

| Change | Impact Scan Status |
|--------|-------------------|
| `findExecutionHistoryEntry` extraction | **Skipped** — utility extraction, DCE, no behavior change |

**For ACT 2-3:** Impact scan will be updated when behavior/state seam extractions are performed.

---

## Progress Summary

| Target | Before | After | Change |
|--------|-------:|------:|-------:|
| App.tsx < 500 lines | 794 | 760 | -34 (7%) |
| Remaining to target | — | 260 | — |
| Next ACT expected | — | ~740 | ~20 |

**Estimated total reduction through ACT 2-3:** ~50 lines → App.tsx ~710 lines