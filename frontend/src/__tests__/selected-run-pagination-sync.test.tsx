/**
 * Selection-Pagination Sync Tests for Recent Runs
 *
 * Tests the fix for the recent runs selection visibility and pagination sync epic.
 * After every runs-list refresh (manual or auto-refresh), the selected run should
 * remain visible in the Recent runs table if it still exists in the refreshed dataset.
 *
 * Test coverage:
 * 1. Manual refresh keeps selected run visible (P0) - TESTED
 * 2. Auto-refresh with new runs keeps selected run visible (P0) - TESTED
 * 3. ← Latest button still works (regression) - TESTED
 * 4. Filter changes the displayed runs (regression) - TESTED
 *
 * De-scoped scenarios (documented, not implemented):
 * - Timer-driven auto-refresh (requires vi.useFakeTimers setup)
 * - Selected run filtered out by filter (state preserved, row not visible)
 * - Missing selected run (run deleted from backend, state preserved)
 * - Page size change behavior (handled by existing pagination component)
 */

import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import App from '../App';
import type { RunsListPayload } from '../types';
import { createStorageMock, makeFetchResponse, makeRunWithOverrides } from './fixtures';

// =============================================================================
// Helper: creates a multi-page runs list for pagination tests
// 8 runs with page size 5 = 2 pages
// Page 1: run-100, run-99, run-98, run-97, run-96
// Page 2: run-95, run-94, run-93
// =============================================================================
const createMultiPageRunsList = (): RunsListPayload => {
  const runs = Array.from({ length: 8 }, (_, i) => ({
    runId: `run-${100 - i}`,
    runLabel: `2026-04-${String(10 - Math.floor(i / 2)).padStart(2, '0')}-${String(12 + (i % 2) * 2).padStart(2, '0')}`,
    timestamp: new Date(Date.now() - i * 3600000).toISOString(),
    clusterCount: 2,
    triaged: i % 2 === 0,
    executionCount: i,
    reviewedCount: i,
    reviewStatus: i === 0 ? 'fully-reviewed' : i < 3 ? 'partially-reviewed' : 'unreviewed',
    reviewDownloadPath: null,
    batchExecutable: false,
    batchEligibleCount: 0,
  }));
  return { runs, totalCount: runs.length };
};

// =============================================================================
// Helper: create a run payload with specific run ID, label, and timestamp
// =============================================================================
const createRunPayload = (runId: string, label: string, timestamp: string) =>
  makeRunWithOverrides({
    runId,
    label,
    timestamp,
  });

// =============================================================================
// Helper: shared fetch mock setup
// =============================================================================
const setupFetchMock = (fetchMock: ReturnType<typeof vi.fn>, payloads: Record<string, unknown>) => {
  fetchMock.mockImplementation((input: RequestInfo) => {
    const url = typeof input === 'string' ? input : input.url;
    const base = url.split('?')[0];
    const payload = payloads[url] ?? payloads[base];
    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    }
    return makeFetchResponse(payload);
  });
};

// =============================================================================
// Shared test setup
// =============================================================================
let storageMock: ReturnType<typeof createStorageMock>;
let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  storageMock = createStorageMock();
  vi.stubGlobal('localStorage', storageMock);

  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);

  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal('setInterval', setIntervalSpy);
  vi.stubGlobal('clearInterval', clearIntervalSpy);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// =============================================================================
