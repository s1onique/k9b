// Advisory Lower Sections Tests
//
// Tests for the compressed lower advisory sections added to App.tsx:
// - Top concerns (AdvisoryTopConcernsSection)
// - Evidence gaps (AdvisoryEvidenceGapsSection)
// - Next checks (AdvisoryNextChecksSection + parseNextCheckEntry)
// - Focus notes (AdvisoryFocusNotesSection)
// - Section coexistence under the provider summary
// - Empty state handling

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { parseNextCheckEntry } from "../App";
import {
  createFetchMock,
  createStorageMock,
  sampleFleet,
  sampleProposals,
  sampleRun,
} from "./fixtures";

// ---------------------------------------------------------------------------
// Unit tests for parseNextCheckEntry view-model helper
// ---------------------------------------------------------------------------
describe("parseNextCheckEntry", () => {
  it("returns intent and null cluster/command for plain text", () => {
    const result = parseNextCheckEntry("Validate ingress controller");
    expect(result.intent).toBe("Validate ingress controller");
    expect(result.targetCluster).toBeNull();
    expect(result.commandPreview).toBeNull();
  });

  it("extracts cluster from leading bracket prefix", () => {
    const result = parseNextCheckEntry("[prod-cluster] Check pod restarts");
    expect(result.targetCluster).toBe("prod-cluster");
    expect(result.intent).toBe("Check pod restarts");
    expect(result.commandPreview).toBeNull();
  });

  it("extracts kubectl command preview when intent precedes it", () => {
    const result = parseNextCheckEntry(
      "Inspect recent events: kubectl get events -n default --sort-by=.lastTimestamp"
    );
    expect(result.intent).toBe("Inspect recent events");
    expect(result.commandPreview).not.toBeNull();
    expect(result.commandPreview).toContain("kubectl");
  });

  it("treats lone kubectl command as intent with no separate commandPreview", () => {
    const result = parseNextCheckEntry("kubectl logs -n monitoring pod-xyz --tail=100");
    expect(result.intent).toContain("kubectl");
    expect(result.commandPreview).toBeNull();
  });

  it("handles cluster prefix + kubectl command", () => {
    const result = parseNextCheckEntry(
      "[staging] Check logs: kubectl logs -n app svc/frontend --tail=50"
    );
    expect(result.targetCluster).toBe("staging");
    expect(result.intent).toBeTruthy();
    expect(result.commandPreview).toContain("kubectl");
  });

  it("truncates very long intents to at most 120 chars", () => {
    const longText = "A".repeat(200);
    const result = parseNextCheckEntry(longText);
    expect(result.intent.length).toBeLessThanOrEqual(120);
  });
});

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------
const createMockEnrichment = (overrides = {}) => ({
  status: "success" as const,
  provider: "test-provider",
  timestamp: "2026-04-07T12:00:00Z",
  summary: "Test enrichment summary",
  triageOrder: ["cluster-a", "cluster-b"],
  topConcerns: [
    "High API latency in cluster-a",
    "Pod restarts in cluster-b kube-system",
  ],
  evidenceGaps: [
    "Missing node metrics for cluster-a",
    "Incomplete logs for kube-scheduler",
  ],
  nextChecks: [
    "Validate API response times: kubectl get events -n default",
    "[cluster-b] Check pod restart frequency",
  ],
  focusNotes: ["Prioritize cluster-a due to active alerts"],
  artifactPath: "/artifacts/review-enrichment.json",
  errorSummary: null,
  skipReason: null,
  ...overrides,
});

const createMockEnrichmentStatus = (overrides = {}) => ({
  status: "available" as const,
  provider: "test-provider",
  runEnabled: true,
  runProvider: "test-provider",
  reason: null,
  ...overrides,
});

let storageMock: ReturnType<typeof createStorageMock>;

const setupRender = (enrichmentOverrides = {}) => {
  const runPayload = {
    ...sampleRun,
    reviewEnrichment: createMockEnrichment(enrichmentOverrides),
    reviewEnrichmentStatus: createMockEnrichmentStatus(),
  };
  const payloads = {
    "/api/run": runPayload,
    "/api/runs": { runs: [], totalCount: 0 },
    "/api/fleet": sampleFleet,
    "/api/proposals": sampleProposals,
  };
  globalThis.fetch = createFetchMock(payloads);
  render(<App />);
};

