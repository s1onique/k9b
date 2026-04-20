# App.tsx Hook Extraction Audit — E1-3-audit

**File:** `frontend/src/App.tsx`
**Original line count:** 6782
**Current line count:** 6621
**Reduction:** 161 lines (2.4%)
**Goal:** Thin composition root (~500–800 lines)

---

## Implementation Status

### ✅ Phase 3 Complete: `useUIState.ts` (220 lines)

The following items have been extracted from `App.tsx` to `useUIState.ts`:

| Item | Type | Status |
|------|------|--------|
| `statusFilter` / `setStatusFilter` | state | ✅ Extracted |
| `searchText` / `setSearchText` | state | ✅ Extracted |
| `sortKey` / `setSortKey` | state | ✅ Extracted |
| `activeTab` / `setActiveTab` | state | ✅ Extracted |
| `clusterDetailExpanded` / `setClusterDetailExpanded` | state | ✅ Extracted |
| `highlightedClusterLabel` / `setHighlightedClusterLabel` | state | ✅ Extracted |
| `incidentExpandedClusters` / `setIncidentExpandedClusters` | state | ✅ Extracted |
| `executionHistoryHighlightKey` / `setExecutionHistoryHighlightKey` | state | ✅ Extracted |
| `queueHighlightKey` / `setQueueHighlightKey` | state | ✅ Extracted |
| `executionHistoryFilter` / `setExecutionHistoryFilter` | state | ✅ Extracted |
| `expandedQueueItems` / `setExpandedQueueItems` | state | ✅ Extracted |
| `toggleQueueDetails` | callback | ✅ Extracted |
| persist execution history filter effect | effect | ✅ Extracted |

**Current useUIState.ts:** 220 lines

---

### ✅ Phase 2 Complete: `useAppData.ts` (316 lines)

The following items have been extracted from `App.tsx` to `useAppData.ts`:

| Item | Type | Status |
|------|------|--------|
| `fleet` / `setFleet` | state | ✅ Extracted |
| `proposals` / `setProposals` | state | ✅ Extracted |
| `clusterDetail` / `setClusterDetail` | state | ✅ Extracted |
| `error` / `setError` | state | ✅ Extracted |
| `selectedClusterLabel` / `setSelectedClusterLabel` | state | ✅ Extracted |
| `expandedProposals` / `setExpandedProposals` | state | ✅ Extracted |
| `isClusterDetailLoading` | state | ✅ Extracted |
| `notifications` | state | ✅ Extracted |
| `statusOptions` | derived | ✅ Extracted |
| `handleToggleProposal` | callback | ✅ Extracted |
| `handleClusterSelection` | callback | ✅ Extracted |
| `refreshAppData` | callback | ✅ Extracted |
| `handlePromoteDeterministicCheck` | callback | ✅ Extracted |
| `handleUsefulnessFeedback` | callback | ✅ Extracted |
| main refresh effect | effect | ✅ Extracted |
| initial fetch effect | effect | ✅ Extracted |
| visibility change effect | effect | ✅ Extracted |
| cluster detail fetch effect | effect | ✅ Extracted |
| refreshInProgress ref | ref | ✅ Extracted |

**Current useAppData.ts:** 316 lines

---

### ✅ Phase 1 Complete: `useRunSelection.ts` additions

The following items have been extracted from `App.tsx` to `useRunSelection.ts`:

| Item | Type | Status |
|------|------|--------|
| `runsFilter` / `setRunsFilter` | state | ✅ Extracted |
| `runsPageSize` / `setRunsPageSize` | state | ✅ Extracted |
| `runsPage` / `setRunsPage` | state | ✅ Extracted |
| `isRunsListFollowingSelection` / `setIsRunsListFollowingSelection` | state | ✅ Extracted |
| `filteredRunsList` | derived | ✅ Extracted |
| `runsFilterCounts` | derived | ✅ Extracted |
| `paginatedRunsList` | derived | ✅ Extracted |
| `isSelectedRunVisibleOnCurrentRunsPage` | derived | ✅ Extracted |
| `handleRunsFilterChange` | callback | ✅ Extracted |
| `handleRunsPageSizeChange` | callback | ✅ Extracted |
| `handleRunsPageChange` | callback | ✅ Extracted |
| `computePageForRunId` | callback | ✅ Extracted |
| `navigateToPageContainingRun` | callback | ✅ Extracted |
| `handleShowSelectedRun` | callback | ✅ Extracted |
| `jumpToLatest` | callback | ✅ Extracted (renamed from `handleJumpToLatest`) |
| `handleRunSelection` | callback | ✅ Extracted |
| runs list navigation effect | effect | ✅ Extracted |

