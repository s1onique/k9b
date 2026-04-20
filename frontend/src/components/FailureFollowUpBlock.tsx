/**
 * Failure Follow-Up Block Component
 *
 * Renders a failure interpretation with human-readable class label.
 * Delegates to InterpretationBlock for display.
 */

import React from "react";
import { InterpretationBlock } from "./InterpretationBlock";

export interface FailureFollowUpProps {
  failureClass?: string | null;
  failureSummary?: string | null;
  suggestedNextOperatorMove?: string | null;
}

// Human-readable labels for failure classes
const FAILURE_FOLLOW_UP_LABELS: Record<string, string> = {
  "timed-out": "Timed out",
  "command-unavailable": "Command unavailable",
  "context-unavailable": "Context unavailable",
  "command-failed": "Command failed",
  "blocked-by-gating": "Blocked",
  "approval-missing-or-stale": "Approval needed",
  "unknown-failure": "Action needed",
};

export const FailureFollowUpBlock: React.FC<FailureFollowUpProps> = ({
  failureClass,
  failureSummary,
  suggestedNextOperatorMove,
}) => {
  if (!failureClass) {
    return null;
  }
  const badgeLabel = FAILURE_FOLLOW_UP_LABELS[failureClass] ?? failureClass;
  return (
    <InterpretationBlock
      badgeLabel={badgeLabel}
      badgeClass={`follow-up-badge-${failureClass}`}
      summary={failureSummary}
      suggestedNextOperatorMove={suggestedNextOperatorMove}
    />
  );
};

export default FailureFollowUpBlock;