/**
 * RuntimeStatusSummary.test.tsx - Tests for runtime status components.
 *
 * Tests cover:
 * - Normal state with data
 * - Zero warning/error state
 * - Unavailable logs state
 * - Unavailable PVC state
 * - High usage PVC state
 * - Loading state
 * - Error state
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { RuntimeStatusSummary } from "../RuntimeStatusSummary";
import type { RuntimeStatusPayload } from "../runtimeStatusTypes";

// Helper to create sample payload
const createSamplePayload = (overrides: Partial<RuntimeStatusPayload> = {}): RuntimeStatusPayload => ({
  log_windows: {
    backend: {
      "5m": { warning: 2, error: 1 },
      "10m": { warning: 4, error: 1 },
      "15m": { warning: 7, error: 2 },
    },
    scheduler: {
      "5m": { warning: 0, error: 0 },
      "10m": { warning: 1, error: 0 },
      "15m": { warning: 1, error: 0 },
    },
  },
  backend_pvc: {
    name: "backend-data",
    used_bytes: 3221225472,
    free_bytes: 7516192768,
    capacity_bytes: 10737418240,
    used_percent: 30,
  },
  ...overrides,
});

describe("RuntimeStatusSummary", () => {
  describe("Loading state", () => {
    it("shows loading state when isLoading is true", () => {
      render(
        <RuntimeStatusSummary
          runtimeStatus={null}
          isLoading={true}
          isError={false}
        />
      );

      expect(screen.getByTestId("runtime-status-summary")).toHaveClass(
        "runtime-status-summary--loading"
      );
      expect(screen.getByText("Loading runtime status...")).toBeInTheDocument();
    });
  });

  describe("Error state", () => {
    it("shows unavailable state when isError is true", () => {
      render(
        <RuntimeStatusSummary
          runtimeStatus={null}
          isLoading={false}
          isError={true}
        />
      );

      expect(screen.getByTestId("runtime-status-summary")).toHaveClass(
        "runtime-status-summary--error"
      );
      // Should show unavailable for both pods
      expect(screen.getByText("backend")).toBeInTheDocument();
      expect(screen.getByText("scheduler")).toBeInTheDocument();
      expect(screen.getAllByText("unavailable")).toHaveLength(2);
    });
  });

  describe("Normal state", () => {
    it("renders backend log counts with warnings and errors", () => {
      const payload = createSamplePayload();
      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      const backendLogCounts = screen.getByTestId("log-counts-backend");
      expect(backendLogCounts).toBeInTheDocument();
      // Errors take precedence over warnings (test data has { warning: 2, error: 1 })
      expect(backendLogCounts).toHaveClass("log-counts--error");
      expect(screen.getByText("1 error / 2 warnings")).toBeInTheDocument();
    });

    it("renders scheduler log counts with zero counts", () => {
      const payload = createSamplePayload();
      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      const schedulerLogCounts = screen.getByTestId("log-counts-scheduler");
      expect(schedulerLogCounts).toBeInTheDocument();
      expect(schedulerLogCounts).toHaveClass("log-counts--ok");
      expect(schedulerLogCounts).toHaveTextContent("0 error / 0 warning");
    });

    it("renders PVC usage bar with correct percentage", () => {
      const payload = createSamplePayload();
      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      const pvcBar = screen.getByTestId("pvc-usage-bar");
      expect(pvcBar).toBeInTheDocument();
      expect(pvcBar).toHaveAttribute("aria-valuenow", "30");
      expect(screen.getByText("backend-data")).toBeInTheDocument();
      expect(screen.getByText("30%")).toBeInTheDocument();
    });
  });

  describe("Unavailable logs", () => {
    it("renders unavailable for backend when all window values are null", () => {
      const payload = createSamplePayload({
        log_windows: {
          backend: {
            "5m": { warning: null, error: null },
            "10m": { warning: null, error: null },
            "15m": { warning: null, error: null },
          },
          scheduler: {
            "5m": { warning: 0, error: 0 },
            "10m": { warning: 0, error: 0 },
            "15m": { warning: 0, error: 0 },
          },
        },
      });

      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      // Backend should be unavailable
      const backendLogCounts = screen.getByTestId("log-counts-backend-unavailable");
      expect(backendLogCounts).toBeInTheDocument();
      expect(backendLogCounts).toHaveClass("log-counts--unavailable");
    });
  });

  describe("Unavailable PVC", () => {
    it("renders unavailable PVC when all values are null", () => {
      const payload = createSamplePayload({
        backend_pvc: {
          name: "backend-data",
          used_bytes: null,
          free_bytes: null,
          capacity_bytes: null,
          used_percent: null,
        },
      });

      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      const pvcUnavailable = screen.getByTestId("pvc-usage-bar-unavailable");
      expect(pvcUnavailable).toBeInTheDocument();
      expect(pvcUnavailable).toHaveClass("pvc-usage-bar--unavailable");
      expect(screen.getByText("PVC usage unavailable")).toBeInTheDocument();
    });

    it("renders unavailable when backend_pvc is null", () => {
      const payload = createSamplePayload({
        backend_pvc: null,
      });

      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      const pvcUnavailable = screen.getByTestId("pvc-usage-bar-unavailable");
      expect(pvcUnavailable).toBeInTheDocument();
    });
  });

  describe("High usage PVC", () => {
    it("shows high usage warning when usage > 80%", () => {
      const payload = createSamplePayload({
        backend_pvc: {
          name: "backend-data",
          used_bytes: 9663676416, // 90% used
          free_bytes: 1073741824,
          capacity_bytes: 10737418240,
          used_percent: 90,
        },
      });

      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      const pvcBar = screen.getByTestId("pvc-usage-bar");
      expect(pvcBar).toHaveClass("pvc-usage-bar--high");
      expect(screen.getByText("High storage usage")).toBeInTheDocument();
    });

    it("does not show high usage warning when usage <= 80%", () => {
      const payload = createSamplePayload({
        backend_pvc: {
          name: "backend-data",
          used_bytes: 6442450944, // 60% used
          free_bytes: 4294967296,
          capacity_bytes: 10737418240,
          used_percent: 60,
        },
      });

      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      const pvcBar = screen.getByTestId("pvc-usage-bar");
      expect(pvcBar).not.toHaveClass("pvc-usage-bar--high");
      expect(screen.queryByText("High storage usage")).not.toBeInTheDocument();
    });
  });

  describe("Accessible labels", () => {
    it("PVC usage bar has accessible aria-label", () => {
      const payload = createSamplePayload();
      render(
        <RuntimeStatusSummary
          runtimeStatus={payload}
          isLoading={false}
          isError={false}
        />
      );

      const pvcBar = screen.getByTestId("pvc-usage-bar");
      expect(pvcBar).toHaveAttribute(
        "aria-label",
        "30% used, 70% free"
      );
      expect(pvcBar).toHaveAttribute("role", "meter");
      expect(pvcBar).toHaveAttribute("aria-valuemin", "0");
      expect(pvcBar).toHaveAttribute("aria-valuemax", "100");
    });
  });
});
