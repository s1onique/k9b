/**
 * incidentsUpdate.test.ts
 *
 * Unit tests for the incidentsUpdate reducer.
 * Tests all Msg variants and update rules.
 */

import { describe, it, expect } from "vitest";
import { incidentsUpdate, isValidStatusFilter } from "../incidentsUpdate";
import type { IncidentsModel, IncidentsMsg } from "../incidentsTypes";

// Helper to create a minimal valid model
function createTestModel(overrides: Partial<IncidentsModel> = {}): IncidentsModel {
  return {
    runId: null,
    loadState: "idle",
    errorMessage: null,
    incidents: [],
    statusFilter: "all",
    page: 1,
    pageSize: 10,
    expandedIncidentIds: new Set(),
    refreshToken: 0,
    ...overrides,
  };
}

// Helper to create test incidents
function createTestIncidents(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    incident_id: `inc-${i}`,
    namespace: "default",
    object_kind: "Pod",
    object_name: `pod-${i}`,
    raw_object_kind: null,
    candidate_class: "Pod_failure",
    severity: "error",
    status: "open",
    first_observed_at: "2024-01-01T00:00:00Z",
    last_observed_at: "2024-01-01T00:00:00Z",
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

describe("incidentsUpdate", () => {
  describe("runChanged", () => {
    it("sets runId and resets page to 1", () => {
      const model = createTestModel({ page: 5 });
      const msg: IncidentsMsg = { type: "runChanged", runId: "run-123" };

      const result = incidentsUpdate(model, msg);

      expect(result.runId).toBe("run-123");
      expect(result.page).toBe(1);
      expect(result.loadState).toBe("loading");
      expect(result.expandedIncidentIds.size).toBe(0);
    });

    it("clears error on run change", () => {
      const model = createTestModel({ errorMessage: "Previous error" });
      const msg: IncidentsMsg = { type: "runChanged", runId: "run-456" };

      const result = incidentsUpdate(model, msg);

      expect(result.errorMessage).toBe(null);
    });

    it("collapses all expansions on run change", () => {
      const model = createTestModel({
        expandedIncidentIds: new Set(["inc-1", "inc-2"]),
      });
      const msg: IncidentsMsg = { type: "runChanged", runId: "run-789" };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.size).toBe(0);
    });

    it("handles null runId", () => {
      const model = createTestModel({ runId: "run-123" });
      const msg: IncidentsMsg = { type: "runChanged", runId: null };

      const result = incidentsUpdate(model, msg);

      expect(result.runId).toBe(null);
    });
  });

  describe("loadStarted", () => {
    it("sets loadState to loading", () => {
      const model = createTestModel({ loadState: "loaded" });
      const msg: IncidentsMsg = { type: "loadStarted" };

      const result = incidentsUpdate(model, msg);

      expect(result.loadState).toBe("loading");
    });

    it("clears error on load start", () => {
      const model = createTestModel({ errorMessage: "Previous error" });
      const msg: IncidentsMsg = { type: "loadStarted" };

      const result = incidentsUpdate(model, msg);

      expect(result.errorMessage).toBe(null);
    });
  });

  describe("loadSucceeded", () => {
    it("stores incidents and sets loadState to loaded", () => {
      const model = createTestModel({ loadState: "loading" });
      const incidents = createTestIncidents(3);
      const msg: IncidentsMsg = { type: "loadSucceeded", incidents };

      const result = incidentsUpdate(model, msg);

      expect(result.loadState).toBe("loaded");
      expect(result.incidents).toHaveLength(3);
      expect(result.errorMessage).toBe(null);
    });

    it("clamps page to valid range when filter reduces incidents", () => {
      const model = createTestModel({ 
        loadState: "loaded",
        page: 10,
        pageSize: 5,
        statusFilter: "open",
      });
      const incidents = createTestIncidents(3);
      const msg: IncidentsMsg = { type: "loadSucceeded", incidents };

      const result = incidentsUpdate(model, msg);

      // 3 incidents / 5 per page = 1 page max
      expect(result.page).toBe(1);
    });

    it("removes expanded IDs that no longer exist", () => {
      const model = createTestModel({
        expandedIncidentIds: new Set(["inc-1", "inc-2", "inc-999"]),
      });
      const incidents = createTestIncidents(3);
      const msg: IncidentsMsg = { type: "loadSucceeded", incidents };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.has("inc-1")).toBe(true);
      expect(result.expandedIncidentIds.has("inc-2")).toBe(true);
      expect(result.expandedIncidentIds.has("inc-999")).toBe(false);
    });
  });

  describe("loadFailed", () => {
    it("sets loadState to failed and stores error message", () => {
      const model = createTestModel({ loadState: "loading" });
      const msg: IncidentsMsg = { type: "loadFailed", message: "Network error" };

      const result = incidentsUpdate(model, msg);

      expect(result.loadState).toBe("failed");
      expect(result.errorMessage).toBe("Network error");
    });

    it("keeps old incidents on failure", () => {
      const model = createTestModel({
        loadState: "loading",
        incidents: createTestIncidents(5),
      });
      const msg: IncidentsMsg = { type: "loadFailed", message: "Error" };

      const result = incidentsUpdate(model, msg);

      expect(result.incidents).toHaveLength(5);
    });
  });

  describe("statusFilterChanged", () => {
    it("sets status filter", () => {
      const model = createTestModel({ statusFilter: "all" });
      const msg: IncidentsMsg = { type: "statusFilterChanged", statusFilter: "open" };

      const result = incidentsUpdate(model, msg);

      expect(result.statusFilter).toBe("open");
    });

    it("resets page to 1 on filter change", () => {
      const model = createTestModel({ page: 5 });
      const msg: IncidentsMsg = { type: "statusFilterChanged", statusFilter: "resolved" };

      const result = incidentsUpdate(model, msg);

      expect(result.page).toBe(1);
    });

    it("collapses all expansions on filter change", () => {
      const model = createTestModel({
        expandedIncidentIds: new Set(["inc-1", "inc-2"]),
      });
      const msg: IncidentsMsg = { type: "statusFilterChanged", statusFilter: "investigating" };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.size).toBe(0);
    });
  });

  describe("refreshRequested", () => {
    it("increments refreshToken to trigger refetch", () => {
      const model = createTestModel({ loadState: "loaded", refreshToken: 0 });
      const msg: IncidentsMsg = { type: "refreshRequested" };

      const result = incidentsUpdate(model, msg);

      expect(result.refreshToken).toBe(1);
      expect(result).not.toBe(model);
    });

    it("can increment token multiple times", () => {
      const model = createTestModel({ refreshToken: 5 });
      const msg: IncidentsMsg = { type: "refreshRequested" };

      const result = incidentsUpdate(model, msg);

      expect(result.refreshToken).toBe(6);
    });
  });

  describe("pageChanged", () => {
    it("updates page number", () => {
      const model = createTestModel({ 
        page: 1,
        incidents: createTestIncidents(50),
        pageSize: 10,
      });
      const msg: IncidentsMsg = { type: "pageChanged", page: 3 };

      const result = incidentsUpdate(model, msg);

      expect(result.page).toBe(3);
    });

    it("clamps page to valid range", () => {
      const model = createTestModel({
        page: 1,
        incidents: createTestIncidents(10),
        pageSize: 10,
      });
      const msg: IncidentsMsg = { type: "pageChanged", page: 99 };

      const result = incidentsUpdate(model, msg);

      // 10 incidents / 10 per page = 1 page
      expect(result.page).toBe(1);
    });

    it("clamps negative page to 1", () => {
      const model = createTestModel({ page: 1 });
      const msg: IncidentsMsg = { type: "pageChanged", page: -5 };

      const result = incidentsUpdate(model, msg);

      expect(result.page).toBe(1);
    });

    it("collapses all expansions on page change", () => {
      const model = createTestModel({
        expandedIncidentIds: new Set(["inc-1"]),
      });
      const msg: IncidentsMsg = { type: "pageChanged", page: 2 };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.size).toBe(0);
    });
  });

  describe("pageSizeChanged", () => {
    it("updates page size", () => {
      const model = createTestModel({ pageSize: 10 });
      const msg: IncidentsMsg = { type: "pageSizeChanged", pageSize: 25 };

      const result = incidentsUpdate(model, msg);

      expect(result.pageSize).toBe(25);
    });

    it("resets page to 1 on page size change", () => {
      const model = createTestModel({ page: 5, pageSize: 10 });
      const msg: IncidentsMsg = { type: "pageSizeChanged", pageSize: 50 };

      const result = incidentsUpdate(model, msg);

      expect(result.page).toBe(1);
    });

    it("collapses all expansions on page size change", () => {
      const model = createTestModel({
        expandedIncidentIds: new Set(["inc-1"]),
      });
      const msg: IncidentsMsg = { type: "pageSizeChanged", pageSize: 25 };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.size).toBe(0);
    });

    it("ignores invalid page size", () => {
      const model = createTestModel({ pageSize: 10 });
      const msg: IncidentsMsg = { type: "pageSizeChanged", pageSize: 33 };

      const result = incidentsUpdate(model, msg);

      // Should keep original page size
      expect(result.pageSize).toBe(10);
    });
  });

  describe("incidentExpansionToggled", () => {
    it("adds incident to expanded set when not present", () => {
      const model = createTestModel({ expandedIncidentIds: new Set() });
      const msg: IncidentsMsg = { type: "incidentExpansionToggled", incidentId: "inc-1" };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.has("inc-1")).toBe(true);
    });

    it("removes incident from expanded set when present", () => {
      const model = createTestModel({
        expandedIncidentIds: new Set(["inc-1", "inc-2"]),
      });
      const msg: IncidentsMsg = { type: "incidentExpansionToggled", incidentId: "inc-1" };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.has("inc-1")).toBe(false);
      expect(result.expandedIncidentIds.has("inc-2")).toBe(true);
    });

    it("allows multiple expanded incidents", () => {
      const model = createTestModel({ expandedIncidentIds: new Set(["inc-1"]) });
      const msg: IncidentsMsg = { type: "incidentExpansionToggled", incidentId: "inc-2" };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.has("inc-1")).toBe(true);
      expect(result.expandedIncidentIds.has("inc-2")).toBe(true);
    });
  });

  describe("allExpansionsCollapsed", () => {
    it("clears all expanded incidents", () => {
      const model = createTestModel({
        expandedIncidentIds: new Set(["inc-1", "inc-2", "inc-3"]),
      });
      const msg: IncidentsMsg = { type: "allExpansionsCollapsed" };

      const result = incidentsUpdate(model, msg);

      expect(result.expandedIncidentIds.size).toBe(0);
    });
  });
});

describe("isValidStatusFilter", () => {
  it("returns true for valid filters", () => {
    expect(isValidStatusFilter("all")).toBe(true);
    expect(isValidStatusFilter("open")).toBe(true);
    expect(isValidStatusFilter("collecting_evidence")).toBe(true);
    expect(isValidStatusFilter("ready_for_review")).toBe(true);
    expect(isValidStatusFilter("investigating")).toBe(true);
    expect(isValidStatusFilter("suppressed")).toBe(true);
    expect(isValidStatusFilter("duplicate")).toBe(true);
    expect(isValidStatusFilter("resolved")).toBe(true);
  });

  it("returns false for invalid filters", () => {
    expect(isValidStatusFilter("invalid")).toBe(false);
    expect(isValidStatusFilter("")).toBe(false);
    expect(isValidStatusFilter("OPEN")).toBe(false);
  });
});
