import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AlertmanagerSourcesPanel } from "../App";

// Import types for fixture creation
import type { AlertmanagerSources, AlertmanagerSource } from "../types";

// Re-export types for test file access
export type { AlertmanagerSources, AlertmanagerSource };

// Realistic fixture data aligned with backend/model contract
// Backend values: origin ∈ {"manual", "alertmanager-crd", "prometheus-crd-config", "service-heuristic"}
// Backend values: state ∈ {"discovered", "auto-tracked", "degraded", "missing", "manual"}
const makeAlertmanagerSource = (overrides: Partial<AlertmanagerSource> = {}): AlertmanagerSource => ({
  source_id: "monitoring/alertmanager-main",
  endpoint: "http://alertmanager-main.monitoring.svc.cluster.local:9093",
  namespace: "monitoring",
  name: "alertmanager-main",
  origin: "alertmanager-crd",
  state: "auto-tracked",
  discovered_at: "2026-04-18T10:30:00Z",
  verified_at: "2026-04-18T10:30:15Z",
  last_check: "2026-04-18T12:00:00Z",
  last_error: null,
  verified_version: "v0.27.1",
  confidence_hints: ["crd-detected", "service-monitor", "kubernetes-discovery"],
  is_manual: false,
  is_tracking: true,
  can_disable: false,
  can_promote: true,
  display_origin: "Alertmanager CRD",
  display_state: "tracked",
  provenance_summary: "Discovered via Alertmanager CRD",
  ...overrides,
});

const makeAlertmanagerSources = (overrides: Partial<AlertmanagerSources> = {}): AlertmanagerSources => ({
  sources: [],
  total_count: 0,
  tracked_count: 0,
  manual_count: 0,
  degraded_count: 0,
  missing_count: 0,
  discovery_timestamp: null,
  cluster_context: null,
  ...overrides,
});

