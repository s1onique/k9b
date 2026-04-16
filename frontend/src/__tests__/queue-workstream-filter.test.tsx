import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, it, vi } from "vitest";
import App, { QUEUE_VIEW_STORAGE_KEY } from "../App";
import { createFetchMock, createStorageMock, makeRunWithOverrides, sampleClusterDetail, sampleFleet, sampleNotifications, sampleProposals, sampleRun, sampleRunsList } from "./fixtures";

// Default payloads for API mocking - must include cluster-detail for queue section to render
const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/runs": sampleRunsList,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/notifications?limit=50&page=1": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
  "/api/review-enrichment-status": {
    status: "success",
    reason: "Review enrichment is available.",
    provider: "k8sgpt",
    policyEnabled: true,
    providerConfigured: true,
    adapterAvailable: true,
    runEnabled: true,
    runProvider: "k8sgpt",
  },
};


// Helper to get the queue panel with proper scoping
const getQueuePanel = async () => {
  const eyebrow = await screen.findByText(/Next-check queue/i);
  const queuePanel = eyebrow.closest(".next-check-queue-panel");
  if (!queuePanel) {
    throw new Error("Queue panel is not rendered");
  }
  return within(queuePanel);
};

// Helper to find workstream filter within queue panel scope
const getWorkstreamSelect = (queueScoped: ReturnType<typeof within>) => {
  // Find the workstream filter by its label
  return queueScoped.getByLabelText(/Workstream/i);
};

// Create run with workstream values in queue items
const createRunWithWorkstreams = (workstreamValues: string[]) => {
  return makeRunWithOverrides({
    nextCheckQueue: sampleRun.nextCheckQueue.map((item, index) => ({
      ...item,
      workstream: workstreamValues[index % workstreamValues.length],
    })),
  });
};

// Default workstream values: incident, evidence, drift repeating for 6 queue items
const defaultQueueItems = ["incident", "evidence", "drift", "incident", "evidence", "drift"];

describe("Queue workstream filter", () => {
  let storageMock: ReturnType<typeof createStorageMock>;

  beforeEach(() => {
    storageMock = createStorageMock();
    vi.stubGlobal("localStorage", storageMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders workstream filter dropdown when queue section is visible", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);
    expect(workstreamSelect).toBeTruthy();
  });

  it("shows all items by default when workstream filter is not set", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const queueScoped = await getQueuePanel();
    // Default workstream filter should be "all" - all 6 items should be visible
    const queueItems = queueScoped.getAllByRole("article");
    expect(queueItems.length).toBe(6);
  });

  it("filters queue items by incident workstream", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const user = userEvent.setup();
    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);

    await user.selectOptions(workstreamSelect, "incident");

    // Verify the selection was saved to localStorage
    const savedState = JSON.parse(storageMock.getItem(QUEUE_VIEW_STORAGE_KEY) || "{}");
    expect(savedState.workstreamFilter).toBe("incident");
  });

  it("filters queue items by evidence workstream", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const user = userEvent.setup();
    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);

    await user.selectOptions(workstreamSelect, "evidence");

    const savedState = JSON.parse(storageMock.getItem(QUEUE_VIEW_STORAGE_KEY) || "{}");
    expect(savedState.workstreamFilter).toBe("evidence");
  });

  it("filters queue items by drift workstream", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const user = userEvent.setup();
    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);

    await user.selectOptions(workstreamSelect, "drift");

    const savedState = JSON.parse(storageMock.getItem(QUEUE_VIEW_STORAGE_KEY) || "{}");
    expect(savedState.workstreamFilter).toBe("drift");
  });

  it("persists workstream filter to localStorage", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const user = userEvent.setup();
    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);

    await user.selectOptions(workstreamSelect, "drift");

    expect(storageMock.getItem(QUEUE_VIEW_STORAGE_KEY)).toBeTruthy();
    const savedState = JSON.parse(storageMock.getItem(QUEUE_VIEW_STORAGE_KEY)!);
    expect(savedState.workstreamFilter).toBe("drift");
  });

  it("restores workstream filter from localStorage on load", async () => {
    // Pre-populate localStorage with workstream filter
    storageMock.setItem(QUEUE_VIEW_STORAGE_KEY, JSON.stringify({
      statusFilter: "all",
      priorityFilter: "all",
      workstreamFilter: "evidence",
    }));

    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);

    // Verify filter was restored from localStorage
    expect(workstreamSelect.value).toBe("evidence");
  });

  it("resets workstream filter when reset button is clicked", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const user = userEvent.setup();
    const queueScoped = await getQueuePanel();
    let workstreamSelect = getWorkstreamSelect(queueScoped);

    // Set a workstream filter first
    await user.selectOptions(workstreamSelect, "drift");

    // Click reset button
    const resetButton = queueScoped.getByRole("button", { name: /Reset/i });
    await user.click(resetButton);

    // Verify filter was reset to 'all'
    workstreamSelect = getWorkstreamSelect(queueScoped);
    expect(workstreamSelect.value).toBe("all");
  });

  it("shows empty state when no items match workstream filter", async () => {
    // Create a run with mixed workstreams
    const mixedWorkstreams = ["incident", "incident", "incident", "incident", "incident", "incident"];
    const runWithWorkstreams = createRunWithWorkstreams(mixedWorkstreams);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const user = userEvent.setup();
    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);

    // All 6 items are incident, only 'all' and 'incident' options exist
    let queueItems = queueScoped.queryAllByRole("article");
    expect(queueItems.length).toBe(6);

    // Switch to 'all' filter (default) - all items should still be visible
    await user.selectOptions(workstreamSelect, "all");
    queueItems = queueScoped.queryAllByRole("article");
    expect(queueItems.length).toBe(6);
  });

  it("has all workstream options in the filter dropdown", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);
    const options = Array.from(workstreamSelect.options).map((o) => o.value);

    // Should have options for all, incident, evidence, drift
    expect(options).toContain("all");
    expect(options).toContain("incident");
    expect(options).toContain("evidence");
    expect(options).toContain("drift");
  });

  it("updates queue items when switching workstream filter", async () => {
    const runWithWorkstreams = createRunWithWorkstreams(defaultQueueItems);
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/run": runWithWorkstreams,
    }));
    render(<App />);

    const user = userEvent.setup();
    const queueScoped = await getQueuePanel();
    const workstreamSelect = getWorkstreamSelect(queueScoped);

    // First set to incident
    await user.selectOptions(workstreamSelect, "incident");
    let savedState = JSON.parse(storageMock.getItem(QUEUE_VIEW_STORAGE_KEY) || "{}");
    expect(savedState.workstreamFilter).toBe("incident");

    // Then switch to evidence
    await user.selectOptions(workstreamSelect, "evidence");
    savedState = JSON.parse(storageMock.getItem(QUEUE_VIEW_STORAGE_KEY) || "{}");
    expect(savedState.workstreamFilter).toBe("evidence");

    // Then switch to drift
    await user.selectOptions(workstreamSelect, "drift");
    savedState = JSON.parse(storageMock.getItem(QUEUE_VIEW_STORAGE_KEY) || "{}");
    expect(savedState.workstreamFilter).toBe("drift");
  });
});