/**
 * OperatorWorklistCard.tsx
 *
 * Phase 2: Canonical Operator Worklist Surface
 *
 * Renders the operator worklist as a first-class selected-run UI surface.
 * Visual design follows the review bar:
 * - Ranked action items
 * - Command (executable when present, "No executable command yet" when null)
 * - Target cluster/context
 * - Reason and expected evidence
 * - Safety note
 * - Approval/execution/feedback state
 * - Source artifact links
 *
 * Rules enforced:
 * - Null command must not render as an empty code block.
 * - Show "No executable command yet" for null commands.
 * - Empty sourceArtifactRefs do not render broken artifact links.
 * - Empty states are honest: "No operator worklist items are available for this run."
 */

import type { OperatorWorklistPayload, OperatorWorklistItemPayload, ArtifactLinkRef } from "../../types";
import { artifactUrl } from "../../utils";

// ============================================================================
// Props
// ============================================================================

export interface OperatorWorklistCardProps {
  /** The operator worklist payload from the selected run */
  operatorWorklist: OperatorWorklistPayload | null | undefined;
}

// ============================================================================
// Helper subcomponents
// ============================================================================

/** Renders a single artifact link as a clickable link */
const ArtifactLinkItem = ({ artifactRef }: { artifactRef: ArtifactLinkRef }) => {
  if (!artifactRef?.path) {
    // Empty sourceArtifactRefs do not render broken links
    return null;
  }
  const url = artifactUrl(artifactRef.path);
  if (!url) {
    return null;
  }
  return (
    <a
      key={artifactRef.path}
      className="artifact-link worklist-artifact-link"
      href={url}
      target="_blank"
      rel="noreferrer"
      title={artifactRef.path}
    >
      {artifactRef.label}
    </a>
  );
};

/** Renders a single worklist item */
const WorklistItemRow = ({ item }: { item: OperatorWorklistItemPayload }) => {
  return (
    <li className="worklist-item" data-testid={`worklist-item-${item.rank}`}>
      {/* Rank + workstream header */}
      <div className="worklist-item-header">
        <span className="worklist-rank" data-testid={`worklist-rank-${item.rank}`}>#{item.rank}</span>
        {item.workstream && (
          <span className="worklist-workstream worklist-workstream-badge">{item.workstream}</span>
        )}
        <span className="worklist-title">{item.title}</span>
      </div>

      {/* Command section - critical for truthfulness */}
      <div className="worklist-command-section">
        {item.command ? (
          <code className="worklist-command" data-testid={`worklist-command-${item.rank}`}>
            {item.command}
          </code>
        ) : (
          <span className="worklist-no-command muted tiny" data-testid={`worklist-no-command-${item.rank}`}>
            No executable command yet.
          </span>
        )}
      </div>

      {/* Target cluster/context */}
      {(item.targetCluster || item.targetContext) && (
        <div className="worklist-target muted tiny">
          <span className="worklist-target-label">target:</span>
          <span className="worklist-target-value">
            {[item.targetCluster, item.targetContext].filter(Boolean).join(" · ")}
          </span>
        </div>
      )}

      {/* Reason */}
      {item.reason && (
        <div className="worklist-reason muted tiny">
          <span className="worklist-reason-label">why now:</span>
          <span className="worklist-reason-value">{item.reason}</span>
        </div>
      )}

      {/* Expected evidence */}
      {item.expectedEvidence && (
        <div className="worklist-evidence muted tiny">
          <span className="worklist-evidence-label">expected evidence:</span>
          <span className="worklist-evidence-value">{item.expectedEvidence}</span>
        </div>
      )}

      {/* Safety note */}
      {item.safetyNote && (
        <div className="worklist-safety tiny">
          <span className="worklist-safety-label">safety:</span>
          <span className="worklist-safety-value">{item.safetyNote}</span>
        </div>
      )}

      {/* State indicators */}
      <div className="worklist-state-row">
        {item.approvalState && (
          <span className={`worklist-state worklist-approval-state worklist-state-${item.approvalState}`}>
            {item.approvalState}
          </span>
        )}
        {item.executionState && (
          <span className={`worklist-state worklist-execution-state worklist-state-${item.executionState}`}>
            {item.executionState}
          </span>
        )}
        {item.feedbackState && (
          <span className={`worklist-state worklist-feedback-state worklist-state-${item.feedbackState}`}>
            {item.feedbackState}
          </span>
        )}
      </div>

      {/* Source artifact links */}
      {item.sourceArtifactRefs.length > 0 && (
        <div className="worklist-artifacts">
          {item.sourceArtifactRefs.map((artifactRef) => (
            <ArtifactLinkItem key={artifactRef.path} artifactRef={artifactRef} />
          ))}
        </div>
      )}
    </li>
  );
};

/** Summary stats row */
const WorklistSummary = ({
  total,
  completed,
  pending,
  blocked,
}: {
  total: number;
  completed: number;
  pending: number;
  blocked: number;
}) => {
  return (
    <div className="worklist-summary" data-testid="worklist-summary">
      <span className="worklist-stat">
        <strong>{total}</strong> total
      </span>
      {completed > 0 && (
        <span className="worklist-stat worklist-stat-completed">
          <strong>{completed}</strong> done
        </span>
      )}
      {pending > 0 && (
        <span className="worklist-stat worklist-stat-pending">
          <strong>{pending}</strong> pending
        </span>
      )}
      {blocked > 0 && (
        <span className="worklist-stat worklist-stat-blocked">
          <strong>{blocked}</strong> blocked
        </span>
      )}
    </div>
  );
};

// ============================================================================
// Main component
// ============================================================================

export const OperatorWorklistCard = ({ operatorWorklist }: OperatorWorklistCardProps) => {
  // Empty state: honest message when no worklist is available
  if (!operatorWorklist) {
    return (
      <div className="run-overview-card operator-worklist-card" data-testid="operator-worklist-card">
        <div className="preview-card-header">
          <span className="preview-card-icon" aria-hidden="true">▸</span>
          <h3>Operator worklist</h3>
        </div>
        <p className="muted tiny">No operator worklist items are available for this run.</p>
      </div>
    );
  }

  const hasItems = operatorWorklist.items.length > 0;

  return (
    <div className="run-overview-card operator-worklist-card" data-testid="operator-worklist-card">
      {/* Header: icon + title */}
      <div className="preview-card-header">
        <span className="preview-card-icon" aria-hidden="true">▸</span>
        <h3>Operator worklist</h3>
      </div>

      {/* Summary stats */}
      {hasItems && (
        <WorklistSummary
          total={operatorWorklist.totalItems}
          completed={operatorWorklist.completedItems}
          pending={operatorWorklist.pendingItems}
          blocked={operatorWorklist.blockedItems}
        />
      )}

      {/* Worklist items */}
      {hasItems ? (
        <ul className="worklist-items">
          {operatorWorklist.items.map((item) => (
            <WorklistItemRow key={item.id} item={item} />
          ))}
        </ul>
      ) : (
        <p className="muted tiny">No operator worklist items are available for this run.</p>
      )}
    </div>
  );
};
