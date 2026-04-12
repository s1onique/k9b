import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { AUTOREFRESH_STORAGE_KEY, QUEUE_VIEW_STORAGE_KEY } from "../App";
import type { NotificationEntry } from "../types";
import {
  makeDiagnosticPackReview,
  makeRunWithOverrides,
  sampleClusterDetail,
  sampleFleet,
  sampleNextCheckCandidates,
  sampleNotifications,
  sampleProposals,
  sampleRun,
} from "./fixtures";

const createStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
};

const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/notifications?limit=50&page=1": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
  "/api/deterministic-next-check/promote": {
    status: "success",
    summary: "Deterministic next check promoted to the queue.",
    artifactPath: "/artifacts/promoted.json",
    candidateId: "promo-1",
  },
};

const getQueuePanel = async () => {
  const eyebrow = await screen.findByText(/Next-check queue/i);
  const queuePanel = eyebrow.closest(".next-check-queue-panel");
  if (!queuePanel) {
    throw new Error("Queue panel is not rendered");
  }
  return within(queuePanel);
};

const NOTIFICATION_BASE_TIME = Date.UTC(2026, 3, 7, 0, 0, 0);
const PLANNER_HINT_TEXT =
  "Cluster Detail next checks may still reflect deterministic assessments or review content even when the planner artifact is absent.";

const buildNotificationEntry = (
  index: number,
  overrides: Partial<NotificationEntry> = {}
): NotificationEntry => {
  const defaultTimestamp = new Date(NOTIFICATION_BASE_TIME - index * 60000).toISOString();
  return {
    kind: overrides.kind ?? (index % 2 ? "Warning" : "Info"),
    summary: overrides.summary ?? `Notification ${index + 1}`,
    timestamp: overrides.timestamp ?? defaultTimestamp,
    runId: overrides.runId ?? `run-${(index % 3) + 1}`,
    clusterLabel: overrides.clusterLabel ?? `cluster-${(index % 2) + 1}`,
    context: overrides.context ?? "test-context",
    details: overrides.details ?? [{ label: "Pod", value: `pod-${index}` }],
    artifactPath: overrides.artifactPath ?? (index % 4 === 0 ? null : `/artifacts/n-${index}.json`),
  };
};

const buildNotificationList = (count: number) =>
  Array.from({ length: count }, (_, index) => buildNotificationEntry(index));

const createFetchMock = (payloads: Record<string, unknown>) =>
  vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    const base = url.split("?")[0];
    const payload = payloads[url] ?? payloads[base];
    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      json: () => Promise.resolve(payload),
    });
  });

const renderAppWithRunOverride = async (overrides: Partial<RunPayload>) => {
  const payloads = {
    ...defaultPayloads,
    "/api/run": makeRunWithOverrides(overrides),
  };
  vi.stubGlobal("fetch", createFetchMock(payloads));
  render(<App />);
  await screen.findByRole("heading", { name: /Fleet overview/i });
};

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

