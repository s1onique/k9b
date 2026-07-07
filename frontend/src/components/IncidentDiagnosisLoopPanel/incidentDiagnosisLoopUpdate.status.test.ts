/**
 * incidentDiagnosisLoopUpdate.status.test.ts — State transition tests.
 *
 * Tests pure state transitions for the Elm-style reducer.
 * Proves the state machine guards against impossible states.
 *
 * Key behaviors tested:
 * 1. Valid transitions are allowed
 * 2. Invalid transitions are rejected (impossible states prevented)
 * 3. State is preserved when transitions are invalid
 * 4. Stale completions are rejected (runId ownership verification)
 */

import { update } from "./incidentDiagnosisLoopUpdate";
import type { DiagnosisLoopState } from "./incidentDiagnosisLoopModel";
import {
  INCIDENT_ID,
  RUN_ID,
  createEmptyState,
  createIdleState,
  createRunningState,
  createSuccessState,
  createErrorState,
  createFakeResponse,
  buildRunRequestedMsg,
  buildCheckToggledMsg,
  buildInitMsg,
  buildRunCompletedMsg,
  buildRunFailedMsg,
  buildResetRequestedMsg,
} from "./incidentDiagnosisLoopUpdate.testSupport";

// =============================================================================
// empty State Tests
// =============================================================================

describe("empty state transitions", () => {
  test("init transitions from empty to idle", () => {
    const state = createEmptyState();
    const msg = buildInitMsg(INCIDENT_ID);

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "idle",
      incidentId: INCIDENT_ID,
      selectedCheckIds: new Set(),
    });
  });

  test("checkToggled is ignored in empty state", () => {
    const state = createEmptyState();
    const msg = buildCheckToggledMsg("check-1");

    const next = update(state, msg);

    expect(next).toEqual(state);
  });

  test("runRequested is ignored in empty state", () => {
    const state = createEmptyState();
    const msg = buildRunRequestedMsg(RUN_ID);

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
    const msg = buildCheckToggledMsg("check-1");

    const next = update(state, msg);

    expect(next.tag).toBe("idle");
    if (next.tag === "idle") {
      expect(next.selectedCheckIds.has("check-1")).toBe(true);
    }
  });

  test("checkToggled removes existing check from selection", () => {
    const state = createIdleState({ selectedCheckIds: new Set(["check-1", "check-2"]) });
    const msg = buildCheckToggledMsg("check-1");

    const next = update(state, msg);

    expect(next.tag).toBe("idle");
    if (next.tag === "idle") {
      expect(next.selectedCheckIds.has("check-1")).toBe(false);
      expect(next.selectedCheckIds.has("check-2")).toBe(true);
    }
  });

  test("runRequested transitions from idle to running with runId", () => {
    const state = createIdleState({ selectedCheckIds: new Set(["check-1"]) });
    const msg = buildRunRequestedMsg(RUN_ID);

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
    const msg = buildInitMsg(INCIDENT_ID);

    const next = update(state, msg);

    expect(next).toEqual(state);
  });

  test("init with different incidentId resets state", () => {
    const state = createIdleState({ selectedCheckIds: new Set(["check-1"]) });
    const msg = buildInitMsg("different-incident");

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "idle",
      incidentId: "different-incident",
      selectedCheckIds: new Set(),
    });
  });
});

// =============================================================================
// running State Tests
// =============================================================================

