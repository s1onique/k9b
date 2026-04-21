/**
 * Tests for ExecutionHistoryPanel Alertmanager relevance feedback feature.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import { ExecutionHistoryPanel } from "../components/ExecutionHistoryPanel";
import type { NextCheckExecutionHistoryEntry } from "../types";

// Minimal filter state for testing
const defaultFilterState = {
  outcomeFilter: "all" as const,
  usefulnessFilter: "all" as const,
  commandFamilyFilter: "all",
  clusterFilter: "all",
};

// Sample execution history entry with Alertmanager provenance
const createEntryWithProvenance = (overrides: Partial<NextCheckExecutionHistoryEntry> = {}): NextCheckExecutionHistoryEntry => ({
  timestamp: "2026-04-06T12:05:00Z",
  clusterLabel: "cluster-a",
  candidateId: "candidate-1",
  candidateIndex: 0,
  candidateDescription: "Collect kubelet logs",
  commandFamily: "kubectl-logs",
  status: "success",
  durationMs: 95,
  artifactPath: "/artifacts/run-123-execution-1.json",
  timedOut: false,
  stdoutTruncated: false,
  stderrTruncated: false,
  resultClass: "useful-signal",
  resultSummary: "Logs include control-plane errors.",
  ...overrides,
});

describe("ExecutionHistoryPanel - Alertmanager relevance UI", () => {
  describe("Alertmanager provenance rendering", () => {
    test("shows provenance block when entry has alertmanagerProvenance", () => {
      const entry = createEntryWithProvenance({
        alertmanagerProvenance: {
          matchedDimensions: ["namespace", "cluster"],
          matchedValues: { namespace: ["monitoring"], cluster: ["cluster-a"] },
          appliedBonus: 10,
          baseBonus: 10,
          severitySummary: { critical: 2, warning: 5 },
        },
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
        />
      );

      expect(screen.getByText(/Alertmanager provenance/i)).toBeInTheDocument();
      expect(screen.getByText(/Matched: namespace, cluster/i)).toBeInTheDocument();
      expect(screen.getByText(/bonus \+10/i)).toBeInTheDocument();
    });

    test("does not show provenance block when entry has no alertmanagerProvenance", () => {
      const entry = createEntryWithProvenance();

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
        />
      );

      expect(screen.queryByText(/Alertmanager provenance/i)).not.toBeInTheDocument();
    });
  });

  describe("Saved relevance rendering", () => {
    test("shows relevance badge when entry has alertmanagerRelevance", () => {
      const entry = createEntryWithProvenance({
        alertmanagerRelevance: "relevant",
        alertmanagerRelevanceSummary: "This check was useful for debugging the issue",
        alertmanagerReviewedAt: "2026-04-06T14:00:00Z",
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
        />
      );

      expect(screen.getByText(/relevant/i)).toBeInTheDocument();
      expect(screen.getByText(/This check was useful/i)).toBeInTheDocument();
    });

    test("does not show relevance badge when entry has no alertmanagerRelevance", () => {
      const entry = createEntryWithProvenance();

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
        />
      );

      // Should not show any relevance badge (the text "relevant" might appear in other contexts)
      // The badge has a specific class pattern
      const badges = screen.queryAllByText((content, element) => {
        if (!element) return false;
        return element.className.includes("alertmanager-relevance-badge");
      });
      expect(badges.length).toBe(0);
    });
  });

  describe("Feedback control visibility", () => {
    test("shows feedback control when provenance exists, no saved relevance, and callback provided", () => {
      const mockSubmit = vi.fn().mockResolvedValue(undefined);
      const entry = createEntryWithProvenance({
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
          onSubmitAlertmanagerRelevanceFeedback={mockSubmit}
        />
      );

      expect(screen.getByText(/Rate Alertmanager relevance/i)).toBeInTheDocument();
    });

    test("does not show feedback control when relevance is already saved", () => {
      const mockSubmit = vi.fn().mockResolvedValue(undefined);
      const entry = createEntryWithProvenance({
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
        alertmanagerRelevance: "relevant",
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
          onSubmitAlertmanagerRelevanceFeedback={mockSubmit}
        />
      );

      expect(screen.queryByText(/Rate Alertmanager relevance/i)).not.toBeInTheDocument();
    });

    test("does not show feedback control when callback is not provided", () => {
      const entry = createEntryWithProvenance({
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
        />
      );

      expect(screen.queryByText(/Rate Alertmanager relevance/i)).not.toBeInTheDocument();
    });

    test("does not show feedback control when no provenance exists", () => {
      const mockSubmit = vi.fn().mockResolvedValue(undefined);
      const entry = createEntryWithProvenance();

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
          onSubmitAlertmanagerRelevanceFeedback={mockSubmit}
        />
      );

      expect(screen.queryByText(/Rate Alertmanager relevance/i)).not.toBeInTheDocument();
    });
  });

  describe("Feedback control interaction", () => {
    test("expands feedback form on click", async () => {
      const user = userEvent.setup();
      const mockSubmit = vi.fn().mockResolvedValue(undefined);
      const entry = createEntryWithProvenance({
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
          onSubmitAlertmanagerRelevanceFeedback={mockSubmit}
        />
      );

      await user.click(screen.getByText(/Rate Alertmanager relevance/i));

      // Check that the form expanded with key elements
      expect(screen.getByText(/Was Alertmanager influence relevant/i)).toBeInTheDocument();
      
      // Check that radio options exist using getAllByRole for specificity
      const radios = document.querySelectorAll('input[type="radio"]');
      expect(radios.length).toBe(4); // relevant, not_relevant, noisy, unsure
      
      // Check for Save and Cancel buttons
      expect(screen.getByText(/Save/i)).toBeInTheDocument();
      expect(screen.getByText(/Cancel/i)).toBeInTheDocument();
    });

    test("calls callback with correct arguments on save", async () => {
      const user = userEvent.setup();
      const mockSubmit = vi.fn().mockResolvedValue(undefined);
      const entry = createEntryWithProvenance({
        artifactPath: "/artifacts/test-execution.json",
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
          onSubmitAlertmanagerRelevanceFeedback={mockSubmit}
        />
      );

      // Expand the form
      await user.click(screen.getByText(/Rate Alertmanager relevance/i));

      // Select "Relevant" radio button - use more specific selector
      const relevantRadio = document.querySelector('input[type="radio"][value="relevant"]');
      if (relevantRadio) {
        await user.click(relevantRadio);
      }

      // Enter optional note
      const noteInput = screen.getByPlaceholderText(/Optional note/i);
      await user.type(noteInput, "This was helpful");

      // Click Save
      await user.click(screen.getByText(/Save/i));

      expect(mockSubmit).toHaveBeenCalledWith(
        "/artifacts/test-execution.json",
        "relevant",
        "This was helpful"
      );
    });

    test("shows success message after submit resolves", async () => {
      const user = userEvent.setup();
      const mockSubmit = vi.fn().mockResolvedValue(undefined);
      const entry = createEntryWithProvenance({
        artifactPath: "/artifacts/test-execution.json",
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
          onSubmitAlertmanagerRelevanceFeedback={mockSubmit}
        />
      );

      // Expand and submit
      await user.click(screen.getByText(/Rate Alertmanager relevance/i));
      const relevantRadio = document.querySelector('input[type="radio"][value="relevant"]');
      if (relevantRadio) {
        await user.click(relevantRadio);
      }
      await user.click(screen.getByText(/Save/i));

      // Should show success message
      expect(screen.getByText(/✓ Alertmanager relevance recorded/i)).toBeInTheDocument();
    });

    test("shows error message when submit fails", async () => {
      const user = userEvent.setup();
      const mockSubmit = vi.fn().mockRejectedValue(new Error("Network error"));
      const entry = createEntryWithProvenance({
        artifactPath: "/artifacts/test-execution.json",
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
          onSubmitAlertmanagerRelevanceFeedback={mockSubmit}
        />
      );

      // Expand and submit
      await user.click(screen.getByText(/Rate Alertmanager relevance/i));
      const relevantRadio = document.querySelector('input[type="radio"][value="relevant"]');
      if (relevantRadio) {
        await user.click(relevantRadio);
      }
      await user.click(screen.getByText(/Save/i));

      // Should show error message
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });

    test("cancels form on cancel button", async () => {
      const user = userEvent.setup();
      const mockSubmit = vi.fn();
      const entry = createEntryWithProvenance({
        alertmanagerProvenance: {
          matchedDimensions: ["namespace"],
          matchedValues: { namespace: ["monitoring"] },
          appliedBonus: 5,
          baseBonus: 5,
        },
      });

      render(
        <ExecutionHistoryPanel
          history={[entry]}
          runId="run-123"
          runLabel="123"
          queueCandidateCount={0}
          highlightedKey={null}
          filter={defaultFilterState}
          onFilterChange={vi.fn()}
          onSubmitAlertmanagerRelevanceFeedback={mockSubmit}
        />
      );

      // Expand form
      await user.click(screen.getByText(/Rate Alertmanager relevance/i));
      expect(screen.getByText(/Was Alertmanager influence relevant/i)).toBeInTheDocument();

      // Cancel
      await user.click(screen.getByText(/Cancel/i));

      // Form should close
      expect(screen.queryByText(/Was Alertmanager influence relevant/i)).not.toBeInTheDocument();
      // And the original link should be back
      expect(screen.getByText(/Rate Alertmanager relevance/i)).toBeInTheDocument();
    });
  });
});
