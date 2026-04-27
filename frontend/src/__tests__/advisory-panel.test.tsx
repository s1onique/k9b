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
  sampleRunsList,
  sampleRun,
  sampleNotifications,
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
    it("renders section-head header with title and timestamp", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment(),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      // Wait for the component to render
      await waitFor(() => {
        expect(screen.getAllByText("Provider advisory")[0]).toBeInTheDocument();
      });

      // Check for the header structure - now uses shared section-head pattern
      const headerSection = document.querySelector(".review-enrichment");
      expect(headerSection).toBeTruthy();

      // Verify section-head exists (shared header pattern)
      const header = headerSection?.querySelector(".section-head");
      expect(header).toBeTruthy();

      // Verify title is present (eyebrow removed during header normalization)
      expect(header?.textContent).toContain("Provider advisory");

      // Verify status badges container exists
      const statusBadges = header?.querySelector(".status-badges");
      expect(statusBadges).toBeTruthy();

      // Verify timestamp appears in the status badges area
      expect(header?.textContent).toContain("Apr 7, 2026 12:00 UTC");
    });

    it("renders status badge in header", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({ status: "success" }),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        const statusBadge = screen.getAllByText("success")[0];
        expect(statusBadge).toBeInTheDocument();
      });
    });
  });

  describe("Executive Summary Strip - New Semantic Classes", () => {
    it("renders advisory-summary-strip with all metric tiles", async () => {
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        const summaryStrip = document.querySelector(".advisory-summary-strip");
        expect(summaryStrip).toBeTruthy();
      });

      // Check for provider display
      const providerDisplay = document.querySelector(".advisory-summary-provider");
      expect(providerDisplay).toBeTruthy();
      expect(providerDisplay?.textContent).toContain("Provider test-provider");

      // Check for metrics container (new semantic class)
      const metricsContainer = document.querySelector(".provider-metrics");
      expect(metricsContainer).toBeTruthy();
    });

    it("metric tiles all have provider-metric class", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a", "cluster-b", "cluster-c"],
          topConcerns: ["Concern A", "Concern B"],
          nextChecks: ["Check A", "Check B"],
          evidenceGaps: ["Gap A"],
        }),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        const metrics = document.querySelectorAll(".provider-metric");
        expect(metrics.length).toBeGreaterThanOrEqual(4);
      });

      // All metrics should have the provider-metric base class
      const metrics = document.querySelectorAll(".provider-metric");
      metrics.forEach((metric) => {
        expect(metric).toHaveClass("provider-metric");
      });
    });

    it("each semantic metric variant exists", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a", "cluster-b"],
          topConcerns: ["Concern A", "Concern B"],
          nextChecks: ["Check A", "Check B"],
          evidenceGaps: ["Gap A", "Gap B"],
        }),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        expect(document.querySelector(".provider-metric--clusters")).toBeTruthy();
        expect(document.querySelector(".provider-metric--concerns")).toBeTruthy();
        expect(document.querySelector(".provider-metric--checks")).toBeTruthy();
        expect(document.querySelector(".provider-metric--gaps")).toBeTruthy();
      });

      // Verify metric values
      const clusters = document.querySelector(".provider-metric--clusters");
      expect(clusters?.textContent).toContain("2");

      const concerns = document.querySelector(".provider-metric--concerns");
      expect(concerns?.textContent).toContain("2");

      const checks = document.querySelector(".provider-metric--checks");
      expect(checks?.textContent).toContain("2");

      const gaps = document.querySelector(".provider-metric--gaps");
      expect(gaps?.textContent).toContain("2");
    });

    it("gaps metric uses provider-metric--gaps, not warning class", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          evidenceGaps: ["Missing edge logs", "Incomplete metrics"],
        }),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        // Should use the new semantic class
        const gapMetric = document.querySelector(".provider-metric--gaps");
        expect(gapMetric).toBeTruthy();
        expect(gapMetric?.textContent).toContain("2"); // 2 gaps
        expect(gapMetric?.textContent).toContain("Gaps");
      });

      // Should NOT use the legacy warning class
      const legacyWarning = document.querySelector(".advisory-summary-metric--warning");
      expect(legacyWarning).toBeNull();
    });
  });

  describe("Chip Semantic Classes", () => {
    it("concern chips have advisory-chip advisory-chip--concern", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          topConcerns: ["Ingress latency", "Storage delays"],
        }),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        const chips = document.querySelectorAll(".advisory-chip--concern");
        expect(chips.length).toBe(2);
      });

      // Both chips should have the base advisory-chip class AND the concern variant
      const chips = document.querySelectorAll(".advisory-chip--concern");
      chips.forEach((chip) => {
        expect(chip).toHaveClass("advisory-chip");
        expect(chip).toHaveClass("advisory-chip--concern");
      });

      expect(chips[0].textContent).toContain("Ingress latency");
      expect(chips[1].textContent).toContain("Storage delays");
    });

    it("focus chips have advisory-chip advisory-chip--focus", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          focusNotes: ["Prioritize cluster-a"],
        }),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        const chip = document.querySelector(".advisory-chip--focus");
        expect(chip).toBeTruthy();
      });

      // Focus chip should have both base and variant classes
      const chip = document.querySelector(".advisory-chip--focus");
      expect(chip).toHaveClass("advisory-chip");
      expect(chip).toHaveClass("advisory-chip--focus");
      expect(chip.textContent).toContain("Focus note");
    });

    it("chips are rendered in advisory-chip-row container", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          topConcerns: ["Concern A"],
          focusNotes: ["Focus note"],
        }),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        const chipRow = document.querySelector(".advisory-chip-row");
        expect(chipRow).toBeTruthy();
      });

      // Chips should be inside the chip row
      const chipRow = document.querySelector(".advisory-chip-row");
      const chips = chipRow?.querySelectorAll(".advisory-chip");
      expect(chips?.length).toBeGreaterThanOrEqual(1);
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        expect(screen.getAllByText("Provider advisory")[0]).toBeInTheDocument();
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

      // Then advisory-lower-sections container with new structured sections
      const gridIndex = Array.from(childElements || []).findIndex(
        (el) => el.className.includes("advisory-lower-sections")
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
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
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        const focusElements = document.querySelectorAll(".advisory-cluster-focus");
        expect(focusElements.length).toBeGreaterThanOrEqual(1);
      });

      const focusElement = document.querySelector(".advisory-cluster-focus");
      expect(focusElement?.textContent).toContain("Focus:");
      expect(focusElement?.textContent).toContain("cluster-a");
    });

    it("focus text is readable (not washed-out muted)", async () => {
      const runPayload = {
        ...sampleRun,
        reviewEnrichment: createMockEnrichment({
          triageOrder: ["cluster-a"],
          focusNotes: ["Focus note for cluster-a"],
        }),
        reviewEnrichmentStatus: createMockEnrichmentStatus(),
      };

      const payloads = {
        "/api/run": runPayload,
        "/api/runs": sampleRunsList,
        "/api/fleet": sampleFleet,
        "/api/proposals": sampleProposals,
        "/api/notifications": sampleNotifications,
      };
      vi.stubGlobal("fetch", createFetchMock(payloads));
      render(<App />);

      await waitFor(() => {
        const focusElement = document.querySelector(".advisory-cluster-focus");
        expect(focusElement).toBeTruthy();
      });

      // Focus text should NOT have the muted class (which would make it washed out)
      const focusElement = document.querySelector(".advisory-cluster-focus");
      expect(focusElement).not.toHaveClass("muted");
      
      // Focus hint should use the advisory-focus-fg color
      const focusHint = document.querySelector(".advisory-focus-hint");
      expect(focusHint).toBeTruthy();
    });
  });

});
