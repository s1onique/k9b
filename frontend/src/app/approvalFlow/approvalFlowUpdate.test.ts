/**
 * approvalFlowUpdate.test.ts - Unit tests for the pure update function.
 *
 * Tests all state transitions in the approval flow Elm-ish model
 * without any React or async dependencies.
 *
 * @module app/approvalFlow/approvalFlowUpdate.test
 */
import { describe, it, expect } from "vitest";
import { update, createInitialModel, isApproving, getResult, isAnyApproving } from "./approvalFlowUpdate";
import type { ApprovalFlowModel, Msg } from "./approvalFlowModel";
import { initialModel } from "./approvalFlowModel";

// Helper to create a minimal model for testing
function createModel(overrides: Partial<ApprovalFlowModel> = {}): ApprovalFlowModel {
  return { ...initialModel, ...overrides };
}

// Helper to create a mock approval request
function mockRequest() {
  return {
    candidateId: "candidate-1",
    candidateIndex: 0,
    clusterLabel: "test-cluster",
  };
}

// Helper to create a mock success response
function mockSuccessResponse(candidateKey: string) {
  return {
    status: "success" as const,
    summary: `Approval completed for ${candidateKey}`,
    artifactPath: `/artifacts/${candidateKey}`,
    approvalTimestamp: "2024-01-01T00:00:00Z",
  };
}

// Helper to create a mock error response
function mockErrorResponse(candidateKey: string, summary = "Approval failed") {
  return {
    status: "error" as const,
    summary,
  };
}

