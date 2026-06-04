import { useCallback, useEffect, useRef } from "react";

import type { NextCheckExecutionHistoryEntry, NextCheckQueueItem } from "../types";
import { buildExecutionEntryKey } from "../components/ExecutionHistoryPanel";

const NAVIGATION_HIGHLIGHT_DURATION_MS = 2200;

export interface UseAppNavigationHighlightsArgs {
  /** Set the highlighted cluster label */
  setHighlightedClusterLabel: (label: string | null) => void;
  /** Set the highlighted execution history key */
  setExecutionHistoryHighlightKey: (key: string | null) => void;
  /** Set the highlighted queue card key */
  setQueueHighlightKey: (key: string | null) => void;
  /** Select and focus a cluster with optional expansion */
  onClusterSelect: (clusterLabel: string, options?: { expand?: boolean }) => void;
  /** Find matching execution history entry for a queue candidate */
  findExecutionHistoryEntry: (candidate: NextCheckQueueItem) => NextCheckExecutionHistoryEntry | null;
  /** Get available discovery clusters for fallback selection */
  getDiscoveryClusters: () => string[];
  /** Get the currently selected cluster label */
  getSelectedClusterLabel: () => string | null;
}

export interface AppNavigationHighlights {
  /** Smooth scroll to a section by its DOM ID */
  scrollToSection: (sectionId: string) => void;
  /** Flash a cluster row and auto-clear after NAVIGATION_HIGHLIGHT_DURATION_MS */
  highlightCluster: (clusterLabel: string | null) => void;
  /** Flash an execution entry and auto-clear after NAVIGATION_HIGHLIGHT_DURATION_MS */
  highlightExecutionEntry: (executionKey: string | null) => void;
  /** Flash a queue card, scroll into view, and auto-clear */
  highlightQueueCard: (queueKey: string | null) => void;
  /** Navigate back to the queue section */
  handleBackToQueue: () => void;
  /** Jump from a queue candidate to its cluster detail */
  handleQueueClusterJump: (candidate: NextCheckQueueItem) => void;
  /** Jump from a queue candidate to its execution history entry */
  handleQueueExecutionJump: (candidate: NextCheckQueueItem) => void;
}

export function useAppNavigationHighlights(
  args: UseAppNavigationHighlightsArgs,
): AppNavigationHighlights {
  const {
    setHighlightedClusterLabel,
    setExecutionHistoryHighlightKey,
    setQueueHighlightKey,
    onClusterSelect,
    findExecutionHistoryEntry,
    getDiscoveryClusters,
    getSelectedClusterLabel,
  } = args;

  const clusterHighlightTimer = useRef<number | null>(null);
  const executionHighlightTimer = useRef<number | null>(null);
  const queueHighlightTimer = useRef<number | null>(null);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (clusterHighlightTimer.current) window.clearTimeout(clusterHighlightTimer.current);
      if (executionHighlightTimer.current) window.clearTimeout(executionHighlightTimer.current);
      if (queueHighlightTimer.current) window.clearTimeout(queueHighlightTimer.current);
    };
  }, []);

  const scrollToSection = useCallback((sectionId: string) => {
    if (typeof document === "undefined") {
      return;
    }
    const section = document.getElementById(sectionId);
    if (!section) {
      return;
    }
    section.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, []);

  const highlightCluster = useCallback((clusterLabel: string | null) => {
    setHighlightedClusterLabel(clusterLabel);
    if (clusterHighlightTimer.current) {
      window.clearTimeout(clusterHighlightTimer.current);
    }
    if (!clusterLabel) {
      return;
    }
    clusterHighlightTimer.current = window.setTimeout(() => {
      setHighlightedClusterLabel(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
  }, [setHighlightedClusterLabel]);

  const highlightExecutionEntry = useCallback((executionKey: string | null) => {
    setExecutionHistoryHighlightKey(executionKey);
    if (executionHighlightTimer.current) {
      window.clearTimeout(executionHighlightTimer.current);
    }
    if (!executionKey) {
      return;
    }
    executionHighlightTimer.current = window.setTimeout(() => {
      setExecutionHistoryHighlightKey(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
  }, [setExecutionHistoryHighlightKey]);

  const highlightQueueCard = useCallback((queueKey: string | null) => {
    setQueueHighlightKey(queueKey);
    if (queueHighlightTimer.current) {
      window.clearTimeout(queueHighlightTimer.current);
    }
    if (!queueKey) {
      return;
    }
    queueHighlightTimer.current = window.setTimeout(() => {
      setQueueHighlightKey(null);
    }, NAVIGATION_HIGHLIGHT_DURATION_MS);
    // Scroll the highlighted queue card into view
    requestAnimationFrame(() => {
      const element = document.querySelector(`[data-queue-key="${CSS.escape(queueKey)}"]`);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }, [setQueueHighlightKey]);

  const handleBackToQueue = useCallback(() => {
    scrollToSection("next-check-queue");
  }, [scrollToSection]);

  const handleQueueClusterJump = useCallback(
    (candidate: NextCheckQueueItem) => {
      // Fallback chain: candidate target -> discovery clusters -> selected
      const target =
        candidate.targetCluster ||
        getDiscoveryClusters()[0] ||
        getSelectedClusterLabel() ||
        null;
      if (!target) {
        return;
      }
      onClusterSelect(target, { expand: true });
      highlightCluster(target);
      scrollToSection("cluster");
    },
    [onClusterSelect, highlightCluster, scrollToSection, getDiscoveryClusters, getSelectedClusterLabel],
  );

  const handleQueueExecutionJump = useCallback(
    (candidate: NextCheckQueueItem) => {
      const entry = findExecutionHistoryEntry(candidate);
      highlightExecutionEntry(entry ? buildExecutionEntryKey(entry) : null);
      scrollToSection("execution-history");
    },
    [findExecutionHistoryEntry, highlightExecutionEntry, scrollToSection],
  );

  return {
    scrollToSection,
    highlightCluster,
    highlightExecutionEntry,
    highlightQueueCard,
    handleBackToQueue,
    handleQueueClusterJump,
    handleQueueExecutionJump,
  };
}