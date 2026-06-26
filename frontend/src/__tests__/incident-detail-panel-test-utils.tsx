/**
 * Shared test utilities for IncidentDetailPanel tests.
 *
 * Provides common fixtures, render helpers, and mock setups
 * to reduce duplication across split test files.
 */

import type { IncidentDetailPayload } from "../api";

/**
 * Default fixture for IncidentDetailPayload.
 * Use as the base for all test incidents, then override specific fields.
 */
export const createIncidentFixture = (
  overrides: Partial<IncidentDetailPayload> = {},
): IncidentDetailPayload => ({
  incident_id: "default-pod-test-pod-crash_loop",
  namespace: "default",
  object_kind: "Pod",
  object_name: "test-pod",
  raw_object_kind: null,
  candidate_class: "crash_loop",
  severity: "error",
  status: "open",
  first_observed_at: "2026-01-01T12:00:00Z",
  last_observed_at: "2026-01-01T14:00:00Z",
  signal_count: 2,
  evidence_count: 3,
  latest_snapshot_bundle_id: "default-20260101-140000",
  review_packet: {
    status: "not_generated",
    id: null,
    generated_at: null,
    error_message: null,
  },
  suppressed_reason: null,
  duplicate_of: null,
  resolved_at: null,
  resolution_notes: null,
  source_candidate_id: "candidate-abc",
  signals: [],
  evidence_needed: [],
  evidence_links: [],
  events: [],
  evidence_artifacts: [],
  suggested_checks: [],
  automatic_diagnosis_review: {
    available: false,
    unavailable_reason: "no_review_packet",
  },
  automatic_diagnosis_loop_summary: {
    status: "not_run",
    latest_started_at: null,
    latest_completed_at: null,
    latest_failed_at: null,
    latest_event_id: null,
    latest_event_type: null,
    unavailable_reason: null,
    checks_requested: null,
    checks_run: null,
    checks_rejected: null,
    review_packet_available: false,
    review_packet_id: null,
    read_only: true,
    review_required_before_any_action: true,
    no_remediation_attempted: true,
  },
  ...overrides,
});
