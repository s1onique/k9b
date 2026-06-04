# Frontend App Shell Extraction Plan

**File:** `frontend/src/App.tsx`  
**Current line count:** 1594  
**Goal:** Thin composition root (~400–500 lines)  
**Date:** 2026-06-04

---

## Executive Summary

`App.tsx` is the root composition layer but has accumulated responsibilities beyond simple composition. This document audits current responsibilities, identifies extraction seams, and proposes an ordered extraction plan that makes App.tsx smaller, safer, and LLM-friendly without changing behavior.

**Previous extraction work (Phases 1-4):**  
See `frontend/src/hooks/AUDIT_HOOK_EXTRACTION.md` for the hook extraction history. The hooks are already well-factored:

| Hook | Lines | Responsibility |
|------|-------|----------------|
| `useRunSelection` | 641 | Runs pagination, filtering, follow mode, auto-refresh preference |
| `useAppData` | 459 | Fleet, proposals, cluster detail fetch + state |
| `useQueueState` | 514 | Queue filtering, sorting, derived options |
| `useUIState` | 220 | Panel toggles, filter state, sort state, highlights |

---

## 1. What Responsibilities Currently Live in App.tsx

### 1.1 Pure Data Shaping (Lines ~795–1000)

| Item | Type | Purpose |
|------|------|---------|
| `renderLlmStatsLine` | function | Builds LLM stats display line for run header |
| `findingSelectionInput` | `useMemo` | Maps run data → demo shell finding input |
| `queuePanelProps` | `useMemo` | Packages all queue-related props for QueuePanel |
| `headerRunId`, `headerRunLabel`, `runRecency` | derived | Run identity display data |
| `latestRunTimestamp`, `latestRunRecency` | derived | Latest run display data |
| `headerStats`, `runStatsSummary` | derived | Run statistics for header |
| `runSummaryStats` | derived | Cluster/proposal counts for run panel |
| `selectedCluster`, `clusterRecency`, `clusterFresh` | derived | Cluster display metadata |
| `autoRefreshSelectValue`, `autoRefreshStatusText` | derived | Auto-refresh UI text |
| `interpretation`, `recommendedArtifacts`, `clusterTriggerReason` | derived | Cluster detail display data |
| `drilldownAvailability`, `drilldownSummary` | derived | Drilldown status text |
| `planCandidates`, `runPlan`, `orphanedApprovals` | derived | Next-check plan data |
| `plannerAvailability`, `plannerReason`, `plannerHint` | derived | Planner display data |
| `planSummaryText`, `plannerReasonText`, `planCandidateCountLabel` | derived | Plan text snippets |
| `planStatusText`, `outcomeSummary` | derived | Plan status metadata |
| `runPlanCandidates` | derived | Plan candidate list |
| `discoveryVariantOrder`, `discoveryVariantCounts`, `discoveryClusters` | derived | Discovery variant metadata |
| `deterministicChecks`, `deterministicClusters`, `hasDeterministicNextChecks` | derived | Deterministic checks data |
| `deterministicSummary` | derived | Deterministic checks summary text |
| `runLlmStatsLine`, `historicalLlmStatsLine`, `providerBreakdown` | derived | LLM stats for run summary panel |
| `telemetryData` | derived | Structured telemetry for LlmTelemetryPreviewCard |

### 1.2 UI Composition (Lines ~1076–1594)

| Item | Lines | Purpose |
|------|-------|---------|
| Header hero | 17 | Run identity, badge, freshness, latest link |
| Refresh controls | 16 | Refresh button, auto-refresh dropdown |
| Demo entry button | 9 | "Start demo" CTA |
| Nav bar | 18 | Section navigation links |
| `<RecentRunsPanel>` | 24 | Runs list with pagination |
| `<RunSummaryPanel>` | 71 | Run header + stats (two branches: loaded/loading/error) |
| Workflow lane "Diagnose Now" | 7 | Lane header |
| `<ReviewEnrichmentPanel>` | 12 | Provider advisory panel |
| `<ProviderExecutionPanel>` | 6 | Provider branches |
| `<RunDiagnosticPackPanel>` | 6 | Diagnostic package |
| `<DiagnosticPackReviewPanel>` | 2 | Diagnostic pack review |
| `<AlertmanagerSnapshotPanel>` | 6 | Alertmanager snapshot |
| `<AlertmanagerSourcesPanel>` | 8 | Alertmanager sources |
| `<VmalertDiscoveryPanel>` | 2 | vmalert discovery |
| `<VmalertAlertStatePanel>` | 2 | vmalert alert state |
| `<DeterministicNextChecksPanel>` | 21 | Deterministic next checks |
| `<WorkNextChecksLane>` | 13 | Work list + execution history |
| Fleet overview | 93 | Fleet table with cluster rows |
| `<ClusterDetailSection>` | 41 | Cluster detail with tabbed sections |
| Workflow lane "Improve the System" | 7 | Lane header |
| Proposals section | 44 | Proposal list with filter controls |
| `<NotificationHistoryTable>` | 6 | Notification archive |
| `<LLMPolicyPanel>` | 9 | LLM policy panel |
| `<LLMActivityPanel>` | 9 | LLM activity panel |
| `<DemoShell>` | 6 | Demo overlay |