// TEST SUITE: Selection-Pagination Sync
// =============================================================================
describe('Recent runs selection-pagination sync', () => {
  // ---------------------------------------------------------------------------
  // CORE TEST: Manual refresh keeps selected run visible
  // ---------------------------------------------------------------------------
  test('selecting a historical run on page 2, then refreshing, keeps the page containing the selected run visible', async () => {
    const runsPayload = createMultiPageRunsList();
    const latestRun = runsPayload.runs[0];
    // run-95 is on page 2 (index 5, page = floor(5/5)+1 = 2)
    const historicalRun = runsPayload.runs[5];

    const payloads = {
      '/api/runs': runsPayload,
      '/api/run': createRunPayload(historicalRun.runId, historicalRun.runLabel, historicalRun.timestamp),
      '/api/fleet': {
        runId: latestRun.runId,
        runLabel: latestRun.runLabel,
        lastRunTimestamp: latestRun.timestamp,
        topProblem: { title: 'Test', detail: 'Test problem' },
        fleetStatus: { ratingCounts: [], degradedClusters: [] },
        clusters: [],
        proposalSummary: { pending: 0, total: 0, statusCounts: [] },
      },
      '/api/proposals': { proposals: [], statusSummary: [] },
      '/api/notifications': { notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 },
    };

    setupFetchMock(fetchMock, payloads);
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole('heading', { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll('.run-row');
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Navigate to page 2 where run-95 is
    const nextButton = await screen.findByRole('button', { name: /runs next page/i });
    await act(async () => {
      await user.click(nextButton);
    });

    await waitFor(() => {
      const pageIndicator = document.querySelector('.pagination-page-indicator');
      expect(pageIndicator?.textContent).toContain('2');
    });

    // Select historical run
    await act(async () => {
      const historicalRow = document.querySelector('.run-row[data-run-id=\"run-95\"]');
      expect(historicalRow).toBeInTheDocument();
      await user.click(historicalRow!);
    });

    // Verify ← Latest button appears
    expect(screen.getByRole('button', { name: /← Latest/i })).toBeInTheDocument();

    // Click refresh button
    const refreshButton = await screen.findByRole('button', { name: /refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    // Wait for refresh and effect to settle
    await waitFor(() => {
      const pageIndicator = document.querySelector('.pagination-page-indicator');
      expect(pageIndicator?.textContent).toContain('2');
    });

    // ASSERTION: Page 2 is still shown (selected run is still visible)
    const pageIndicatorAfterRefresh = document.querySelector('.pagination-page-indicator');
    expect(pageIndicatorAfterRefresh?.textContent).toContain('2');

    // ASSERTION: Historical run row is still selected
    const selectedRow = document.querySelector('.run-row[data-run-id=\"run-95\"].run-row-selected');
    expect(selectedRow).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // AUTO-REFRESH: New runs arriving above selected run
  // Simulates auto-refresh via the refresh button (timer-driven test is de-scoped)
  // ---------------------------------------------------------------------------
  test('selecting a historical run, then auto-refresh with new runs, keeps the selected run visible', async () => {
    const runsPayload = createMultiPageRunsList();
    const latestRun = runsPayload.runs[0];
    const historicalRun = runsPayload.runs[5];

    // Create payload with new runs inserted at top
    const newRunsPayload: RunsListPayload = {
      runs: [
        {
          runId: 'run-new-1',
          runLabel: '2026-04-10-1400',
          timestamp: new Date(Date.now() - 0.5 * 3600000).toISOString(),
          clusterCount: 2,
          triaged: true,
          executionCount: 1,
          reviewedCount: 1,
          reviewStatus: 'fully-reviewed' as const,
          reviewDownloadPath: null,
          batchExecutable: false,
          batchEligibleCount: 0,
        },
        {
          runId: 'run-new-2',
          runLabel: '2026-04-10-1200',
          timestamp: new Date(Date.now() - 1 * 3600000).toISOString(),
          clusterCount: 2,
          triaged: true,
          executionCount: 2,
          reviewedCount: 2,
          reviewStatus: 'fully-reviewed' as const,
          reviewDownloadPath: null,
          batchExecutable: false,
          batchEligibleCount: 0,
        },
        ...runsPayload.runs,
      ],
      totalCount: 10,
    };

    const payloads = {
      '/api/runs': runsPayload,
      '/api/run': createRunPayload(historicalRun.runId, historicalRun.runLabel, historicalRun.timestamp),
      '/api/fleet': {
        runId: latestRun.runId,
        runLabel: latestRun.runLabel,
        lastRunTimestamp: latestRun.timestamp,
        topProblem: { title: 'Test', detail: 'Test problem' },
        fleetStatus: { ratingCounts: [], degradedClusters: [] },
        clusters: [],
        proposalSummary: { pending: 0, total: 0, statusCounts: [] },
      },
      '/api/proposals': { proposals: [], statusSummary: [] },
      '/api/notifications': { notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 },
    };

    setupFetchMock(fetchMock, payloads);
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole('heading', { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll('.run-row');
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Navigate to page 2 and select run-95
    const nextButton = await screen.findByRole('button', { name: /runs next page/i });
    await act(async () => {
      await user.click(nextButton);
    });

    await waitFor(() => {
      const pageIndicator = document.querySelector('.pagination-page-indicator');
      expect(pageIndicator?.textContent).toContain('2');
    });

    await act(async () => {
      const historicalRow = document.querySelector('.run-row[data-run-id=\"run-95\"]');
      expect(historicalRow).toBeInTheDocument();
      await user.click(historicalRow!);
    });

    expect(screen.getByRole('button', { name: /← Latest/i })).toBeInTheDocument();

    // Simulate auto-refresh with new runs
    payloads['/api/runs'] = newRunsPayload;

    const refreshButton = await screen.findByRole('button', { name: /refresh/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    // Wait for effect to settle - the effect fires after filteredRunsList changes
    // and navigates to the page containing run-95 (now at index 7, page 3)
    await waitFor(() => {
      const row = document.querySelector('.run-row[data-run-id=\"run-95\"]');
      expect(row).toBeInTheDocument();
    });

    // ASSERTION: run-95 is still visible
    const selectedRowAfterRefresh = document.querySelector('.run-row[data-run-id=\"run-95\"]');
    expect(selectedRowAfterRefresh).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // REGRESSION: ← Latest button still works
  // ---------------------------------------------------------------------------
  test('← Latest button still navigates to page 1 and selects latest run', async () => {
    const runsPayload = createMultiPageRunsList();
    const latestRun = runsPayload.runs[0];
    const historicalRun = runsPayload.runs[5];

    const payloads = {
      '/api/runs': runsPayload,
      '/api/run': createRunPayload(historicalRun.runId, historicalRun.runLabel, historicalRun.timestamp),
      '/api/fleet': {
        runId: latestRun.runId,
        runLabel: latestRun.runLabel,
        lastRunTimestamp: latestRun.timestamp,
        topProblem: { title: 'Test', detail: 'Test problem' },
        fleetStatus: { ratingCounts: [], degradedClusters: [] },
        clusters: [],
        proposalSummary: { pending: 0, total: 0, statusCounts: [] },
      },
      '/api/proposals': { proposals: [], statusSummary: [] },
      '/api/notifications': { notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 },
    };

    setupFetchMock(fetchMock, payloads);
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole('heading', { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll('.run-row');
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Navigate to page 2
    const nextButton = await screen.findByRole('button', { name: /runs next page/i });
    await act(async () => {
      await user.click(nextButton);
    });

    await waitFor(() => {
      const pageIndicator = document.querySelector('.pagination-page-indicator');
      expect(pageIndicator?.textContent).toContain('2');
    });

    // Select historical run
    await act(async () => {
      const historicalRow = document.querySelector('.run-row[data-run-id=\"run-95\"]');
      await user.click(historicalRow!);
    });

    // Click ← Latest
    const latestButton = await screen.findByRole('button', { name: /← Latest/i });
    payloads['/api/run'] = createRunPayload(latestRun.runId, latestRun.runLabel, latestRun.timestamp);

    await act(async () => {
      await user.click(latestButton);
    });

    // ASSERTION: Page 1 is shown
    await waitFor(() => {
      const pageIndicator = document.querySelector('.pagination-page-indicator');
      expect(pageIndicator?.textContent).toContain('1');
    });

    // ASSERTION: Latest run row is selected
    const latestRowSelected = document.querySelector('.run-row[data-run-id=\"run-100\"].run-row-selected');
    expect(latestRowSelected).toBeInTheDocument();

    // ASSERTION: ← Latest button is gone
    expect(screen.queryByRole('button', { name: /← Latest/i })).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // REGRESSION: Filter changes the displayed runs
  // ---------------------------------------------------------------------------
  test('filter change shows only matching runs', async () => {
    const runsPayload = createMultiPageRunsList();
    const latestRun = runsPayload.runs[0];

    const payloads = {
      '/api/runs': runsPayload,
      '/api/run': createRunPayload(latestRun.runId, latestRun.runLabel, latestRun.timestamp),
      '/api/fleet': {
        runId: latestRun.runId,
        runLabel: latestRun.runLabel,
        lastRunTimestamp: latestRun.timestamp,
        topProblem: { title: 'Test', detail: 'Test problem' },
        fleetStatus: { ratingCounts: [], degradedClusters: [] },
        clusters: [],
        proposalSummary: { pending: 0, total: 0, statusCounts: [] },
      },
      '/api/proposals': { proposals: [], statusSummary: [] },
      '/api/notifications': { notifications: [], total: 0, page: 1, limit: 50, total_pages: 1 },
    };

    setupFetchMock(fetchMock, payloads);
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole('heading', { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll('.run-row');
      expect(runRows.length).toBeGreaterThan(0);
    });

    // Click Awaiting review filter
    const filterButton = await screen.findByRole('button', { name: /Awaiting review/i });
    await act(async () => {
      await user.click(filterButton);
    });

    // ASSERTION: After filter, only 5 unreviewed runs are shown (from 8 total)
    await waitFor(() => {
      const runRows = document.querySelectorAll('.run-row');
      expect(runRows.length).toBe(5);
    });

    // ASSERTION: Active filter button should be visually marked
    const activeFilterButton = await screen.findByRole('button', { name: /Awaiting review/i });
    expect(activeFilterButton).toHaveClass('active');
  });
});

// =============================================================================
// De-scoped scenarios (for future enhancement)
// =============================================================================
//
// Timer-driven auto-refresh test:
// - Requires vi.useFakeTimers() in beforeEach
// - Enable auto-refresh via UI, then vi.advanceTimersByTime(5000)
// - Verify the selected run is still visible after the timer fires
//
// Selected run filtered out test:
// - Select a run, then apply a filter that excludes that run
// - Verify the row is not visible but selection state is preserved
// - The ← Latest button should still appear
//
// Missing selected run test:
// - Select a run, then refresh with that run removed from the dataset
// - Verify the row is not visible but selection state is preserved
// - Consider adding a UI notice about the missing run
//
// Page size change test:
// - Select a run, then change the page size
// - Verify the selected run is still visible (page recalculated)
// =============================================================================