describe("Advisory Lower Sections", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storageMock = createStorageMock();
    Object.defineProperty(globalThis, "localStorage", {
      value: storageMock,
      writable: true,
      configurable: true,
    });
    vi.spyOn(globalThis, "clearInterval");
    vi.spyOn(globalThis, "setInterval").mockImplementation(() => 1);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Top Concerns
  // -------------------------------------------------------------------------
  describe("Top concerns section", () => {
    it("renders concern rows for each concern", async () => {
      setupRender({
        topConcerns: ["CPU spike in control plane", "Storage latency on node-3"],
      });

      await waitFor(() => {
        const concerns = document.querySelectorAll(".advisory-concern-row");
        expect(concerns.length).toBeGreaterThanOrEqual(2);
      });

      const concernTexts = Array.from(
        document.querySelectorAll(".advisory-concern-row")
      ).map((el) => el.textContent);
      expect(concernTexts.some((t) => t?.includes("CPU spike"))).toBe(true);
      expect(concernTexts.some((t) => t?.includes("Storage latency"))).toBe(true);
    });

    it("renders concerns section with correct label", async () => {
      setupRender({ topConcerns: ["Memory pressure"] });

      await waitFor(() => {
        const section = document.querySelector(".advisory-concerns-section");
        expect(section).toBeTruthy();
        expect(section?.textContent).toContain("Top concerns");
      });
    });

    it("does not render concerns section when concerns array is empty", async () => {
      setupRender({ topConcerns: [], triageOrder: [] });

      await new Promise((resolve) => setTimeout(resolve, 15));
      const section = document.querySelector(".advisory-concerns-section");
      expect(section).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Evidence Gaps
  // -------------------------------------------------------------------------
  describe("Evidence gaps section", () => {
    it("renders gap rows with gap marker for each gap", async () => {
      setupRender({
        evidenceGaps: ["Missing node CPU metrics", "Incomplete scheduler logs"],
      });

      await waitFor(() => {
        const gaps = document.querySelectorAll(".advisory-gap-row");
        expect(gaps.length).toBeGreaterThanOrEqual(2);
      });

      const gapTexts = Array.from(
        document.querySelectorAll(".advisory-gap-row")
      ).map((el) => el.textContent);
      expect(gapTexts.some((t) => t?.includes("Missing node CPU metrics"))).toBe(true);
      expect(gapTexts.some((t) => t?.includes("Incomplete scheduler logs"))).toBe(true);
    });

    it("renders gap marker element in each gap row", async () => {
      setupRender({ evidenceGaps: ["Missing log data"] });

      await waitFor(() => {
        const markers = document.querySelectorAll(".advisory-gap-marker");
        expect(markers.length).toBeGreaterThanOrEqual(1);
      });
    });

    it("renders gaps section with uncertainty-oriented label", async () => {
      setupRender({ evidenceGaps: ["Incomplete data"] });

      await waitFor(() => {
        const label = document.querySelector(".advisory-gaps-label");
        expect(label).toBeTruthy();
        expect(label?.textContent).toContain("Evidence gaps");
      });
    });

    it("does not render gaps section when gaps array is empty", async () => {
      setupRender({ evidenceGaps: [], triageOrder: [] });

      await new Promise((resolve) => setTimeout(resolve, 15));
      const section = document.querySelector(".advisory-gaps-section");
      expect(section).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Next Checks
  // -------------------------------------------------------------------------
  describe("Next checks section", () => {
    it("renders action rows from nextChecks data", async () => {
      setupRender({
        nextChecks: [
          "Validate API response times",
          "Check pod restart frequency",
        ],
      });

      await waitFor(() => {
        const rows = document.querySelectorAll(".advisory-check-row");
        expect(rows.length).toBeGreaterThanOrEqual(2);
      });
    });

    it("renders check intent text for each check", async () => {
      setupRender({
        nextChecks: ["Inspect ingress logs", "Review scheduler behavior"],
      });

      await waitFor(() => {
        const intents = document.querySelectorAll(".advisory-check-intent");
        expect(intents.length).toBeGreaterThanOrEqual(2);
        const intentTexts = Array.from(intents).map((el) => el.textContent);
        expect(intentTexts.some((t) => t?.includes("Inspect ingress"))).toBe(true);
        expect(intentTexts.some((t) => t?.includes("Review scheduler"))).toBe(true);
      });
    });

    it("shows cluster badge when check has a cluster prefix", async () => {
      setupRender({
        nextChecks: ["[prod-cluster] Run kubectl get events -n kube-system"],
      });

      await waitFor(() => {
        const clusterBadges = document.querySelectorAll(".advisory-check-cluster");
        expect(clusterBadges.length).toBeGreaterThanOrEqual(1);
        expect(clusterBadges[0].textContent).toContain("prod-cluster");
      });
    });

    it("renders command preview in monospace code element when command is present", async () => {
      setupRender({
        nextChecks: [
          "Check pod logs: kubectl logs -n default pod/api-server --tail=100",
        ],
      });

      await waitFor(() => {
        const cmdPreview = document.querySelector(".advisory-check-cmd");
        expect(cmdPreview).toBeTruthy();
        expect(cmdPreview?.tagName.toLowerCase()).toBe("code");
        expect(cmdPreview?.textContent).toContain("kubectl");
      });
    });

    it("does not render a single giant raw text blob for long command entries", async () => {
      setupRender({
        nextChecks: [
          "Review API logs: kubectl logs -n production deployment/api-gateway --since=1h --tail=200 --follow=false",
        ],
      });

      await waitFor(() => {
        const rows = document.querySelectorAll(".advisory-check-row");
        expect(rows.length).toBeGreaterThanOrEqual(1);
      });

      // Intent and command should be in separate elements, not one raw text dump
      const intent = document.querySelector(".advisory-check-intent");
      expect(intent).toBeTruthy();
      // Intent should be shorter than the full raw entry
      const fullEntry =
        "Review API logs: kubectl logs -n production deployment/api-gateway --since=1h --tail=200 --follow=false";
      expect((intent?.textContent?.length ?? 0)).toBeLessThan(fullEntry.length);
    });

    it("does not render checks section when nextChecks is empty", async () => {
      setupRender({ nextChecks: [], triageOrder: [] });

      await new Promise((resolve) => setTimeout(resolve, 15));
      const section = document.querySelector(".advisory-next-checks-section");
      expect(section).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Focus Notes
  // -------------------------------------------------------------------------
  describe("Focus notes section", () => {
    it("renders focus note rows", async () => {
      setupRender({
        focusNotes: ["Prioritize cluster-a for incident response"],
      });

      await waitFor(() => {
        const noteRows = document.querySelectorAll(".advisory-focus-note-row");
        expect(noteRows.length).toBeGreaterThanOrEqual(1);
        expect(noteRows[0].textContent).toContain("Prioritize cluster-a");
      });
    });

    it("renders focus notes with demoted secondary label", async () => {
      setupRender({ focusNotes: ["Guidance note"] });

      await waitFor(() => {
        const label = document.querySelector(".advisory-focus-notes-label");
        expect(label).toBeTruthy();
        expect(label?.textContent).toContain("Focus guidance");
      });
    });

    it("does not render focus notes section when array is empty", async () => {
      setupRender({ focusNotes: [], triageOrder: [] });

      await new Promise((resolve) => setTimeout(resolve, 15));
      const section = document.querySelector(".advisory-focus-notes-section");
      expect(section).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Section Coexistence
  // -------------------------------------------------------------------------
  describe("Lower sections coexistence", () => {
    it("renders all four lower sections together correctly", async () => {
      setupRender();

      await waitFor(() => {
        expect(document.querySelector(".advisory-lower-sections")).toBeTruthy();
        expect(document.querySelector(".advisory-concerns-section")).toBeTruthy();
        expect(document.querySelector(".advisory-gaps-section")).toBeTruthy();
        expect(document.querySelector(".advisory-next-checks-section")).toBeTruthy();
        expect(document.querySelector(".advisory-focus-notes-section")).toBeTruthy();
      });
    });

    it("lower sections container exists under review-enrichment-body", async () => {
      setupRender();

      await waitFor(() => {
        const body = document.querySelector(".review-enrichment-body");
        expect(body).toBeTruthy();
        const lowerSections = body?.querySelector(".advisory-lower-sections");
        expect(lowerSections).toBeTruthy();
      });
    });

    it("concerns and gaps sections are inside a top row container", async () => {
      setupRender();

      await waitFor(() => {
        const topRow = document.querySelector(".advisory-lower-row--top");
        expect(topRow).toBeTruthy();
        expect(topRow?.querySelector(".advisory-concerns-section")).toBeTruthy();
        expect(topRow?.querySelector(".advisory-gaps-section")).toBeTruthy();
      });
    });

    it("does not break layout when all arrays are empty", async () => {
      setupRender({
        topConcerns: [],
        evidenceGaps: [],
        nextChecks: [],
        focusNotes: [],
        triageOrder: [],
      });

      await new Promise((resolve) => setTimeout(resolve, 15));

      // Panel itself still exists
      const panel = document.querySelector(".review-enrichment");
      expect(panel).toBeTruthy();

      // None of the lower section elements render
      expect(document.querySelector(".advisory-concerns-section")).toBeNull();
      expect(document.querySelector(".advisory-gaps-section")).toBeNull();
      expect(document.querySelector(".advisory-next-checks-section")).toBeNull();
      expect(document.querySelector(".advisory-focus-notes-section")).toBeNull();
    });
  });
});
