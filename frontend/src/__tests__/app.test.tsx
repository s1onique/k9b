import { act, render, screen, waitFor, within } from "@testing-library/react";
import dayjs from "dayjs";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { AUTOREFRESH_STORAGE_KEY, QUEUE_VIEW_STORAGE_KEY } from "../App";
import type { NotificationEntry } from "../types";

const minsAgo = (minutes: number) => dayjs().subtract(minutes, "minute").toISOString();

import {
  createFetchMock,
  createStorageMock,
  makeDiagnosticPackReview,
  makeRunWithOverrides,
  sampleClusterDetail,
  sampleFleet,
  sampleNextCheckCandidates,
  sampleNotifications,
  sampleProposals,
  sampleRun,
  sampleRunsList,
  UI_STRINGS,
} from "./fixtures";

const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/runs": sampleRunsList,
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

// Local fetch mock for tests that need custom payloads
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
    expect(scoped.getAllByText(UI_STRINGS.queueStatus.safeCandidate, { exact: false }).length).toBeGreaterThan(0);
    expect(scoped.getByText(UI_STRINGS.queueStatus.approvalNeeded, { exact: false })).toBeInTheDocument();
    expect(scoped.getByText(UI_STRINGS.gating.commandNotRecognized, { exact: false })).toBeInTheDocument();
    expect(
      scoped.getByText(
        UI_STRINGS.gating.matchesDeterministicNextCheck("Collect kubelet metrics"),
        { exact: false }
      )
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
    const unreviewedPills = screen.getAllByText("unreviewed");
    expect(unreviewedPills.length).toBeGreaterThan(0);
    const partiallyReviewedPills = screen.getAllByText("partially-reviewed");
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

    // Test "no-executions" filter button - should show runs with no executions
    // From fixtures: run-120 (reviewStatus: "no-executions") = 1 run
    // The filter buttons are in order: All runs, No executions yet, Awaiting review, etc.
    const noExecutionsFilterButton = document.querySelectorAll(".runs-filter-button")[1] as HTMLButtonElement;
    await act(async () => {
      await user.click(noExecutionsFilterButton);
    });
    let filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(1);

    // Test "Awaiting review" filter - should show runs with reviewStatus "unreviewed"
    // From fixtures: run-122 (reviewStatus: "unreviewed") = 1 run
    const awaitingReviewFilter = document.querySelectorAll(".runs-filter-button")[2] as HTMLButtonElement;
    await act(async () => {
      await user.click(awaitingReviewFilter);
    });
    filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(1);
    expect(screen.getByText(/Showing 1 of 4/)).toBeInTheDocument();

    // Test "all" filter button - should show all runs again, no summary text
    const allFilterButton = document.querySelectorAll(".runs-filter-button")[0] as HTMLButtonElement;
    await act(async () => {
      await user.click(allFilterButton);
    });
    filteredItems = document.querySelectorAll(".run-row");
    expect(filteredItems.length).toBe(4);
  });

  test("recent-runs review download link uses /artifact endpoint not /api/artifacts", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Find the recent runs panel and ensure "All runs" filter is active
    await screen.findAllByText(/Recent runs/i)[0];
    const allFilterButton = document.querySelectorAll(".runs-filter-button")[0] as HTMLButtonElement;
    if (allFilterButton) {
      await act(async () => {
        await user.click(allFilterButton);
      });
    }

    // Wait for the run rows to appear
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the download link - it's in the Review column
    // The fixture has run-122 with reviewDownloadPath set
    const downloadLinks = document.querySelectorAll(".run-row a.btn");
    expect(downloadLinks.length).toBeGreaterThan(0);

    // Check that the href contains /artifact?path= and not /api/artifacts
    const downloadLink = downloadLinks[0] as HTMLAnchorElement;
    const href = downloadLink.href;
    expect(href).toContain("/artifact?path=");
    expect(href).not.toContain("/api/artifacts");
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
    // Updated wording: "candidate check to review and promote"
    expect(screen.getByText(/candidate check.*to review and promote/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review cluster detail/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View assessment artifact/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Firefight now/i).length).toBeGreaterThan(0);
    const driftNodes = screen.getAllByText(/Drift \/ toil follow-up/i);
    expect(driftNodes.length).toBeGreaterThan(0);
    // Drift bucket is closed by default when degraded clusters exist
    // (sampleFleet has cluster-a as Degraded, so drift bucket should be collapsed)
    const driftDetails = driftNodes[0].closest("details");
    expect(driftDetails).not.toHaveAttribute("open");
  });

  test("drift bucket is collapsed during active degraded runs", async () => {
    // sampleFleet has 1 degraded cluster (cluster-a is "Degraded")
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();

    // Find the drift bucket
    const driftNodes = screen.getAllByText(/Drift \/ toil follow-up/i);
    expect(driftNodes.length).toBeGreaterThan(0);

    const driftDetails = driftNodes[0].closest("details") as HTMLElement;
    expect(driftDetails).not.toBeNull();

    // During active degraded run (sampleFleet has degraded cluster), drift bucket should be collapsed
    expect(driftDetails).not.toHaveAttribute("open");

    // Verify drift items still exist in the DOM (not removed)
    // "Compare baseline release parity" is a drift workstream check from fixtures
    expect(panel!.textContent).toContain("Compare baseline release parity");
  });

  test("drift bucket is expanded by default when no degraded clusters exist", async () => {
    // Create a fleet with no degraded clusters
    const healthyFleet = JSON.parse(JSON.stringify(sampleFleet));
    healthyFleet.fleetStatus = {
      ratingCounts: [
        { rating: "healthy", count: 2 },
        { rating: "degraded", count: 0 },
      ],
      degradedClusters: [],
    };

    const payloads = { ...defaultPayloads, "/api/fleet": healthyFleet };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();

    // Find the drift bucket
    const driftNodes = screen.getAllByText(/Drift \/ toil follow-up/i);
    expect(driftNodes.length).toBeGreaterThan(0);

    const driftDetails = driftNodes[0].closest("details") as HTMLElement;
    expect(driftDetails).not.toBeNull();

    // When no degraded clusters, drift bucket should be expanded by default
    expect(driftDetails).toHaveAttribute("open");

    // Verify drift items are visible
    // "Compare baseline release parity" is a drift workstream check from fixtures
    expect(within(driftDetails).getByText(/Compare baseline release parity/i)).toBeInTheDocument();
  });

  test("drift bucket can be manually expanded by the operator", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Find the deterministic panel first
    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();

    // Find the drift bucket within the panel
    const driftDetails = panel!.querySelector("details.deterministic-group--drift") as HTMLElement;
    expect(driftDetails).not.toBeNull();

    // Initially should be collapsed (degraded cluster exists)
    expect(driftDetails).not.toHaveAttribute("open");

    // Click the summary to expand
    const summaryElement = driftDetails.querySelector("summary") as HTMLElement;
    await act(async () => {
      await user.click(summaryElement);
    });

    // Now it should be expanded
    expect(driftDetails).toHaveAttribute("open");

    // Drift items should be visible
    expect(within(driftDetails).getByText(/Compare baseline release parity/i)).toBeInTheDocument();
  });

  test("promote deterministic next check button triggers API and shows status", async () => {
    const payloads = { ...defaultPayloads };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const promoteButtons = await screen.findAllByRole("button", { name: /Add to work list/i });
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
    const promoteButtons = await screen.findAllByRole("button", { name: /Add to work list/i });
    await act(async () => {
      await user.click(promoteButtons[0]);
    });

    // Wait for promotion success message
    await waitFor(() =>
      expect(
        screen.getByText(/Deterministic next check promoted to the queue/i)
      ).toBeInTheDocument()
    );

    // Verify "View in work list →" link is present
    const viewInQueueLink = await screen.findByRole("button", { name: /View in work list →/i });
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
    const promoteButtons = await screen.findAllByRole("button", { name: /Add to work list/i });
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

    const viewInQueueLink = await screen.findByRole("button", { name: /View in work list →/i });

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

  test("all three workstream bucket headings render when deterministic checks exist", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();

    // All three workstream headings must be present
    expect(within(panel!).getAllByText(/Firefight now/i).length).toBeGreaterThan(0);
    expect(within(panel!).getAllByText(/Evidence gathering/i).length).toBeGreaterThan(0);
    expect(within(panel!).getAllByText(/Drift \/ toil follow-up/i).length).toBeGreaterThan(0);
  });

  test("workstream bucket counts are shown per bucket", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();

    // Find each workstream bucket section and verify the count label appears within it
    // Incident bucket - section with class "deterministic-group" (first one)
    const incidentSection = panel!.querySelector("section.deterministic-group");
    expect(incidentSection).not.toBeNull();
    const incidentHeadDiv = incidentSection!.querySelector(".deterministic-group-head");
    expect(incidentHeadDiv).not.toBeNull();
    expect(within(incidentHeadDiv!).getByText(/Firefight now/i)).toBeInTheDocument();
    expect(incidentHeadDiv!.textContent).toMatch(/\d+ check/);

    // Evidence bucket - section with class "deterministic-group" (second one)
    const evidenceSection = panel!.querySelectorAll("section.deterministic-group")[1];
    expect(evidenceSection).not.toBeNull();
    const evidenceHeadDiv = evidenceSection.querySelector(".deterministic-group-head");
    expect(evidenceHeadDiv).not.toBeNull();
    expect(within(evidenceHeadDiv!).getByText(/Evidence gathering/i)).toBeInTheDocument();
    expect(evidenceHeadDiv!.textContent).toMatch(/\d+ check/);

    // Drift bucket - details element with class "deterministic-group--drift"
    const driftDetails = panel!.querySelector("details.deterministic-group--drift");
    expect(driftDetails).not.toBeNull();
    const driftHeadDiv = driftDetails!.querySelector(".deterministic-group-head");
    expect(driftHeadDiv).not.toBeNull();
    expect(within(driftHeadDiv!).getByText(/Drift \/ toil follow-up/i)).toBeInTheDocument();
    expect(driftHeadDiv!.textContent).toMatch(/\d+ check/);
  });

  test("evidence cards appear in the correct workstream bucket", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();

    // Find the incident bucket and verify incident checks appear there
    const incidentLabel = within(panel!).getAllByText(/Firefight now/i)[0];
    const incidentSection = incidentLabel.closest("section");
    expect(incidentSection).not.toBeNull();
    // "Capture tcpdump" is an incident workstream check from fixtures
    expect(within(incidentSection!).getByText(/Capture tcpdump/i)).toBeInTheDocument();

    // Find the evidence bucket and verify evidence check appears there
    const evidenceLabel = within(panel!).getAllByText(/Evidence gathering/i)[0];
    const evidenceSection = evidenceLabel.closest("section");
    expect(evidenceSection).not.toBeNull();
    // "Collect kubelet metrics from nodes" is an evidence workstream check from fixtures
    expect(within(evidenceSection!).getByText(/Collect kubelet metrics from nodes/i)).toBeInTheDocument();

    // Find the drift bucket (it's a <details> element)
    const driftLabel = within(panel!).getAllByText(/Drift \/ toil follow-up/i)[0];
    const driftSection = driftLabel.closest("details");
    expect(driftSection).not.toBeNull();
    // "Compare baseline release parity" is a drift workstream check from fixtures
    expect(within(driftSection!).getByText(/Compare baseline release parity/i)).toBeInTheDocument();
  });

  test("empty workstream bucket shows empty state message", async () => {
    // Build a payload with only incident workstream checks
    const runWithIncidentOnly = JSON.parse(JSON.stringify(sampleRun));
    if (runWithIncidentOnly.deterministicNextChecks) {
      runWithIncidentOnly.deterministicNextChecks.clusters.forEach((cluster: { deterministicNextCheckSummaries?: Array<{ workstream: string }> }) => {
        if (cluster.deterministicNextCheckSummaries) {
          cluster.deterministicNextCheckSummaries.forEach((check: { workstream: string }) => {
            check.workstream = "incident";
          });
        }
      });
    }
    const payloads = { ...defaultPayloads, "/api/run": runWithIncidentOnly };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /Deterministic next checks/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();

    // Incident bucket should have checks
    const incidentLabel = within(panel!).getAllByText(/Firefight now/i)[0];
    const incidentSection = incidentLabel.closest("section");
    expect(incidentSection).not.toBeNull();
    const incidentItems = within(incidentSection!).getAllByRole("listitem");
    expect(incidentItems.length).toBeGreaterThan(0);

    // Evidence bucket should show empty state
    const evidenceLabel = within(panel!).getAllByText(/Evidence gathering/i)[0];
    const evidenceSection = evidenceLabel.closest("section");
    expect(evidenceSection).not.toBeNull();
    expect(within(evidenceSection!).getByText(/No evidence gathering checks/i)).toBeInTheDocument();
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

    // Updated wording: "No evidence-based checks" and "Review the cluster detail for evidence-based checks to promote"
    expect(await screen.findByText(/No evidence-based checks are available/i)).toBeInTheDocument();
    expect(screen.getByText(/Review the cluster detail for evidence-based checks to promote/i)).toBeInTheDocument();
  });

  test("renders next-check queue panel with queue items", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const eyebrow = await screen.findByText(/Next-check queue/i);
    const queuePanel = eyebrow.closest(".next-check-queue-panel");
    expect(queuePanel).not.toBeNull();
    const queueScoped = within(queuePanel!);
    expect(queueScoped.getByRole("heading", { name: /Work list/i })).toBeInTheDocument();
    expect(queueScoped.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
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
    const showButton = within(describeCard!).getByRole("button", { name: /More/i });
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
    const showButton = within(logsCard!).getByRole("button", { name: /More/i });
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
    expect(within(approvalCard!).getByText(/Approval required before execution/i)).toBeInTheDocument();
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
    expect(queueScoped.queryByText(/Approval required before execution/i)).toBeNull();
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

  test("plan card shows priorityRationale when present", async () => {
    // candidate-describe (candidate[1]) has priorityRationale: "Approval required before execution"
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    // Navigate to cluster detail via the Review next checks button
    const reviewButton = await screen.findByRole("button", { name: /Review next checks/i });
    await act(async () => {
      await user.click(reviewButton);
    });

    // Open findings to expose the Next check plan section
    const details = screen.getByText(/Tap to expand findings/i).closest("details");
    await act(async () => {
      if (details) details.setAttribute("open", "");
    });

    await screen.findByRole("heading", { name: /Next check plan/i });

    // Verify the rationale appears inside the plan section (scoped to the plan heading)
    const planHeading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planSection = planHeading.closest("section") ?? planHeading.parentElement;
    expect(planSection).not.toBeNull();
    // The approval rationale for candidate-describe should appear in the plan
    expect(within(planSection!).queryByText(/Approval required before execution/i)).toBeInTheDocument();
  });

  test("plan card omits priorityRationale when field is absent", async () => {
    // Remove priorityRationale from candidate-describe to test absence
    const detailWithoutRationale = {
      ...sampleClusterDetail,
      nextCheckPlan: sampleClusterDetail.nextCheckPlan.map((c) =>
        c.candidateId === "candidate-describe"
          ? { ...c, priorityRationale: undefined }
          : c
      ),
    };
    const payloads = { ...defaultPayloads, "/api/cluster-detail": detailWithoutRationale };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);

    // Navigate to cluster detail
    const reviewButton = await screen.findByRole("button", { name: /Review next checks/i });
    await act(async () => {
      await user.click(reviewButton);
    });

    // Open findings to expose the Next check plan section
    const details = screen.getByText(/Tap to expand findings/i).closest("details");
    await act(async () => {
      if (details) details.setAttribute("open", "");
    });

    await screen.findByRole("heading", { name: /Next check plan/i });

    const planHeading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planSection = planHeading.closest("section") ?? planHeading.parentElement;
    expect(planSection).not.toBeNull();
    // The approval rationale text should NOT appear anywhere in the plan
    expect(within(planSection!).queryByText(/Approval required before execution/i)).toBeNull();
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
    expect(screen.getByText(/^Current$/i, { selector: ".hero-run-label" })).toBeInTheDocument();
    expect(screen.getAllByText(/ID run-123/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/(Fresh|Aging|Stale)$/i, { selector: ".freshness-indicator__label" })
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
    // Page indicator text is broken across elements, so we search for a parent that contains "Page 1 of 2"
    const notificationSection = document.getElementById("notifications");
    await waitFor(() => expect(notificationSection!.textContent).toMatch(/Page\s+1\s+of\s+2/));
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("limit=50&page=1");
    })).toBe(true);
    const nextButton = screen.getByRole("button", { name: /notifications next page/i });
    expect(nextButton).not.toBeDisabled();
    await act(async () => {
      await user.click(nextButton);
    });
    await waitFor(() => expect(notificationSection!.textContent).toMatch(/Page\s+2\s+of\s+2/));
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("/api/notifications?limit=50&page=2");
    })).toBe(true);
    const pageTwoRows = await screen.findAllByTestId("notification-row");
    expect(pageTwoRows).toHaveLength(10);
    const prevButton = screen.getByRole("button", { name: /notifications previous page/i });
    expect(prevButton).not.toBeDisabled();
    await act(async () => {
      await user.click(prevButton);
    });
    await waitFor(() => expect(notificationSection!.textContent).toMatch(/Page\s+1\s+of\s+2/));
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
    // Single-page pagination hides nav controls entirely - no next/prev buttons
    // Verify only pagination summary is present (not page indicator)
    const notificationSection = document.getElementById("notifications");
    expect(notificationSection).not.toBeNull();
    expect(within(notificationSection!).getByText(/Showing 1–30 of 30/i)).toBeInTheDocument();
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
      // Override notifications entries to ensure multi-page initial state
      "/api/notifications": basePayload,
      "/api/notifications?limit=50&page=1": basePayload,
      "/api/notifications?search=Entry&limit=50&page=1": searchPayload,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });

    // Wait for pagination to load - look for the page indicator first
    const notificationSection = document.getElementById("notifications");
    expect(notificationSection).not.toBeNull();
    await waitFor(() => {
      expect(notificationSection!.textContent).toMatch(/Page\s+1\s+of\s+2/);
    });

    // Initial state: 60 notifications across 2 pages, showing first 50
    expect(notificationSection!.textContent).toMatch(/Showing.*1.*50.*of.*60/);
    // Page indicator is split across elements: "Page ", <strong>1</strong>, " of ", <strong>2</strong>
    // Use textContent match since it concatenates all text nodes
    expect(notificationSection!.textContent).toMatch(/Page\s+1\s+of\s+2/);

    // Now apply search filter
    const searchInput = screen.getByRole("searchbox", {
      name: /Notification text search/i,
    });
    await act(async () => {
      await user.type(searchInput, "Entry");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(30));

    // Search reduces to 30 items (1 page): page indicator hidden, only range summary
    // Check the pagination summary text content directly (split across strong elements)
    expect(notificationSection!.textContent).toMatch(/Showing.*1.*30.*of.*30/);
    // Single-page: no Next button exists (nav controls hidden when totalPages <= 1)
    expect(screen.queryByRole("button", { name: /notifications next page/i })).toBeNull();
  });

  test("autorefresh dropdown persists selection and disables timer", async () => {
    localStorage.setItem(AUTOREFRESH_STORAGE_KEY, "30");
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    const select = await screen.findByLabelText(/Auto/i);
    expect(select).toHaveValue("30");
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 30000);

    await act(async () => {
      await user.selectOptions(select, "off");
    });
    await waitFor(() => expect(localStorage.getItem(AUTOREFRESH_STORAGE_KEY)).toBe("off"));
    await waitFor(() => expect(clearIntervalSpy).toHaveBeenCalled());
    
  });

  test("shows loading and surfaces API errors", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network boom"))));
    render(<App />);

    expect(screen.getByText(/Loading operator data/i)).toBeInTheDocument();
    await screen.findByText(/network boom/i);
  });
});

