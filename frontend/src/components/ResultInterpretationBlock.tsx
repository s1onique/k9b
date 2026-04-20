/**
 * Result Interpretation Block Component
 *
 * Renders a result interpretation with human-readable class label.
 * Delegates to InterpretationBlock for display.
 */

import React from "react";
import { InterpretationBlock } from "./InterpretationBlock";

export interface ResultInterpretationBlockProps {
  resultClass?: string | null;
  resultSummary?: string | null;
  suggestedNextOperatorMove?: string | null;
}

// Human-readable labels for result classes
const RESULT_FOLLOW_UP_LABELS: Record<string, string> = {
  "useful-signal": "Useful signal",
  "empty-result": "Empty result",
  "noisy-result": "Noisy result",
  "inconclusive": "Inconclusive",
  "partial-result": "Partial output",
};

export const ResultInterpretationBlock: React.FC<ResultInterpretationBlockProps> = ({
  resultClass,
  resultSummary,
  suggestedNextOperatorMove,
}) => {
  if (!resultClass) {
    return null;
  }
  const badgeLabel = RESULT_FOLLOW_UP_LABELS[resultClass] ?? resultClass;
  return (
    <InterpretationBlock
      badgeLabel={badgeLabel}
      badgeClass={`follow-up-badge-${resultClass}`}
      summary={resultSummary}
      suggestedNextOperatorMove={suggestedNextOperatorMove}
    />
  );
};

export default ResultInterpretationBlock;