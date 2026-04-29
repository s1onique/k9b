/**
 * runControlReducer.test.ts — Unit tests for the run-control reducer.
 *
 * Phase 1: Tests all 24 reducer scenarios.
 */
import { describe, expect, test } from "vitest";
import {
  createInitialRunControlModel,
  updateRunControl,
  getSelectedRunId,
  getLatestRunId,
  shouldShowRunLoading,
  shouldShowLatestJump,
  getHeaderRunId,
  getRunOwnedPanelState,
} from "../index";
import type {
  RunControlModel,
  RunPayload,
  RunsListPayload,
} from "../../types";

// ============================================================================
// Test fixtures
// ============================================================================

const makeRunsListPayload = (
  runs: Array<{ runId: string; runLabel: string }>
): RunsListPayload => ({
  runs: runs.map((r, idx) => ({
    runId: r.runId,
    runLabel: r.runLabel,
    timestamp: `2026-04-07T${10 + idx}:00:00Z`,
    clusterCount: 2,
    triaged: true,
    executionCount: 5,
    reviewedCount: 5,
    reviewStatus: "fully-reviewed",
  })),
  totalCount: runs.length,
  executionCountsComplete: true,
});

const makeRunPayload = (runId: string): RunPayload => ({
  runId,
  label: `Test run ${runId}`,
  timestamp: "2026-04-07T12:00:00Z",
  collectorVersion: "v1.0",
  clusterCount: 2,
  drilldownCount: 5,
  proposalCount: 4,
  externalAnalysisCount: 1,
  notificationCount: 2,
  artifacts: [],
  runStats: {
    lastRunDurationSeconds: 30,
    totalRuns: 12,
    p50RunDurationSeconds: 24,
    p95RunDurationSeconds: 48,
    p99RunDurationSeconds: 64,
  },
  llmStats: {
    totalCalls: 3,
    successfulCalls: 2,
    failedCalls: 1,
    lastCallTimestamp: null,
    p50LatencyMs: 110,
    p95LatencyMs: 220,
    p99LatencyMs: 300,
    providerBreakdown: [],
    scope: "current_run",
  },
  llmActivity: { entries: [], summary: { retainedEntries: 0 } },
});

// ============================================================================
// Tests
// ============================================================================