describe("App", () => {
  test("renders fleet overview data from the API payload", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    expect(screen.getByText(/Loading operator data/i)).toBeInTheDocument();
    await screen.findByRole("heading", { name: /Fleet overview/i });

    expect(
      screen.getByText(sampleFleet.topProblem.detail, { exact: false })
    ).toBeInTheDocument();
    expect(screen.getAllByText(sampleFleet.clusters[0].label).length).toBeGreaterThan(0);
    const triggerMatches = screen.getAllByText(sampleFleet.clusters[0].topTriggerReason!, {
      exact: false,
    });
    expect(triggerMatches.length).toBeGreaterThan(0);
  });

  test("switches cluster detail tabs to reveal hypotheses and checks", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const findingMatches = await screen.findAllByText(sampleClusterDetail.findings[0].label!, {
      exact: false,
    });
    expect(findingMatches.length).toBeGreaterThan(0);

    const tabList = screen.getByRole("tablist", { name: /Cluster detail tabs/i });
    await act(async () => {
      await user.click(within(tabList).getByRole("button", { name: /Hypotheses/i }));
    });
    expect(
      await screen.findByText(sampleClusterDetail.hypotheses[0].description)
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(within(tabList).getByRole("button", { name: /Next checks/i }));
    });
    expect(
      await screen.findByText(sampleClusterDetail.nextChecks[0].description)
    ).toBeInTheDocument();
  });

  test("cluster detail summary highlights health cues and recommended artifacts", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    expect(await screen.findByText(/Control plane saturation/i)).toBeInTheDocument();
    expect(await screen.findByText(/gRPC queues are growing/i)).toBeInTheDocument();
    expect(screen.getAllByText(/High CPU/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Recommended artifacts/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /diagnostic bundle/i }).length).toBeGreaterThan(0);
  });

  test("renders next check plan section with planner candidates", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const heading = await screen.findByRole("heading", { name: /Next check plan/i });
    expect(heading).toBeInTheDocument();
    const planPanel = heading.closest(".next-check-plan");
    expect(planPanel).not.toBeNull();
    expect(
      within(planPanel!).getByText(/Collect kubelet logs for control-plane pods/i)
    ).toBeInTheDocument();
    expect(within(planPanel!).getByText(/kubectl-logs/i)).toBeInTheDocument();
  });

  test("next check plan calls out safe, approval, and duplicate candidates", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const heading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planPanel = heading.closest(".next-check-plan");
    expect(planPanel).not.toBeNull();
    const scoped = within(planPanel!);
    expect(scoped.getAllByText(/Safe candidate/i).length).toBeGreaterThan(0);
    expect(scoped.getByText(/Approval needed/i)).toBeInTheDocument();
    expect(scoped.getByText(/Command not recognized or too vague/i)).toBeInTheDocument();
    expect(
      scoped.getByText(/Matches deterministic next check: Collect kubelet metrics/i)
    ).toBeInTheDocument();
  });

  test("next check outcome summary reveals status counts", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Next check plan/i });
    expect(screen.getByText(/Executed \(success\) · 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Awaiting approval · 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Not used · 1/i)).toBeInTheDocument();
  });

  test("run summary surfaces next-check discovery actions", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findAllByText(/Daily sweep/i);
    const summaryPanel = document.getElementById("run-detail");
    expect(summaryPanel).not.toBeNull();
    const summaryScoped = within(summaryPanel!);
    expect(summaryScoped.getByText(/Planner candidates/i)).toBeInTheDocument();
    expect(summaryScoped.getByText(/Safe candidate/i)).toBeInTheDocument();
    expect(summaryScoped.getByText(/Approval needed/i)).toBeInTheDocument();
    expect(summaryScoped.getByRole("button", { name: /Review next checks/i })).toBeInTheDocument();
    expect(summaryScoped.getByRole("link", { name: /View planner artifact/i })).toBeInTheDocument();
  });

  test("deterministic panel surfaces run-derived checks", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    expect(heading).toBeInTheDocument();
    expect(
      screen.getByText(/deterministic check.*derived from assessments/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review cluster detail/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View assessment artifact/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Firefight now/i).length).toBeGreaterThan(0);
    const driftNodes = screen.getAllByText(/Drift \/ toil follow-up/i);
    expect(driftNodes.length).toBeGreaterThan(0);
    const driftDetails = driftNodes[0].closest("details");
    expect(driftDetails).not.toHaveAttribute("open");
  });

  test("promote deterministic next check button triggers API and shows status", async () => {
    const payloads = { ...defaultPayloads };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const promoteButtons = await screen.findAllByRole("button", { name: /Promote to queue/i });
    expect(promoteButtons.length).toBeGreaterThan(0);
    await act(async () => {
      await user.click(promoteButtons[0]);
    });
    await waitFor(() =>
      expect(
        screen.getByText(/Deterministic next check promoted to the queue/i)
      ).toBeInTheDocument()
    );
    const promoteCall = fetchMock.mock.calls.find((call) =>
      typeof call[0] === "string" && call[0].includes("/api/deterministic-next-check/promote")
    );
    expect(promoteCall).toBeDefined();
    expect(promoteCall?.[1]).toMatchObject({ method: "POST" });
  });

  test("successful promotion shows link to filter queue by approval-needed status", async () => {
    const payloads = { ...defaultPayloads };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const promoteButtons = await screen.findAllByRole("button", { name: /Promote to queue/i });
    await act(async () => {
      await user.click(promoteButtons[0]);
    });

    // Wait for promotion success message
    await waitFor(() =>
      expect(
        screen.getByText(/Deterministic next check promoted to the queue/i)
      ).toBeInTheDocument()
    );

    // Verify "View in queue →" link is present
    const viewInQueueLink = await screen.findByRole("button", { name: /View in queue →/i });
    expect(viewInQueueLink).toBeInTheDocument();

    // Click the link and verify queue status filter changes
    await act(async () => {
      await user.click(viewInQueueLink);
    });

    // Verify the queue status filter is now set to "approval-needed"
    const queueScoped = await getQueuePanel();
    const statusSelect = queueScoped.getByLabelText(/Queue status/i);
    expect(statusSelect).toHaveValue("approval-needed");

    // Verify the queue cluster filter is set to the promoted cluster
    const clusterSelect = queueScoped.getByLabelText(/Cluster filter/i);
    expect(clusterSelect).toHaveValue("cluster-a");

    // Verify the queue section is scrolled into view
    const queueSection = document.getElementById("next-check-queue");
    expect(queueSection).toBeInTheDocument();
  });

  test("view in queue click scrolls to queue section", async () => {
    const payloads = { ...defaultPayloads };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App />);

    await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const promoteButtons = await screen.findAllByRole("button", { name: /Promote to queue/i });
    await act(async () => {
      await user.click(promoteButtons[0]);
    });

    // Wait for promotion success
    await waitFor(() =>
      expect(
        screen.getByText(/Deterministic next check promoted to the queue/i)
      ).toBeInTheDocument()
    );

    // Get the queue section element
    const queueSection = document.getElementById("next-check-queue");
    expect(queueSection).toBeInTheDocument();

    // Mock scrollIntoView on the element
    const scrollMock = vi.fn();
    const originalScrollIntoView = queueSection!.scrollIntoView;
    queueSection!.scrollIntoView = scrollMock;

    const viewInQueueLink = await screen.findByRole("button", { name: /View in queue →/i });

    // Click the link
    await act(async () => {
      await user.click(viewInQueueLink);
    });

    // Verify scrollIntoView was called (this verifies the scroll behavior)
    expect(scrollMock).toHaveBeenCalled();

    // Restore original
    queueSection!.scrollIntoView = originalScrollIntoView;
  });

  test("incident group shows limited checks before expanding", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    const incidentLabel = within(panel!).getAllByText(/Firefight now/i)[0];
    const incidentSection = incidentLabel.closest("section");
    expect(incidentSection).not.toBeNull();
    const incidentItems = within(incidentSection!).getAllByRole("listitem");
    expect(incidentItems.length).toBe(3);
    expect(
      within(incidentSection!).getByRole("button", { name: /Show all 4 incident checks/i })
    ).toBeInTheDocument();
  });

  test("incident show more toggle reveals additional checks", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    const incidentLabel = within(panel!).getAllByText(/Firefight now/i)[0];
    const incidentSection = incidentLabel.closest("section");
    expect(incidentSection).not.toBeNull();
    const showButton = within(incidentSection!).getByRole("button", {
      name: /Show all 4 incident checks/i,
    });
    await act(async () => {
      await userEvent.click(showButton);
    });
    expect(within(incidentSection!).getAllByRole("listitem").length).toBe(4);
    expect(
      within(incidentSection!).getByRole("button", { name: /Show fewer incident checks/i })
    ).toBeInTheDocument();
  });

  test("deterministic panel empty state is obvious when data is absent", async () => {
    const payloads = {
      ...defaultPayloads,
      "/api/run": {
        ...sampleRun,
        deterministicNextChecks: null,
      },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    expect(await screen.findByText(/No deterministic next checks were generated for this run./i)).toBeInTheDocument();
    expect(screen.getByText(/Review cluster detail to inspect evidence-derived work./i)).toBeInTheDocument();
  });

  test("renders next-check queue panel with queue items", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const eyebrow = await screen.findByText(/Next-check queue/i);
    const queuePanel = eyebrow.closest(".next-check-queue-panel");
    expect(queuePanel).not.toBeNull();
    const queueScoped = within(queuePanel!);
    expect(queueScoped.getByRole("heading", { name: /Planner queue/i })).toBeInTheDocument();
    expect(queueScoped.getAllByRole("button", { name: /Approve candidate/i }).length).toBeGreaterThan(0);
    expect(queueScoped.getAllByRole("link", { name: /View latest artifact/i }).length).toBeGreaterThan(0);
  });

  test("queue item details toggle reveals metadata and command preview", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const eyebrow = await screen.findByText(/Next-check queue/i);
    const queuePanel = eyebrow.closest(".next-check-queue-panel");
    expect(queuePanel).not.toBeNull();
    const queueScoped = within(queuePanel!);
    const describeCard = queueScoped
      .getByText(/Describe diag CRD for control plane/i)
      .closest("article");
    expect(describeCard).not.toBeNull();
    const showButton = within(describeCard!).getByRole("button", { name: /Show details/i });
    await act(async () => {
      await user.click(showButton);
    });
    expect(queueScoped.getByText(/Source reason:/i)).toBeInTheDocument();
    expect(queueScoped.getByText(/Command preview/i)).toBeInTheDocument();
    expect(queueScoped.getByText(/Plan artifact/i)).toBeInTheDocument();
    expect(queueScoped.getByText(/kubectl describe diag/i)).toBeInTheDocument();
  });

  test("execution history cards surface result interpretations", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const summaryText = /control-plane errors useful for diagnosing the incident/i;
    expect(await screen.findByText(summaryText)).toBeInTheDocument();
  });

  test("queue details show result interpretation for completed entries", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const queueScoped = await getQueuePanel();
    const logsCard = queueScoped
      .getByText(/Collect kubelet logs for control-plane pods/i)
      .closest("article");
    expect(logsCard).not.toBeNull();
    const showButton = within(logsCard!).getByRole("button", { name: /Show details/i });
    await act(async () => {
      await user.click(showButton);
    });
    expect(
      queueScoped.getByText(/Captured control-plane logs that highlight recent kubelet errors/i)
    ).toBeInTheDocument();
    expect(
      queueScoped.getByText(/Correlate this output with the target incident/i)
    ).toBeInTheDocument();
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

  test("run summary shows empty state when planner data is absent", async () => {
    const payloads = {
      ...defaultPayloads,
      "/api/run": { ...sampleRun, nextCheckPlan: null },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    expect(await screen.findByText(/No next checks generated for this run/i)).toBeInTheDocument();
  });

  test("run summary empty state explains review enrichment not attempted", async () => {
    const reasonText = "Review enrichment was not attempted for this run.";
    const payloads = {
      ...defaultPayloads,
        "/api/run": {
          ...sampleRun,
          nextCheckPlan: null,
          plannerAvailability: {
            status: "enrichment-not-attempted",
            reason: reasonText,
            hint: PLANNER_HINT_TEXT,
            nextActionHint:
              "Inspect Review Enrichment configuration or provider registration to understand why the planner didn't run.",
          },
        },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    expect(await screen.findByText(new RegExp(reasonText, "i"))).toBeInTheDocument();
    expect(screen.getByText(/No next checks generated for this run/i)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(PLANNER_HINT_TEXT, "i"))).toBeInTheDocument();
    expect(
      screen.getByText(
        /Inspect Review Enrichment configuration or provider registration/i
      )
    ).toBeInTheDocument();
  });

  test("run summary empty state explains review enrichment succeeded but no nextChecks", async () => {
    const reasonText = "Review enrichment succeeded but returned no nextChecks.";
    const payloads = {
      ...defaultPayloads,
        "/api/run": {
          ...sampleRun,
          nextCheckPlan: null,
          reviewEnrichment: {
            ...sampleRun.reviewEnrichment!,
            nextChecks: [],
          },
          plannerAvailability: {
            status: "enrichment-succeeded-without-next-checks",
            reason: reasonText,
            hint: PLANNER_HINT_TEXT,
            nextActionHint:
              "Review deterministic Cluster Detail next-checks since enrichment returned no planner candidates.",
          },
        },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    expect(await screen.findByText(new RegExp(reasonText, "i"))).toBeInTheDocument();
    expect(screen.getByText(/No next checks generated for this run/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Review deterministic Cluster Detail next-checks/i)
    ).toBeInTheDocument();
  });

  test("review next checks button opens the cluster detail panel", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const reviewButton = await screen.findByRole("button", { name: /Review next checks/i });
    await act(async () => {
      await user.click(reviewButton);
    });

    const details = screen.getByText(/Tap to expand findings/i).closest("details");
    expect(details).not.toBeNull();
    expect(details).toHaveAttribute("open");
    expect(await screen.findByRole("heading", { name: /Next check plan/i })).toBeInTheDocument();
  });

  test("renders stale and orphaned approvals", async () => {
    const staleCandidates = sampleNextCheckCandidates.map((candidate) =>
      candidate.candidateId === "candidate-describe"
        ? { ...candidate, approvalStatus: "approval-stale" }
        : candidate
    );
    const orphanedApprovals = [
      {
        approvalStatus: "approval-orphaned",
        candidateId: "orphaned-candidate",
        candidateIndex: 5,
        candidateDescription: "Inspect orphaned candidate",
        targetCluster: "cluster-b",
        planArtifactPath: "/artifacts/old-plan.json",
        approvalArtifactPath: "/artifacts/orphan-approval.json",
        approvalTimestamp: "2026-04-06T11:30:00Z",
      },
    ];
    const runWithOrphaned = {
      ...sampleRun,
      nextCheckPlan: {
        ...sampleRun.nextCheckPlan,
        candidates: staleCandidates,
        orphanedApprovals,
      },
    };
    const detailWithStale = {
      ...sampleClusterDetail,
      nextCheckPlan: staleCandidates,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/run": runWithOrphaned,
      "/api/cluster-detail": detailWithStale,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const heading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planPanel = heading.closest(".next-check-plan");
    expect(planPanel).not.toBeNull();
    const scoped = within(planPanel!);
    expect(scoped.getByText(/Approval stale/i)).toBeInTheDocument();
    expect(scoped.getByText(/Orphaned approvals/i)).toBeInTheDocument();
  });

  test("displays run button only for allowed next-check candidates", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const heading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planPanel = heading.closest(".next-check-plan");
    expect(planPanel).not.toBeNull();
    const buttons = within(planPanel!).getAllByRole("button", { name: /Run candidate/i });
    expect(buttons.length).toBe(1);
  });

    test("manual execution button triggers API and shows artifact link", async () => {
        const executionResponse = {
            status: "success",
            summary: "Manual execution recorded",
      artifactPath: "external-analysis/run-123-next-check-execution-0.json",
      durationMs: 150,
      command: ["kubectl", "logs"],
      targetCluster: "cluster-a",
      planCandidateIndex: 0,
      rawOutput: "logs output",
      errorSummary: null,
    };
    const fetchMock = vi.fn((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;
      if (url === "/api/next-check-execution" && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve(executionResponse),
        });
      }
      const base = url.split("?")[0];
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const planHeading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planPanel = planHeading.closest(".next-check-plan");
    expect(planPanel).not.toBeNull();
    const runButton = within(planPanel!).getByRole("button", { name: /Run candidate/i });
    await act(async () => {
      await user.click(runButton);
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/next-check-execution",
      expect.objectContaining({ method: "POST" })
    );
    const executionCall = fetchMock.mock.calls.find(
      ([input]) => typeof input === "string" && input === "/api/next-check-execution"
    );
    expect(executionCall).toBeTruthy();
    const executionInit = executionCall![1] as RequestInit;
    const executionBody = JSON.parse(executionInit.body as string);
    expect(executionBody.candidateId).toBe("candidate-logs");
    expect(executionBody.candidateIndex).toBe(0);
    const successMessages = await within(planPanel!).findAllByText(/Manual execution recorded/i);
    expect(successMessages.length).toBeGreaterThan(0);
    const manualActions = successMessages[0].closest(".next-check-manual-actions");
    expect(manualActions).not.toBeNull();
    const artifactLink = within(manualActions!).getByRole("link", { name: /View artifact/i });
    expect(artifactLink).toHaveAttribute(
      "href",
      expect.stringContaining("external-analysis%2Frun-123-next-check-execution-0.json")
    );
  });

    test("approve candidate button calls API and shows approval record", async () => {
        const approvalResponse = {
            status: "success",
            summary: "Candidate approved",
            artifactPath: "external-analysis/approval-0.json",
            durationMs: 10,
            candidateIndex: 1,
            approvalTimestamp: "2026-04-06T12:01:00Z",
        };
    const fetchMock = vi.fn((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.url;
      if (url === "/api/next-check-approval" && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve(approvalResponse),
        });
      }
      const base = url.split("?")[0];
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const planHeading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planPanel = planHeading.closest(".next-check-plan");
    expect(planPanel).not.toBeNull();
    const approveButton = within(planPanel!).getByRole("button", { name: /Approve candidate/i });
    await act(async () => {
      await user.click(approveButton);
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/next-check-approval",
      expect.objectContaining({ method: "POST" })
    );
    const approvalCall = fetchMock.mock.calls.find(
      ([input]) => typeof input === "string" && input === "/api/next-check-approval"
    );
    expect(approvalCall).toBeTruthy();
    const approvalInit = approvalCall![1] as RequestInit;
    const approvalBody = JSON.parse(approvalInit.body as string);
    expect(approvalBody.candidateId).toBe("candidate-describe");
    expect(approvalBody.candidateIndex).toBe(1);
    const approvalMessage = await within(planPanel!).findByText(/Candidate approved/i);
    expect(approvalMessage).toBeInTheDocument();
    const approvalLink = within(planPanel!).getByRole("link", { name: /View approval record/i });
    expect(approvalLink).toHaveAttribute("href", expect.stringContaining("external-analysis/approval-0.json"));
  });

  test("renders execution history entries from the run payload", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const panel = await screen.findByRole("heading", { name: /Manual next-check runs/i });
    expect(panel).toBeInTheDocument();
    expect(screen.getByText(/Manual next-check runs/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Collect kubelet logs for control-plane pods/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Timed out/i, { selector: ".execution-history-badge" })).toBeInTheDocument();
  });

  test("execution history follow-up block surfaces retry guidance", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    expect(await screen.findByText(/Retry candidate/i)).toBeInTheDocument();
  });

  test("queue details expose follow-up guidance for failed executions", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const queueCard = await screen.findByText(/Inspect etcd leader/i);
    const queueArticle = queueCard.closest("article");
    expect(queueArticle).not.toBeNull();
    const showDetails = within(queueArticle!).getByRole("button", { name: /Show details/i });
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

    // Verify the title/reason block exists (left column content)
    const titleBlock = within(queueCard!).getByText(/Describe diag CRD for control plane/i);
    expect(titleBlock).toBeInTheDocument();

    // Verify the "Why this check" label exists (part of the left column)
    expect(within(queueCard!).getByText(/Why this check:/i)).toBeInTheDocument();

    // Verify the status block exists (right column: Approval, Execution, Outcome)
    const statusBlock = queueCard!.querySelector(".next-check-queue-item-status");
    expect(statusBlock).not.toBeNull();
    expect(within(statusBlock!).getByText(/Approval:/i)).toBeInTheDocument();
    expect(within(statusBlock!).getByText(/Execution:/i)).toBeInTheDocument();
    expect(within(statusBlock!).getByText(/Outcome:/i)).toBeInTheDocument();

    // Verify the status block is a separate DOM element from the title
    // The status block should be a sibling to the left content div, not nested inside it
    const metaContainer = within(queueCard!).getByText(/Why this check:/i).closest(".next-check-queue-item-meta");
    expect(metaContainer).not.toBeNull();

    // The meta container should have two direct children: the left content div and the status div
    const metaChildren = metaContainer!.children;
    expect(metaChildren.length).toBe(2);

    // First child should contain the title/reason (left column)
    const leftColumn = metaChildren[0];
    expect(leftColumn.textContent).toContain("Describe diag CRD");
    expect(leftColumn.textContent).toContain("Why this check:");

    // Second child should be the status block (right column)
    const rightColumn = metaChildren[1];
    expect(rightColumn.className).toContain("next-check-queue-item-status");
  });

  test("hides next check plan section when planner data is absent", async () => {
    const noPlanCluster = { ...sampleClusterDetail, nextCheckPlan: [] };
    const runWithoutPlan = { ...sampleRun, nextCheckPlan: null };
    const payloads = {
      ...defaultPayloads,
      "/api/cluster-detail": noPlanCluster,
      "/api/run": runWithoutPlan,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    expect(screen.queryByRole("heading", { name: /Next check plan/i })).toBeNull();
  });

  test("renders compact run stats string", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(
      screen.getByText("Last 32s · Runs 12 · P50 24s · P95 48s · P99 1m 4s")
    ).toBeInTheDocument();
    expect(screen.getByText(/Run LLM calls:/i)).toBeInTheDocument();
    expect(screen.getByText(/Historical LLM calls:/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Providers: k8sgpt 2 \(0 failed\) · default 1 \(1 failed\)/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Retained history stats/i)).toBeInTheDocument();
    expect(screen.getByText(/Current run/i)).toBeInTheDocument();
    expect(screen.getAllByText(/ID run-123/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/(Fresh|Stale) data/i, { selector: ".freshness-pill" })
    ).toBeInTheDocument();
    expect(screen.getByText(/LLM telemetry/i)).toBeInTheDocument();
    expect(screen.getByText(/Collector collector:v1.2.0/i)).toBeInTheDocument();
  });

  test("renders llm policy block with budget details", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /LLM policy/i });
    expect(heading).toBeInTheDocument();
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    const scoped = within(panel!);
    expect(scoped.getByText(/Provider/i)).toBeInTheDocument();
    expect(scoped.getByText(/Budget status/i)).toBeInTheDocument();
    expect(scoped.getByText(/Within budget/i)).toBeInTheDocument();
    expect(scoped.getByText(/Used this run/i)).toBeInTheDocument();
  });

  test("renders review enrichment panel status message", async () => {
    const pendingRun = {
      ...sampleRun,
      reviewEnrichment: undefined,
      reviewEnrichmentStatus: undefined,
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        ...defaultPayloads,
        "/api/run": pendingRun,
      })
    );
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(heading).toBeInTheDocument();
    expect(
      await screen.findByText(/Provider-assisted review enrichment is not configured for this run/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Provider unspecified/i)).toBeInTheDocument();
  });

  test("shows review enrichment status when enrichment is disabled", async () => {
    const disabledRun = {
      ...sampleRun,
      reviewEnrichment: undefined,
      reviewEnrichmentStatus: {
        status: "policy-disabled",
        reason: "Review enrichment is disabled in the current configuration.",
        provider: null,
        policyEnabled: false,
        providerConfigured: false,
        adapterAvailable: null,
        runEnabled: false,
        runProvider: null,
      },
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        ...defaultPayloads,
        "/api/run": disabledRun,
      })
    );
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(heading).toBeInTheDocument();
    expect(
      screen.getByText(/Review enrichment is disabled in the current configuration/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Provider unspecified/i)).toBeInTheDocument();
  });

  test("renders awaiting-next-run status when run metadata lags", async () => {
    const awaitingRun = {
      ...sampleRun,
      reviewEnrichment: undefined,
      reviewEnrichmentStatus: {
        status: "awaiting-next-run",
        reason: "Awaiting a run that has enrichment enabled.",
        provider: "k8sgpt",
        policyEnabled: true,
        providerConfigured: true,
        adapterAvailable: true,
        runEnabled: false,
        runProvider: "old-provider",
      },
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        ...defaultPayloads,
        "/api/run": awaitingRun,
      })
    );
    render(<App />);

    await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(
      screen.getByText(/Awaiting a run that has enrichment enabled./i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Provider k8sgpt · Run configuration disabled review enrichment/i)
    ).toBeInTheDocument();
  });

  test("shows provider name when run config enabled review enrichment", async () => {
    const providerRun = {
      ...sampleRun,
      reviewEnrichment: undefined,
      reviewEnrichmentStatus: {
        status: "not-attempted",
        reason: "Review enrichment has not yet run for this run.",
        provider: null,
        policyEnabled: true,
        providerConfigured: true,
        adapterAvailable: true,
        runEnabled: true,
        runProvider: "llamacpp",
      },
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        ...defaultPayloads,
        "/api/run": providerRun,
      })
    );
    render(<App />);

    await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(screen.getByText(/Provider llamacpp/i)).toBeInTheDocument();
    expect(screen.getByText(/Run configuration enabled \(llamacpp\)/i)).toBeInTheDocument();
  });

  test("renders review enrichment details when enrichment data exists", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(screen.getByText(/Review enrichment reshaped the triage order/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Provider k8sgpt/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: /View enrichment artifact/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Provider-assisted review enrichment is not configured/i)
    ).toBeNull();
    expect(screen.queryByText(/Provider unspecified/i)).toBeNull();
  });

  test("renders provider execution panel", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Provider-assisted advisory/i });
    const executionHeading = await screen.findByText(/Provider execution/i);
    const executionPanel = executionHeading.closest("section");
    const scoped = within(executionPanel!);
    expect(scoped.getByText(/Provider execution/i)).toBeInTheDocument();
    expect(scoped.getByText(/Auto drilldown/i)).toBeInTheDocument();
    expect(scoped.getByText(/eligible 2/i)).toBeInTheDocument();
    const attemptedMatches = scoped.getAllByText(/attempted 1/i);
    expect(attemptedMatches.length).toBeGreaterThanOrEqual(1);
    const reviewMatches = scoped.getAllByText(/Review enrichment/i);
    expect(reviewMatches[0]).toBeInTheDocument();
  });

  test("renders diagnostic pack review panel when data exists", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Automated review insights/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText(/Review detected ranking mismatches/i)).toBeInTheDocument();
    expect(screen.getByText(/Major disagreements · 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing checks · 2/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Provider k8sgpt validated the review and provided metadata./i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Provider flagged suspected drift misprioritization/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /View diagnostic pack review artifact/i })
    ).toBeInTheDocument();
  });

  test("renders run diagnostic pack download link when run artifact is present", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Run diagnostic package archive/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText(/Run 123 pack/i)).toBeInTheDocument();
    expect(screen.getByText(/Apr 6, 2026 12:01 UTC/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Download diagnostic pack/i })
    ).toHaveAttribute("href", expect.stringContaining("run-123-diagnostic-pack.zip"));
  });

  test("diagnostic pack review panel surfaces provider error details", async () => {
    const runWithError = {
      ...sampleRun,
      diagnosticPackReview: makeDiagnosticPackReview({
        providerErrorSummary: "Timeout contacting adapter",
        providerStatus: "error",
        majorDisagreements: ["Erroring provider"],
      }),
    };
    const payloads = { ...defaultPayloads, "/api/run": runWithError };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Automated review insights/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText(/Timeout contacting adapter/i)).toBeInTheDocument();
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    expect(within(panel!).getByText(/^error$/i)).toHaveClass("status-pill");
    expect(screen.getByText(/Major disagreements · 1/i)).toBeInTheDocument();
  });

  test("diagnostic pack review panel handles skip-state with empty lists", async () => {
    const runWithSkip = {
      ...sampleRun,
      diagnosticPackReview: makeDiagnosticPackReview({
        majorDisagreements: [],
        missingChecks: [],
        rankingIssues: [],
        recommendedNextActions: [],
        providerStatus: null,
        providerSkipReason: "Provider intentionally skipped for this run",
        providerSummary: null,
        providerErrorSummary: null,
      }),
    };
    const payloads = { ...defaultPayloads, "/api/run": runWithSkip };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Automated review insights/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.queryByText(/Provider unspecified/i)).toBeNull();
    expect(screen.getByText(/Provider intentionally skipped for this run/i)).toBeInTheDocument();
    expect(screen.queryByText(/Major disagreements ·/i)).toBeNull();
    expect(screen.queryByText(/Missing checks ·/i)).toBeNull();
    expect(screen.queryByText(/Recommended next actions/i)).toBeNull();
  });

  test("hides diagnostic pack review panel when the payload is missing", async () => {
    const payloads = {
      ...defaultPayloads,
      "/api/run": {
        ...sampleRun,
        diagnosticPackReview: null,
      },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Provider-assisted advisory/i });
    expect(screen.queryByText(/Automated review insights/i)).toBeNull();
    expect(screen.queryByText(/Major disagreements/i)).toBeNull();
  });

  test("renders llm activity panel and filters entries", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const panelHeading = await screen.findByRole("heading", { name: /LLM activity/i });
    const notificationMatches = await screen.findAllByText(
      sampleClusterDetail.relatedNotifications[0].summary
    );
    expect(notificationMatches.length).toBeGreaterThan(0);
    expect(screen.getByText(/Retained entries: 19/i)).toBeInTheDocument();
    const panelSection = panelHeading.closest("section");
    expect(panelSection).not.toBeNull();
    const statusSelect = within(panelSection!).getByLabelText(/Status/i);
    await act(async () => {
      await user.selectOptions(statusSelect, "failed");
    });
    expect(await within(panelSection!).findByText(/timeout/i)).toBeInTheDocument();
  });

  test("renders notification history table and pagination summary", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);
    const heading = await screen.findByRole("heading", { name: /Notification history/i });
    expect(heading).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: /Notification history table/i });
    expect(within(table).getByText(sampleNotifications.notifications[0].summary)).toBeInTheDocument();
    await screen.findAllByTestId("notification-row");
    expect(within(table).getAllByTestId("notification-row")).toHaveLength(1);
    expect(screen.getAllByText(/Showing 1–1 of 1/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/50 per page/i)).toBeInTheDocument();
  });

  test("sorts notifications newest first", async () => {
    const orderedNotifications = [
      buildNotificationEntry(0, { summary: "Newest", timestamp: "2026-04-06T12:00:00Z" }),
      buildNotificationEntry(1, { summary: "Older", timestamp: "2026-04-06T11:00:00Z" }),
    ];
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": {
        notifications: orderedNotifications,
        total: orderedNotifications.length,
        page: 1,
        limit: 50,
        total_pages: 1,
      },
      "/api/notifications?limit=50&page=1": {
        notifications: orderedNotifications,
        total: orderedNotifications.length,
        page: 1,
        limit: 50,
        total_pages: 1,
      },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);
    const table = await screen.findByRole("table", { name: /Notification history table/i });
    const rows = within(table).getAllByTestId("notification-row");
    expect(within(rows[0]).getByText("Newest")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Older")).toBeInTheDocument();
  });

  test("paginates notification history after 50 rows", async () => {
    const manyNotifications = buildNotificationList(60);
    const pageOne = {
      notifications: manyNotifications.slice(0, 50),
      total: manyNotifications.length,
      page: 1,
      limit: 50,
      total_pages: 2,
    };
    const pageTwo = {
      notifications: manyNotifications.slice(50),
      total: manyNotifications.length,
      page: 2,
      limit: 50,
      total_pages: 2,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": pageOne,
      "/api/notifications?limit=50&page=1": pageOne,
      "/api/notifications?limit=50&page=2": pageTwo,
    };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    await waitFor(() => expect(screen.getByText(/Page 1 of 2/i)).toBeInTheDocument());
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("limit=50&page=1");
    })).toBe(true);
    const nextButton = screen.getByRole("button", { name: /Next notifications page/i });
    expect(nextButton).not.toBeDisabled();
    await act(async () => {
      await user.click(nextButton);
    });
    await waitFor(() => expect(screen.getByText(/Page 2 of 2/i)).toBeInTheDocument());
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("/api/notifications?limit=50&page=2");
    })).toBe(true);
    const pageTwoRows = await screen.findAllByTestId("notification-row");
    expect(pageTwoRows).toHaveLength(10);
    const prevButton = screen.getByRole("button", { name: /Previous notifications page/i });
    expect(prevButton).not.toBeDisabled();
    await act(async () => {
      await user.click(prevButton);
    });
    await waitFor(() => expect(screen.getByText(/Page 1 of 2/i)).toBeInTheDocument());
    expect(fetchMock.mock.calls.filter(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("page=1");
    }).length).toBeGreaterThanOrEqual(2);
  });

  test("pagination remains single-page when server reports only one page", async () => {
    const limitedNotifications = buildNotificationList(30);
    const payload = {
      notifications: limitedNotifications,
      total: limitedNotifications.length,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": payload,
      "/api/notifications?limit=50&page=1": payload,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    await screen.findAllByTestId("notification-row");
    await screen.findByRole("option", { name: /Warning/i });
    expect(screen.getByText(/Page 1 of 1/i)).toBeInTheDocument();
    const nextButton = screen.getByRole("button", { name: /Next notifications page/i });
    expect(nextButton).toBeDisabled();
    expect(screen.getByRole("button", { name: /Previous notifications page/i })).toBeDisabled();
  });

  test("filters notification history table by kind, cluster, and search", async () => {
    const customNotifications = [
      buildNotificationEntry(0, {
        kind: "Warning",
        summary: "CPU spike on alpha",
        runId: "run-alpha",
        clusterLabel: "cluster-alpha",
        details: [{ label: "Confidence", value: "High" }],
      }),
      buildNotificationEntry(1, {
        kind: "Info",
        summary: "Routine health report",
        runId: "run-beta",
        clusterLabel: "cluster-beta",
      }),
      buildNotificationEntry(2, {
        kind: "Warning",
        summary: "Memory pressure on beta",
        runId: "run-zeta",
        clusterLabel: "cluster-beta",
        details: [{ label: "Target", value: "db" }],
      }),
    ];
    const basePayload = {
      notifications: customNotifications,
      total: 3,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const warningPayload = {
      notifications: customNotifications.filter((entry) => entry.kind === "Warning"),
      total: 2,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const clusterPayload = {
      notifications: customNotifications.filter(
        (entry) => entry.clusterLabel === "cluster-beta" && entry.kind === "Warning"
      ),
      total: 1,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const searchPayload = {
      notifications: customNotifications.filter(
        (entry) => entry.summary.includes("Memory") || entry.details.some((detail) => detail.value === "db")
      ),
      total: 1,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": basePayload,
      "/api/notifications?limit=50&page=1": basePayload,
      "/api/notifications?kind=Warning&limit=50&page=1": warningPayload,
      "/api/notifications?kind=Warning&cluster_label=cluster-beta&limit=50&page=1": clusterPayload,
      "/api/notifications?kind=Warning&cluster_label=cluster-beta&search=memory&limit=50&page=1":
        searchPayload,
    };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(3));
    const kindSelect = screen.getByRole("combobox", {
      name: /Notification kind filter/i,
    });
    await screen.findByRole("option", { name: /Warning/i });
    const clusterSelect = screen.getByRole("combobox", {
      name: /Notification cluster filter/i,
    });
    const searchInput = screen.getByRole("searchbox", {
      name: /Notification text search/i,
    });
    await act(async () => {
      await user.selectOptions(kindSelect, "Warning");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(2));
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("/api/notifications?kind=Warning");
    })).toBe(true);
    await act(async () => {
      await user.selectOptions(clusterSelect, "cluster-beta");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(1));
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("cluster_label=cluster-beta");
    })).toBe(true);
    await act(async () => {
      await user.type(searchInput, "memory");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(1));
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("search=memory");
    })).toBe(true);
    expect(screen.getAllByText(/Showing 1–1 of 1/i).length).toBeGreaterThan(0);
    expect(
      await screen.findByText(/Run run-zeta · Cluster cluster-beta/i)
    ).toBeInTheDocument();
  });

  test("pagination summary updates when filters reduce the dataset", async () => {
    const manyNotifications = buildNotificationList(60);
    const basePayload = {
      notifications: manyNotifications.slice(0, 50),
      total: manyNotifications.length,
      page: 1,
      limit: 50,
      total_pages: 2,
    };
    const searchPayload = {
      notifications: manyNotifications.slice(0, 30),
      total: 30,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": basePayload,
      "/api/notifications?search=Entry&limit=50&page=1": searchPayload,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    expect(screen.getByText(/Page 1 of 1/i)).toBeInTheDocument();
    const searchInput = screen.getByRole("searchbox", {
      name: /Notification text search/i,
    });
    await act(async () => {
      await user.type(searchInput, "Entry");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(30));
    expect(screen.getByText(/Page 1 of 1/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Showing 1–30 of 30/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Next notifications page/i })).toBeDisabled();
  });

  test("autorefresh dropdown persists selection and disables timer", async () => {
    localStorage.setItem(AUTOREFRESH_STORAGE_KEY, "30");
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    const select = await screen.findByLabelText(/auto refresh/i);
    expect(select).toHaveValue("30");
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 30000);

    await act(async () => {
      await user.selectOptions(select, "off");
    });
    await waitFor(() => expect(localStorage.getItem(AUTOREFRESH_STORAGE_KEY)).toBe("off"));
    await waitFor(() => expect(clearIntervalSpy).toHaveBeenCalled());
    await screen.findByText(/Auto refresh is off/i);
  });

  test("shows loading and surfaces API errors", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network boom"))));
    render(<App />);

    expect(screen.getByText(/Loading operator data/i)).toBeInTheDocument();
    await screen.findByText(/network boom/i);
  });
});
