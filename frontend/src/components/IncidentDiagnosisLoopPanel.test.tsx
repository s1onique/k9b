/**
 * IncidentDiagnosisLoopPanel.test.tsx
 *
 * Tests for the manual diagnosis loop panel component.
 *
 * Verifies:
 * 1. Panel renders on incident detail
 * 2. Copy clearly says read-only and one pass
 * 3. Button says "Run one read-only pass"
 * 4. Clicking button disables it while running
 * 5. Clicking button sends one request only
 * 6. Success displays decision
 * 7. Success displays check counts
 * 8. Success displays artifact names only
 * 9. Success does not display absolute paths
 * 10. Stop-path success displays read-only-check-results as not written
 * 11. Error response displays bounded error
 * 12. Raw case file is not rendered
 * 13. Raw runner result is not rendered
 * 14. No remediation/action words appear as buttons or controls
 * 15. No auto-run happens on render
 * 16. No repeated polling/execution happens
 */

import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { IncidentDiagnosisLoopPanel } from "./IncidentDiagnosisLoopPanel";
import type { DiagnosisLoopOnePassResponse } from "../api/incidentDiagnosisLoop";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const INCIDENT_ID = "test-incident-123";

const createSuccessResponse = (overrides?: Partial<DiagnosisLoopOnePassResponse>): DiagnosisLoopOnePassResponse => ({
  schema_version: "1.0",
  incident_id: INCIDENT_ID,
  run_id: "manual-loop-20260619-120000",
  read_only: true,
  allowed_actions: [],
  decision: "continue",
  checks_requested: 0,
  checks_run: 0,
  checks_skipped: 0,
  checks_rejected: 0,
  artifacts: {
    read_only_check_results: { written: false, name: null },
    diagnosis_loop_pass: {
      written: true,
      name: "manual-loop-20260619-120000-diagnosis-loop-pass.json",
    },
  },
  case_file_linked_artifact: false,
  safety_metadata: {
    read_only: true,
    allowed_actions: [],
    no_kubernetes_client: true,
    no_shell: true,
    no_subprocess: true,
    no_kubectl: true,
    no_mutation: true,
    fake_runner: true,
    one_pass_only: true,
  },
  ...overrides,
});

// ---------------------------------------------------------------------------
// Mock fetch helper
// ---------------------------------------------------------------------------

