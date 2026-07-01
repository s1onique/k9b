/**
 * api.ts — Backend API client for the K9b diagnostics frontend.
 *
 * This file is a thin compatibility façade that re-exports from focused modules.
 * New code should import directly from the submodules:
 *
 *   import { fetchRun, fetchFleet } from "./api/runs";
 *   import { listIncidents, getIncident } from "./api/incidents";
 *   import { fetchNotifications } from "./api/notifications";
 *   import { performAlertmanagerSourceAction } from "./api/alertmanager";
 *   import { fetchJson, fetchRuntimeStatus } from "./api/client";
 *
 * Exported symbols (backward-compatible):
 *   fetchRun, fetchFleet, fetchProposals, fetchNotifications,
 *   fetchClusterDetail, fetchRunsList, executeNextCheckCandidate,
 *   approveNextCheckCandidate, promoteDeterministicNextCheck,
 *   submitUsefulnessFeedback, runBatchExecution,
 *   performAlertmanagerSourceAction, promoteAlertmanagerSource,
 *   stopTrackingAlertmanagerSource, submitAlertmanagerRelevanceFeedback,
 *   fetchRuntimeStatus, fetchDebugDiagnosticsEnabled,
 *   downloadExecutionStateDiagnostics,
 *   captureIncidentSnapshot, generateIncidentReviewPacket,
 *   listIncidents, getIncident, getAutomaticDiagnosisReviewHandoff,
 *   + incident-related types
 *
 * Used by: All frontend components that load or mutate backend state.
 */

// =============================================================================
// Re-exports from client module
// =============================================================================

export {
  fetchJson,
  logFetchPhase,
  type FetchPhaseTiming,
  type FetchRunInit,
  fetchRuntimeStatus,
  fetchDebugDiagnosticsEnabled,
  downloadExecutionStateDiagnostics,
  type RuntimeStatusPayload,
  type DebugDiagnosticsEnabledResponse,
} from "./api/client";

export { extractErrorMessage } from "./api/client";

export type { FetchJsonOptions } from "./api/client";

// =============================================================================
// Re-exports from incidents module
// =============================================================================

export {
  listIncidents,
  getIncident,
  captureIncidentSnapshot,
  generateIncidentReviewPacket,
  getAutomaticDiagnosisReviewHandoff,
} from "./api/incidents";

export type {
  // List/Detail types
  IncidentSignal,
  IncidentEvidenceLink,
  IncidentReviewPacketPayload,
  IncidentEvent,
  IncidentSuggestedCheck,
  AutomaticDiagnosisReviewPayload,
  IncidentSummaryPayload,
  EvidenceArtifact,
  DiagnosisLoopStatus,
  AutomaticDiagnosisLoopSummary,
  AutomaticDiagnosisReviewHandoffPayload,
  IncidentDetailPayload,
  IncidentsListResponse,
  // Snapshot types
  IncidentSnapshotRequest,
  IncidentCandidateSignal,
  IncidentCandidate,
  IncidentSnapshotSummary,
  IncidentSnapshotBundle,
  IncidentSnapshotResponse,
  // Review packet types
  IncidentReviewPacketRequest,
  IncidentReviewPacketResponse,
} from "./api/incidents-types";

// =============================================================================
// Re-exports from alertmanager module
// =============================================================================

export {
  performAlertmanagerSourceAction,
  promoteAlertmanagerSource,
  stopTrackingAlertmanagerSource,
  submitAlertmanagerRelevanceFeedback,
} from "./api/alertmanager";

// =============================================================================
// Re-exports from runs module
// =============================================================================

export {
  fetchRun,
  fetchFleet,
  fetchProposals,
  fetchClusterDetail,
  fetchRunsList,
  runBatchExecution,
  type FetchRunOptions,
} from "./api/runs";

// =============================================================================
// Re-exports from notifications module
// =============================================================================

export {
  fetchNotifications,
  type NotificationsQuery,
  type NotificationsResponse,
} from "./api/notifications";

// =============================================================================
// Re-exports from next-checks module
// =============================================================================

export {
  executeNextCheckCandidate,
  approveNextCheckCandidate,
  promoteDeterministicNextCheck,
  submitUsefulnessFeedback,
} from "./api/nextChecks";

// =============================================================================
// Alertmanager relevance feedback types (re-exported)
// =============================================================================

export type AlertmanagerRelevanceFeedbackRequest = import("./types").AlertmanagerRelevanceFeedbackRequest;
export type AlertmanagerRelevanceFeedbackResponse = import("./types").AlertmanagerRelevanceFeedbackResponse;

// =============================================================================
// Incident Diagnosis Loop API Types
// Re-exported from incidentDiagnosisLoop.ts for consumer convenience
// =============================================================================

export type {
  DiagnosisInvestigation,
  DiagnosisSection,
  DiagnosisReport,
  DiagnosisLoopOnePassRequest,
  DiagnosisArtifactRef,
  DiagnosisArtifacts,
  DiagnosisSafetyMetadata,
  DiagnosisLoopOnePassResponse,
} from "./api/incidentDiagnosisLoop";

// =============================================================================
// Batch execution types (re-exported)
// =============================================================================

export type BatchExecutionRequest = import("./types").BatchExecutionRequest;
export type BatchExecutionResponse = import("./types").BatchExecutionResponse;
export type RunsListPayload = import("./types").RunsListPayload;