### 1.3 Side Effects / Fetching / Refresh (Lines ~294–462)

| Item | Type | Purpose |
|------|------|---------|
| Auto-refresh timer | `useEffect` | Calls `poll()` at `autoRefreshInterval` |
| `handleRunSelectionViaRunControl` | callback | Selects run + navigates to page |
| `handleBatchExecution` | callback | Batch execution + refresh orchestration |

### 1.4 Execution / Approval Transient State (Lines ~401–746)

| Item | Type | Purpose |
|------|------|---------|
| `executionResults` | `useState` | Per-execution result map |
| `executingCandidate` | `useState` | Currently executing candidate key |
| `approvalResults` | `useState` | Per-approval result map |
| `approvingCandidate` | `useState` | Currently approving candidate key |
| `executionHighlightTimer`, `queueHighlightTimer`, `clusterHighlightTimer` | refs | Highlight animation timers |
| `lastExecutedCandidateKey` | ref | Track last executed for post-refresh highlight |
| `executingBatchRunId`, `batchExecutionError` | `useState` | Batch execution state |
| `handleManualExecution` | callback | Execute single candidate |
| `handleApproveCandidate` | callback | Approve single candidate |
| `isManualExecutionAllowed` | callback | Check if candidate is executable |
| `getNotRunnableExplanation` | callback | Human-readable reason for non-execution |

### 1.5 Navigation / Highlight Helpers (Lines ~499–624)

| Item | Type | Purpose |
|------|------|---------|
| `scrollToSection` | function | Smooth scroll to section by ID |
| `highlightCluster` | function | Flash cluster row + auto-clear |
| `highlightExecutionEntry` | function | Flash execution entry + auto-clear |
| `highlightQueueCard` | function | Flash queue card + scroll into view |
| `toggleIncidentExpansion` | callback | Toggle incident cluster expansion |
| `buildCandidateKey` | function | Build queue item key |
| `findExecutionHistoryEntry` | callback | Match queue item to history entry |
| `toggleQueueFocusPreset` | callback | Toggle queue focus mode |
| `resetQueueFilters` | callback | Reset all queue filters to default |
| `resetQueueView` | callback | Reset + clear stored state |
| `buildPromotionKey` | function | Build deterministic check promotion key |

### 1.6 Cluster / Navigation Wrappers (Lines ~464–493)

| Item | Type | Purpose |
|------|------|---------|
| `handleClusterSelection` | callback | Combines hook + local clusterDetailExpanded |
| `refresh` | callback | App-level refresh wrapper (clears executionResults + schedules highlight) |
| `focusClusterForNextChecks` | callback | Focus cluster + expand + highlight |
| `handleBackToQueue` | callback | Scroll to queue section |
| `handleQueueClusterJump` | callback | Jump from queue to cluster detail |
| `handleQueueExecutionJump` | callback | Jump from queue to execution history |

---

## 2. Which Responsibilities Are Pure Data Shaping

These are `useMemo` or plain functions that transform data without side effects:

1. **`renderLlmStatsLine`** — transforms `LLMStats` → JSX element
2. **`findingSelectionInput`** — maps `run` + `selectedRunId` → demo finding input
3. **`queuePanelProps`** — packages queue-related values into a typed interface
4. All `header*`, `run*`, `cluster*`, `plan*`, `discovery*`, `deterministic*` derived values
5. **`telemetryData`** — transforms run LLM stats into telemetry preview format

**Extraction recommendation:** These belong in utility modules or custom hooks. They should not live in App.tsx.

---

## 3. Which Are UI Composition

The JSX return block is pure composition — it assembles components. Some components have inline prop computation that should be extracted:

- **`RecentRunsPanel`** — receives 23 props from App; many are grouped from hooks
- **`RunSummaryPanel`** — receives 27 props; two render branches for loaded/loading states
- **`WorkNextChecksLane`** — receives 13 props including `queuePanelProps`
- **`ClusterDetailSection`** — receives 20 props with nested `nextCheckPlanSectionProps`
- **Proposals section controls** — `statusFilter`, `sortKey`, `searchText` from useUIState

**Extraction recommendation:** The return block is acceptable as composition. The prop-passing complexity signals that App.tsx is doing too much data shaping before composition.

