/**
 * incidents-types.ts — Type definitions for incident operations.
 *
 * Shared types for incident list, detail, snapshot, and review-packet operations.
 * These types are re-exported from the incidents module.
 */

/**
 * Signal that contributed to an incident.
 * Read-only; provenance for diagnostic context.
 */
export type IncidentSignal = {
  source: string;
  reason: string;
  message: string;
  captured_at: string;
  run_id?: string | null;
  detector_id?: string | null;
  finding_id?: string | null;
  fingerprint?: string | null;
};

/**
 * Evidence artifact attached to an incident.
 * Read-only; links incident to artifact store.
 */
export type IncidentEvidenceLink = {
  incident_id: string;
  artifact_id: string;
  role: string;
  attached_at: string;
};

/**
 * Review packet state for an incident.
 * Replaces old review_packet_available + review_packet_id pattern.
 */
export type IncidentReviewPacketPayload = {
  status: string;
  id?: string | null;
  generated_at?: string | null;
  error_message?: string | null;
};

/**
 * Timeline event in an incident's lifecycle.
 * Read-only; append-only record of state transitions.
 */
export type IncidentEvent = {
  event_id: string;
  incident_id: string;
  event_type: string;
  actor: string;
  occurred_at: string;
  message: string;
  actor_id?: string | null;
  data?: Record<string, unknown> | null;
};

/**
 * Read-only suggested-check compatibility projection for incident detail views.
 * This is NOT a fully implemented persistence object.
 *
 * The status field indicates the mapping reliability:
 * - "suggested": Next-check artifact successfully mapped to incident
 * - "compatibility": Legacy artifact without reliable incident mapping
 * - "unknown": No mapping attempted or mapping failed
 *
 * Hard constraints:
 * - NO check execution
 * - NO manual promotion
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 */
export type IncidentSuggestedCheck = {
  check_id: string;
  title: string;
  rationale: string;
  source: string;
  risk_level: string | null;
  status: "suggested" | "compatibility" | "unknown";
  artifact_id: string | null;
  run_id: string | null;
};

/**
 * Bounded automatic diagnosis review packet summary for incident detail views.
 *
 * This payload provides a safe, read-only summary of the latest automatic
 * diagnosis loop review packet for an incident. It exposes metadata only
 * and does NOT include raw packet contents, paths, or secrets.
 *
 * Safety constraints enforced:
 * - artifact_name is filename only (no path)
 * - All string fields are bounded (max lengths enforced at serialization)
 * - read_only is always True
 * - review_required_before_any_action is always True
 * - no_remediation_attempted is always True
 *
 * Hard constraints:
 * - NO remediation actions
 * - NO raw packet contents
 * - NO absolute paths
 * - NO secrets, tokens, or kubeconfig
 */
export type AutomaticDiagnosisReviewPayload = {
  // Availability state
  available: boolean;
  // When available=true: bounded summary fields
  artifact_type?: string | null;
  artifact_name?: string | null; // Filename only, no path (max 240 chars)
  run_id?: string | null; // Collector run ID (max 160 chars)
  collector_run_id?: string | null; // Batch collector run ID (max 160 chars)
  generated_at?: string | null; // ISO timestamp (max 80 chars)
  decision?: string | null; // Loop decision (max 120 chars)
  checks_requested?: number | null;
  checks_run?: number | null;
  checks_rejected?: number | null;
  eligible?: boolean | null;
  eligibility_reason?: string | null; // Reason for eligibility (max 160 chars)
  read_only?: boolean | null; // Always true
  review_required_before_any_action?: boolean | null; // Always true
  no_remediation_attempted?: boolean | null; // Always true
  // When available=false: reason for unavailability
  unavailable_reason?: string | null; // "no_review_packet" or "malformed_review_packet"
};

/**
 * Incident summary payload - lightweight list view.
 * Uses latest_snapshot_bundle_id (not snapshot_bundle_id).
 * Uses review_packet object (not review_packet_available + review_packet_id).
 */
export type IncidentSummaryPayload = {
  incident_id: string;
  namespace: string;
  object_kind: string;
  object_name: string;
  raw_object_kind: string | null;
  candidate_class: string;
  severity: string;
  status: string;
  first_observed_at: string;
  last_observed_at: string;
  signal_count: number;
  evidence_count: number;
  latest_snapshot_bundle_id: string | null;
  review_packet: IncidentReviewPacketPayload;
  suppressed_reason: string | null;
  duplicate_of: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
};