describe("runControlReducer", () => {
  describe("Boot", () => {
    test("1. emits fetchRuns and marks runs loading", () => {
      const model = createInitialRunControlModel();
      const nowMs = 1000;

      const result = updateRunControl(model, { type: "Boot", nowMs });

      expect(result.effects).toHaveLength(1);
      expect(result.effects[0].type).toBe("fetchRuns");
      expect((result.effects[0] as { reason: string }).reason).toBe("boot");
      expect(result.model.runs.status).toBe("loading");
      expect(result.model.runs.requestSeq).toBe(1);
      expect(result.model.nextRequestSeq).toBe(2);
    });
  });

  describe("RunsLoaded", () => {
    test("2. with empty list leaves selectedRun idle", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([]);
      const nowMs = 1000;

      // First boot to set up runs request
      const { model: m1 } = updateRunControl(model, {
        type: "Boot",
        nowMs,
      });

      // Then load runs
      const result = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      expect(result.model.selectedRun.status).toBe("idle");
      expect(result.model.selection.selectedRunId).toBeNull();
    });

    test("3. with no selection selects latest and emits fetchRun plus slow timer", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-latest", runLabel: "Latest" },
      ]);
      const nowMs = 1000;

      // Boot
      const { model: m1 } = updateRunControl(model, {
        type: "Boot",
        nowMs,
      });

      // Load runs
      const result = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      expect(result.model.selection.selectedRunId).toBe("run-latest");
      expect(result.model.selection.selectedReason).toBe("boot");
      expect(result.model.selectedRun.status).toBe("loading");
      expect(result.model.selectedRun.requestedRunId).toBe("run-latest");
      expect(result.effects.some((e) => e.type === "fetchRun")).toBe(true);
      expect(result.effects.some((e) => e.type === "scheduleSlowRunTimer")).toBe(
        true
      );
    });

    test(
      "4. while viewing historical selection preserves historical selection and does not refetch",
      () => {
        const model = createInitialRunControlModel();
        const payload = makeRunsListPayload([
          { runId: "run-latest", runLabel: "Latest" },
          { runId: "run-historical", runLabel: "Historical" },
        ]);
        const nowMs = 1000;

        // Boot -> seq=1
        const { model: m1 } = updateRunControl(model, {
          type: "Boot",
          nowMs,
        });

        // Load runs - latest selected -> seq=1
        const { model: m2 } = updateRunControl(m1, {
          type: "RunsLoaded",
          requestSeq: 1,
          payload,
          receivedAtMs: nowMs + 100,
        });

        // User selects historical -> allocates seq=3
        const { model: m3 } = updateRunControl(m2, {
          type: "RunSelected",
          runId: "run-historical",
          nowMs: nowMs + 200,
        });

        // Load historical run -> seq=3
        const { model: m4 } = updateRunControl(m3, {
          type: "RunLoaded",
          requestSeq: 3,
          runId: "run-historical",
          payload: makeRunPayload("run-historical"),
          receivedAtMs: nowMs + 300,
        });

        // PollTick -> allocates seq=5, sets runs.requestSeq=5
        const { model: m5 } = updateRunControl(m4, {
          type: "PollTick",
          nowMs: nowMs + 350,
        });

        // RunsLoaded with seq=5 (from PollTick) - historical still in list
        const result = updateRunControl(m5, {
          type: "RunsLoaded",
          requestSeq: 5,
          payload,
          receivedAtMs: nowMs + 400,
        });

        // Selection should be preserved
        expect(result.model.selection.selectedRunId).toBe("run-historical");
        // No refetch of selected run
        expect(
          result.effects.some(
            (e) => e.type === "fetchRun" && (e as { runId: string }).runId === "run-historical"
          )
        ).toBe(false);
      }
    );

    test("5. with newer latest sets hasNewerLatest=true", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-new-latest", runLabel: "New Latest" },
        { runId: "run-old", runLabel: "Old" },
      ]);
      const nowMs = 1000;

      // Boot -> seq=1
      const { model: m1 } = updateRunControl(model, {
        type: "Boot",
        nowMs,
      });

      // Load runs - latest selected -> seq=1
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      // User switches to old run -> allocates seq=3
      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-old",
        nowMs: nowMs + 200,
      });

      // PollTick -> allocates seq=5, sets runs.requestSeq=5
      const { model: m4 } = updateRunControl(m3, {
        type: "PollTick",
        nowMs: nowMs + 300,
      });

      // RunsLoaded with seq=5 (from PollTick) - new latest appears
      const result = updateRunControl(m4, {
        type: "RunsLoaded",
        requestSeq: 5,
        payload: makeRunsListPayload([
          { runId: "run-newest", runLabel: "Newest" },
          { runId: "run-new-latest", runLabel: "New Latest" },
          { runId: "run-old", runLabel: "Old" },
        ]),
        receivedAtMs: nowMs + 400,
      });

      expect(result.model.freshness.hasNewerLatest).toBe(true);
    });

    test("6. ignores stale response", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-latest", runLabel: "Latest" },
      ]);
      const nowMs = 1000;

      // Boot with seq=1
      const { model: m1 } = updateRunControl(model, {
        type: "Boot",
        nowMs,
      });

      // Try to load with stale seq=99
      const result = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 99,
        payload,
        receivedAtMs: nowMs + 100,
      });

      expect(result.model.runs.status).toBe("loading"); // unchanged
      expect(result.model.runs.items).toEqual([]);
    });
  });

  describe("RunsFailed", () => {
    test("7. ignores stale failure", () => {
      const model = createInitialRunControlModel();
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, {
        type: "Boot",
        nowMs,
      });

      const result = updateRunControl(m1, {
        type: "RunsFailed",
        requestSeq: 99,
        error: "Network error",
        failedAtMs: nowMs + 100,
      });

      expect(result.model.runs.status).toBe("loading"); // unchanged
      expect(result.model.runs.error).toBeNull();
    });

    test("7b. stale failure after newer success is ignored", () => {
      const model = createInitialRunControlModel();
      const nowMs = 1000;
      const payload = makeRunsListPayload([
        { runId: "run-latest", runLabel: "Latest" },
      ]);

      // Boot -> seq=1
      const { model: m1 } = updateRunControl(model, {
        type: "Boot",
        nowMs,
      });

      // Success with seq=1
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      // Trigger new poll (allocates seq=3)
      const { model: m3 } = updateRunControl(m2, {
        type: "PollTick",
        nowMs: nowMs + 200,
      });

      // Late failure for old seq=1 should be ignored
      const result = updateRunControl(m3, {
        type: "RunsFailed",
        requestSeq: 1, // stale - seq=1 is older than current seq=3
        error: "Network error",
        failedAtMs: nowMs + 300,
      });

      expect(result.model.runs.status).toBe("loading"); // from PollTick
      expect(result.model.runs.error).toBeNull();
    });
  });

  describe("LatestClicked", () => {
    test("8. selects latest, clears hasNewerLatest, emits fetchRun plus slow timer", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-latest", runLabel: "Latest" },
      ]);
      const nowMs = 1000;

      // Boot and load
      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      // Click latest
      const result = updateRunControl(m2, {
        type: "LatestClicked",
        nowMs: nowMs + 200,
      });

      expect(result.model.selection.selectedRunId).toBe("run-latest");
      expect(result.model.selection.selectedReason).toBe("latest-click");
      expect(result.model.freshness.hasNewerLatest).toBe(false);
      expect(result.effects.some((e) => e.type === "fetchRun")).toBe(true);
      expect(
        result.effects.some((e) => e.type === "scheduleSlowRunTimer")
      ).toBe(true);
    });

    test("9. with no latest is no-op", () => {
      const model = createInitialRunControlModel();
      const nowMs = 1000;

      const result = updateRunControl(model, {
        type: "LatestClicked",
        nowMs,
      });

      expect(result.model).toBe(model);
      expect(result.effects).toEqual([]);
    });
  });

  describe("RunSelected", () => {
    test("10. emits fetchRun and slow timer", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const result = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      expect(result.model.selection.selectedRunId).toBe("run-123");
      expect(result.model.selectedRun.status).toBe("loading");
      expect(result.effects.some((e) => e.type === "fetchRun")).toBe(true);
      expect(
        result.effects.some((e) => e.type === "scheduleSlowRunTimer")
      ).toBe(true);
    });

    test("11. clears payload when previous payload belongs to a different run", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
        { runId: "run-456", runLabel: "Run 456" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      // Select and load run-123
      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const { model: m4 } = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 3,
        runId: "run-123",
        payload: makeRunPayload("run-123"),
        receivedAtMs: nowMs + 300,
      });

      // Now select run-456 (allocates new seq, clears payload)
      const result = updateRunControl(m4, {
        type: "RunSelected",
        runId: "run-456",
        nowMs: nowMs + 400,
      });

      expect(result.model.selectedRun.payload).toBeNull();
    });

    test("12. preserves payload when previous payload belongs to same run", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const runPayload = makeRunPayload("run-123");
      const { model: m4 } = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 3,
        runId: "run-123",
        payload: runPayload,
        receivedAtMs: nowMs + 300,
      });

      // Select same run again
      // Since payload.runId === runId, the payload should be preserved
      const result = updateRunControl(m4, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 400,
      });

      // The payload should be preserved because it belongs to the same run
      expect(result.model.selectedRun.payload).toBe(runPayload);
    });
  });

  describe("RunLoaded", () => {
    test("13. accepted when requestSeq and runId match", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;
      const runPayload = makeRunPayload("run-123");

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      // RunSelected allocates seq = 3
      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      // RunLoaded must use seq = 3 to match
      const result = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 3,
        runId: "run-123",
        payload: runPayload,
        receivedAtMs: nowMs + 300,
      });

      expect(result.model.selectedRun.status).toBe("loaded");
      expect(result.model.selectedRun.payload).toBe(runPayload);
      expect(
        result.effects.some((e) => e.type === "cancelSlowRunTimer")
      ).toBe(true);
    });

    test("14. ignored when requestSeq is stale", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      // Send stale response (seq 99 instead of 3)
      const result = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 99, // stale
        runId: "run-123",
        payload: makeRunPayload("run-123"),
        receivedAtMs: nowMs + 300,
      });

      expect(result.model.selectedRun.status).toBe("loading"); // unchanged
      expect(result.model.selectedRun.payload).toBeNull();
    });

    test("15. ignored when runId does not match requestedRunId", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
        { runId: "run-456", runLabel: "Run 456" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      // Response is for different run
      const result = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 3,
        runId: "run-456", // wrong run
        payload: makeRunPayload("run-456"),
        receivedAtMs: nowMs + 300,
      });

      expect(result.model.selectedRun.status).toBe("loading"); // unchanged
    });
  });

  describe("RunFailed", () => {
    test("16. preserves old payload only when runId matches", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;
      const runPayload = makeRunPayload("run-123");

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const { model: m4 } = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 3,
        runId: "run-123",
        payload: runPayload,
        receivedAtMs: nowMs + 300,
      });

      // Fail with matching runId - payload preserved
      const result = updateRunControl(m4, {
        type: "RunFailed",
        requestSeq: 3,
        runId: "run-123",
        error: "Server error",
        failedAtMs: nowMs + 400,
      });

      expect(result.model.selectedRun.status).toBe("failed");
      expect(result.model.selectedRun.error).toBe("Server error");
      expect(result.model.selectedRun.payload).toBe(runPayload);
    });

    test("16b. stale selected-run failure after newer success is ignored", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;
      const payloadB = makeRunPayload("run-123");

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      // RunSelected creates request A (seq=3)
      const { model: m3, effects: effectsA } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });
      const seqA = (effectsA.find((e) => e.type === "fetchRun") as { requestSeq: number }).requestSeq;

      // RetrySelectedRunClicked creates request B (seq=5)
      const { model: m4, effects: effectsB } = updateRunControl(m3, {
        type: "RetrySelectedRunClicked",
        nowMs: nowMs + 300,
      });
      const seqB = (effectsB.find((e) => e.type === "fetchRun") as { requestSeq: number }).requestSeq;

      // RunLoaded with seq B succeeds
      const { model: m5 } = updateRunControl(m4, {
        type: "RunLoaded",
        requestSeq: seqB,
        runId: "run-123",
        payload: payloadB,
        receivedAtMs: nowMs + 400,
      });

      // Late RunFailed for seq A should be ignored
      const result = updateRunControl(m5, {
        type: "RunFailed",
        requestSeq: seqA,
        runId: "run-123",
        error: "Network error",
        failedAtMs: nowMs + 500,
      });

      // State should remain from RunLoaded(seq B)
      expect(result.model.selectedRun.status).toBe("loaded");
      expect(result.model.selectedRun.payload).toBe(payloadB);
      expect(result.model.selectedRun.error).toBeNull();
      // No cancelSlowRunTimer for stale failure
      expect(
        result.effects.some((e) => e.type === "cancelSlowRunTimer" && (e as { requestSeq: number }).requestSeq === seqA)
      ).toBe(false);
    });
  });

  describe("RunSlowThresholdReached", () => {
    test("17. changes loading to slow", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const result = updateRunControl(m3, {
        type: "RunSlowThresholdReached",
        requestSeq: 3,
        runId: "run-123",
      });

      expect(result.model.selectedRun.status).toBe("slow");
    });

    test("18. ignored after loaded", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const { model: m4 } = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 3,
        runId: "run-123",
        payload: makeRunPayload("run-123"),
        receivedAtMs: nowMs + 300,
      });

      const result = updateRunControl(m4, {
        type: "RunSlowThresholdReached",
        requestSeq: 3,
        runId: "run-123",
      });

      expect(result.model.selectedRun.status).toBe("loaded"); // unchanged
    });
  });

  describe("ManualRefreshClicked", () => {
    test("19. fetches runs and preserves selectedRunId/payload", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;
      const runPayload = makeRunPayload("run-123");

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const { model: m4 } = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 3,
        runId: "run-123",
        payload: runPayload,
        receivedAtMs: nowMs + 300,
      });

      const result = updateRunControl(m4, {
        type: "ManualRefreshClicked",
        nowMs: nowMs + 400,
      });

      expect(result.model.runs.status).toBe("loading");
      expect(result.model.runs.lastRefreshReason).toBe("manual");
      expect(result.model.selectedRun.status).toBe("loaded"); // preserved
      expect(result.model.selectedRun.payload).toBe(runPayload); // preserved
    });
  });

  describe("PollTick", () => {
    test("20. fetches runs and preserves selectedRunId/payload", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;
      const runPayload = makeRunPayload("run-123");

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const { model: m4 } = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 3,
        runId: "run-123",
        payload: runPayload,
        receivedAtMs: nowMs + 300,
      });

      const result = updateRunControl(m4, {
        type: "PollTick",
        nowMs: nowMs + 400,
      });

      expect(result.model.runs.status).toBe("loading");
      expect(result.model.runs.lastRefreshReason).toBe("poll");
      expect(result.model.selectedRun.status).toBe("loaded"); // preserved
      expect(result.model.selectedRun.payload).toBe(runPayload); // preserved
    });
  });

  describe("RetrySelectedRunClicked", () => {
    test("21. refetches selected run", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const result = updateRunControl(m3, {
        type: "RetrySelectedRunClicked",
        nowMs: nowMs + 400,
      });

      expect(result.model.selectedRun.status).toBe("loading");
      expect(result.effects.some((e) => e.type === "fetchRun")).toBe(true);
      expect(
        result.effects.some((e) => e.type === "scheduleSlowRunTimer")
      ).toBe(true);
    });
  });

  describe("SelectionCleared", () => {
    test("22. resets selected-run state", () => {
      const model = createInitialRunControlModel();
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      const result = updateRunControl(m3, {
        type: "SelectionCleared",
      });

      expect(result.model.selection.selectedRunId).toBeNull();
      expect(result.model.selectedRun.status).toBe("idle");
      expect(result.model.selectedRun.requestSeq).toBeNull();
      expect(result.model.selectedRun.requestedRunId).toBeNull();
      expect(result.model.selectedRun.payload).toBeNull();
      expect(result.model.freshness.hasNewerLatest).toBe(false);
    });
  });

  describe("DebugModeDetected", () => {
    test("23. toggles debug.enabled", () => {
      const model = createInitialRunControlModel();
      const nowMs = 1000;

      const result = updateRunControl(model, {
        type: "DebugModeDetected",
        enabled: true,
      });

      expect(result.model.debug.enabled).toBe(true);
    });
  });

  describe("stale RunLoaded with debug", () => {
    test("24. emits debugLog only when debug.enabled", () => {
      const model = createInitialRunControlModel({ debugEnabled: true });
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      // Stale response
      const result = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 99,
        runId: "run-123",
        payload: makeRunPayload("run-123"),
        receivedAtMs: nowMs + 300,
      });

      expect(
        result.effects.some((e) => e.type === "debugLog")
      ).toBe(true);
    });

    test("24b. does NOT emit debugLog when debug disabled", () => {
      const model = createInitialRunControlModel({ debugEnabled: false });
      const payload = makeRunsListPayload([
        { runId: "run-123", runLabel: "Run 123" },
      ]);
      const nowMs = 1000;

      const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
      const { model: m2 } = updateRunControl(m1, {
        type: "RunsLoaded",
        requestSeq: 1,
        payload,
        receivedAtMs: nowMs + 100,
      });

      const { model: m3 } = updateRunControl(m2, {
        type: "RunSelected",
        runId: "run-123",
        nowMs: nowMs + 200,
      });

      // Stale response
      const result = updateRunControl(m3, {
        type: "RunLoaded",
        requestSeq: 99,
        runId: "run-123",
        payload: makeRunPayload("run-123"),
        receivedAtMs: nowMs + 300,
      });

      expect(result.effects).toEqual([]);
    });
  });
});

