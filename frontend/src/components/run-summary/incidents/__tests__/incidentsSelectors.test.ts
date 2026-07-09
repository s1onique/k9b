/**
 * incidentsSelectors.test.ts
 *
 * Unit tests for the incidentsSelectors.
 * Tests all selector functions for correctness.
 */

import { describe, it, expect } from "vitest";
import {
  selectFilteredIncidents,
  selectIncidentStatusCounts,
  selectSortedIncidents,
  selectPageCount,
  selectVisibleIncidents,
  selectPageRangeLabel,
  selectIsIncidentExpanded,
  selectHasExpandedIncidents,
  selectTotalStatusCounts,
  selectFilteredStatusCounts,
} from "../incidentsSelectors";
import type { IncidentsModel, IncidentSummaryPayload } from "../incidentsTypes";

// Helper to create test incidents
function createTestIncidents(
  count: number,
  options: Partial<{
    status: string;
    severity: string;
    last_observed_at: string;
  }> = {}
): IncidentSummaryPayload[] {
  const { status = "open", severity = "error", last_observed_at = "2024-01-01T00:00:00Z" } = options;
  
  return Array.from({ length: count }, (_, i) => ({
    incident_id: `inc-${i}`,
    namespace: "default",
    object_kind: "Pod",
    object_name: `pod-${i}`,
    raw_object_kind: null,
    candidate_class: "Pod_failure",
    severity,
    status,
    first_observed_at: "2024-01-01T00:00:00Z",
    last_observed_at,
    signal_count: 1,
    evidence_count: 0,
    latest_snapshot_bundle_id: null,
    review_packet: { status: "not_generated" },
    suppressed_reason: null,
    duplicate_of: null,
    resolved_at: null,
    resolution_notes: null,
  }));
}

// Helper to create a test model
function createTestModel(overrides: Partial<IncidentsModel> = {}): IncidentsModel {
  return {
    runId: "run-123",
    loadState: "loaded",
    errorMessage: null,
    incidents: [],
    statusFilter: "all",
    page: 1,
    pageSize: 10,
    expandedIncidentIds: new ReadonlySet(),
    refreshToken: 0,
    ...overrides,
  };
}

describe("selectFilteredIncidents", () => {
  it("returns all incidents when filter is 'all'", () => {
    const incidents = [
      ...createTestIncidents(3, { status: "open" }),
      ...createTestIncidents(2, { status: "resolved" }),
    ];
    const model = createTestModel({ incidents, statusFilter: "all" });

    const result = selectFilteredIncidents(model);

    expect(result).toHaveLength(5);
  });

  it("filters by status correctly", () => {
    const incidents = [
      ...createTestIncidents(3, { status: "open" }),
      ...createTestIncidents(2, { status: "resolved" }),
    ];
    const model = createTestModel({ incidents, statusFilter: "open" });

    const result = selectFilteredIncidents(model);

    expect(result).toHaveLength(3);
    expect(result.every((i) => i.status === "open")).toBe(true);
  });

  it("returns empty array when no incidents match filter", () => {
    const incidents = createTestIncidents(3, { status: "open" });
    const model = createTestModel({ incidents, statusFilter: "resolved" });

    const result = selectFilteredIncidents(model);

    expect(result).toHaveLength(0);
  });

  it("does not mutate the original array", () => {
    const incidents = createTestIncidents(3, { status: "open" });
    const model = createTestModel({ incidents, statusFilter: "resolved" });

    selectFilteredIncidents(model);

    expect(incidents).toHaveLength(3);
  });
});

describe("selectIncidentStatusCounts", () => {
  it("counts all statuses correctly", () => {
    const incidents: IncidentSummaryPayload[] = [
      ...createTestIncidents(5, { status: "open" }),
      ...createTestIncidents(3, { status: "collecting_evidence" }),
      ...createTestIncidents(2, { status: "ready_for_review" }),
      ...createTestIncidents(1, { status: "investigating" }),
      ...createTestIncidents(4, { status: "resolved" }),
    ];

    const counts = selectIncidentStatusCounts(incidents);

    expect(counts.open).toBe(5);
    expect(counts.collecting_evidence).toBe(3);
    expect(counts.ready_for_review).toBe(2);
    expect(counts.investigating).toBe(1);
    expect(counts.resolved).toBe(4);
    expect(counts.total).toBe(15);
  });

  it("handles empty array", () => {
    const counts = selectIncidentStatusCounts([]);

    expect(counts.total).toBe(0);
    expect(counts.open).toBe(0);
  });

  it("ignores unknown statuses", () => {
    const incidents = createTestIncidents(2, { status: "unknown_status" as any });

    const counts = selectIncidentStatusCounts(incidents);

    expect(counts.total).toBe(2);
    expect(counts.open).toBe(0);
  });
});

