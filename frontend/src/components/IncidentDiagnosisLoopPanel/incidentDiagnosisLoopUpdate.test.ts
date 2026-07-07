/**
 * incidentDiagnosisLoopUpdate.test.ts — Unit tests for Elm-style reducer.
 *
 * Tests pure state transitions without mounting React components.
 * These tests prove the state machine guards against impossible states.
 *
 * The key tests:
 * 1. Valid transitions are allowed
 * 2. Invalid transitions are rejected (impossible states prevented)
 * 3. State is preserved when transitions are invalid
 * 4. Stale completions are rejected (runId ownership verification)
 */

import { update, toggleCheckId } from "./incidentDiagnosisLoopUpdate";
import type { DiagnosisLoopState, DiagnosisLoopMsg } from "./incidentDiagnosisLoopModel";
import type { DiagnosisLoopOnePassResponse } from "../../api/incidentDiagnosisLoop";

// =============================================================================
// Test Fixtures
// =============================================================================

const INCIDENT_ID = "test-incident-123";
const RUN_ID = "test-run-id";

const createFakeResponse = (overrides: Partial<DiagnosisLoopOnePassResponse> = {}): DiagnosisLoopOnePassResponse => ({
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

const createIdleState = (overrides: Partial<DiagnosisLoopState> = {}): DiagnosisLoopState => ({
  tag: "idle",
  incidentId: INCIDENT_ID,
  selectedCheckIds: new Set(),
  ...overrides,
} as DiagnosisLoopState);

const createRunningState = (selectedCheckIds: Set<string> = new Set(), runId: string = RUN_ID): DiagnosisLoopState => ({
  tag: "running",
  incidentId: INCIDENT_ID,
  runId,
  selectedCheckIds,
});

const createSuccessState = (response: DiagnosisLoopOnePassResponse, runId: string = RUN_ID): DiagnosisLoopState => ({
  tag: "success",
  incidentId: INCIDENT_ID,
  runId,
  selectedCheckIds: new Set(),
  response,
});

const createErrorState = (errorMessage: string = "Test error", runId: string = RUN_ID): DiagnosisLoopState => ({
  tag: "error",
  incidentId: INCIDENT_ID,
  runId,
  selectedCheckIds: new Set(),
  errorMessage,
});

// =============================================================================
// empty State Tests
// =============================================================================

describe("empty state transitions", () => {
  test("init transitions from empty to idle", () => {
    const state: DiagnosisLoopState = { tag: "empty" };
    const msg: DiagnosisLoopMsg = { type: "init", incidentId: INCIDENT_ID };

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "idle",
      incidentId: INCIDENT_ID,
      selectedCheckIds: new Set(),
    });
  });

  test("checkToggled is ignored in empty state", () => {
    const state: DiagnosisLoopState = { tag: "empty" };
    const msg: DiagnosisLoopMsg = { type: "checkToggled", checkId: "check-1" };

    const next = update(state, msg);

    expect(next).toEqual(state);
  });

  test("runRequested is ignored in empty state", () => {
    const state: DiagnosisLoopState = { tag: "empty" };
    const msg: DiagnosisLoopMsg = { type: "runRequested", runId: RUN_ID };

    const next = update(state, msg);

    expect(next).toEqual(state);
  });
});

// =============================================================================
// idle State Tests
// =============================================================================

