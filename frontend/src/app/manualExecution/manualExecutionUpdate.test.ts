/**
 * manualExecutionUpdate.test.ts - Unit tests for the pure update function.
 *
 * Tests all state transitions in the manual execution Elm-ish model
 * without any React or async dependencies.
 *
 * @module app/manualExecution/manualExecutionUpdate.test
 */
import { describe, it, expect } from "vitest";
import { update, createInitialModel, isExecuting, getResult, isAnyExecuting } from "./manualExecutionUpdate";
import type { ManualExecutionModel, Msg } from "./manualExecutionModel";
import { initialModel } from "./manualExecutionModel";

// Helper to create a minimal model for testing
function createModel(overrides: Partial<ManualExecutionModel> = {}): ManualExecutionModel {
  return { ...initialModel, ...overrides };
}

// Helper to create a mock execution request
function mockRequest() {
  return {
    candidateId: "candidate-1",
    candidateIndex: 0,
    clusterLabel: "test-cluster",
    planArtifactPath: null,
  };
}

// Helper to create a mock success result
function mockSuccessResult(candidateKey: string) {
  return {
    status: "success",
    summary: `Execution completed for ${candidateKey}`,
    artifactPath: `/artifacts/${candidateKey}`,
    durationMs: 1234,
    command: ["kubectl", "get", "pods"],
    targetCluster: "test-cluster",
    planCandidateIndex: 0,
    rawOutput: "output",
  };
}

// Helper to create a mock error result
function mockErrorResult(candidateKey: string, message = "Execution failed") {
  return {
    status: "error" as const,
    summary: message,
    blockingReason: null,
  };
}