describe("selectSortedIncidents", () => {
  it("sorts by severity descending (error > warning > info)", () => {
    const incidents: IncidentSummaryPayload[] = [
      ...createTestIncidents(2, { severity: "info" }),
      ...createTestIncidents(2, { severity: "error" }),
      ...createTestIncidents(2, { severity: "warning" }),
    ];

    const sorted = selectSortedIncidents(incidents);

    expect(sorted[0].severity).toBe("error");
    expect(sorted[1].severity).toBe("error");
    expect(sorted[2].severity).toBe("warning");
    expect(sorted[3].severity).toBe("warning");
    expect(sorted[4].severity).toBe("info");
    expect(sorted[5].severity).toBe("info");
  });

  it("sorts by last_observed_at descending within same severity", () => {
    const incidents: IncidentSummaryPayload[] = [
      ...createTestIncidents(1, { last_observed_at: "2024-01-01T00:00:00Z" }),
      ...createTestIncidents(1, { last_observed_at: "2024-01-03T00:00:00Z" }),
      ...createTestIncidents(1, { last_observed_at: "2024-01-02T00:00:00Z" }),
    ];

    const sorted = selectSortedIncidents(incidents);

    expect(sorted[0].last_observed_at).toBe("2024-01-03T00:00:00Z");
    expect(sorted[1].last_observed_at).toBe("2024-01-02T00:00:00Z");
    expect(sorted[2].last_observed_at).toBe("2024-01-01T00:00:00Z");
  });

  it("uses incident_id as tiebreaker", () => {
    const now = "2024-01-01T00:00:00Z";
    const incidents: IncidentSummaryPayload[] = [
      { ...createTestIncidents(1, { last_observed_at: now })[0], incident_id: "zzz" },
      { ...createTestIncidents(1, { last_observed_at: now })[0], incident_id: "aaa" },
    ];

    const sorted = selectSortedIncidents(incidents);

    expect(sorted[0].incident_id).toBe("aaa");
    expect(sorted[1].incident_id).toBe("zzz");
  });

  it("does not mutate the original array", () => {
    const incidents = createTestIncidents(3);

    selectSortedIncidents(incidents);

    // Original array should still have all elements
    expect(incidents).toHaveLength(3);
  });
});

describe("selectPageCount", () => {
  it("returns 1 for 0 items", () => {
    expect(selectPageCount(0, 10)).toBe(1);
  });

  it("calculates page count correctly", () => {
    expect(selectPageCount(10, 10)).toBe(1);
    expect(selectPageCount(11, 10)).toBe(2);
    expect(selectPageCount(25, 10)).toBe(3);
    expect(selectPageCount(100, 10)).toBe(10);
  });

  it("handles different page sizes", () => {
    expect(selectPageCount(50, 25)).toBe(2);
    expect(selectPageCount(50, 50)).toBe(1);
    expect(selectPageCount(50, 100)).toBe(1);
  });
});

describe("selectVisibleIncidents", () => {
  it("returns page 1 incidents", () => {
    const incidents = createTestIncidents(15);
    const model = createTestModel({ incidents, page: 1, pageSize: 10 });

    const visible = selectVisibleIncidents(model);

    expect(visible).toHaveLength(10);
  });

  it("returns correct page of incidents", () => {
    const incidents = createTestIncidents(15);
    const model = createTestModel({ incidents, page: 2, pageSize: 10 });

    const visible = selectVisibleIncidents(model);

    expect(visible).toHaveLength(5);
  });

  it("clamps to valid page range", () => {
    const incidents = createTestIncidents(15);
    const model = createTestModel({ incidents, page: 99, pageSize: 10 });

    const visible = selectVisibleIncidents(model);

    // Should show last page (page 2)
    expect(visible).toHaveLength(5);
  });

  it("handles empty filtered list", () => {
    const model = createTestModel({ incidents: [], page: 1, pageSize: 10 });

    const visible = selectVisibleIncidents(model);

    expect(visible).toHaveLength(0);
  });

  it("applies status filter before pagination", () => {
    const incidents: IncidentSummaryPayload[] = [
      ...createTestIncidents(12, { status: "open" }),
      ...createTestIncidents(3, { status: "resolved" }),
    ];
    const model = createTestModel({ incidents, statusFilter: "open", page: 2, pageSize: 10 });

    const visible = selectVisibleIncidents(model);

    // Only 12 open incidents, page 2 should show 2
    expect(visible).toHaveLength(2);
    expect(visible.every((i) => i.status === "open")).toBe(true);
  });
});

