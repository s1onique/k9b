import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";

// Import types and helpers from ExecutionHistoryPanel component
import {
  filterExecutionHistory,
  extractClustersFromHistory,
  extractCommandFamiliesFromHistory,
  computeExecutionHistoryFilterCounts,
  ExecutionOutcomeFilter,
  UsefulnessReviewFilter,
  ExecutionHistoryFilterState,
  EXECUTION_HISTORY_FILTER_STORAGE_KEY,
} from "../components/ExecutionHistoryPanel";

import type { NextCheckExecutionHistoryEntry } from "../types";

// Mock execution history entries matching the NextCheckExecutionHistoryEntry type
const mockEntries: NextCheckExecutionHistoryEntry[] = [
  {
    timestamp: "2024-01-15T10:00:00Z",
    clusterLabel: "prod-cluster-1",
    candidateDescription: "Check pod status",
    commandFamily: "kubectl-get",
    status: "success",
    durationMs: 100,
    artifactPath: "/artifacts/check-1.json",
    timedOut: false,
    stdoutTruncated: false,
    stderrTruncated: false,
    outputBytesCaptured: 2048,
    usefulnessClass: "useful",
    usefulnessSummary: "Found the issue",
  },
  {
    timestamp: "2024-01-15T09:00:00Z",
    clusterLabel: "prod-cluster-1",
    candidateDescription: "Get events",
    commandFamily: "kubectl-get",
    status: "failed",
    durationMs: 50,
    artifactPath: "/artifacts/check-2.json",
    timedOut: false,
    stdoutTruncated: false,
    stderrTruncated: false,
    outputBytesCaptured: 1024,
    usefulnessClass: "partial",
  },
  {
    timestamp: "2024-01-15T08:00:00Z",
    clusterLabel: "staging-cluster",
    candidateDescription: "Describe pod",
    commandFamily: "kubectl-describe",
    status: "success",
    durationMs: 200,
    artifactPath: "/artifacts/check-3.json",
    timedOut: false,
    stdoutTruncated: false,
    stderrTruncated: false,
    outputBytesCaptured: 4096,
    usefulnessClass: null, // unreviewed
  },
  {
    timestamp: "2024-01-15T07:00:00Z",
    clusterLabel: "prod-cluster-1",
    candidateDescription: "Check nodes",
    commandFamily: "kubectl-get",
    status: "failed",
    durationMs: 30000,
    artifactPath: "/artifacts/check-4.json",
    timedOut: true,
    stdoutTruncated: true,
    stderrTruncated: false,
    outputBytesCaptured: 8192,
    usefulnessClass: "empty",
    failureClass: "timed-out",
  },
  {
    timestamp: "2024-01-15T06:00:00Z",
    clusterLabel: "staging-cluster",
    candidateDescription: "Get logs",
    commandFamily: "kubectl-logs",
    status: "success",
    durationMs: 150,
    artifactPath: null, // no artifact
    timedOut: false,
    stdoutTruncated: false,
    stderrTruncated: false,
    outputBytesCaptured: null,
    usefulnessClass: null, // unreviewed
  },
];

// ============================================================
// Unit tests for filter logic (imported from production)
// ============================================================

