/**
 * Demo Shell Finding Input Builder
 *
 * Extracts finding selection input derivation from App.tsx.
 * Maps run, incident report, and worklist data to DemoShell input format.
 *
 * This is a pure function - no React hooks required.
 */

import type { SeverityLevel } from "../components/demo-shell/DemoShellTypes";

/** Input arguments for building DemoShell finding input */
export interface BuildDemoShellFindingInputArgs {
  /** Selected run payload */
  run: {
    incidentReport?: {
      status?: "critical" | "degraded" | "warning" | "healthy";
      topFinding?: {
        affectedResource?: string;
        findingType?: string;
      };
    };
    operatorWorklist?: unknown;
    timestamp?: string;
  } | null;
  /** Selected run ID */
  selectedRunId: string | null;
  /** Selected cluster label */
  selectedClusterLabel: string | null;
  /** Run age in minutes (already computed in App.tsx) */
  runAgeMinutes: number;
  /** Whether run is fresh (already computed in App.tsx) */
  runFresh: boolean;
}

/** Output shape matching DemoShellProps['findingSelectionInput'] */
export interface DemoShellFindingInput {
  incidentReport?: {
    status?: "critical" | "degraded" | "warning" | "healthy";
    severity?: SeverityLevel;
    resource?: string;
    findingType?: string;
  };
  operatorWorklist?: Array<{
    severity?: SeverityLevel;
    resource?: string;
    status?: string;
    message?: string;
  }>;
  freshness?: {
    age?: number;
    isStale?: boolean;
  };
  runId?: string;
  clusterLabel?: string;
}

/**
 * Build finding selection input for DemoShell.
 *
 * Preserves exact field names, nullability, fallback strings,
 * and ordering from the original App.tsx derivation.
 */
export function buildDemoShellFindingInput(
  args: BuildDemoShellFindingInputArgs,
): DemoShellFindingInput | undefined {
  const { run, selectedRunId, selectedClusterLabel, runAgeMinutes, runFresh } = args;

  if (!run) {
    return undefined;
  }

  // Extract incident report status from run data
  const incidentReport = run.incidentReport
    ? {
        status: run.incidentReport.status as "critical" | "degraded" | "warning" | "healthy" | undefined,
        resource: run.incidentReport.topFinding?.affectedResource,
        findingType: run.incidentReport.topFinding?.findingType,
      }
    : undefined;

  // Extract operator worklist items
  // NOTE: run.operatorWorklist is OperatorWorklistPayload (object with items array), NOT a direct array.
  // Guard against non-array shapes to prevent TypeError at runtime.
  const worklistPayload = run.operatorWorklist;
  const worklistItems = Array.isArray(worklistPayload)
    ? worklistPayload
    : Array.isArray(worklistPayload?.items)
      ? worklistPayload.items
      : Array.isArray(worklistPayload?.candidates)
        ? worklistPayload.candidates
        : [];

  const operatorWorklist = worklistItems.length > 0
    ? worklistItems.map((item: { severity?: string; resource?: string; status?: string; message?: string }) => ({
        severity: item.severity as SeverityLevel | undefined,
        resource: item.resource,
        status: item.status,
        message: item.message,
      }))
    : undefined;

  // Extract run freshness
  const freshness = {
    age: runAgeMinutes * 60, // Convert to seconds
    isStale: !runFresh,
  };

  return {
    incidentReport,
    operatorWorklist,
    freshness,
    runId: selectedRunId ?? undefined,
    clusterLabel: selectedClusterLabel ?? undefined,
  };
}