**Current useRunSelection.ts:** ~500 lines

---

### `frontend/src/hooks/useRunData.ts` (166 lines)

| Export | Type | Purpose |
|--------|------|---------|
| `useRunData({ selectedRunId })` | hook | Fetches run payload, manages polling, auto-refresh |
| `run` | state | `RunPayload | null` |
| `isLoading` | state | boolean |
| `isError` | state | `string | null` |
| `lastRefresh` | state | `Dayjs` |
| `refresh` | callback | manual trigger |
| `autoRefreshInterval` | state | `number | null` |
| `handleAutoRefreshChange` | callback | handler |
| `AUTOREFRESH_STORAGE_KEY` | const | localStorage key |
| `UseRunDataOptions` | interface | |
| `UseRunDataReturn` | interface | |

---

## Audit Table

| Name | Kind | Current location | Proposed hook | Status |
|------|------|------------------|---------------|--------|
| `fleet` / `setFleet` | useState | App component body | **useAppData.ts** | ✅ Extracted |
| `proposals` / `setProposals` | useState | App component body | **useAppData.ts** | ✅ Extracted |
| `clusterDetail` / `setClusterDetail` | useState | App component body | **useAppData.ts** | ✅ Extracted |
| `error` / `setError` | useState | App component body | **useAppData.ts** | ✅ Extracted |
| `statusFilter` / `setStatusFilter` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `searchText` / `setSearchText` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `sortKey` / `setSortKey` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `expandedProposals` / `setExpandedProposals` | useState | App component body | **useAppData.ts** | ✅ Extracted |
| `activeTab` / `setActiveTab` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `selectedClusterLabel` / `setSelectedClusterLabel` | useState | App component body | **useAppData.ts** | ✅ Extracted |
| `clusterDetailExpanded` / `setClusterDetailExpanded` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `executionResults` / `setExecutionResults` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `executingCandidate` / `setExecutingCandidate` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `approvalResults` / `setApprovalResults` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `approvingCandidate` / `setApprovingCandidate` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `promotionStatus` / `setPromotionStatus` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `promotingDeterministic` / `setPromotingDeterministic` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `promotionMessages` / `setPromotionMessages` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `initialQueueViewState` | useMemo | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueClusterFilter` / `setQueueClusterFilter` | useState | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueStatusFilter` / `setQueueStatusFilter` | useState | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueCommandFamilyFilter` / `setQueueCommandFamilyFilter` | useState | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queuePriorityFilter` / `setQueuePriorityFilter` | useState | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueWorkstreamFilter` / `setQueueWorkstreamFilter` | useState | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueSearch` / `setQueueSearch` | useState | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueSortOption` / `setQueueSortOption` | useState | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueFocusMode` / `setQueueFocusMode` | useState | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `highlightedClusterLabel` / `setHighlightedClusterLabel` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `incidentExpandedClusters` / `setIncidentExpandedClusters` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `executionHistoryHighlightKey` / `setExecutionHistoryHighlightKey` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `queueHighlightKey` / `setQueueHighlightKey` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `executionHistoryFilter` / `setExecutionHistoryFilter` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `runsFilter` / `setRunsFilter` | useState | App component body | **useRunSelection.ts** | ✅ Extracted |
| `runsPageSize` / `setRunsPageSize` | useState | App component body | **useRunSelection.ts** | ✅ Extracted |
| `runsPage` / `setRunsPage` | useState | App component body | **useRunSelection.ts** | ✅ Extracted |
| `isRunsListFollowingSelection` / `setIsRunsListFollowingSelection` | useState | App component body | **useRunSelection.ts** | ✅ Extracted |
| `executingBatchRunId` / `setExecutingBatchRunId` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `batchExecutionError` / `setBatchExecutionError` | useState | App component body | **stays in App.tsx** | ✅ Stays |
| `expandedQueueItems` / `setExpandedQueueItems` | useState | App component body | **useUIState.ts** | ✅ Extracted |
| `handleRunsFilterChange` | useCallback | App component body | **useRunSelection.ts** | ✅ Extracted |
| `handleRunsPageSizeChange` | useCallback | App component body | **useRunSelection.ts** | ✅ Extracted |
| `handleRunsPageChange` | useCallback | App component body | **useRunSelection.ts** | ✅ Extracted |
| `computePageForRunId` | useCallback | App component body | **useRunSelection.ts** | ✅ Extracted |
| `navigateToPageContainingRun` | useCallback | App component body | **useRunSelection.ts** | ✅ Extracted |
| `handleShowSelectedRun` | useCallback | App component body | **useRunSelection.ts** | ✅ Extracted |
| `handleBatchExecution` | useCallback | App component body | **stays in App.tsx** | ✅ Stays |
| `handleJumpToLatest` | useCallback | App component body | **useRunSelection.ts** | ✅ Extracted (renamed to `jumpToLatest`) |
| `handleRunSelection` | useCallback | App component body | **useRunSelection.ts** | ✅ Extracted |
| `refresh` | useCallback | App component body | **useAppData.ts** (wrapper stays in App) | ✅ Stays (uses hook's refresh) |
| `handlePromoteDeterministicCheck` | useCallback | App component body | **useAppData.ts** (calls hook handler) | ✅ Stays (uses hook handler) |
| `handleUsefulnessFeedback` | useCallback | App component body | **useAppData.ts** | ✅ Stays (uses hook handler) |
| `toggleQueueDetails` | useCallback | App component body | **useUIState.ts** | ✅ Extracted |
| runs list navigation effect | useEffect | App component body | **useRunSelection.ts** | ✅ Extracted |
| main refresh effect | useEffect | App component body | **useAppData.ts** | ✅ Extracted |
| initial fetch effect | useEffect | App component body | **useAppData.ts** | ✅ Extracted |
| visibility change effect | useEffect | App component body | **useAppData.ts** | ✅ Extracted |
| timer cleanup effect | useEffect | App component body | **stays in App.tsx** | ✅ Stays |
| cluster detail fetch effect | useEffect | App component body | **useAppData.ts** | ✅ Extracted |
| persist queue view effect | useEffect | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| persist execution history filter effect | useEffect | App component body | **useUIState.ts** | ✅ Extracted |
| `statusOptions` | useMemo | App component body | **useAppData.ts** | ✅ Extracted |
| `queueClusterOptions` | useMemo | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueCommandFamilyOptions` | useMemo | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queuePriorityOptions` | useMemo | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `queueWorkstreamOptions` | useMemo | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `filteredQueue` | useMemo | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |
| `sortedQueue` | useMemo | App component body | **useUIState.ts** | ⏳ Pending (Phase 4) |

---

## Remaining Implementation Phases

### ✅ Phase 3 Complete: `useUIState.ts` (220 lines)
**Purpose:** Panel toggles, filter state, sort state, expanded sections, highlight state

### ⏳ Phase 4: `useQueueState.ts` — NEW hook (⏳ Pending)
**Purpose:** Queue filtering, sorting, expanded items

### ⏳ Phase 5: Extract components — NEW files (⏳ Pending)
**Purpose:** Move sub-components to separate files

---

## Stays in App.tsx

These items are transient, tightly coupled to rendering, or require orchestrating multiple hooks:

| Item | Reason |
|------|--------|
| `executionResults` / `setExecutionResults` | Per-execution transient state, directly rendered in queue |
| `executingCandidate` / `setExecutingCandidate` | Per-execution transient state |
| `approvalResults` / `setApprovalResults` | Per-approval transient state |
| `approvingCandidate` / `setApprovingCandidate` | Per-approval transient state |
| `promotionStatus` / `setPromotionStatus` | Per-promotion transient state |
| `promotingDeterministic` / `setPromotingDeterministic` | Per-promotion transient state |
| `promotionMessages` / `setPromotionMessages` | Per-promotion transient state |
| Queue filter/sort state | Tightly coupled with queue rendering and runtime data (`run?.nextCheckQueue`) |
| Queue derived values | `queueClusterOptions`, `filteredQueue`, `sortedQueue`, `queueGroups` depend on runtime data |
| Queue UI helpers | `handleManualExecution`, `handleApproveCandidate`, `handleBackToQueue`, etc. |
| Queue highlight functions | `highlightQueueCard`, `highlightCluster`, `highlightExecutionEntry` depend on multiple UI states |
| `executingBatchRunId` / `setExecutingBatchRunId` | Batch execution transient state |
| `batchExecutionError` / `setBatchExecutionError` | Batch execution error state |
| `handleBatchExecution` | Orchestrates multiple hooks (refreshRuns, refreshRunData) |
| `handlePromoteDeterministicCheck` | Uses hook handler from useAppData |
| `handleUsefulnessFeedback` | Uses hook handler from useAppData |
| `clusterHighlightTimer` / `executionHighlightTimer` / `queueHighlightTimer` | Timers for highlight animations |
| `lastExecutedCandidateKey` | Ref for execution tracking |
| `timer cleanup effect` | Cleans up timers on unmount |
| `refresh` wrapper | App-level wrapper that calls hook refresh + handles side effects |

**Note on queue state:** Queue state was NOT extracted to a separate hook because:
1. Queue state depends on derived data from `run?.nextCheckQueue` and other runtime data
2. Queue state is tightly coupled with the queue UI rendering
3. Extracting to a hook would require passing too many dependencies
4. Queue state is already modular within App.tsx (grouped together in the component body)

---

## Inter-Hook Dependencies

```
useRunSelection (✅ Phase 1 Complete)
    ↓ selectedRunId
useRunData
    ↓ lastRefresh
useAppData (✅ Phase 2 Complete)
    ↓
    ├─ fleet, proposals (direct)
    ├─ selectedClusterLabel → clusterDetail (triggers fetch)
    └─ refresh (orchestrates hooks)

useUIState (✅ Phase 3 Complete)
    ├─ filter state (independent)
    ├─ highlight state (independent)
    └─ executionHistoryFilter (independent)

useQueueState (⏳ Phase 4 - Pending)
    ↑ derived from runQueue
    ↓
    ├─ queue filters (cluster, status, command family, priority, workstream)
    ├─ queue sorting
    └─ expanded queue items
```

---

## Implementation Order Recommendation

1. ✅ **Phase 1: Extract `useRunSelection` additions** (COMPLETE)
   - Runs pagination, filtering, follow mode
   - No dependencies on other hooks

2. ✅ **Phase 2: Extract `useAppData`** (COMPLETE)
   - Fleet, proposals, cluster detail fetch
   - Needs careful handling of refresh orchestration

3. ✅ **Phase 3: Extract `useUIState`** (COMPLETE)
   - Filter state, highlight state, active tab, expanded sections
   - Phase 3 extracted: statusFilter, searchText, sortKey, activeTab, clusterDetailExpanded, highlightedClusterLabel, incidentExpandedClusters, executionHistoryHighlightKey, queueHighlightKey, executionHistoryFilter, expandedQueueItems, toggleQueueDetails

4. ⏳ **Phase 4: Extract `useQueueState`** (depends on run data)
   - Queue filtering, sorting, expanded items
   - Queue state (queueClusterFilter, queueStatusFilter, etc.) still in App.tsx

5. ⏳ **Phase 5: Extract components** (LLMActivityPanel, NotificationHistoryTable, etc.)
   - Move sub-components to separate files
   - Reduces App.tsx rendering complexity

6. ⏳ **Phase 6: Thin App.tsx** (final cleanup)
   - Remove inline handlers that can be hooks
   - Verify composition layer is clean

---

## Build Verification

```
$ cd frontend && npm run build
✓ 46 modules transformed.
✓ built in 430ms
```

---

*Document generated: 2026-04-20*
*Task: E1-3-audit*
*Last updated: 2026-04-20*