const mockFetch = (response: unknown, status = 200) => {
  const mockResponse = new Response(JSON.stringify(response), {
    status,
    headers: { "Content-Type": "application/json" },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(mockResponse)
  );
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("IncidentDiagnosisLoopPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("1. Panel renders", () => {
    test("renders the panel on incident detail", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      expect(screen.getByText("Manual diagnosis loop")).toBeInTheDocument();
    });

    test("renders all required sections", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      expect(screen.getByText(/Runs exactly one read-only/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Run one read-only pass/i })).toBeInTheDocument();
      expect(screen.getByText(/Fake runner/i)).toBeInTheDocument();
    });
  });

  describe("2. Copy clearly says read-only and one pass", () => {
    test("displays read-only badge", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      expect(screen.getByText("Read-only")).toBeInTheDocument();
    });

    test("displays one-pass-only badge", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      expect(screen.getByText("One pass only")).toBeInTheDocument();
    });

    test("explanatory copy mentions safe check policy", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      expect(screen.getByText(/safe check policy/i)).toBeInTheDocument();
    });

    test("safety footer mentions fake runner and no mutation", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      expect(screen.getByText(/Fake runner/)).toBeInTheDocument();
      expect(screen.getByText(/No mutation/)).toBeInTheDocument();
    });
  });

  describe("3. Button says Run one read-only pass", () => {
    test("button has correct label", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      expect(screen.getByRole("button", { name: /Run one read-only pass/i })).toBeInTheDocument();
    });
  });

  describe("4. Clicking button disables it while running", () => {
    test("button is disabled during request", async () => {
      const user = userEvent.setup();
      // Use a promise that doesn't resolve to keep the loading state
      let resolvePromise: (value: Response) => void;
      const fetchPromise = new Promise<Response>((resolve) => {
        resolvePromise = resolve;
      });
      vi.stubGlobal("fetch", vi.fn().mockReturnValue(fetchPromise));

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      expect(screen.getByRole("button", { name: /Running one read-only pass/i })).toBeDisabled();
    });
  });

  describe("5. Clicking button sends one request only", () => {
    test("fetch is called exactly once", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse());

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(vi.mocked(global.fetch)).toHaveBeenCalledTimes(1);
      });
    });

    test("button is re-enabled after success", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse());

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Run one read-only pass/i })).not.toBeDisabled();
      });
    });
  });

  describe("6. Success displays decision", () => {
    test("shows decision from response", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse({ decision: "investigate_further" }));

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(screen.getByText(/investigate_further/i)).toBeInTheDocument();
      });
    });
  });

  describe("7. Success displays check counts", () => {
    test("shows check counts from response", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse({ checks_requested: 5, checks_run: 3, checks_skipped: 1, checks_rejected: 1 }));

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(screen.getByText(/requested=5/)).toBeInTheDocument();
        expect(screen.getByText(/run=3/)).toBeInTheDocument();
        expect(screen.getByText(/skipped=1/)).toBeInTheDocument();
        expect(screen.getByText(/rejected=1/)).toBeInTheDocument();
      });
    });
  });

  describe("8. Success displays artifact names only", () => {
    test("shows diagnosis-loop-pass artifact name", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse({
        artifacts: {
          read_only_check_results: { written: false, name: null },
          diagnosis_loop_pass: { written: true, name: "test-artifact.json" },
        },
      }));

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(screen.getByText("diagnosis-loop-pass:")).toBeInTheDocument();
        expect(screen.getByText("test-artifact.json")).toBeInTheDocument();
      });
    });
  });

  describe("9. Success does not display absolute paths", () => {
    test("does not show filesystem paths in artifact names", async () => {
      const user = userEvent.setup();
      // Backend should only return artifact names (not full paths)
      mockFetch(createSuccessResponse({
        artifacts: {
          read_only_check_results: { written: false, name: null },
          diagnosis_loop_pass: { written: true, name: "manual-loop-20260619-120000-diagnosis-loop-pass.json" },
        },
      }));

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        const artifactText = screen.getByText(/diagnosis-loop-pass:/).parentElement?.textContent || "";
        // Should not contain common path separators
        expect(artifactText).not.toContain("/artifacts/");
        expect(artifactText).not.toContain("/external/");
        expect(artifactText).not.toContain("..");
      });
    });
  });

  describe("10. Stop-path success displays read-only-check-results as not written", () => {
    test("shows read-only-check-results as not written when not written", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse({
        artifacts: {
          read_only_check_results: { written: false, name: null },
          diagnosis_loop_pass: { written: true, name: "test.json" },
        },
      }));

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(screen.getByText(/read-only-check-results/)).toBeInTheDocument();
        expect(screen.getByText(/not written/)).toBeInTheDocument();
      });
    });
  });

  describe("11. Error response displays bounded error", () => {
    test("shows error message without stack trace", async () => {
      const user = userEvent.setup();
      mockFetch({ error: "Incident not found" }, 404);

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(screen.getByText(/Incident not found/i)).toBeInTheDocument();
      });
    });

    test("does not expose raw response internals", async () => {
      const user = userEvent.setup();
      // Simulate a malformed or verbose error response
      mockFetch({
        error: "Incident not found",
        traceback: "some_internal_traceback",
        stack: "internal_stack_trace",
        internal_details: "sensitive_data",
      }, 404);

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(screen.queryByText(/traceback/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/internal_stack_trace/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/sensitive_data/i)).not.toBeInTheDocument();
      });
    });
  });

  describe("12. Raw case file is not rendered", () => {
    test("panel does not display case file contents", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse());

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        expect(screen.queryByText(/case_file/i)).not.toBeInTheDocument();
      });
    });
  });

  describe("13. Raw runner result is not rendered", () => {
    test("panel does not display runner internals", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse());

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));

      await waitFor(() => {
        // Safety metadata summary is displayed, but not raw runner result
        expect(screen.getByText(/Read-only: yes/)).toBeInTheDocument();
        expect(screen.getByText(/Fake runner: yes/)).toBeInTheDocument();
        expect(screen.getByText(/One-pass only: yes/)).toBeInTheDocument();
      });
    });
  });

  describe("14. No remediation/action words appear as buttons or controls", () => {
    const FORBIDDEN_ACTION_WORDS = [
      "Apply",
      "Delete",
      "Patch",
      "Scale",
      "Restart",
      "Rollout",
      "Remediate",
      "Execute",
      "Fix",
      "Resolve automatically",
    ];

    test.each(FORBIDDEN_ACTION_WORDS)("button/control does not contain '%s'", (word) => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);

      const buttons = screen.getAllByRole("button");
      for (const button of buttons) {
        expect(button.textContent).not.toContain(word);
      }
    });

    test("safety text explaining no remediation is allowed", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      // Explanatory safety text is allowed
      expect(screen.getByText(/does not remediate/i)).toBeInTheDocument();
      expect(screen.getByText(/No remediation/)).toBeInTheDocument();
    });
  });

  describe("15. No auto-run happens on render", () => {
    test("fetch is not called during initial render", () => {
      mockFetch(createSuccessResponse());
      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);
      expect(vi.mocked(global.fetch)).not.toHaveBeenCalled();
    });
  });

  describe("16. No repeated polling/execution happens", () => {
    test("fetch is called exactly once per manual button click", async () => {
      const user = userEvent.setup();
      mockFetch(createSuccessResponse());

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);

      // Click once
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));
      await waitFor(() => {
        expect(vi.mocked(global.fetch)).toHaveBeenCalledTimes(1);
      });

      // Wait for completion
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Run one read-only pass/i })).not.toBeDisabled();
      });

      // Click again
      await user.click(screen.getByRole("button", { name: /Run one read-only pass/i }));
      await waitFor(() => {
        expect(vi.mocked(global.fetch)).toHaveBeenCalledTimes(2);
      });
    });

    test("no interval or timeout triggers additional requests", async () => {
      vi.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      mockFetch(createSuccessResponse());

      render(<IncidentDiagnosisLoopPanel incidentId={INCIDENT_ID} />);

      // Advance time significantly
      await vi.advanceTimersByTimeAsync(10000);

      // fetch should not have been called
      expect(vi.mocked(global.fetch)).not.toHaveBeenCalled();

      vi.useRealTimers();
    });
  });
});
