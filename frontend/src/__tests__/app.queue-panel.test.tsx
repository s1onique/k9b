/**
 * Queue panel behavior tests.
 * 
 * Tests the next check queue panel rendering, queue item selection,
 * queue status display, queue filtering, and queue card details.
 * 
 * Split from app.test.tsx as part of the LLM-friendly file split.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { QUEUE_VIEW_STORAGE_KEY } from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  getQueuePanel,
  makeRunWithOverrides,
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

describe("Queue panel", () => {
  test("renders next-check queue panel with queue items", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    // Wait for data to load first
    await waitFor(() => {
      expect(screen.queryByText(/Loading selected run/i)).not.toBeInTheDocument();
    });

    // Wait for queue items to appear
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
    });

    const heading = await screen.findByRole("heading", { name: /Work list/i });
    const queuePanel = heading.closest(".next-check-queue-panel");
    expect(queuePanel).not.toBeNull();
    const queueScoped = within(queuePanel!);
    expect(queueScoped.getByRole("heading", { name: /Work list/i })).toBeInTheDocument();
    expect(queueScoped.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
  });

  test("queue item details toggle reveals metadata and command preview", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Use getQueuePanel which properly waits for queue content to load
    const queueScoped = await getQueuePanel();
    const describeCard = queueScoped
      .getByText(/Describe diag CRD for control plane/i)
      .closest("article");
    expect(describeCard).not.toBeNull();
    const showButton = within(describeCard!).getByRole("button", { name: /More/i });
    await act(async () => {
      await user.click(showButton);
    });
    expect(queueScoped.getByText(/Source reason:/i)).toBeInTheDocument();
    expect(queueScoped.getByText(UI_STRINGS.commandPreview.commandPreview, { exact: false })).toBeInTheDocument();
    expect(queueScoped.getByText(/Plan artifact/i)).toBeInTheDocument();
    expect(queueScoped.getByText(/kubectl describe diag/i)).toBeInTheDocument();
  });

  test("queue card shows priorityRationale with label when present", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const queueScoped = await getQueuePanel();
    // candidate-vague has priorityRationale: "Approval required before execution"
    const approvalCard = queueScoped
      .getByText(/Describe diag CRD for control plane/i)
      .closest("article");
    expect(approvalCard).not.toBeNull();
    // Verify the blocker note with icon is present (displays priorityRationale with ⏸ icon)
    expect(within(approvalCard!).getByText(/⏸/i)).toBeInTheDocument();
    // Verify the rationale content appears in the blocker note
    expect(within(approvalCard!).getByText(UI_STRINGS.emptyState.approvalRequiredBeforeExecution, { exact: false })).toBeInTheDocument();
  });

  test("queue card omits priorityRationale label when field is absent", async () => {
    const runWithoutRationale = JSON.parse(JSON.stringify(sampleRun));
    // candidate-vague is at nextCheckQueue[0] and normally has priorityRationale
    // Remove it to test absence
    delete runWithoutRationale.nextCheckQueue[0].priorityRationale;
    const payloads = { ...defaultPayloads, "/api/run": runWithoutRationale };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    const queueScoped = await getQueuePanel();
    // After removing priorityRationale from candidate-vague, the "Approval required before execution"
    // text should NOT appear anywhere in the queue
    expect(queueScoped.queryByText(UI_STRINGS.emptyState.approvalRequiredBeforeExecution, { exact: false })).toBeNull();
  });

  test("queue card shows rankingReason badge when present", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const queueScoped = await getQueuePanel();
    // candidate-vague has rankingReason: "approval-gated"
    const approvalCard = queueScoped
      .getByText(/Describe diag CRD for control plane/i)
      .closest("article");
    expect(approvalCard).not.toBeNull();
    // Verify the rankingReason badge appears with the structured category
    expect(within(approvalCard!).getByText(/approval-gated/i)).toBeInTheDocument();
  });

  test("queue card omits rankingReason badge when field is absent", async () => {
    const runWithoutRanking = JSON.parse(JSON.stringify(sampleRun));
    // candidate-vague is at nextCheckQueue[0] and normally has rankingReason: "approval-gated"
    // Remove it to test absence
    delete runWithoutRanking.nextCheckQueue[0].rankingReason;
    const payloads = { ...defaultPayloads, "/api/run": runWithoutRanking };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    const queueScoped = await getQueuePanel();
    // After removing rankingReason from candidate-vague, "approval-gated" should NOT appear in the queue
    expect(queueScoped.queryByText(/approval-gated/i)).toBeNull();
  });

  test("queue metadata shows deterministic origin label", async () => {
    const runWithSource = JSON.parse(JSON.stringify(sampleRun));
    runWithSource.nextCheckQueue[0].sourceType = "deterministic";
    const payloads = { ...defaultPayloads, "/api/run": runWithSource };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);

    const queueScoped = await getQueuePanel();
    const logsCard = queueScoped
      .getByText(/Collect kubelet logs for control-plane pods/i)
      .closest("article");
    expect(logsCard).not.toBeNull();
    await queueScoped.findByText(/Deterministic evidence/i);
  });

  test("queue cluster filter scopes to selected cluster", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Wait for queue items to be present before interacting
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
    });
    const queueScoped = await getQueuePanel();
    const clusterSelect = queueScoped.getByLabelText(/Cluster filter/i);
    await act(async () => {
      await user.selectOptions(clusterSelect, "cluster-b");
    });
    expect(queueScoped.getAllByText(/Cluster: cluster-b/i).length).toBeGreaterThan(0);
    expect(queueScoped.queryByText(/Cluster: cluster-a/i)).toBeNull();
    expect(queueScoped.queryByText(/Cluster: Unassigned/i)).toBeNull();
  });

  test("queue status filter limits to chosen status", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Wait for queue items to be present before interacting
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
    });
    const queueScoped = await getQueuePanel();
    const statusSelect = queueScoped.getByLabelText(/Queue status/i);
    await act(async () => {
      await user.selectOptions(statusSelect, "duplicate-or-stale");
    });
    expect(queueScoped.getAllByRole("heading", { level: 3, name: /Duplicate \/ stale/i }).length).toBeGreaterThan(0);
    expect(
      queueScoped.queryByRole("heading", { name: /Approval needed/i })
    ).toBeNull();
  });

  test("queue command family filter restricts to logs", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Wait for queue items to be present before interacting
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
    });
    const queueScoped = await getQueuePanel();
    const commandSelect = queueScoped.getByLabelText(/Command family/i);
    await act(async () => {
      await user.selectOptions(commandSelect, "kubectl-logs");
    });
    expect(queueScoped.getByText(/Collect kubelet logs for control-plane pods/i)).toBeInTheDocument();
    expect(queueScoped.queryByText(/Describe diag CRD for control plane/i)).toBeNull();
  });

  test("queue priority filter narrows to fallback candidates", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Wait for queue items to be present before interacting
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
    });
    const queueScoped = await getQueuePanel();
    const prioritySelect = queueScoped.getByLabelText(/Priority/i);
    await act(async () => {
      await user.selectOptions(prioritySelect, "fallback");
    });
    expect(queueScoped.getByText(/Capture kubelet metrics for control-plane nodes/i)).toBeInTheDocument();
    expect(queueScoped.queryByText(/Collect kubelet logs for control-plane pods/i)).toBeNull();
  });

  test("queue search matches description or reason", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Wait for queue items to be present before interacting
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
    });
    const queueScoped = await getQueuePanel();
    const searchInput = queueScoped.getByPlaceholderText(/Description, reason, or signal/i);
    await act(async () => {
      await user.type(searchInput, "storage");
    });
    expect(queueScoped.getByText(/Collect storage latency metrics/i)).toBeInTheDocument();
    expect(queueScoped.queryByText(/Collect kubelet logs for control-plane pods/i)).toBeNull();
  });

  test("queue focus presets toggle actionable sets", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Wait for queue items to be present before interacting
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
    });
    const queueScoped = await getQueuePanel();
    const workButton = queueScoped.getByRole("button", { name: /Work now/i });
    const reviewButton = queueScoped.getByRole("button", { name: /Needs review/i });
    await act(async () => {
      await user.click(workButton);
    });
    expect(
      queueScoped.getAllByRole("heading", { level: 3, name: /Safe to automate/i }).length
    ).toBeGreaterThan(0);
    expect(
      queueScoped.queryByRole("heading", { name: /Approval needed/i })
    ).toBeNull();
    await act(async () => {
      await user.click(reviewButton);
    });
    expect(
      queueScoped.getAllByRole("heading", { level: 3, name: /Approval needed/i }).length
    ).toBeGreaterThan(0);
    expect(
      queueScoped.getAllByRole("heading", { level: 3, name: /Duplicate \/ stale/i }).length
    ).toBeGreaterThan(0);
    expect(queueScoped.queryByRole("heading", { level: 3, name: /Safe to automate/i })).toBeNull();
  });

  test("queue filters restore saved queue view", async () => {
    localStorage.setItem(
      QUEUE_VIEW_STORAGE_KEY,
      JSON.stringify({
        clusterFilter: "cluster-b",
        statusFilter: "safe-ready",
        commandFamilyFilter: "kubectl-get",
        priorityFilter: "primary",
        searchText: "storage",
        focusMode: "work",
        sortOption: "activity",
      })
    );
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const queueScoped = await getQueuePanel();
    expect(queueScoped.getByLabelText(/Cluster filter/i)).toHaveValue("cluster-b");
    expect(queueScoped.getByLabelText(/Queue status/i)).toHaveValue("safe-ready");
    expect(queueScoped.getByLabelText(/Command family/i)).toHaveValue("kubectl-get");
    expect(queueScoped.getByLabelText(/Priority/i)).toHaveValue("primary");
    expect(queueScoped.getByLabelText(/Sort by/i)).toHaveValue("activity");
    expect(queueScoped.getByPlaceholderText(/Description, reason, or signal/i)).toHaveValue(
      "storage"
    );
    const workButton = queueScoped.getByRole("button", { name: /Work now/i });
    expect(workButton).toHaveClass("active");
    expect(queueScoped.getByText(/Collect storage latency metrics/i)).toBeInTheDocument();
    expect(queueScoped.queryByText(/Collect kubelet logs for control-plane pods/i)).toBeNull();
  });

  test("reset queue view clears persisted filters", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const queueScoped = await getQueuePanel();
    const clusterSelect = queueScoped.getByLabelText(/Cluster filter/i);
    await act(async () => {
      await user.selectOptions(clusterSelect, "cluster-b");
    });
    await waitFor(() => {
      const stored = localStorage.getItem(QUEUE_VIEW_STORAGE_KEY);
      expect(stored).not.toBeNull();
      expect(stored ? JSON.parse(stored).clusterFilter : null).toBe("cluster-b");
    });

    const resetButton = queueScoped.getByRole("button", { name: /Reset queue view/i });
    await act(async () => {
      await user.click(resetButton);
    });
    expect(clusterSelect).toHaveValue("all");
    await waitFor(() => {
      const stored = localStorage.getItem(QUEUE_VIEW_STORAGE_KEY);
      expect(stored).not.toBeNull();
      expect(stored ? JSON.parse(stored).clusterFilter : null).toBe("all");
    });
  });

  test("invalid stored queue view falls back to defaults", async () => {
    localStorage.setItem(
      QUEUE_VIEW_STORAGE_KEY,
      JSON.stringify({
        clusterFilter: 123,
        statusFilter: "nonexistent",
        commandFamilyFilter: null,
        priorityFilter: { label: "fallback" },
        searchText: 5,
        focusMode: "broken",
        sortOption: "unexpected",
      })
    );
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const queueScoped = await getQueuePanel();
    expect(queueScoped.getByLabelText(/Cluster filter/i)).toHaveValue("all");
    expect(queueScoped.getByLabelText(/Queue status/i)).toHaveValue("all");
    expect(queueScoped.getByLabelText(/Command family/i)).toHaveValue("all");
    expect(queueScoped.getByLabelText(/Priority/i)).toHaveValue("all");
    expect(queueScoped.getByLabelText(/Sort by/i)).toHaveValue("default");
    expect(queueScoped.getByPlaceholderText(/Description, reason, or signal/i)).toHaveValue("");
    const workButton = queueScoped.getByRole("button", { name: /Work now/i });
    const reviewButton = queueScoped.getByRole("button", { name: /Needs review/i });
    expect(workButton).not.toHaveClass("active");
    expect(reviewButton).not.toHaveClass("active");
    await waitFor(() => {
      const stored = localStorage.getItem(QUEUE_VIEW_STORAGE_KEY);
      expect(stored).not.toBeNull();
      expect(stored ? JSON.parse(stored).statusFilter : null).toBe("all");
    });
  });

  test("queue details expose follow-up guidance for failed executions", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const queueCard = await screen.findByText(/Inspect etcd leader/i);
    const queueArticle = queueCard.closest("article");
    expect(queueArticle).not.toBeNull();
    const showDetails = within(queueArticle!).getByRole("button", { name: /More/i });
    await act(async () => {
      await user.click(showDetails);
    });
    expect(within(queueArticle!).getByText(/Inspect artifact output/i)).toBeInTheDocument();
  });

  test("queue card status metadata is visually separate from title content", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const queueScoped = await getQueuePanel();
    // Find a queue card - the first one that has both title and status
    const queueCard = queueScoped
      .getByText(/Describe diag CRD for control plane/i)
      .closest("article");
    expect(queueCard).not.toBeNull();

    // Verify the title block exists (h4 element with queue-item-title class)
    const titleBlock = within(queueCard!).getByText(/Describe diag CRD for control plane/i);
    expect(titleBlock).toBeInTheDocument();

    // Verify the "Why:" label exists (part of the rationale line)
    expect(within(queueCard!).getByText(/Why:/i)).toBeInTheDocument();

    // Verify the status badges container exists (right column: status badges)
    const statusBadges = queueCard!.querySelector(".queue-item-status-badges");
    expect(statusBadges).not.toBeNull();

    // Verify the header block separates title from status badges
    const headerBlock = queueCard!.querySelector(".next-check-queue-item-header");
    expect(headerBlock).not.toBeNull();

    // The header block should have two direct children: the title block and the status badges
    const headerChildren = headerBlock!.children;
    expect(headerChildren.length).toBe(2);

    // First child should be the title block containing the h4 title
    const titleColumn = headerChildren[0];
    expect(titleColumn.className).toContain("queue-item-title-block");
    expect(titleColumn.textContent).toContain("Describe diag CRD");

    // Second child should be the status badges container (right column)
    const statusColumn = headerChildren[1];
    expect(statusColumn.className).toContain("queue-item-status-badges");
  });
});