---

## 4. Which Are Side Effects / Fetching / Refresh

| Item | Status | Reason |
|------|--------|--------|
| Auto-refresh timer | ✅ Already minimal | Single `useEffect` calling `poll()` |
| `handleRunSelectionViaRunControl` | ⚠️ Orchestration | Wires RunControl + navigate |
| `handleBatchExecution` | ⚠️ Orchestration | Wires execution + refresh |

**Extraction recommendation:** These are fine in App.tsx as coordination logic. They should not grow.

---

## 5. Which Seams Are Safest to Extract First

### Extraction Safety Matrix

| Seam | Safety | Reasoning |
|------|--------|-----------|
| `renderLlmStatsLine` | 🟢 Highest | Pure function, no state, no deps |
| Header derived values (`headerRunId`, `runRecency`, etc.) | 🟢 High | All from stable inputs (`run`, `runsList`) |
| Demo shell derived values (`findingSelectionInput`) | 🟢 High | `useMemo` from run data |
| Queue props package (`queuePanelProps`) | 🟢 High | `useMemo` from hook outputs |
| `clusterDetailSectionProps` | 🟡 Medium | Many nested derived values |
| Run summary derived values | 🟡 Medium | Depends on `run`, `fleet`, `selectedClusterLabel` |
| Execution/approval handlers | 🔴 Low | Closely tied to transient state |
| Navigation/highlight helpers | 🔴 Low | Depend on multiple UI state sources |

---

## 6. Proposed Extraction Order

### ACT 1: Extract Header Display Model

**File:** `frontend/src/components/run-summary/useRunHeaderModel.ts` (new)

**Extract these pure functions:**
```typescript
// Extract: renderLlmStatsLine
export const renderLlmStatsLine = (stats: LLMStats, modifier?: string) => { ... }

// Extract: header metadata derivations  
export const getHeaderRunMetadata = (run, runsList, selectedRunId, selectedClusterLabel) => {
  // headerRunId, headerRunLabel, runRecency, latestRunTimestamp, latestRunRecency
  // headerStats, runStatsSummary, runSummaryStats
  // selectedCluster, clusterRecency, clusterFresh
  // degradedCount, hasDegradedClusters
}
```

**Lines removed from App.tsx:** ~100  
**Tests to validate:** `frontend/src/__tests__/llm-telemetry-card.test.tsx`

---

### ACT 2: Extract Run Summary Props Builder

**File:** `frontend/src/components/run-summary/useRunSummaryProps.ts` (new)

**Extract:** All derived values passed to `<RunSummaryPanel>` except those already in ACT 1.

**Lines removed from App.tsx:** ~80  
**Tests to validate:** RunSummaryPanel integration tests

---

### ACT 3: Extract Cluster Detail Props Builder

**File:** `frontend/src/components/ClusterDetailSection/useClusterDetailSectionProps.ts` (new)

**Extract:**
- `interpretation`, `recommendedArtifacts`, `clusterTriggerReason`
- `drilldownAvailability`, `drilldownSummary`, `recencyTimestamp`
- `planCandidates`, `orphanedApprovals`, `planArtifactLink`
- All planner-related derivations
- `planSummaryText`, `plannerReasonText`, `planCandidateCountLabel`
- `discoveryVariantOrder`, `discoveryVariantCounts`, `discoveryClusters`
- `nextCheckPlanSectionProps` object

**Lines removed from App.tsx:** ~150  
**Tests to validate:** `frontend/src/__tests__/panel-selection-binding-per-run-panel-policy.test.tsx`

---

### ACT 4: Extract Queue Props Package

**File:** `frontend/src/components/QueuePanel/useQueuePanelProps.ts` (new)

**Note:** `queuePanelProps` is already a `useMemo`. Extract the entire memo block to a hook.

**Lines removed from App.tsx:** ~55  
**Tests to validate:** QueuePanel integration tests, `frontend/src/__tests__/execution-history-filter.test.tsx`

---

### ACT 5: Extract Demo Shell Finding Input Builder

**File:** `frontend/src/demo-shell/useDemoShellInput.ts` (new)

**Extract:** `findingSelectionInput` useMemo block.

**Lines removed from App.tsx:** ~50  
**Tests to validate:** `frontend/src/__tests__/demo-shell-action-preview-policy.test.tsx`

---

### ACT 6: Extract Deterministic Checks Props

**File:** `frontend/src/components/DeterministicNextChecksPanel/useDeterministicChecksProps.ts` (new)

**Extract:** `deterministicChecks`, `deterministicClusters`, `hasDeterministicNextChecks`, `deterministicSummary`.

**Lines removed from App.tsx:** ~30  
**Tests to validate:** DeterministicNextChecksPanel tests

