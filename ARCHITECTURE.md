# Architecture Overview

LLM-based Kubernetes monitoring and diagnostics agent. Helps platform engineers detect abnormal states, correlate signals, generate hypotheses, and recommend diagnostic steps.

## Repository Layout

```
frontend/src/           React/TypeScript UI
  components/           19 dedicated panel/component files
  hooks/                5 state management hooks
  api.ts                Backend API client (fetch wrappers)
  types.ts              TypeScript type definitions
  utils.ts              Pure utility functions

src/k8s_diag_agent/     Python backend
  collect/              Cluster snapshot collection
  correlate/            Diagnostic signal correlation
  external_analysis/    LLM adapters, alertmanager, next-check planner
  feedback/             Usefulness feedback processing
  health/               Health loop, assessment, drilldown, proposals
  identity/            Cluster/object identity resolution
  llm/                  LLM provider interfaces, prompts, schemas
  normalize/            Evidence normalization
  notifications/        Alert delivery (Mattermost)
  reason/               Finding/hypothesis generation
  recommend/            Next-step recommendations
  render/               Output formatting
  ui/                   API endpoints, read models, server
  cli.py                Main CLI entrypoint
  models.py             Core domain models
  schemas.py            Validation schemas

scripts/                CLI utilities and operators
  run_health_scheduler.py  Scheduled health loop
  run_batch_next_checks.py  Batch next-check execution
  verify_all.sh         Verification gate
  [20+ diagnostic/review/export scripts]

docs/                   Architecture and schema docs
evals/                  Evaluation suite
fixtures/               Test fixtures
runs/                   Runtime artifact storage
tests/                  Python and TypeScript tests
```

## Data Flow

1. **Scheduler** (`run_health_scheduler.py`) triggers `HealthLoopRunner.execute()` on configured interval
2. **Collection**: `collect_cluster_snapshot()` captures Kubernetes state → `runs/health/snapshots/`
3. **Assessment**: `build_health_assessment()` produces findings/hypotheses from snapshots → `runs/health/assessments/`
4. **Comparison**: Peer cluster comparisons detect drift → `runs/health/comparisons/`
5. **Drilldown**: Triggered collectors gather detailed evidence → `runs/health/drilldowns/`
6. **Review**: `build_health_review()` aggregates all artifacts
7. **Proposals**: `generate_proposals_from_review()` creates tuning suggestions → `runs/health/proposals/`
8. **UI Index**: `write_health_ui_index()` produces `runs/health/ui-index.json`
9. **Frontend fetch**: `GET /api/run` returns RunPayload derived from ui-index
10. **State hooks**: `useRunData` owns run payload, `useAppData` owns fleet/proposals/notifications, `useUIState` owns filters/highlights, `useQueueState` owns queue filtering

## Frontend Module Map

