import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import React from "react";

import App from "../App";
import {
  sampleRun,
  sampleFleet,
  sampleProposals,
  sampleRunsList,
  sampleClusterDetail,
  makeRunWithOverrides,
} from "./fixtures";

import type { NextCheckExecutionHistoryEntry, RunPayload } from "../types";

// Create localStorage mock
const createStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
};

let storageMock: ReturnType<typeof createStorageMock>;

// Create a mock fetch that returns our test data
const createFetchMock = (runPayload: RunPayload = sampleRun) => {
  const mockFetch = vi.fn().mockImplementation((url: string | Request) => {
    const urlStr = typeof url === "string" ? url : url.url;
    // Check /api/runs FIRST to avoid /api/run matching /api/runs
    if (urlStr.includes("/api/runs")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(sampleRunsList),
      });
    }
    if (urlStr.includes("/api/run")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(runPayload),
      });
    }
    if (urlStr.includes("/api/fleet")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(sampleFleet),
      });
    }
    if (urlStr.includes("/api/proposals")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(sampleProposals),
      });
    }
    if (urlStr.includes("/api/cluster-detail")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(sampleClusterDetail),
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({}),
    });
  });
  return mockFetch;
};

// Helper to build a run with specific execution history entries
const buildRunWithHistory = (entries: NextCheckExecutionHistoryEntry[]): RunPayload => {
  return makeRunWithOverrides({
    nextCheckExecutionHistory: entries,
    nextCheckQueue: [],
  });
};

// ============================================================
// Real Rendered UI Tests for Execution History Usefulness
// ============================================================

