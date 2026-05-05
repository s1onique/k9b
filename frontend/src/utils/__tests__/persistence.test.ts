/**
 * Focused tests for localStorage persistence helpers in persistence.ts.
 * Tests all storage helpers extracted from App.tsx.
 */
import {
  clearStoredQueueViewState,
  DEFAULT_QUEUE_VIEW_STATE,
  isRunsPageSizeValue,
  persistQueueViewState,
  persistRunsPageSize,
  persistRunsReviewFilter,
  persistSelectedRunId,
  QUEUE_VIEW_STORAGE_KEY,
  readStoredQueueViewState,
  readStoredRunsPageSize,
  readStoredRunsReviewFilter,
  readStoredSelectedRunId,
  RUNS_PAGE_SIZE_STORAGE_KEY,
  RUNS_REVIEW_FILTER_STORAGE_KEY,
  SELECTED_RUN_STORAGE_KEY,
  type QueueViewState,
} from "../persistence";

describe("storage keys", () => {
  it("exports QUEUE_VIEW_STORAGE_KEY", () => {
    expect(QUEUE_VIEW_STORAGE_KEY).toBe("dashboard-queue-view-state");
  });

  it("exports RUNS_REVIEW_FILTER_STORAGE_KEY", () => {
    expect(RUNS_REVIEW_FILTER_STORAGE_KEY).toBe("dashboard-runs-review-filter");
  });

  it("exports SELECTED_RUN_STORAGE_KEY", () => {
    expect(SELECTED_RUN_STORAGE_KEY).toBe("dashboard-selected-run-id");
  });

  it("exports RUNS_PAGE_SIZE_STORAGE_KEY", () => {
    expect(RUNS_PAGE_SIZE_STORAGE_KEY).toBe("dashboard-runs-page-size");
  });
});

describe("readStoredRunsReviewFilter", () => {
  const key = RUNS_REVIEW_FILTER_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
  });

  it("returns default filter when storage is empty", () => {
    expect(readStoredRunsReviewFilter()).toBe("all");
  });

  it("returns stored valid filter value", () => {
    localStorage.setItem(key, "awaiting-review");
    expect(readStoredRunsReviewFilter()).toBe("awaiting-review");
  });

  it("returns default when stored value is invalid", () => {
    localStorage.setItem(key, "invalid-value");
    expect(readStoredRunsReviewFilter()).toBe("all");
  });

  it("returns default when stored value is empty string", () => {
    localStorage.setItem(key, "");
    expect(readStoredRunsReviewFilter()).toBe("all");
  });
});

describe("persistRunsReviewFilter", () => {
  const key = RUNS_REVIEW_FILTER_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
  });

  it("writes the exact filter value", () => {
    persistRunsReviewFilter("fully-reviewed");
    expect(localStorage.getItem(key)).toBe("fully-reviewed");
  });

  it("writes 'all' filter value", () => {
    persistRunsReviewFilter("all");
    expect(localStorage.getItem(key)).toBe("all");
  });
});

describe("readStoredSelectedRunId", () => {
  const key = SELECTED_RUN_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when storage is empty", () => {
    expect(readStoredSelectedRunId()).toBeNull();
  });

  it("returns stored run ID", () => {
    localStorage.setItem(key, "run-abc123");
    expect(readStoredSelectedRunId()).toBe("run-abc123");
  });

  it("returns null when stored value is empty", () => {
    localStorage.setItem(key, "");
    // Empty string is falsy, so !stored triggers null return
    expect(readStoredSelectedRunId()).toBeNull();
  });
});