| File | Owns | Key Exports |
|------|------|-------------|
| `hooks/useRunData.ts` | Run payload fetching, polling, auto-refresh | `run`, `refresh`, `isLoading`, `autoRefreshInterval` |
| `hooks/useAppData.ts` | Fleet, proposals, notifications, cluster detail | `fleet`, `proposals`, `notifications`, `clusterDetail` |
| `hooks/useUIState.ts` | Filters, sort, tabs, highlights | `statusFilter`, `searchText`, `activeTab`, `highlightedClusterLabel` |
| `hooks/useQueueState.ts` | Queue filter/sort, derived options | `filteredQueue`, `sortedQueue`, cluster/status/priority filters |
| `hooks/useRunSelection.ts` | Runs list, selection, pagination | `selectedRunId`, `selectRun`, `runsPage`, `paginatedRunsList` |
| `components/QueuePanel.tsx` | Next-check queue display and actions | Queue worklist with cluster/status/priority filters |
| `components/ExecutionHistoryPanel.tsx` | Check execution history, summary strip | History table with outcome/usefulness filtering |
| `components/AlertmanagerPanel.tsx` | Alertmanager snapshots and sources | Severity breakdowns, promote/stop-tracking actions |
| `components/LLMActivityPanel.tsx` | LLM activity log | Filterable table of provider calls, tokens, latency |
| `components/DeterministicNextChecksPanel.tsx` | Workstream-organized diagnostic checks | Promotion and filtering by workstream |
| `components/ReviewEnrichmentPanel.tsx` | Provider-assisted advisory | Top concerns, evidence gaps, next-check recommendations |
| `components/DiagnosticPackReviewPanel.tsx` | Automated review insights | Provider status, confidence, categorized lists |
| `components/RunsPanel.tsx` | Runs list navigation | Pagination, filtering, selection |
| `components/RunDiagnosticPackPanel.tsx` | Diagnostic pack display | Pack contents and metadata |
| `components/EvidenceDetails.tsx` | Evidence entry rendering | Collapsible label/value evidence display |
| `components/Pagination.tsx` | Reusable pagination | Items-per-page, prev/next, range summary |
| `components/NotificationHistoryTable.tsx` | Notification history | Kind/cluster filtering, text search |
| `components/HeaderBranding.tsx` | App header branding | Header UI |
| `components/ThemeSwitch.tsx` | Theme toggle | Light/dark mode switch |
| `components/AdvisorySections.tsx` | Compact advisory display | Top concerns, evidence gaps, next checks |
| `components/InterpretationBlock.tsx` | Finding/hypothesis interpretation | Labels and next-operator suggestions |
| `components/ResultInterpretationBlock.tsx` | Execution result interpretation | Useful-signal, empty-result, noisy-result labels |
| `components/FailureFollowUpBlock.tsx` | Failure follow-up | Failure details and next steps |
| `components/ProviderExecutionComponents.tsx` | Provider execution display | Branch data (eligible/attempted/ok/failed/skipped) |
| `components/DiagnosticPackReviewList.tsx` | Diagnostic pack review list | Compact entry preview with overflow |

## Elm-ish Run Control Plane

k9b uses an Elm-inspired pattern for selected-run frontend state, without adopting Elm itself. The goal is to make asynchronous run selection explicit and testable.

### Pattern Mapping

| Elm Concept | k9b Implementation | Description |
|-------------|-------------------|-------------|
| **Model** | `RunControlModel` | Single source of truth for runs list state, selected run id, latest run id, selected-run load state, slow/error state, and freshness. |
| **Msg** | `RunControlMsg` | All events that can change run-control state: `Boot`, `RunsLoaded`, `RunSelected`, `RunLoaded`, `PollTick`, `RunSlowThresholdReached`, `LatestClicked`, `ManualRefreshClicked`, `RetrySelectedRunClicked`, `SelectionCleared`, `DebugModeDetected`. |
| **Update** | `updateRunControl(model, msg)` | Pure reducer in `frontend/src/run-control/runControlReducer.ts` returning `{ model: RunControlModel; effects: RunControlEffect[] }`. No I/O inside reducer. |
| **Effects/Commands** | `RunControlEffect` | Data-only descriptions: `fetchRuns`, `fetchRun`, `scheduleSlowRunTimer`, `cancelSlowRunTimer`, `abortRunFetch`, `debugLog`. React hooks interpret these effects. |
| **View** | React components | Render from model/selectors. Run-owned panels must wait for loaded-content sentinels in tests, not placeholder headings. |

### Why This Architecture

This architecture was introduced after progressive loading allowed the shell to render while run-owned panels could remain stuck in placeholder states. The explicit state machine makes async ownership visible: whether `fetchRun` was emitted, whether `RunLoaded` was accepted or rejected, and which model state caused a panel to render loading/slow/error/loaded.

### Stale Response Guard

The stale guard must remain strict: `requestSeq` and `runId` must both match for `RunLoaded` and `RunFailed` messages to be accepted. A response is rejected if either:
- The `requestSeq` does not match the current pending request sequence, or
- The `runId` does not match the `requestedRunId` in the model