describe("App panel order regression", () => {
  /**
   * Enforces the intended high-level panel order in the main App render.
   * Tests key relations rather than the full list to avoid brittle DOM coupling.
   */
  test("panel order: Provider-assisted advisory before Deterministic next checks", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Provider-assisted advisory/i });
    
    // Wait for all sections to be fully rendered
    await waitFor(() => {
      const sections = document.querySelectorAll("section[id]");
      expect(sections.length).toBeGreaterThan(10);
    });

    const providerPanel = document.getElementById("review-enrichment");
    const deterministicPanel = document.getElementById("deterministic-next-checks");

    console.log("providerPanel:", providerPanel?.tagName, providerPanel?.id);
    console.log("deterministicPanel:", deterministicPanel?.tagName, deterministicPanel?.id);
    
    expect(providerPanel).not.toBeNull();
    expect(deterministicPanel).not.toBeNull();
    
    // Get document positions using treeWalker approach as alternative
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posA = -1, posB = -1, count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if ((node as Element).id === "review-enrichment") posA = count;
      if ((node as Element).id === "deterministic-next-checks") posB = count;
      if (posA !== -1 && posB !== -1) break;
      count++;
      node = walker.nextNode();
    }
    console.log("TreeWalker positions - review-enrichment:", posA, "deterministic-next-checks:", posB);
    
    // Assert order via treeWalker
    expect(posA).toBeLessThan(posB);
  });

  test("panel order: Check execution review before Work list", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Check execution review/i });
    
    await waitFor(() => {
      const sections = document.querySelectorAll("section[id]");
      expect(sections.length).toBeGreaterThan(10);
    });
    
    const executionPanel = document.getElementById("execution-history");
    const workListPanel = document.getElementById("next-check-queue");

    expect(executionPanel).not.toBeNull();
    expect(workListPanel).not.toBeNull();
    
    // Use TreeWalker approach
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posA = -1, posB = -1, count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if ((node as Element).id === "execution-history") posA = count;
      if ((node as Element).id === "next-check-queue") posB = count;
      if (posA !== -1 && posB !== -1) break;
      count++;
      node = walker.nextNode();
    }
    
    expect(posA).toBeLessThan(posB);
  });

  test("panel order: Notification history before LLM policy", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Notification history/i });
    
    await waitFor(() => {
      const sections = document.querySelectorAll("section[id]");
      expect(sections.length).toBeGreaterThan(10);
    });
    
    const notificationPanel = document.getElementById("notifications");
    const llmPolicyPanel = document.getElementById("llm-policy");

    expect(notificationPanel).not.toBeNull();
    expect(llmPolicyPanel).not.toBeNull();
    
    // Use TreeWalker approach
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posA = -1, posB = -1, count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if ((node as Element).id === "notifications") posA = count;
      if ((node as Element).id === "llm-policy") posB = count;
      if (posA !== -1 && posB !== -1) break;
      count++;
      node = walker.nextNode();
    }
    
    expect(posA).toBeLessThan(posB);
  });

  test("panel order: LLM policy before LLM activity", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /LLM policy/i });
    
    await waitFor(() => {
      const sections = document.querySelectorAll("section[id]");
      expect(sections.length).toBeGreaterThan(10);
    });
    
    const llmPolicyPanel = document.getElementById("llm-policy");
    const llmActivityPanel = document.getElementById("llm-activity");

    expect(llmPolicyPanel).not.toBeNull();
    expect(llmActivityPanel).not.toBeNull();
    
    // Use TreeWalker approach
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posA = -1, posB = -1, count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if ((node as Element).id === "llm-policy") posA = count;
      if ((node as Element).id === "llm-activity") posB = count;
      if (posA !== -1 && posB !== -1) break;
      count++;
      node = walker.nextNode();
    }
    
    expect(posA).toBeLessThan(posB);
  });
});