describe("persistSelectedRunId", () => {
  const key = SELECTED_RUN_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
  });

  it("writes the run ID when value is non-empty", () => {
    persistSelectedRunId("run-xyz789");
    expect(localStorage.getItem(key)).toBe("run-xyz789");
  });

  it("removes the key when value is null", () => {
    localStorage.setItem(key, "run-xyz789");
    persistSelectedRunId(null);
    expect(localStorage.getItem(key)).toBeNull();
  });

  it("removes the key when value is undefined", () => {
    localStorage.setItem(key, "run-xyz789");
    persistSelectedRunId(undefined as unknown as null);
    expect(localStorage.getItem(key)).toBeNull();
  });

  it("removes the key when value is empty string", () => {
    localStorage.setItem(key, "run-xyz789");
    persistSelectedRunId("");
    expect(localStorage.getItem(key)).toBeNull();
  });
});

describe("isRunsPageSizeValue", () => {
  it("accepts allowed page sizes", () => {
    expect(isRunsPageSizeValue(5)).toBe(true);
    expect(isRunsPageSizeValue(10)).toBe(true);
    expect(isRunsPageSizeValue(20)).toBe(true);
  });

  it("rejects non-allowed page sizes", () => {
    expect(isRunsPageSizeValue(1)).toBe(false);
    expect(isRunsPageSizeValue(15)).toBe(false);
    expect(isRunsPageSizeValue(25)).toBe(false);
    expect(isRunsPageSizeValue(0)).toBe(false);
    expect(isRunsPageSizeValue(-5)).toBe(false);
  });

  it("rejects non-number values", () => {
    expect(isRunsPageSizeValue("5")).toBe(false);
    expect(isRunsPageSizeValue(null)).toBe(false);
    expect(isRunsPageSizeValue(undefined)).toBe(false);
    expect(isRunsPageSizeValue({})).toBe(false);
    expect(isRunsPageSizeValue([])).toBe(false);
  });
});

describe("readStoredRunsPageSize", () => {
  const key = RUNS_PAGE_SIZE_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
  });

  it("returns default when storage is empty", () => {
    expect(readStoredRunsPageSize()).toBe(5);
  });

  it("returns stored valid page size", () => {
    localStorage.setItem(key, "10");
    expect(readStoredRunsPageSize()).toBe(10);
  });

  it("returns default for invalid values", () => {
    localStorage.setItem(key, "invalid");
    expect(readStoredRunsPageSize()).toBe(5);
  });

  it("returns stored value for values >= 1 and <= 20 (even if not in options)", () => {
    // The read function only validates NaN, <1, and >20, allowing 1 through
    localStorage.setItem(key, "1");
    expect(readStoredRunsPageSize()).toBe(1);
  });

  it("returns default for values above maximum (20)", () => {
    localStorage.setItem(key, "25");
    expect(readStoredRunsPageSize()).toBe(5);
  });

  it("returns default for zero", () => {
    localStorage.setItem(key, "0");
    expect(readStoredRunsPageSize()).toBe(5);
  });

  it("returns default for negative values", () => {
    localStorage.setItem(key, "-5");
    expect(readStoredRunsPageSize()).toBe(5);
  });

  it("returns default for non-numeric strings", () => {
    localStorage.setItem(key, "abc");
    expect(readStoredRunsPageSize()).toBe(5);
  });
});

describe("persistRunsPageSize", () => {
  const key = RUNS_PAGE_SIZE_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
  });

  it("writes numeric value as string", () => {
    persistRunsPageSize(10);
    expect(localStorage.getItem(key)).toBe("10");
  });

  it("writes the exact number format", () => {
    persistRunsPageSize(20);
    expect(localStorage.getItem(key)).toBe("20");
  });
});