This prevents race conditions where an older response arrives after a newer one.

### Boot Sequence

Poll/manual refresh must not be required for initial selected-run content. The authoritative boot path is:
1. `Boot` → emits `fetchRuns` with reason `"boot"`
2. `RunsLoaded` → if no previous selection, auto-selects latest and emits `fetchRun` plus slow timer
3. `RunLoaded` → with matching `requestSeq` and `runId`, marks run as loaded

The slow timer (default 10s) transitions `selectedRun.status` from `"loading"` to `"slow"` if the run has not loaded by then.

### Non-goals

- **Not a global Redux/Zustand replacement.** RunControl is scoped to runs list and selected-run state only.
- **Not a rewrite of all frontend state.** Other hooks (`useAppData`, `useUIState`, `useQueueState`) remain unchanged.
- **Not a backend performance fix.** Does not address slow `/api/runs` or `/api/run` responses.
- **Not permission for poll/interval workarounds.** UI tests must not trigger auto-refresh/polling to make boot content appear. Run-owned panels must use loaded-content sentinels.

### Testing Notes

- **Reducer tests** in `frontend/src/run-control/__tests__/runControlReducer.test.ts` cover request sequencing and stale-response guards.
- **Timer tests** must scope fake timers per test file and restore real timers afterward using `vi.useFakeTimers()` / `vi.useRealTimers()`.
- **UI tests** should use stable panel containers plus loaded-content sentinels, not global "Loading selected run" disappearance.

### References