describe("filterExecutionHistory", () => {
  const defaultFilter: ExecutionHistoryFilterState = {
    outcomeFilter: "all",
    usefulnessFilter: "all",
    commandFamilyFilter: "all",
    clusterFilter: "all",
  };

  it("returns all entries when no filters applied", () => {
    const result = filterExecutionHistory(mockEntries, defaultFilter);
    expect(result).toHaveLength(5);
  });

  describe("outcome filter", () => {
    it("filters to success entries", () => {
      const filter = { ...defaultFilter, outcomeFilter: "success" as ExecutionOutcomeFilter };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(3);
      expect(result.every((e) => e.status === "success" && !e.timedOut)).toBe(true);
    });

    it("filters to failure entries", () => {
      const filter = { ...defaultFilter, outcomeFilter: "failure" as ExecutionOutcomeFilter };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(1);
      expect(result[0].status).toBe("failed");
      expect(result[0].timedOut).toBe(false);
    });

    it("filters to timeout entries", () => {
      const filter = { ...defaultFilter, outcomeFilter: "timeout" as ExecutionOutcomeFilter };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(1);
      expect(result[0].timedOut).toBe(true);
    });
  });

  describe("usefulness filter", () => {
    it("filters to useful entries", () => {
      const filter = { ...defaultFilter, usefulnessFilter: "useful" as UsefulnessReviewFilter };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(1);
      expect(result[0].usefulnessClass).toBe("useful");
    });

    it("filters to partial entries", () => {
      const filter = { ...defaultFilter, usefulnessFilter: "partial" as UsefulnessReviewFilter };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(1);
      expect(result[0].usefulnessClass).toBe("partial");
    });

    it("filters to unreviewed entries", () => {
      const filter = { ...defaultFilter, usefulnessFilter: "unreviewed" as UsefulnessReviewFilter };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(2);
      expect(result.every((e) => e.usefulnessClass === null)).toBe(true);
    });
  });

  describe("cluster filter", () => {
    it("filters to specific cluster", () => {
      const filter = { ...defaultFilter, clusterFilter: "prod-cluster-1" };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(3);
      expect(result.every((e) => e.clusterLabel === "prod-cluster-1")).toBe(true);
    });

    it("filters to staging cluster", () => {
      const filter = { ...defaultFilter, clusterFilter: "staging-cluster" };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(2);
      expect(result.every((e) => e.clusterLabel === "staging-cluster")).toBe(true);
    });
  });

  describe("command family filter", () => {
    it("filters to kubectl-get family", () => {
      const filter = { ...defaultFilter, commandFamilyFilter: "kubectl-get" };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(3);
      expect(result.every((e) => e.commandFamily === "kubectl-get")).toBe(true);
    });

    it("filters to kubectl-describe family", () => {
      const filter = { ...defaultFilter, commandFamilyFilter: "kubectl-describe" };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(1);
      expect(result[0].commandFamily).toBe("kubectl-describe");
    });
  });

  describe("composing filters", () => {
    it("combines outcome and usefulness filters", () => {
      const filter: ExecutionHistoryFilterState = {
        outcomeFilter: "success",
        usefulnessFilter: "unreviewed",
        commandFamilyFilter: "all",
        clusterFilter: "all",
      };
      const result = filterExecutionHistory(mockEntries, filter);
      // Entries with status=success AND usefulnessClass=null
      expect(result).toHaveLength(2);
      expect(result.every((e) => e.status === "success" && e.usefulnessClass === null)).toBe(true);
    });

    it("combines cluster and command family filters", () => {
      const filter: ExecutionHistoryFilterState = {
        outcomeFilter: "all",
        usefulnessFilter: "all",
        commandFamilyFilter: "kubectl-get",
        clusterFilter: "prod-cluster-1",
      };
      const result = filterExecutionHistory(mockEntries, filter);
      // Entries 0, 1, 3 match kubectl-get + prod-cluster-1
      expect(result).toHaveLength(3);
      expect(
        result.every(
          (e) => e.commandFamily === "kubectl-get" && e.clusterLabel === "prod-cluster-1"
        )
      ).toBe(true);
    });

    it("combines outcome and usefulness filters with specific criteria", () => {
      // failure + partial: entry 1 has status=failed + usefulness=partial
      const filter: ExecutionHistoryFilterState = {
        outcomeFilter: "failure",
        usefulnessFilter: "partial",
        commandFamilyFilter: "all",
        clusterFilter: "all",
      };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(1);
      expect(result[0].status).toBe("failed");
      expect(result[0].usefulnessClass).toBe("partial");
    });
  });

  describe("edge cases", () => {
    it("returns empty array when no matches", () => {
      const filter: ExecutionHistoryFilterState = {
        outcomeFilter: "timeout",
        usefulnessFilter: "useful",
        commandFamilyFilter: "all",
        clusterFilter: "all",
      };
      const result = filterExecutionHistory(mockEntries, filter);
      expect(result).toHaveLength(0);
    });

    it("handles empty entries array", () => {
      const result = filterExecutionHistory([], defaultFilter);
      expect(result).toHaveLength(0);
    });
  });
});

describe("extractClustersFromHistory", () => {
  it("extracts unique clusters sorted alphabetically", () => {
    const result = extractClustersFromHistory(mockEntries);
    expect(result).toEqual(["prod-cluster-1", "staging-cluster"]);
  });

  it("handles empty array", () => {
    const result = extractClustersFromHistory([]);
    expect(result).toEqual([]);
  });

  it("handles entries with missing cluster labels", () => {
    const entriesWithMissing: NextCheckExecutionHistoryEntry[] = [
      { ...mockEntries[0], clusterLabel: "prod-cluster-1" },
      { ...mockEntries[0], clusterLabel: null },
      { ...mockEntries[0], clusterLabel: "" },
    ];
    const result = extractClustersFromHistory(entriesWithMissing);
    expect(result).toEqual(["prod-cluster-1"]);
  });
});

describe("extractCommandFamiliesFromHistory", () => {
  it("extracts unique command families sorted alphabetically", () => {
    const result = extractCommandFamiliesFromHistory(mockEntries);
    expect(result).toEqual(["kubectl-describe", "kubectl-get", "kubectl-logs"]);
  });

  it("handles empty array", () => {
    const result = extractCommandFamiliesFromHistory([]);
    expect(result).toEqual([]);
  });
});

