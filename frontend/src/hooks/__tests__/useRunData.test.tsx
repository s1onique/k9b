/**
 * Regression tests for useRunData hook.
 *
 * These tests verify that the hook correctly fetches run data when
 * selectedRunId changes. This was the root cause of execution-history-filter
 * test timeouts - the refresh() function existed but was never called
 * when selectedRunId changed.
 *
 * Key behaviors tested:
 * 1. selectedRunId is set -> fetchRun is called for that run
 * 2. selectedRunId changes -> a new fetch starts
 * 3. requestedRunId reflects the currently requested run (monotonic sequence guard support)
 */
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRunData } from "../useRunData";
import { fetchRun } from "../../api";
import { makeRunWithOverrides } from "../../__tests__/fixtures";

// Mock at module level - hoisted to top
vi.mock("../../api", () => ({
  fetchRun: vi.fn(),
}));

describe("useRunData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("setInterval", vi.fn(() => 123));
    vi.stubGlobal("clearInterval", vi.fn());
    // Mock localStorage for auto-refresh interval reading
    const storageMock = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    };
    vi.stubGlobal("localStorage", storageMock);
    // Mock document visibility
    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      writable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("selectedRunId triggers fetch", () => {
    it("calls fetchRun with selectedRunId when run ID is provided", async () => {
      vi.mocked(fetchRun).mockResolvedValue(
        makeRunWithOverrides({ runId: "run-123" })
      );

      renderHook(() => useRunData({ selectedRunId: "run-123" }));

      // Wait for the effect to trigger and verify correct run ID was requested
      await waitFor(
        () => {
          expect(fetchRun).toHaveBeenCalledWith("run-123");
        },
        { timeout: 2000 }
      );
    });

    it("calls fetchRun with undefined when selectedRunId is null (fetch latest)", async () => {
      vi.mocked(fetchRun).mockResolvedValue(
        makeRunWithOverrides({ runId: "latest-run" })
      );

      renderHook(() => useRunData({ selectedRunId: null }));

      // Wait for the effect to trigger and verify undefined was passed (meaning "fetch latest")
      await waitFor(
        () => {
          expect(fetchRun).toHaveBeenCalledWith(undefined);
        },
        { timeout: 2000 }
      );
    });
  });

  describe("selectedRunId changes trigger new fetch", () => {
    it("verifies new fetch is called when selectedRunId changes from run-1 to run-2", async () => {
      vi.mocked(fetchRun).mockResolvedValue(
        makeRunWithOverrides({ runId: "run-1" })
      );

      const { rerender } = renderHook(
        ({ selectedRunId }: { selectedRunId: string | null }) =>
          useRunData({ selectedRunId }),
        { initialProps: { selectedRunId: "run-1" } }
      );

      // Wait for first fetch with run-1
      await waitFor(
        () => {
          expect(fetchRun).toHaveBeenCalledWith("run-1");
        },
        { timeout: 2000 }
      );

      // Change to run-2 - update mock to return run-2 data
      vi.mocked(fetchRun).mockResolvedValue(
        makeRunWithOverrides({ runId: "run-2" })
      );

      // Rerender with new selectedRunId
      rerender({ selectedRunId: "run-2" });

      // Wait for second fetch with run-2
      await waitFor(
        () => {
          expect(fetchRun).toHaveBeenCalledWith("run-2");
        },
        { timeout: 2000 }
      );

      // Verify both fetches were made with correct IDs
      expect(fetchRun).toHaveBeenCalledWith("run-1");
      expect(fetchRun).toHaveBeenCalledWith("run-2");
    });

    it("captures call count baseline and verifies new fetch occurred", async () => {
      vi.mocked(fetchRun).mockResolvedValue(
        makeRunWithOverrides({ runId: "run-1" })
      );

      const { rerender } = renderHook(
        ({ selectedRunId }: { selectedRunId: string | null }) =>
          useRunData({ selectedRunId }),
        { initialProps: { selectedRunId: "run-1" } }
      );

      // Wait for first fetch
      await waitFor(
        () => {
          expect(fetchRun).toHaveBeenCalledWith("run-1");
        },
        { timeout: 2000 }
      );

      // Capture baseline count before rerender
      const baselineCount = vi.mocked(fetchRun).mock.calls.length;

      // Update mock for second run
      vi.mocked(fetchRun).mockResolvedValue(
        makeRunWithOverrides({ runId: "run-2" })
      );

      // Rerender with new selectedRunId
      rerender({ selectedRunId: "run-2" });

      // Wait for additional fetch call (not exact count, just verify increase)
      await waitFor(
        () => {
          expect(vi.mocked(fetchRun).mock.calls.length).toBeGreaterThan(
            baselineCount
          );
        },
        { timeout: 2000 }
      );

      // Verify the new call was with run-2
      expect(fetchRun).toHaveBeenCalledWith("run-2");
    });
  });

  describe("stale-response monotonic sequence guard support", () => {
    /**
     * Verifies that requestedRunId correctly tracks the current fetch request.
     * This supports the monotonic sequence guard pattern where we need to know
     * which run was requested when a response arrives.
     */
    it("verifies requestedRunId matches what was requested after rerender", async () => {
      vi.mocked(fetchRun).mockResolvedValue(
        makeRunWithOverrides({ runId: "run-1" })
      );

      const { rerender, result } = renderHook(
        ({ selectedRunId }: { selectedRunId: string | null }) =>
          useRunData({ selectedRunId }),
        { initialProps: { selectedRunId: "run-1" } }
      );

      // Wait for first fetch
      await waitFor(
        () => {
          expect(fetchRun).toHaveBeenCalledWith("run-1");
        },
        { timeout: 2000 }
      );

      // Verify requestedRunId matches
      expect(result.current.requestedRunId).toBe("run-1");

      // Change to run-2
      vi.mocked(fetchRun).mockResolvedValue(
        makeRunWithOverrides({ runId: "run-2" })
      );
      rerender({ selectedRunId: "run-2" });

      // Wait for second fetch
      await waitFor(
        () => {
          expect(fetchRun).toHaveBeenCalledWith("run-2");
        },
        { timeout: 2000 }
      );

      // Verify requestedRunId was updated to run-2
      expect(result.current.requestedRunId).toBe("run-2");
    });
  });
});
