/**
 * App main test file.
 * 
 * Contains remaining tests not split into behavior-grouped files:
 * - Deterministic checks panel tests
 * - Queue details with result interpretation
 * - Manual execution and approval tests
 * 
 * Primary test file for deterministic panel promotion behavior,
 * workstream bucket organization, and execution actions.
 * 
 * Split from this file as part of the LLM-friendly file split:
 * - app.smoke.test.tsx - App bootstrap and cluster detail tabs
 * - app.queue-panel.test.tsx - Queue panel behavior
 * - app.run-selection.test.tsx - Run selection and summary
 * - app.panel-layout.test.tsx - Navigation and panel ordering
 * - app.notifications.test.tsx - Notification history and autorefresh
 * - app.review-enrichment.test.tsx - Review enrichment and diagnostic pack
 * - app.llm-policy.test.tsx - LLM activity and policy
 * - app.test-fixtures.tsx - Shared fixtures and helpers
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  getLoadedDeterministicPanel,
  getQueuePanel,
  makeFetchResponse,
  makeRunWithOverrides,
  sampleFleet,
  sampleRun,
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

describe("App", () => {
  test("deterministic panel surfaces run-derived checks", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const panel = await getLoadedDeterministicPanel();

    const scoped = within(panel);
    expect(scoped.getByText(/candidate check.*to review and promote/i)).toBeInTheDocument();
    expect(scoped.getAllByRole("button", { name: /Review cluster detail/i }).length).toBeGreaterThan(0);
    expect(scoped.getAllByRole("link", { name: /View assessment artifact/i }).length).toBeGreaterThan(0);
    expect(scoped.getAllByText(/Firefight now/i).length).toBeGreaterThan(0);
    const driftNodes = scoped.getAllByText(/Drift \/ toil follow-up/i);
    expect(driftNodes.length).toBeGreaterThan(0);
    const driftDetails = driftNodes[0].closest("details");
    expect(driftDetails).not.toHaveAttribute("open");
  });

  test("drift bucket is collapsed during active degraded runs", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const panel = await getLoadedDeterministicPanel();

    const driftDetails = panel.querySelector("details.deterministic-group--drift") as HTMLElement;
    expect(driftDetails).not.toBeNull();
    expect(driftDetails).not.toHaveAttribute("open");
    expect(panel.textContent).toContain("Compare baseline release parity");
  });

  test("drift bucket is expanded by default when no degraded clusters exist", async () => {
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

    const panel = await getLoadedDeterministicPanel();

    const driftDetails = panel.querySelector("details.deterministic-group--drift") as HTMLElement;
    expect(driftDetails).not.toBeNull();
    expect(driftDetails).toHaveAttribute("open");
    expect(within(driftDetails).getByText(/Compare baseline release parity/i)).toBeInTheDocument();
  });

  test("drift bucket can be manually expanded by the operator", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const panel = await getLoadedDeterministicPanel();

    const driftDetails = panel.querySelector("details.deterministic-group--drift") as HTMLElement;
    expect(driftDetails).not.toBeNull();
    expect(driftDetails).not.toHaveAttribute("open");

    const summaryElement = driftDetails.querySelector("summary") as HTMLElement;
    await act(async () => {
      await user.click(summaryElement);
    });

    expect(driftDetails).toHaveAttribute("open");
    expect(within(driftDetails).getByText(/Compare baseline release parity/i)).toBeInTheDocument();
  });

  test("promote deterministic next check button triggers API and shows status", async () => {
    const payloads = { ...defaultPayloads };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Deterministic checks/i });
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

    await screen.findByRole("heading", { name: /Deterministic checks/i });
    const promoteButtons = await screen.findAllByRole("button", { name: /Add to work list/i });
    await act(async () => {
      await user.click(promoteButtons[0]);
    });

    await waitFor(() =>
      expect(
        screen.getByText(/Deterministic next check promoted to the queue/i)
      ).toBeInTheDocument()
    );

    const viewInQueueLink = await screen.findByRole("button", { name: /View in work list →/i });
    expect(viewInQueueLink).toBeInTheDocument();

    await act(async () => {
      await user.click(viewInQueueLink);
    });

    const queueScoped = await getQueuePanel();
    const statusSelect = queueScoped.getByLabelText(/Queue status/i);
    expect(statusSelect).toHaveValue("approval-needed");

    const clusterSelect = queueScoped.getByLabelText(/Cluster filter/i);
    expect(clusterSelect).toHaveValue("cluster-a");

    const queueSection = document.getElementById("next-check-queue");
    expect(queueSection).toBeInTheDocument();
  });

  test("view in queue click scrolls to queue section", async () => {
    const payloads = { ...defaultPayloads };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await screen.findByRole("heading", { name: /Deterministic checks/i });
    const promoteButtons = await screen.findAllByRole("button", { name: /Add to work list/i });
    await act(async () => {
      await userEvent.setup().click(promoteButtons[0]);
    });

    await waitFor(() =>
      expect(
        screen.getByText(/Deterministic next check promoted to the queue/i)
      ).toBeInTheDocument()
    );

    const queueSection = document.getElementById("next-check-queue");
    expect(queueSection).toBeInTheDocument();

    const scrollMock = vi.fn();
    const originalScrollIntoView = queueSection!.scrollIntoView;
    queueSection!.scrollIntoView = scrollMock;

    const viewInQueueLink = await screen.findByRole("button", { name: /View in work list →/i });

    await act(async () => {
      await userEvent.setup().click(viewInQueueLink);
    });

    expect(scrollMock).toHaveBeenCalled();

    queueSection!.scrollIntoView = originalScrollIntoView;
  });

  test("incident group shows limited checks before expanding", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const panel = await getLoadedDeterministicPanel();
    const incidentLabel = within(panel).getAllByText(/Firefight now/i)[0];
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

    const panel = await getLoadedDeterministicPanel();
    const incidentLabel = within(panel).getAllByText(/Firefight now/i)[0];
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

    const panel = await getLoadedDeterministicPanel();

    expect(within(panel).getAllByText(/Firefight now/i).length).toBeGreaterThan(0);
    expect(within(panel).getAllByText(/Evidence gathering/i).length).toBeGreaterThan(0);
    expect(within(panel).getAllByText(/Drift \/ toil follow-up/i).length).toBeGreaterThan(0);
  });

  test("workstream bucket counts are shown per bucket", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const panel = await getLoadedDeterministicPanel();

    const incidentSection = panel.querySelector("section.deterministic-group");
    expect(incidentSection).not.toBeNull();
    const incidentHeadDiv = incidentSection!.querySelector(".deterministic-group-head");
    expect(incidentHeadDiv).not.toBeNull();
    expect(within(incidentHeadDiv!).getByText(/Firefight now/i)).toBeInTheDocument();
    expect(incidentHeadDiv!.textContent).toMatch(/\d+ check/);

    const evidenceSection = panel.querySelectorAll("section.deterministic-group")[1];
    expect(evidenceSection).not.toBeNull();
    const evidenceHeadDiv = evidenceSection.querySelector(".deterministic-group-head");
    expect(evidenceHeadDiv).not.toBeNull();
    expect(within(evidenceHeadDiv!).getByText(/Evidence gathering/i)).toBeInTheDocument();
    expect(evidenceHeadDiv!.textContent).toMatch(/\d+ check/);

    const driftDetails = panel.querySelector("details.deterministic-group--drift");
    expect(driftDetails).not.toBeNull();
    const driftHeadDiv = driftDetails!.querySelector(".deterministic-group-head");
    expect(driftHeadDiv).not.toBeNull();
    expect(within(driftHeadDiv!).getByText(/Drift \/ toil follow-up/i)).toBeInTheDocument();
    expect(driftHeadDiv!.textContent).toMatch(/\d+ check/);
  });

  test("evidence cards appear in the correct workstream bucket", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const panel = await getLoadedDeterministicPanel();

    const incidentLabel = within(panel).getAllByText(/Firefight now/i)[0];
    const incidentSection = incidentLabel.closest("section");
    expect(incidentSection).not.toBeNull();
    expect(within(incidentSection!).getByText(/Capture tcpdump/i)).toBeInTheDocument();

    const evidenceLabel = within(panel).getAllByText(/Evidence gathering/i)[0];
    const evidenceSection = evidenceLabel.closest("section");
    expect(evidenceSection).not.toBeNull();
    expect(within(evidenceSection!).getByText(/Collect kubelet metrics from nodes/i)).toBeInTheDocument();

    const driftLabel = within(panel).getAllByText(/Drift \/ toil follow-up/i)[0];
    const driftSection = driftLabel.closest("details");
    expect(driftSection).not.toBeNull();
    expect(within(driftSection!).getByText(/Compare baseline release parity/i)).toBeInTheDocument();
  });

  test("empty workstream bucket shows empty state message", async () => {
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

    const panel = await getLoadedDeterministicPanel();

    const incidentLabel = within(panel).getAllByText(/Firefight now/i)[0];
    const incidentSection = incidentLabel.closest("section");
    expect(incidentSection).not.toBeNull();
    const incidentItems = within(incidentSection!).getAllByRole("listitem");
    expect(incidentItems.length).toBeGreaterThan(0);

    const evidenceLabel = within(panel).getAllByText(/Evidence gathering/i)[0];
    const evidenceSection = evidenceLabel.closest("section");
    expect(evidenceSection).not.toBeNull();
    expect(within(evidenceSection!).getByText(/No evidence gathering checks/i, { exact: false })).toBeInTheDocument();
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

    expect(await screen.findByText(/No evidence-based checks are available/i)).toBeInTheDocument();
    expect(screen.getByText(/Use the Work list below for the full queue of planner candidates/i)).toBeInTheDocument();
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
        return makeFetchResponse(executionResponse);
      }
      const base = url.split("?")[0];
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return makeFetchResponse(payload);
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
        return makeFetchResponse(approvalResponse);
      }
      const base = url.split("?")[0];
      const payload = defaultPayloads[url] ?? defaultPayloads[base];
      if (!payload) {
        return Promise.reject(new Error(`Unexpected fetch ${url}`));
      }
      return makeFetchResponse(payload);
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
});
