import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AlertmanagerSnapshotPanel } from "../App";

// Import types for fixture creation
import type { AlertmanagerCompact } from "../types";

// Re-export types for test file access
export type { AlertmanagerCompact };

// Helper to create realistic Alertmanager compact snapshot fixtures
const makeAlertmanagerCompact = (overrides: Partial<AlertmanagerCompact> = {}): AlertmanagerCompact => ({
  status: "available",
  alert_count: 0,
  severity_counts: {},
  state_counts: {},
  top_alert_names: [],
  affected_namespaces: [],
  affected_clusters: [],
  affected_services: [],
  truncated: false,
  captured_at: "2026-04-18T10:30:00Z",
  ...overrides,
});

describe("AlertmanagerSnapshotPanel", () => {
  // Reset document theme before each test to ensure consistent CSS
  beforeEach(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  });

  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
  });

  describe("Panel structure", () => {
    it("renders the panel with correct section header", () => {
      const compact = makeAlertmanagerCompact({ status: "available" });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("Alertmanager context")).toBeInTheDocument();
      expect(screen.getByText("Alertmanager snapshot")).toBeInTheDocument();
    });

    it("renders 'Captured' status pill when status is available", () => {
      const compact = makeAlertmanagerCompact({ status: "available" });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("Captured")).toBeInTheDocument();
    });

    it("renders 'Captured' status pill when status is ok", () => {
      const compact = makeAlertmanagerCompact({ status: "ok" });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("Captured")).toBeInTheDocument();
    });

    it("shows unavailable message when status is not available or ok", () => {
      const compact = makeAlertmanagerCompact({ status: "no-artifact" });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // Status label is humanized: "no-artifact" → "Not captured"
      expect(screen.getByText(/Alertmanager snapshot is not available: not captured/)).toBeInTheDocument();
    });

    it("renders empty state message when compact is null", () => {
      render(<AlertmanagerSnapshotPanel compact={null} />);

      expect(screen.getByText(/Alertmanager snapshot data is not available/)).toBeInTheDocument();
    });

    it("renders empty state message when compact is undefined", () => {
      render(<AlertmanagerSnapshotPanel compact={undefined} />);

      expect(screen.getByText(/Alertmanager snapshot data is not available/)).toBeInTheDocument();
    });

    it("shows 'No active alerts captured' when alert_count is 0", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 0,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("No active alerts captured.")).toBeInTheDocument();
    });
  });

  describe("Total alert count display", () => {
    it("renders alert_count prominently in a metric block", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 42,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // Alert count should be in a strong element with metric value class
      const metricValue = screen.getByText("42");
      expect(metricValue).toBeInTheDocument();
      expect(metricValue.tagName).toBe("STRONG");
      expect(metricValue).toHaveClass("alertmanager-metric-value");
    });

    it("renders 'Total alerts' label below the count", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 42,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("Total alerts")).toBeInTheDocument();
    });

    it("metric block has correct CSS class for visual separation", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 42,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      const metricBlock = document.querySelector(".alertmanager-snapshot-metric");
      expect(metricBlock).toBeInTheDocument();
      expect(metricBlock).toHaveClass("alertmanager-snapshot-metric");
    });
  });

  describe("Severity breakdown", () => {
    it("renders severity counts as distinct badges", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 25,
        severity_counts: {
          critical: 5,
          warning: 10,
          info: 10,
        },
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // Each severity should be a separate badge
      expect(screen.getByText("critical: 5")).toBeInTheDocument();
      expect(screen.getByText("warning: 10")).toBeInTheDocument();
      expect(screen.getByText("info: 10")).toBeInTheDocument();
    });

    it("applies color variant class for severity badges", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 25,
        severity_counts: {
          critical: 5,
        },
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      const criticalBadge = document.querySelector(".alertmanager-severity-badge--critical");
      expect(criticalBadge).toBeInTheDocument();
    });

    it("does not render severity section when severity_counts is empty", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 0,
        severity_counts: {},
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.queryByText("By severity")).not.toBeInTheDocument();
    });

    it("renders severity section label", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 10,
        severity_counts: { warning: 10 },
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("By severity")).toBeInTheDocument();
    });

    it("renders severity badges in a flex wrap container", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 25,
        severity_counts: {
          critical: 5,
          warning: 10,
          info: 10,
        },
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      const list = document.querySelector(".alertmanager-severity-list");
      expect(list).toBeInTheDocument();
    });
  });

  describe("State breakdown", () => {
    it("renders state counts as distinct badges", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 15,
        state_counts: {
          firing: 10,
          pending: 3,
          resolved: 2,
        },
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("firing: 10")).toBeInTheDocument();
      expect(screen.getByText("pending: 3")).toBeInTheDocument();
      expect(screen.getByText("resolved: 2")).toBeInTheDocument();
    });

    it("does not render state section when state_counts is empty", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 0,
        state_counts: {},
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.queryByText("By state")).not.toBeInTheDocument();
    });

    it("renders state section label", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 15,
        state_counts: { firing: 15 },
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("By state")).toBeInTheDocument();
    });

    it("renders state badges with correct CSS class", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 15,
        state_counts: { firing: 15 },
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      const badges = document.querySelectorAll(".alertmanager-state-badge");
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  describe("Top alerts display", () => {
    it("renders top alert names in a list", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 10,
        top_alert_names: ["HighMemoryUsage", "HighCPUUsage", "PodRestart"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("HighMemoryUsage")).toBeInTheDocument();
      expect(screen.getByText("HighCPUUsage")).toBeInTheDocument();
      expect(screen.getByText("PodRestart")).toBeInTheDocument();
    });

    it("limits top alerts to 5 items", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 20,
        top_alert_names: [
          "Alert1", "Alert2", "Alert3", "Alert4", "Alert5", "Alert6", "Alert7",
        ],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // Only first 5 should be visible
      expect(screen.getByText("Alert1")).toBeInTheDocument();
      expect(screen.getByText("Alert5")).toBeInTheDocument();
      expect(screen.queryByText("Alert6")).not.toBeInTheDocument();
      expect(screen.queryByText("Alert7")).not.toBeInTheDocument();
    });

    it("does not render top alerts section when top_alert_names is empty", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 0,
        top_alert_names: [],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.queryByText("Top alerts")).not.toBeInTheDocument();
    });

    it("renders top alerts section label", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 5,
        top_alert_names: ["TestAlert"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("Top alerts")).toBeInTheDocument();
    });

    it("renders alerts in a list element", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 5,
        top_alert_names: ["Alert1", "Alert2"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      const list = document.querySelector(".alertmanager-top-alerts");
      expect(list).toBeInTheDocument();
    });
  });

  describe("Affected namespaces", () => {
    it("renders namespaces as tags with overflow handling", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 15,
        affected_namespaces: ["monitoring", "kube-system", "default"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("monitoring")).toBeInTheDocument();
      expect(screen.getByText("kube-system")).toBeInTheDocument();
      expect(screen.getByText("default")).toBeInTheDocument();
    });

    it("shows count in section label", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 15,
        affected_namespaces: ["ns1", "ns2", "ns3"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText(/Affected namespaces \(3\)/)).toBeInTheDocument();
    });

    it("limits displayed namespaces to 10 with '+N more' indicator", () => {
      const namespaces = Array.from({ length: 15 }, (_, i) => `namespace-${i}`);
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 15,
        affected_namespaces: namespaces,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // First 10 should be visible
      expect(screen.getByText("namespace-0")).toBeInTheDocument();
      expect(screen.getByText("namespace-9")).toBeInTheDocument();
      // 11th should not be visible
      expect(screen.queryByText("namespace-10")).not.toBeInTheDocument();
      // "+5 more" should be visible
      expect(screen.getByText("+5 more")).toBeInTheDocument();
    });

    it("does not render namespace section when affected_namespaces is empty", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 0,
        affected_namespaces: [],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.queryByText(/^Affected namespaces/)).not.toBeInTheDocument();
    });

    it("renders namespace tags with correct CSS class", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 5,
        affected_namespaces: ["monitoring"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      const tags = document.querySelectorAll(".alertmanager-tag");
      expect(tags.length).toBeGreaterThan(0);
    });

    it("renders '+N more' tag with modifier class", () => {
      const namespaces = Array.from({ length: 15 }, (_, i) => `ns-${i}`);
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 15,
        affected_namespaces: namespaces,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      const moreTag = document.querySelector(".alertmanager-tag--more");
      expect(moreTag).toBeInTheDocument();
      expect(moreTag?.textContent).toBe("+5 more");
    });
  });

  describe("Affected services", () => {
    it("renders services as tags with overflow handling", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 20,
        affected_services: ["api-server", "frontend", "backend"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("api-server")).toBeInTheDocument();
      expect(screen.getByText("frontend")).toBeInTheDocument();
      expect(screen.getByText("backend")).toBeInTheDocument();
    });

    it("shows count in section label", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 20,
        affected_services: ["svc1", "svc2"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText(/Affected services \(2\)/)).toBeInTheDocument();
    });

    it("limits displayed services to 10 with '+N more' indicator", () => {
      const services = Array.from({ length: 15 }, (_, i) => `service-${i}`);
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 15,
        affected_services: services,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // First 10 should be visible
      expect(screen.getByText("service-0")).toBeInTheDocument();
      expect(screen.getByText("service-9")).toBeInTheDocument();
      // 11th should not be visible
      expect(screen.queryByText("service-10")).not.toBeInTheDocument();
      // "+5 more" should be visible
      expect(screen.getByText("+5 more")).toBeInTheDocument();
    });

    it("does not render services section when affected_services is empty", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 0,
        affected_services: [],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.queryByText(/^Affected services/)).not.toBeInTheDocument();
    });
  });

  describe("Affected clusters", () => {
    it("renders clusters as tags", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 10,
        affected_clusters: ["prod-cluster", "staging-cluster"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("prod-cluster")).toBeInTheDocument();
      expect(screen.getByText("staging-cluster")).toBeInTheDocument();
    });

    it("shows count in section label", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 10,
        affected_clusters: ["cluster1", "cluster2", "cluster3"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText(/Affected clusters \(3\)/)).toBeInTheDocument();
    });

    it("does not limit cluster count (no truncation for small lists)", () => {
      const clusters = Array.from({ length: 8 }, (_, i) => `cluster-${i}`);
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 10,
        affected_clusters: clusters,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // All clusters should be visible (no 10-item limit for clusters)
      expect(screen.getByText("cluster-0")).toBeInTheDocument();
      expect(screen.getByText("cluster-7")).toBeInTheDocument();
      // No "+N more" indicator for clusters
      const moreTag = document.querySelector(".alertmanager-tag--more");
      if (moreTag) {
        // Only the last namespace/service section might have more
        const nsSection = screen.getByText(/^Affected namespaces/);
        expect(nsSection).toBeInTheDocument();
      }
    });
  });

  describe("Captured timestamp", () => {
    it("renders captured timestamp", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 10,
        captured_at: "2026-04-18T10:30:00Z",
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // Both status pill and timestamp contain "Captured" - check for the pill specifically
      expect(screen.getByText("Captured")).toBeInTheDocument();
      // Also verify the timestamp text is present (the "Captured" timestamp line)
      expect(screen.getByText(/Apr 18, 2026 10:30 UTC/)).toBeInTheDocument();
    });

    it("shows truncated indicator when data is truncated", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 10,
        truncated: true,
        captured_at: "2026-04-18T10:30:00Z",
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText(/Truncated/)).toBeInTheDocument();
    });

    it("does not show truncated indicator when data is not truncated", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 10,
        truncated: false,
        captured_at: "2026-04-18T10:30:00Z",
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.queryByText(/Truncated/)).not.toBeInTheDocument();
    });
  });

  describe("Theme compatibility", () => {
    it("renders correctly in dark theme", () => {
      document.documentElement.setAttribute("data-theme", "dark");
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 42,
        severity_counts: { critical: 10, warning: 20, info: 12 },
        state_counts: { firing: 30, pending: 12 },
        top_alert_names: ["HighMemory", "PodRestart"],
        affected_namespaces: ["monitoring", "kube-system"],
        affected_services: ["api-server"],
        affected_clusters: ["prod"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // Panel should render without errors
      expect(screen.getByText("Alertmanager snapshot")).toBeInTheDocument();
      expect(screen.getByText("42")).toBeInTheDocument();
    });

    it("renders correctly in solarized light theme", () => {
      document.documentElement.setAttribute("data-theme", "solarized-light");
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 42,
        severity_counts: { critical: 10, warning: 20, info: 12 },
        state_counts: { firing: 30, pending: 12 },
        top_alert_names: ["HighMemory", "PodRestart"],
        affected_namespaces: ["monitoring", "kube-system"],
        affected_services: ["api-server"],
        affected_clusters: ["prod"],
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // Panel should render without errors
      expect(screen.getByText("Alertmanager snapshot")).toBeInTheDocument();
      expect(screen.getByText("42")).toBeInTheDocument();
    });
  });

  describe("Empty and edge cases", () => {
    it("renders with minimal data (only alert_count > 0)", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 5,
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      expect(screen.getByText("Alertmanager snapshot")).toBeInTheDocument();
      expect(screen.getByText("5")).toBeInTheDocument();
    });

    it("renders with all sections populated", () => {
      const compact = makeAlertmanagerCompact({
        status: "available",
        alert_count: 100,
        severity_counts: {
          critical: 10,
          warning: 30,
          info: 40,
          debug: 20,
        },
        state_counts: {
          firing: 60,
          pending: 30,
          resolved: 10,
        },
        top_alert_names: [
          "HighMemoryUsage",
          "HighCPUUsage",
          "PodRestart",
          "DiskPressure",
          "NetworkLatency",
        ],
        affected_namespaces: [
          "monitoring",
          "kube-system",
          "default",
          "ingress-nginx",
          "cert-manager",
        ],
        affected_clusters: ["prod-us-east-1", "prod-eu-west-1"],
        affected_services: [
          "api-gateway",
          "frontend",
          "backend",
          "database",
          "cache",
          "queue",
        ],
        truncated: false,
        captured_at: "2026-04-18T10:30:00Z",
      });
      render(<AlertmanagerSnapshotPanel compact={compact} />);

      // Verify all sections render
      expect(screen.getByText("100")).toBeInTheDocument();
      expect(screen.getByText("critical: 10")).toBeInTheDocument();
      expect(screen.getByText("firing: 60")).toBeInTheDocument();
      expect(screen.getByText("HighMemoryUsage")).toBeInTheDocument();
      expect(screen.getByText("monitoring")).toBeInTheDocument();
      expect(screen.getByText("api-gateway")).toBeInTheDocument();
      expect(screen.getByText("prod-us-east-1")).toBeInTheDocument();
    });
  });
});
