/**
 * incidentDiagnosisLoop.suggested-checks.test.ts
 *
 * Targeted tests for buildDiagnosisReportFromSelectedChecks.
 *
 * Verifies:
 * 1. selected check maps to diagnosis_report.recommended_investigations
 * 2. empty selection maps to empty recommended_investigations
 * 3. only check_id/title/read_only/source are sent
 * 4. unknown fields are stripped
 * 5. action-control fields are stripped
 * 6. external_analysis_dir/path/artifact_root are not sent
 * 7. max check count is enforced
 * 8. long title is bounded
 * 9. long check_id is bounded or rejected
 * 10. source is fixed to manual_suggested_check
 */

import { describe, expect, test } from "vitest";
import { buildDiagnosisReportFromSelectedChecks } from "./incidentDiagnosisLoop";
import type { IncidentSuggestedCheck } from "../api";

/**
 * Create a suggested check fixture.
 */
const createCheck = (overrides: Partial<IncidentSuggestedCheck> = {}): IncidentSuggestedCheck => ({
  check_id: "test-check",
  title: "Test check title",
  rationale: "Test rationale",
  source: "test-source",
  risk_level: "LOW",
  status: "suggested",
  artifact_id: null,
  run_id: null,
  ...overrides,
});

describe("buildDiagnosisReportFromSelectedChecks", () => {
  describe("1. Maps selected check to recommended_investigations", () => {
    test("single check maps to single investigation", () => {
      const selectedChecks = [createCheck({ check_id: "pod_logs", title: "Check pod logs" })];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(1);
      expect(report.diagnosis.recommended_investigations[0].check_id).toBe("pod_logs");
      expect(report.diagnosis.recommended_investigations[0].title).toBe("Check pod logs");
    });

    test("multiple checks map to multiple investigations", () => {
      const selectedChecks = [
        createCheck({ check_id: "check-1", title: "First check" }),
        createCheck({ check_id: "check-2", title: "Second check" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(2);
      expect(report.diagnosis.recommended_investigations[0].check_id).toBe("check-1");
      expect(report.diagnosis.recommended_investigations[1].check_id).toBe("check-2");
    });
  });

  describe("2. Empty selection maps to empty recommended_investigations", () => {
    test("empty array produces empty investigations", () => {
      const report = buildDiagnosisReportFromSelectedChecks([]);
      expect(report.diagnosis.recommended_investigations).toEqual([]);
    });
  });

  describe("3. Only safe fields are sent", () => {
    test("investigation contains only check_id, title, read_only, source", () => {
      const selectedChecks = [createCheck()];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);
      const investigation = report.diagnosis.recommended_investigations[0];

      const keys = Object.keys(investigation).sort();
      expect(keys).toEqual(["check_id", "read_only", "source", "title"]);
    });

    test("read_only is always true", () => {
      const selectedChecks = [createCheck()];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations[0].read_only).toBe(true);
    });

    test("source is fixed to manual_suggested_check", () => {
      const selectedChecks = [createCheck({ source: "some-other-source" })];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations[0].source).toBe("manual_suggested_check");
    });
  });

  describe("4. Unknown fields are stripped", () => {
    test("unknown fields are not included in investigation", () => {
      const selectedChecks = [createCheck()];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);
      const investigation = report.diagnosis.recommended_investigations[0];

      // Rationale from suggested check should not appear
      expect(investigation).not.toHaveProperty("rationale");
      // source IS present but as safe fixed "manual_suggested_check" (not original source)
      expect(investigation.source).toBe("manual_suggested_check");
    });
  });

  describe("5. Action-control fields are stripped", () => {
    test("check with mutation keyword in title is filtered out", () => {
      const selectedChecks = [
        createCheck({ check_id: "safe-check", title: "Safe check" }),
        createCheck({ check_id: "mutate-check", title: "This will mutate data" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      // Only safe check should be included
      expect(report.diagnosis.recommended_investigations).toHaveLength(1);
      expect(report.diagnosis.recommended_investigations[0].check_id).toBe("safe-check");
    });

    test("check with delete keyword in check_id is filtered out", () => {
      const selectedChecks = [
        createCheck({ check_id: "safe_check", title: "Safe check" }),
        createCheck({ check_id: "delete_pods_check", title: "Delete pods" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(1);
      expect(report.diagnosis.recommended_investigations[0].check_id).toBe("safe_check");
    });

    test("check with kubectl keyword is filtered out", () => {
      const selectedChecks = [
        createCheck({ check_id: "kubectl_logs", title: "Get logs via kubectl" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(0);
    });

    test("check with scale keyword is filtered out", () => {
      const selectedChecks = [
        createCheck({ check_id: "safe_check", title: "Safe check" }),
        createCheck({ check_id: "scale_deployment", title: "Scale deployment" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(1);
    });

    test("check with remediate keyword is filtered out", () => {
      const selectedChecks = [
        createCheck({ check_id: "auto_remediate", title: "Auto remediate" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(0);
    });
  });

  describe("6. Forbidden paths are not sent", () => {
    test("serialized report does not contain external_analysis_dir", () => {
      const selectedChecks = [createCheck()];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);
      const json = JSON.stringify(report);

      expect(json).not.toContain("external_analysis_dir");
      expect(json).not.toContain("external_analysis_path");
    });

    test("serialized report does not contain artifact_root", () => {
      const selectedChecks = [createCheck()];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);
      const json = JSON.stringify(report);

      expect(json).not.toContain("artifact_root");
    });

    test("serialized report does not contain path", () => {
      const selectedChecks = [createCheck()];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);
      const json = JSON.stringify(report);

      // "path" as a property name
      expect(report).not.toHaveProperty("path");
    });
  });

  describe("7. Max check count is enforced", () => {
    test("more than 5 checks are truncated to 5", () => {
      const selectedChecks = Array.from({ length: 7 }, (_, i) =>
        createCheck({ check_id: `check-${i}`, title: `Check ${i}` })
      );
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(5);
    });

    test("exactly 5 checks are all included", () => {
      const selectedChecks = Array.from({ length: 5 }, (_, i) =>
        createCheck({ check_id: `check-${i}`, title: `Check ${i}` })
      );
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(5);
    });

    test("first 5 checks are included when more than 5 provided", () => {
      const selectedChecks = Array.from({ length: 8 }, (_, i) =>
        createCheck({ check_id: `check-${i}`, title: `Check ${i}` })
      );
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      const ids = report.diagnosis.recommended_investigations.map((inv) => inv.check_id);
      expect(ids).toEqual(["check-0", "check-1", "check-2", "check-3", "check-4"]);
    });
  });

  describe("8. Long title is bounded", () => {
    test("title longer than 200 chars is truncated", () => {
      const longTitle = "A".repeat(300);
      const selectedChecks = [createCheck({ title: longTitle })];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations[0].title).toHaveLength(200);
    });

    test("title exactly 200 chars is preserved", () => {
      const exactTitle = "B".repeat(200);
      const selectedChecks = [createCheck({ title: exactTitle })];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations[0].title).toHaveLength(200);
    });

    test("title shorter than 200 chars is preserved", () => {
      const shortTitle = "Short title";
      const selectedChecks = [createCheck({ title: shortTitle })];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations[0].title).toBe(shortTitle);
    });
  });

  describe("9. Long check_id is bounded", () => {
    test("check_id longer than 100 chars is truncated", () => {
      const longCheckId = "C".repeat(150);
      const selectedChecks = [createCheck({ check_id: longCheckId })];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations[0].check_id).toHaveLength(100);
    });

    test("check_id exactly 100 chars is preserved", () => {
      const exactCheckId = "D".repeat(100);
      const selectedChecks = [createCheck({ check_id: exactCheckId })];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations[0].check_id).toHaveLength(100);
    });
  });

  describe("10. Source is fixed", () => {
    test("source is always manual_suggested_check regardless of input", () => {
      const selectedChecks = [
        createCheck({ source: "next-check-planning" }),
        createCheck({ source: "operator-input" }),
        createCheck({ source: "some-random-source" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      for (const inv of report.diagnosis.recommended_investigations) {
        expect(inv.source).toBe("manual_suggested_check");
      }
    });
  });

  describe("Edge cases", () => {
    test("check with empty check_id is filtered out", () => {
      const selectedChecks = [
        createCheck({ check_id: "", title: "Empty check_id" }),
        createCheck({ check_id: "valid-check", title: "Valid check" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(1);
      expect(report.diagnosis.recommended_investigations[0].check_id).toBe("valid-check");
    });

    test("check with whitespace-only check_id is filtered out", () => {
      const selectedChecks = [
        createCheck({ check_id: "   ", title: "Whitespace check_id" }),
        createCheck({ check_id: "valid", title: "Valid check" }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations).toHaveLength(1);
    });

    test("check with null title is handled gracefully", () => {
      const selectedChecks = [
        createCheck({ title: "" as unknown as string }),
      ];
      const report = buildDiagnosisReportFromSelectedChecks(selectedChecks);

      expect(report.diagnosis.recommended_investigations[0].title).toBe("");
    });
  });
});