describe("Recent runs review status badges", () => {
  test("recent-runs fully-reviewed status renders with green badge style", async () => {
    // Build a runs list with only fully-reviewed runs
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

    // Find the status pill for fully-reviewed runs - should have the green class
    const fullyReviewedPills = document.querySelectorAll(".status-pill-fully-reviewed");
    expect(fullyReviewedPills.length).toBe(2);

    // Verify each pill has both the base status-pill class and the specific fully-reviewed class
    fullyReviewedPills.forEach((pill) => {
      expect(pill).toHaveClass("status-pill");
      expect(pill).toHaveClass("status-pill-fully-reviewed");
      // Verify it does NOT have the unreviewed class (different color)
      expect(pill).not.toHaveClass("status-pill-unreviewed");
    });
  });

  test("recent-runs unreviewed status renders with non-green badge style", async () => {
    // Build a runs list with only unreviewed runs
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

    // Find the status pill for unreviewed runs - should have the amber class
    const unreviewedPills = document.querySelectorAll(".status-pill-unreviewed");
    expect(unreviewedPills.length).toBe(1);

    // Verify the pill has both base class and specific unreviewed class
    const pill = unreviewedPills[0];
    expect(pill).toHaveClass("status-pill");
    expect(pill).toHaveClass("status-pill-unreviewed");
    // Verify it does NOT have the fully-reviewed class (green color)
    expect(pill).not.toHaveClass("status-pill-fully-reviewed");
  });

  test("recent-runs badges distinguish fully-reviewed (green) from unreviewed (amber)", async () => {
    // Build a mixed runs list to compare badge styles
    const mixedRuns = {
      runs: [
        {
          runId: "run-400",
          runLabel: "2026-04-07-1400",
          timestamp: "2026-04-07T14:00:00Z",
          clusterCount: 2,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
          batchExecutable: false,
          batchEligibleCount: 0,
        },
        {
          runId: "run-401",
          runLabel: "2026-04-07-1500",
          timestamp: "2026-04-07T15:00:00Z",
          clusterCount: 2,
          triaged: false,
          executionCount: 3,
          reviewedCount: 0,
          reviewStatus: "unreviewed",
          batchExecutable: false,
          batchEligibleCount: 0,
        },
      ],
      totalCount: 2,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/runs": mixedRuns,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(2);
    });

    // Find both pill types
    const fullyReviewedPill = document.querySelector(".status-pill-fully-reviewed");
    const unreviewedPill = document.querySelector(".status-pill-unreviewed");

    expect(fullyReviewedPill).not.toBeNull();
    expect(unreviewedPill).not.toBeNull();

    // Verify they have different CSS classes (different styles)
    expect(fullyReviewedPill).toHaveClass("status-pill-fully-reviewed");
    expect(unreviewedPill).toHaveClass("status-pill-unreviewed");

    // Verify they are distinct from each other
    expect(fullyReviewedPill).not.toHaveClass("status-pill-unreviewed");
    expect(unreviewedPill).not.toHaveClass("status-pill-fully-reviewed");

    // Both should have the base status-pill class
    expect(fullyReviewedPill).toHaveClass("status-pill");
    expect(unreviewedPill).toHaveClass("status-pill");
  });
});