describe("Execution History Usefulness Rendering - Real UI", () => {
  beforeEach(() => {
    vi.stubGlobal("setInterval", vi.fn(() => 123));
    vi.stubGlobal("clearInterval", vi.fn());
    storageMock = createStorageMock();
    vi.stubGlobal("localStorage", storageMock);
    vi.stubGlobal("fetch", createFetchMock(sampleRun));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("usefulness badge renders in real UI", () => {
    it("renders usefulness badge when usefulnessClass is 'useful'", async () => {
      const runWithUseful = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Check pod status",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 100,
          artifactPath: "/artifacts/useful-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 2048,
          usefulnessClass: "useful",
          usefulnessSummary: "Found the issue",
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithUseful));
      render(<App />);

      // Wait for the app to load
      await screen.findByText("Check pod status");

      // The usefulness badge should be rendered
      const usefulBadge = screen.getByText("useful");
      expect(usefulBadge).toBeInTheDocument();
      expect(usefulBadge.className).toContain("usefulness-badge-useful");
    });

    it("renders usefulness badge when usefulnessClass is 'partial'", async () => {
      const runWithPartial = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Get deployment status",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 80,
          artifactPath: "/artifacts/partial-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 1024,
          usefulnessClass: "partial",
          usefulnessSummary: "Partially useful - some metrics missing",
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithPartial));
      render(<App />);

      await screen.findByText("Get deployment status");

      const partialBadge = screen.getByText("partial");
      expect(partialBadge).toBeInTheDocument();
      expect(partialBadge.className).toContain("usefulness-badge-partial");
    });

    it("renders usefulness badge when usefulnessClass is 'noisy'", async () => {
      const runWithNoisy = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Get verbose logs",
          commandFamily: "kubectl-logs",
          status: "success",
          durationMs: 200,
          artifactPath: "/artifacts/noisy-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 50000,
          usefulnessClass: "noisy",
          usefulnessSummary: "Too much noise in output",
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithNoisy));
      render(<App />);

      await screen.findByText("Get verbose logs");

      const noisyBadge = screen.getByText("noisy");
      expect(noisyBadge).toBeInTheDocument();
      expect(noisyBadge.className).toContain("usefulness-badge-noisy");
    });

    it("renders usefulness badge when usefulnessClass is 'empty'", async () => {
      const runWithEmpty = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Get events for namespace",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 50,
          artifactPath: "/artifacts/empty-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 100,
          usefulnessClass: "empty",
          usefulnessSummary: "No events found",
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithEmpty));
      render(<App />);

      await screen.findByText("Get events for namespace");

      const emptyBadge = screen.getByText("empty");
      expect(emptyBadge).toBeInTheDocument();
      expect(emptyBadge.className).toContain("usefulness-badge-empty");
    });
  });

  describe("unreviewed indicator renders in real UI", () => {
    it("shows 'Not reviewed' when usefulnessClass is null", async () => {
      const runWithUnreviewed = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Check node status",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 90,
          artifactPath: "/artifacts/unreviewed-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 1500,
          usefulnessClass: null,
          usefulnessSummary: null,
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithUnreviewed));
      render(<App />);

      await screen.findByText("Check node status");

      const unreviewed = screen.getByText("Not reviewed");
      expect(unreviewed).toBeInTheDocument();
      
      // Verify the parent has the unreviewed class
      const indicator = unreviewed.closest(".usefulness-indicator");
      expect(indicator).toBeInTheDocument();
      expect(indicator?.className).toContain("unreviewed");
    });
  });

  describe("resultSummary renders in real UI", () => {
    it("renders resultSummary when present", async () => {
      const runWithResultSummary = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Collect deployment info",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 110,
          artifactPath: "/artifacts/result-summary-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 3000,
          resultClass: "useful-signal",
          resultSummary: "Found critical deployment issue",
          usefulnessClass: "useful",
          usefulnessSummary: "Good signal",
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithResultSummary));
      render(<App />);

      await screen.findByText("Collect deployment info");

      // The result summary should be visible
      expect(screen.getByText("Found critical deployment issue")).toBeInTheDocument();
    });

    it("omits resultSummary gracefully when absent", async () => {
      const runWithoutResultSummary = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Quick health check",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 50,
          artifactPath: "/artifacts/no-summary-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 500,
          usefulnessClass: "useful",
          usefulnessSummary: null,
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithoutResultSummary));
      render(<App />);

      await screen.findByText("Quick health check");

      // The card should still render without crashing
      expect(screen.getByText("Quick health check")).toBeInTheDocument();
    });
  });

  describe("usefulnessSummary renders in real UI", () => {
    it("renders usefulnessSummary when present", async () => {
      const runWithSummary = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Describe service",
          commandFamily: "kubectl-describe",
          status: "success",
          durationMs: 100,
          artifactPath: "/artifacts/summary-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 2000,
          usefulnessClass: "useful",
          usefulnessSummary: "Service configuration is correct",
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithSummary));
      render(<App />);

      await screen.findByText("Describe service");

      // usefulnessSummary should appear with the badge
      expect(screen.getByText(/Service configuration is correct/)).toBeInTheDocument();
    });

    it("renders badge without usefulnessSummary when summary is null", async () => {
      const runWithoutSummary = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Get pod count",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 60,
          artifactPath: "/artifacts/no-summary-badge-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 200,
          usefulnessClass: "useful",
          usefulnessSummary: null,
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithoutSummary));
      render(<App />);

      await screen.findByText("Get pod count");

      // Badge should still show, just without the summary text
      const badge = screen.getByText("useful");
      expect(badge).toBeInTheDocument();
    });
  });

  describe("timeout/failure combinations in real UI", () => {
    it("renders timeout entry with unreviewed state", async () => {
      const runWithTimeout = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Get full logs",
          commandFamily: "kubectl-logs",
          status: "failed",
          durationMs: 60000,
          artifactPath: "/artifacts/timeout-check.json",
          timedOut: true,
          stdoutTruncated: true,
          stderrTruncated: false,
          outputBytesCaptured: 10000,
          failureClass: "timed-out",
          failureSummary: "Command timed out after 60 seconds",
          usefulnessClass: null,
          usefulnessSummary: null,
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithTimeout));
      render(<App />);

      await screen.findByText("Get full logs");

      // Should show timeout badge (use getAllByText since "Timed out" may appear multiple times)
      const timeoutBadges = screen.getAllByText("Timed out");
      expect(timeoutBadges.length).toBeGreaterThan(0);
      // Should show unreviewed state
      expect(screen.getByText("Not reviewed")).toBeInTheDocument();
    });

    it("renders failed entry with unreviewed state", async () => {
      const runWithFailure = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Describe CRD",
          commandFamily: "kubectl-describe",
          status: "failed",
          durationMs: 30,
          artifactPath: "/artifacts/failed-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 0,
          failureClass: "command-failed",
          failureSummary: "CRD not found",
          usefulnessClass: null,
          usefulnessSummary: null,
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithFailure));
      render(<App />);

      await screen.findByText("Describe CRD");

      // Should show unreviewed state even with failure
      expect(screen.getByText("Not reviewed")).toBeInTheDocument();
    });

    it("renders successful entry with reviewed usefulness", async () => {
      const runWithSuccess = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Get resource quota",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 70,
          artifactPath: "/artifacts/success-check.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 800,
          resultClass: "useful-signal",
          resultSummary: "Quota information retrieved successfully",
          usefulnessClass: "useful",
          usefulnessSummary: "Good diagnostic signal",
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithSuccess));
      render(<App />);

      await screen.findByText("Get resource quota");

      // Should show the usefulness badge
      expect(screen.getByText("useful")).toBeInTheDocument();
      // Should show the result summary
      expect(screen.getByText("Quota information retrieved successfully")).toBeInTheDocument();
    });
  });

  describe("multiple entries with different states", () => {
    it("renders multiple entries with different usefulness states", async () => {
      const runWithMixed = buildRunWithHistory([
        {
          timestamp: "2024-01-15T10:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Entry with useful",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 100,
          artifactPath: "/artifacts/useful-mixed.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 2000,
          usefulnessClass: "useful",
          usefulnessSummary: "Good result",
        },
        {
          timestamp: "2024-01-15T09:00:00Z",
          clusterLabel: "prod-cluster",
          candidateDescription: "Entry without review",
          commandFamily: "kubectl-get",
          status: "failed",
          durationMs: 50,
          artifactPath: "/artifacts/unreviewed-mixed.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 0,
          failureClass: "command-failed",
          usefulnessClass: null,
          usefulnessSummary: null,
        },
        {
          timestamp: "2024-01-15T08:00:00Z",
          clusterLabel: "staging-cluster",
          candidateDescription: "Entry with partial",
          commandFamily: "kubectl-get",
          status: "success",
          durationMs: 120,
          artifactPath: "/artifacts/partial-mixed.json",
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 1500,
          usefulnessClass: "partial",
          usefulnessSummary: "Some data missing",
        },
      ]);

      vi.stubGlobal("fetch", createFetchMock(runWithMixed));
      render(<App />);

      // All entries should render
      await screen.findByText("Entry with useful");
      await screen.findByText("Entry without review");
      await screen.findByText("Entry with partial");

      // All usefulness badges should appear
      expect(screen.getByText("useful")).toBeInTheDocument();
      expect(screen.getByText("partial")).toBeInTheDocument();
      expect(screen.getByText("Not reviewed")).toBeInTheDocument();
    });
  });

  // ============================================================
  // Real DOM Truncation Tests
  // ============================================================

  describe('DOM truncation for long text in real UI', () => {
    it('truncates long resultSummary text with ellipsis in DOM', async () => {
      // Create a resultSummary longer than 120 characters
      // Using a unique string to avoid false matches
      const longResultText = 'RESULT_LONG_UNIQUE_1234567890123456789012345678901234567890123456789012345678901234567890_EXTRA_CHARS_TO_MAKE_IT_LONG_ENOUGH';
      // Verify the text is longer than 120
      expect(longResultText.length).toBeGreaterThan(120);

      const runWithLongResult = buildRunWithHistory([
        {
          timestamp: '2024-01-15T10:00:00Z',
          clusterLabel: 'prod-cluster',
          candidateDescription: 'Test long result truncation',
          commandFamily: 'kubectl-get',
          status: 'success',
          durationMs: 100,
          artifactPath: '/artifacts/long-result.json',
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 2048,
          resultClass: 'useful-signal',
          resultSummary: longResultText,
          usefulnessClass: 'useful',
          usefulnessSummary: 'Good',
        },
      ]);

      vi.stubGlobal('fetch', createFetchMock(runWithLongResult));
      const { container } = render(<App />);

      await screen.findByText('Test long result truncation');

      // Find the truncated text - it should contain the unique prefix
      const truncatedElements = document.querySelectorAll('.follow-up-summary');
      expect(truncatedElements.length).toBeGreaterThan(0);
      
      // Get the full text content
      const fullText = truncatedElements[0].textContent ?? '';
      console.log('Full text length:', fullText.length);
      console.log('Full text ends with ellipsis:', fullText.endsWith('…'));
      console.log('Full text last 10 chars:', JSON.stringify(fullText.slice(-10)));
      
      // Verify the text is truncated (starts with expected prefix but doesn't have the full original)
      const startsWithPrefix = fullText.startsWith('RESULT_LONG_UNIQUE_123456789012345678901234567890');
      const hasEllipsis = fullText.endsWith('…');
      const isShorterThanOriginal = fullText.length < longResultText.length;
      
      expect(startsWithPrefix).toBe(true);
      expect(hasEllipsis).toBe(true);
      expect(isShorterThanOriginal).toBe(true);

      // Verify full untruncated text is NOT present
      expect(screen.queryByText(longResultText)).not.toBeInTheDocument();
    });

    it('truncates long usefulnessSummary text with ellipsis in DOM', async () => {
      // Create a usefulnessSummary longer than 80 characters
      // The em-dash prefix " — " adds 3 characters to the display
      const longUsefulnessText = 'USE_LONG_UNIQUE_12345678901234567890123456789012345678901234567890_TRUNCAT_EXTRA_SUFFIX_TO_MAKE_IT_LONG';
      // Make sure the original is long enough to exceed 80 + 3 = 83 char limit
      expect(longUsefulnessText.length).toBeGreaterThan(90);

      const runWithLongUsefulness = buildRunWithHistory([
        {
          timestamp: '2024-01-15T10:00:00Z',
          clusterLabel: 'prod-cluster',
          candidateDescription: 'Test long usefulness truncation',
          commandFamily: 'kubectl-get',
          status: 'success',
          durationMs: 100,
          artifactPath: '/artifacts/long-usefulness.json',
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 2048,
          usefulnessClass: 'useful',
          usefulnessSummary: longUsefulnessText,
        },
      ]);

      vi.stubGlobal('fetch', createFetchMock(runWithLongUsefulness));
      render(<App />);

      await screen.findByText('Test long usefulness truncation');

      // Find the usefulness text element - the em-dash prefix is separate from the text content
      const usefulnessElements = document.querySelectorAll('.usefulness-indicator .small');
      expect(usefulnessElements.length).toBeGreaterThan(0);
      
      // Get full text which includes em-dash prefix
      const fullText = usefulnessElements[0].textContent ?? '';
      
      // Verify text is truncated - ends with ellipsis
      expect(fullText.endsWith('…')).toBe(true);
      // The total displayed length (including em-dash prefix) should be less than original
      expect(fullText.length).toBeLessThan(longUsefulnessText.length);
    });

    it('shows both resultSummary and usefulnessSummary truncated in DOM', async () => {
      // Make strings long enough to exceed their limits (120 and 80+ chars respectively)
      const longResultText = 'RESULT_TEXT_THAT_IS_DEFINITELY_OVER_120_CHARACTERS_LONG_AND_SHOULD_BE_TRUNCATED_WHEN_DISPLAYED_IN_THE_EXECUTION_HISTORY_CARD';
      const longUsefulnessText = 'USE_TEXT_THAT_IS_DEFINITELY_OVER_80_CHARACTERS_LONG_AND_SHOULD_BE_TRUNCATED_WHEN_DISPLAYED_EXTRA';
      
      // Verify they're long enough
      expect(longResultText.length).toBeGreaterThan(120);
      expect(longUsefulnessText.length).toBeGreaterThan(90);

      const runWithBothLong = buildRunWithHistory([
        {
          timestamp: '2024-01-15T10:00:00Z',
          clusterLabel: 'prod-cluster',
          candidateDescription: 'Test both long truncation',
          commandFamily: 'kubectl-get',
          status: 'success',
          durationMs: 100,
          artifactPath: '/artifacts/both-long.json',
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 2048,
          resultClass: 'useful-signal',
          resultSummary: longResultText,
          usefulnessClass: 'useful',
          usefulnessSummary: longUsefulnessText,
        },
      ]);

      vi.stubGlobal('fetch', createFetchMock(runWithBothLong));
      render(<App />);

      await screen.findByText('Test both long truncation');

      // Check resultSummary truncation
      const resultElements = document.querySelectorAll('.follow-up-summary');
      expect(resultElements.length).toBeGreaterThan(0);
      const resultFullText = resultElements[0].textContent ?? '';
      expect(resultFullText.length).toBeLessThan(longResultText.length);
      expect(resultFullText.endsWith('…')).toBe(true);

      // Check usefulnessSummary truncation
      const usefulnessElements = document.querySelectorAll('.usefulness-indicator .small');
      expect(usefulnessElements.length).toBeGreaterThan(0);
      const usefulnessFullText = usefulnessElements[0].textContent ?? '';
      expect(usefulnessFullText.length).toBeLessThan(longUsefulnessText.length);
      expect(usefulnessFullText.endsWith('…')).toBe(true);

      // Verify full untruncated texts are NOT present
      expect(screen.queryByText(longResultText)).not.toBeInTheDocument();
      expect(screen.queryByText(longUsefulnessText)).not.toBeInTheDocument();
    });

    it('does not truncate short resultSummary and usefulnessSummary', async () => {
      const shortResult = 'Short result';
      const shortUsefulness = 'Short usefulness';

      const runWithShort = buildRunWithHistory([
        {
          timestamp: '2024-01-15T10:00:00Z',
          clusterLabel: 'prod-cluster',
          candidateDescription: 'Test short text',
          commandFamily: 'kubectl-get',
          status: 'success',
          durationMs: 100,
          artifactPath: '/artifacts/short.json',
          timedOut: false,
          stdoutTruncated: false,
          stderrTruncated: false,
          outputBytesCaptured: 2048,
          resultClass: 'useful-signal',
          resultSummary: shortResult,
          usefulnessClass: 'useful',
          usefulnessSummary: shortUsefulness,
        },
      ]);

      vi.stubGlobal('fetch', createFetchMock(runWithShort));
      render(<App />);

      await screen.findByText('Test short text');

      // Short texts should appear without ellipsis
      const resultElements = document.querySelectorAll('.follow-up-summary');
      const shortResultInDom = Array.from(resultElements).some(el => el.textContent === shortResult);
      expect(shortResultInDom).toBe(true);

      // Check that no ellipsis appears in these short text elements
      const usefulnessElements = document.querySelectorAll('.usefulness-indicator .small');
      const hasEllipsisInShort = Array.from(usefulnessElements).some(el => el.textContent?.includes('…'));
      expect(hasEllipsisInShort).toBe(false);
    });
  });
});
