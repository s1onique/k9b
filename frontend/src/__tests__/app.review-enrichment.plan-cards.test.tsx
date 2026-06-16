/**
 * Next check plan and plan cards tests.
 *
 * Tests the rendering of next check plan sections, plan card behavior,
 * priority rationale, and plan visibility conditions.
 *
 * Part of app.review-enrichment.test.tsx split for LLM-friendly file sizes.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  PLANNER_HINT_TEXT,
  sampleClusterDetail,
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

describe("Next check plan and plan cards", () => {
  test("renders next check plan section with planner candidates", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await user.click(summaryToggle);
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
    await user.click(summaryToggle);
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
    expect(screen.getByText(UI_STRINGS.queueStatus.awaitingApprovalWithCount(1), { exact: false })).toBeInTheDocument();
    expect(screen.getByText(UI_STRINGS.queueStatus.notUsedWithCount(1), { exact: false })).toBeInTheDocument();
  });

  test("plan card shows priorityRationale when present", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const reviewButton = await screen.findByRole("button", { name: /Review next checks/i });
    await user.click(reviewButton);

    const details = screen.getByText(/Tap to expand findings/i).closest("details");
    await act(async () => {
      if (details) details.setAttribute("open", "");
    });

    await screen.findByRole("heading", { name: /Next check plan/i });

    const planHeading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planSection = planHeading.closest("section") ?? planHeading.parentElement;
    expect(planSection).not.toBeNull();
    expect(within(planSection!).queryByText(/Approval required before execution/i)).toBeInTheDocument();
  });

  test("plan card omits priorityRationale when field is absent", async () => {
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
    render(<App />);

    const reviewButton = await screen.findByRole("button", { name: /Review next checks/i });
    await userEvent.setup().click(reviewButton);

    const details = screen.getByText(/Tap to expand findings/i).closest("details");
    await act(async () => {
      if (details) details.setAttribute("open", "");
    });

    await screen.findByRole("heading", { name: /Next check plan/i });

    const planHeading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planSection = planHeading.closest("section") ?? planHeading.parentElement;
    expect(planSection).not.toBeNull();
    expect(within(planSection!).queryByText(/Approval required before execution/i)).toBeNull();
  });

  test("displays run button only for allowed next-check candidates", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await user.click(summaryToggle);
    const heading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planPanel = heading.closest(".next-check-plan");
    expect(planPanel).not.toBeNull();
    const buttons = within(planPanel!).getAllByRole("button", { name: /Run candidate/i });
    expect(buttons.length).toBe(1);
  });

  test("renders stale and orphaned approvals", async () => {
    const staleCandidates = sampleRun.nextCheckPlan?.candidates?.map((candidate) =>
      candidate.candidateId === "candidate-describe"
        ? { ...candidate, approvalStatus: "approval-stale" }
        : candidate
    ) ?? [];
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
        candidates: staleCandidates as typeof sampleRun.nextCheckPlan.candidates,
        orphanedApprovals,
      },
    };
    const detailWithStale = {
      ...sampleClusterDetail,
      nextCheckPlan: staleCandidates as typeof sampleClusterDetail.nextCheckPlan,
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
    await user.click(summaryToggle);
    const heading = await screen.findByRole("heading", { name: /Next check plan/i });
    const planPanel = heading.closest(".next-check-plan");
    expect(planPanel).not.toBeNull();
    const scoped = within(planPanel!);
    expect(scoped.getByText(UI_STRINGS.approvalStates.approvalStale, { exact: false })).toBeInTheDocument();
    expect(scoped.getByText(UI_STRINGS.approvalStates.orphanedApprovals, { exact: false })).toBeInTheDocument();
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
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await userEvent.setup().click(summaryToggle);
    expect(screen.queryByRole("heading", { name: /Next check plan/i })).toBeNull();
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

    await screen.findByRole("heading", { name: /Fleet overview/i });
    await waitFor(() => {
      expect(screen.queryByText(/No next checks generated for this run/i)).toBeInTheDocument();
    });
    
    expect(await screen.findByText(new RegExp(reasonText, "i"))).toBeInTheDocument();
  });

  test("review next checks button opens the cluster detail panel", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const reviewButton = await screen.findByRole("button", { name: /Review next checks/i });
    await user.click(reviewButton);

    expect(await screen.findByRole("heading", { name: /Cluster detail/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /Next check plan/i })).toBeInTheDocument();
  });
});