describe("idle state transitions", () => {
  test("checkToggled adds new check to selection", () => {
    const state = createIdleState();
    const msg: DiagnosisLoopMsg = { type: "checkToggled", checkId: "check-1" };

    const next = update(state, msg);

    expect(next.tag).toBe("idle");
    if (next.tag === "idle") {
      expect(next.selectedCheckIds.has("check-1")).toBe(true);
    }
  });

  test("checkToggled removes existing check from selection", () => {
    const state = createIdleState({ selectedCheckIds: new Set(["check-1", "check-2"]) });
    const msg: DiagnosisLoopMsg = { type: "checkToggled", checkId: "check-1" };

    const next = update(state, msg);

    expect(next.tag).toBe("idle");
    if (next.tag === "idle") {
      expect(next.selectedCheckIds.has("check-1")).toBe(false);
      expect(next.selectedCheckIds.has("check-2")).toBe(true);
    }
  });

  test("runRequested transitions from idle to running with runId", () => {
    const state = createIdleState({ selectedCheckIds: new Set(["check-1"]) });
    const msg: DiagnosisLoopMsg = { type: "runRequested", runId: RUN_ID };

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "running",
      incidentId: INCIDENT_ID,
      runId: RUN_ID,
      selectedCheckIds: new Set(["check-1"]),
    });
  });

  test("init with same incidentId returns same state", () => {
    const state = createIdleState();
    const msg: DiagnosisLoopMsg = { type: "init", incidentId: INCIDENT_ID };

    const next = update(state, msg);

    expect(next).toEqual(state);
  });

  test("init with different incidentId resets state", () => {
    const state = createIdleState({ selectedCheckIds: new Set(["check-1"]) });
    const msg: DiagnosisLoopMsg = { type: "init", incidentId: "different-incident" };

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "idle",
      incidentId: "different-incident",
      selectedCheckIds: new Set(),
    });
  });

  test("runCompleted is rejected in idle state", () => {
    const state = createIdleState();
    const msg: DiagnosisLoopMsg = { type: "runCompleted", incidentId: INCIDENT_ID, runId: RUN_ID, response: createFakeResponse() };

    const next = update(state, msg);

    // State unchanged - cannot complete when idle
    expect(next).toEqual(state);
  });

  test("runFailed is rejected in idle state", () => {
    const state = createIdleState();
    const msg: DiagnosisLoopMsg = { type: "runFailed", incidentId: INCIDENT_ID, runId: RUN_ID, errorMessage: "Network error" };

    const next = update(state, msg);

    // State unchanged - cannot fail when idle
    expect(next).toEqual(state);
  });
});

// =============================================================================
// running State Tests
// =============================================================================

describe("running state transitions", () => {
  test("runCompleted transitions from running to success with matching runId", () => {
    const response = createFakeResponse();
    const state = createRunningState(new Set(["check-1"]));
    const msg: DiagnosisLoopMsg = { type: "runCompleted", incidentId: INCIDENT_ID, runId: RUN_ID, response };

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "success",
      incidentId: INCIDENT_ID,
      runId: RUN_ID,
      selectedCheckIds: new Set(["check-1"]),
      response,
    });
  });

  test("runFailed transitions from running to error with matching runId", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg: DiagnosisLoopMsg = { type: "runFailed", incidentId: INCIDENT_ID, runId: RUN_ID, errorMessage: "Server error" };

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "error",
      incidentId: INCIDENT_ID,
      runId: RUN_ID,
      selectedCheckIds: new Set(["check-1"]),
      errorMessage: "Server error",
    });
  });

  test("checkToggled is rejected while running", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg: DiagnosisLoopMsg = { type: "checkToggled", checkId: "check-2" };

    const next = update(state, msg);

    // State unchanged - cannot toggle while running
    expect(next).toEqual(state);
  });

  test("runRequested is ignored while already running", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg: DiagnosisLoopMsg = { type: "runRequested", runId: "new-run-id" };

    const next = update(state, msg);

    // State unchanged - already running
    expect(next).toEqual(state);
  });

  test("resetRequested is rejected while running", () => {
    const state = createRunningState();
    const msg: DiagnosisLoopMsg = { type: "resetRequested" };

    const next = update(state, msg);

    // State unchanged - must wait for completion or failure
    expect(next).toEqual(state);
  });
});

// =============================================================================
// success State Tests
// =============================================================================

