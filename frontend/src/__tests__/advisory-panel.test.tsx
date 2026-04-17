// Advisory Panel Component Tests
//
// Tests for the advisory panel components in App.tsx:
// - Header structure (title, timestamp, status)
// - Executive summary strip (metrics, tags, hints)
// - Cluster overview cards (rank, name, concerns, focus notes)
// - Section coexistence and order
// - Empty state handling

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import {
  createFetchMock,
  createStorageMock,
  sampleFleet,
  sampleProposals,
  sampleRun,
} from "./fixtures";

// Test data fixtures
const createMockEnrichment = (overrides = {}) => ({
  status: "success" as const,
  provider: "test-provider",
  timestamp: "2026-04-07T12:00:00Z",
  summary: "Test enrichment summary",
  triageOrder: ["cluster-a", "cluster-b"],
  topConcerns: ["Ingress latency", "Storage delays"],
  evidenceGaps: ["Edge logs"],
  nextChecks: ["Validate ingress", "Collect metrics"],
  focusNotes: ["Prioritize cluster-a"],
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

describe("Advisory Panel Components", () => {
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

  describe("Header Structure", () => {
    it("renders advisory-panel-header with title and timestamp", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment(),
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

      // Wait for the component to render
      await waitFor(() => {
        expect(screen.getAllByText("Provider-assisted advisory")[0]).toBeInTheDocument();
      });

      // Check for the header structure
      const headerSection = document.querySelector(".review-enrichment");
      expect(headerSection).toBeTruthy();

      // Verify advisory-panel-header exists
      const header = headerSection?.querySelector(".advisory-panel-header");
      expect(header).toBeTruthy();

      // Verify advisory-header-left contains the title
      const headerLeft = header?.querySelector(".advisory-header-left");
      expect(headerLeft).toBeTruthy();
      expect(headerLeft?.textContent).toContain("Review enrichment");
      expect(headerLeft?.textContent).toContain("Provider-assisted advisory");

      // Verify advisory-meta-timestamp contains the timestamp
      const headerMeta = header?.querySelector(".advisory-header-meta");
      expect(headerMeta).toBeTruthy();
      expect(headerMeta?.textContent).toContain("Apr 7, 2026 12:00 UTC");
    });

    it("renders status badge in header", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({ status: "success" }),
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

      await waitFor(() => {
        const statusBadge = screen.getAllByText("success")[0];
        expect(statusBadge).toBeInTheDocument();
      });
    });
  });

  describe("Executive Summary Strip", () => {
    it("renders advisory-summary-strip with all metrics", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a", "cluster-b"],
          topConcerns: ["Ingress latency", "Storage delays"],
          nextChecks: ["Validate ingress", "Collect metrics"],
          evidenceGaps: ["Edge logs"],
        }),
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

      await waitFor(() => {
        const summaryStrip = document.querySelector(".advisory-summary-strip");
        expect(summaryStrip).toBeTruthy();
      });

      // Check for provider display
      const providerDisplay = document.querySelector(".advisory-summary-provider");
      expect(providerDisplay).toBeTruthy();
      expect(providerDisplay?.textContent).toContain("Provider test-provider");

      // Check for metrics container
      const metricsContainer = document.querySelector(".advisory-summary-metrics");
      expect(metricsContainer).toBeTruthy();

      // Check for individual metric elements
      const metrics = document.querySelectorAll(".advisory-summary-metric");
      expect(metrics.length).toBeGreaterThanOrEqual(3); // Clusters, Concerns, Checks

      // Verify metric values are present (2 clusters from triageOrder)
      const clusterMetric = Array.from(metrics).find(
        (m) => m.textContent?.includes("Cluster")
      );
      expect(clusterMetric?.textContent).toContain("2");
      expect(clusterMetric?.textContent).toContain("Clusters");

      // Verify concerns count (2 concerns)
      const concernMetric = Array.from(metrics).find(
        (m) => m.textContent?.includes("Concern")
      );
      expect(concernMetric?.textContent).toContain("2");
      expect(concernMetric?.textContent).toContain("Concerns");

      // Verify next checks count (2 checks)
      const checksMetric = Array.from(metrics).find(
        (m) => m.textContent?.includes("Check")
      );
      expect(checksMetric?.textContent).toContain("2");
      expect(checksMetric?.textContent).toContain("Checks");
    });

    it("renders concern tags when concerns exist", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          topConcerns: ["Ingress latency", "Storage delays"],
        }),
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

      await waitFor(() => {
        const tagsContainer = document.querySelector(".advisory-summary-tags");
        expect(tagsContainer).toBeTruthy();
      });

      // Check for individual tags (shows first 2)
      const tags = document.querySelectorAll(".advisory-tag");
      expect(tags.length).toBe(2);
      expect(tags[0].textContent).toContain("Ingress latency");
      expect(tags[1].textContent).toContain("Storage delays");
    });

    it("renders focus note hint when focus notes exist", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          focusNotes: ["Prioritize cluster-a"],
        }),
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

      await waitFor(() => {
        const hintContainer = document.querySelector(".advisory-summary-hint");
        expect(hintContainer).toBeTruthy();
        expect(hintContainer?.textContent).toContain("Focus note");
      });
    });

    it("shows warning styling for evidence gaps", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          evidenceGaps: ["Missing edge logs", "Incomplete metrics"],
        }),
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

      await waitFor(() => {
        const gapMetric = document.querySelector(".advisory-summary-metric--warning");
        expect(gapMetric).toBeTruthy();
        expect(gapMetric?.textContent).toContain("2"); // 2 gaps
        expect(gapMetric?.textContent).toContain("Gaps");
      });
    });
  });

  describe("Cluster Overview Cards", () => {
    it("renders cluster cards for each cluster in triage order", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a", "cluster-b"],
          topConcerns: ["cluster-a concern", "cluster-b concern"],
        }),
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

      await waitFor(() => {
        const clusterGrid = document.querySelector(".advisory-cluster-grid");
        expect(clusterGrid).toBeTruthy();
      });

      // Check for cluster cards
      const clusterCards = document.querySelectorAll(".advisory-cluster-card");
      expect(clusterCards.length).toBe(2);

      // Verify first cluster (rank 1)
      expect(clusterCards[0].textContent).toContain("#1");
      expect(clusterCards[0].textContent).toContain("cluster-a");

      // Verify second cluster (rank 2)
      expect(clusterCards[1].textContent).toContain("#2");
      expect(clusterCards[1].textContent).toContain("cluster-b");
    });

    it("renders cluster card header with rank and name", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a", "cluster-b"],
        }),
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

      await waitFor(() => {
        const cardHeaders = document.querySelectorAll(".advisory-cluster-card-header");
        expect(cardHeaders.length).toBe(2);
      });

      // Check first card header
      const firstHeader = document.querySelector(".advisory-cluster-card-header");
      const rank = firstHeader?.querySelector(".advisory-cluster-rank");
      const name = firstHeader?.querySelector(".advisory-cluster-name");
      
      expect(rank?.textContent).toContain("#1");
      expect(name?.textContent).toContain("cluster-a");
    });

    it("attaches cluster-specific concerns to matching clusters", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a", "cluster-b"],
          topConcerns: ["cluster-a ingress latency", "cluster-b storage delays", "Generic concern"],
        }),
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

      await waitFor(() => {
        const clusterCards = document.querySelectorAll(".advisory-cluster-card");
        expect(clusterCards.length).toBe(2);
      });

      // First cluster should have cluster-a specific concern
      const firstCard = document.querySelector(".advisory-cluster-card");
      expect(firstCard?.textContent).toContain("cluster-a ingress latency");

      // Second cluster should have cluster-b specific concern
      const secondCard = document.querySelectorAll(".advisory-cluster-card")[1];
      expect(secondCard.textContent).toContain("cluster-b storage delays");
    });

    it("renders primary concern in cluster card", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a", "cluster-b"],
          topConcerns: ["High CPU", "Memory pressure"],
        }),
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

      await waitFor(() => {
        const concernElements = document.querySelectorAll(".advisory-cluster-concern");
        expect(concernElements.length).toBeGreaterThan(0);
      });

      const concernElement = document.querySelector(".advisory-cluster-concern");
      expect(concernElement?.textContent).toBeTruthy();
    });
  });

  describe("Section Coexistence and Order", () => {
    it("renders sections in correct order: summary, cards, details", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment(),
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

      await waitFor(() => {
        expect(screen.getAllByText("Provider-assisted advisory")[0]).toBeInTheDocument();
      });

      const reviewEnrichment = document.querySelector(".review-enrichment");
      expect(reviewEnrichment).toBeTruthy();

      // Get all direct children of the review-enrichment section body
      const body = reviewEnrichment?.querySelector(".review-enrichment-body");
      expect(body).toBeTruthy();

      const childElements = body?.children;
      expect(childElements?.length).toBeGreaterThanOrEqual(4);

      // Verify order: advisory-summary-strip first
      expect(childElements?.[0].className).toContain("advisory-summary-strip");

      // Then advisory-cluster-grid
      expect(childElements?.[1].className).toContain("advisory-cluster-grid");

      // Then advisory-summary-collapsible (if summary exists)
      if (childElements?.[2].className.includes("advisory-summary-collapsible")) {
        expect(childElements?.[2].className).toContain("advisory-summary-collapsible");
      }

      // Then review-enrichment-grid with lists
      const gridIndex = Array.from(childElements || []).findIndex(
        (el) => el.className.includes("review-enrichment-grid")
      );
      expect(gridIndex).toBeGreaterThan(0);
    });

    it("renders collapsible provider summary when enrichment has summary", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          summary: "Test enrichment summary",
        }),
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

      await waitFor(() => {
        const collapsible = document.querySelector(".advisory-summary-collapsible");
        expect(collapsible).toBeTruthy();
        expect(collapsible?.textContent).toContain("View provider summary");
      });
    });
  });

  describe("Empty State Handling", () => {
    it("renders empty state message when enrichment is disabled", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: undefined,
        reviewEnrichmentStatus: createMockEnrichmentStatus({
          status: "policy-disabled",
        }),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": { runs: [], totalCount: 0 },
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
      };
      globalThis.fetch = createFetchMock(payloads);
      render(<App />);

      await waitFor(() => {
        const disabledEl = screen.getAllByText(/not configured|disabled/i)[0];
        expect(disabledEl).toBeInTheDocument();
      });
    });

    it("does not render summary strip when triageOrder is empty", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: [],
        }),
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

      // Wait a tick for any conditional rendering
      await new Promise((resolve) => setTimeout(resolve, 10));

      const summaryStrip = document.querySelector(".advisory-summary-strip");
      expect(summaryStrip).toBeNull();
    });
  });

  describe("Focus Notes in Cluster Cards", () => {
    it("renders focus notes in matching cluster cards", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a", "cluster-b"],
          focusNotes: ["Prioritize cluster-a for investigation"],
        }),
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

      await waitFor(() => {
        const focusElements = document.querySelectorAll(".advisory-cluster-focus");
        expect(focusElements.length).toBeGreaterThanOrEqual(1);
      });

      const focusElement = document.querySelector(".advisory-cluster-focus");
      expect(focusElement?.textContent).toContain("Focus:");
      expect(focusElement?.textContent).toContain("cluster-a");
    });
  });
});