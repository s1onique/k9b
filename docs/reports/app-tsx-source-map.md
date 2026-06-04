# App.tsx Source Map — Remaining Ownership Analysis

**Generated:** 2026-06-05  
**Status:** ACT 4 Completed — Source map refresh and DCE

---

## Current line count

| File | Lines | Change from start |
|------|------:|-----------------:|
| `frontend/src/App.tsx` (start) | 1,455 | — |
| `frontend/src/App.tsx` (current) | 747 | **-708 (49%)** |

---

## Remaining Sections

| Lines | Section | Responsibility | Classification |
|-------|---------|----------------|----------------|
| 1-34 | Type imports | ClusterDetailPayload, FleetPayload, LLMPolicy, etc. | ✓ Well organized |
| 36-62 | Component imports | AppHeader, VmAlertPanels, AppDiagnosePanels, etc. | ✓ Well organized |
| 64-73 | Hook imports | useAppRunSummaryProps, usePlannerDataProps, etc. | ✓ Well organized |
| 75-82 | Utils imports | artifactUrl, formatTimestamp, statusClass | ✓ Well organized |
| 82-130 | Selectors imports | confidenceWeight, priorityLabel, etc. | ✓ Well organized |
| 131-160 | Compatibility exports | Backward compatibility exports for tests | ✓ Keep |
| 162-165 | Persistence imports | readStoredSelectedRunId, QUEUE_VIEW_STORAGE_KEY, etc. | ✓ Stable |
| 168-186 | `useRunControl` call | RunControl owns selected-run causal chain | ✓ Extracted |
| 190-227 | `useRunSelection` call | Pagination/filter/navigation helpers | ✓ Extracted |
| 232-240 | Auto-refresh timer | App-level refresh via poll() | ✓ Kept inline |
| 245-271 | `useAppData` call | Fleet, proposals, cluster detail, refresh | ✓ Extracted |
| 276-301 | `useUIState` call | UI state (tabs, filters, highlights) | ✓ Extracted |
| 304-331 | `useQueueState` call | Queue filtering/sorting/grouping | ✓ Extracted |
| 334 | executionHistory derivation | State pass-through to hooks | ✓ Kept inline |
| 336-345 | `useAppBatchExecutionHandlers` | Batch execution state/handlers | ✓ Extracted |
| 347-351 | `useAppRunSelectionHandlers` | Run selection handlers | ✓ Extracted |
| 353-358 | `useAppClusterSelectionHandlers` | Cluster selection handlers | ✓ Extracted |
| 360-375 | `useAppNavigationHighlights` | Navigation highlight coordination | ✓ Extracted |
| 377-391 | `useAppManualExecutionHandlers` | Manual execution state/handlers | ✓ Extracted |
| 393-404 | `refresh` callback | App-level refresh wrapper | ✓ Kept inline |
| 406-415 | `useApprovalFlowController` | Elm-ish approval state machine | ✓ Extracted |
| 417-419 | `buildPromotionKey` helper | 2-line string interpolation | ✓ Keep inline |
| 421-427 | `toggleIncidentExpansion` | State handler (incident expansion) | ✓ Keep inline |
| 429 | queueExplanation derivation | 1-line data pass-through | ✓ Keep inline |
| 431-441 | `useQueueFilterHandlers` call | Queue filter handlers | ✓ Extracted (ACT 2) |
| 443-458 | `useAppHeaderProps` call | Header freshness, stats | ✓ Extracted |
| 460-470 | `useAppDemoShellOverlayProps` call | Demo shell state (called once) | ✓ Extracted |
| 472-476 | appHeaderProps construction | Combines header + demo shell | ✓ Keep inline |
| 478-489 | Progressive loading guard | Critical data loading check | ✓ Keep inline |
| 491-515 | `useAppClusterDetailSectionProps` call | Cluster detail prop construction | ✓ Extracted |
| 517-538 | `usePlannerDataProps` call | Planner data derivation | ✓ Extracted (ACT 3) |
| 540-543 | `buildDeterministicChecksProps` call | Deterministic checks | ✓ Extracted |
| 545-554 | `useAppClusterFocusHandler` call | Cluster focus coordination | ✓ Extracted |
| 556-584 | `useAppRunSummaryProps` call | Run summary prop construction | ✓ Extracted |
| 586-637 | `useAppQueuePanelProps` call | Queue panel prop construction | ✓ Extracted |
| 639-651 | `useAppProposalSectionProps` call | Proposal section props | ✓ Extracted |
| 653-665 | `useAppWorkNextChecksLaneProps` call | Work lane props | ✓ Extracted |
| 667-691 | `useAppRecentRunsPanelProps` call | Recent runs props | ✓ Extracted |
| 693-711 | `useAppDiagnosePanelsProps` call | Diagnose panels props | ✓ Extracted |
| 713-747 | JSX render + export | Component rendering | ✓ No extraction possible |