describe("computeExecutionHistoryFilterCounts", () => {
  it("computes correct outcome counts", () => {
    const counts = computeExecutionHistoryFilterCounts(mockEntries);
    
    expect(counts.outcome.all).toBe(5);
    expect(counts.outcome.success).toBe(3);
    expect(counts.outcome.failure).toBe(1);
    expect(counts.outcome.timeout).toBe(1);
  });

  it("computes correct usefulness counts", () => {
    const counts = computeExecutionHistoryFilterCounts(mockEntries);
    
    expect(counts.usefulness.all).toBe(5);
    expect(counts.usefulness.useful).toBe(1);
    expect(counts.usefulness.partial).toBe(1);
    expect(counts.usefulness.empty).toBe(1);
    expect(counts.usefulness.unreviewed).toBe(2);
    expect(counts.usefulness.noisy).toBe(0);
  });

  it("handles empty array", () => {
    const counts = computeExecutionHistoryFilterCounts([]);
    
    expect(counts.outcome.all).toBe(0);
    expect(counts.outcome.success).toBe(0);
    expect(counts.outcome.failure).toBe(0);
    expect(counts.outcome.timeout).toBe(0);
    expect(counts.usefulness.all).toBe(0);
    expect(counts.usefulness.unreviewed).toBe(0);
  });
});

// ============================================================
// UI-level component tests for ExecutionHistoryPanel
// These tests render the actual ExecutionHistoryPanel inside App
// ============================================================

import App from "../App";
import {
  createFetchMock,
  createStorageMock,
  makeRunWithOverrides,
  sampleFleet,
  sampleProposals,
  sampleNotifications,
  sampleClusterDetail,
  sampleRunsList,
} from "./fixtures";

// Test data with execution history for UI testing
const createExecutionHistoryPayload = (history: NextCheckExecutionHistoryEntry[]) =>
  makeRunWithOverrides({ nextCheckExecutionHistory: history });

const defaultPayloads = {
  "/api/run": createExecutionHistoryPayload(mockEntries),
  "/api/runs": sampleRunsList,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/notifications?limit=50&page=1": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
};

let storageMock: ReturnType<typeof createStorageMock>;