describe("selectPageRangeLabel", () => {
  it("returns 'No incidents' for empty list", () => {
    const model = createTestModel({ incidents: [] });

    expect(selectPageRangeLabel(model)).toBe("No incidents");
  });

  it("returns correct label for first page", () => {
    const incidents = createTestIncidents(42);
    const model = createTestModel({ incidents, page: 1, pageSize: 10 });

    expect(selectPageRangeLabel(model)).toBe("Showing 1–10 of 42");
  });

  it("returns correct label for middle page", () => {
    const incidents = createTestIncidents(42);
    const model = createTestModel({ incidents, page: 2, pageSize: 10 });

    expect(selectPageRangeLabel(model)).toBe("Showing 11–20 of 42");
  });

  it("returns correct label for last page", () => {
    const incidents = createTestIncidents(42);
    const model = createTestModel({ incidents, page: 5, pageSize: 10 });

    expect(selectPageRangeLabel(model)).toBe("Showing 41–42 of 42");
  });

  it("handles small dataset (single page)", () => {
    const incidents = createTestIncidents(5);
    const model = createTestModel({ incidents, page: 1, pageSize: 10 });

    expect(selectPageRangeLabel(model)).toBe("Showing 5 of 5");
  });

  it("handles exact page boundary", () => {
    const incidents = createTestIncidents(20);
    const model = createTestModel({ incidents, page: 2, pageSize: 10 });

    expect(selectPageRangeLabel(model)).toBe("Showing 11–20 of 20");
  });
});

describe("selectIsIncidentExpanded", () => {
  it("returns true when incident is expanded", () => {
    const model = createTestModel({
      expandedIncidentIds: new ReadonlySet(["inc-1", "inc-2"]),
    });

    expect(selectIsIncidentExpanded(model, "inc-1")).toBe(true);
    expect(selectIsIncidentExpanded(model, "inc-2")).toBe(true);
  });

  it("returns false when incident is not expanded", () => {
    const model = createTestModel({
      expandedIncidentIds: new ReadonlySet(["inc-1"]),
    });

    expect(selectIsIncidentExpanded(model, "inc-2")).toBe(false);
  });

  it("returns false for empty expanded set", () => {
    const model = createTestModel({
      expandedIncidentIds: new ReadonlySet(),
    });

    expect(selectIsIncidentExpanded(model, "inc-1")).toBe(false);
  });
});

describe("selectHasExpandedIncidents", () => {
  it("returns true when there are expanded incidents", () => {
    const model = createTestModel({
      expandedIncidentIds: new ReadonlySet(["inc-1"]),
    });

    expect(selectHasExpandedIncidents(model)).toBe(true);
  });

  it("returns false when no incidents are expanded", () => {
    const model = createTestModel({
      expandedIncidentIds: new ReadonlySet(),
    });

    expect(selectHasExpandedIncidents(model)).toBe(false);
  });
});

describe("selectTotalStatusCounts", () => {
  it("counts all incidents regardless of filter", () => {
    const incidents: IncidentSummaryPayload[] = [
      ...createTestIncidents(5, { status: "open" }),
      ...createTestIncidents(3, { status: "resolved" }),
    ];
    const model = createTestModel({
      incidents,
      statusFilter: "open",
    });

    const counts = selectTotalStatusCounts(model);

    expect(counts.total).toBe(8);
    expect(counts.open).toBe(5);
    expect(counts.resolved).toBe(3);
  });
});

describe("selectFilteredStatusCounts", () => {
  it("counts only filtered incidents", () => {
    const incidents: IncidentSummaryPayload[] = [
      ...createTestIncidents(5, { status: "open" }),
      ...createTestIncidents(3, { status: "resolved" }),
    ];
    const model = createTestModel({
      incidents,
      statusFilter: "open",
    });

    const counts = selectFilteredStatusCounts(model);

    expect(counts.total).toBe(5);
    expect(counts.open).toBe(5);
    expect(counts.resolved).toBe(0);
  });
});
