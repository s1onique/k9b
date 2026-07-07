/**
 * incidentDiagnosisLoopUpdate.testSupport.ts — Shared test fixtures.
 *
 * Builders and fake payloads for incidentDiagnosisLoopUpdate reducer tests.
 * No test blocks (describe/it/test) in this file.
 */

import type { DiagnosisLoopState, DiagnosisLoopMsg } from "./incidentDiagnosisLoopModel";
import type { DiagnosisLoopOnePassResponse } from "../../api/incidentDiagnosisLoop";

// =============================================================================
// Constants
// =============================================================================

export const INCIDENT_ID = "test-incident-123";
export const RUN_ID = "test-run-id";

// =============================================================================
// Fake Payload Builders
// =============================================================================

export const createFakeResponse = (
  overrides: Partial<DiagnosisLoopOnePassResponse> = {},
): DiagnosisLoopOnePassResponse => ({
  schema_version: "1.0",
  incident_id: INCIDENT_ID,
  run_id: "manual-loop-2026-01-01T00-00-00",
  read_only: true,
  allowed_actions: [],
  decision: "test-decision",
  checks_requested: 1,
  checks_run: 1,
  checks_skipped: 0,
  checks_rejected: 0,
  artifacts: {
    read_only_check_results: { written: true, name: "test-results.json" },
    diagnosis_loop_pass: { written: true, name: "test-pass.json" },
  },
  case_file_linked_artifact: true,
  safety_metadata: {
    read_only: true,
    allowed_actions: [],
    no_kubernetes_client: true,
    no_shell: true,
    no_subprocess: true,
    no_kubectl: true,
    no_mutation: true,
    fake_runner: true,
    one_pass_only: true,
  },
  ...overrides,
});

// =============================================================================
// State Builders
// =============================================================================

export const createEmptyState = (): DiagnosisLoopState => ({ tag: "empty" });

export const createIdleState = (
  overrides: Partial<DiagnosisLoopState> = {},
): DiagnosisLoopState => ({
  tag: "idle",
  incidentId: INCIDENT_ID,
  selectedCheckIds: new Set(),
  ...overrides,
} as DiagnosisLoopState);

export const createRunningState = (
  selectedCheckIds: Set<string> = new Set(),
  runId: string = RUN_ID,
): DiagnosisLoopState => ({
  tag: "running",
  incidentId: INCIDENT_ID,
  runId,
  selectedCheckIds,
});

export const createSuccessState = (
  response: DiagnosisLoopOnePassResponse,
  runId: string = RUN_ID,
): DiagnosisLoopState => ({
  tag: "success",
  incidentId: INCIDENT_ID,
  runId,
  selectedCheckIds: new Set(),
  response,
});

export const createErrorState = (
  errorMessage: string = "Test error",
  runId: string = RUN_ID,
): DiagnosisLoopState => ({
  tag: "error",
  incidentId: INCIDENT_ID,
  runId,
  selectedCheckIds: new Set(),
  errorMessage,
});

// =============================================================================
// Message Builders
// =============================================================================

export const buildInitMsg = (incidentId: string): DiagnosisLoopMsg => ({
  type: "init",
  incidentId,
});

export const buildCheckToggledMsg = (checkId: string): DiagnosisLoopMsg => ({
  type: "checkToggled",
  checkId,
});

export const buildRunRequestedMsg = (runId: string): DiagnosisLoopMsg => ({
  type: "runRequested",
  runId,
});

export const buildResetRequestedMsg = (): DiagnosisLoopMsg => ({
  type: "resetRequested",
});

export const buildRunCompletedMsg = (
  incidentId: string,
  runId: string,
  response: DiagnosisLoopOnePassResponse,
): DiagnosisLoopMsg => ({
  type: "runCompleted",
  incidentId,
  runId,
  response,
});

export const buildRunFailedMsg = (
  incidentId: string,
  runId: string,
  errorMessage: string,
): DiagnosisLoopMsg => ({
  type: "runFailed",
  incidentId,
  runId,
  errorMessage,
});