- [Elm Architecture: Model / View / Update](https://guide.elm-lang.org/architecture/)
- [Elm Commands and Subscriptions](https://guide.elm-lang.org/effects/)
## Backend Module Map

| Module | Owns |
|--------|------|
| `models.py` | Core domain enums (ConfidenceLevel, SafetyLevel, Signal, Finding, Hypothesis) |
| `collect/cluster_snapshot.py` | Kubernetes cluster snapshot dataclasses |
| `collect/live_snapshot.py` | Live cluster data collection |
| `correlate/linkers.py` | Diagnostic signal grouping by infrastructure layer |
| `health/loop.py` | Main HealthLoopRunner execution sequence |
| `health/summary.py` | Health assessment intent summaries |
| `health/drilldown.py` | Triggered drilldown collection |
| `health/review.py` | Review assembly from assessments/triggers/drilldowns |
| `health/proposals.py` | Proposal generation from review |
| `llm/base.py` | Abstract LLMProvider interface |
| `llm/prompts.py` | LLM evaluation prompt templates |
| `llm/llamacpp_provider.py` | llama.cpp adapter implementation |
| `external_analysis/adapter.py` | Provider invocation orchestration |
| `external_analysis/alertmanager_adapter.py` | Alertmanager integration |
| `external_analysis/next_check_planner.py` | Deterministic next-check planning |
| `external_analysis/review_schema.py` | Review-enrichment validation |
| `reason/diagnoser.py` | Finding/hypothesis generation from signals |
| `recommend/next_steps.py` | Next-step recommendations |
| `identity/cluster.py` | Cluster identity from namespace metadata |
| `identity/k8s_object.py` | Canonical Kubernetes object references |
| `ui/api.py` | Read-model payload builders |
| `ui/model.py` | View model helpers |
| `ui/server.py` | HTTP server and UI endpoints |
| `notifications/delivery.py` | Alert delivery to Mattermost |
| `feedback/runner.py` | Feedback run orchestration |
| `normalize/evidence.py` | Evidence normalization from fixtures |

## Key Concepts Glossary

| Term | Meaning |
|------|---------|
| **Run** | Single health assessment execution; produces snapshot, assessment, drilldowns, review |
| **RunId** | Runtime-generated unique identifier per execution (timestamped) |
| **RunLabel** | Declared fleet identifier from health-config; stable across runs |
| **HealthTarget** | Cluster + context + metadata (cluster_class, watched_releases, etc.) |
| **ClusterSnapshot** | Sanitized Kubernetes state capture (nodes, pods, CRDs, releases) |
| **Assessment** | Findings, hypotheses, next-evidence, recommended-actions from snapshot |
| **Signal** | Raw health indicator (warning, error, missing-data, version-drift) |
| **Finding** | Interpreted signal with confidence level and safety assessment |
| **Hypothesis** | Candidate explanation for observed findings |
| **Drilldown** | Triggered detailed evidence collection (events, pod descriptions) |
| **Review** | Aggregated current-run state (assessments + drilldowns + proposals) |
| **Proposal** | Suggested tuning to warning thresholds, noise filters, baselines |
| **ExternalAnalysisArtifact** | LLM/provider invocation output with status, findings, suggestions |
| **ReviewEnrichment** | Provider-assisted advisory (summary, concerns, gaps, next-checks) |
| **DeterministicNextCheck** | Evidence-based diagnostic command organized by workstream |
| **NextCheckQueue** | Execution queue combining planner suggestions + promoted checks |
| **LLMPolicy** | Auto-drilldown budget and provider configuration |
| **ProviderExecution** | Per-branch execution stats (eligible/attempted/ok/failed/skipped) |
| **UsefulnessFeedback** | Operator classification of check results (useful/partial/noisy/empty) |

## Where to Make Common Changes

| Change Needed | Files to Edit |
|---------------|---------------|
| Add queue filter | `QueuePanel.tsx` + `useQueueState.ts` |
| Add queue action (approve/execute) | `QueuePanel.tsx` + `frontend/src/api.ts` |
| Change run fetch logic | `useRunData.ts` + `frontend/src/api.ts` |
| Add execution history column | `ExecutionHistoryPanel.tsx` + `types.ts` |
| Change alertmanager display | `AlertmanagerPanel.tsx` + `ui/api.py` |
| Add new LLM activity metric | `LLMActivityPanel.tsx` + `types.ts` |
| Add deterministic check workstream | `DeterministicNextChecksPanel.tsx` + `types.ts` |
| Add review enrichment field | `ReviewEnrichmentPanel.tsx` + `external_analysis/review_schema.py` |
| Add proposal type | `health/proposals.py` + `types.ts` + `ReviewEnrichmentPanel.tsx` |
| Change snapshot collection | `collect/cluster_snapshot.py` + `collect/live_snapshot.py` |
| Add finding type | `models.py` + `reason/diagnoser.py` + `types.ts` |
| Add notification delivery channel | `notifications/delivery.py` + `health/notifications.py` |
| Add new API endpoint | `ui/api.py` + `ui/server.py` + `frontend/src/api.ts` |
| Change theme/styles | `theme.ts` + `themes.css` + `index.css` |
| Add runs filter | `RunsPanel.tsx` + `useRunSelection.ts` |
| Add cluster detail field | `ui/model.py` + `ui/api.py` + `types.ts` |

## API Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /api/run` | `RunPayload` (full run state) |
| `GET /api/fleet` | `FleetPayload` (cluster summaries) |
| `GET /api/proposals` | `ProposalsPayload` (pending proposals) |
| `GET /api/notifications` | `NotificationsPayload` (event log) |
| `GET /api/cluster-detail` | `ClusterDetailPayload` (detailed cluster state) |
| `POST /api/next-check-execution` | Execute next-check candidate |
| `POST /api/next-check-approval` | Approve/deny queue item |
| `POST /api/usefulness-feedback` | Submit usefulness classification |
| `POST /api/deterministic-promotion` | Promote deterministic check to queue |

## Key Files for Debugging

- `scripts/verify_all.sh` — Verification gate (must pass)
- `runs/health/ui-index.json` — Current run state (generated)
- `src/k8s_diag_agent/health/loop.py` — Main execution loop
- `src/k8s_diag_agent/ui/api.py` — API payload builders
- `frontend/src/App.tsx` — Root component (3027 lines post-refactor)
- `frontend/src/hooks/*.ts` — State ownership boundaries
