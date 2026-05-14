/**
 * Tests for execution-state-chip rendering in QueuePanel.
 *
 * Verifies that executed queue items render with correct semantic chip classes
 * and visible text labels (color is not the only signal).
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { QueuePanel } from "../components/QueuePanel";
import {
  createFetchMock,
  createStorageMock,
  makeRunWithOverrides,
  sampleClusterDetail,
  sampleFleet,
  sampleNotifications,
  sampleProposals,
  sampleRun,
  sampleRunsList,
} from "./fixtures";

const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/runs": sampleRunsList,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
};

const getQueuePanelWithRunData = async () => {
  const { waitFor, within } = await import("@testing-library/react");
  await waitFor(() => {
    expect(
      document.querySelector(".next-check-queue-panel")
    ).toBeInTheDocument();
  });
  const panel = document.querySelector(".next-check-queue-panel");
  return within(panel!);
};

describe("Execution State Chips", () => {
  beforeEach(() => {
    const storageMock = createStorageMock();
    vi.stubGlobal("localStorage", storageMock);
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("executed-success renders success chip class", async () => {
    const run = makeRunWithOverrides({
      nextCheckQueue: [
        {
          ...sampleRun.nextCheckQueue![0],
          executionState: "executed-success",
          itemState: "executed",
        },
      ],
    });

    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": run }));

    render(<QueuePanel {...createMockQueuePanelProps(run)} />);

    const panel = await getQueuePanelWithRunData();
    const chip = panel.getByText("executed / success");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveClass("execution-state-chip");
    expect(chip).toHaveClass("execution-state-chip--executed-success");
  });

  test("executed-failed renders failed chip class", async () => {
    const run = makeRunWithOverrides({
      nextCheckQueue: [
        {
          ...sampleRun.nextCheckQueue![0],
          executionState: "executed-failed",
          itemState: "executed",
        },
      ],
    });

    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": run }));

    render(<QueuePanel {...createMockQueuePanelProps(run)} />);

    const panel = await getQueuePanelWithRunData();
    const chip = panel.getByText("executed / failed");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveClass("execution-state-chip");
    expect(chip).toHaveClass("execution-state-chip--executed-failed");
  });

  test("timed-out renders timed-out chip class", async () => {
    const run = makeRunWithOverrides({
      nextCheckQueue: [
        {
          ...sampleRun.nextCheckQueue![0],
          executionState: "timed-out",
          itemState: "executed",
        },
      ],
    });

    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": run }));

    render(<QueuePanel {...createMockQueuePanelProps(run)} />);

    const panel = await getQueuePanelWithRunData();
    const chip = panel.getByText("executed / timed-out");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveClass("execution-state-chip");
    expect(chip).toHaveClass("execution-state-chip--timed-out");
  });

  test("completed renders completed chip class", async () => {
    const run = makeRunWithOverrides({
      nextCheckQueue: [
        {
          ...sampleRun.nextCheckQueue![0],
          executionState: "completed",
          itemState: "executed",
        },
      ],
    });

    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": run }));

    render(<QueuePanel {...createMockQueuePanelProps(run)} />);

    const panel = await getQueuePanelWithRunData();
    const chip = panel.getByText("executed / completed");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveClass("execution-state-chip");
    expect(chip).toHaveClass("execution-state-chip--completed");
  });

  test("unexecuted items show no execution chip (approval badge shown instead)", async () => {
    const run = makeRunWithOverrides({
      nextCheckQueue: [
        {
          ...sampleRun.nextCheckQueue![0],
          executionState: "unexecuted",
          approvalState: "pending",
        },
      ],
    });

    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": run }));

    render(<QueuePanel {...createMockQueuePanelProps(run)} />);

    const panel = await getQueuePanelWithRunData();
    // Should NOT have execution state chip for unexecuted items
    expect(panel.queryByText("executed / success")).not.toBeInTheDocument();
    expect(panel.queryByText("executed / failed")).not.toBeInTheDocument();
    expect(panel.queryByText("executed / timed-out")).not.toBeInTheDocument();
    expect(panel.queryByText("executed / completed")).not.toBeInTheDocument();
    // Should show approval badge instead
    expect(panel.getByText("Pending")).toBeInTheDocument();
  });

  test("pending approval badge has action-state-badge class", async () => {
    const run = makeRunWithOverrides({
      nextCheckQueue: [
        {
          ...sampleRun.nextCheckQueue![0],
          executionState: "unexecuted",
          approvalState: "pending",
        },
      ],
    });

    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": run }));

    render(<QueuePanel {...createMockQueuePanelProps(run)} />);

    const panel = await getQueuePanelWithRunData();
    const badge = panel.getByText("Pending");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("action-state-badge");
    // Badge should have action-state-badge class (geometry shared with execution-state-chip)
    expect(badge.className).toContain("action-state-badge");
  });

  test("both action-state-badge and execution-state-chip classes exist in CSS", async () => {
    // Verify the CSS file contains both shared geometry selectors
    const cssContent = await import("fs").then((fs) =>
      fs.readFileSync(
        require("path").resolve(__dirname, "../styles/components/badges-pills.css"),
        "utf8"
      )
    );
    expect(cssContent).toContain(".action-state-badge,");
    expect(cssContent).toContain(".execution-state-chip");
    expect(cssContent).toContain("min-height: 1.45rem");
    expect(cssContent).toContain("padding: 0.2rem 0.65rem");
  });

  test("text label is always present (color is not the only signal)", async () => {
    const run = makeRunWithOverrides({
      nextCheckQueue: [
        {
          ...sampleRun.nextCheckQueue![0],
          executionState: "executed-success",
          itemState: "executed",
        },
      ],
    });

    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": run }));

    render(<QueuePanel {...createMockQueuePanelProps(run)} />);

    const panel = await getQueuePanelWithRunData();
    const chip = panel.getByText("executed / success");
    // Text content is the label - verify it exists as text node, not just aria
    expect(chip.textContent).toBe("executed / success");
  });
});

// Helper to create minimal props for QueuePanel rendering
import type { NextCheckQueueItem, NextCheckQueueStatus } from "../types";
import type { RunPayload } from "../types";

function createMockQueuePanelProps(run: RunPayload) {
  const queue = run.nextCheckQueue ?? [];
  return {
    queueClusterFilter: "all",
    queueStatusFilter: "all" as NextCheckQueueStatus | "all",
    queueCommandFamilyFilter: "all",
    queuePriorityFilter: "all",
    queueWorkstreamFilter: "all",
    queueSearch: "",
    queueSortOption: "default",
    queueFocusMode: "none",
    setQueueClusterFilter: () => {},
    setQueueStatusFilter: () => {},
    setQueueCommandFamilyFilter: () => {},
    setQueuePriorityFilter: () => {},
    setQueueWorkstreamFilter: () => {},
    setQueueSearch: () => {},
    setQueueSortOption: () => {},
    setQueueFocusMode: () => {},
    queueClusterOptions: ["all"],
    queueCommandFamilyOptions: ["all"],
    queuePriorityOptions: ["all"],
    queueWorkstreamOptions: ["all"],
    runQueue: queue,
    sortedQueue: queue,
    queueGroups: [
      { status: "approved-ready" as NextCheckQueueStatus, label: "Approved & ready", items: queue },
    ],
    queueExplanation: null,
    expandedQueueItems: {},
    toggleQueueDetails: () => {},
    queueHighlightKey: null,
    executionResults: {},
    approvalResults: {},
    executingCandidate: null,
    approvingCandidate: null,
    onToggleQueueFocusPreset: () => {},
    onResetQueueFilters: () => {},
    onResetQueueView: () => {},
    onBackToQueue: () => {},
    onManualExecution: () => {},
    onApproveCandidate: () => {},
    onQueueClusterJump: () => {},
    onQueueExecutionJump: () => {},
    buildCandidateKey: (_: NextCheckQueueItem, index: number) => `candidate-${index}`,
    findExecutionHistoryEntry: () => null,
    isManualExecutionAllowed: () => false,
    getNotRunnableExplanation: () => null,
    getAlertmanagerProvenanceSubtext: () => "",
    formatAlertmanagerProvenance: () => "",
    getAlertmanagerPromotionSubtext: () => null,
    formatAlertmanagerPromotion: () => "",
    getFeedbackAdaptationProvenanceSubtext: () => "",
    formatFeedbackAdaptationProvenance: () => "",
    onRefresh: () => {},
  };
}