---

## Completed ACTs

| ACT | Extraction | Lines saved | Status |
|-----|------------|-------------:|--------|
| ACT 1 | `findExecutionHistoryEntry` utility | ~34 | ✓ Done |
| ACT 2 | `useQueueFilterHandlers` (toggleQueueFocusPreset, resetQueueFilters, resetQueueView) | ~20 | ✓ Done |
| ACT 3 | `usePlannerDataProps` (planCandidates, discoveryClusters, etc.) | ~16 | ✓ Done |
| ACT 4 | Source map refresh + DCE verification | 0 | ✓ Done |

**Total reduction:** 708 lines (49% from start)

---

## Extraction Candidates

| Candidate | Type | Est. Net Reduction | Risk | Status |
|-----------|------|-------------------:|------|--------|
| `findExecutionHistoryEntry` (L336-368) | Utility extraction (DCE) | ~34 lines | Low | **DONE** |
| Queue filter handlers (L431-441) | State seam | ~20 lines | Low | **DONE** |
| Planner data derivation (L517-538) | Derived data seam | ~16 lines | Low | **DONE** |
| `useAppQueuePanelProps` args | Prop-wiring | ~52 lines | Low | **DEFER** — <10 net lines |
| `useAppRunSummaryProps` args | Prop-wiring | ~28 lines | Low | **DEFER** — <10 net lines |
| `useAppClusterDetailSectionProps` args | Prop-wiring | ~22 lines | Low | **DEFER** — <10 net lines |
| `buildPromotionKey` (L417-419) | Inline helper | ~3 lines | Low | **REJECT** — <10 net lines |
| `toggleIncidentExpansion` (L421-427) | State handler | ~7 lines | Low | **REJECT** — <10 net lines |
| `queueExplanation` (L429) | Data pass-through | ~1 line | Low | **REJECT** — <10 net lines |
| appHeaderProps construction (L472-476) | Prop wiring | ~5 lines | Low | **REJECT** — <10 net lines |

---

## Rejected Candidates

| Candidate | Reason for Rejection |
|-----------|----------------------|
| `VmAlertPanels` prop wrapper | Would increase App.tsx (import/hook-call overhead > prop lines saved) |
| `AppFleetSection` prop wrapper | Counterproductive — increases App.tsx line count |
| `AppRunSummarySection` args | Prop-wiring only, <10 net lines, hook already exists |
| Small handler wrappers (batch, run selection, cluster selection) | <10 net lines, already extracted to stable hooks |
| `buildPromotionKey` | 3 lines, hook extraction overhead > inline cost |
| `toggleIncidentExpansion` | 7 lines, hook extraction overhead > inline cost |
| `queueExplanation` | 1 line, trivial pass-through |
| appHeaderProps construction | 5 lines, trivial prop combination |

---

## Remaining Extraction Candidates

### Candidate A: Extract `buildPromotionKey` to standalone utility

- **Current:** Inline arrow function (lines 417-419)
- **Size:** 3 lines
- **Risk:** Low — pure function, no external dependencies
- **Net reduction:** ~3 lines (after import overhead)
- **Decision:** **REJECT** — <10 net lines per decision rule

### Candidate B: Extract `toggleIncidentExpansion` to `useIncidentExpansionHandlers`

