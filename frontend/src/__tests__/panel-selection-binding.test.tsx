import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";
import type {
  DiagnosticPackReview,
  LLMActivity,
  LLMPolicy,
  ProviderExecution,
  ReviewEnrichment,
  ReviewEnrichmentStatus,
  RunPayload,
} from "../types";
import { makeRunWithOverrides, sampleFleet, sampleProposals, sampleClusterDetail, sampleNotifications } from "./fixtures";

// Helper to create a smart fetch mock that returns run-specific data
const createRunAwareFetchMock = (
  run123Payload: RunPayload,
  run122Payload: RunPayload,
  globalPayloads: Record<string, unknown> = {}
) => {
  const defaultPayloads = {
    "/api/run": run123Payload,
    "/api/runs": {
      runs: [
        { runId: "run-123", runLabel: "2026-04-07-1200", timestamp: "2026-04-07T12:00:00Z", clusterCount: 2, triaged: true, executionCount: 5, reviewedCount: 5, reviewStatus: "fully-reviewed" },
        { runId: "run-122", runLabel: "2026-04-07-1100", timestamp: "2026-04-07T11:00:00Z", clusterCount: 2, triaged: false, executionCount: 3, reviewedCount: 0, reviewStatus: "unreviewed" },
      ],
      totalCount: 2,
    },
    "/api/fleet": sampleFleet,
    "/api/proposals": sampleProposals,
    "/api/notifications": sampleNotifications,
    "/api/notifications?limit=50&page=1": sampleNotifications,
    "/api/cluster-detail": sampleClusterDetail,
    ...globalPayloads,
  };

  return vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    const base = url.split("?")[0];

    if (base === "/api/run") {
      const params = new URLSearchParams(url.split("?")[1] || "");
      const runId = params.get("run_id");
      if (runId === "run-122") {
        return Promise.resolve({
          ok: true, status: 200, statusText: "OK",
          json: () => Promise.resolve(run122Payload),
        });
      }
      // Default to run-123 payload
      return Promise.resolve({
        ok: true, status: 200, statusText: "OK",
        json: () => Promise.resolve(run123Payload),
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
};

// Create run-specific payloads for testing
const createRun123Payload = (overrides: Partial<RunPayload> = {}): RunPayload =>
  makeRunWithOverrides({
    runId: "run-123",
    label: "Run 123",
    reviewEnrichment: {
      status: "success",
      provider: "k8sgpt",
      timestamp: "2026-04-07T12:00:00Z",
      summary: "Run 123 enrichment summary",
      triageOrder: ["cluster-a", "cluster-b"],
      topConcerns: ["Run 123 concern 1", "Run 123 concern 2"],
      evidenceGaps: [],
      nextChecks: [],
      focusNotes: [],
      artifactPath: "/artifacts/run-123-review-enrichment.json",
      errorSummary: null,
      skipReason: null,
    },
    reviewEnrichmentStatus: {
      status: "success",
      reason: "Run 123 enrichment succeeded.",
      provider: "k8sgpt",
      policyEnabled: true,
      providerConfigured: true,
      adapterAvailable: true,
      runEnabled: true,
      runProvider: "k8sgpt",
    },
    providerExecution: {
      autoDrilldown: { enabled: true, provider: "default", maxPerRun: 3, eligible: 2, attempted: 1, succeeded: 1, failed: 0, skipped: 0, unattempted: 1, budgetLimited: null, notes: null },
      reviewEnrichment: { enabled: true, provider: "k8sgpt", maxPerRun: 1, eligible: 1, attempted: 1, succeeded: 1, failed: 0, skipped: 0, unattempted: 0, budgetLimited: null, notes: null },
    },
    diagnosticPack: {
      path: "/artifacts/run-123-diagnostic-pack.zip",
      timestamp: "2026-04-07T12:00:00Z",
      sizeBytes: 123456,
    },
    diagnosticPackReview: {
      timestamp: "2026-04-07T12:00:00Z",
      summary: "Run 123 diagnostic review summary",
      majorDisagreements: ["Run 123 disagreement 1"],
      missingChecks: ["Run 123 missing check 1"],
      rankingIssues: [],
      genericChecks: [],
      recommendedNextActions: [],
      driftMisprioritized: false,
      confidence: "high",
      providerStatus: "provider-ok",
      providerSummary: "Run 123 provider summary",
      providerErrorSummary: null,
      providerSkipReason: null,
      providerReview: null,
      artifactPath: "/artifacts/run-123-diagnostic-review.json",
    },
    llmPolicy: {
      autoDrilldown: {
        enabled: true,
        provider: "default",
        maxPerRun: 3,
        usedThisRun: 1,
        successfulThisRun: 1,
        failedThisRun: 0,
        skippedThisRun: 0,
        budgetExhausted: false,
      },
    },
    llmActivity: {
      entries: [
        { timestamp: "2026-04-07T12:00:00Z", runId: "run-123", runLabel: "Run 123", clusterLabel: "cluster-a", toolName: "k8sgpt", provider: "k8sgpt", purpose: "review-enrichment", status: "success", latencyMs: 100, artifactPath: "/artifacts/run-123-llm.json", summary: "Run 123 LLM activity", errorSummary: null, skipReason: null },
      ],
      summary: { retainedEntries: 5 },
    },
    deterministicNextChecks: {
      clusterCount: 1,
      clusters: [
        {
          clusterLabel: "cluster-a",
          context: "cluster-a",
          topProblem: "Run 123 problem",
          assessmentArtifactPath: "/artifacts/run-123-assessment.json",
          drilldownArtifactPath: "/artifacts/run-123-drilldown.json",
          deterministicNextCheckSummaries: [
            { description: "Run 123 deterministic check", workstream: "incident", urgency: "high", isPrimaryTriage: true, method: "kubectl", owner: "platform", whyNow: "Run 123 rationale", evidenceNeeded: ["evidence1"] },
          ],
        },
      ],
    },
    ...overrides,
  } as RunPayload);

const createRun122Payload = (overrides: Partial<RunPayload> = {}): RunPayload =>
  makeRunWithOverrides({
    runId: "run-122",
    label: "Run 122",
    reviewEnrichment: {
      status: "success",
      provider: "llamacpp",
      timestamp: "2026-04-07T11:00:00Z",
      summary: "Run 122 enrichment summary",
      triageOrder: ["cluster-b"],
      topConcerns: ["Run 122 concern 1"],
      evidenceGaps: [],
      nextChecks: [],
      focusNotes: [],
      artifactPath: "/artifacts/run-122-review-enrichment.json",
      errorSummary: null,
      skipReason: null,
    },
    reviewEnrichmentStatus: {
      status: "not-attempted",
      reason: "Run 122 not attempted.",
      provider: "llamacpp",
      policyEnabled: true,
      providerConfigured: true,
      adapterAvailable: true,
      runEnabled: true,
      runProvider: "llamacpp",
    },
    providerExecution: {
      autoDrilldown: { enabled: true, provider: "stub", maxPerRun: 3, eligible: 1, attempted: 0, succeeded: 0, failed: 0, skipped: 1, unattempted: 0, budgetLimited: null, notes: null },
      reviewEnrichment: { enabled: true, provider: "llamacpp", maxPerRun: 1, eligible: 1, attempted: 1, succeeded: 0, failed: 1, skipped: 0, unattempted: 0, budgetLimited: null, notes: null },
    },
    diagnosticPack: {
      path: "/artifacts/run-122-diagnostic-pack.zip",
      timestamp: "2026-04-07T11:00:00Z",
      sizeBytes: 78901,
    },
    diagnosticPackReview: {
      timestamp: "2026-04-07T11:00:00Z",
      summary: "Run 122 diagnostic review summary",
      majorDisagreements: ["Run 122 disagreement 1", "Run 122 disagreement 2"],
      missingChecks: ["Run 122 missing check 1", "Run 122 missing check 2"],
      rankingIssues: [],
      genericChecks: [],
      recommendedNextActions: [],
      driftMisprioritized: true,
      confidence: "low",
      providerStatus: "provider-ok",
      providerSummary: "Run 122 provider summary",
      providerErrorSummary: null,
      providerSkipReason: null,
      providerReview: null,
      artifactPath: "/artifacts/run-122-diagnostic-review.json",
    },
    llmPolicy: {
      autoDrilldown: {
        enabled: false,
        provider: "stub",
        maxPerRun: 3,
        usedThisRun: 0,
        successfulThisRun: 0,
        failedThisRun: 0,
        skippedThisRun: 0,
        budgetExhausted: false,
      },
    },
    llmActivity: {
      entries: [
        { timestamp: "2026-04-07T11:00:00Z", runId: "run-122", runLabel: "Run 122", clusterLabel: "cluster-b", toolName: "llamacpp", provider: "llamacpp", purpose: "manual", status: "failed", latencyMs: 200, artifactPath: "/artifacts/run-122-llm.json", summary: "Run 122 LLM activity", errorSummary: "timeout", skipReason: null },
      ],
      summary: { retainedEntries: 3 },
    },
    deterministicNextChecks: null,
    ...overrides,
  } as RunPayload);

const createStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
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

describe("Panel selection binding - Per-run panels", () => {
  test("Review Enrichment Panel shows run-specific enrichment data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for runs to render
    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Initially run-123 should be selected - verify enrichment shows run-123 provider
    await waitFor(() => {
      expect(screen.getByText(/Provider k8sgpt/i)).toBeInTheDocument();
    });

    // Verify enrichment summary is from run-123
    expect(screen.getByText(/Run 123 enrichment summary/i)).toBeInTheDocument();

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Verify enrichment now shows run-122 provider
    await waitFor(() => {
      expect(screen.getByText(/Provider llamacpp/i)).toBeInTheDocument();
    });

    // Verify enrichment summary is from run-122
    expect(screen.getByText(/Run 122 enrichment summary/i)).toBeInTheDocument();
  });

  test("Provider Execution Panel shows run-specific execution data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the Provider Execution Panel section
    const providerPanel = document.getElementById("provider-execution");
    expect(providerPanel).toBeInTheDocument();

    // Verify the panel is visible with its heading
    await waitFor(() => {
      expect(within(providerPanel!).getByText(/Auto drilldown/i)).toBeInTheDocument();
    });

    // --- STRENGTHENED: Assert run-123 specific content BEFORE switching ---
    // Run-123 autoDrilldown: eligible=2, attempted=1, succeeded=1, failed=0, skipped=0, unattempted=1
    // Run-123 reviewEnrichment: eligible=1, attempted=1, succeeded=1, failed=0, skipped=0, unattempted=0
    // Unique differentiator: unattempted 1 (autoDrilldown) vs unattempted 0 (reviewEnrichment)
    await waitFor(() => {
      // Check both branches exist with expected titles
      expect(within(providerPanel!).getByText(/Auto drilldown/i)).toBeInTheDocument();
      expect(within(providerPanel!).getByText(/Review enrichment/i)).toBeInTheDocument();
      // Use unattempted 1 as unique marker for autoDrilldown in run-123
      expect(within(providerPanel!).getByText(/unattempted 1/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBe(1);
    });

    // --- STRENGTHENED: Assert run-122 specific content AFTER switching ---
    // Run-122 autoDrilldown: eligible=1, attempted=0, succeeded=0, failed=0, skipped=1, unattempted=0
    // Run-122 reviewEnrichment: eligible=1, attempted=1, succeeded=0, failed=1, skipped=0
    // Unique differentiators for run-122: skipped 1 and failed 1
    await waitFor(() => {
      // Check skipped=1 for autoDrilldown (unique to run-122 vs run-123 which has skipped 0)
      expect(within(providerPanel!).getByText(/skipped 1/i)).toBeInTheDocument();
      // Check failed=1 for reviewEnrichment (unique to run-122 vs run-123 which has failed 0)
      expect(within(providerPanel!).getByText(/failed 1/i)).toBeInTheDocument();
    });

    // Panel should still be visible
    await waitFor(() => {
      expect(within(providerPanel!).getByText(/Auto drilldown/i)).toBeInTheDocument();
    });
  });

  test("Run Diagnostic Pack Panel shows run-specific pack data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the Diagnostic Pack Download Panel
    const packPanel = document.getElementById("diagnostic-pack-download");
    expect(packPanel).toBeInTheDocument();

    // Should show the panel heading
    await waitFor(() => {
      expect(within(packPanel!).getByRole("heading", { name: /Run diagnostic package archive/i })).toBeInTheDocument();
    });

    // --- STRENGTHENED: Assert run-123 specific content BEFORE switching ---
    // Run-123 diagnosticPack: timestamp 2026-04-07T12:00:00Z (Apr 7, 2026 12:00 UTC)
    await waitFor(() => {
      // Verify run-123 timestamp is rendered
      expect(within(packPanel!).getByText(/Apr 7, 2026 12:00 UTC/i)).toBeInTheDocument();
    });

    // Verify Download link exists with run-123 path (URL-encoded)
    const run123Link = within(packPanel!).getByText(/Download diagnostic pack/i);
    expect(run123Link).toBeInTheDocument();
    // The href is URL-encoded: /artifact?path=%2Fartifacts%2Frun-123-diagnostic-pack.zip
    const run123Href = run123Link.getAttribute("href") || "";
    expect(decodeURIComponent(run123Href)).toContain("/artifacts/run-123-diagnostic-pack.zip");

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // --- STRENGTHENED: Assert run-122 specific content AFTER switching ---
    // Run-122 diagnosticPack: timestamp 2026-04-07T11:00:00Z (Apr 7, 2026 11:00 UTC)
    await waitFor(() => {
      // Verify timestamp changed to run-122
      expect(within(packPanel!).getByText(/Apr 7, 2026 11:00 UTC/i)).toBeInTheDocument();
    });

    // Verify download link changed to run-122 path (URL-encoded)
    const run122Link = within(packPanel!).getByText(/Download diagnostic pack/i);
    expect(run122Link).toBeInTheDocument();
    const run122Href = run122Link.getAttribute("href") || "";
    expect(decodeURIComponent(run122Href)).toContain("/artifacts/run-122-diagnostic-pack.zip");

    // Panel should still be visible
    await waitFor(() => {
      expect(within(packPanel!).getByRole("heading", { name: /Run diagnostic package archive/i })).toBeInTheDocument();
    });
  });

  test("Diagnostic Pack Review Panel shows run-specific review data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the Diagnostic Pack Review Panel
    const reviewPanel = document.getElementById("diagnostic-pack-review");
    expect(reviewPanel).toBeInTheDocument();

    // Should show run-123 disagreement
    await waitFor(() => {
      expect(within(reviewPanel!).getByText(/Run 123 disagreement 1/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Should now show run-122 disagreement
    await waitFor(() => {
      expect(within(reviewPanel!).getByText(/Run 122 disagreement 1/i)).toBeInTheDocument();
    });
  });

  test("Run Summary shows run-specific data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the Run Summary Panel
    const summaryPanel = document.getElementById("run-detail");
    expect(summaryPanel).toBeInTheDocument();

    // Should show run-123 label
    await waitFor(() => {
      expect(within(summaryPanel!).getByRole("heading", { name: /Run 123/i })).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Should now show run-122 label
    await waitFor(() => {
      expect(within(summaryPanel!).getByRole("heading", { name: /Run 122/i })).toBeInTheDocument();
    });
  });

  test("Deterministic Next Checks Panel shows run-specific data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload({ deterministicNextChecks: null });
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the Deterministic Next Checks Panel
    const deterministicPanel = document.getElementById("deterministic-next-checks");
    expect(deterministicPanel).toBeInTheDocument();

    // Should show run-123 deterministic check
    await waitFor(() => {
      expect(within(deterministicPanel!).getByText(/Run 123 deterministic check/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Should show empty state for run-122 (no deterministic checks)
    await waitFor(() => {
      expect(within(deterministicPanel!).getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
    });
  });

  test("LLM Policy Panel shows run-specific policy data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the LLM Policy Panel
    const llmPolicyPanel = document.getElementById("llm-policy");
    expect(llmPolicyPanel).toBeInTheDocument();

    // --- STRENGTHENED: Assert run-123 specific content BEFORE switching ---
    // Run-123 llmPolicy.autoDrilldown: enabled=true, provider=default, usedThisRun=1, success/failed/skipped=1/0/0
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/used this run/i)).toBeInTheDocument();
    });

    // Check enabled status pill
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/Auto drilldown enabled/i)).toBeInTheDocument();
    });

    // Check provider name (rendered as separate elements: "Provider" label + "default" value)
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/^Provider$/i)).toBeInTheDocument();
      // The value is rendered as <strong>default</strong>
      expect(within(llmPolicyPanel!).getByText(/^default$/)).toBeInTheDocument();
    });

    // Check success count (run-123: 1 successful, 0 failed, 0 skipped)
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/1 \/ 0 \/ 0/i)).toBeInTheDocument();
    });

    // Check budget status
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/Within budget/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // --- STRENGTHENED: Assert run-122 specific content AFTER switching ---
    // Run-122 llmPolicy.autoDrilldown: enabled=false, provider=stub, usedThisRun=0, success/failed/skipped=0/0/0

    // Check disabled status pill
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/Auto drilldown disabled/i)).toBeInTheDocument();
    });

    // Check provider changed to stub (rendered as separate elements)
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/^Provider$/i)).toBeInTheDocument();
      // The value is rendered as <strong>stub</strong>
      expect(within(llmPolicyPanel!).getByText(/^stub$/)).toBeInTheDocument();
    });

    // Check success/failed/skipped changed to 0/0/0
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/0 \/ 0 \/ 0/i)).toBeInTheDocument();
    });

    // Panel should still be visible
    await waitFor(() => {
      expect(within(llmPolicyPanel!).getByText(/used this run/i)).toBeInTheDocument();
    });
  });

  test("LLM Activity Panel shows run-specific activity data", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the LLM Activity Panel
    const llmActivityPanel = document.getElementById("llm-activity");
    expect(llmActivityPanel).toBeInTheDocument();

    // Should show run-123 LLM activity entry
    await waitFor(() => {
      expect(within(llmActivityPanel!).getByText(/Run 123 LLM activity/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Verify fetch was called with run-122
    await waitFor(() => {
      const runCalls = fetchMock.mock.calls.filter(
        ([input]) => {
          const url = typeof input === "string" ? input : (input as Request).url;
          return url.includes("/api/run") && url.includes("run_id=run-122");
        }
      );
      expect(runCalls.length).toBeGreaterThan(0);
    });

    // Should now show run-122 LLM activity entry
    await waitFor(() => {
      expect(within(llmActivityPanel!).getByText(/Run 122 LLM activity/i)).toBeInTheDocument();
    });
  });
});

describe("Panel selection binding - Empty state wording", () => {
  test("Review Enrichment empty state says 'for this run'", async () => {
    const run123 = createRun123Payload({ reviewEnrichment: undefined, reviewEnrichmentStatus: undefined });
    const run122 = createRun122Payload({ reviewEnrichment: undefined, reviewEnrichmentStatus: undefined });
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Should show empty state for run-123
    await waitFor(() => {
      expect(screen.getByText(/Provider-assisted review enrichment is not configured for this run/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Should still show 'for this run' wording
    await waitFor(() => {
      expect(screen.getByText(/Provider-assisted review enrichment is not configured for this run/i)).toBeInTheDocument();
    });
  });

  test("Deterministic Next Checks empty state says 'for this run'", async () => {
    const run123 = createRun123Payload({ deterministicNextChecks: null });
    const run122 = createRun122Payload({ deterministicNextChecks: null });
    const fetchMock = createRunAwareFetchMock(run123, run122);

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find the deterministic panel
    const deterministicPanel = document.getElementById("deterministic-next-checks");
    expect(deterministicPanel).toBeInTheDocument();

    // Should show empty state for run-123
    await waitFor(() => {
      expect(within(deterministicPanel!).getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
    });

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Should still show 'for this run' wording
    await waitFor(() => {
      expect(within(deterministicPanel!).getByText(/No evidence-based checks are available for this run/i)).toBeInTheDocument();
    });
  });
});

describe("Panel selection binding - Global panels", () => {
  test("Fleet Overview does not change when selecting different run", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    
    // Use stable fleet data - copy sampleFleet to avoid mutation
    const stableFleet = JSON.parse(JSON.stringify(sampleFleet));
    stableFleet.topProblem = {
      title: "API pressure",
      detail: "Control plane latency is trending upward",
    };
    
    const fetchMock = createRunAwareFetchMock(run123, run122, {
      "/api/fleet": stableFleet,
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Verify fleet shows stable content (topProblem.detail from sampleFleet)
    expect(screen.getByText(sampleFleet.topProblem.detail, { exact: false })).toBeInTheDocument();

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Fleet should still show stable content
    expect(screen.getByText(sampleFleet.topProblem.detail, { exact: false })).toBeInTheDocument();

    // Fleet data should remain unchanged (stable across run selections)
    // The fleet panel should still show the same content
    expect(screen.getByText(sampleFleet.topProblem.detail, { exact: false })).toBeInTheDocument();
  });

  test("Cluster Detail does not change when selecting different run", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    
    // Create stable cluster detail that won't change
    const stableClusterDetail = {
      ...sampleClusterDetail,
      selectedClusterLabel: "cluster-a",
      findings: [{ label: "Stable Finding", context: "stable", triggerReasons: [], warningEvents: 0, nonRunningPods: 0, summaryEntries: [], patternDetails: [], rolloutStatus: [], artifactPath: null }],
      hypotheses: [{ description: "Stable Hypothesis", confidence: "high", probableLayer: "control-plane", falsifier: "none" }],
      nextChecks: [],
    };
    
    const fetchMock = createRunAwareFetchMock(run123, run122, {
      "/api/cluster-detail": stableClusterDetail,
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find cluster detail section
    const clusterSection = document.getElementById("cluster");
    expect(clusterSection).toBeInTheDocument();

    // Verify stable content
    expect(within(clusterSection).getByText(/Stable Finding/i)).toBeInTheDocument();

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Cluster detail should still show stable content
    expect(within(clusterSection).getByText(/Stable Finding/i)).toBeInTheDocument();
  });

  test("Action Proposals does not change when selecting different run", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    
    // Create stable proposals that won't change
    const stableProposals = {
      proposals: [
        { 
          proposalId: "stable-proposal-1", 
          status: "pending", 
          confidence: "high", 
          target: "Stable Target 1", 
          rationale: "Stable rationale",
          expectedBenefit: "Improve stability",
          sourceRunId: "run-123",
          latestNote: null,
          lifecycle: [
            { status: "pending", timestamp: "2026-04-07T10:00:00Z", note: null },
          ],
          artifacts: [
            { label: "diagnostic", path: "/artifacts/stable-1.json" },
          ],
        },
        { 
          proposalId: "stable-proposal-2", 
          status: "approved", 
          confidence: "medium", 
          target: "Stable Target 2", 
          rationale: "Another stable rationale",
          expectedBenefit: "Reduce alerts",
          sourceRunId: "run-123",
          latestNote: null,
          lifecycle: [
            { status: "approved", timestamp: "2026-04-07T11:00:00Z", note: null },
          ],
          artifacts: [
            { label: "diagnostic", path: "/artifacts/stable-2.json" },
          ],
        },
      ],
      statusSummary: [
        { status: "pending", count: 1 },
        { status: "approved", count: 1 },
      ],
    };
    
    const fetchMock = createRunAwareFetchMock(run123, run122, {
      "/api/proposals": stableProposals,
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find proposals section
    const proposalsSection = document.getElementById("proposals");
    expect(proposalsSection).toBeInTheDocument();

    // Verify stable content
    expect(within(proposalsSection).getByText(/Stable Target 1/i)).toBeInTheDocument();

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Proposals should still show stable content
    expect(within(proposalsSection).getByText(/Stable Target 1/i)).toBeInTheDocument();
  });

  test("Notification History does not change when selecting different run", async () => {
    const run123 = createRun123Payload();
    const run122 = createRun122Payload();
    
    // Create stable notifications that won't change
    const stableNotifications = {
      notifications: [
        { kind: "Info", summary: "Stable notification 1", timestamp: "2026-04-07T10:00:00Z", runId: "run-old", clusterLabel: "cluster-a", context: "stable", details: [] },
        { kind: "Warning", summary: "Stable notification 2", timestamp: "2026-04-07T11:00:00Z", runId: "run-old", clusterLabel: "cluster-b", context: "stable", details: [] },
      ],
      total: 2,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    
    const fetchMock = createRunAwareFetchMock(run123, run122, {
      "/api/notifications": stableNotifications,
      "/api/notifications?limit=50&page=1": stableNotifications,
    });

    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Find notification history section
    const notificationSection = document.getElementById("notifications");
    expect(notificationSection).toBeInTheDocument();

    // Verify stable content
    expect(within(notificationSection).getByText(/Stable notification 1/i)).toBeInTheDocument();

    // Click on run-122
    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    expect(run122Row).not.toBeNull();

    await act(async () => {
      await user.click(run122Row!);
    });

    // Notifications should still show stable content
    expect(within(notificationSection).getByText(/Stable notification 1/i)).toBeInTheDocument();
  });
});
