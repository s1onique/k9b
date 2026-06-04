/**
 * AppDemoShellOverlay Component
 *
 * Demo shell overlay for K8s Accelerator walkthrough.
 * Extracted from App.tsx to reduce component size.
 */

import { DemoShell } from "../components/DemoShell";
import type { DemoShellRealContext } from "../components/DemoShell";

export interface AppDemoShellOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  findingSelectionInput?: {
    incidentReport?: {
      status?: "critical" | "degraded" | "warning" | "healthy";
      severity?: string;
      resource?: string;
      findingType?: string;
    };
    operatorWorklist?: Array<{
      severity?: string;
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
  };
  realContext?: {
    runId: string;
    clusterLabel?: string;
    isFresh: boolean;
    runCapturedAt?: string;
  } | null;
}

export function AppDemoShellOverlay({
  isOpen,
  onClose,
  findingSelectionInput,
  realContext,
}: AppDemoShellOverlayProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <DemoShell
      onClose={onClose}
      findingSelectionInput={findingSelectionInput}
      realContext={realContext}
    />
  );
}