---

### ACT 7: Group Navigation/Highlight Helpers

**File:** `frontend/src/hooks/useNavigationHelpers.ts` (new)

**Extract:**
- `scrollToSection`
- `highlightCluster` (timer logic)
- `highlightExecutionEntry` (timer logic)
- `highlightQueueCard` (timer logic + scroll)
- `toggleIncidentExpansion`
- `focusClusterForNextChecks`
- `handleBackToQueue`
- `handleQueueClusterJump`
- `handleQueueExecutionJump`
- `buildCandidateKey`
- `buildPromotionKey`

**Lines removed from App.tsx:** ~120  
**Tests to validate:** UI behavior tests

---

## 7. What Is the Smallest First Implementation ACT

**ACT 1: Extract Header Display Model**

This is the safest first step:

1. Create `frontend/src/components/run-summary/useRunHeaderModel.ts`
2. Move `renderLlmStatsLine` (34 lines) to the new file
3. Move `telemetryData` derivation (10 lines) to the new file
4. Export from new file; import in App.tsx
5. Run: `npm run build` in frontend
6. Run: `npm test` in frontend

**Why this is smallest:**
- `renderLlmStatsLine` is a pure function at the top of App.tsx (lines 183–214)
- It has no state dependencies — only uses props passed in
- It's already isolated (just builds JSX from data)
- No behavior changes
- No test breakage expected (it's a pure transform)

**Lines in App.tsx after ACT 1:** ~1550  
**Lines in new file:** ~50

---

## 8. Current Test Coverage for App.tsx

**No direct App.tsx unit tests exist.** However, integration tests cover App-level behavior:

| Test File | Coverage |
|-----------|----------|
| `frontend/src/__tests__/selected-run-pagination-sync.test.tsx` | Recent runs selection + pagination sync |
| `frontend/src/__tests__/panel-selection-binding-per-run-panel-policy.test.tsx` | Per-run panel binding |
| `frontend/src/__tests__/panel-selection-binding-empty-state.test.tsx` | Empty state wording |
| `frontend/src/__tests__/execution-history-filter.test.tsx` | Queue/execution filtering |
| `frontend/src/__tests__/llm-telemetry-card.test.tsx` | LLM stats rendering |
| `frontend/src/__tests__/advisory-panel.test.tsx` | Advisory sections |
| `frontend/src/__tests__/demo-shell-action-preview-policy.test.tsx` | Demo shell behavior |
| `frontend/src/__tests__/detached-notice-visibility.test.tsx` | Navigation detached mode |
| `frontend/src/hooks/__tests__/useRunSelection-refresh.test.tsx` | useRunSelection hook |
| `frontend/src/hooks/__tests__/useRunData.test.tsx` | useRunData hook |

**Strategy:** After each extraction, run integration tests to ensure behavior is preserved.

---

## 9. Summary: Extraction Target State

| Phase | File | Lines Extracted | App.tsx After |
|-------|------|-----------------|---------------|
| (Current) | App.tsx | — | 1594 |
| ACT 1 | `useRunHeaderModel.ts` | ~50 | ~1540 |
| ACT 2 | `useRunSummaryProps.ts` | ~80 | ~1460 |
| ACT 3 | `useClusterDetailSectionProps.ts` | ~150 | ~1310 |
| ACT 4 | `useQueuePanelProps.ts` | ~55 | ~1255 |
| ACT 5 | `useDemoShellInput.ts` | ~50 | ~1205 |
| ACT 6 | `useDeterministicChecksProps.ts` | ~30 | ~1175 |
| ACT 7 | `useNavigationHelpers.ts` | ~120 | ~1055 |

**Note:** These line counts are approximate. The goal is not a specific line count but logical coherence. If components become too tightly coupled across files, the plan should be adjusted.

---

## 10. Non-Goals

This plan does NOT include:
- Moving UI components to separate files (they're already in `components/`)
- Changing the hook ownership model (useRunSelection, useAppData, useQueueState, useUIState are correct)
- Modifying backend API contracts
- Changing CSS/styling
- Adding new features

---

## 11. Acceptance Criteria Verification

| Criterion | Status |
|-----------|--------|
| Extraction plan document exists | ✅ This document |
| Plan names concrete functions/state blocks/components | ✅ See Sections 1, 6 |
| Plan proposes ordered ACTs | ✅ ACTs 1-7 with descriptions |
| Plan identifies tests to run after each extraction | ✅ See Section 6 |
| No behavior changes | ✅ All extractions are pure refactoring |
| Frontend tests/build still pass if code was touched | ✅ Verified in existing AUDIT_HOOK_EXTRACTION.md |

---

*Document generated: 2026-06-04*  
*Task: Frontend app shell extraction audit*
