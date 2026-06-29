/**
 * clusterNextCheckPlanFormatters.ts
 *
 * Pure formatting helpers for ClusterNextCheckPlanSection.
 * Labels, dates, status text, CSS class mapping - no React hooks.
 */

import type { NextCheckStatusVariant } from "./ClusterNextCheckPlanTypes";

// =============================================================================
// Priority formatting
// =============================================================================

const formatCandidatePriority = (value?: string | null) => {
  const normalized = (value ?? "secondary").toLowerCase();
  return `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}`;
};

export { formatCandidatePriority };

// =============================================================================
// Status label mapping
// =============================================================================

const approvalStatusLabels: Record<string, string> = {
  approved: "Approved candidate",
  "approval-required": "Approval needed",
  "approval-stale": "Approval stale",
  "approval-orphaned": "Orphaned approval",
  "not-required": "Safe candidate",
};

export { approvalStatusLabels };

const nextCheckStatusLabel = (variant: NextCheckStatusVariant) => {
  switch (variant) {
    case "approval":
      return "Approval needed";
    case "approved":
      return "Approved candidate";
    case "duplicate":
      return "Duplicate / already covered";
    case "stale":
      return "Approval stale";
    default:
      return "Safe candidate";
  }
};

export { nextCheckStatusLabel };

// =============================================================================
// Outcome status formatting
// =============================================================================

const outcomeStatusLabels: Record<string, string> = {
  "executed-success": "Executed (success)",
  "executed-failed": "Executed (failed)",
  "timed-out": "Execution timed out",
  "approval-required": "Awaiting approval",
  approved: "Approved",
  "approval-stale": "Approval stale",
  "approval-orphaned": "Orphaned approval",
  "not-used": "Not used",
  pending: "Awaiting approval",
  unknown: "Unknown",
};

export { outcomeStatusLabels };

const outcomeStatusDisplay = (status?: string | null) =>
  outcomeStatusLabels[status ?? "unknown"] || (status ? status : "Unknown");

const outcomeStatusClass = (status?: string | null) =>
  `outcome-pill outcome-pill-${((status ?? "unknown").replace(/[^a-z0-9]+/gi, "-").toLowerCase())}`;

export { outcomeStatusDisplay, outcomeStatusClass };

// =============================================================================
// Humanization helpers
// =============================================================================

const humanizeReason = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
};

export { humanizeReason };

// =============================================================================
// Priority indicator class
// =============================================================================

const priorityIndicatorClass = (priority: string) => `priority-pill priority-pill-${priority}`;

export { priorityIndicatorClass };

// =============================================================================
// Orphaned approval formatting
// =============================================================================

const formatOrphanedApprovalLabel = (approval: {
  candidateDescription: string | null;
  candidateId: string | null;
}) => {
  return approval.candidateDescription || approval.candidateId || "Unknown approval";
};

export { formatOrphanedApprovalLabel };