describe("Cockpit navigation", () => {
  test("renders cockpit navigation with chip-style links", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    // Wait for app to load (loading state has no nav)
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Find the cockpit nav container
    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();
    expect(cockpitNav).toHaveAttribute("aria-label", "Fleet cockpit sections");

    // Verify nav uses chip-style links (not plain anchor tags)
    const navItems = cockpitNav!.querySelectorAll(".cockpit-nav__item");
    expect(navItems.length).toBeGreaterThan(0);

    // Verify all nav items are anchor elements with proper href attributes
    navItems.forEach((item) => {
      expect(item.tagName.toLowerCase()).toBe("a");
      expect(item).toHaveAttribute("href");
    });
  });

  test("renders all expected section navigation links", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    // Wait for app to load (loading state has no nav)
    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    // Expected navigation links based on the redesigned navigation
    const expectedLinks = [
      "Recent runs",
      "Run summary",
      "Provider-assisted advisory",
      "Provider-assisted branches",
      "Diagnostic package",
      "Evidence checks",
      "Execution review",
      "Work list",
      "Fleet overview",
      "Cluster detail",
      "Action proposals",
      "Notifications",
      "LLM policy",
      "LLM activity",
    ];

    expectedLinks.forEach((linkText) => {
      const link = cockpitNav!.querySelector(`.cockpit-nav__item[href="#${linkText.toLowerCase().replace(/[^a-z]+/g, "-").replace(/-+/g, "-")}"]`);
      // Use more flexible matching
      const links = Array.from(cockpitNav!.querySelectorAll(".cockpit-nav__item"));
      const found = links.some(
        (el) => el.textContent?.trim() === linkText
      );
      expect(found).toBe(true);
    });
  });

  test("navigation renders correctly with all sections visible", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify cockpit-nav exists and has multiple items
    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    const navItems = cockpitNav!.querySelectorAll(".cockpit-nav__item");
    // Should have at least 14 nav items (15 minus conditional review-insights which depends on run.diagnosticPackReview)
    expect(navItems.length).toBeGreaterThanOrEqual(14);

    // Verify nav chips have proper styling class
    navItems.forEach((item) => {
      expect(item).toHaveClass("cockpit-nav__item");
    });
  });

  test("navigation chips have correct href attributes for section targeting", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    // Wait for app to load (loading state has no nav)
    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    // Map of expected text to href fragments
    const expectedHrefs: Record<string, string> = {
      "Recent runs": "#recent-runs",
      "Run summary": "#run-detail",
      "Work list": "#next-check-queue",
      "Fleet overview": "#fleet",
      "Cluster detail": "#cluster",
      "LLM activity": "#llm-activity",
    };

    Object.entries(expectedHrefs).forEach(([text, href]) => {
      const links = Array.from(
        cockpitNav!.querySelectorAll(".cockpit-nav__item")
      );
      const matchingLink = links.find(
        (el) => el.textContent?.trim() === text
      );
      expect(matchingLink).not.toBeNull();
      expect(matchingLink).toHaveAttribute("href", href);
    });
  });

  test("navigation chips wrap gracefully without breaking layout", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    // Wait for app to load (loading state has no nav)
    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    // Verify nav chip items exist and have proper CSS class structure
    const navItems = cockpitNav!.querySelectorAll(".cockpit-nav__item");
    expect(navItems.length).toBeGreaterThan(10);

    // Verify nav chips have border-radius via CSS class (not computed style in jsdom)
    // The class name itself indicates the styling pattern
    navItems.forEach((item) => {
      expect(item).toHaveClass("cockpit-nav__item");
    });

    // Verify chips use anchor tags for navigation (accessibility)
    const anchorTags = cockpitNav!.querySelectorAll("a");
    expect(anchorTags.length).toBe(navItems.length);
  });

  test("navigation maintains dark theme styling", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    // Wait for app to load (loading state has no nav)
    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    // Verify nav has the cockpit-nav class (dark theme styling applied via CSS class)
    expect(cockpitNav).toHaveClass("cockpit-nav");

    // Verify chips have proper class names indicating dark theme styling
    const chips = cockpitNav!.querySelectorAll(".cockpit-nav__item");
    expect(chips.length).toBeGreaterThan(10);

    // Verify chips are anchor elements with href attributes
    chips.forEach((chip) => {
      expect(chip.tagName.toLowerCase()).toBe("a");
      expect(chip).toHaveAttribute("href");
    });
  });
});

