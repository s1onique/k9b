/**
 * Incident View Model Helpers
 *
 * Pure formatting helpers for incident display.
 * Keeps formatting logic centralized and testable.
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence
 */

import type { IncidentSummaryPayload, IncidentDetailPayload, DiagnosisLoopStatus } from "../api";

/**
 * Signal source types supported by the UI.
 * Reserved for future integration: alertmanager, vmalert, manual
 */
export type SignalSource = "k8s" | "alertmanager" | "vmalert" | "manual";

/**
 * Maps signal source from backend to UI type.
 * Falls back to "k8s" for current implementation.
 */
export const getSignalSourceType = (source: string): SignalSource => {
  const lower = source.toLowerCase();
  if (lower.includes("k8s") || lower.includes("kubernetes") || lower.includes("metrics") || lower.includes("events")) {
    return "k8s";
  }
  if (lower.includes("alertmanager")) return "alertmanager";
  if (lower.includes("vmalert")) return "vmalert";
  if (lower.includes("manual")) return "manual";
  return "k8s"; // Default to k8s for current implementation
};

/**
 * Returns display label for signal source type.
 */
export const getSignalSourceLabel = (source: SignalSource): string => {
  switch (source) {
    case "k8s":
      return "k8s";
    case "alertmanager":
      return "alertmanager";
    case "vmalert":
      return "vmalert";
    case "manual":
      return "manual";
    default:
      return source;
  }
};

/**
 * CSS class for signal source badge.
 */
export const getSignalSourceClass = (source: SignalSource): string => {
  return `source-badge source-${source}`;
};

/**
 * Returns display title for an incident.
 */
export const incidentDisplayTitle = (incident: IncidentSummaryPayload | IncidentDetailPayload): string => {
  const displayKind = incident.raw_object_kind || incident.object_kind;
  return `${displayKind} ${incident.object_name}`;
};

/**
 * Returns primary entity description for an incident.
 */
export const incidentPrimaryEntity = (incident: IncidentSummaryPayload | IncidentDetailPayload): string => {
  const displayKind = incident.raw_object_kind || incident.object_kind;
  return `${displayKind} ${incident.object_name} in ${incident.namespace}`;
};

/**
 * Status label mappings.
 */
const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  collecting_evidence: "Collecting Evidence",
  ready_for_review: "Ready for Review",
  investigating: "Investigating",
  suppressed: "Suppressed",
  duplicate: "Duplicate",
  resolved: "Resolved",
};

/**
 * Returns display label for incident status.
 */
export const incidentStatusLabel = (incident: IncidentSummaryPayload | IncidentDetailPayload): string => {
  return STATUS_LABELS[incident.status] ?? incident.status;
};

/**
 * Returns display label for severity.
 */
export const incidentSeverityLabel = (incident: IncidentSummaryPayload | IncidentDetailPayload): string => {
  return incident.severity.charAt(0).toUpperCase() + incident.severity.slice(1);
};

/**
 * Returns display label for incident class (converts snake_case to Title Case).
 */
export const incidentClassLabel = (incident: IncidentSummaryPayload | IncidentDetailPayload): string => {
  return incident.candidate_class.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * CSS class for severity badge.
 */
export const incidentSeverityClass = (severity: string): string => {
  switch (severity.toLowerCase()) {
    case "error":
      return "severity-badge severity-error";
    case "warning":
      return "severity-badge severity-warning";
    default:
      return "severity-badge severity-info";
  }
};

/**
 * CSS class for status badge.
 */
export const incidentStatusClass = (status: string): string => {
  switch (status.toLowerCase()) {
    case "open":
      return "status-badge status-open";
    case "collecting_evidence":
      return "status-badge status-collecting";
    case "ready_for_review":
      return "status-badge status-review";
    case "investigating":
      return "status-badge status-investigating";
    case "suppressed":
      return "status-badge status-suppressed";
    case "duplicate":
      return "status-badge status-duplicate";
    case "resolved":
      return "status-badge status-resolved";
    default:
      return "status-badge status-unknown";
  }
};

/**
 * Diagnosis loop status labels.
 */
const DIAGNOSIS_LOOP_STATUS_LABELS: Record<DiagnosisLoopStatus, string> = {
  not_run: "Not run",
  running_or_started: "Running",
  completed: "Completed",
  failed_or_unavailable: "Failed",
};

/**
 * Returns display label for diagnosis loop status.
 */
export const incidentDiagnosisLoopLabel = (status: DiagnosisLoopStatus): string => {
  return DIAGNOSIS_LOOP_STATUS_LABELS[status] ?? status;
};

/**
 * CSS class for diagnosis loop status badge.
 */
export const incidentDiagnosisLoopClass = (status: DiagnosisLoopStatus): string => {
  switch (status) {
    case "not_run":
      return "diagnosis-status-badge diagnosis-status-not-run";
    case "running_or_started":
      return "diagnosis-status-badge diagnosis-status-running";
    case "completed":
      return "diagnosis-status-badge diagnosis-status-completed";
    case "failed_or_unavailable":
      return "diagnosis-status-badge diagnosis-status-failed";
    default:
      return "diagnosis-status-badge diagnosis-status-unknown";
  }
};

/**
 * Returns diagnosis summary for an incident.
 */
export const incidentDiagnosisSummary = (
  incident: IncidentDetailPayload
): { status: DiagnosisLoopStatus; label: string; hasRun: boolean } => {
  const summary = incident.automatic_diagnosis_loop_summary;
  return {
    status: summary.status,
    label: DIAGNOSIS_LOOP_STATUS_LABELS[summary.status],
    hasRun: summary.status !== "not_run",
  };
};

/**
 * Returns source badges for an incident.
 * Currently only k8s is supported; other sources are reserved for future integration.
 */
export const incidentSourceBadges = (incident: IncidentSummaryPayload | IncidentDetailPayload): SignalSource[] => {
  // Current implementation: all incidents are from Kubernetes signals
  return ["k8s"];
};

/**
 * Formats timestamp for display.
 */
export const formatIncidentTimestamp = (timestamp: string): string => {
  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch {
    return timestamp;
  }
};

/**
 * Returns signal count label.
 */
export const incidentSignalCountLabel = (incident: IncidentSummaryPayload | IncidentDetailPayload): string => {
  return `${incident.signal_count} signal${incident.signal_count !== 1 ? "s" : ""}`;
};

/**
 * Returns evidence count label.
 */
export const incidentEvidenceCountLabel = (incident: IncidentSummaryPayload | IncidentDetailPayload): string => {
  return `${incident.evidence_count} evidence`;
};

/**
 * Returns review packet status label.
 */
export const incidentReviewPacketLabel = (
  incident: IncidentSummaryPayload | IncidentDetailPayload
): { label: string; state: "available" | "generating" | "pending" | "failed" | "none" } => {
  const rp = incident.review_packet;
  switch (rp.status) {
    case "available":
      return { label: "Review packet available", state: "available" };
    case "generating":
      return { label: "Generating review packet...", state: "generating" };
    case "failed":
      return { label: `Review packet failed: ${rp.error_message || "Unknown error"}`, state: "failed" };
    case "not_generated":
    default:
      return { label: "Review packet not generated", state: "pending" };
  }
};
