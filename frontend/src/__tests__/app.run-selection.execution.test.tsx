/**
 * Run selection execution and rendering tests.
 *
 * Tests recent runs panel display, run selection behavior, and
 * run summary panel rendering.
 *
 * Part of app.run-selection.test.tsx split for LLM-friendly file sizes.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  makeFetchResponse,
  sampleRun,
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

    // Verify runs are displayed with review status pills
    const unreviewedPills = screen.getAllByText("Needs attention");
    expect(unreviewedPills.length).toBeGreaterThan(0);
    const partiallyReviewedPills = screen.getAllByText("Partially executed");
    expect(partiallyReviewedPills.length).toBeGreaterThan(0);

    // Verify runs list has items
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

    // Test "No executions yet" filter button
    const noExecutionsFilterButton = document.querySelectorAll(".runs-filter-button")[2] as HTMLButtonElement;
    await user.click(noExecutionsFilterButton);
    let filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(1);

    // Test "Needs attention" filter
    const awaitingReviewFilter = document.querySelectorAll(".runs-filter-button")[5] as HTMLButtonElement;
    await user.click(awaitingReviewFilter);
    filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(2);
    expect(screen.getByText(/Showing 2 of 4/)).toBeInTheDocument();

    // Test "all" filter button
    const allFilterButton = document.querySelectorAll(".runs-filter-button")[0] as HTMLButtonElement;
    await user.click(allFilterButton);
    filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(4);
  });

  test("recent-runs review download link uses /artifact endpoint", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findAllByText(/Recent runs/i)[0];
    const allFilterButton = document.querySelectorAll(".runs-filter-button")[0] as HTMLButtonElement;
    if (allFilterButton) {
      await userEvent.setup().click(allFilterButton);
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

    await user.click(olderRunRow!);

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

    await user.click(olderRunRow!);

    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    const selectedLabel = screen.queryByText(/^Selected run$/i);
    expect(selectedLabel).toBeInTheDocument();

    const jumpButton = await screen.findByText(/← Latest/i);
    expect(jumpButton).toBeInTheDocument();

    await user.click(jumpButton);

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
});
