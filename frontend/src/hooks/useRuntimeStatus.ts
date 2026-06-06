/**
 * useRuntimeStatus.ts - Hook for fetching runtime status data.
 *
 * Manages fetching runtime status (log windows + PVC usage) with
 * loading and error states.
 */

import { useCallback, useEffect, useState } from "react";
import { fetchRuntimeStatus } from "../api";
import type { RuntimeStatusPayload } from "../components/runtime-status/runtimeStatusTypes";

// ============================================================================
// Types
// ============================================================================

export interface UseRuntimeStatusReturn {
  /** Runtime status data */
  runtimeStatus: RuntimeStatusPayload | null;
  /** Whether data is still loading */
  isLoading: boolean;
  /** Whether there was an error fetching data */
  isError: boolean;
  /** Manual refresh function */
  refresh: () => Promise<void>;
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook to fetch runtime status data.
 *
 * Fetches log window counts for backend and scheduler pods,
 * and PVC usage for the backend.
 *
 * Uses no-cache fetch to ensure fresh data on each request.
 */
export function useRuntimeStatus(): UseRuntimeStatusReturn {
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatusPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setIsError(false);

    try {
      const data = await fetchRuntimeStatus();
      setRuntimeStatus(data);
      setIsError(false);
    } catch {
      setIsError(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    runtimeStatus,
    isLoading,
    isError,
    refresh,
  };
}
