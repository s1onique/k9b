/**
 * Pure unit tests for getRunsDisplayStatus helper function.
 * No mocking — tests the real implementation.
 */
import { describe, expect, test } from "vitest";
import { getRunsDisplayStatus } from "../useRunSelection";

describe("getRunsDisplayStatus", () => {
  test("returns 'unknown' for no-executions when counts are incomplete", () => {
    expect(getRunsDisplayStatus("no-executions", false)).toBe("unknown");
  });

  test("returns 'no-executions' when counts are complete", () => {
    expect(getRunsDisplayStatus("no-executions", true)).toBe("no-executions");
  });

  test("returns other review statuses directly regardless of counts", () => {
    expect(getRunsDisplayStatus("fully-reviewed", false)).toBe("fully-reviewed");
    expect(getRunsDisplayStatus("fully-reviewed", true)).toBe("fully-reviewed");
    expect(getRunsDisplayStatus("unreviewed", false)).toBe("unreviewed");
    expect(getRunsDisplayStatus("unreviewed", true)).toBe("unreviewed");
    expect(getRunsDisplayStatus("partially-reviewed", false)).toBe("partially-reviewed");
    expect(getRunsDisplayStatus("partially-reviewed", true)).toBe("partially-reviewed");
  });
});