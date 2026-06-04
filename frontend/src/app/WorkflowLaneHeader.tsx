/**
 * WorkflowLaneHeader Component
 *
 * Workflow lane header for grouping related sections.
 * Extracted from App.tsx to reduce component size.
 */

import { WORKFLOW_LANES } from "../utils/selectors";

export type WorkflowLaneType = "diagnose" | "improve";

export interface WorkflowLaneHeaderProps {
  type: WorkflowLaneType;
}

export function WorkflowLaneHeader({ type }: WorkflowLaneHeaderProps) {
  const lane = WORKFLOW_LANES[type];
  const icon = type === "diagnose" ? "🔍" : "📈";

  return (
    <div className="workflow-lane-header">
      <div className="workflow-lane-label">
        <span className="workflow-lane-icon">{icon}</span>
        <span className="workflow-lane-title">{lane.label}</span>
      </div>
      <p className="workflow-lane-description muted small">{lane.description}</p>
    </div>
  );
}