describe("running state transitions", () => {
  test("runCompleted transitions from running to success with matching runId", () => {
    const response = createFakeResponse();
    const state = createRunningState(new Set(["check-1"]));
    const msg = buildRunCompletedMsg(INCIDENT_ID, RUN_ID, response);

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
    const msg = buildRunFailedMsg(INCIDENT_ID, RUN_ID, "Server error");

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "error",
      incidentId: INCIDENT_ID,
      runId: RUN_ID,
      selectedCheckIds: new Set(["check-1"]),
      errorMessage: "Server error",
    });
  });

  test("runRequested is ignored while already running", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg = buildRunRequestedMsg("new-run-id");

    const next = update(state, msg);

    // State unchanged - already running
    expect(next).toEqual(state);
  });

  test("resetRequested is rejected while running", () => {
    const state = createRunningState();
    const msg = buildResetRequestedMsg();

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
    const msg = buildRunRequestedMsg("new-run-id");

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
    const msg = buildResetRequestedMsg();

    const next = update(successState, msg);

    expect(next).toEqual({
      tag: "idle",
      incidentId: INCIDENT_ID,
      selectedCheckIds: new Set(),
    });
  });

  test("runRequested transitions from success to running (retry)", () => {
    const successState = createSuccessState(response);
    const msg = buildRunRequestedMsg("retry-run-id");

    const next = update(successState, msg);

    expect(next.tag).toBe("running");
    if (next.tag === "running") {
      expect(next.runId).toBe("retry-run-id");
    }
  });
});

// =============================================================================
// error State Tests
// =============================================================================

describe("error state transitions", () => {
  test("runRequested transitions from error to running (retry)", () => {
    const state = createErrorState("Network error");
    const msg = buildRunRequestedMsg("retry-run-id");

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
    const msg = buildResetRequestedMsg();

    const next = update(state, msg);

    expect(next).toEqual({
      tag: "idle",
      incidentId: INCIDENT_ID,
      selectedCheckIds: new Set(),
    });
  });

  test("repeated runFailed updates error message", () => {
    const state = createErrorState("First error");
    const msg = buildRunFailedMsg(INCIDENT_ID, "stale-run", "Second error");

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
    const msg = buildRunCompletedMsg(
      "different-incident",
      RUN_ID,
      createFakeResponse({ incident_id: "different-incident" }),
    );

    const next = update(state, msg);

    // State unchanged - response is for different incident
    expect(next).toEqual(state);
  });

  test("rejects completion with wrong runId for same incident", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg = buildRunCompletedMsg(
      INCIDENT_ID,
      "stale-run-id",
      createFakeResponse({ incident_id: INCIDENT_ID }),
    );

    const next = update(state, msg);

    // State unchanged - runId doesn't match
    expect(next).toEqual(state);
  });

  test("rejects failure with wrong incidentId", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg = buildRunFailedMsg("different-incident", RUN_ID, "Network error");

    const next = update(state, msg);

    // State unchanged - failure is for different incident
    expect(next).toEqual(state);
  });

  test("rejects failure with wrong runId for same incident", () => {
    const state = createRunningState(new Set(["check-1"]));
    const msg = buildRunFailedMsg(INCIDENT_ID, "stale-run-id", "stale failure");

    const next = update(state, msg);

    // State unchanged - runId doesn't match
    expect(next).toEqual(state);
  });

  test("accepts completion with matching incidentId and runId", () => {
    const state = createRunningState(new Set(["check-1"]));
    const response = createFakeResponse();
    const msg = buildRunCompletedMsg(INCIDENT_ID, RUN_ID, response);

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
    const msg = buildRunCompletedMsg(INCIDENT_ID, RUN_ID, createFakeResponse());

    const next = update(state, msg);

    // Should remain in loading state, not transition to success
    expect(next).toEqual(state);
  });

  test("cannot transition to running without explicit runRequested", () => {
    const state = createIdleState();
    const msg = buildCheckToggledMsg("check-1");

    const next = update(state, msg);

    // Still idle, not running
    expect(next.tag).toBe("idle");
  });

  test("cannot skip running state to reach success", () => {
    const state = createIdleState();
    const msg = buildRunCompletedMsg(INCIDENT_ID, RUN_ID, createFakeResponse());

    const next = update(state, msg);

    // Cannot go directly to success from idle
    expect(next.tag).toBe("idle");
  });

  test("cannot skip running state to reach error", () => {
    const state = createIdleState();
    const msg = buildRunFailedMsg(INCIDENT_ID, RUN_ID, "Error");

    const next = update(state, msg);

    // Cannot go directly to error from idle
    expect(next.tag).toBe("idle");
  });
});
