import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { VmalertDiscoveryPanel } from "../components/VmalertDiscoveryPanel";
import type { VmalertSources } from "../types/vmalert";

// Re-export types for test file access
export type { VmalertSources };

// Fixture builders aligned with backend model_vmalert.py contract
const makeVmalertSources = (overrides: Partial<VmalertSources> = {}): VmalertSources => ({
  sources: [],
  total_count: 0,
  source_count: 0,
  discovered_count: 0,
  discovered_but_unverified_count: 0,
  auto_tracked_count: 0,
  manual_count: 0,
  discovery_timestamp: null,
  cluster_context: null,
  ...overrides,
});

describe("VmalertDiscoveryPanel", () => {
  // Reset document theme before each test to ensure consistent CSS
  beforeEach(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  });

  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
  });

  describe("Null-state behavior", () => {
    it("renders nothing when vmalertSources is null", () => {
      render(<VmalertDiscoveryPanel vmalertSources={null} />);
      expect(screen.queryByText(/vmalert/i)).not.toBeInTheDocument();
    });

    it("renders nothing when vmalertSources is undefined", () => {
      render(<VmalertDiscoveryPanel vmalertSources={undefined} />);
      expect(screen.queryByText(/vmalert/i)).not.toBeInTheDocument();
    });
  });

  describe("Zero sources - quiet neutral state", () => {
    it("renders neutral 'Not discovered' when source_count is 0", () => {
      const sources = makeVmalertSources({ source_count: 0 });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/vmalert discovery/i)).toBeInTheDocument();
      expect(screen.getByText("Not discovered")).toBeInTheDocument();
    });

    it("shows quiet message when no sources are present", () => {
      const sources = makeVmalertSources({ source_count: 0 });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/No vmalert sources discovered for this run/i)).toBeInTheDocument();
    });

    it("does NOT show an error or warning when source_count is 0", () => {
      const sources = makeVmalertSources({ source_count: 0 });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      // No error pill, no warning indicator
      expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/⚠/)).not.toBeInTheDocument();
    });
  });

  describe("Discovered state - positive count display", () => {
    it("renders 'vmalert discovered' heading", () => {
      const sources = makeVmalertSources({
        source_count: 2,
        discovered_count: 2,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/vmalert discovery/i)).toBeInTheDocument();
    });

    it("shows source count in status pill", () => {
      const sources = makeVmalertSources({
        source_count: 3,
        discovered_count: 3,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/Discovered · 3/)).toBeInTheDocument();
    });

    it("shows summary metrics for discovered sources", () => {
      const sources = makeVmalertSources({
        source_count: 5,
        discovered_count: 5,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText("5")).toBeInTheDocument();
      expect(screen.getByText("Discovered")).toBeInTheDocument();
    });
  });

  describe("Auto-tracked state", () => {
    it("shows 'Auto-tracked' status when sources are auto-tracked", () => {
      const sources = makeVmalertSources({
        source_count: 2,
        auto_tracked_count: 2,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/Auto-tracked · 2/)).toBeInTheDocument();
    });

    it("shows summary metric for auto-tracked", () => {
      const sources = makeVmalertSources({
        source_count: 3,
        auto_tracked_count: 3,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText("3")).toBeInTheDocument();
      expect(screen.getByText("Auto-tracked")).toBeInTheDocument();
    });
  });

  describe("Manual state", () => {
    it("shows 'Manual' status when sources are manual", () => {
      const sources = makeVmalertSources({
        source_count: 1,
        manual_count: 1,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/Manual · 1/)).toBeInTheDocument();
    });

    it("shows summary metric for manual sources", () => {
      const sources = makeVmalertSources({
        source_count: 2,
        manual_count: 2,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("Manual")).toBeInTheDocument();
    });
  });

  describe("Discovered-but-unverified state - non-fatal warning", () => {
    it("shows warning indicator when discovered_but_unverified_count > 0", () => {
      const sources = makeVmalertSources({
        source_count: 2,
        discovered_but_unverified_count: 2,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/⚠/)).toBeInTheDocument();
    });

    it("shows clear message about unverified sources", () => {
      const sources = makeVmalertSources({
        source_count: 3,
        discovered_but_unverified_count: 3,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/discovered but unverified/i)).toBeInTheDocument();
    });

    it("shows count in unverified message (singular)", () => {
      const sources = makeVmalertSources({
        source_count: 1,
        discovered_but_unverified_count: 1,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/1 source discovered but unverified/i)).toBeInTheDocument();
    });

    it("shows count in unverified message (plural)", () => {
      const sources = makeVmalertSources({
        source_count: 5,
        discovered_but_unverified_count: 5,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/5 sources discovered but unverified/i)).toBeInTheDocument();
    });

    it("renders unverified warning as non-fatal (no error styling)", () => {
      const sources = makeVmalertSources({
        source_count: 2,
        discovered_but_unverified_count: 2,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      // Warning uses warning color (yellow/orange), not error color (red)
      const warningNote = screen.getByText(/discovered but unverified/i).closest("p");
      expect(warningNote).toHaveClass("vmalert-discovery-unverified-note");
    });
  });

  describe("Mixed state priority", () => {
    it("shows manual first when both manual and auto-tracked present", () => {
      const sources = makeVmalertSources({
        source_count: 5,
        manual_count: 2,
        auto_tracked_count: 3,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      // Manual has priority
      expect(screen.getByText(/Manual · 2/)).toBeInTheDocument();
      // But auto-tracked metric still visible
      expect(screen.getByText("3")).toBeInTheDocument();
    });

    it("shows auto-tracked when no manual but auto-tracked present", () => {
      const sources = makeVmalertSources({
        source_count: 3,
        auto_tracked_count: 3,
        manual_count: 0,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/Auto-tracked · 3/)).toBeInTheDocument();
    });

    it("shows discovered-but-unverified when that's the highest priority state", () => {
      const sources = makeVmalertSources({
        source_count: 2,
        discovered_but_unverified_count: 2,
        manual_count: 0,
        auto_tracked_count: 0,
      });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByText(/Discovered \(unverified\) · 2/)).toBeInTheDocument();
    });
  });

  describe("Section heading and structure", () => {
    it("renders with correct section heading", () => {
      const sources = makeVmalertSources({ source_count: 1, manual_count: 1 });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(screen.getByRole("heading", { name: /vmalert discovery/i })).toBeInTheDocument();
    });

    it("renders with correct section id for navigation", () => {
      const sources = makeVmalertSources({ source_count: 1, manual_count: 1 });
      render(<VmalertDiscoveryPanel vmalertSources={sources} />);

      expect(document.getElementById("vmalert-discovery")).toBeInTheDocument();
    });
  });
});