describe("Recent runs selection", () => {
  test("first load defaults to latest run", async () => {
    // The sampleRunsList has run-123 as the first (latest) run
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for run rows to be fully rendered with selection state
    await waitFor(() => {
      const selectedRow = document.querySelector(".run-row-selected");
      expect(selectedRow).not.toBeNull();
    });

    // The latest run should be selected by default
    const latestRunRow = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(latestRunRow).not.toBeNull();
    expect(latestRunRow).toHaveClass("run-row-selected");

    // Hero section should show "Current" label for the latest run
    const heroLabel = await screen.findByText(/^Current$/i);
    expect(heroLabel).toBeInTheDocument();
  });

  test("selecting a run from Recent runs changes selectedRunId and fetches correct data", async () => {
    // Create a smarter mock that returns run-specific data based on run_id query param
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      
      // Handle run-specific payloads based on run_id query param
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return Promise.resolve({
            ok: true, status: 200, statusText: "OK",
            json: () => Promise.resolve({
              ...sampleRun,
              runId: "run-122",
              label: "Run 122 specific",
              nextCheckExecutionHistory: [],
              nextCheckQueue: [],
            }),
          });
        }
        if (runId === "run-123" || !runId) {
          return Promise.resolve({
            ok: true, status: 200, statusText: "OK",
            json: () => Promise.resolve(sampleRun),
          });
        }
      }
      
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });
    
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for runs to render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Initially run-123 should be selected - verify it fetches correct data
    const latestRunRow = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(latestRunRow).toHaveClass("run-row-selected");
    
    // Wait for initial fetch to complete and verify it was called
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Click on a different run (run-122)
    const olderRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(olderRunRow).not.toBeNull();

    await act(async () => {
      await user.click(olderRunRow!);
    });

    // Now run-122 should be selected
    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    // run-123 should no longer be selected
    expect(latestRunRow).not.toHaveClass("run-row-selected");
    
    // Verify that fetch was called with run-122's run_id
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Hero section should show "Selected" label (not "Current" since it's older)
    const selectedLabel = await screen.findByText(/^Selected$/i);
    expect(selectedLabel).toBeInTheDocument();
  });

  test("selected row is visually obvious with selected class", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the selected row
    const selectedRow = document.querySelector(".run-row-selected");
    expect(selectedRow).not.toBeNull();

    // Verify it has the correct class for visual styling
    expect(selectedRow).toHaveClass("run-row-selected");

    // Verify aria-pressed attribute indicates selection
    expect(selectedRow).toHaveAttribute("aria-pressed", "true");

    // Find a non-selected row
    const allRows = document.querySelectorAll(".run-row");
    const nonSelectedRows = Array.from(allRows).filter(
      (row) => !row.classList.contains("run-row-selected")
    );
    expect(nonSelectedRows.length).toBeGreaterThan(0);

    // Non-selected rows should have aria-pressed="false"
    nonSelectedRows.forEach((row) => {
      expect(row).toHaveAttribute("aria-pressed", "false");
    });
  });

  test("selecting a run updates Execution History and verifies correct run_id in fetch", async () => {
    // Create a fetch mock that returns run-specific data based on run_id query param
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return Promise.resolve({
            ok: true, status: 200, statusText: "OK",
            json: () => Promise.resolve(makeRunWithOverrides({
              runId: "run-122",
              label: "2026-04-07-1100",
              nextCheckExecutionHistory: [
                {
                  timestamp: "2026-04-07T11:05:00Z",
                  clusterLabel: "cluster-x",
                  candidateId: "candidate-122",
                  candidateIndex: 0,
                  candidateDescription: "Check for run-122 specific data",
                  commandFamily: "kubectl-get",
                  status: "success",
                  durationMs: 100,
                  artifactPath: "/artifacts/run-122-exec-0.json",
                  timedOut: false,
                  stdoutTruncated: false,
                  stderrTruncated: false,
                  outputBytesCaptured: 1024,
                  resultClass: "useful-signal",
                  resultSummary: "Run-122 specific execution result.",
                },
              ],
              nextCheckQueue: [],
            })),
          });
        }
        // Default to sampleRun for any other run_id
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(sampleRun),
        });
      }
      
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for runs to render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122's run_id
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Execution history should update to show run-122's history
    await waitFor(() => {
      const execHistory = document.getElementById("execution-history");
      expect(execHistory).toBeInTheDocument();
    });

    // Should show run-122 specific description
    const runSpecificHistory = await screen.findByText(/Check for run-122 specific data/i);
    expect(runSpecificHistory).toBeInTheDocument();
  });

  test("selecting a run updates Work list to show that run's queue and verifies run_id in fetch", async () => {
    // Create a smart mock that returns run-specific queue based on run_id query param
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return Promise.resolve({
            ok: true, status: 200, statusText: "OK",
            json: () => Promise.resolve(makeRunWithOverrides({
              runId: "run-122",
              label: "2026-04-07-1100",
              nextCheckExecutionHistory: [],
              nextCheckQueue: [
                {
                  candidateId: "candidate-122-queue",
                  candidateIndex: 0,
                  description: "Run-122 specific queue item",
                  targetCluster: "cluster-x",
                  priorityLabel: "primary",
                  suggestedCommandFamily: "kubectl-get",
                  safeToAutomate: true,
                  requiresOperatorApproval: false,
                  approvalState: "not-required",
                  executionState: "unexecuted",
                  outcomeStatus: "pending",
                  latestArtifactPath: null,
                  sourceReason: "test",
                  expectedSignal: "test",
                  normalizationReason: "test",
                  safetyReason: "test",
                  approvalReason: null,
                  duplicateReason: null,
                  blockingReason: null,
                  targetContext: "cluster-x",
                  commandPreview: "kubectl get all",
                  planArtifactPath: null,
                  queueStatus: "safe-ready",
                  workstream: "incident",
                },
              ],
            })),
          });
        }
        // Default to sampleRun for any other run_id
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(sampleRun),
        });
      }
      
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for runs to render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122's run_id
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Work list should update to show run-122's queue
    await waitFor(() => {
      const queueSection = document.getElementById("next-check-queue");
      expect(queueSection).toBeInTheDocument();
    });

    // Should show run-122 specific queue item
    const runSpecificQueue = await screen.findByText(/Run-122 specific queue item/i);
    expect(runSpecificQueue).toBeInTheDocument();
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

    // Select an older run first
    const olderRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(olderRunRow).not.toBeNull();

    await act(async () => {
      await user.click(olderRunRow!);
    });

    // Verify older run is selected
    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    // Should show "Selected" label (not "Current")
    const selectedLabel = screen.queryByText(/^Selected$/i);
    expect(selectedLabel).toBeInTheDocument();

    // Should show "Jump to latest" button
    const jumpButton = await screen.findByText(/← Latest/i);
    expect(jumpButton).toBeInTheDocument();

    // Click jump to latest
    await act(async () => {
      await user.click(jumpButton);
    });

    // Should now show latest run selected
    const latestRunRow = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(latestRunRow).toHaveClass("run-row-selected");

    // Should show "Current" label
    const currentRunLabel = await screen.findByText(/^Current$/i);
    expect(currentRunLabel).toBeInTheDocument();

    // "Jump to latest" button should be hidden
    const jumpButtonAfter = screen.queryByText(/← Latest/i);
    expect(jumpButtonAfter).not.toBeInTheDocument();
  });

  test("selected run remains stable when runs list updates with new latest run", async () => {
    // This test simulates a poll that adds a new run
    // The selected run should remain selected even when the list changes
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Select an older run (run-122)
    const olderRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(olderRunRow).not.toBeNull();

    await act(async () => {
      await user.click(olderRunRow!);
    });

    // Verify run-122 is selected
    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    // Simulate a new run appearing (e.g., via auto-refresh)
    // Create a new runs list with run-124 added as latest
    const newRunsList = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1400",
          timestamp: "2026-04-07T14:00:00Z",
          clusterCount: 2,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
          batchExecutable: true,
          batchEligibleCount: 3,
        },
        ...sampleRunsList.runs,
      ],
      totalCount: 5,
    };

    // Mock the new response
    let callCount = 0;
    vi.stubGlobal("fetch", createFetchMock({
      ...defaultPayloads,
      "/api/runs": newRunsList,
    }));

    // Trigger a refresh (simulate auto-refresh or manual refresh)
    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    // Selected should still be run-122
    const selectedAfterRefresh = document.querySelector('.run-row-selected');
    expect(selectedAfterRefresh).toHaveAttribute("data-run-id", "run-122");

    // Jump to latest button should be visible since we now have a newer run
    const jumpButton = await screen.findByText(/← Latest/i);
    expect(jumpButton).toBeInTheDocument();
  });

  test("empty states are selected-run-specific for Execution History and verifies run_id", async () => {
    // Create a smart mock that returns run-specific empty data based on run_id query param
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          // Return run with empty execution history
          return Promise.resolve({
            ok: true, status: 200, statusText: "OK",
            json: () => Promise.resolve(makeRunWithOverrides({
              runId: "run-122",
              label: "2026-04-07-1100",
              nextCheckExecutionHistory: [],
              nextCheckQueue: [],
            })),
          });
        }
        // Default to sampleRun for any other run_id
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(sampleRun),
        });
      }
      
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Click on run-122 (which has no execution history)
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122's run_id
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Wait for panel update
    await waitFor(() => {
      const execHistory = document.getElementById("execution-history");
      expect(execHistory).toBeInTheDocument();
    });

    // Empty state should reference "this run"
    const emptyState = await screen.findByText(/No execution history for this run yet/i);
    expect(emptyState).toBeInTheDocument();
  });

  test("empty states are selected-run-specific for Work list and verifies run_id", async () => {
    // Create a smart mock that returns run-specific empty data based on run_id query param
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];
      
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          // Return run with empty queue
          return Promise.resolve({
            ok: true, status: 200, statusText: "OK",
            json: () => Promise.resolve(makeRunWithOverrides({
              runId: "run-122",
              label: "2026-04-07-1100",
              nextCheckExecutionHistory: [],
              nextCheckQueue: [],
            })),
          });
        }
        // Default to sampleRun for any other run_id
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(sampleRun),
        });
      }
      
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Click on run-122 (which has no queue)
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122's run_id
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Wait for panel update
    await waitFor(() => {
      const queueSection = document.getElementById("next-check-queue");
      expect(queueSection).toBeInTheDocument();
    });

    // Empty state should reference "this run"
    const emptyState = await screen.findByText(/Work list is empty for this run/i);
    expect(emptyState).toBeInTheDocument();
  });

  test("keyboard navigation works for run selection", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Focus the first run row
    const firstRunRow = document.querySelector('.run-row[data-run-id="run-123"]') as HTMLElement;
    expect(firstRunRow).not.toBeNull();
    firstRunRow.focus();

    // Verify it's focusable
    expect(document.activeElement).toBe(firstRunRow);

    // Press Enter to select (should already be selected, but verifies keyboard works)
    await act(async () => {
      firstRunRow.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });

    // Run should still be selected
    expect(firstRunRow).toHaveClass("run-row-selected");

    // Tab to another run row
    const secondRunRow = document.querySelector('.run-row[data-run-id="run-122"]') as HTMLElement;
    secondRunRow.focus();

    // Press Space to select
    await act(async () => {
      secondRunRow.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    });

    // Second run should now be selected
    await waitFor(() => {
      expect(secondRunRow).toHaveClass("run-row-selected");
    });
  });
});