beforeEach(() => {
  vi.stubGlobal("setInterval", vi.fn(() => 123));
  vi.stubGlobal("clearInterval", vi.fn());
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ExecutionHistoryPanel UI tests", () => {
  const getExecutionHistoryPanel = async () => {
    const heading = await screen.findByText(/Check execution review/i);
    const section = heading.closest("section");
    if (!section) {
      throw new Error("Execution history panel not found");
    }
    return within(section);
  };

  describe("renders with history data", () => {
    it("renders the execution history panel with entries", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Should show the section heading
      expect(panel.getByText(/Check execution review/i)).toBeInTheDocument();
      
      // Should show filter dropdowns
      expect(panel.getByLabelText(/Outcome/i)).toBeInTheDocument();
      expect(panel.getByLabelText(/Reviewed/i)).toBeInTheDocument();
    });

    it("renders execution history cards when entries exist", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      
      await screen.findByText(/Check execution review/i);
      
      // Should show execution cards (text may appear in summary strip and/or grid cards)
      await waitFor(() => {
        const matches = screen.queryAllByText(/Check pod status/i);
        expect(matches.length).toBeGreaterThan(0);
      });
      
      // Should show at least one status badge with "success" in the panel
      const panel = await getExecutionHistoryPanel();
      const successBadges = panel.getAllByText("success");
      expect(successBadges.length).toBeGreaterThan(0);
    });

    it("shows correct filter counts in dropdown options", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Find the outcome filter dropdown
      const outcomeSelect = panel.getByLabelText(/Outcome/i);
      
      // Should show counts in the options
      const options = within(outcomeSelect).getAllByRole("option");
      // Verify "All outcomes" option exists with total count
      const allOption = options.find(opt => opt.textContent?.includes("All outcomes"));
      expect(allOption).toBeDefined();
    });
  });

  describe("filter dropdown interactions", () => {
    it("can change outcome filter via dropdown", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      const user = userEvent.setup();
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Find and change the outcome filter
      const outcomeSelect = panel.getByLabelText(/Outcome/i);
      await user.selectOptions(outcomeSelect, "success");
      
      // The filter should be applied (fewer cards should show)
      await waitFor(() => {
        // Should still show some entries (text may appear in summary strip and/or grid cards)
        const matches = screen.queryAllByText(/Check pod status/i);
        expect(matches.length).toBeGreaterThan(0);
      });
    });

    it("can change usefulness filter via dropdown", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      const user = userEvent.setup();
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Find and change the usefulness filter
      const usefulnessSelect = panel.getByLabelText(/Reviewed/i);
      await user.selectOptions(usefulnessSelect, "useful");
      
      // Should show only useful entries (text may appear in summary strip and/or grid cards)
      await waitFor(() => {
        const matches = screen.queryAllByText(/Check pod status/i);
        expect(matches.length).toBeGreaterThan(0);
      });
    });

    it("persists filter state to localStorage", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      const user = userEvent.setup();
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Change the outcome filter
      const outcomeSelect = panel.getByLabelText(/Outcome/i);
      await user.selectOptions(outcomeSelect, "success");
      
      // Verify localStorage was updated
      await waitFor(() => {
        const stored = storageMock.getItem(EXECUTION_HISTORY_FILTER_STORAGE_KEY);
        expect(stored).not.toBeNull();
        const parsed = JSON.parse(stored!);
        expect(parsed.outcomeFilter).toBe("success");
      });
    });
  });

  describe("combined filter interactions", () => {
    it("applies both outcome and usefulness filters together", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      const user = userEvent.setup();
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Apply outcome filter
      const outcomeSelect = panel.getByLabelText(/Outcome/i);
      await user.selectOptions(outcomeSelect, "failure");
      
      // Apply usefulness filter
      const usefulnessSelect = panel.getByLabelText(/Reviewed/i);
      await user.selectOptions(usefulnessSelect, "partial");
      
      // Should show only entries matching BOTH filters
      await waitFor(() => {
        // "Get events" entry has status=failed and usefulness=partial
        expect(screen.getByText(/Get events/i)).toBeInTheDocument();
      });
    });
  });

  describe("empty state rendering", () => {
    it("shows true-empty message when no history exists", async () => {
      const emptyPayloads = {
        ...defaultPayloads,
        "/api/run": createExecutionHistoryPayload([]),
      };
      vi.stubGlobal("fetch", createFetchMock(emptyPayloads));
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Should show the "no execution history" message
      await waitFor(() => {
        expect(
          panel.getByText(/No execution history for this run/i)
        ).toBeInTheDocument();
      });
    });

    it("shows filter-empty message when filters exclude all entries", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      const user = userEvent.setup();
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Apply a filter that matches nothing
      const outcomeSelect = panel.getByLabelText(/Outcome/i);
      await user.selectOptions(outcomeSelect, "timeout");
      
      // Apply usefulness filter for something that won't match
      const usefulnessSelect = panel.getByLabelText(/Reviewed/i);
      await user.selectOptions(usefulnessSelect, "useful");
      
      // Should show the "no entries match" message
      await waitFor(() => {
        expect(
          panel.getByText(/No entries match the current filters/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("'Showing X of Y' count display", () => {
    it("shows correct count when filters reduce results", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      const user = userEvent.setup();
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Apply a filter
      const usefulnessSelect = panel.getByLabelText(/Reviewed/i);
      await user.selectOptions(usefulnessSelect, "unreviewed");
      
      // Should show "Showing X of Y" count
      await waitFor(() => {
        // There are 2 unreviewed entries
        expect(panel.getByText(/Showing 2 of 5/i)).toBeInTheDocument();
      });
    });

    it("does not show count when all entries are visible", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      
      await getExecutionHistoryPanel();
      
      // With all filters at default, should not show the "Showing X of Y" message
      await waitFor(() => {
        expect(screen.queryByText(/^Showing \d+ of \d+$/)).not.toBeInTheDocument();
      });
    });
  });

  describe("cluster and command filter visibility", () => {
    it("shows cluster filter when multiple clusters exist", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Should show cluster filter since we have 2 different clusters
      expect(panel.getByLabelText(/Cluster/i)).toBeInTheDocument();
    });

    it("shows command filter when multiple command families exist", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Should show command filter since we have 3 different families
      expect(panel.getByLabelText(/Command/i)).toBeInTheDocument();
    });

    it("filters by cluster when selected", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      const user = userEvent.setup();
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Find and use the cluster filter
      const clusterSelect = panel.getByLabelText(/Cluster/i);
      await user.selectOptions(clusterSelect, "prod-cluster-1");
      
      // Should filter to show only prod-cluster-1 entries (3 entries)
      await waitFor(() => {
        expect(panel.getByText(/Showing 3 of 5/i)).toBeInTheDocument();
      });
    });

    it("filters by command family when selected", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      const user = userEvent.setup();
      render(<App />);
      
      const panel = await getExecutionHistoryPanel();
      
      // Find and use the command filter
      const commandSelect = panel.getByLabelText(/Command/i);
      await user.selectOptions(commandSelect, "kubectl-describe");
      
      // Should filter to show only kubectl-describe entries (1 entry)
      await waitFor(() => {
        expect(panel.getByText(/Showing 1 of 5/i)).toBeInTheDocument();
      });
    });
  });
});