describe("approvalFlowUpdate", () => {
  describe("initial state", () => {
    it("should have correct initial values", () => {
      const model = createInitialModel();
      expect(model.approvalResults).toEqual({});
      expect(model.approvingCandidate).toBeNull();
    });

    it("isApproving should return false for any key in initial state", () => {
      const model = createInitialModel();
      expect(isApproving(model, "key-1")).toBe(false);
      expect(isApproving(model, "key-2")).toBe(false);
    });

    it("isAnyApproving should return false in initial state", () => {
      const model = createInitialModel();
      expect(isAnyApproving(model)).toBe(false);
    });

    it("getResult should return undefined for any key in initial state", () => {
      const model = createInitialModel();
      expect(getResult(model, "key-1")).toBeUndefined();
      expect(getResult(model, "key-2")).toBeUndefined();
    });
  });

  describe("ApprovalRequested message", () => {
    it("should set approvingCandidate and emit ApproveCandidate command", () => {
      const model = createInitialModel();
      const request = mockRequest();
      const msg: Msg = { type: "ApprovalRequested", candidateKey: "candidate-1", request };
      const result = update(model, msg);

      expect(result.model.approvingCandidate).toBe("candidate-1");
      expect(result.model.approvalResults).toEqual({});
      expect(result.cmd).toEqual({ type: "ApproveCandidate", candidateKey: "candidate-1", request });
    });

    it("should allow multiple approval requests (overwrites previous)", () => {
      const model = createModel({ approvingCandidate: "candidate-1" });
      const request = mockRequest();
      const msg: Msg = { type: "ApprovalRequested", candidateKey: "candidate-2", request };
      const result = update(model, msg);

      expect(result.model.approvingCandidate).toBe("candidate-2");
      expect(result.cmd.type).toBe("ApproveCandidate");
      expect(result.cmd.candidateKey).toBe("candidate-2");
    });

    it("should preserve existing approval results when new approval starts", () => {
      const model = createModel({
        approvalResults: { "candidate-1": { status: "success", summary: "Approved" } },
      });
      const request = mockRequest();
      const msg: Msg = { type: "ApprovalRequested", candidateKey: "candidate-2", request };
      const result = update(model, msg);

      expect(result.model.approvalResults).toHaveProperty("candidate-1");
      expect(result.model.approvingCandidate).toBe("candidate-2");
    });

    it("isApproving should return true for approving candidate", () => {
      const model = createModel({ approvingCandidate: "candidate-1" });
      expect(isApproving(model, "candidate-1")).toBe(true);
      expect(isApproving(model, "candidate-2")).toBe(false);
    });

    it("isAnyApproving should return true when candidate is approving", () => {
      const model = createModel({ approvingCandidate: "candidate-1" });
      expect(isAnyApproving(model)).toBe(true);
    });
  });

  describe("ApprovalSucceeded message", () => {
    it("should store success result, clear approving state", () => {
      const model = createModel({ approvingCandidate: "candidate-1" });
      const response = mockSuccessResponse("candidate-1");
      const msg: Msg = { type: "ApprovalSucceeded", candidateKey: "candidate-1", result: response };
      const result = update(model, msg);

      expect(result.model.approvingCandidate).toBeNull();
      expect(result.model.approvalResults["candidate-1"]).toEqual({
        status: "success",
        summary: "Approval completed for candidate-1",
        artifactPath: "/artifacts/candidate-1",
        approvalTimestamp: "2024-01-01T00:00:00Z",
      });
    });

    it("should preserve other approval results", () => {
      const model = createModel({
        approvingCandidate: "candidate-2",
        approvalResults: { "candidate-1": { status: "success", summary: "Approved" } },
      });
      const response = mockSuccessResponse("candidate-2");
      const msg: Msg = { type: "ApprovalSucceeded", candidateKey: "candidate-2", result: response };
      const result = update(model, msg);

      expect(result.model.approvalResults).toHaveProperty("candidate-1");
      expect(result.model.approvalResults).toHaveProperty("candidate-2");
      expect(Object.keys(result.model.approvalResults)).toHaveLength(2);
    });

    it("should emit NoOp command on success", () => {
      const model = createModel({ approvingCandidate: "candidate-1" });
      const response = mockSuccessResponse("candidate-1");
      const msg: Msg = { type: "ApprovalSucceeded", candidateKey: "candidate-1", result: response };
      const result = update(model, msg);

      expect(result.cmd).toEqual({ type: "NoOp" });
    });

    it("should handle success response with minimal data", () => {
      const model = createModel({ approvingCandidate: "candidate-1" });
      const response = { status: "success" as const };
      const msg: Msg = { type: "ApprovalSucceeded", candidateKey: "candidate-1", result: response };
      const result = update(model, msg);

      expect(result.model.approvalResults["candidate-1"].status).toBe("success");
      expect(result.model.approvalResults["candidate-1"].summary).toBe("Candidate approved");
    });

    it("getResult should return the stored success result", () => {
      const model = createModel({
        approvalResults: { "candidate-1": { status: "success", summary: "Approved" } },
      });
      expect(getResult(model, "candidate-1")?.status).toBe("success");
      expect(getResult(model, "candidate-2")).toBeUndefined();
    });
  });

  describe("ApprovalFailed message", () => {
    it("should store error result and clear approving state", () => {
      const model = createModel({ approvingCandidate: "candidate-1" });
      const msg: Msg = { type: "ApprovalFailed", candidateKey: "candidate-1", summary: "Network error" };
      const result = update(model, msg);

      expect(result.model.approvingCandidate).toBeNull();
      expect(result.model.approvalResults["candidate-1"]).toEqual({
        status: "error",
        summary: "Network error",
      });
    });

    it("should preserve other approval results on failure", () => {
      const model = createModel({
        approvingCandidate: "candidate-2",
        approvalResults: { "candidate-1": { status: "success", summary: "Approved" } },
      });
      const msg: Msg = { type: "ApprovalFailed", candidateKey: "candidate-2", summary: "Permission denied" };
      const result = update(model, msg);

      expect(result.model.approvalResults).toHaveProperty("candidate-1");
      expect(result.model.approvalResults).toHaveProperty("candidate-2");
      expect(result.model.approvalResults["candidate-2"].status).toBe("error");
    });

    it("getResult should return the stored error result", () => {
      const model = createModel({
        approvalResults: { "candidate-1": { status: "error", summary: "Failed" } },
      });
      expect(getResult(model, "candidate-1")?.status).toBe("error");
    });
  });

  describe("ClearResults message", () => {
    it("should clear all approval results", () => {
      const model = createModel({
        approvalResults: {
          "candidate-1": { status: "success", summary: "Approved" },
          "candidate-2": { status: "error", summary: "Failed" },
        },
      });
      const msg: Msg = { type: "ClearResults" };
      const result = update(model, msg);

      expect(result.model.approvalResults).toEqual({});
    });

    it("should preserve approving candidate when clearing results", () => {
      const model = createModel({
        approvingCandidate: "candidate-1",
        approvalResults: { "candidate-1": { status: "success", summary: "Approved" } },
      });
      const msg: Msg = { type: "ClearResults" };
      const result = update(model, msg);

      expect(result.model.approvingCandidate).toBe("candidate-1");
      expect(result.model.approvalResults).toEqual({});
    });
  });

  describe("update function purity", () => {
    it("should not mutate the original model", () => {
      const model = createModel({ approvingCandidate: "candidate-1" });
      const originalModel = { ...model };
      const request = mockRequest();
      const msg: Msg = { type: "ApprovalRequested", candidateKey: "candidate-1", request };
      update(model, msg);

      expect(model).toEqual(originalModel);
    });

    it("should always return a new model object", () => {
      const model = createModel();
      const request = mockRequest();
      const msg: Msg = { type: "ApprovalRequested", candidateKey: "candidate-1", request };
      const result = update(model, msg);

      expect(result.model).not.toBe(model);
    });

    it("should always return a cmd property", () => {
      const model = createModel();
      const messages: Msg[] = [
        { type: "ApprovalRequested", candidateKey: "candidate-1", request: mockRequest() },
        { type: "ApprovalSucceeded", candidateKey: "candidate-1", result: mockSuccessResponse("candidate-1") },
        { type: "ApprovalFailed", candidateKey: "candidate-1", summary: "Error" },
        { type: "ClearResults" },
      ];

      for (const msg of messages) {
        const result = update(model, msg);
        expect(result).toHaveProperty("cmd");
        expect(result.cmd).toHaveProperty("type");
      }
    });
  });

  describe("helper functions", () => {
    describe("isApproving", () => {
      it("should return true only for the approving candidate", () => {
        const model = createModel({ approvingCandidate: "candidate-2" });
        expect(isApproving(model, "candidate-2")).toBe(true);
        expect(isApproving(model, "candidate-1")).toBe(false);
        expect(isApproving(model, "candidate-3")).toBe(false);
      });

      it("should return false when no candidate is approving", () => {
        const model = createModel({ approvingCandidate: null });
        expect(isApproving(model, "candidate-1")).toBe(false);
      });
    });

    describe("getResult", () => {
      it("should return undefined for unknown keys", () => {
        const model = createModel({
          approvalResults: { "candidate-1": { status: "success", summary: "Approved" } },
        });
        expect(getResult(model, "unknown-key")).toBeUndefined();
      });

      it("should return the correct result for known keys", () => {
        const result = { status: "success" as const, summary: "Approved" };
        const model = createModel({
          approvalResults: { "candidate-1": result },
        });
        expect(getResult(model, "candidate-1")).toEqual(result);
      });
    });

    describe("isAnyApproving", () => {
      it("should return true when approvingCandidate is set", () => {
        const model = createModel({ approvingCandidate: "candidate-1" });
        expect(isAnyApproving(model)).toBe(true);
      });

      it("should return false when approvingCandidate is null", () => {
        const model = createModel({ approvingCandidate: null });
        expect(isAnyApproving(model)).toBe(false);
      });
    });
  });

  describe("exhaustiveness check", () => {
    // TypeScript would catch unhandled cases at compile time
    // This test just verifies all known message types are handled
    it("should handle all known message types without throwing", () => {
      const model = createModel();
      const messages: Msg[] = [
        { type: "ApprovalRequested", candidateKey: "candidate-1", request: mockRequest() },
        { type: "ApprovalSucceeded", candidateKey: "candidate-1", result: mockSuccessResponse("candidate-1") },
        { type: "ApprovalFailed", candidateKey: "candidate-1", summary: "Error" },
        { type: "ClearResults" },
      ];

      for (const msg of messages) {
        expect(() => update(model, msg)).not.toThrow();
      }
    });
  });
});