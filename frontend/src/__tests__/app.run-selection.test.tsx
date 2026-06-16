/**
 * Run selection and summary tests.
 * 
 * Tests recent runs panel display, run selection behavior,
 * run summary panel, and run freshness indicators.
 * 
 * Split from app.test.tsx as part of the LLM-friendly file split.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";

import {
  createFetchMock,
  createFetchQueueMock,
  createStorageMock,
  defaultPayloads,
  getQueuePanel,
  getLoadedDeterministicPanel,
  makeFetchResponse,
  makeRunWithOverrides,
  minsAgo,
  sampleRun,
  sampleRunsList,
  UI_STRINGS,
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

describe("Recent runs selection", () => {
  test("recent-runs panel displays runs with triage status and allows selection", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Find the recent runs panel
    const recentRunsPanel = (await screen.findAllByText(/Recent runs/i))[0];
    expect(recentRunsPanel).toBeInTheDocument();

    // Verify runs list is rendered
    const runsList = document.querySelector(".runs-table-wrapper");
    expect(runsList).not.toBeNull();

    // Verify runs are displayed with review status pills - use getAll since there may be multiple
    // Note: StatusBadge renders "Needs attention" for reviewStatus="unreviewed" per RunsPanel.tsx
    const unreviewedPills = screen.getAllByText("Needs attention");
    expect(unreviewedPills.length).toBeGreaterThan(0);
    const partiallyReviewedPills = screen.getAllByText("Partially executed");
    expect(partiallyReviewedPills.length).toBeGreaterThan(0);

    // Verify runs list has items - the run items are rendered
    const runItems = screen.getAllByTestId("run-entry");
    expect(runItems.length).toBeGreaterThan(0);
  });

  test("recent-runs panel filter buttons filter runs by review status", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Find the recent runs panel and wait for run rows to appear
    await screen.findAllByText(/Recent runs/i)[0];

    // Wait for the runs to render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Verify the filter buttons exist
    const noExecutionsFilter = document.querySelector(".runs-filter-button") as HTMLButtonElement;
    expect(noExecutionsFilter).not.toBeNull();

    // Initially should show all 4 runs
    const allRunItems = document.querySelectorAll(".run-row");
    expect(allRunItems.length).toBe(4);

    // Test "No executions yet" filter button - should show runs with no executions
    // From fixtures: run-120 (reviewStatus: "no-executions") = 1 run
    const noExecutionsFilterButton = document.querySelectorAll(".runs-filter-button")[2] as HTMLButtonElement;
    await act(async () => {
      await user.click(noExecutionsFilterButton);
    });
    let filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(1);

    // Test "Needs attention" filter - should show runs with reviewStatus "unreviewed" or "partially-reviewed"
    const awaitingReviewFilter = document.querySelectorAll(".runs-filter-button")[5] as HTMLButtonElement;
    await act(async () => {
      await user.click(awaitingReviewFilter);
    });
    filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(2);
    expect(screen.getByText(/Showing 2 of 4/)).toBeInTheDocument();

    // Test "all" filter button - should show all runs again
    const allFilterButton = document.querySelectorAll(".runs-filter-button")[0] as HTMLButtonElement;
    await act(async () => {
      await user.click(allFilterButton);
    });
    filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(4);
  });

  test("recent-runs review download link uses /artifact endpoint", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findAllByText(/Recent runs/i)[0];
    const allFilterButton = document.querySelectorAll(".runs-filter-button")[0] as HTMLButtonElement;
    if (allFilterButton) {
      await act(async () => {
        await userEvent.setup().click(allFilterButton);
      });
    }

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const downloadLinks = document.querySelectorAll(".run-row a.row-action");
    expect(downloadLinks.length).toBeGreaterThan(0);

    const downloadLink = downloadLinks[0] as HTMLAnchorElement;
    const href = downloadLink.href;
    expect(href).toContain("/artifact?path=");
    expect(href).not.toContain("/api/artifacts");
  });

  test("first load defaults to latest run", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const selectedRow = document.querySelector(".run-row-selected");
      expect(selectedRow).not.toBeNull();
    });

    const latestRunRow = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(latestRunRow).not.toBeNull();
    expect(latestRunRow).toHaveClass("run-row-selected");

    const heroLabel = await screen.findByText(/^Latest$/i);
    expect(heroLabel).toBeInTheDocument();
  });

  test("selecting a run from Recent runs changes selectedRunId and fetches data", async () => {
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return makeFetchResponse({
              ...sampleRun,
              runId: "run-122",
              label: "Run 122 specific",
              nextCheckExecutionHistory: [],
              nextCheckQueue: [],
            });
        }
        return makeFetchResponse(sampleRun);
      }
      
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) return Promise.reject(new Error(`Unexpected fetch ${url}`));
      return makeFetchResponse(payload);
    });
    
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const latestRunRow = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(latestRunRow).toHaveClass("run-row-selected");
    
    const olderRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(olderRunRow).not.toBeNull();

    await act(async () => {
      await user.click(olderRunRow!);
    });

    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    expect(latestRunRow).not.toHaveClass("run-row-selected");
    
    const selectedLabel = await screen.findByText(/^Selected run$/i);
    expect(selectedLabel).toBeInTheDocument();
  });

  test("jump-to-latest returns to current/latest run", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const olderRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(olderRunRow).not.toBeNull();

    await act(async () => {
      await user.click(olderRunRow!);
    });

    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    const selectedLabel = screen.queryByText(/^Selected run$/i);
    expect(selectedLabel).toBeInTheDocument();

    const jumpButton = await screen.findByText(/← Latest/i);
    expect(jumpButton).toBeInTheDocument();

    await act(async () => {
      await user.click(jumpButton);
    });

    const latestRunRow = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(latestRunRow).toHaveClass("run-row-selected");

    const currentRunLabel = await screen.findByText(/^Latest$/i);
    expect(currentRunLabel).toBeInTheDocument();
  });

  test("keyboard navigation works for run selection", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const firstRunRow = document.querySelector('.run-row[data-run-id="run-123"]') as HTMLElement;
    expect(firstRunRow).not.toBeNull();
    firstRunRow.focus();

    expect(document.activeElement).toBe(firstRunRow);

    await act(async () => {
      firstRunRow.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });

    expect(firstRunRow).toHaveClass("run-row-selected");

    const secondRunRow = document.querySelector('.run-row[data-run-id="run-122"]') as HTMLElement;
    secondRunRow.focus();

    await act(async () => {
      secondRunRow.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    });

    await waitFor(() => {
      expect(secondRunRow).toHaveClass("run-row-selected");
    });
  });
});

describe("Run summary", () => {
  test("run summary surfaces next-check discovery actions", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findAllByText(/Daily sweep/i);
    const summaryPanel = document.getElementById("run-detail");
    expect(summaryPanel).not.toBeNull();
    const summaryScoped = within(summaryPanel!);

    const nextChecksTab = await summaryScoped.findByRole("tab", { name: /Next checks/i });
    await act(async () => {
      nextChecksTab.click();
    });

    expect(summaryScoped.getByText(UI_STRINGS.planner.plannerCandidates, { exact: false })).toBeInTheDocument();
    expect(summaryScoped.getByText(UI_STRINGS.workflowLanes.safeCandidate, { exact: false })).toBeInTheDocument();
    expect(summaryScoped.getByText(UI_STRINGS.workflowLanes.approvalNeeded, { exact: false })).toBeInTheDocument();
    expect(summaryScoped.getByRole("button", { name: /Review next checks/i })).toBeInTheDocument();
    expect(summaryScoped.getByRole("link", { name: /View planner artifact/i })).toBeInTheDocument();
  });

  test("run summary shows empty state when planner data is absent", async () => {
    const payloads = {
      ...defaultPayloads,
      "/api/run": { ...sampleRun, nextCheckPlan: null },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    expect(await screen.findByText(/No next checks generated for this run/i)).toBeInTheDocument();
  });

  test("execution history cards surface result interpretations", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const summaryText = /control-plane errors useful for diagnosing the incident/i;
    expect(await screen.findByText(summaryText)).toBeInTheDocument();
  });

  test("renders execution history entries from the run payload", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const panel = await screen.findByRole("heading", { name: /Check execution review/i });
    expect(panel).toBeInTheDocument();
    expect(screen.getByText(/Check execution review/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Collect kubelet logs for control-plane pods/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Timed out/i, { selector: ".execution-history-badge" })).toBeInTheDocument();
  });

  test("execution history follow-up block surfaces retry guidance", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    expect(await screen.findByText(/Retry candidate/i)).toBeInTheDocument();
  });
});

describe("Run freshness thresholds", () => {
  test("run shows Fresh status when timestamp is <= 15 minutes old", async () => {
    const freshRun = {
      ...sampleRun,
      timestamp: minsAgo(10),
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": freshRun }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const freshLabel = screen.getByText(/^Fresh$/i);
    expect(freshLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--fresh");
    expect(freshnessIndicator).not.toBeNull();
  });

  test("run shows Aging status when timestamp is > 15 and <= 45 minutes old", async () => {
    const agingTimestamp = minsAgo(30);
    const agingRun = {
      ...sampleRun,
      timestamp: agingTimestamp,
    };
    const agingRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Aging run", timestamp: agingTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": agingRun, "/api/runs": agingRunsList }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const agingLabel = screen.getByText(/^Aging$/i);
    expect(agingLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--warning");
    expect(freshnessIndicator).not.toBeNull();
  });

  test("run shows Stale status when timestamp is > 45 minutes old", async () => {
    const staleTimestamp = minsAgo(60);
    const staleRun = {
      ...sampleRun,
      timestamp: staleTimestamp,
    };
    const staleRunsList = {
      runs: [
        { runId: "run-123", runLabel: "Stale run", timestamp: staleTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": staleRun, "/api/runs": staleRunsList }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const staleLabel = screen.getByText(/^Stale$/i);
    expect(staleLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--stale");
    expect(freshnessIndicator).not.toBeNull();
  });

  test("selecting a past run hides freshness indicator but shows Past run badge", async () => {
    const freshRunTimestamp = minsAgo(10);
    const staleRunTimestamp = minsAgo(120);

    const runsWithDifferentTimestamps = {
      runs: [
        { runId: "run-123", runLabel: "Fresh run", timestamp: freshRunTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "Stale run", timestamp: staleRunTimestamp, clusterCount: 2, triaged: true, executionCount: 3, reviewedCount: 3, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 2,
    };

    const freshRun = { ...sampleRun, timestamp: freshRunTimestamp };
    const staleRun = { ...sampleRun, runId: "run-122", timestamp: staleRunTimestamp };

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve(makeFetchResponse(runsWithDifferentTimestamps));
      }
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return Promise.resolve(makeFetchResponse(staleRun));
        }
        return Promise.resolve(makeFetchResponse(freshRun));
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) return Promise.reject(new Error(`Unexpected fetch ${url}`));
      return Promise.resolve(makeFetchResponse(payload));
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      expect(screen.queryByText(/^Fresh$/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^Fresh$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Latest$/i)).toBeInTheDocument();

    const staleRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    await act(async () => {
      await user.click(staleRunRow!);
    });

    await waitFor(() => {
      expect(screen.queryByText(/^Past run$/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/^Past run$/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Stale$/i)).not.toBeInTheDocument();
    const staleIndicator = document.querySelector(".freshness-indicator");
    expect(staleIndicator).toBeNull();

    expect(screen.getByText(/← Latest/)).toBeInTheDocument();
    expect(screen.getByText(/Latest run available:/i)).toBeInTheDocument();
  });
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