/**
 * Bounded evidence artifact metadata for incident detail views.
 *
 * This payload provides safe, read-only metadata about evidence artifacts
 * linked to an incident. It exposes identifying information only and does NOT
 * include raw artifact contents, logs, stdout/stderr, stack traces, prompts,
 * or secrets.
 *
 * Safety constraints enforced:
 * - All fields are bounded metadata only
 * - read_only is always True
 * - raw_content_available is always False
 * - no_remediation_attempted is always True
 *
 * Hard constraints:
 * - NO raw artifact contents
 * - NO raw Kubernetes object JSON/YAML
 * - NO logs, stdout/stderr, stack traces
 * - NO prompts, secrets, tokens, kubeconfig
 * - NO kubectl/Helm command text
 * - NO action/remediation controls
 */
export type EvidenceArtifact = {
  // Identity
  artifact_id: string;
  artifact_kind: string | null; // e.g., "snapshot_bundle", "review_packet"

  // Role in incident
  evidence_role: string | null; // e.g., "primary", "supporting", "snapshot", "review_packet"

  // Provenance
  source: string | null; // Origin system (e.g., "k9b-collector", "system")
  created_at: string | null; // ISO timestamp when artifact was created
  attached_at: string | null; // ISO timestamp when linked to incident

  // Run linkage
  run_id: string | null; // Associated run ID
  collector_run_id: string | null; // Batch collector run ID

  // Safe display fields
  summary: string | null; // Safe human-readable summary (bounded)
  safe_reference: string | null; // Safe reference identifier

  // Availability
  available: boolean; // Always True in this implementation
  unavailable_reason: string | null; // Always None

  // Safety flags - always present and True
  read_only: boolean; // Always True
  raw_content_available: boolean; // Always False
  no_remediation_attempted: boolean; // Always True
};

/**
 * Automatic diagnosis loop summary status values.
 */
export type DiagnosisLoopStatus = "not_run" | "running_or_started" | "completed" | "failed_or_unavailable";

/**
 * Read-only summary of the latest automatic diagnosis loop run.
 *
 * This payload provides a compact current-state summary derived from
 * incident timeline events and existing automatic diagnosis review metadata.
 *
 * The summary answers:
 * - Has automatic diagnosis run for this incident?
 * - Is the latest known state started/running, completed, or failed/unavailable?
 * - Was a review packet produced?
 * - How many checks were requested/run/rejected?
 * - Did the system remain read-only and non-remediating?
 *
 * Status values:
 * - "not_run": No diagnosis-loop lifecycle events exist
 * - "running_or_started": Latest event is diagnosis_loop_started
 * - "completed": Latest event is diagnosis_loop_completed
 * - "failed_or_unavailable": Latest event is diagnosis_loop_failed
 *
 * "Latest" is based on occurred_at, not input list order.
 *
 * Hard constraints:
 * - NO remediation actions
 * - NO raw event data
 * - NO raw packet contents
 * - NO logs, stdout/stderr, stack traces
 */
export type AutomaticDiagnosisLoopSummary = {
  // Status of the latest diagnosis loop run
  status: DiagnosisLoopStatus;

  // Timestamps (ISO format) - null if that event hasn't occurred
  latest_started_at: string | null;
  latest_completed_at: string | null;
  latest_failed_at: string | null;

  // Latest event metadata
  latest_event_id: string | null;
  latest_event_type: string | null;

  // Failure information (from failed events)
  unavailable_reason: string | null;

  // Check counts (from completed events)
  checks_requested: number | null;
  checks_run: number | null;
  checks_rejected: number | null;

  // Review packet availability
  review_packet_available: boolean;
  review_packet_id: string | null;

  // Safety flags - always True
  read_only: boolean;
  review_required_before_any_action: boolean;
  no_remediation_attempted: boolean;
};

/**
 * Bounded handoff payload for automatic diagnosis review packets.
 * Provides a safe, read-only markdown handoff for human/ChatGPT review.
 */
export type AutomaticDiagnosisReviewHandoffPayload = {
  // Availability state
  available: boolean;
  // When available=true: handoff fields
  incident_id?: string | null;
  artifact_type?: string | null;
  artifact_name?: string | null;
  run_id?: string | null;
  collector_run_id?: string | null;
  generated_at?: string | null;
  format?: string | null;
  content?: string | null;
  content_sha256?: string | null;
  read_only?: boolean | null;
  review_required_before_any_action?: boolean | null;
  no_remediation_attempted?: boolean | null;
  // When available=false: reason for unavailability
  unavailable_reason?: string | null;
};