describe("Cockpit refresh regression", () => {
  test("manual refresh surfaces newer latest run in the runs list", async () => {
    // Initial runs list with run-123 as latest
    const initialRunsList = {
      runs: [
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
      ],
      totalCount: 2,
    };

    // Newer runs list with run-124 as latest (added 1 hour later)
    const newerRunsList = {
      runs: [
        { runId: "run-124", runLabel: "2026-04-07-1300", timestamp: "2026-04-07T13:00:00Z", clusterCount: 3, triaged: true, executionCount: 6, reviewedCount: 6, reviewStatus: "fully-reviewed" },
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
      ],
      totalCount: 3,
    };

    // Use a mutable ref for the runs list to simulate refresh response change
    let runsListRef = { current: initialRunsList };
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      // Return current runs list state (simulates backend response change on refresh)
      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(runsListRef.current),
        });
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for initial runs to render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(2);
    });

    // Verify run-123 is latest (first in list)
    expect(document.querySelector('.run-row[data-run-id="run-123"]')).not.toBeNull();
    // run-124 should NOT be in the list yet
    expect(document.querySelector('.run-row[data-run-id="run-124"]')).toBeNull();

    // Simulate the new run appearing on the backend
    runsListRef.current = newerRunsList;

    // Trigger manual refresh
    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    // Wait for runs list to update
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(3);
    });

    // run-124 should now appear in the list as the latest run
    const newRunRow = document.querySelector('.run-row[data-run-id="run-124"]');
    expect(newRunRow).not.toBeNull();

    // run-123 should still be in the list (now second position)
    expect(document.querySelector('.run-row[data-run-id="run-123"]')).not.toBeNull();
  });

  test("selected historical run is not mislabeled as current after latest advances", async () => {
    // Initial runs list
    const initialRunsList = {
      runs: [
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
      ],
      totalCount: 2,
    };

    // Newer runs list with run-124 as latest
    const newerRunsList = {
      runs: [
        { runId: "run-124", runLabel: "2026-04-07-1300", timestamp: "2026-04-07T13:00:00Z", clusterCount: 3, triaged: true, executionCount: 6, reviewedCount: 6, reviewStatus: "fully-reviewed" },
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
      ],
      totalCount: 3,
    };

    let runsListRef = { current: initialRunsList };
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(runsListRef.current),
        });
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for initial render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(2);
    });

    // Select an older run (run-122)
    const olderRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    await act(async () => {
      await user.click(olderRunRow!);
    });

    // Verify run-122 is selected
    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    // Hero should show "Selected" (not "Current") since run-122 is not the latest
    // Note: The hero shows "Current" only when selectedRunId === latestRunId
    // When we select run-122, selectedRunId !== latestRunId, so it should show "Selected"
    // But initially run-123 is selected, so let's wait for the selection to settle

    // Now a new run appears
    runsListRef.current = newerRunsList;

    // Trigger refresh
    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    // Wait for the runs list to update
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(3);
    });

    // run-122 should still be selected
    expect(olderRunRow).toHaveClass("run-row-selected");

    // run-124 is now the latest run (index 0)
    const latestRunRow = document.querySelector('.run-row[data-run-id="run-124"]');
    expect(latestRunRow).not.toBeNull();

    // "← Latest" jump button should be visible since run-122 is no longer the latest
    const jumpButton = screen.queryByText(/← Latest/i);
    expect(jumpButton).not.toBeNull();
  });

  test("staleness hint is truthful after new run appears", async () => {
    // Create a run with a timestamp that's clearly in the past
    const now = new Date();
    const oldTimestamp = new Date(now.getTime() - 60 * 60 * 1000).toISOString(); // 1 hour ago
    const newerTimestamp = new Date(now.getTime() - 30 * 60 * 1000).toISOString(); // 30 min ago

    const initialRunsList = {
      runs: [
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: oldTimestamp, clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 1,
    };

    const newerRunsList = {
      runs: [
        { runId: "run-124", runLabel: "2026-04-07-1300", timestamp: newerTimestamp, clusterCount: 3, triaged: true, executionCount: 6, reviewedCount: 6, reviewStatus: "fully-reviewed" },
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: oldTimestamp, clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 2,
    };

    let runsListRef = { current: initialRunsList };
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(runsListRef.current),
        });
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for initial render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(1);
    });

    // Initially run-123 is the latest (and selected)
    // Hero should show "Current"
    expect(screen.getByText(/^Current$/i)).toBeInTheDocument();

    // Now a newer run appears
    runsListRef.current = newerRunsList;

    // Trigger refresh
    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    // Wait for the runs list to update
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(2);
    });

    // run-123 is now an OLDER run (second in list)
    // It should NOT be labeled as "Current" anymore
    // Instead, "← Latest" button should be visible
    expect(screen.getByText(/← Latest/i)).toBeInTheDocument();
  });

  test("latest navigation button targets the actual newest run after refresh", async () => {
    const initialRunsList = {
      runs: [
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
      ],
      totalCount: 2,
    };

    const newerRunsList = {
      runs: [
        { runId: "run-124", runLabel: "2026-04-07-1300", timestamp: "2026-04-07T13:00:00Z", clusterCount: 3, triaged: true, executionCount: 6, reviewedCount: 6, reviewStatus: "fully-reviewed" },
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 3, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 3, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
      ],
      totalCount: 3,
    };

    let runsListRef = { current: initialRunsList };
    let runIdOverride: string | null = null;

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(runsListRef.current),
        });
      }

      if (base === "/api/run") {
        // Support run_id query param
        const params = new URLSearchParams(url.split("?")[1] || "");
        const requestedRunId = params.get("run_id");
        if (requestedRunId) {
          return Promise.resolve({
            ok: true, status: 200, statusText: "OK",
            json: () => Promise.resolve({ ...sampleRun, runId: requestedRunId }),
          });
        }
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(payload),
      });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for initial render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(2);
    });

    // Initially run-123 is selected (and is latest)
    expect(screen.getByText(/^Current$/i)).toBeInTheDocument();

    // Select an older run
    const olderRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    await act(async () => {
      await user.click(olderRunRow!);
    });

    // Wait for selection
    await waitFor(() => {
      expect(olderRunRow).toHaveClass("run-row-selected");
    });

    // Now a newer run appears
    runsListRef.current = newerRunsList;

    // Trigger refresh
    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    // Wait for update
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(3);
    });

    // Click "← Latest" button
    const jumpButton = screen.getByText(/← Latest/i);
    await act(async () => {
      await user.click(jumpButton);
    });

    // Now run-124 should be selected (the newest run)
    const latestRunRow = document.querySelector('.run-row[data-run-id="run-124"]');
    expect(latestRunRow).toHaveClass("run-row-selected");

    // Hero should show "Current" again
    expect(screen.getByText(/^Current$/i)).toBeInTheDocument();
  });

  test("interval polling does not leak or duplicate timers", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Record state after initial render
    setIntervalSpy.mockClear();
    clearIntervalSpy.mockClear();

    // Change auto-refresh setting
    const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
    await act(async () => {
      autoRefreshSelect.value = "10";
      autoRefreshSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });

    // Verify a new interval was created for the new duration
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 10000);

    // Verify clearInterval was called for cleanup (at least once for the old timer)
    expect(clearIntervalSpy).toHaveBeenCalled();
  });

});

