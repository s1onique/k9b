/**
 * clusterNextCheckPlanViewModel.ts
 *
 * Pure derivation helpers for ClusterNextCheckPlanSection.
 * Deterministic transformations - no React hooks.
 */

import type {
  NextCheckPlanCandidate,
  NextCheckStatusVariant,
} from "./ClusterNextCheckPlanTypes";
import { nextCheckStatusLabel, approvalStatusLabels } from "./clusterNextCheckPlanFormatters";

// =============================================================================
// Status variant determination
// =============================================================================

export function determineNextCheckStatusVariant(
  candidate: NextCheckPlanCandidate
): NextCheckStatusVariant {
  if (candidate.duplicateOfExistingEvidence) {
    return "duplicate";
  }
  if (candidate.requiresOperatorApproval) {
    if (candidate.approvalStatus === "approved") {
      return "approved";
    }
    if (candidate.approvalStatus === "approval-stale") {
      return "stale";
    }
    return "approval";
  }
  return "safe";
}

export function getPlanStatusLabel(
  variant: NextCheckStatusVariant,
  candidate: NextCheckPlanCandidate
): string {
  if (candidate.approvalStatus) {
    const override = approvalStatusLabels[candidate.approvalStatus];
    if (override) {
      return override;
    }
  }
  return nextCheckStatusLabel(variant);
}

// =============================================================================
// Rationale entries extraction
// =============================================================================

export type RationaleEntry = {
  label: string;
  value: string | null | undefined;
};

export function buildRationaleEntries(candidate: NextCheckPlanCandidate): RationaleEntry[] {
  return [
    { label: "Normalization", value: candidate.normalizationReason },
    { label: "Safety", value: candidate.safetyReason },
    { label: "Approval", value: candidate.approvalReason },
    { label: "Duplicate", value: candidate.duplicateReason },
    { label: "Block", value: candidate.blockingReason },
  ].filter((entry) => entry.value);
}

// =============================================================================
// Card display state
// =============================================================================

export type PlanCardDisplayState = {
  variant: NextCheckStatusVariant;
  statusLabel: string;
  statusClassName: string;
  displayPriority: string;
  priorityIndicatorClass: string;
  targetLabel: string;
  hasRationaleEntries: boolean;
  rationaleEntries: RationaleEntry[];
  hasAlertmanagerProvenance: boolean;
  hasApprovalArtifactLink: boolean;
  approvalArtifactLink: string | null;
  executionBlockingReason: string | null;
};

export function buildCardDisplayState(
  candidate: NextCheckPlanCandidate,
  variant: NextCheckStatusVariant,
  statusLabel: string,
  displayPriority: string,
  priorityIndicatorClass: string,
  targetLabel: string,
  rationaleEntries: RationaleEntry[],
  approvalArtifactLink: string | null,
  executionBlockingReason: string | null
): PlanCardDisplayState {
  return {
    variant,
    statusLabel,
    statusClassName: `plan-status-pill plan-status-pill-${variant}`,
    displayPriority,
    priorityIndicatorClass,
    targetLabel,
    hasRationaleEntries: rationaleEntries.length > 0,
    rationaleEntries,
    hasAlertmanagerProvenance: !!candidate.alertmanagerProvenance,
    hasApprovalArtifactLink: !!approvalArtifactLink,
    approvalArtifactLink,
    executionBlockingReason,
  };
}

// =============================================================================
// Execution state helpers
// =============================================================================

export function hasRenderablePlan(planCandidates: NextCheckPlanCandidate[]): boolean {
  return planCandidates.length > 0;
}

export function hasOrphanedApprovals(orphanedApprovals: { length: number }): boolean {
  return orphanedApprovals.length > 0;
}

// =============================================================================
// Alertmanager provenance display
// =============================================================================

export function formatAlertmanagerTooltip(
  prov: NonNullable<NextCheckPlanCandidate["alertmanagerProvenance"]>
): string {
  const parts: string[] = [];
  if (prov.baseBonus !== prov.appliedBonus) {
    parts.push(`Base bonus: ${prov.baseBonus}, Applied: ${prov.appliedBonus}`);
  } else if (prov.appliedBonus > 0) {
    parts.push(`Bonus: ${prov.appliedBonus}`);
  }
  if (Object.keys(prov.severitySummary).length > 0) {
    const sevParts = Object.entries(prov.severitySummary)
      .map(([sev, count]) => `${sev}: ${count}`)
      .join(", ");
    parts.push(`Severity: ${sevParts}`);
  }
  if (prov.signalStatus) {
    parts.push(`Signal: ${prov.signalStatus}`);
  }
  return parts.length > 0 ? parts.join(" · ") : "Ranking influenced by Alertmanager snapshot";
}

export function formatAlertmanagerBadgeLabel(
  prov: NonNullable<NextCheckPlanCandidate["alertmanagerProvenance"]>
): string {
  if (prov.matchedDimensions.length === 0) {
    return "Promoted by Alertmanager";
  }
  const parts = prov.matchedDimensions.map((dim) => {
    const values = prov.matchedValues[dim] ?? [];
    const valuesStr = values.length > 0 ? `: ${values.join(", ")}` : "";
    return `${dim}${valuesStr}`;
  });
  const bonusStr = prov.appliedBonus > 0 ? ` (+${prov.appliedBonus})` : "";
  return `Matched ${parts.join(", ")}${bonusStr}`;
}
