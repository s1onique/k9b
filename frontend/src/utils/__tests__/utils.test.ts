/**
 * Unit tests for shared utility functions in utils.ts.
 *
 * Covers: isItemExecuted, deriveExecutionLabel, hasExecutionArtifactPath
 */

import { describe, expect, test } from "vitest";
import {
  isItemExecuted,
  deriveExecutionLabel,
  hasExecutionArtifactPath,
  EXECUTED_STATES,
  EXECUTED_ITEM_STATES,
} from "../../utils";

describe("hasExecutionArtifactPath", () => {
  test("returns true for path containing next-check-execution", () => {
    expect(hasExecutionArtifactPath("runs/abc/next-check-execution-0.json")).toBe(true);
    expect(hasExecutionArtifactPath("next-check-execution-1.json")).toBe(true);
    expect(hasExecutionArtifactPath("/path/to/next-check-execution-999.json")).toBe(true);
  });

  test("returns false for non-execution paths", () => {
    expect(hasExecutionArtifactPath("runs/abc/next-check-plan.json")).toBe(false);
    expect(hasExecutionArtifactPath("runs/abc/some-other-execution.json")).toBe(false);
    expect(hasExecutionArtifactPath("next-check-plan-0.json")).toBe(false);
  });

  test("handles null/undefined", () => {
    expect(hasExecutionArtifactPath(null)).toBe(false);
    expect(hasExecutionArtifactPath(undefined)).toBe(false);
  });

  test("handles empty string", () => {
    expect(hasExecutionArtifactPath("")).toBe(false);
  });
});

describe("isItemExecuted", () => {
  describe("itemState signals", () => {
    test("returns true for itemState='executed'", () => {
      expect(isItemExecuted({ itemState: "executed" })).toBe(true);
    });

    test("returns true for itemState='reviewed'", () => {
      expect(isItemExecuted({ itemState: "reviewed" })).toBe(true);
    });

    test("returns false for other itemState values", () => {
      expect(isItemExecuted({ itemState: "pending" })).toBe(false);
      expect(isItemExecuted({ itemState: "queued" })).toBe(false);
      expect(isItemExecuted({ itemState: null })).toBe(false);
      expect(isItemExecuted({ itemState: undefined })).toBe(false);
    });
  });

  describe("executionState signals", () => {
    test("returns true for executed-success", () => {
      expect(isItemExecuted({ executionState: "executed-success" })).toBe(true);
    });

    test("returns true for executed-failed", () => {
      expect(isItemExecuted({ executionState: "executed-failed" })).toBe(true);
    });

    test("returns true for timed-out", () => {
      expect(isItemExecuted({ executionState: "timed-out" })).toBe(true);
    });

    test("returns true for completed", () => {
      expect(isItemExecuted({ executionState: "completed" })).toBe(true);
    });

    test("returns false for unexecuted", () => {
      expect(isItemExecuted({ executionState: "unexecuted" })).toBe(false);
    });

    test("returns false for pending", () => {
      expect(isItemExecuted({ executionState: "pending" })).toBe(false);
    });
  });

  describe("outcomeStatus signals (plan-candidate shape)", () => {
    test("returns true for outcomeStatus='executed-success'", () => {
      expect(isItemExecuted({ outcomeStatus: "executed-success" })).toBe(true);
    });

    test("returns true for outcomeStatus='executed-failed'", () => {
      expect(isItemExecuted({ outcomeStatus: "executed-failed" })).toBe(true);
    });

    test("returns true for outcomeStatus='timed-out'", () => {
      expect(isItemExecuted({ outcomeStatus: "timed-out" })).toBe(true);
    });

    test("returns true for outcomeStatus='completed'", () => {
      expect(isItemExecuted({ outcomeStatus: "completed" })).toBe(true);
    });

    test("returns false for null/undefined outcomeStatus", () => {
      expect(isItemExecuted({ outcomeStatus: null })).toBe(false);
      expect(isItemExecuted({ outcomeStatus: undefined })).toBe(false);
    });
  });

  describe("latestArtifactPath signals (plan-candidate shape)", () => {
    test("returns true when latestArtifactPath contains next-check-execution", () => {
      expect(
        isItemExecuted({ latestArtifactPath: "runs/abc/next-check-execution-0.json" })
      ).toBe(true);
    });

    test("returns false for non-execution artifact paths", () => {
      expect(
        isItemExecuted({ latestArtifactPath: "runs/abc/next-check-plan.json" })
      ).toBe(false);
    });

    test("returns false for null/undefined/latestArtifactPath", () => {
      expect(isItemExecuted({ latestArtifactPath: null })).toBe(false);
      expect(isItemExecuted({ latestArtifactPath: undefined })).toBe(false);
    });
  });

  describe("sourceArtifactRefs signals", () => {
    test("returns true when sourceArtifactRefs contains execution path", () => {
      expect(
        isItemExecuted({
          sourceArtifactRefs: [{ path: "runs/abc/next-check-execution-0.json" }],
        })
      ).toBe(true);
    });

    test("returns false when sourceArtifactRefs has no execution paths", () => {
      expect(
        isItemExecuted({
          sourceArtifactRefs: [{ path: "runs/abc/next-check-plan.json" }],
        })
      ).toBe(false);
    });

    test("returns false for empty sourceArtifactRefs", () => {
      expect(isItemExecuted({ sourceArtifactRefs: [] })).toBe(false);
    });
  });

  describe("mixed signals (split-brain scenarios)", () => {
    test("executionState=unexecuted + outcomeStatus=executed-success → executed", () => {
      // This is the key bug that was fixed: outcomeStatus should take precedence
      expect(
        isItemExecuted({
          executionState: "unexecuted",
          outcomeStatus: "executed-success",
        })
      ).toBe(true);
    });

    test("executionState=unexecuted + latestArtifactPath with execution → executed", () => {
      expect(
        isItemExecuted({
          executionState: "unexecuted",
          latestArtifactPath: "runs/abc/next-check-execution-0.json",
        })
      ).toBe(true);
    });

    test("executionState=unexecuted + sourceArtifactRefs with execution → executed", () => {
      expect(
        isItemExecuted({
          executionState: "unexecuted",
          sourceArtifactRefs: [{ path: "runs/abc/next-check-execution-0.json" }],
        })
      ).toBe(true);
    });
  });
});