/**
 * Incident detail payload - full case view.
 * Includes signals, evidence links, timeline, suggested checks, and
 * automatic diagnosis review summary.
 * Run artifacts remain evidence provenance, not the primary case object.
 *
 * Note: suggested_checks is a read-only compatibility projection.
 * Currently returns empty list when no next-check-to-incident mapping exists.
 *
 * Note: automatic_diagnosis_review provides a bounded summary of the latest
 * automatic diagnosis loop review packet. Raw packet contents are not exposed.
 *
 * Note: evidence_artifacts provides bounded metadata for evidence artifacts
 * linked to the incident. No raw artifact contents are exposed.
 */
export type IncidentDetailPayload = IncidentSummaryPayload & {
  source_candidate_id: string;
  signals: IncidentSignal[];
  evidence_needed: string[];
  evidence_links: IncidentEvidenceLink[];
  events: IncidentEvent[];
  // Evidence artifacts - bounded metadata for linked artifacts
  // No raw artifact contents, logs, stdout/stderr, stack traces, or secrets
  evidence_artifacts: EvidenceArtifact[];
  suggested_checks: IncidentSuggestedCheck[];
  automatic_diagnosis_review: AutomaticDiagnosisReviewPayload;
  // Automatic diagnosis loop summary - derived from timeline events
  automatic_diagnosis_loop_summary: AutomaticDiagnosisLoopSummary;
};

export type IncidentsListResponse = {
  incidents: IncidentSummaryPayload[];
  total: number;
};

// =============================================================================
// Incident Snapshot Types
// =============================================================================

export type IncidentSnapshotRequest = {
  namespace: string;
  since_hours?: number;
};

/**
 * Incident Candidate shape for frontend display
 */
export type IncidentCandidateSignal = {
  source: string;
  reason: string;
  message: string;
};

export type IncidentCandidate = {
  candidate_id: string;
  namespace: string;
  object_kind: string;
  object_name: string;
  class: string;
  severity: string;
  signals: IncidentCandidateSignal[];
  evidence_needed: string[];
  raw_object_kind?: string | null;
};

export type IncidentSnapshotSummary = {
  total_pods: number;
  failing_pods_count: number;
  total_deployments: number;
  total_events: number;
  symptoms_count: number;
  candidates_count: number;
  incidents_promoted_count: number;
};

export type IncidentSnapshotBundle = {
  metadata: {
    bundle_id: string;
    captured_at: string;
    namespace: string;
    since_hours: number;
    context: string | null;
    total_pods: number;
    total_events: number;
    total_deployments: number;
    failing_pods_count: number;
    symptoms_count: number;
    candidates_count: number;
  };
  pods: Array<{
    name: string;
    namespace: string;
    phase: string;
    health_status: string;
    restart_count: number;
    node: string | null;
    image_refs: string[];
    reason: string | null;
    message: string | null;
    is_failing: boolean;
  }>;
  events: Array<{
    namespace: string;
    name: string;
    type: string;
    reason: string;
    message: string;
    involved_object_kind: string | null;
    involved_object_name: string | null;
    count: number;
    last_timestamp: string | null;
  }>;
  deployments: Array<{
    name: string;
    namespace: string;
    replicas: number;
    available_replicas: number;
    ready_replicas: number;
    updated_replicas: number;
    available: boolean;
  }>;
  symptoms: Array<{
    symptom_type: string;
    pod_name: string | null;
    message: string;
    severity: string;
  }>;
  collection_errors: string[];
  candidates: IncidentCandidate[];
};

export type IncidentSnapshotResponse = {
  bundle_id: string;
  captured_at: string;
  namespace: string;
  summary: IncidentSnapshotSummary;
  bundle?: IncidentSnapshotBundle;
  error?: string | null;
};

// =============================================================================
// Incident Review Packet Types
// =============================================================================

export type IncidentReviewPacketRequest = {
  bundle: Record<string, unknown>;
  format?: "markdown";
};

export type IncidentReviewPacketResponse = {
  bundle_id: string;
  packet: string;
  format: string;
  error?: string | null;
};
