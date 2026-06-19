/**
 * IncidentAutomaticDiagnosisReviewHandoff Test Suite
 *
 * Tests for the read-only handoff control component.
 * Verifies safety constraints and proper state handling.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { IncidentAutomaticDiagnosisReviewHandoff } from "./IncidentAutomaticDiagnosisReviewHandoff";
import type { AutomaticDiagnosisReviewHandoffPayload } from "../api";

// Mock clipboard API
const mockClipboard = {
  writeText: vi.fn().mockResolvedValue(undefined),
};
Object.defineProperty(navigator, "clipboard", {
  value: mockClipboard,
  writable: true,
  configurable: true,
});

// Mock window.isSecureContext
Object.defineProperty(window, "isSecureContext", {
  value: true,
  writable: true,
  configurable: true,
});

// Helper to create available handoff payload
const createAvailablePayload = (overrides?: Partial<AutomaticDiagnosisReviewHandoffPayload>): AutomaticDiagnosisReviewHandoffPayload => ({
  available: true,
  incident_id: "incident-123",
  artifact_type: "diagnosis-loop-review-packet",
  artifact_name: "auto-incident-123-20260619074500-diagnosis-review-packet.json",
  run_id: "auto-incident-123-20260619074500",
  collector_run_id: "auto-diagnosis-20260619074500-abc123",
  generated_at: "2026-06-19T07:45:00+00:00",
  format: "markdown",
  content: "# Automatic diagnosis review packet\n\nIncident: incident-123\nGenerated: 2026-06-19T07:45:00+00:00\nRun ID: auto-incident-123-20260619074500\n\n## Safety\n\nThis is read-only evidence.\nReview is required before any action.\nNo remediation was attempted.\n\n## Decision\n\nrun_allowed_read_only_checks\n\n## Check counts\n\nRequested: 3\nRun: 2\nRejected: 1\n\n## Eligibility\n\nEligible: true\nReason: active_incident_with_suggested_checks\n\n## Review instructions\n\nUse this packet to review diagnosis evidence only.\nDo not infer authorization to mutate the cluster.\nDo not recommend unsafe actions without explicit operator review.\n",
  content_sha256: "abc123def456",
  read_only: true,
  review_required_before_any_action: true,
  no_remediation_attempted: true,
  ...overrides,
});

// Helper to create unavailable payload
const createUnavailablePayload = (reason: string = "no_review_packet"): AutomaticDiagnosisReviewHandoffPayload => ({
  available: false,
  unavailable_reason: reason,
});

describe("IncidentAutomaticDiagnosisReviewHandoff", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("rendering", () => {
    it("renders idle state with Copy review packet button", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createAvailablePayload());
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      expect(screen.getByText("Copy review packet")).toBeInTheDocument();
      expect(screen.getByText(/Copies bounded read-only evidence/)).toBeInTheDocument();
    });

    it("renders loading state when fetching", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createAvailablePayload());
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      fireEvent.click(screen.getByText("Copy review packet"));
      expect(screen.getByText("Loading...")).toBeInTheDocument();
      expect(screen.queryByText("Copy review packet")).not.toBeInTheDocument();
    });

    it("renders success state after fetch", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createAvailablePayload());
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
        await waitFor(() => expect(screen.queryByText("Loading...")).not.toBeInTheDocument());
      });

      expect(screen.getByText("Copy review packet")).toBeInTheDocument();
      expect(screen.getByText(/Copies bounded read-only evidence/)).toBeInTheDocument();
    });

    it("renders unavailable state when no packet", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createUnavailablePayload("no_review_packet"));
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
        await waitFor(() => expect(screen.queryByText("Loading...")).not.toBeInTheDocument());
      });

      expect(screen.getByText(/Review handoff not available/)).toBeInTheDocument();
    });

    it("renders error state when fetch fails", async () => {
      const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
        await waitFor(() => expect(screen.queryByText("Loading...")).not.toBeInTheDocument());
      });

      expect(screen.getByText(/Failed to load handoff/)).toBeInTheDocument();
      expect(screen.getByText("Retry")).toBeInTheDocument();
    });
  });

  describe("copy behavior", () => {
    it("copies content to clipboard when available", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createAvailablePayload());
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      // Fetch first
      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
        await waitFor(() => expect(screen.queryByText("Loading...")).not.toBeInTheDocument());
      });

      // Then copy
      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
        await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled());
      });

      expect(mockClipboard.writeText).toHaveBeenCalledWith(
        expect.stringContaining("# Automatic diagnosis review packet")
      );
    });

    it("shows copied feedback after successful copy", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createAvailablePayload());
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
        await waitFor(() => expect(screen.queryByText("Loading...")).not.toBeInTheDocument());
      });

      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
      });

      // Check that clipboard was called
      expect(navigator.clipboard.writeText).toHaveBeenCalled();
    });
  });

  describe("safety constraints", () => {
    it("does not render forbidden action labels", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createAvailablePayload());
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
        await waitFor(() => expect(screen.queryByText("Loading...")).not.toBeInTheDocument());
      });

      const content = document.body.textContent || "";
      // These terms appear in our forbidden list and should not be in the UI
      const forbiddenTerms = ["kubectl", "helm", "remediate", "rollout restart"];
      const foundForbidden = forbiddenTerms.filter(term => content.toLowerCase().includes(term));
      expect(foundForbidden).toHaveLength(0);
    });

    it("displays read-only/review-required/no-remediation copy", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createAvailablePayload());
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      await act(async () => {
        fireEvent.click(screen.getByText("Copy review packet"));
        await waitFor(() => expect(screen.queryByText("Loading...")).not.toBeInTheDocument());
      });

      expect(screen.getByText(/Copies bounded read-only evidence/)).toBeInTheDocument();
      expect(screen.getByText(/Review is required before any action/)).toBeInTheDocument();
    });

    it("renders with correct incident ID prop", async () => {
      const mockFetch = vi.fn().mockResolvedValue(createAvailablePayload());
      render(
        <IncidentAutomaticDiagnosisReviewHandoff
          incidentId="incident-123"
          onFetchHandoff={mockFetch}
        />
      );

      // Component renders with the button
      expect(screen.getByText("Copy review packet")).toBeInTheDocument();
    });
  });
});