describe("Run freshness thresholds", () => {
  /**
   * Run freshness thresholds (via getRunFreshnessLevel):
   * - Fresh: run age <= 15 minutes (green 🟢 "Fresh")
   * - Aging: run age > 15 and <= 45 minutes (yellow 🟡 "Aging")
   * - Stale: run age > 45 minutes (red 🔴 "Stale")
   *
   * Timestamps are hardcoded relative to test execution date (Apr 7, 2026).
   * No fake timers needed - we test the freshness calculation directly.
   */

  test("run shows Fresh status when timestamp is <= 15 minutes old", async () => {
    const freshRun = {
      ...sampleRun,
      timestamp: minsAgo(10), // 10 min ago
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": freshRun }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const freshLabel = screen.getByText(/^Fresh$/i);
    expect(freshLabel).toBeInTheDocument();

    const freshnessIndicator = document.querySelector(".freshness-indicator--fresh");
    expect(freshnessIndicator).not.toBeNull();

    const emoji = freshnessIndicator?.querySelector(".freshness-indicator__emoji");
    expect(emoji?.textContent).toBe("🟢");
  });

  test("run shows Aging status when timestamp is > 15 and <= 45 minutes old", async () => {
    // Create a run with timestamp 30 minutes ago (should be Aging)
    const agingRun = {
      ...sampleRun,
      timestamp: minsAgo(30), // 30 minutes ago
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": agingRun }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Find the freshness indicator label - should show "Aging"
    const agingLabel = screen.getByText(/^Aging$/i);
    expect(agingLabel).toBeInTheDocument();

    // The indicator should have the warning class (maps to Aging)
    const freshnessIndicator = document.querySelector(".freshness-indicator--warning");
    expect(freshnessIndicator).not.toBeNull();

    // Verify emoji is 🟡 for aging/warning
    const emoji = freshnessIndicator?.querySelector(".freshness-indicator__emoji");
    expect(emoji?.textContent).toBe("🟡");
  });

  test("run shows Stale status when timestamp is > 45 minutes old", async () => {
    // Create a run with timestamp 60 minutes ago (should be Stale)
    const staleRun = {
      ...sampleRun,
      timestamp: minsAgo(60), // 60 minutes ago
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": staleRun }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Find the freshness indicator label - should show "Stale"
    const staleLabel = screen.getByText(/^Stale$/i);
    expect(staleLabel).toBeInTheDocument();

    // The indicator should have the stale class
    const freshnessIndicator = document.querySelector(".freshness-indicator--stale");
    expect(freshnessIndicator).not.toBeNull();

    // Verify emoji is 🔴 for stale
    const emoji = freshnessIndicator?.querySelector(".freshness-indicator__emoji");
    expect(emoji?.textContent).toBe("🔴");
  });

  test("boundary: run at exactly 15 minutes shows Fresh", async () => {
    // Use timestamp just inside Fresh boundary (14 min 59 sec ago) to avoid edge flake
    const freshTimestamp = dayjs().subtract(14, "minute").subtract(59, "second").toISOString();
    const freshRun = {
      ...sampleRun,
      timestamp: freshTimestamp,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": freshRun }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByText(/^Fresh$/i)).toBeInTheDocument();
  });

  test("boundary: run at exactly 45 minutes shows Aging", async () => {
    // Use timestamp just inside Aging boundary (44 min 59 sec ago) to avoid edge flake
    const agingTimestamp = dayjs().subtract(44, "minute").subtract(59, "second").toISOString();
    const agingRun = {
      ...sampleRun,
      timestamp: agingTimestamp,
    };
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": agingRun }));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByText(/^Aging$/i)).toBeInTheDocument();
  });

  test("selecting a different run changes freshness indicator to match new run's timestamp", async () => {
    // Create two runs with different timestamps - one Fresh, one Stale
    const freshRunTimestamp = minsAgo(10); // 10 min ago = Fresh
    const staleRunTimestamp = minsAgo(120); // 120 min ago = Stale

    const runsWithDifferentTimestamps = {
      runs: [
        { runId: "run-123", runLabel: "Fresh run", timestamp: freshRunTimestamp, clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "Stale run", timestamp: staleRunTimestamp, clusterCount: 2, triaged: true, executionCount: 3, reviewedCount: 3, reviewStatus: "fully-reviewed" },
      ],
      totalCount: 2,
    };

    // Initial fetch returns fresh run
    const freshRun = { ...sampleRun, timestamp: freshRunTimestamp };
    const staleRun = { ...sampleRun, runId: "run-122", timestamp: staleRunTimestamp };

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(runsWithDifferentTimestamps),
        });
      }
      if (base === "/api/run") {
        const params = new URLSearchParams(url.split("?")[1] || "");
        const runId = params.get("run_id");
        if (runId === "run-122") {
          return Promise.resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(staleRun) });
        }
        return Promise.resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(freshRun) });
      }

      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) return Promise.reject(new Error(`Unexpected fetch ${url}`));
      return Promise.resolve({ ok: true, status: 200, statusText: "OK", json: () => Promise.resolve(payload) });
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for initial state - run-123 (Fresh) should be selected
    await waitFor(() => {
      expect(screen.queryByText(/^Fresh$/i)).toBeInTheDocument();
    });

    // Verify Fresh is shown initially
    expect(screen.getByText(/^Fresh$/i)).toBeInTheDocument();
    const freshIndicator = document.querySelector(".freshness-indicator--fresh");
    expect(freshIndicator).not.toBeNull();

    // Select run-122 (Stale)
    const staleRunRow = document.querySelector('.run-row[data-run-id="run-122"]');
    await act(async () => {
      await user.click(staleRunRow!);
    });

    // Wait for UI to update - should now show Stale
    await waitFor(() => {
      expect(screen.queryByText(/^Stale$/i)).toBeInTheDocument();
    });

    // Verify Stale is now shown
    expect(screen.getByText(/^Stale$/i)).toBeInTheDocument();
    const staleIndicator = document.querySelector(".freshness-indicator--stale");
    expect(staleIndicator).not.toBeNull();

    // Verify that fetch was called with run_id=run-122
    const run122FetchCalls = fetchMock.mock.calls.filter(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("run_id=run-122");
    });
    expect(run122FetchCalls.length).toBeGreaterThan(0);
  });

  test("refresh controls remain present and queryable in header", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Refresh button should be present
    const refreshButton = await screen.findByRole("button", { name: /Refresh/i });
    expect(refreshButton).toBeInTheDocument();
    expect(refreshButton).not.toBeDisabled();

    // Auto-refresh dropdown should be present
    const autoRefreshSelect = await screen.findByLabelText(/Auto/i);
    expect(autoRefreshSelect).toBeInTheDocument();

    // Page freshness indicator should be present
    const pageFreshness = document.querySelector(".page-freshness-indicator");
    expect(pageFreshness).not.toBeNull();
  });

  test("panel switching behavior still works after run selection", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Navigate to a cluster detail tab
    const clusterSection = await screen.findByRole("heading", { name: /Cluster detail/i });
    expect(clusterSection).toBeInTheDocument();

    // Verify tabs are present
    const tabList = await screen.findByRole("tablist", { name: /Cluster detail tabs/i });
    expect(tabList).toBeInTheDocument();

    // Click Hypotheses tab
    await act(async () => {
      await user.click(within(tabList).getByRole("button", { name: /Hypotheses/i }));
    });
    expect(screen.getByText(sampleClusterDetail.hypotheses[0].description)).toBeInTheDocument();

    // Now select a different run
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Wait for UI to update
    await waitFor(() => {
      const updatedTabList = document.querySelector('[role="tablist"]');
      expect(updatedTabList).toBeInTheDocument();
    });

    // Tab list should still be functional after run selection
    const updatedTabList = await screen.findByRole("tablist", { name: /Cluster detail tabs/i });
    await act(async () => {
      await user.click(within(updatedTabList).getByRole("button", { name: /Next checks/i }));
    });

    // Should show next checks tab content
    expect(within(updatedTabList).getByRole("button", { name: /Next checks/i })).toBeInTheDocument();
  });
});