describe("deriveExecutionLabel", () => {
  describe("executionState priority", () => {
    test("returns 'executed / success' for executionState=executed-success", () => {
      expect(deriveExecutionLabel({ executionState: "executed-success" })).toBe(
        "executed / success"
      );
    });

    test("returns 'executed / failed' for executionState=executed-failed", () => {
      expect(deriveExecutionLabel({ executionState: "executed-failed" })).toBe(
        "executed / failed"
      );
    });

    test("returns 'executed / timed-out' for executionState=timed-out", () => {
      expect(deriveExecutionLabel({ executionState: "timed-out" })).toBe(
        "executed / timed-out"
      );
    });

    test("returns 'executed / completed' for executionState=completed", () => {
      expect(deriveExecutionLabel({ executionState: "completed" })).toBe(
        "executed / completed"
      );
    });
  });

  describe("outcomeStatus priority (plan-candidate)", () => {
    test("returns execution label for outcomeStatus=executed-success", () => {
      expect(deriveExecutionLabel({ outcomeStatus: "executed-success" })).toBe(
        "executed / success"
      );
    });

    test("returns execution label for outcomeStatus=executed-failed", () => {
      expect(deriveExecutionLabel({ outcomeStatus: "executed-failed" })).toBe(
        "executed / failed"
      );
    });

    test("prefers executionState over outcomeStatus when both are present", () => {
      expect(
        deriveExecutionLabel({
          executionState: "executed-success",
          outcomeStatus: "executed-failed",
        })
      ).toBe("executed / success");
    });
  });

  describe("itemState priority", () => {
    test("returns 'executed' for itemState=executed with no executionState", () => {
      expect(deriveExecutionLabel({ itemState: "executed" })).toBe("executed");
    });

    test("returns 'executed' for itemState=executed with unexecuted", () => {
      expect(
        deriveExecutionLabel({ itemState: "executed", executionState: "unexecuted" })
      ).toBe("executed");
    });

    test("returns 'executed' for itemState=reviewed with no executionState", () => {
      expect(deriveExecutionLabel({ itemState: "reviewed" })).toBe("executed");
    });
  });

  describe("latestArtifactPath priority (plan-candidate)", () => {
    test("returns 'executed' for execution artifact path with no explicit status", () => {
      expect(
        deriveExecutionLabel({ latestArtifactPath: "runs/abc/next-check-execution-0.json" })
      ).toBe("executed");
    });

    test("uses outcomeStatus when available alongside execution artifact path", () => {
      expect(
        deriveExecutionLabel({
          latestArtifactPath: "runs/abc/next-check-execution-0.json",
          outcomeStatus: "executed-failed",
        })
      ).toBe("executed / failed");
    });
  });

  describe("not executed scenarios", () => {
    test("returns null for missing/null signals", () => {
      expect(deriveExecutionLabel({})).toBe(null);
      expect(deriveExecutionLabel({ executionState: null })).toBe(null);
      expect(deriveExecutionLabel({ executionState: undefined })).toBe(null);
    });

    test("returns null for unexecuted state with no other signals", () => {
      expect(deriveExecutionLabel({ executionState: "unexecuted" })).toBe(null);
    });

    test("returns null for pending state with no other signals", () => {
      expect(deriveExecutionLabel({ executionState: "pending" })).toBe(null);
    });
  });
});

describe("regression: split-brain between executionState and plan-candidate fields", () => {
  test("candidate with executionState=unexecuted + outcomeStatus=executed-success hides Run candidate", () => {
    // isItemExecuted should return true
    expect(
      isItemExecuted({
        executionState: "unexecuted",
        outcomeStatus: "executed-success",
      })
    ).toBe(true);

    // deriveExecutionLabel should show execution label
    expect(
      deriveExecutionLabel({
        executionState: "unexecuted",
        outcomeStatus: "executed-success",
      })
    ).toBe("executed / success");
  });

  test("candidate with executionState=unexecuted + latestArtifactPath with next-check-execution hides Run candidate", () => {
    expect(
      isItemExecuted({
        executionState: "unexecuted",
        latestArtifactPath: "runs/abc/next-check-execution-0.json",
      })
    ).toBe(true);
  });

  test("candidate with outcomeStatus=executed-failed shows 'executed / failed', not PENDING", () => {
    const label = deriveExecutionLabel({
      executionState: "unexecuted",
      outcomeStatus: "executed-failed",
    });
    expect(label).toBe("executed / failed");
  });

  test("unexecuted candidate with no artifact/outcome still needs Run candidate", () => {
    expect(
      isItemExecuted({
        executionState: "unexecuted",
      })
    ).toBe(false);

    expect(deriveExecutionLabel({ executionState: "unexecuted" })).toBe(null);
  });
});