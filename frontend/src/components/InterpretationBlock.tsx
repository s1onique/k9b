/**
 * Interpretation Block Component
 *
 * Renders a compact follow-up block with badge, optional summary, and optional next-step guidance.
 * Used for both failure and result interpretation displays.
 */

import React from "react";

export interface InterpretationBlockProps {
  /** Text to display on the badge */
  badgeLabel: string;
  /** Optional CSS class for the badge */
  badgeClass?: string;
  /** Optional summary text below the badge */
  summary?: string | null;
  /** Optional recommended next operator action */
  suggestedNextOperatorMove?: string | null;
}

export const InterpretationBlock: React.FC<InterpretationBlockProps> = ({
  badgeLabel,
  badgeClass,
  summary,
  suggestedNextOperatorMove,
}) => (
  <div className="follow-up-block">
    <span className={`follow-up-badge ${badgeClass ?? ""}`.trim()}>{badgeLabel}</span>
    {summary ? <p className="follow-up-summary">{summary}</p> : null}
    {suggestedNextOperatorMove ? (
      <p className="follow-up-action">
        <strong>Next step:</strong> {suggestedNextOperatorMove}
      </p>
    ) : null}
  </div>
);

export default InterpretationBlock;