describe("selectors", () => {
  test("getSelectedRunId returns selectedRunId", () => {
    const model = createInitialRunControlModel();
    const payload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const nowMs = 1000;

    const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
    const { model: m2 } = updateRunControl(m1, {
      type: "RunsLoaded",
      requestSeq: 1,
      payload,
      receivedAtMs: nowMs + 100,
    });

    expect(getSelectedRunId(m2)).toBe("run-123");
  });

  test("getLatestRunId returns latestRunId", () => {
    const model = createInitialRunControlModel();
    const payload = makeRunsListPayload([
      { runId: "run-latest", runLabel: "Latest" },
      { runId: "run-old", runLabel: "Old" },
    ]);
    const nowMs = 1000;

    const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
    const { model: m2 } = updateRunControl(m1, {
      type: "RunsLoaded",
      requestSeq: 1,
      payload,
      receivedAtMs: nowMs + 100,
    });

    expect(getLatestRunId(m2)).toBe("run-latest");
  });

  test("shouldShowRunLoading returns true when loading", () => {
    const model = createInitialRunControlModel();
    const payload = makeRunsListPayload([
      { runId: "run-123", runLabel: "Run 123" },
    ]);
    const nowMs = 1000;

    const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });
    const { model: m2 } = updateRunControl(m1, {
      type: "RunsLoaded",
      requestSeq: 1,
      payload,
      receivedAtMs: nowMs + 100,
    });

    const { model: m3 } = updateRunControl(m2, {
      type: "RunSelected",
      runId: "run-123",
      nowMs: nowMs + 200,
    });

    expect(shouldShowRunLoading(m3)).toBe(true);
  });

  test("shouldShowLatestJump returns true when hasNewerLatest and selectedRunId differs", () => {
    const model = createInitialRunControlModel();
    const nowMs = 1000;

    const { model: m1 } = updateRunControl(model, { type: "Boot", nowMs });

    // Simulate state with hasNewerLatest
    const stateWithNewerLatest: RunControlModel = {
      ...m1,
      selection: {
        selectedRunId: "run-old",
        latestRunId: "run-new-latest",
        selectedReason: "user",
      },
      freshness: {
        hasNewerLatest: true,
        latestKnownAtMs: nowMs,
      },
    };

    expect(shouldShowLatestJump(stateWithNewerLatest)).toBe(true);
  });

  test("getHeaderRunId prefers selectedRunId over latestRunId", () => {
    const model: RunControlModel = {
      ...createInitialRunControlModel(),
      selection: {
        selectedRunId: "run-selected",
        latestRunId: "run-latest",
        selectedReason: "user",
      },
    };

    expect(getHeaderRunId(model)).toBe("run-selected");
  });

  test("getRunOwnedPanelState returns correct state", () => {
    const idleModel: RunControlModel = {
      ...createInitialRunControlModel(),
      selection: { selectedRunId: null, latestRunId: null, selectedReason: null },
    };
    expect(getRunOwnedPanelState(idleModel)).toBe("no-selection");

    const loadingModel: RunControlModel = {
      ...createInitialRunControlModel(),
      selection: { selectedRunId: "run-123", latestRunId: "run-123", selectedReason: "user" },
      selectedRun: { ...createInitialRunControlModel().selectedRun, status: "loading" },
    };
    expect(getRunOwnedPanelState(loadingModel)).toBe("loading");

    const slowModel: RunControlModel = {
      ...createInitialRunControlModel(),
      selection: { selectedRunId: "run-123", latestRunId: "run-123", selectedReason: "user" },
      selectedRun: { ...createInitialRunControlModel().selectedRun, status: "slow" },
    };
    expect(getRunOwnedPanelState(slowModel)).toBe("slow");

    const failedModel: RunControlModel = {
      ...createInitialRunControlModel(),
      selection: { selectedRunId: "run-123", latestRunId: "run-123", selectedReason: "user" },
      selectedRun: { ...createInitialRunControlModel().selectedRun, status: "failed" },
    };
    expect(getRunOwnedPanelState(failedModel)).toBe("failed");

    const loadedModel: RunControlModel = {
      ...createInitialRunControlModel(),
      selection: { selectedRunId: "run-123", latestRunId: "run-123", selectedReason: "user" },
      selectedRun: { ...createInitialRunControlModel().selectedRun, status: "loaded" },
    };
    expect(getRunOwnedPanelState(loadedModel)).toBe("loaded");
  });
});
