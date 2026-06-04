/**
 * approvalFlowEffects.test.ts - Tests for the effect runner.
 *
 * Tests the async side effects that cannot be in the pure update() function.
 *
 * @module app/approvalFlow/approvalFlowEffects.test
 */
import { describe, it, expect, vi } from "vitest";
import { runEffect } from "./approvalFlowEffects";
import type { Cmd, Msg } from "./approvalFlowModel";

// Mock the API module
vi.mock("../../api", () => ({
  approveNextCheckCandidate: vi.fn(),
}));

import { approveNextCheckCandidate } from "../../api";

describe("approvalFlowEffects", () => {
  describe("runEffect - ApproveCandidate command", () => {
    it("should dispatch ApprovalSucceeded when approval API succeeds", async () => {
      const mockResult = {
        status: "success" as const,
        summary: "Approved",
        artifactPath: "/artifacts/test",
      };
      vi.mocked(approveNextCheckCandidate).mockResolvedValue(mockResult);

      const dispatch = vi.fn();
      const cmd: Cmd = {
        type: "ApproveCandidate",
        candidateKey: "candidate-1",
        request: { candidateId: "1", clusterLabel: "test" },
      };

      await runEffect(cmd, dispatch);

      expect(dispatch).toHaveBeenCalledOnce();
      expect(dispatch).toHaveBeenCalledWith({
        type: "ApprovalSucceeded",
        candidateKey: "candidate-1",
        result: mockResult,
      });
    });

    it("should dispatch ApprovalFailed when approval API rejects", async () => {
      vi.mocked(approveNextCheckCandidate).mockRejectedValue(new Error("Network error"));

      const dispatch = vi.fn();
      const cmd: Cmd = {
        type: "ApproveCandidate",
        candidateKey: "candidate-1",
        request: { candidateId: "1", clusterLabel: "test" },
      };

      await runEffect(cmd, dispatch);

      expect(dispatch).toHaveBeenCalledOnce();
      expect(dispatch).toHaveBeenCalledWith({
        type: "ApprovalFailed",
        candidateKey: "candidate-1",
        summary: "Network error",
      });
    });

    it("should dispatch ApprovalFailed with default message when error has no message", async () => {
      vi.mocked(approveNextCheckCandidate).mockRejectedValue({});

      const dispatch = vi.fn();
      const cmd: Cmd = {
        type: "ApproveCandidate",
        candidateKey: "candidate-1",
        request: { candidateId: "1", clusterLabel: "test" },
      };

      await runEffect(cmd, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: "ApprovalFailed",
        candidateKey: "candidate-1",
        summary: "Approval failed",
      });
    });

    it("should call refresh after successful approval", async () => {
      const mockResult = { status: "success" as const, summary: "Approved" };
      vi.mocked(approveNextCheckCandidate).mockResolvedValue(mockResult);

      const dispatch = vi.fn();
      const refresh = vi.fn().mockResolvedValue(undefined);
      const cmd: Cmd = {
        type: "ApproveCandidate",
        candidateKey: "candidate-1",
        request: { candidateId: "1", clusterLabel: "test" },
      };

      await runEffect(cmd, dispatch, refresh);

      expect(refresh).toHaveBeenCalledOnce();
      expect(dispatch).toHaveBeenCalledWith({
        type: "ApprovalSucceeded",
        candidateKey: "candidate-1",
        result: mockResult,
      });
    });

    it("should NOT call refresh when approval API fails", async () => {
      vi.mocked(approveNextCheckCandidate).mockRejectedValue(new Error("API error"));

      const dispatch = vi.fn();
      const refresh = vi.fn().mockResolvedValue(undefined);
      const cmd: Cmd = {
        type: "ApproveCandidate",
        candidateKey: "candidate-1",
        request: { candidateId: "1", clusterLabel: "test" },
      };

      await runEffect(cmd, dispatch, refresh);

      expect(refresh).not.toHaveBeenCalled();
      expect(dispatch).toHaveBeenCalledWith({
        type: "ApprovalFailed",
        candidateKey: "candidate-1",
        summary: "API error",
      });
    });

    it("should dispatch ApprovalSucceeded even when refresh fails after approval success", async () => {
      const mockResult = { status: "success" as const, summary: "Approved" };
      vi.mocked(approveNextCheckCandidate).mockResolvedValue(mockResult);

      const dispatch = vi.fn();
      const refresh = vi.fn().mockRejectedValue(new Error("Refresh failed"));
      const cmd: Cmd = {
        type: "ApproveCandidate",
        candidateKey: "candidate-1",
        request: { candidateId: "1", clusterLabel: "test" },
      };

      await runEffect(cmd, dispatch, refresh);

      // Approval succeeded and was dispatched
      expect(dispatch).toHaveBeenCalledWith({
        type: "ApprovalSucceeded",
        candidateKey: "candidate-1",
        result: mockResult,
      });
      // Only one dispatch (no ApprovalFailed)
      expect(dispatch).toHaveBeenCalledTimes(1);
      // Refresh was called and failed silently
      expect(refresh).toHaveBeenCalledOnce();
    });

    it("should not crash when refresh is not provided", async () => {
      const mockResult = { status: "success" as const, summary: "Approved" };
      vi.mocked(approveNextCheckCandidate).mockResolvedValue(mockResult);

      const dispatch = vi.fn();
      const cmd: Cmd = {
        type: "ApproveCandidate",
        candidateKey: "candidate-1",
        request: { candidateId: "1", clusterLabel: "test" },
      };

      // Should not throw
      await runEffect(cmd, dispatch, undefined);

      expect(dispatch).toHaveBeenCalledWith({
        type: "ApprovalSucceeded",
        candidateKey: "candidate-1",
        result: mockResult,
      });
    });
  });

  describe("runEffect - NoOp command", () => {
    it("should not dispatch anything for NoOp", async () => {
      const dispatch = vi.fn();
      const cmd: Cmd = { type: "NoOp" };

      await runEffect(cmd, dispatch);

      expect(dispatch).not.toHaveBeenCalled();
    });

    it("should not crash for NoOp even with refresh", async () => {
      const dispatch = vi.fn();
      const refresh = vi.fn();
      const cmd: Cmd = { type: "NoOp" };

      await runEffect(cmd, dispatch, refresh);

      expect(dispatch).not.toHaveBeenCalled();
      expect(refresh).not.toHaveBeenCalled();
    });
  });
});