/**
 * IncidentListPanel tests
 *
 * Verifies:
 * - API client list call parses incidents
 * - Empty incident list renders empty state
 * - Incidents render status/severity/class/object
 * - snapshot_bundle_id renders when present
 * - No remediation/action buttons exist (strong assertions)
 * - Component handles API error with generic message
 * - Read-only notice is always displayed
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IncidentListPanel } from "../components/IncidentListPanel";

// Mock the API functions
vi.mock("../api", () => ({
  listIncidents: vi.fn(),
  getIncident: vi.fn(),
}));

import { listIncidents } from "../api";

// Fixtures
const mockIncident = {
  incident_id: "default-pod-test-pod-crash_loop",
  source_candidate_id: "default-pod-test-pod-crash_loop",
  namespace: "default",
  object_kind: "Pod",
  object_name: "test-pod",
  raw_object_kind: null,
  class: "crash_loop",
  severity: "error",
  status: "open",
  first_observed_at: "2026-01-01T12:00:00Z",
  last_observed_at: "2026-01-01T14:00:00Z",
  signals: [
    {
      source: "pod",
      reason: "CrashLoopBackOff",
      message: "Back-off 5m40s restarting",
      captured_at: "2026-01-01T14:00:00Z",
    },
  ],
  evidence_needed: ["pod_logs", "pod_describe"],
  snapshot_bundle_id: "default-20260101-140000",
  review_packet_available: false,
  review_packet_id: null,
  suppressed_reason: null,
  duplicate_of: null,
  resolved_at: null,
  resolution_notes: null,
};

const mockIncidentWithBundle = {
  ...mockIncident,
  snapshot_bundle_id: "default-20260101-140000",
};

const mockIncidentWithoutBundle = {
  ...mockIncident,
  snapshot_bundle_id: null,
};

describe("IncidentListPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("API client list call parses incidents", () => {
    it("calls listIncidents without filter when no status selected", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [],
        total: 0,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(listIncidents).toHaveBeenCalledTimes(1);
      });
      expect(listIncidents).toHaveBeenCalledWith(undefined);
    });

    it("calls listIncidents with status filter when selected", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [],
        total: 0,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(listIncidents).toHaveBeenCalled();
      });

      const select = screen.getByRole("combobox");
      await act(async () => {
        await user.selectOptions(select, "open");
      });

      await waitFor(() => {
        expect(listIncidents).toHaveBeenLastCalledWith("open");
      }, { timeout: 2000 });
    });

    it("parses incident list response correctly", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/1 incident/)).toBeInTheDocument();
      });
    });
  });

  describe("Empty incident list renders empty state", () => {
    it("shows empty state message when no incidents", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [],
        total: 0,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/No incidents recorded/i)).toBeInTheDocument();
      });
    });

    it("shows filtered empty state when no matching status", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [],
        total: 0,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.queryByText(/No incidents recorded/i)).toBeInTheDocument();
      });

      const select = screen.getByRole("combobox");
      await act(async () => {
        await user.selectOptions(select, "resolved");
      });

      await waitFor(() => {
        const panel = document.getElementById("incident-list");
        expect(panel?.textContent).toContain("Resolved");
      });
    });
  });

  describe("Incidents render status/severity/class/object", () => {
    it("renders incident severity badge", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      });
    });

    it("renders incident status badge", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/Open/i)).toBeInTheDocument();
      });
    });

    it("renders incident class", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/crash loop/i)).toBeInTheDocument();
      });
    });

    it("renders object kind and name", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        const incidentRow = document.querySelector(".incident-row");
        expect(incidentRow).not.toBeNull();
        expect(incidentRow?.textContent).toContain("Pod");
        expect(incidentRow?.textContent).toContain("test-pod");
      });
    });

    it("renders namespace", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        const incidentRow = document.querySelector(".incident-row");
        expect(incidentRow).not.toBeNull();
        expect(incidentRow?.textContent).toContain("default");
      });
    });

    it("renders incident_id", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/default-pod-test-pod-crash_loop/i)).toBeInTheDocument();
      });
    });
  });

  describe("snapshot_bundle_id renders when present", () => {
    it("shows bundle ID when incident has snapshot_bundle_id", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncidentWithBundle],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/default-20260101-140000/i)).toBeInTheDocument();
      });
    });

    it("does not show bundle section when snapshot_bundle_id is null", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncidentWithoutBundle],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.queryByText(/Bundle:/i)).not.toBeInTheDocument();
      });
    });
  });

  describe("review_packet fields render correctly", () => {
    it("shows review packet available badge and ID when review_packet_available=true", async () => {
      const incidentWithReviewPacket = {
        ...mockIncident,
        snapshot_bundle_id: "default-20260101-140000",
        review_packet_available: true,
        review_packet_id: "review-packet-abc123",
      };
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [incidentWithReviewPacket],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/Review Packet:/i)).toBeInTheDocument();
        // Use specific selector for the badge element
        const badge = document.querySelector(".review-packet-badge");
        expect(badge).not.toBeNull();
        expect(badge?.textContent).toBe("Available");
        expect(screen.getByText(/review-packet-abc123/i)).toBeInTheDocument();
      });
    });

    it("shows 'Not generated yet' when review_packet_available=false", async () => {
      const incidentWithoutReviewPacket = {
        ...mockIncident,
        snapshot_bundle_id: "default-20260101-140000",
        review_packet_available: false,
        review_packet_id: null,
      };
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [incidentWithoutReviewPacket],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/Review Packet:/i)).toBeInTheDocument();
        expect(screen.getByText(/Not generated yet/i)).toBeInTheDocument();
      });
    });

    it("shows 'Not generated yet' when review_packet_id is null even if review_packet_available=true", async () => {
      const incidentWithFlagOnly = {
        ...mockIncident,
        snapshot_bundle_id: "default-20260101-140000",
        review_packet_available: true,
        review_packet_id: null,
      };
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [incidentWithFlagOnly],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/Review Packet:/i)).toBeInTheDocument();
        expect(screen.getByText(/Not generated yet/i)).toBeInTheDocument();
      });
    });

    it("renders review packet section for multiple incidents with different states", async () => {
      const incidents = [
        {
          ...mockIncident,
          incident_id: "incident-1",
          snapshot_bundle_id: "bundle-1",
          review_packet_available: true,
          review_packet_id: "review-1",
        },
        {
          ...mockIncident,
          incident_id: "incident-2",
          snapshot_bundle_id: "bundle-2",
          review_packet_available: false,
          review_packet_id: null,
        },
      ];
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents,
        total: 2,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/review-1/i)).toBeInTheDocument();
        expect(screen.getByText(/Not generated yet/i)).toBeInTheDocument();
      });
    });
  });

  describe("Read-only notice is always displayed", () => {
    it("displays read-only notice with all required text", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [],
        total: 0,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/No incidents recorded/i)).toBeInTheDocument();
      });

      // Use specific selector for the notice div
      const notice = document.querySelector(".incident-notice");
      expect(notice).not.toBeNull();
      expect(notice?.textContent).toContain("No remediation");
      expect(notice?.textContent?.toLowerCase()).toContain("mutation");
      expect(notice?.textContent).toContain("LLM actions");
    });
  });

  describe("No remediation/action buttons exist", () => {
    it("has no remediation action buttons", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/1 incident/)).toBeInTheDocument();
      });

      // Get all buttons in the incident panel
      const panel = document.getElementById("incident-list");
      const buttons = panel?.querySelectorAll("button") || [];
      const buttonTexts = Array.from(buttons).map(b => b.textContent?.toLowerCase() || "");

      // Should NOT have any remediation/action buttons
      const forbiddenActions = [
        "remediate", "resolve", "suppress", "delete", "patch",
        "apply", "execute", "create", "update", "edit", "remove"
      ];

      forbiddenActions.forEach(action => {
        expect(buttonTexts.some(t => t.includes(action))).toBe(false);
      });

      // Should ONLY have "Refresh incidents" as the action button
      const refreshButtons = buttons;
      expect(refreshButtons.length).toBe(1);
      expect(refreshButtons[0]?.textContent).toContain("Refresh incidents");
    });

    it("has only refresh button as action control with correct aria-label", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/1 incident/)).toBeInTheDocument();
      });

      // Use aria-label to get the specific button
      const refreshButton = screen.getByRole("button", { name: /refresh incidents/i });
      expect(refreshButton).toBeInTheDocument();
      expect(refreshButton).toHaveAttribute("aria-label", "Refresh incidents");
    });
  });

  describe("Component handles API error with generic message", () => {
    it("shows error message when API fails", async () => {
      // Use a resolved promise followed by rejection for more predictable behavior
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [],
        total: 0,
      });

      render(<IncidentListPanel />);

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText(/No incidents recorded/i)).toBeInTheDocument();
      });

      // Now reject the next call
      vi.mocked(listIncidents).mockRejectedValueOnce(new Error("Server error"));

      // Click refresh to trigger error
      const refreshButton = screen.getByRole("button", { name: /refresh incidents/i });
      await act(async () => {
        await refreshButton.click();
      });

      await waitFor(() => {
        const errorDiv = document.querySelector(".incident-error");
        expect(errorDiv).not.toBeNull();
        expect(errorDiv?.textContent).toContain("Failed to load incidents");
        expect(errorDiv?.textContent).toContain("Server error");
      });
    });

    it("allows retry via refresh button after error", async () => {
      const user = userEvent.setup();

      // First call returns error
      vi.mocked(listIncidents).mockRejectedValueOnce(new Error("Server error"));

      render(<IncidentListPanel />);

      // Wait for error state
      await waitFor(() => {
        const errorDiv = document.querySelector(".incident-error");
        expect(errorDiv).not.toBeNull();
      });

      // Change mock to return success on next call
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      // Click refresh to retry
      const refreshButton = screen.getByRole("button", { name: /refresh incidents/i });
      await act(async () => {
        await user.click(refreshButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/1 incident/)).toBeInTheDocument();
      });

      // Error should be gone
      expect(document.querySelector(".incident-error")).toBeNull();
    });
  });

  describe("Loading state", () => {
    it("shows loading message while fetching", async () => {
      vi.mocked(listIncidents).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ incidents: [], total: 0 }), 1000))
      );

      render(<IncidentListPanel />);

      expect(screen.getByText(/loading incidents/i)).toBeInTheDocument();
    });

    it("disables filter while loading", async () => {
      vi.mocked(listIncidents).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ incidents: [], total: 0 }), 1000))
      );

      render(<IncidentListPanel />);

      const select = screen.getByRole("combobox");
      expect(select).toBeDisabled();
    });
  });
});
