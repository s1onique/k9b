/**
 * incidentOnePassDiagnosisValidation.test.ts
 *
 * Targeted tests for safety validation in incidentOnePassDiagnosis.ts.
 */

import { describe, expect, test } from "vitest";
import {
  validateOnePassSafety,
  type IncidentOnePassDiagnosisResponse,
} from "./incidentOnePassDiagnosis";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SAFE_RESPONSE: IncidentOnePassDiagnosisResponse = {
  schema_version: "1.0",
  incident_id: "test-incident",
  run_id: "one-pass-20260619-120000",
  category: "readiness_probe_failure",
  root_cause: "Pod readiness probe failure",
  confidence: "high",
  description: "The pod is not ready",
  evidence_refs: ["evidence-1", "evidence-2"],
  read_only: true,
  allowed_actions: [],
  forbidden_actions_observed: [],
  mutation_proposals_observed: [],
  decision: "run_allowed_read_only_checks",
  checks_run: 2,
  next_checks: [
    { check_id: "check-1", title: "Check pod events", read_only: true, source: "system" },
  ],
  artifact_written: true,
  artifact_name: "test-incident-diagnosis.json",
  error: null,
};

// ---------------------------------------------------------------------------
// Safety Validation Tests
// ---------------------------------------------------------------------------

describe("validateOnePassSafety", () => {
  test("safe response with read_only=true, no allowed_actions, no mutations passes", () => {
    const result = validateOnePassSafety(SAFE_RESPONSE);
    expect(result.isValid).toBe(true);
    expect(result.readOnlyViolation).toBe(false);
    expect(result.allowedActionsViolation).toBe(false);
    expect(result.mutationProposalsViolation).toBe(false);
    expect(result.nextChecksViolation).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(0);
  });

  test("read_only=false is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      read_only: false,
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.readOnlyViolation).toBe(true);
  });

  test("non-empty allowed_actions is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      allowed_actions: ["some-action"],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.allowedActionsViolation).toBe(true);
  });

  test("non-empty mutation_proposals_observed is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      mutation_proposals_observed: ["scale-replicas"],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.mutationProposalsViolation).toBe(true);
  });

  test("next_check with kubectl in check_id is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "kubectl-exec-check", title: "Exec into pod", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with mutate in title is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "check-1", title: "Mutate deployment", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with delete in check_id is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "delete-pod-check", title: "Delete pod", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with patch in title is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "patch-check", title: "Patch service", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with scale in check_id is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "scale-deployment-check", title: "Scale deployment", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with restart in title is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "restart-check", title: "Restart pod", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with rollout in check_id is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "rollout-restart-check", title: "Rollout restart", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with apply in title is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "apply-check", title: "Apply manifest", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with remediate in check_id is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "remediate-fault-check", title: "Remediate", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with exec in check_id is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "exec-into-pod-check", title: "Exec into pod", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with run in title is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "run-script-check", title: "Run diagnostic script", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("next_check with execute in check_id is a violation", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "execute-command-check", title: "Execute command", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("multiple violations are all reported", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      read_only: false,
      allowed_actions: ["action-1"],
      mutation_proposals_observed: ["scale"],
      next_checks: [
        { check_id: "kubectl-check", title: "Kubectl exec", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.readOnlyViolation).toBe(true);
    expect(result.allowedActionsViolation).toBe(true);
    expect(result.mutationProposalsViolation).toBe(true);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("case-insensitive pattern matching works", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "KUBECTL-EXEC", title: "EXEC INTO POD", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.unsafeNextChecks).toHaveLength(1);
  });

  test("safe next_check with check_readiness passes", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "check-readiness", title: "Check readiness", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(true);
    expect(result.unsafeNextChecks).toHaveLength(0);
  });

  test("safe next_check with check_logs passes", () => {
    const response: IncidentOnePassDiagnosisResponse = {
      ...SAFE_RESPONSE,
      next_checks: [
        { check_id: "check-logs", title: "Check logs", read_only: true },
      ],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(true);
    expect(result.unsafeNextChecks).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // Fail-closed tests for missing/null/malformed arrays
  // -------------------------------------------------------------------------

  test("null allowed_actions is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      allowed_actions: null as unknown as string[],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.allowedActionsViolation).toBe(true);
    expect(result.nextChecksViolation).toBe(false);
  });

  test("undefined allowed_actions is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      allowed_actions: undefined as unknown as string[],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.allowedActionsViolation).toBe(true);
    expect(result.nextChecksViolation).toBe(false);
  });

  test("string instead of allowed_actions array is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      allowed_actions: "not-an-array" as unknown as string[],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.allowedActionsViolation).toBe(true);
    expect(result.nextChecksViolation).toBe(false);
  });

  test("null mutation_proposals_observed is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      mutation_proposals_observed: null as unknown as string[],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.mutationProposalsViolation).toBe(true);
    expect(result.nextChecksViolation).toBe(false);
  });

  test("undefined mutation_proposals_observed is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      mutation_proposals_observed: undefined as unknown as string[],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.mutationProposalsViolation).toBe(true);
    expect(result.nextChecksViolation).toBe(false);
  });

  test("string instead of mutation_proposals_observed array is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      mutation_proposals_observed: "not-an-array" as unknown as string[],
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.mutationProposalsViolation).toBe(true);
    expect(result.nextChecksViolation).toBe(false);
  });

  test("null next_checks is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      next_checks: null as unknown as typeof SAFE_RESPONSE.next_checks,
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.nextChecksViolation).toBe(true);
  });

  test("undefined next_checks is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      next_checks: undefined as unknown as typeof SAFE_RESPONSE.next_checks,
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.nextChecksViolation).toBe(true);
  });

  test("string instead of next_checks array is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      next_checks: "not-an-array" as unknown as typeof SAFE_RESPONSE.next_checks,
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.nextChecksViolation).toBe(true);
  });

  test("object instead of next_checks array is a violation (fail closed)", () => {
    const response = {
      ...SAFE_RESPONSE,
      next_checks: { check_id: "test" } as unknown as typeof SAFE_RESPONSE.next_checks,
    };
    const result = validateOnePassSafety(response);
    expect(result.isValid).toBe(false);
    expect(result.nextChecksViolation).toBe(true);
  });
});
