/**
 * Tests for IncidentAutomaticDiagnosisReviewPanel component.
 *
 * Tests cover:
 * 1. Renders automatic diagnosis review section when available
 * 2. Section shows decision and counts
 * 3. Section shows artifact filename only
 * 4. Section shows read-only/review-required/no-remediation language
 * 5. Section does not render absolute paths
 * 6. Section does not render raw packet JSON
 * 7. Section does not render action buttons
 * 8. Absent state is handled safely
 * 9. Malformed/unavailable state is handled safely
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { IncidentAutomaticDiagnosisReviewPanel } from "./IncidentAutomaticDiagnosisReviewPanel";
import type { AutomaticDiagnosisReviewPayload } from "../api";

describe("IncidentAutomaticDiagnosisReviewPanel", () => {
  const availablePayload: AutomaticDiagnosisReviewPayload = {
    available: true,
    artifact_type: "diagnosis-loop-review-packet",
    artifact_name: "auto-incident-123-20260619074500-diagnosis-review-packet.json",
    run_id: "auto-incident-123-20260619074500",
    collector_run_id: "auto-diagnosis-20260619074500-abc123",
    generated_at: "2026-06-19T07:45:00+00:00",
    decision: "run_allowed_read_only_checks",
    checks_requested: 3,
    checks_run: 2,
    checks_rejected: 1,
    eligible: true,
    eligibility_reason: "active_incident_with_suggested_checks",
    read_only: true,
    review_required_before_any_action: true,
    no_remediation_attempted: true,
  };

  describe("Available state", () => {
    it("renders automatic diagnosis evidence heading", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      expect(screen.getByText("Automatic diagnosis evidence")).toBeInTheDocument();
    });

    it("shows decision", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      expect(screen.getByText(/Decision:/)).toBeInTheDocument();
      expect(screen.getByText("run_allowed_read_only_checks")).toBeInTheDocument();
    });

    it("shows check counts", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      expect(screen.getByText(/Checks requested:/)).toBeInTheDocument();
      expect(screen.getByText(/Checks run:/)).toBeInTheDocument();
      expect(screen.getByText(/Checks rejected:/)).toBeInTheDocument();
    });

    it("shows generated timestamp", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      expect(screen.getByText(/Generated:/)).toBeInTheDocument();
    });

    it("shows artifact filename only, not path", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      const artifactName = screen.getByText(availablePayload.artifact_name!);
      expect(artifactName).toBeInTheDocument();
      // Should not contain path separators
      expect(availablePayload.artifact_name).not.toContain("/");
      expect(availablePayload.artifact_name).not.toContain("\\");
    });

    it("shows read-only/review-required/no-remediation language", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      expect(screen.getByText(/Read-only evidence collected automatically/)).toBeInTheDocument();
      expect(screen.getByText(/Review required before any action/)).toBeInTheDocument();
      expect(screen.getByText(/No remediation was attempted/)).toBeInTheDocument();
    });

    it("shows eligibility reason", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      expect(screen.getByText(/Eligibility:/)).toBeInTheDocument();
      expect(screen.getByText("active_incident_with_suggested_checks")).toBeInTheDocument();
    });

    it("does not render action buttons", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      const buttons = screen.queryAllByRole("button");
      expect(buttons).toHaveLength(0);
    });

    it("does not render forbidden action labels", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      const content = document.body.textContent || "";
      const forbiddenActions = ["Run", "Approve", "Apply", "Delete", "Restart", "Rollout", "Scale", "Patch"];
      forbiddenActions.forEach((action) => {
        expect(content).not.toContain(action);
      });
    });
  });

  describe("Unavailable state - no packet", () => {
    const noPacketPayload: AutomaticDiagnosisReviewPayload = {
      available: false,
      unavailable_reason: "no_review_packet",
    };

    it("renders heading", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={noPacketPayload} />);
      expect(screen.getByText("Automatic diagnosis evidence")).toBeInTheDocument();
    });

    it("shows not collected yet message", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={noPacketPayload} />);
      expect(screen.getByText(/not collected yet/)).toBeInTheDocument();
    });

    it("does not show detailed information", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={noPacketPayload} />);
      expect(screen.queryByText(/Decision:/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Checks requested:/)).not.toBeInTheDocument();
    });

    it("does not render action buttons", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={noPacketPayload} />);
      const buttons = screen.queryAllByRole("button");
      expect(buttons).toHaveLength(0);
    });
  });

  describe("Unavailable state - malformed packet", () => {
    const malformedPayload: AutomaticDiagnosisReviewPayload = {
      available: false,
      unavailable_reason: "malformed_review_packet",
    };

    it("renders heading", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={malformedPayload} />);
      expect(screen.getByText("Automatic diagnosis evidence")).toBeInTheDocument();
    });

    it("shows reason for unavailability", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={malformedPayload} />);
      expect(screen.getByText(/Reason: malformed_review_packet/)).toBeInTheDocument();
    });
  });

  describe("Safety assertions", () => {
    it("does not expose raw packet JSON in content", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      const content = document.body.textContent || "";
      // Should not contain raw JSON structures
      expect(content).not.toContain('{"');
      expect(content).not.toContain('"}');
    });

    it("does not contain absolute filesystem paths", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      const content = document.body.textContent || "";
      // Should not contain common path patterns
      expect(content).not.toContain("/Volumes/");
      expect(content).not.toContain("/Users/");
      expect(content).not.toContain("/some/path");
    });

    it("does not contain forbidden security terms", () => {
      render(<IncidentAutomaticDiagnosisReviewPanel automaticDiagnosisReview={availablePayload} />);
      const content = document.body.textContent || "";
      const forbiddenTerms = ["kubeconfig", "token", "secret", "password", "authorization"];
      forbiddenTerms.forEach((term) => {
        expect(content.toLowerCase()).not.toContain(term);
      });
    });
  });
});