- **Current:** Inline state handler (lines 421-427)
- **Size:** 7 lines
- **Risk:** Low — React state handler only
- **Net reduction:** ~5 lines (after hook call overhead)
- **Decision:** **DEFER** — borderline, depends on state coupling with App.tsx
- **May revisit** if more incident-related state needs coordination

### Candidate C: Prop-wiring consolidation for `useAppQueuePanelProps`

- **Current:** 52-line argument object (lines 586-637)
- **Risk:** Low — prop wiring only
- **Net reduction:** Likely negative (hook call + import overhead > prop lines saved)
- **Decision:** **DEFER** — per decision rule: "Prop-wiring extraction must reduce App.tsx by at least 10 net lines"

### Candidate D: JSX render block (lines 713-747)

- **Size:** 35 lines
- **Risk:** N/A — component rendering, cannot be extracted
- **Decision:** Keep inline

---

## Recommended Next ACTs

Given the decision rule ("Prop-wiring extraction must reduce App.tsx by at least 10 net lines"), the remaining candidates are all below threshold. The next meaningful extraction requires:

### ACT 5: Investigate state seam opportunities

- **Scope:** Look for groups of related state that could be extracted to stable hooks
- **Potential candidates:**
  - Cluster detail state coordination
  - Queue panel expansion state
  - Proposal panel expansion state
- **Note:** Current prop-wiring hooks are already well-organized

### ACT 6: DCE pass with TypeScript strict mode

- **Scope:** Run TypeScript with --strict to identify unused variables/types
- **Expected:** Potential small DCE wins (unused imports, stale comments)
- **Risk:** Very low — DCE only

### ACT 7: Final source map accuracy check

- **Scope:** Verify all sections are correctly classified
- **Expected:** No changes, documentation only
- **Risk:** None

---

## Test Results

```
Test Files  75 passed (75)
     Tests  1544 passed (1544)
  Duration  13.97s
```

| Check | Status |
|-------|--------|
| No code behavior changes | ✓ Confirmed |
| `useAppDemoShellOverlayProps` called exactly once | ✓ Confirmed (line 460) |
| All frontend tests pass | ✓ 1544 tests |
| Build passes | ✓ vite build succeeded |
| Line count 747 | ✓ Within expected range |

---

## Verification

| Check | Status |
|-------|--------|
| Compatibility exports still used | ✓ Verified via rg |
| `AlertmanagerSnapshotPanel` exported | ✓ 1 test import |
| `AlertmanagerSourcesPanel` exported | ✓ 1 test import |
| `ProposalList` exported | ✓ 1 test import |
| `RecentRunsPanelProps` exported | ✓ Type re-export |
| `RunSummaryPanelProps` exported | ✓ Type re-export |
| `parseNextCheckEntry` exported | ✓ 2 test imports |
| `AUTOREFRESH_STORAGE_KEY` exported | ✓ 2 test imports |
| `QUEUE_VIEW_STORAGE_KEY` exported | ✓ 2 test imports |
| `SELECTED_RUN_STORAGE_KEY` exported | ✓ 2 test imports |
| `formatAgeDuration` exported | ✓ Used in tests |

---

## Progress Summary

| Metric | Value |
|--------|------:|
| App.tsx start | 1,455 lines |
| App.tsx current | 747 lines |
| Total reduction | 708 lines (49%) |
| Target | < 500 lines |
| Remaining to target | 247 lines |
| Hooks extracted | 12 |

**Decision rule note:** Per the task constraint "Prop-wiring extraction must reduce App.tsx by at least 10 net lines or be rejected/reverted", remaining candidates are either:
- Below threshold (prop-wiring hooks)
- Already extracted (queue filter, planner data)
- Cannot be extracted (JSX render, inline helpers)

---

## Impact Scan Ledger

| Change | Impact Scan Status |
|--------|-------------------|
| `findExecutionHistoryEntry` extraction | **Skipped** — utility extraction, DCE, no behavior change |
| `useQueueFilterHandlers` extraction | **Updated** — state seam; ledger entry added in that ACT |
| `usePlannerDataProps` extraction | **Updated** — derived-data seam; ledger entry added in that ACT |
| Source map refresh (this ACT) | **Skipped** — planning/source-map refresh and DCE verification only |

**Status:** No behavior or ownership changes in this ACT.