describe("Auto-refresh polling behavior", () => {
  /**
   * Tests for auto-refresh polling behavior.
   * IMPORTANT: Bootstrap the app on REAL timers first, then switch to fake timers.
   * Do not use findBy* or waitFor after fake timers are enabled.
   * Product behavior is proven via UI assertions, not timer spy assertions.
   */

  test("enabling auto-refresh fetches new data and updates UI with run-124 as latest", async () => {
    // Build initial runs list with run-123 as latest
    const initialRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
        {
          runId: "run-122",
          runLabel: "2026-04-07-1100",
          timestamp: "2026-04-07T11:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 3,
          reviewedCount: 0,
          reviewStatus: "unreviewed",
        },
      ],
      totalCount: 2,
    };

    // Build updated runs list with run-124 as latest
    const updatedRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1300",
          timestamp: "2026-04-07T13:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
        {
          runId: "run-122",
          runLabel: "2026-04-07-1100",
          timestamp: "2026-04-07T11:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 3,
          reviewedCount: 0,
          reviewStatus: "unreviewed",
        },
      ],
      totalCount: 3,
    };

    // Mutable reference for the runs list response
    let currentRunsList = initialRunsList;

    // Create mutable fetch mock
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve({ ...currentRunsList }),
        });
      }

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

    // STEP 1: Bootstrap on REAL timers first
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify initial state on real timers: run-123 is selected
    const run123Row = document.querySelector('.run-row[data-run-id="run-123"]');
    expect(run123Row).not.toBeNull();
    expect(run123Row).toHaveClass("run-row-selected");

    // STEP 2: Now switch to fake timers
    vi.useFakeTimers();
    try {
      // Setup userEvent with fake timer control (NO setIntervalSpy assertions)
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      // Enable auto-refresh with 10 second interval
      const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
      await act(async () => {
        await user.selectOptions(autoRefreshSelect, "10");
      });

      // STEP 3: Update the mock to return run-124 as latest
      currentRunsList = updatedRunsList;

      // STEP 4: Advance one interval
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
        // Flush React state update after fetch resolves
        await Promise.resolve();
      });

      // STEP 5: Assert synchronously - product behavior proof
      const run124Row = document.querySelector('.run-row[data-run-id="run-124"]');
      expect(run124Row).not.toBeNull();

      // run-124 exists in the list
      // Note: selectedRunId remains on run-123 (no auto-selection on new runs)
      // The "← Latest" button appears to allow jumping to the newest run

      // Verify the total count shows 3 runs
      const showingText = screen.getByText(/Showing \d+ of 3/i);
      expect(showingText).toBeInTheDocument();

      // The "← Latest" jump button should be visible since a newer run exists
      const jumpButton = screen.queryByText(/← Latest/i);
      expect(jumpButton).not.toBeNull();
    } finally {
      // Cleanup
      vi.runOnlyPendingTimers();
      vi.useRealTimers();
    }
  });

  test("disabling auto-refresh prevents UI update even when data changes", async () => {
    // Initial runs with run-123 as latest
    const initialRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 1,
    };

    // Updated runs with run-124 as latest
    const updatedRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1300",
          timestamp: "2026-04-07T13:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 2,
    };

    let currentRunsList = initialRunsList;

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve({ ...currentRunsList }),
        });
      }

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

    // STEP 1: Bootstrap on REAL timers
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify initial state - run-123 exists
    expect(document.querySelector('.run-row[data-run-id="run-123"]')).not.toBeNull();

    // STEP 2: Switch to fake timers
    vi.useFakeTimers();
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      // Enable auto-refresh
      const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
      await act(async () => {
        await user.selectOptions(autoRefreshSelect, "10");
      });

      // Disable auto-refresh
      await act(async () => {
        await user.selectOptions(autoRefreshSelect, "off");
      });

      // Re-query after interactions to get fresh DOM reference
      const run123After = document.querySelector('.run-row[data-run-id="run-123"]');
      expect(run123After).not.toBeNull();

      // STEP 3: Update the mock data - run-124 now available
      currentRunsList = updatedRunsList;

      // STEP 4: Advance time - no update should happen since disabled
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20000);
      });

      // STEP 5: Assert - run-124 should NOT appear (polling disabled)
      const run124Row = document.querySelector('.run-row[data-run-id="run-124"]');
      expect(run124Row).toBeNull();

      // Verify only 1 run exists in the list (no new data fetched)
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBe(1);
    } finally {
      // Cleanup
      vi.runOnlyPendingTimers();
      vi.useRealTimers();
    }
  });

  test("changing auto-refresh interval updates polling schedule", async () => {
    // Initial runs with run-123 as latest
    const initialRunsList: RunsListPayload = {
      runs: [
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 1,
    };

    // Data after 15 seconds
    const runsAt15s: RunsListPayload = {
      runs: [
        {
          runId: "run-124",
          runLabel: "2026-04-07-1300",
          timestamp: "2026-04-07T13:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 2,
    };

    // Data after 25 seconds (when 30s interval would have triggered but we changed it)
    const runsAt25s: RunsListPayload = {
      runs: [
        {
          runId: "run-125",
          runLabel: "2026-04-07-1400",
          timestamp: "2026-04-07T14:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-124",
          runLabel: "2026-04-07-1300",
          timestamp: "2026-04-07T13:00:00Z",
          clusterCount: 3,
          triaged: false,
          executionCount: 0,
          reviewedCount: 0,
          reviewStatus: "no-executions",
        },
        {
          runId: "run-123",
          runLabel: "2026-04-07-1200",
          timestamp: "2026-04-07T12:00:00Z",
          clusterCount: 3,
          triaged: true,
          executionCount: 5,
          reviewedCount: 5,
          reviewStatus: "fully-reviewed",
        },
      ],
      totalCount: 3,
    };

    let currentRunsList = initialRunsList;

    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = typeof input === "string" ? input : input.url;
      const base = url.split("?")[0];

      if (base === "/api/runs") {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          json: () => Promise.resolve({ ...currentRunsList }),
        });
      }

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

    // STEP 1: Bootstrap on REAL timers
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for UI to settle after initial fetch - verify run-123 is selected
    await waitFor(() => {
      const selectedRow = document.querySelector('.run-row[data-run-id="run-123"]');
      expect(selectedRow).toHaveClass("run-row-selected");
    });

    // STEP 2: Switch to fake timers
    vi.useFakeTimers();
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      // Enable 30 second interval
      const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
      await act(async () => {
        await user.selectOptions(autoRefreshSelect, "30");
      });

      // Advance 15 seconds - no update should happen (30s interval not reached)
      currentRunsList = runsAt15s;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(15000);
      });

      // Re-query run-123 (DOM may have updated) - should still be selected
      const run123Row15s = document.querySelector('.run-row[data-run-id="run-123"]');
      expect(run123Row15s).toHaveClass("run-row-selected");
      // run-124 should NOT exist yet (30s interval not reached)
      expect(document.querySelector('.run-row[data-run-id="run-124"]')).toBeNull();

      // Change to 10 second interval
      await act(async () => {
        await user.selectOptions(autoRefreshSelect, "10");
      });

      // Advance 10 seconds - update should happen
      currentRunsList = runsAt25s;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      // Verify run-124 is now in the list
      const run124Row = document.querySelector('.run-row[data-run-id="run-124"]');
      expect(run124Row).not.toBeNull();
    } finally {
      // Cleanup
      vi.runOnlyPendingTimers();
      vi.useRealTimers();
    }
  });

  test("auto-refresh dropdown persists selection to localStorage", async () => {
    // This test uses real timers only - no fake timers needed
    localStorage.removeItem(AUTOREFRESH_STORAGE_KEY);
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Select 10 second auto-refresh
    const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "10");
    });

    // Verify localStorage was updated
    await waitFor(() => {
      expect(localStorage.getItem(AUTOREFRESH_STORAGE_KEY)).toBe("10");
    });

    // Change to 30 second
    await act(async () => {
      await user.selectOptions(autoRefreshSelect, "30");
    });

    // Verify localStorage was updated to new value
    await waitFor(() => {
      expect(localStorage.getItem(AUTOREFRESH_STORAGE_KEY)).toBe("30");
    });
  });
});
