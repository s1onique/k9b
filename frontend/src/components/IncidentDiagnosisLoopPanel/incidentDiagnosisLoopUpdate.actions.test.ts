/**
 * incidentDiagnosisLoopUpdate.actions.test.ts — Action behavior tests.
 *
 * Tests which actions are accepted/rejected in each state.
 * Verifies that actions produce correct state changes or are properly ignored.
 */

import { update } from "./incidentDiagnosisLoopUpdate";
import {
  INCIDENT_ID,
  RUN_ID,
  createIdleState,
  createRunningState,
  createSuccessState,
  createErrorState,
  createFakeResponse,
  buildCheckToggledMsg,
  buildRunCompletedMsg,
  buildRunFailedMsg,
} from "./incidentDiagnosisLoopUpdate.testSupport";

// =============================================================================
// checkToggled Action Tests
// =============================================================================

describe("checkToggled action behavior", () => {
  describe("in idle state", () => {
    test("adds new check to selection", () => {
      const state = createIdleState();
      const msg = buildCheckToggledMsg("check-1");

      const next = update(state, msg);

      expect(next.tag).toBe("idle");
      if (next.tag === "idle") {
        expect(next.selectedCheckIds.has("check-1")).toBe(true);
      }
    });

    test("removes existing check from selection", () => {
      const state = createIdleState({ selectedCheckIds: new Set(["check-1", "check-2"]) });
      const msg = buildCheckToggledMsg("check-1");

      const next = update(state, msg);

      expect(next.tag).toBe("idle");
      if (next.tag === "idle") {
        expect(next.selectedCheckIds.has("check-1")).toBe(false);
        expect(next.selectedCheckIds.has("check-2")).toBe(true);
      }
    });
  });

  describe("in empty state", () => {
    test("is ignored", () => {
      const state = { tag: "empty" as const };
      const msg = buildCheckToggledMsg("check-1");

      const next = update(state, msg);

      expect(next).toEqual(state);
    });
  });

  describe("in running state", () => {
    test("is rejected while running", () => {
      const state = createRunningState(new Set(["check-1"]));
      const msg = buildCheckToggledMsg("check-2");

      const next = update(state, msg);

      // State unchanged - cannot toggle while running
      expect(next).toEqual(state);
    });
  });

  describe("in success state", () => {
    test("is ignored in success state", () => {
      const successState = createSuccessState(createFakeResponse());
      const msg = buildCheckToggledMsg("check-1");

      const next = update(successState, msg);

      // State unchanged - toggles don't affect current result
      expect(next).toEqual(successState);
    });
  });

  describe("in error state", () => {
    test("is ignored in error state", () => {
      const state = createErrorState("Network error");
      const msg = buildCheckToggledMsg("check-1");

      const next = update(state, msg);

      // State unchanged - toggles don't affect current error
      expect(next).toEqual(state);
    });
  });
});

// =============================================================================
// runCompleted Action Tests
// =============================================================================

describe("runCompleted action behavior", () => {
  describe("in idle state", () => {
    test("is rejected in idle state", () => {
      const state = createIdleState();
      const msg = buildRunCompletedMsg(INCIDENT_ID, RUN_ID, createFakeResponse());

      const next = update(state, msg);

      // State unchanged - cannot complete when idle
      expect(next).toEqual(state);
    });
  });

  describe("in empty state", () => {
    test("is rejected", () => {
      const state = { tag: "empty" as const };
      const msg = buildRunCompletedMsg(INCIDENT_ID, RUN_ID, createFakeResponse());

      const next = update(state, msg);

      expect(next).toEqual(state);
    });
  });

  describe("in success state", () => {
    test("is ignored in success state", () => {
      const successState = createSuccessState(createFakeResponse());
      const msg = buildRunCompletedMsg(INCIDENT_ID, "new-run", createFakeResponse());

      const next = update(successState, msg);

      // State unchanged - already succeeded
      expect(next).toEqual(successState);
    });
  });

  describe("in error state", () => {
    test("is rejected in error state", () => {
      const state = createErrorState("Network error");
      const msg = buildRunCompletedMsg(INCIDENT_ID, RUN_ID, createFakeResponse());

      const next = update(state, msg);

      // State unchanged - already failed
      expect(next).toEqual(state);
    });
  });

  describe("stale response handling", () => {
    test("rejects completion with wrong incidentId", () => {
      const state = createRunningState(new Set(["check-1"]));
      const msg = buildRunCompletedMsg(
        "different-incident",
        RUN_ID,
        createFakeResponse({ incident_id: "different-incident" }),
      );

      const next = update(state, msg);

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

      expect(next).toEqual(state);
    });
  });
});