describe("success state transitions", () => {
  const response = createFakeResponse();

  test("runRequested transitions from success to running (run another pass)", () => {
    const successState = createSuccessState(response);
    const msg: DiagnosisLoopMsg = { type: "runRequested", runId: "new-run-id" };

    const next = update(successState, msg);

    expect(next).toEqual({
      tag: "running",
      incidentId: INCIDENT_ID,
      runId: "new-run-id",
      selectedCheckIds: new Set(),
    });
  });

  test("resetRequested transitions from success to idle", () => {
    const successState = createSuccessState(response);
    const msg: DiagnosisLoopMsg = { type: "resetRequested" };

    const next = update(successState, msg);

    expect(next).toEqual({
      tag: "idle",
      incidentId: INCIDENT_ID,
      selectedCheckIds: new Set(),
    });
  });

  test("checkToggled is ignored in success state", () => {
    const successState = createSuccessState(response);
    const msg: DiagnosisLoopMsg = { type: "checkToggled", checkId: "check-1" };

    const next = update(successState, msg);

    // State unchanged - toggles don't affect current result
    expect(next).toEqual(successState);
  });

  test("runCompleted is ignored in success state", () => {
    const successState = createSuccessState(response);
    const msg: DiagnosisLoopMsg = { type: "runCompleted", incidentId: INCIDENT_ID, runId: "new-run", response: createFakeResponse() };

    const next = update(successState, msg);

    // State unchanged - already succeeded
    expect(next).toEqual(successState);
  });

  test("runFailed is rejected in success state", () => {
    const successState = createSuccessState(response);
    const msg: DiagnosisLoopMsg = { type: "runFailed", incidentId: INCIDENT_ID, runId: "new-run", errorMessage: "Should not happen" };

    const next = update(successState, msg);

    // State unchanged - already succeeded
    expect(next).toEqual(successState);
  });
});

// =============================================================================
// error State Tests
// =============================================================================

describe("error state transitions", () => {
  test("runRequested transitions from error to running (retry)", () => {
    const state = createErrorState("Network error");
    const msg: DiagnosisLoopMsg = { type: "runRequested", runId: "retry-run-id" };

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "running",
      incidentId: INCIDENT_ID,
      runId: "retry-run-id",
      selectedCheckIds: new Set(),
    });
  });

  test("resetRequested transitions from error to idle", () => {
    const state = createErrorState("Network error");
    const msg: DiagnosisLoopMsg = { type: "resetRequested" };

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "idle",
      incidentId: INCIDENT_ID,
      selectedCheckIds: new Set(),
    });
  });

  test("checkToggled is ignored in error state", () => {
    const state = createErrorState("Network error");
    const msg: DiagnosisLoopMsg = { type: "checkToggled", checkId: "check-1" };

    const next = update(state, msg);

    // State unchanged - toggles don't affect current error
    expect(next).toEqual(state);
  });

  test("runCompleted is rejected in error state", () => {
    const state = createErrorState("Network error");
    const msg: DiagnosisLoopMsg = { type: "runCompleted", incidentId: INCIDENT_ID, runId: RUN_ID, response: createFakeResponse() };

    const next = update(state, msg);

    // State unchanged - already failed
    expect(next).toEqual(state);
  });

  test("repeated runFailed updates error message", () => {
    const state = createErrorState("First error");
    const msg: DiagnosisLoopMsg = { type: "runFailed", incidentId: INCIDENT_ID, runId: "stale-run", errorMessage: "Second error" };

    const next = update(state, msg);

    expect(next.tag).toBe("error");
    if (next.tag === "error") {
      expect(next.errorMessage).toBe("Second error");
    }
  });
});

// =============================================================================
// Stale Completion Rejection Tests
// =============================================================================

