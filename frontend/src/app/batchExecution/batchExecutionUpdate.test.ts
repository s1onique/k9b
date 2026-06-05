/**
 * batchExecutionUpdate.test.ts - Unit tests for the pure update function.
 *
 * Tests all state transitions in the batch execution Elm-ish model
 * without any React or async dependencies.
 *
 * @module app/batchExecution/batchExecutionUpdate.test
 */
import { describe, it, expect } from "vitest";
import { update, createInitialModel, isExecuting, getError, isAnyExecuting } from "./batchExecutionUpdate";
import type { BatchExecutionModel, Msg } from "./batchExecutionModel";
import { initialModel } from "./batchExecutionModel";

// Helper to create a minimal model for testing
function createModel(overrides: Partial<BatchExecutionModel> = {}): BatchExecutionModel {
  return { ...initialModel, ...overrides };
}

describe("batchExecutionUpdate", () => {
  describe("initial state", () => {
    it("should have correct initial values", () => {
      const model = createInitialModel();
      expect(model.executingBatchRunId).toBeNull();
      expect(model.batchExecutionError).toEqual({});
    });

    it("isExecuting should return false for any runId in initial state", () => {
      const model = createInitialModel();
      expect(isExecuting(model, "run-1")).toBe(false);
      expect(isExecuting(model, "run-2")).toBe(false);
    });

    it("isAnyExecuting should return false in initial state", () => {
      const model = createInitialModel();
      expect(isAnyExecuting(model)).toBe(false);
    });

    it("getError should return undefined for any runId in initial state", () => {
      const model = createInitialModel();
      expect(getError(model, "run-1")).toBeUndefined();
      expect(getError(model, "run-2")).toBeUndefined();
    });
  });

  describe("BatchExecutionRequested message", () => {
    it("should set executingBatchRunId and emit ExecuteBatch command", () => {
      const model = createInitialModel();
      const msg: Msg = { type: "BatchExecutionRequested", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBe("run-1");
      expect(result.model.batchExecutionError).toEqual({});
      expect(result.cmd).toEqual({ type: "ExecuteBatch", runId: "run-1" });
    });

    it("should clear any previous error for the run being executed", () => {
      const model = createModel({ batchExecutionError: { "run-1": "Previous error" } });
      const msg: Msg = { type: "BatchExecutionRequested", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBe("run-1");
      expect(result.model.batchExecutionError).toEqual({});
    });

    it("should preserve errors for other runs when starting execution", () => {
      const model = createModel({ batchExecutionError: { "run-2": "Error for run-2" } });
      const msg: Msg = { type: "BatchExecutionRequested", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBe("run-1");
      expect(result.model.batchExecutionError).toEqual({ "run-2": "Error for run-2" });
    });

    it("should allow multiple execution requests (overwrites previous)", () => {
      const model = createModel({ executingBatchRunId: "run-1" });
      const msg: Msg = { type: "BatchExecutionRequested", runId: "run-2" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBe("run-2");
      expect(result.cmd.type).toBe("ExecuteBatch");
      expect(result.cmd.runId).toBe("run-2");
    });

    it("isExecuting should return true for executing run", () => {
      const model = createModel({ executingBatchRunId: "run-1" });
      expect(isExecuting(model, "run-1")).toBe(true);
      expect(isExecuting(model, "run-2")).toBe(false);
    });

    it("isAnyExecuting should return true when a run is executing", () => {
      const model = createModel({ executingBatchRunId: "run-1" });
      expect(isAnyExecuting(model)).toBe(true);
    });
  });

  describe("BatchExecutionSucceeded message", () => {
    it("should clear executing state", () => {
      const model = createModel({ executingBatchRunId: "run-1" });
      const msg: Msg = { type: "BatchExecutionSucceeded", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBeNull();
    });

    it("should preserve existing errors", () => {
      const model = createModel({
        executingBatchRunId: "run-1",
        batchExecutionError: { "run-2": "Error for run-2" },
      });
      const msg: Msg = { type: "BatchExecutionSucceeded", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBeNull();
      expect(result.model.batchExecutionError).toEqual({ "run-2": "Error for run-2" });
    });

    it("should emit NoOp command on success", () => {
      const model = createModel({ executingBatchRunId: "run-1" });
      const msg: Msg = { type: "BatchExecutionSucceeded", runId: "run-1" };
      const result = update(model, msg);

      expect(result.cmd).toEqual({ type: "NoOp" });
    });
  });

  describe("BatchExecutionFailed message", () => {
    it("should store error and clear executing state", () => {
      const model = createModel({ executingBatchRunId: "run-1" });
      const msg: Msg = { type: "BatchExecutionFailed", runId: "run-1", error: "Network error" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBeNull();
      expect(result.model.batchExecutionError["run-1"]).toBe("Network error");
    });

    it("should preserve errors for other runs", () => {
      const model = createModel({
        executingBatchRunId: "run-2",
        batchExecutionError: { "run-1": "Previous error" },
      });
      const msg: Msg = { type: "BatchExecutionFailed", runId: "run-2", error: "New error" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBeNull();
      expect(result.model.batchExecutionError).toHaveProperty("run-1");
      expect(result.model.batchExecutionError["run-2"]).toBe("New error");
    });

    it("should emit NoOp command on failure", () => {
      const model = createModel({ executingBatchRunId: "run-1" });
      const msg: Msg = { type: "BatchExecutionFailed", runId: "run-1", error: "Error" };
      const result = update(model, msg);

      expect(result.cmd).toEqual({ type: "NoOp" });
    });

    it("getError should return the stored error", () => {
      const model = createModel({
        batchExecutionError: { "run-1": "Network error" },
      });
      expect(getError(model, "run-1")).toBe("Network error");
      expect(getError(model, "run-2")).toBeUndefined();
    });
  });

  describe("ClearBatchExecutionError message", () => {
    it("should clear error for the specified run", () => {
      const model = createModel({
        batchExecutionError: { "run-1": "Error 1", "run-2": "Error 2" },
      });
      const msg: Msg = { type: "ClearBatchExecutionError", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model.batchExecutionError).toEqual({ "run-2": "Error 2" });
    });

    it("should preserve executing state when clearing error", () => {
      const model = createModel({
        executingBatchRunId: "run-1",
        batchExecutionError: { "run-1": "Error" },
      });
      const msg: Msg = { type: "ClearBatchExecutionError", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model.executingBatchRunId).toBe("run-1");
      expect(result.model.batchExecutionError).toEqual({});
    });

    it("should handle clearing non-existent error gracefully", () => {
      const model = createModel({ batchExecutionError: {} });
      const msg: Msg = { type: "ClearBatchExecutionError", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model.batchExecutionError).toEqual({});
    });

    it("should emit NoOp command", () => {
      const model = createModel({
        batchExecutionError: { "run-1": "Error" },
      });
      const msg: Msg = { type: "ClearBatchExecutionError", runId: "run-1" };
      const result = update(model, msg);

      expect(result.cmd).toEqual({ type: "NoOp" });
    });
  });

  describe("update function purity", () => {
    it("should not mutate the original model", () => {
      const model = createModel({ executingBatchRunId: "run-1" });
      const originalModel = { ...model };
      const msg: Msg = { type: "BatchExecutionRequested", runId: "run-2" };
      update(model, msg);

      expect(model).toEqual(originalModel);
    });

    it("should always return a new model object", () => {
      const model = createModel();
      const msg: Msg = { type: "BatchExecutionRequested", runId: "run-1" };
      const result = update(model, msg);

      expect(result.model).not.toBe(model);
    });

    it("should always return a cmd property", () => {
      const model = createModel();
      const messages: Msg[] = [
        { type: "BatchExecutionRequested", runId: "run-1" },
        { type: "BatchExecutionSucceeded", runId: "run-1" },
        { type: "BatchExecutionFailed", runId: "run-1", error: "Error" },
        { type: "ClearBatchExecutionError", runId: "run-1" },
      ];

      for (const msg of messages) {
        const result = update(model, msg);
        expect(result).toHaveProperty("cmd");
        expect(result.cmd).toHaveProperty("type");
      }
    });
  });

  describe("helper functions", () => {
    describe("isExecuting", () => {
      it("should return true only for the executing run", () => {
        const model = createModel({ executingBatchRunId: "run-2" });
        expect(isExecuting(model, "run-2")).toBe(true);
        expect(isExecuting(model, "run-1")).toBe(false);
        expect(isExecuting(model, "run-3")).toBe(false);
      });

      it("should return false when no run is executing", () => {
        const model = createModel({ executingBatchRunId: null });
        expect(isExecuting(model, "run-1")).toBe(false);
      });
    });

    describe("getError", () => {
      it("should return undefined for unknown run IDs", () => {
        const model = createModel({
          batchExecutionError: { "run-1": "Error 1" },
        });
        expect(getError(model, "unknown-run")).toBeUndefined();
      });

      it("should return the correct error for known run IDs", () => {
        const model = createModel({
          batchExecutionError: { "run-1": "Error 1", "run-2": "Error 2" },
        });
        expect(getError(model, "run-1")).toBe("Error 1");
        expect(getError(model, "run-2")).toBe("Error 2");
      });
    });

    describe("isAnyExecuting", () => {
      it("should return true when executingBatchRunId is set", () => {
        const model = createModel({ executingBatchRunId: "run-1" });
        expect(isAnyExecuting(model)).toBe(true);
      });

      it("should return false when executingBatchRunId is null", () => {
        const model = createModel({ executingBatchRunId: null });
        expect(isAnyExecuting(model)).toBe(false);
      });
    });
  });

  describe("exhaustiveness check", () => {
    // TypeScript would catch unhandled cases at compile time
    // This test just verifies all known message types are handled
    it("should handle all known message types without throwing", () => {
      const model = createModel();
      const messages: Msg[] = [
        { type: "BatchExecutionRequested", runId: "run-1" },
        { type: "BatchExecutionSucceeded", runId: "run-1" },
        { type: "BatchExecutionFailed", runId: "run-1", error: "Error" },
        { type: "ClearBatchExecutionError", runId: "run-1" },
      ];

      for (const msg of messages) {
        expect(() => update(model, msg)).not.toThrow();
      }
    });
  });
});
