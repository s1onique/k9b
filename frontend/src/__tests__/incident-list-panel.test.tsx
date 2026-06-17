/**
 * IncidentListPanel tests
 *
 * Verifies:
 * - API client list call parses incidents
 * - Empty incident list renders empty state
 * - Incidents render status/severity/class/object
 * - latest_snapshot_bundle_id renders when present
 * - review_packet object fields render correctly (status-based)
 * - No remediation/action buttons exist (strong assertions)
 * - Component handles API error with generic message
 * - Read-only notice is always displayed
 * - Expandable details functionality (View/Hide details)
 * - Loading state during detail fetch
 * - Error state when detail fetch fails
 * - Stale response protection
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

import { listIncidents, getIncident } from "../api";
import type { IncidentSummaryPayload, IncidentDetailPayload } from "../api";

// Fixtures using new IncidentSummaryPayload shape
const mockIncident: IncidentSummaryPayload = {
  incident_id: "default-pod-test-pod-crash_loop",
  namespace: "default",
  object_kind: "Pod",
  object_name: "test-pod",
  raw_object_kind: null,
  candidate_class: "crash_loop",
  severity: "error",
  status: "open",
  first_observed_at: "2026-01-01T12:00:00Z",
  last_observed_at: "2026-01-01T14:00:00Z",
  signal_count: 1,
  evidence_count: 2,
  latest_snapshot_bundle_id: "default-20260101-140000",
  review_packet: {
    status: "not_generated",
    id: null,
    generated_at: null,
    error_message: null,
  },
  suppressed_reason: null,
  duplicate_of: null,
  resolved_at: null,
  resolution_notes: null,
};

const mockIncidentWithBundle = {
  ...mockIncident,
  latest_snapshot_bundle_id: "default-20260101-140000",
};

const mockIncidentWithoutBundle = {
  ...mockIncident,
  latest_snapshot_bundle_id: null,
};

// Full detail fixture using IncidentDetailPayload
const mockIncidentDetail: IncidentDetailPayload = {
  ...mockIncident,
  source_candidate_id: "candidate-abc",
  signals: [
    {
      source: "metrics-collector",
      reason: "HighErrorRate",
      message: "Error rate exceeded threshold",
      captured_at: "2026-01-01T13:00:00Z",
    },
  ],
  evidence_needed: ["kubectl logs for test-pod"],
  evidence_links: [
    {
      incident_id: "default-pod-test-pod-crash_loop",
      artifact_id: "artifact-abc-123",
      role: "snapshot",
      attached_at: "2026-01-01T14:00:00Z",
    },
  ],
  events: [
    {
      event_id: "event-1",
      incident_id: "default-pod-test-pod-crash_loop",
      event_type: "created",
      actor: "system",
      occurred_at: "2026-01-01T12:00:00Z",
      message: "Incident created",
    },
  ],
};

// Second incident for stale response tests
const mockIncident2: IncidentSummaryPayload = {
  incident_id: "default-pod-test-pod-oom",
  namespace: "default",
  object_kind: "Pod",
  object_name: "test-pod-2",
  raw_object_kind: null,
  candidate_class: "oom_kill",
  severity: "warning",
  status: "investigating",
  first_observed_at: "2026-01-01T10:00:00Z",
  last_observed_at: "2026-01-01T15:00:00Z",
  signal_count: 3,
  evidence_count: 1,
  latest_snapshot_bundle_id: "default-20260101-150000",
  review_packet: {
    status: "available",
    id: "review-packet-xyz",
    generated_at: "2026-01-01T12:00:00Z",
    error_message: null,
  },
  suppressed_reason: null,
  duplicate_of: null,
  resolved_at: null,
  resolution_notes: null,
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

  describe("latest_snapshot_bundle_id renders when present", () => {
    it("shows bundle ID when incident has latest_snapshot_bundle_id", async () => {
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
    it("shows review packet available badge and ID when review_packet.status=available", async () => {
      const incidentWithReviewPacket = {
        ...mockIncident,
        latest_snapshot_bundle_id: "default-20260101-140000",
        review_packet: {
          status: "available",
          id: "review-packet-abc123",
          generated_at: "2026-01-01T12:00:00Z",
          error_message: null,
        },
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

    it("shows 'Not generated yet' when review_packet.status=not_generated", async () => {
      const incidentWithoutReviewPacket = {
        ...mockIncident,
        latest_snapshot_bundle_id: "default-20260101-140000",
        review_packet: {
          status: "not_generated",
          id: null,
          generated_at: null,
          error_message: null,
        },
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

    it("shows 'Generating...' when review_packet.status=generating", async () => {
      const incidentGenerating = {
        ...mockIncident,
        latest_snapshot_bundle_id: "default-20260101-140000",
        review_packet: {
          status: "generating",
          id: "review-packet-pending",
          generated_at: null,
          error_message: null,
        },
      };
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [incidentGenerating],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/Review Packet:/i)).toBeInTheDocument();
        expect(screen.getByText(/Generating\.\.\./i)).toBeInTheDocument();
      });
    });

    it("shows error message when review_packet.status=failed", async () => {
      const incidentFailed = {
        ...mockIncident,
        latest_snapshot_bundle_id: "default-20260101-140000",
        review_packet: {
          status: "failed",
          id: null,
          generated_at: null,
          error_message: "LLM unavailable",
        },
      };
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [incidentFailed],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/Review Packet:/i)).toBeInTheDocument();
        expect(screen.getByText(/Failed: LLM unavailable/i)).toBeInTheDocument();
      });
    });

    it("renders review packet section for multiple incidents with different states", async () => {
      const incidents = [
        {
          ...mockIncident,
          incident_id: "incident-1",
          latest_snapshot_bundle_id: "bundle-1",
          review_packet: {
            status: "available",
            id: "review-1",
            generated_at: "2026-01-01T12:00:00Z",
            error_message: null,
          },
        },
        {
          ...mockIncident,
          incident_id: "incident-2",
          latest_snapshot_bundle_id: "bundle-2",
          review_packet: {
            status: "not_generated",
            id: null,
            generated_at: null,
            error_message: null,
          },
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
    it("has no remediation action buttons in row", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/1 incident/)).toBeInTheDocument();
      });

      // Get all buttons in the incident row
      const incidentRow = document.querySelector(".incident-row");
      const buttons = incidentRow?.querySelectorAll("button") || [];
      const buttonTexts = Array.from(buttons).map(b => b.textContent?.toLowerCase() || "");

      // Should NOT have any remediation/action buttons
      const forbiddenActions = [
        "remediate", "resolve", "suppress", "delete", "patch",
        "apply", "execute", "create", "update", "edit", "remove"
      ];

      forbiddenActions.forEach(action => {
        expect(buttonTexts.some(t => t.includes(action))).toBe(false);
      });
    });

    it("has only view/hide details as action control with correct aria attributes", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/1 incident/)).toBeInTheDocument();
      });

      // Use aria-label to get the specific button
      const detailsButton = screen.getByRole("button", { name: /view details/i });
      expect(detailsButton).toBeInTheDocument();
      expect(detailsButton).toHaveAttribute("aria-expanded", "false");
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

  // =============================================================================
  // Expandable details tests
  // =============================================================================

  describe("Expandable details", () => {
    it("shows 'View details' button for each incident row", async () => {
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });
    });

    it("clicking 'View details' calls getIncident() with the incident_id", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      vi.mocked(getIncident).mockResolvedValueOnce(mockIncidentDetail);

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        expect(getIncident).toHaveBeenCalledWith("default-pod-test-pod-crash_loop");
      });
    });

    it("shows loading state while detail fetch is pending", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      // Use a slow promise that won't resolve immediately
      vi.mocked(getIncident).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockIncidentDetail), 1000))
      );

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      // Should show loading text
      expect(screen.getByText(/loading incident details/i)).toBeInTheDocument();
    });

    it("successful fetch renders IncidentDetailPanel content", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      vi.mocked(getIncident).mockResolvedValueOnce(mockIncidentDetail);

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        // IncidentDetailPanel should be rendered
        expect(screen.getByText("Signals")).toBeInTheDocument();
        expect(screen.getByText("Evidence links")).toBeInTheDocument();
        expect(screen.getByText("Timeline")).toBeInTheDocument();
      });

      // Button should now say "Hide details"
      expect(screen.getByRole("button", { name: /hide details/i })).toBeInTheDocument();
    });

    it("clicking 'Hide details' collapses the detail panel", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      vi.mocked(getIncident).mockResolvedValueOnce(mockIncidentDetail);

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      // Expand
      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Signals")).toBeInTheDocument();
      });

      // Collapse
      const hideButton = screen.getByRole("button", { name: /hide details/i });
      await act(async () => {
        await user.click(hideButton);
      });

      await waitFor(() => {
        // Detail panel should be gone
        expect(screen.queryByText("Signals")).not.toBeInTheDocument();
        // View details button should be back
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });
    });

    it("failed fetch shows generic error message", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      vi.mocked(getIncident).mockRejectedValueOnce(new Error("Network error: Connection refused"));

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/unable to load incident details/i)).toBeInTheDocument();
      });

      // Should NOT expose raw exception details
      expect(screen.queryByText(/network error/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/connection refused/i)).not.toBeInTheDocument();
    });

    it("expanding one incident then another renders only the selected incident's detail", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident, mockIncident2],
        total: 2,
      });
      vi.mocked(getIncident).mockResolvedValueOnce(mockIncidentDetail);

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/2 incidents/)).toBeInTheDocument();
      });

      // Click view details on first incident
      const viewButtons = screen.getAllByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButtons[0]);
      });

      await waitFor(() => {
        expect(getIncident).toHaveBeenCalledWith("default-pod-test-pod-crash_loop");
      });

      // Setup mock for second incident
      const mockIncident2Detail: IncidentDetailPayload = {
        ...mockIncident2,
        source_candidate_id: "candidate-xyz",
        signals: [
          {
            source: "events-collector",
            reason: "OOMKill",
            message: "Container was OOM killed",
            captured_at: "2026-01-01T13:00:00Z",
          },
        ],
        evidence_needed: [],
        evidence_links: [],
        events: [],
      };
      vi.mocked(getIncident).mockResolvedValueOnce(mockIncident2Detail);

      // Click view details on second incident
      await act(async () => {
        await user.click(viewButtons[1]);
      });

      await waitFor(() => {
        // Should show signals from second incident
        expect(screen.getByText(/OOMKill/i)).toBeInTheDocument();
        // First incident detail should not be visible
        expect(screen.queryByText(/HighErrorRate/i)).not.toBeInTheDocument();
      });
    });

    it("stale response from a previous incident does not overwrite the currently selected incident", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident, mockIncident2],
        total: 2,
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByText(/2 incidents/)).toBeInTheDocument();
      });

      // Setup slow response for first incident
      const slowPromise = new Promise<IncidentDetailPayload>((resolve) => {
        setTimeout(() => resolve(mockIncidentDetail), 500);
      });
      vi.mocked(getIncident).mockImplementation(
        (id: string) => id === mockIncident.incident_id ? slowPromise : Promise.reject(new Error("Not found"))
      );

      const viewButtons = screen.getAllByRole("button", { name: /view details/i });

      // Click view details on first incident (slow)
      await act(async () => {
        await user.click(viewButtons[0]);
      });

      // Should show loading
      expect(screen.getByText(/loading incident details/i)).toBeInTheDocument();

      // Quickly click view details on second incident (fast - will fail)
      await act(async () => {
        await user.click(viewButtons[1]);
      });

      // Should show error for second incident
      await waitFor(() => {
        expect(screen.getByText(/unable to load incident details/i)).toBeInTheDocument();
      });

      // Wait for slow promise to resolve
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 600));
      });

      // Error from second incident should still be visible (stale response from first should not overwrite)
      expect(screen.getByText(/unable to load incident details/i)).toBeInTheDocument();
      // First incident detail should not appear - check for detail panel content unique to detail view
      // "Evidence links" section only appears in the detail panel, not in list rows
      expect(screen.queryByText(/Evidence links/i)).not.toBeInTheDocument();
    });

    it("no remediation/action buttons are introduced in detail panel", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      vi.mocked(getIncident).mockResolvedValueOnce(mockIncidentDetail);

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Signals")).toBeInTheDocument();
      });

      // Check detail panel for forbidden buttons
      const detailPanel = document.querySelector(".incident-detail-panel");
      const buttons = detailPanel?.querySelectorAll("button") || [];
      const buttonTexts = Array.from(buttons).map(b => b.textContent?.toLowerCase() || "");

      const forbiddenActions = [
        "remediate", "resolve", "suppress", "delete", "patch",
        "apply", "execute", "create", "update", "edit", "remove"
      ];

      forbiddenActions.forEach(action => {
        expect(buttonTexts.some(t => t.includes(action))).toBe(false);
      });
    });

    it("old fields are not required for detail panel", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });

      // Create detail without old fields
      const detailWithoutOldFields: IncidentDetailPayload = {
        ...mockIncidentDetail,
      };

      // Explicitly ensure old fields are not present
      expect((detailWithoutOldFields as Record<string, unknown>).review_packet_available).toBeUndefined();
      expect((detailWithoutOldFields as Record<string, unknown>).review_packet_id).toBeUndefined();
      expect((detailWithoutOldFields as Record<string, unknown>).snapshot_bundle_id).toBeUndefined();

      vi.mocked(getIncident).mockResolvedValueOnce(detailWithoutOldFields);

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        // Should render without errors
        expect(screen.getByText("Signals")).toBeInTheDocument();
      });
    });
  });

  // =============================================================================
  // Detail error recovery tests
  // =============================================================================

  describe("Detail error recovery retry/hide buttons", () => {
    it("failed detail fetch shows Retry details and Hide details buttons", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      vi.mocked(getIncident).mockRejectedValueOnce(new Error("Network error"));

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        // Error message should be visible
        expect(screen.getByText(/unable to load incident details/i)).toBeInTheDocument();
        // Retry details button should be visible
        expect(screen.getByRole("button", { name: /retry details/i })).toBeInTheDocument();
        // Hide details button should be visible
        expect(screen.getByRole("button", { name: /hide details/i })).toBeInTheDocument();
      });
    });

    it("clicking Retry details calls getIncident again and renders detail on success", async () => {
      const user = userEvent.setup();
      // Track call count to return appropriate responses
      let callCount = 0;
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      vi.mocked(getIncident).mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          // First call fails
          return Promise.reject(new Error("Network error"));
        }
        // Second call (retry) succeeds
        return Promise.resolve(mockIncidentDetail);
      });

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      // Click view details - will fail
      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /retry details/i })).toBeInTheDocument();
      });

      // Click retry
      const retryButton = screen.getByRole("button", { name: /retry details/i });
      await act(async () => {
        await user.click(retryButton);
      });

      // Verify getIncident was called twice
      expect(getIncident).toHaveBeenCalledTimes(2);
      expect(getIncident).toHaveBeenLastCalledWith("default-pod-test-pod-crash_loop");

      // Verify IncidentDetailPanel is rendered on success
      await waitFor(() => {
        expect(screen.getByText("Signals")).toBeInTheDocument();
        expect(screen.getByText("Evidence links")).toBeInTheDocument();
        expect(screen.getByText("Timeline")).toBeInTheDocument();
      });

      // Button should now say "Hide details"
      expect(screen.getByRole("button", { name: /hide details/i })).toBeInTheDocument();
    });

    it("clicking Hide details after failure collapses and clears the error", async () => {
      const user = userEvent.setup();
      vi.mocked(listIncidents).mockResolvedValueOnce({
        incidents: [mockIncident],
        total: 1,
      });
      vi.mocked(getIncident).mockRejectedValueOnce(new Error("Network error"));

      render(<IncidentListPanel />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      });

      // Click view details - will fail
      const viewButton = screen.getByRole("button", { name: /view details/i });
      await act(async () => {
        await user.click(viewButton);
      });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /hide details/i })).toBeInTheDocument();
        expect(screen.getByText(/unable to load incident details/i)).toBeInTheDocument();
      });

      // Click hide details
      const hideButton = screen.getByRole("button", { name: /hide details/i });
      await act(async () => {
        await user.click(hideButton);
      });

      await waitFor(() => {
        // Error should be cleared
        expect(screen.queryByText(/unable to load incident details/i)).not.toBeInTheDocument();
        // View details button should be back
        expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
        // Retry button should be gone
        expect(screen.queryByRole("button", { name: /retry details/i })).not.toBeInTheDocument();
      });
    });
  });
});
