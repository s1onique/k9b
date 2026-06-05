/**
 * batchExecutionEffects.test.ts - Tests for the batch execution effect runner.
 *
 * Tests async behavior including:
 * - API success dispatches success message
 * - API failure dispatches failure message
 * - Refresh happens only after success
 * - Refresh failure does not overwrite execution success
 *
 * @module app/batchExecution/batchExecutionEffects.test
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Cmd, Msg } from "./batchExecutionModel";
import type { BatchExecutionRefreshCallbacks } from "./batchExecutionEffects";
import { runEffect } from "./batchExecutionEffects";

// Mock the API module
vi.mock("../../api", () => ({
  runBatchExecution: vi.fn(),
}));

import { runBatchExecution } from "../../api";

describe("batchExecutionEffects", () => {
  let dispatch: (msg: Msg) => void;
  let callbacks: BatchExecutionRefreshCallbacks;
  let pollMock: () => void;
  let retrySelectedRunMock: () => void;

  beforeEach(() => {
    vi.clearAllMocks();
    dispatch = vi.fn();
    pollMock = vi.fn();
    retrySelectedRunMock = vi.fn();
    callbacks = {
      poll: pollMock,
      retrySelectedRun: retrySelectedRunMock,
    };
  });

  describe("runEffect", () => {
    describe("ExecuteBatch command", () => {
      it("should call runBatchExecution API with correct parameters", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockResolvedValue({
          status: "success",
          summary: "Batch execution completed",
          runId: "run-123",
          dryRun: false,
          totalCandidates: 5,
          eligibleCandidates: 3,
          executedCount: 3,
          skippedAlreadyExecuted: 0,
          skippedIneligible: 0,
          failedCount: 0,
          successCount: 3,
        });

        await runEffect(cmd, dispatch, callbacks, null);

        expect(runBatchExecution).toHaveBeenCalledWith({ runId: "run-123", dryRun: false });
      });

      it("should dispatch BatchExecutionSucceeded on API success", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockResolvedValue({
          status: "success",
          summary: "Batch execution completed",
          runId: "run-123",
          dryRun: false,
          totalCandidates: 5,
          eligibleCandidates: 3,
          executedCount: 3,
          skippedAlreadyExecuted: 0,
          skippedIneligible: 0,
          failedCount: 0,
          successCount: 3,
        });

        await runEffect(cmd, dispatch, callbacks, null);

        expect(dispatch).toHaveBeenCalledWith({ type: "BatchExecutionSucceeded", runId: "run-123" });
      });

      it("should call poll() after successful execution", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockResolvedValue({
          status: "success",
          summary: "Batch execution completed",
          runId: "run-123",
          dryRun: false,
          totalCandidates: 5,
          eligibleCandidates: 3,
          executedCount: 3,
          skippedAlreadyExecuted: 0,
          skippedIneligible: 0,
          failedCount: 0,
          successCount: 3,
        });

        await runEffect(cmd, dispatch, callbacks, null);

        expect(pollMock).toHaveBeenCalledTimes(1);
      });

      it("should call retrySelectedRun() after successful execution when selected run matches", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockResolvedValue({
          status: "success",
          summary: "Batch execution completed",
          runId: "run-123",
          dryRun: false,
          totalCandidates: 5,
          eligibleCandidates: 3,
          executedCount: 3,
          skippedAlreadyExecuted: 0,
          skippedIneligible: 0,
          failedCount: 0,
          successCount: 3,
        });

        await runEffect(cmd, dispatch, callbacks, "run-123");

        expect(retrySelectedRunMock).toHaveBeenCalledTimes(1);
      });

      it("should NOT call retrySelectedRun() after successful execution when selected run does not match", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockResolvedValue({
          status: "success",
          summary: "Batch execution completed",
          runId: "run-123",
          dryRun: false,
          totalCandidates: 5,
          eligibleCandidates: 3,
          executedCount: 3,
          skippedAlreadyExecuted: 0,
          skippedIneligible: 0,
          failedCount: 0,
          successCount: 3,
        });

        await runEffect(cmd, dispatch, callbacks, "run-456");

        expect(retrySelectedRunMock).not.toHaveBeenCalled();
      });

      it("should dispatch BatchExecutionFailed on API failure", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Network error"));

        await runEffect(cmd, dispatch, callbacks, null);

        expect(dispatch).toHaveBeenCalledWith({
          type: "BatchExecutionFailed",
          runId: "run-123",
          error: "Network error",
        });
      });

      it("should NOT call poll() after API failure", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Network error"));

        await runEffect(cmd, dispatch, callbacks, null);

        expect(pollMock).not.toHaveBeenCalled();
      });

      it("should NOT call retrySelectedRun() after API failure", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Network error"));

        await runEffect(cmd, dispatch, callbacks, "run-123");

        expect(retrySelectedRunMock).not.toHaveBeenCalled();
      });

      it("should handle non-Error rejection and use default message", async () => {
        const cmd: Cmd = { type: "ExecuteBatch", runId: "run-123" };
        (runBatchExecution as ReturnType<typeof vi.fn>).mockRejectedValue("string error");

        await runEffect(cmd, dispatch, callbacks, null);

        expect(dispatch).toHaveBeenCalledWith({
          type: "BatchExecutionFailed",
          runId: "run-123",
          error: "Batch execution failed",
        });
      });
    });

    describe("NoOp command", () => {
      it("should not call dispatch for NoOp", async () => {
        const cmd: Cmd = { type: "NoOp" };

        await runEffect(cmd, dispatch, callbacks, null);

        expect(dispatch).not.toHaveBeenCalled();
      });

      it("should not call poll for NoOp", async () => {
        const cmd: Cmd = { type: "NoOp" };

        await runEffect(cmd, dispatch, callbacks, null);

        expect(pollMock).not.toHaveBeenCalled();
      });

      it("should not call retrySelectedRun for NoOp", async () => {
        const cmd: Cmd = { type: "NoOp" };

        await runEffect(cmd, dispatch, callbacks, null);

        expect(retrySelectedRunMock).not.toHaveBeenCalled();
      });
    });
  });
});