describe("readStoredQueueViewState", () => {
  const key = QUEUE_VIEW_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
  });

  it("returns default state when storage is empty", () => {
    expect(readStoredQueueViewState()).toEqual(DEFAULT_QUEUE_VIEW_STATE);
  });

  it("returns parsed valid queue view state", () => {
    const validState: QueueViewState = {
      clusterFilter: "prod",
      statusFilter: "safe-ready",
      commandFamilyFilter: "all",
      priorityFilter: "primary",
      workstreamFilter: "all",
      searchText: "nginx",
      focusMode: "work",
      sortOption: "priority",
    };
    localStorage.setItem(key, JSON.stringify(validState));
    expect(readStoredQueueViewState()).toEqual(validState);
  });

  it("returns default on malformed JSON", () => {
    localStorage.setItem(key, "not valid json");
    expect(readStoredQueueViewState()).toEqual(DEFAULT_QUEUE_VIEW_STATE);
  });

  it("returns default on invalid JSON structure", () => {
    localStorage.setItem(key, JSON.stringify("just a string"));
    expect(readStoredQueueViewState()).toEqual(DEFAULT_QUEUE_VIEW_STATE);
  });

  it("returns default on null JSON", () => {
    localStorage.setItem(key, "null");
    expect(readStoredQueueViewState()).toEqual(DEFAULT_QUEUE_VIEW_STATE);
  });

  it("returns default on invalid sort option", () => {
    const invalidState = {
      ...DEFAULT_QUEUE_VIEW_STATE,
      sortOption: "invalid-sort",
    };
    localStorage.setItem(key, JSON.stringify(invalidState));
    expect(readStoredQueueViewState()).toEqual(DEFAULT_QUEUE_VIEW_STATE);
  });

  it("returns default on invalid focus mode", () => {
    const invalidState = {
      ...DEFAULT_QUEUE_VIEW_STATE,
      focusMode: "invalid-focus",
    };
    localStorage.setItem(key, JSON.stringify(invalidState));
    expect(readStoredQueueViewState()).toEqual(DEFAULT_QUEUE_VIEW_STATE);
  });

  it("returns default on invalid status filter", () => {
    const invalidState = {
      ...DEFAULT_QUEUE_VIEW_STATE,
      statusFilter: "invalid-status",
    };
    localStorage.setItem(key, JSON.stringify(invalidState));
    expect(readStoredQueueViewState()).toEqual(DEFAULT_QUEUE_VIEW_STATE);
  });

  it("partially parses valid fields with invalid fields falling back to defaults", () => {
    const partialState = {
      clusterFilter: "staging",
      focusMode: "review",
      // missing other fields
    };
    localStorage.setItem(key, JSON.stringify(partialState));
    const result = readStoredQueueViewState();
    expect(result.clusterFilter).toBe("staging");
    expect(result.focusMode).toBe("review");
    expect(result.statusFilter).toBe(DEFAULT_QUEUE_VIEW_STATE.statusFilter);
    expect(result.sortOption).toBe(DEFAULT_QUEUE_VIEW_STATE.sortOption);
  });
});

describe("persistQueueViewState", () => {
  const key = QUEUE_VIEW_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
  });

  it("writes queue view state as JSON string", () => {
    const state: QueueViewState = {
      clusterFilter: "prod",
      statusFilter: "all",
      commandFamilyFilter: "all",
      priorityFilter: "all",
      workstreamFilter: "all",
      searchText: "",
      focusMode: "none",
      sortOption: "default",
    };
    persistQueueViewState(state);
    expect(localStorage.getItem(key)).toBe(JSON.stringify(state));
  });
});

describe("clearStoredQueueViewState", () => {
  const key = QUEUE_VIEW_STORAGE_KEY;

  beforeEach(() => {
    localStorage.clear();
    // Set up some other keys to ensure only queue view state is cleared
    localStorage.setItem("some-other-key", "value");
    localStorage.setItem(QUEUE_VIEW_STORAGE_KEY, JSON.stringify({ clusterFilter: "prod" }));
  });

  it("removes only queue view state key", () => {
    clearStoredQueueViewState();
    expect(localStorage.getItem(key)).toBeNull();
    expect(localStorage.getItem("some-other-key")).toBe("value");
  });

  it("handles missing key gracefully", () => {
    localStorage.clear();
    expect(() => clearStoredQueueViewState()).not.toThrow();
  });
});