describe("AlertmanagerSourcesPanel", () => {
  // Reset document theme before each test to ensure consistent CSS
  beforeEach(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  });

  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
  });

  describe("Panel structure", () => {
    it("renders the panel with correct section header", () => {
      const sources = makeAlertmanagerSources({
        sources: [],
        total_count: 0,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.getByText("Alertmanager sources")).toBeInTheDocument();
      expect(screen.getByText("Alertmanager discovery")).toBeInTheDocument();
    });

    it("renders empty state when no sources are present", () => {
      const sources = makeAlertmanagerSources({
        sources: [],
        total_count: 0,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.getByText(/No alertmanager sources discovered for this run\./)).toBeInTheDocument();
    });

    it("renders sources table when sources are present", () => {
      const sources = makeAlertmanagerSources({
        sources: [makeAlertmanagerSource()],
        total_count: 1,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // Table should be visible
      expect(screen.getByRole("table")).toBeInTheDocument();
      // Empty state message should not be visible
      expect(screen.queryByText(/No alertmanager sources discovered for this run\./)).not.toBeInTheDocument();
    });
  });

  describe("Summary metrics", () => {
    it("displays all five summary metric items", () => {
      const sources = makeAlertmanagerSources({
        total_count: 5,
        tracked_count: 3,
        manual_count: 2,
        degraded_count: 0,
        missing_count: 0,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // Check values are present (use regex to be unique)
      expect(screen.getByText(/^5$/)).toBeInTheDocument(); // Total
      expect(screen.getByText(/^3$/)).toBeInTheDocument(); // Tracked
      expect(screen.getByText(/^2$/)).toBeInTheDocument(); // Manual

      // Check labels are present
      expect(screen.getByText("Total")).toBeInTheDocument();
      expect(screen.getByText("Tracked")).toBeInTheDocument();
      expect(screen.getByText("Manual")).toBeInTheDocument();
      expect(screen.getByText("Degraded")).toBeInTheDocument();
      expect(screen.getByText("Missing")).toBeInTheDocument();
    });

    it("renders metric values with prominent styling", () => {
      const sources = makeAlertmanagerSources({
        total_count: 42,
        tracked_count: 30,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // Verify the metric value is rendered as strong (prominent)
      const totalMetric = screen.getByText("42");
      expect(totalMetric.tagName).toBe("STRONG");
      expect(totalMetric).toHaveClass("alertmanager-sources-metric-value");
    });
  });

  describe("Table headers", () => {
    it("renders all seven column headers", () => {
      const sources = makeAlertmanagerSources({
        sources: [makeAlertmanagerSource()],
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.getByText("State")).toBeInTheDocument();
      expect(screen.getByText("Origin")).toBeInTheDocument();
      expect(screen.getByText("Endpoint")).toBeInTheDocument();
      expect(screen.getByText("Namespace / Name")).toBeInTheDocument();
      expect(screen.getByText("Version")).toBeInTheDocument();
      expect(screen.getByText("Provenance")).toBeInTheDocument();
      expect(screen.getByText("Last Error")).toBeInTheDocument();
    });
  });

  describe("Source row rendering", () => {
    it("renders a single source with all fields", () => {
      const source = makeAlertmanagerSource();
      const sources = makeAlertmanagerSources({
        sources: [source],
        total_count: 1,
        tracked_count: 1,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // State pill - display_state is "tracked", which maps to healthy class
      expect(screen.getByText("tracked")).toBeInTheDocument();

      // Origin (display_origin is "Alertmanager CRD" for this fixture)
      expect(screen.getByText("Alertmanager CRD")).toBeInTheDocument();

      // Endpoint should be truncated in a code element
      const endpointCode = document.querySelector(".alertmanager-source-endpoint-code");
      expect(endpointCode).toBeInTheDocument();
      expect(endpointCode?.textContent).toContain("alertmanager-main");
      expect(endpointCode?.textContent).toContain("…");

      // Namespace / Name
      expect(screen.getByText("monitoring / alertmanager-main")).toBeInTheDocument();

      // Version
      expect(screen.getByText("v0.27.1")).toBeInTheDocument();

      // Provenance (displayed from provenance_summary field)
      expect(screen.getByText("Discovered via Alertmanager CRD")).toBeInTheDocument();

      // Last Error - should show em-dash since no error
      expect(screen.getByText("—")).toBeInTheDocument();
    });

    it("renders multiple sources", () => {
      const sources = makeAlertmanagerSources({
        sources: [
          makeAlertmanagerSource({ source_id: "src-1" }),
          makeAlertmanagerSource({ source_id: "src-2" }),
        ],
        total_count: 3,
        tracked_count: 2,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // Check row count - 1 header + 2 data rows = 3 rows total
      const rows = screen.getAllByRole("row");
      expect(rows).toHaveLength(3);
      
      // Check both state pills are rendered
      expect(screen.getAllByText("tracked")).toHaveLength(2);
    });
  });

  describe("State-based styling classes", () => {
    it("applies 'healthy' state class for tracked sources", () => {
      const source = makeAlertmanagerSource({ display_state: "tracked" });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      const statePill = screen.getByText("tracked");
      // Check the row has the correct state class (for styling purposes)
      const row = statePill.closest("tr");
      expect(row).toHaveClass("alertmanager-source-healthy");
    });

    it("applies 'caution' state class for discovered sources", () => {
      const source = makeAlertmanagerSource({ display_state: "discovered" });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      const statePill = screen.getByText("discovered");
      const row = statePill.closest("tr");
      expect(row).toHaveClass("alertmanager-source-caution");
    });

    it("applies 'warning' state class for degraded sources", () => {
      const source = makeAlertmanagerSource({ display_state: "degraded" });
      const sources = makeAlertmanagerSources({ sources: [source], degraded_count: 1 });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      const statePill = screen.getByText("degraded");
      const row = statePill.closest("tr");
      expect(row).toHaveClass("alertmanager-source-warning");
    });

    it("applies 'muted' state class for missing sources", () => {
      const source = makeAlertmanagerSource({ display_state: "missing" });
      const sources = makeAlertmanagerSources({ sources: [source], missing_count: 1 });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      const statePill = screen.getByText("missing");
      const row = statePill.closest("tr");
      expect(row).toHaveClass("alertmanager-source-muted");
    });

    it("applies 'default' state class for unknown states", () => {
      const source = makeAlertmanagerSource({ display_state: "unknown-state" });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      const statePill = screen.getByText("unknown-state");
      const row = statePill.closest("tr");
      expect(row).toHaveClass("alertmanager-source-default");
    });

    it("maps 'manual' display_state to healthy styling", () => {
      const source = makeAlertmanagerSource({ display_state: "manual", is_manual: true });
      const sources = makeAlertmanagerSources({ sources: [source], manual_count: 1 });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      const statePill = screen.getByText("manual");
      const row = statePill.closest("tr");
      expect(row).toHaveClass("alertmanager-source-healthy");
    });
  });

  describe("Mixed states rendering", () => {
    it("renders multiple sources with different states", () => {
      const sources = makeAlertmanagerSources({
        sources: [
          makeAlertmanagerSource({ source_id: "src-1", display_state: "tracked" }),
          makeAlertmanagerSource({ source_id: "src-2", display_state: "discovered" }),
          makeAlertmanagerSource({ source_id: "src-3", display_state: "degraded" }),
          makeAlertmanagerSource({ source_id: "src-4", display_state: "missing" }),
        ],
        total_count: 4,
        tracked_count: 1,
        manual_count: 0,
        degraded_count: 1,
        missing_count: 1,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.getByText("4")).toBeInTheDocument();
      expect(screen.getByText("tracked")).toBeInTheDocument();
      expect(screen.getByText("discovered")).toBeInTheDocument();
      expect(screen.getByText("degraded")).toBeInTheDocument();
      expect(screen.getByText("missing")).toBeInTheDocument();
    });
  });

  describe("Error rendering", () => {
    it("displays error text with proper styling when last_error is present", () => {
      const source = makeAlertmanagerSource({
        display_state: "degraded",
        last_error: "Connection timeout after 30s",
      });
      const sources = makeAlertmanagerSources({
        sources: [source],
        degraded_count: 1,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      const errorText = screen.getByText("Connection timeout after 30s");
      expect(errorText).toBeInTheDocument();
      expect(errorText).toHaveClass("alertmanager-source-error-text");
    });

    it("shows em-dash placeholder when no error is present", () => {
      const source = makeAlertmanagerSource({ last_error: null });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.getByText("—")).toBeInTheDocument();
    });

    it("handles long error messages gracefully", () => {
      const longError = "This is a very long error message that exceeds the maximum display width and should be truncated with an ellipsis";
      const source = makeAlertmanagerSource({
        display_state: "degraded",
        last_error: longError,
      });
      const sources = makeAlertmanagerSources({
        sources: [source],
        degraded_count: 1,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // Check that some text from the error is visible (truncated version)
      const errorContainer = document.querySelector(".alertmanager-source-error");
      expect(errorContainer).toBeInTheDocument();
      // The title attribute should contain the full error
      expect(errorContainer?.innerHTML).toContain("title=");
    });
  });

  describe("Discovery timestamp", () => {
    it("renders discovery timestamp when present", () => {
      const sources = makeAlertmanagerSources({
        sources: [makeAlertmanagerSource()],
        discovery_timestamp: "2026-04-18T12:30:00Z",
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // Check that "Discovered" text is present
      const discoveredElements = screen.getAllByText(/Discovered/);
      expect(discoveredElements.length).toBeGreaterThanOrEqual(1);
    });

    it("does not render timestamp section when discovery_timestamp is null", () => {
      const sources = makeAlertmanagerSources({
        sources: [],
        discovery_timestamp: null,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.queryByText(/^Discovered/)).not.toBeInTheDocument();
    });
  });

  describe("Cluster context display", () => {
    it("renders cluster context when present", () => {
      const sources = makeAlertmanagerSources({
        sources: [makeAlertmanagerSource()],
        cluster_context: "prod-us-east-1",
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.getByText("Context: prod-us-east-1")).toBeInTheDocument();
    });

    it("does not render context when cluster_context is null", () => {
      const sources = makeAlertmanagerSources({
        sources: [],
        cluster_context: null,
      });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.queryByText(/Context:/)).not.toBeInTheDocument();
    });
  });

  describe("Namespace and name combination", () => {
    it("renders namespace and name combined when both are present", () => {
      const source = makeAlertmanagerSource({
        namespace: "monitoring",
        name: "alertmanager-main",
      });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.getByText("monitoring / alertmanager-main")).toBeInTheDocument();
    });

    it("renders only namespace when name is null", () => {
      const source = makeAlertmanagerSource({
        namespace: "monitoring",
        name: null,
      });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      expect(screen.getByText("monitoring")).toBeInTheDocument();
      // Check that data rows don't contain "/ " pattern for namespace/name
      const rows = screen.getAllByRole("row");
      const dataRows = rows.slice(1); // Skip header
      dataRows.forEach(row => {
        const namespaceCell = row.querySelector(".alertmanager-source-namespace");
        if (namespaceCell) {
          expect(namespaceCell.textContent).not.toMatch(/\/ /);
        }
      });
    });

    it("renders em-dash when both namespace and name are null", () => {
      const source = makeAlertmanagerSource({
        namespace: null,
        name: null,
      });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // At least one em-dash should be visible in the namespace column
      const emDashes = screen.getAllByText("—");
      expect(emDashes.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("Endpoint truncation", () => {
    it("truncates long endpoint URLs", () => {
      const longEndpoint = "http://very-long-hostname.very-long-subdomain.example.com:9093/api/v1/status";
      const source = makeAlertmanagerSource({
        endpoint: longEndpoint,
      });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // The component truncates at 50 characters
      expect(screen.getByText(/…/)).toBeInTheDocument();
    });
  });

  describe("Version display", () => {
    it("displays version when verified_version is present", () => {
      const source = makeAlertmanagerSource({ verified_version: "v0.27.1" });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // Version appears in the table cell (not the header)
      const versionElements = screen.getAllByText("v0.27.1");
      expect(versionElements.length).toBeGreaterThanOrEqual(1);
      // Check it's in a table cell, not a header
      expect(versionElements[0].closest("td")).toBeInTheDocument();
    });

    it("shows em-dash when verified_version is null", () => {
      const source = makeAlertmanagerSource({ verified_version: null });
      const sources = makeAlertmanagerSources({ sources: [source] });

      render(<AlertmanagerSourcesPanel sources={sources} />);

      // Version column and error column both show em-dash in table rows
      const emDashes = screen.getAllByText("—");
      expect(emDashes.length).toBeGreaterThanOrEqual(2); // At least version + error columns
    });
  });
});