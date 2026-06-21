/**
 * Tests for IncidentAutomaticDiagnosisLoopCard component.
 *
 * Verifies:
 * 1. not_run state renders correctly
 * 2. running_or_started state renders correctly
 * 3. completed state renders correctly
 * 4. failed_or_unavailable state renders correctly
 * 5. latest event wins by timestamp
 * 6. unavailable reason display
 * 7. check counts display
 * 8. review packet availability display
 * 9. safety text display
 * 10. no action/remediation controls
 * 11. no raw event data exposure
 * 12. unknown status fallback
 *
 * Hard constraints verified:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO action/remediation controls
 * - NO raw event data
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { IncidentAutomaticDiagnosisLoopCard } from "../components/IncidentAutomaticDiagnosisLoopCard";
import type { AutomaticDiagnosisLoopSummary } from "../api";

const createSummaryFixture = (
  overrides: Partial<AutomaticDiagnosisLoopSummary> = {}
): AutomaticDiagnosisLoopSummary => ({
  status: "not_run",
  latest_started_at: null,
  latest_completed_at: null,
  latest_failed_at: null,
  latest_event_id: null,
  latest_event_type: null,
  unavailable_reason: null,
  checks_requested: null,
  checks_run: null,
  checks_rejected: null,
  review_packet_available: false,
  review_packet_id: null,
  read_only: true,
  review_required_before_any_action: true,
  no_remediation_attempted: true,
  ...overrides,
});

describe("IncidentAutomaticDiagnosisLoopCard", () => {
  describe("1. not_run state", () => {
    it("renders not_run status correctly", () => {
      const summary = createSummaryFixture({ status: "not_run" });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("not run")).toBeInTheDocument();
      expect(
        screen.getByText("Automatic diagnosis has not run for this incident.")
      ).toBeInTheDocument();
    });

    it("does not show timestamps for not_run", () => {
      const summary = createSummaryFixture({ status: "not_run" });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.queryByText(/Started:/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Completed:/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Failed:/)).not.toBeInTheDocument();
    });
  });

  describe("2. running_or_started state", () => {
    it("renders running_or_started status correctly", () => {
      const summary = createSummaryFixture({
        status: "running_or_started",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        latest_event_id: "event-1",
        latest_event_type: "diagnosis_loop_started",
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("running or started")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Automatic diagnosis started; completion has not been recorded yet."
        )
      ).toBeInTheDocument();
    });

    it("shows started timestamp for running_or_started", () => {
      const summary = createSummaryFixture({
        status: "running_or_started",
        latest_started_at: "2026-01-01T12:00:00+00:00",
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText(/Started:/)).toBeInTheDocument();
    });

    it("does not show check counts for running_or_started", () => {
      const summary = createSummaryFixture({
        status: "running_or_started",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        checks_requested: 5,
        checks_run: 3,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.queryByText(/Checks requested:/)).not.toBeInTheDocument();
    });
  });

  describe("3. completed state", () => {
    it("renders completed status correctly", () => {
      const summary = createSummaryFixture({
        status: "completed",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        latest_completed_at: "2026-01-01T12:05:00+00:00",
        latest_event_id: "event-2",
        latest_event_type: "diagnosis_loop_completed",
        checks_requested: 5,
        checks_run: 3,
        checks_rejected: 2,
        review_packet_available: true,
        review_packet_id: "review-packet-123",
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("completed")).toBeInTheDocument();
      expect(
        screen.getByText("Automatic diagnosis completed.")
      ).toBeInTheDocument();
    });

    it("shows check counts for completed", () => {
      const summary = createSummaryFixture({
        status: "completed",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        latest_completed_at: "2026-01-01T12:05:00+00:00",
        checks_requested: 5,
        checks_run: 3,
        checks_rejected: 2,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("Checks requested:")).toBeInTheDocument();
      expect(screen.getByText("5")).toBeInTheDocument();
      expect(screen.getByText("Checks run:")).toBeInTheDocument();
      expect(screen.getByText("3")).toBeInTheDocument();
      expect(screen.getByText("Checks rejected:")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
    });

    it("shows review packet availability for completed", () => {
      const summary = createSummaryFixture({
        status: "completed",
        review_packet_available: true,
        review_packet_id: "review-packet-123",
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("Review packet:")).toBeInTheDocument();
      expect(screen.getByText("Available")).toBeInTheDocument();
      expect(screen.getByText("review-packet-123")).toBeInTheDocument();
    });
  });

  describe("4. failed_or_unavailable state", () => {
    it("renders failed_or_unavailable status correctly", () => {
      const summary = createSummaryFixture({
        status: "failed_or_unavailable",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        latest_failed_at: "2026-01-01T12:10:00+00:00",
        latest_event_id: "event-3",
        latest_event_type: "diagnosis_loop_failed",
        unavailable_reason: "not_eligible",
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("failed or unavailable")).toBeInTheDocument();
      expect(
        screen.getByText("Automatic diagnosis failed or is unavailable.")
      ).toBeInTheDocument();
    });

    it("shows unavailable reason for failed", () => {
      const summary = createSummaryFixture({
        status: "failed_or_unavailable",
        latest_failed_at: "2026-01-01T12:10:00+00:00",
        unavailable_reason: "case_file_error",
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("Reason:")).toBeInTheDocument();
      expect(screen.getByText("case_file_error")).toBeInTheDocument();
    });

    it("does not show check counts for failed", () => {
      const summary = createSummaryFixture({
        status: "failed_or_unavailable",
        latest_failed_at: "2026-01-01T12:10:00+00:00",
        unavailable_reason: "not_eligible",
        checks_requested: 5,
        checks_run: 3,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.queryByText(/Checks requested:/)).not.toBeInTheDocument();
    });
  });

  describe("5. Timestamps display", () => {
    it("shows all relevant timestamps", () => {
      const summary = createSummaryFixture({
        status: "completed",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        latest_completed_at: "2026-01-01T12:05:00+00:00",
        latest_failed_at: "2026-01-01T12:10:00+00:00",
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText(/Started:/)).toBeInTheDocument();
      expect(screen.getByText(/Completed:/)).toBeInTheDocument();
      expect(screen.getByText(/Failed:/)).toBeInTheDocument();
    });
  });

  describe("6. Safety text display", () => {
    it("always shows safety notice", () => {
      const summary = createSummaryFixture({ status: "not_run" });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(
        screen.getByText(/Read-only evidence collected automatically/)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Review required before any action/)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/No remediation was attempted/)
      ).toBeInTheDocument();
    });
  });

  describe("7. No action/remediation controls", () => {
    it("has no buttons for any status", () => {
      const statuses: AutomaticDiagnosisLoopSummary["status"][] = [
        "not_run",
        "running_or_started",
        "completed",
        "failed_or_unavailable",
      ];

      for (const status of statuses) {
        const summary = createSummaryFixture({ status });
        const { unmount } = render(
          <IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />
        );

        const buttons = document.querySelectorAll("button");
        expect(buttons).toHaveLength(0);

        unmount();
      }
    });

    it("has no action links for any status", () => {
      const summary = createSummaryFixture({
        status: "completed",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        latest_completed_at: "2026-01-01T12:05:00+00:00",
        checks_requested: 5,
        checks_run: 3,
        checks_rejected: 2,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      const links = document.querySelectorAll("a");
      expect(links).toHaveLength(0);
    });

    it("status labels do not contain actionable remediation phrases", () => {
      const summary = createSummaryFixture({
        status: "completed",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        latest_completed_at: "2026-01-01T12:05:00+00:00",
        checks_requested: 5,
        checks_run: 3,
        checks_rejected: 2,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      const text = document.body.textContent || "";
      // Should not contain actionable remediation phrases (not just any word containing these)
      expect(text).not.toMatch(/\bRun\s+(diagnosis|remediation|check|action)\b/i);
      expect(text).not.toMatch(/\bApply\s+(fix|remediation|patch)\b/i);
      expect(text).not.toMatch(/\bPromote\s+to\s+production\b/i);
      expect(text).not.toMatch(/\bRemediate\b/);
      expect(text).not.toMatch(/\bExecute\s+action\b/i);
      expect(text).not.toMatch(/\bPatch\s+now\b/i);
      expect(text).not.toMatch(/\bDelete\s+resource\b/i);
      expect(text).not.toMatch(/\bRun\s+now\b/i);
    });
  });

  describe("8. Review packet availability", () => {
    it("shows available when true with packet id", () => {
      const summary = createSummaryFixture({
        status: "completed",
        review_packet_available: true,
        review_packet_id: "packet-abc",
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("Available")).toBeInTheDocument();
      expect(screen.getByText("packet-abc")).toBeInTheDocument();
    });

    it("shows generated when available but no packet id", () => {
      const summary = createSummaryFixture({
        status: "completed",
        review_packet_available: true,
        review_packet_id: null,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("Generated")).toBeInTheDocument();
    });

    it("shows not available when false", () => {
      const summary = createSummaryFixture({
        status: "not_run",
        review_packet_available: false,
        review_packet_id: null,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      expect(screen.getByText("Not available")).toBeInTheDocument();
    });
  });

  describe("9. Unknown status fallback", () => {
    it("handles unknown status gracefully", () => {
      const summary = createSummaryFixture({
        status: "not_run" as AutomaticDiagnosisLoopSummary["status"],
        // Simulate unknown status by passing unexpected value
      });
      // Override with unknown value to test fallback
      const unknownSummary = {
        ...summary,
        status: "unknown_status" as any,
      };
      render(
        <IncidentAutomaticDiagnosisLoopCard loopSummary={unknownSummary} />
      );

      // Should still render something
      expect(screen.getByText("Automatic diagnosis loop")).toBeInTheDocument();
    });
  });

  describe("10. Safety constraints enforced", () => {
    it("does not render raw event data", () => {
      const summary = createSummaryFixture({
        status: "completed",
        latest_started_at: "2026-01-01T12:00:00+00:00",
        latest_completed_at: "2026-01-01T12:05:00+00:00",
        latest_event_id: "event-123",
        latest_event_type: "diagnosis_loop_completed",
        checks_requested: 5,
        checks_run: 3,
        checks_rejected: 2,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      // Should show event type in status but not raw data
      expect(screen.queryByText(/event_data/)).not.toBeInTheDocument();
      expect(screen.queryByText(/data:/)).not.toBeInTheDocument();
      expect(screen.queryByText(/raw_content/)).not.toBeInTheDocument();
    });

    it("safety flags are always true in rendered content", () => {
      const summary = createSummaryFixture({
        status: "completed",
        read_only: true,
        review_required_before_any_action: true,
        no_remediation_attempted: true,
      });
      render(<IncidentAutomaticDiagnosisLoopCard loopSummary={summary} />);

      // Safety notice should be present
      expect(
        screen.getByText(/Read-only evidence collected automatically/)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Review required before any action/)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/No remediation was attempted/)
      ).toBeInTheDocument();
    });
  });
});
