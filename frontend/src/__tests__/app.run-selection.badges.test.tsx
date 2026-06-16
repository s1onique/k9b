/**
 * Recent runs review status badges tests.
 *
 * Tests the rendering of review status badges (Needs attention,
 * Partially executed, Fully reviewed) in the recent runs panel.
 *
 * Part of app.run-selection.test.tsx split for LLM-friendly file sizes.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
} from "./app.test-fixtures";

let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
let storageMock: ReturnType<typeof createStorageMock>;

beforeEach(() => {
  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Recent runs review status badges", () => {
  test("recent-runs fully-reviewed status renders with green badge style", async () => {
    const fullyReviewedRuns = {
      runs: [
        {
          runId: "run-200",
          runLabel: "2026-04-07-1400",
          timestamp: "2026-04-07T14:00:00Z",
          clusterCount: 2,
          triaged: true,
          executionCount: 4,
          reviewedCount: 4,
          reviewStatus: "fully-reviewed",
          batchExecutable: false,
          batchEligibleCount: 0,
        },
        {
          runId: "run-201",
          runLabel: "2026-04-07-1500",
          timestamp: "2026-04-07T15:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 6,
          reviewedCount: 6,
          reviewStatus: "fully-reviewed",
          batchExecutable: false,
          batchEligibleCount: 0,
        },
      ],
      totalCount: 2,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/runs": fullyReviewedRuns,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(2);
    });

    const fullyReviewedPills = document.querySelectorAll(".status-pill-fully-executed");
    expect(fullyReviewedPills.length).toBe(2);

    fullyReviewedPills.forEach((pill) => {
      expect(pill).toHaveClass("status-pill");
      expect(pill).toHaveClass("status-pill-fully-executed");
      expect(pill).not.toHaveClass("status-pill-needs-attention");
    });
  });

  test("recent-runs unreviewed status renders with non-green badge style", async () => {
    const unreviewedRuns = {
      runs: [
        {
          runId: "run-300",
          runLabel: "2026-04-07-1400",
          timestamp: "2026-04-07T14:00:00Z",
          clusterCount: 2,
          triaged: false,
          executionCount: 3,
          reviewedCount: 0,
          reviewStatus: "unreviewed",
          reviewDownloadPath: "health/diagnostic-packs/run-300/next_check_usefulness_review.json",
          batchExecutable: false,
          batchEligibleCount: 0,
        },
      ],
      totalCount: 1,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/runs": unreviewedRuns,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(1);
    });

    const unreviewedPills = document.querySelectorAll(".status-pill-needs-attention");
    expect(unreviewedPills.length).toBe(1);

    const pill = unreviewedPills[0];
    expect(pill).toHaveClass("status-pill");
    expect(pill).toHaveClass("status-pill-needs-attention");
    expect(pill).not.toHaveClass("status-pill-fully-executed");
  });
});
