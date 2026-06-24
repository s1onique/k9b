/**
 * IncidentOnePassDiagnosisPanel.test.tsx
 *
 * Targeted tests for frontend/src/components/IncidentOnePassDiagnosisPanel.tsx.
 *
 * Verifies:
 * 1. Button is visible with accessible name
 * 2. Clicking button calls API
 * 3. Loading state appears
 * 4. Button disabled while running
 * 5. Success result renders category/root cause/confidence
 * 6. Evidence refs render safely
 * 7. Checks_run is visible
 * 8. read_only=true and allowed_actions=[] are shown/assured
 * 9. Backend error renders bounded error
 * 10. Response with read_only=false is treated as safety failure
 * 11. Response with allowed_actions non-empty is treated as safety failure
 * 12. Mutation-looking next_checks are not rendered as actionable controls
 */

import React from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IncidentOnePassDiagnosisPanel } from "./IncidentOnePassDiagnosisPanel";
import type { IncidentOnePassDiagnosisResponse } from "../api/incidentOnePassDiagnosis";

// ---------------------------------------------------------------------------
// Mock the API module
// ---------------------------------------------------------------------------

const mockRunIncidentOnePassDiagnosis = vi.fn();

vi.mock("../api/incidentOnePassDiagnosis", () => ({
  runIncidentOnePassDiagnosis: (...args: unknown[]) => mockRunIncidentOnePassDiagnosis(...args),
  generateOnePassRunId: () => "one-pass-mock-20260619-120000",
  validateOnePassSafety: (response: IncidentOnePassDiagnosisResponse) => {
    const readOnlyViolation = response.read_only !== true;
    const allowedActionsIsArray = Array.isArray(response.allowed_actions);
    const allowedActions = allowedActionsIsArray ? response.allowed_actions : [];
    const allowedActionsViolation = !allowedActionsIsArray || allowedActions.length > 0;
    const mutationProposalsIsArray = Array.isArray(response.mutation_proposals_observed);
    const mutationProposals = mutationProposalsIsArray ? response.mutation_proposals_observed : [];
    const mutationProposalsViolation = !mutationProposalsIsArray || mutationProposals.length > 0;
    const nextChecksIsArray = Array.isArray(response.next_checks);
    const nextChecks = nextChecksIsArray ? response.next_checks : [];
    const nextChecksViolation = !nextChecksIsArray;
    const unsafeNextChecks = nextChecks.filter((check) => {
      const checkIdLower = (check.check_id || "").toLowerCase();
      const titleLower = (check.title || "").toLowerCase();
      const forbidden = ["mutate", "delete", "patch", "scale", "restart", "rollout", "apply", "remediate", "kubectl", "exec", "run", "execute"];
      return forbidden.some((p) => checkIdLower.includes(p) || titleLower.includes(p));
    });
    const isValid = !readOnlyViolation && !allowedActionsViolation && !mutationProposalsViolation && !nextChecksViolation && unsafeNextChecks.length === 0;
    return { isValid, readOnlyViolation, allowedActionsViolation, mutationProposalsViolation, nextChecksViolation, unsafeNextChecks };
  },
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SUCCESS_RESPONSE: IncidentOnePassDiagnosisResponse = {
  schema_version: "1.0",
  incident_id: "test-incident-123",
  run_id: "one-pass-mock-20260619-120000",
  category: "readiness_probe_failure",
  root_cause: "Pod readiness probe failure",
  confidence: "high",
  description: "The pod is not ready due to failing readiness probe",
  evidence_refs: ["evidence-1", "evidence-2"],
  read_only: true,
  allowed_actions: [],
  forbidden_actions_observed: [],
  mutation_proposals_observed: [],
  decision: "run_allowed_read_only_checks",
  checks_run: 3,
  next_checks: [
    { check_id: "check-1", title: "Check pod events", read_only: true, source: "system" },
  ],
  artifact_written: true,
  artifact_name: "test-incident-123-diagnosis.json",
  error: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("IncidentOnePassDiagnosisPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("1. Button is visible with accessible name", () => {
    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    expect(button).toBeInTheDocument();
  });

  test("2. Clicking button calls API", async () => {
    mockRunIncidentOnePassDiagnosis.mockResolvedValueOnce(SUCCESS_RESPONSE);

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    expect(mockRunIncidentOnePassDiagnosis).toHaveBeenCalledWith(
      "test-incident",
      expect.objectContaining({ runId: expect.any(String) })
    );
  });

  test("3. Loading state appears", async () => {
    mockRunIncidentOnePassDiagnosis.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(SUCCESS_RESPONSE), 100))
    );

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    expect(screen.getByText(/running read-only diagnosis/i)).toBeInTheDocument();
  });

  test("4. Button disabled while running", async () => {
    mockRunIncidentOnePassDiagnosis.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(SUCCESS_RESPONSE), 100))
    );

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  test("5. Success result renders category/root cause/confidence", async () => {
    mockRunIncidentOnePassDiagnosis.mockResolvedValueOnce(SUCCESS_RESPONSE);

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/readiness_probe_failure/i)).toBeInTheDocument();
      expect(screen.getByText(/Pod readiness probe failure/i)).toBeInTheDocument();
      expect(screen.getByText(/high/i)).toBeInTheDocument();
    });
  });

  test("6. Evidence refs render safely", async () => {
    mockRunIncidentOnePassDiagnosis.mockResolvedValueOnce(SUCCESS_RESPONSE);

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/evidence-1/i)).toBeInTheDocument();
      expect(screen.getByText(/evidence-2/i)).toBeInTheDocument();
    });
  });

  test("7. Checks_run is visible", async () => {
    mockRunIncidentOnePassDiagnosis.mockResolvedValueOnce(SUCCESS_RESPONSE);

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    await waitFor(() => {
      // Check for the result header that appears on success
      expect(screen.getByText(/One-pass diagnosis result/i)).toBeInTheDocument();
    });
    // Verify checks_run is in the dedicated element (with class one-pass-checks-run)
    expect(screen.getByText("3", { selector: ".one-pass-checks-run" })).toBeInTheDocument();
  });

  test("8. read_only=true and allowed_actions=[] are shown/assured", async () => {
    mockRunIncidentOnePassDiagnosis.mockResolvedValueOnce(SUCCESS_RESPONSE);

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    await waitFor(() => {
      // Safety confirmation should show read_only=true
      expect(screen.getByText(/read_only=true/i)).toBeInTheDocument();
      // Should show allowed_actions count is 0
      expect(screen.getByText(/allowed_actions=0/i)).toBeInTheDocument();
    });
  });

  test("9. Backend error renders bounded error", async () => {
    mockRunIncidentOnePassDiagnosis.mockRejectedValueOnce(new Error("Incident not found"));

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/Incident not found/i)).toBeInTheDocument();
    });
  });

  test("10. Response with read_only=false is treated as safety failure", async () => {
    const unsafeResponse: IncidentOnePassDiagnosisResponse = {
      ...SUCCESS_RESPONSE,
      read_only: false,
    };
    mockRunIncidentOnePassDiagnosis.mockResolvedValueOnce(unsafeResponse);

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/Safety violation/i)).toBeInTheDocument();
      // Should NOT show the diagnosis result
      expect(screen.queryByText(/readiness_probe_failure/i)).not.toBeInTheDocument();
    });
  });

  test("11. Response with allowed_actions non-empty is treated as safety failure", async () => {
    const unsafeResponse: IncidentOnePassDiagnosisResponse = {
      ...SUCCESS_RESPONSE,
      allowed_actions: ["some-action"],
    };
    mockRunIncidentOnePassDiagnosis.mockResolvedValueOnce(unsafeResponse);

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/Safety violation/i)).toBeInTheDocument();
      // Should NOT show the diagnosis result
      expect(screen.queryByText(/readiness_probe_failure/i)).not.toBeInTheDocument();
    });
  });

  test("12. Mutation-looking next_checks are not rendered as actionable controls", async () => {
    const unsafeResponse: IncidentOnePassDiagnosisResponse = {
      ...SUCCESS_RESPONSE,
      next_checks: [
        { check_id: "kubectl-exec-check", title: "Exec into pod", read_only: true, source: "system" },
      ],
    };
    mockRunIncidentOnePassDiagnosis.mockResolvedValueOnce(unsafeResponse);

    render(<IncidentOnePassDiagnosisPanel incidentId="test-incident" />);

    const button = screen.getByRole("button", { name: /run read-only one-pass diagnosis/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/Safety violation/i)).toBeInTheDocument();
      // Should NOT show the kubectl-exec check as valid
      expect(screen.queryByText(/Exec into pod/i)).not.toBeInTheDocument();
    });
  });
});