describe("stale completion rejection", () => {
  test("rejects completion with wrong incidentId", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg: DiagnosisLoopMsg = {
      type: "runCompleted",
      incidentId: "different-incident",
      runId: RUN_ID,
      response: createFakeResponse({ incident_id: "different-incident" }),
    };

    const next = update(state, msg);

    // State unchanged - response is for different incident
    expect(next).toEqual(state);
  });

  test("rejects completion with wrong runId for same incident", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg: DiagnosisLoopMsg = {
      type: "runCompleted",
      incidentId: INCIDENT_ID,
      runId: "stale-run-id",
      response: createFakeResponse({ incident_id: INCIDENT_ID }),
    };

    const next = update(state, msg);

    // State unchanged - runId doesn't match
    expect(next).toEqual(state);
  });

  test("rejects failure with wrong incidentId", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg: DiagnosisLoopMsg = {
      type: "runFailed",
      incidentId: "different-incident",
      runId: RUN_ID,
      errorMessage: "Network error",
    };

    const next = update(state, msg);

    // State unchanged - failure is for different incident
    expect(next).toEqual(state);
  });

  test("rejects failure with wrong runId for same incident", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg: DiagnosisLoopMsg = {
      type: "runFailed",
      incidentId: INCIDENT_ID,
      runId: "stale-run-id",
      errorMessage: "stale failure",
    };

    const next = update(state, msg);

    // State unchanged - runId doesn't match
    expect(next).toEqual(state);
  });

  test("accepts completion with matching incidentId and runId", () => {
    const state = createRunningState(new Set(["check-1"]));
    const response = createFakeResponse();
    const msg: DiagnosisLoopMsg = {
      type: "runCompleted",
      incidentId: INCIDENT_ID,
      runId: RUN_ID,
      response,
    };

    const next = update(state, msg);

    expect(next.tag).toBe("success");
    if (next.tag === "success") {
      expect(next.runId).toBe(RUN_ID);
      expect(next.response).toBe(response);
    }
  });
});

// =============================================================================
// Impossible State Prevention Tests
// =============================================================================

describe("impossible state prevention", () => {
  /**
   * This is the key test from the Elmish recommendation.
   * It proves that the state machine prevents impossible transitions.
   */
  test("does not accept diagnosis completion while incident detail is still loading", () => {
    const state: DiagnosisLoopState = { tag: "loading" as const, incidentId: "inc-1" };
    const msg: DiagnosisLoopMsg = { type: "runCompleted", incidentId: INCIDENT_ID, runId: RUN_ID, response: createFakeResponse() };

    const next = update(state, msg);

    // Should remain in loading state, not transition to success
    expect(next).toEqual(state);
  });

  test("cannot transition to running without explicit runRequested", () => {
    const state = createIdleState();
    const msg: DiagnosisLoopMsg = { type: "checkToggled", checkId: "check-1" };

    const next = update(state, msg);

    // Still idle, not running
    expect(next.tag).toBe("idle");
  });

  test("cannot skip running state to reach success", () => {
    const state = createIdleState();
    const msg: DiagnosisLoopMsg = { type: "runCompleted", incidentId: INCIDENT_ID, runId: RUN_ID, response: createFakeResponse() };

    const next = update(state, msg);

    // Cannot go directly to success from idle
    expect(next.tag).toBe("idle");
  });

  test("cannot skip running state to reach error", () => {
    const state = createIdleState();
    const msg: DiagnosisLoopMsg = { type: "runFailed", incidentId: INCIDENT_ID, runId: RUN_ID, errorMessage: "Error" };

    const next = update(state, msg);

    // Cannot go directly to error from idle
    expect(next.tag).toBe("idle");
  });
});

// =============================================================================
// toggleCheckId Helper Tests
// =============================================================================

describe("toggleCheckId", () => {
  test("adds checkId when not present", () => {
    const set = new Set<string>(["a", "b"]);
    const result = toggleCheckId(set, "c");

    expect(result).toEqual(new Set(["a", "b", "c"]));
    // Original set unchanged
    expect(set).toEqual(new Set(["a", "b"]));
  });

  test("removes checkId when present", () => {
    const set = new Set<string>(["a", "b", "c"]);
    const result = toggleCheckId(set, "b");

    expect(result).toEqual(new Set(["a", "c"]));
    // Original set unchanged
    expect(set).toEqual(new Set(["a", "b", "c"]));
  });

  test("returns new Set instance (immutability)", () => {
    const set = new Set<string>();
    const result = toggleCheckId(set, "x");

    expect(result).not.toBe(set);
    expect(set.size).toBe(0);
    expect(result.size).toBe(1);
  });
});