describe("manualExecutionUpdate", () => {
  describe("initial state", () => {
    it("should have correct initial values", () => {
      const model = createInitialModel();
      expect(model.executionResults).toEqual({});
      expect(model.executingCandidate).toBeNull();
      expect(model.lastSucceededKey).toBeNull();
    });

    it("isExecuting should return false for any key in initial state", () => {
      const model = createInitialModel();
      expect(isExecuting(model, "key-1")).toBe(false);
      expect(isExecuting(model, "key-2")).toBe(false);
    });

    it("isAnyExecuting should return false in initial state", () => {
      const model = createInitialModel();
      expect(isAnyExecuting(model)).toBe(false);
    });

    it("getResult should return undefined for any key in initial state", () => {
      const model = createInitialModel();
      expect(getResult(model, "key-1")).toBeUndefined();
      expect(getResult(model, "key-2")).toBeUndefined();
    });
  });

  describe("ExecuteRequested message", () => {
    it("should set executingCandidate and emit ExecuteCandidate command", () => {
      const model = createInitialModel();
      const request = mockRequest();
      const msg: Msg = { type: "ExecuteRequested", candidateKey: "candidate-1", request };
      const result = update(model, msg);

      expect(result.model.executingCandidate).toBe("candidate-1");
      expect(result.model.executionResults).toEqual({});
      expect(result.model.lastSucceededKey).toBeNull();
      expect(result.cmd).toEqual({ type: "ExecuteCandidate", candidateKey: "candidate-1", request });
    });

    it("should allow multiple execute requests (overwrites previous)", () => {
      const model = createModel({ executingCandidate: "candidate-1" });
      const request = mockRequest();
      const msg: Msg = { type: "ExecuteRequested", candidateKey: "candidate-2", request };
      const result = update(model, msg);

      expect(result.model.executingCandidate).toBe("candidate-2");
      expect(result.cmd.type).toBe("ExecuteCandidate");
      expect(result.cmd.candidateKey).toBe("candidate-2");
    });

    it("should preserve existing execution results when new execution starts", () => {
      const model = createModel({
        executionResults: { "candidate-1": mockSuccessResult("candidate-1") },
      });
      const request = mockRequest();
      const msg: Msg = { type: "ExecuteRequested", candidateKey: "candidate-2", request };
      const result = update(model, msg);

      expect(result.model.executionResults).toHaveProperty("candidate-1");
      expect(result.model.executingCandidate).toBe("candidate-2");
    });

    it("isExecuting should return true for executing candidate", () => {
      const model = createModel({ executingCandidate: "candidate-1" });
      expect(isExecuting(model, "candidate-1")).toBe(true);
      expect(isExecuting(model, "candidate-2")).toBe(false);
    });

    it("isAnyExecuting should return true when candidate is executing", () => {
      const model = createModel({ executingCandidate: "candidate-1" });
      expect(isAnyExecuting(model)).toBe(true);
    });
  });

  describe("ExecutionSucceeded message", () => {
    it("should store success result, clear executing state, and set lastSucceededKey", () => {
      const model = createModel({ executingCandidate: "candidate-1" });
      const successResult = mockSuccessResult("candidate-1");
      const msg: Msg = { type: "ExecutionSucceeded", candidateKey: "candidate-1", result: successResult };
      const result = update(model, msg);

      expect(result.model.executingCandidate).toBeNull();
      expect(result.model.lastSucceededKey).toBe("candidate-1");
      expect(result.model.executionResults["candidate-1"]).toEqual(successResult);
    });

    it("should preserve other execution results", () => {
      const model = createModel({
        executingCandidate: "candidate-2",
        executionResults: { "candidate-1": mockSuccessResult("candidate-1") },
      });
      const successResult = mockSuccessResult("candidate-2");
      const msg: Msg = { type: "ExecutionSucceeded", candidateKey: "candidate-2", result: successResult };
      const result = update(model, msg);

      expect(result.model.executionResults).toHaveProperty("candidate-1");
      expect(result.model.executionResults).toHaveProperty("candidate-2");
      expect(Object.keys(result.model.executionResults)).toHaveLength(2);
    });

    it("should emit NoOp command on success (highlight handled separately)", () => {
      const model = createModel({ executingCandidate: "candidate-1" });
      const successResult = mockSuccessResult("candidate-1");
      const msg: Msg = { type: "ExecutionSucceeded", candidateKey: "candidate-1", result: successResult };
      const result = update(model, msg);

      expect(result.cmd).toEqual({ type: "NoOp" });
    });

    it("getResult should return the stored success result", () => {
      const model = createModel({
        executionResults: { "candidate-1": mockSuccessResult("candidate-1") },
      });
      expect(getResult(model, "candidate-1")?.status).toBe("success");
      expect(getResult(model, "candidate-2")).toBeUndefined();
    });
  });

  describe("ExecutionFailed message", () => {
    it("should store error result and clear executing state", () => {
      const model = createModel({ executingCandidate: "candidate-1" });
      const errorResult = mockErrorResult("candidate-1", "Network error");
      const msg: Msg = { type: "ExecutionFailed", candidateKey: "candidate-1", error: errorResult };
      const result = update(model, msg);

      expect(result.model.executingCandidate).toBeNull();
      expect(result.model.lastSucceededKey).toBeNull();
      expect(result.model.executionResults["candidate-1"]).toEqual(errorResult);
    });

    it("should preserve other execution results on failure", () => {
      const model = createModel({
        executingCandidate: "candidate-2",
        executionResults: { "candidate-1": mockSuccessResult("candidate-1") },
      });
      const errorResult = mockErrorResult("candidate-2");
      const msg: Msg = { type: "ExecutionFailed", candidateKey: "candidate-2", error: errorResult };
      const result = update(model, msg);

      expect(result.model.executionResults).toHaveProperty("candidate-1");
      expect(result.model.executionResults).toHaveProperty("candidate-2");
      expect(result.model.executionResults["candidate-2"].status).toBe("error");
    });

    it("should handle error with blocking reason", () => {
      const model = createModel({ executingCandidate: "candidate-1" });
      const errorResult = {
        status: "error" as const,
        summary: "Permission denied",
        blockingReason: "Insufficient permissions",
      };
      const msg: Msg = { type: "ExecutionFailed", candidateKey: "candidate-1", error: errorResult };
      const result = update(model, msg);

      expect(result.model.executionResults["candidate-1"]).toEqual(errorResult);
    });

    it("getResult should return the stored error result", () => {
      const model = createModel({
        executionResults: { "candidate-1": mockErrorResult("candidate-1") },
      });
      expect(getResult(model, "candidate-1")?.status).toBe("error");
    });
  });

  describe("ClearResults message", () => {
    it("should clear all execution results", () => {
      const model = createModel({
        executionResults: {
          "candidate-1": mockSuccessResult("candidate-1"),
          "candidate-2": mockErrorResult("candidate-2"),
        },
      });
      const msg: Msg = { type: "ClearResults" };
      const result = update(model, msg);

      expect(result.model.executionResults).toEqual({});
    });

    it("should preserve executing candidate when clearing results", () => {
      const model = createModel({
        executingCandidate: "candidate-1",
        executionResults: { "candidate-1": mockSuccessResult("candidate-1") },
      });
      const msg: Msg = { type: "ClearResults" };
      const result = update(model, msg);

      expect(result.model.executingCandidate).toBe("candidate-1");
      expect(result.model.executionResults).toEqual({});
    });

    it("should preserve lastSucceededKey when clearing results", () => {
      const model = createModel({
        lastSucceededKey: "candidate-1",
        executionResults: { "candidate-1": mockSuccessResult("candidate-1") },
      });
      const msg: Msg = { type: "ClearResults" };
      const result = update(model, msg);

      expect(result.model.lastSucceededKey).toBe("candidate-1");
    });
  });

  describe("ConsumeLastSucceededKey message", () => {
    it("should return highlight command with the last succeeded key", () => {
      const model = createModel({ lastSucceededKey: "candidate-1" });
      const msg: Msg = { type: "ConsumeLastSucceededKey" };
      const result = update(model, msg);

      expect(result.model.lastSucceededKey).toBeNull();
      expect(result.cmd).toEqual({ type: "HighlightCandidate", key: "candidate-1" });
    });

    it("should return NoOp when lastSucceededKey is null", () => {
      const model = createModel({ lastSucceededKey: null });
      const msg: Msg = { type: "ConsumeLastSucceededKey" };
      const result = update(model, msg);

      expect(result.model.lastSucceededKey).toBeNull();
      expect(result.cmd).toEqual({ type: "NoOp" });
    });

    it("should preserve execution results when consuming key", () => {
      const model = createModel({
        lastSucceededKey: "candidate-1",
        executionResults: { "candidate-1": mockSuccessResult("candidate-1") },
      });
      const msg: Msg = { type: "ConsumeLastSucceededKey" };
      const result = update(model, msg);

      expect(result.model.executionResults).toHaveProperty("candidate-1");
    });
  });

  describe("update function purity", () => {
    it("should not mutate the original model", () => {
      const model = createModel({ executingCandidate: "candidate-1" });
      const originalModel = { ...model };
      const request = mockRequest();
      const msg: Msg = { type: "ExecuteRequested", candidateKey: "candidate-1", request };
      update(model, msg);

      expect(model).toEqual(originalModel);
    });

    it("should always return a new model object", () => {
      const model = createModel();
      const request = mockRequest();
      const msg: Msg = { type: "ExecuteRequested", candidateKey: "candidate-1", request };
      const result = update(model, msg);

      expect(result.model).not.toBe(model);
    });

    it("should always return a cmd property", () => {
      const model = createModel();
      const messages: Msg[] = [
        { type: "ExecuteRequested", candidateKey: "candidate-1", request: mockRequest() },
        { type: "ExecutionSucceeded", candidateKey: "candidate-1", result: mockSuccessResult("candidate-1") },
        { type: "ExecutionFailed", candidateKey: "candidate-1", error: mockErrorResult("candidate-1") },
        { type: "ClearResults" },
        { type: "ConsumeLastSucceededKey" },
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
      it("should return true only for the executing candidate", () => {
        const model = createModel({ executingCandidate: "candidate-2" });
        expect(isExecuting(model, "candidate-2")).toBe(true);
        expect(isExecuting(model, "candidate-1")).toBe(false);
        expect(isExecuting(model, "candidate-3")).toBe(false);
      });

      it("should return false when no candidate is executing", () => {
        const model = createModel({ executingCandidate: null });
        expect(isExecuting(model, "candidate-1")).toBe(false);
      });
    });

    describe("getResult", () => {
      it("should return undefined for unknown keys", () => {
        const model = createModel({
          executionResults: { "candidate-1": mockSuccessResult("candidate-1") },
        });
        expect(getResult(model, "unknown-key")).toBeUndefined();
      });

      it("should return the correct result for known keys", () => {
        const successResult = mockSuccessResult("candidate-1");
        const model = createModel({
          executionResults: { "candidate-1": successResult },
        });
        expect(getResult(model, "candidate-1")).toEqual(successResult);
      });
    });

    describe("isAnyExecuting", () => {
      it("should return true when executingCandidate is set", () => {
        const model = createModel({ executingCandidate: "candidate-1" });
        expect(isAnyExecuting(model)).toBe(true);
      });

      it("should return false when executingCandidate is null", () => {
        const model = createModel({ executingCandidate: null });
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
        { type: "ExecuteRequested", candidateKey: "candidate-1", request: mockRequest() },
        { type: "ExecutionSucceeded", candidateKey: "candidate-1", result: mockSuccessResult("candidate-1") },
        { type: "ExecutionFailed", candidateKey: "candidate-1", error: mockErrorResult("candidate-1") },
        { type: "ClearResults" },
        { type: "ConsumeLastSucceededKey" },
      ];

      for (const msg of messages) {
        expect(() => update(model, msg)).not.toThrow();
      }
    });
  });
});