// =============================================================================
// runFailed Action Tests
// =============================================================================

describe("runFailed action behavior", () => {
  describe("in idle state", () => {
    test("is rejected in idle state", () => {
      const state = createIdleState();
      const msg = buildRunFailedMsg(INCIDENT_ID, RUN_ID, "Network error");

      const next = update(state, msg);

      // State unchanged - cannot fail when idle
      expect(next).toEqual(state);
    });
  });

  describe("in empty state", () => {
    test("is rejected", () => {
      const state = { tag: "empty" as const };
      const msg = buildRunFailedMsg(INCIDENT_ID, RUN_ID, "Network error");

      const next = update(state, msg);

      expect(next).toEqual(state);
    });
  });

  describe("in success state", () => {
    test("is rejected in success state", () => {
      const successState = createSuccessState(createFakeResponse());
      const msg = buildRunFailedMsg(INCIDENT_ID, "new-run", "Should not happen");

      const next = update(successState, msg);

      // State unchanged - already succeeded
      expect(next).toEqual(successState);
    });
  });

  describe("stale failure handling", () => {
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
  });
});

// =============================================================================
// runRequested Action Tests
// =============================================================================

describe("runRequested action behavior", () => {
  describe("in empty state", () => {
    test("is ignored", () => {
      const state = { tag: "empty" as const };
      const msg = { type: "runRequested" as const, runId: RUN_ID };

      const next = update(state, msg);

      expect(next).toEqual(state);
    });
  });

  describe("in running state", () => {
    test("is ignored while already running", () => {
      const state = createRunningState(new Set(["check-1"]));
      const msg = { type: "runRequested" as const, runId: "new-run-id" };

      const next = update(state, msg);

      // State unchanged - already running
      expect(next).toEqual(state);
    });
  });

  describe("successful transitions", () => {
    test("transitions from idle to running", () => {
      const state = createIdleState({ selectedCheckIds: new Set(["check-1"]) });
      const msg = { type: "runRequested" as const, runId: RUN_ID };

      const next = update(state, msg);

      expect(next).toEqual({
        tag: "running",
        incidentId: INCIDENT_ID,
        runId: RUN_ID,
        selectedCheckIds: new Set(["check-1"]),
      });
    });

    test("transitions from success to running", () => {
      const successState = createSuccessState(createFakeResponse());
      const msg = { type: "runRequested" as const, runId: "new-run-id" };

      const next = update(successState, msg);

      expect(next.tag).toBe("running");
      if (next.tag === "running") {
        expect(next.runId).toBe("new-run-id");
        expect(next.selectedCheckIds.size).toBe(0);
      }
    });

    test("transitions from error to running (retry)", () => {
      const state = createErrorState("Network error");
      const msg = { type: "runRequested" as const, runId: "retry-run-id" };

      const next = update(state, msg);

      expect(next.tag).toBe("running");
      if (next.tag === "running") {
        expect(next.runId).toBe("retry-run-id");
      }
    });
  });
});

// =============================================================================
// resetRequested Action Tests
// =============================================================================

describe("resetRequested action behavior", () => {
  describe("in running state", () => {
    test("is rejected while running", () => {
      const state = createRunningState();
      const msg = { type: "resetRequested" as const };

      const next = update(state, msg);

      // State unchanged - must wait for completion or failure
      expect(next).toEqual(state);
    });
  });

  describe("successful transitions", () => {
    test("transitions from success to idle", () => {
      const successState = createSuccessState(createFakeResponse());
      const msg = { type: "resetRequested" as const };

      const next = update(successState, msg);

      expect(next).toEqual({
        tag: "idle",
        incidentId: INCIDENT_ID,
        selectedCheckIds: new Set(),
      });
    });

    test("transitions from error to idle", () => {
      const state = createErrorState("Network error");
      const msg = { type: "resetRequested" as const };

      const next = update(state, msg);

      expect(next).toEqual({
        tag: "idle",
        incidentId: INCIDENT_ID,
        selectedCheckIds: new Set(),
      });
    });
  });
});
