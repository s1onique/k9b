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
 * Pagination:
 * - Default page size: 1 item per page
 * - Pagination controls hidden when item count <= page size
 * - Preserves backend item rank (e.g., #1, #2, #3...) not local page index
 * - Shows "Showing X–Y of Z" text
 *
 * Rules enforced:
 * - Null command must not render as an empty code block.
 * - Show "No executable command yet" for null commands.
 * - Empty sourceArtifactRefs do not render broken artifact links.
 * - Empty states are honest: "No operator worklist items are available for this run."
 */

import { useState, useMemo } from "react";
import type { OperatorWorklistPayload, OperatorWorklistItemPayload, ArtifactLinkRef } from "../../types";
import { artifactUrl } from "../../utils";
import Pagination from "../Pagination";
import { CommandText } from "../CommandText";
import { ExpandableText } from "../ExpandableText";

// ============================================================================
// Constants
// ============================================================================

const DEFAULT_PAGE_SIZE = 1;

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

// ============================================================================
// Canonical execution state derivation
// ============================================================================

/** Canonical executed states - any of these means the item has been executed */
const EXECUTED_STATES = new Set([
  "executed-success",
  "executed-failed",
  "timed-out",
  "completed",
]);

/** Canonical item states that indicate execution */
const EXECUTED_ITEM_STATES = new Set(["executed", "reviewed"]);

/**
 * Derive the canonical execution display label for a worklist item.
 * Uses itemState as the authoritative source, with executionState as fallback.
 *
 * Returns the appropriate display text for the execution badge:
 * - "executed / success" for successful execution
 * - "executed / failed" for failed execution
 * - "executed / timed-out" for timed-out execution
 * - "executed" for general executed state
 * - null if not executed
 */
function deriveExecutionLabel(item: OperatorWorklistItemPayload): string | null {
  // Check itemState first (canonical state from backend overlay)
  if (item.itemState && EXECUTED_ITEM_STATES.has(item.itemState)) {
    if (item.executionState === "executed-failed") {
      return "executed / failed";
    } else if (item.executionState === "timed-out") {
      return "executed / timed-out";
    } else if (item.executionState && EXECUTED_STATES.has(item.executionState)) {
      return "executed / success";
    }
    return "executed";
  }

  // Fall back to executionState if itemState is not set
  if (item.executionState && EXECUTED_STATES.has(item.executionState)) {
    if (item.executionState === "executed-failed") {
      return "executed / failed";
    } else if (item.executionState === "timed-out") {
      return "executed / timed-out";
    }
    return "executed / success";
  }

  // Not executed
  return null;
}

/**
 * Check if a worklist item has been executed (has execution artifacts or execution state).
 * This is the canonical predicate for all UI decisions about whether to show
 * "Run candidate" buttons and how to display execution status.
 */
function isItemExecuted(item: OperatorWorklistItemPayload): boolean {
  // Check itemState (canonical state from backend overlay)
  if (item.itemState && EXECUTED_ITEM_STATES.has(item.itemState)) {
    return true;
  }

  // Check executionState
  if (item.executionState && EXECUTED_STATES.has(item.executionState)) {
    return true;
  }

  // Check for execution artifacts (sourceArtifactRefs containing execution artifacts)
  const hasExecutionArtifact = item.sourceArtifactRefs.some((ref) =>
    ref.path?.includes("next-check-execution") || ref.path?.includes("execution")
  );

  return hasExecutionArtifact;
}

/** Renders a single worklist item */
const WorklistItemRow = ({ item }: { item: OperatorWorklistItemPayload }) => {
  // Derive canonical execution state for display
  const executionLabel = deriveExecutionLabel(item);
  const isExecuted = isItemExecuted(item);

  return (
    <li className="worklist-item" data-testid={`worklist-item-${item.rank}`}>
      {/* Rank + workstream header - title uses ExpandableText for truncation */}
      <div className="worklist-item-header">
        <span className="worklist-rank" data-testid={`worklist-rank-${item.rank}`}>#{item.rank}</span>
        {item.workstream && (
          <span className="worklist-workstream worklist-workstream-badge">{item.workstream}</span>
        )}
        <ExpandableText
          text={item.title}
          testId={`worklist-title-${item.rank}`}
          className="worklist-title-expandable"
          popupLabel="Full check text"
        />
      </div>

      {/* Command section - critical for truthfulness */}
      <div className="worklist-command-section">
        {item.command ? (
          <CommandText command={item.command} testId={`worklist-command-${item.rank}`} />
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

      {/* State indicators - use canonical itemState/executionState derivation */}
      <div className="worklist-state-row">
        {item.approvalState && (
          <span className={`worklist-state worklist-approval-state worklist-state-${item.approvalState}`}>
            {item.approvalState}
          </span>
        )}
        {/* Use canonical execution label derived from itemState/executionState */}
        {executionLabel && (
          <span className={`worklist-state worklist-execution-state ${isExecuted ? "worklist-state-executed" : ""}`}>
            {executionLabel}
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
  // CRITICAL: Early return MUST be before all hooks to maintain consistent hook order
  // React throws "Rendered fewer hooks than expected" if hook count differs between renders
  // Guard against null, undefined, and objects without items array (wrong shape)
  if (!operatorWorklist || !Array.isArray(operatorWorklist.items)) {
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

  // Pagination state - local to this component
  const [currentPage, setCurrentPage] = useState(1);

  const totalItems = operatorWorklist.items.length;
  const hasItems = totalItems > 0;

  // Calculate pagination values
  const totalPages = Math.ceil(totalItems / DEFAULT_PAGE_SIZE);

  // Derive safe current page from state - clamp without state update
  // This avoids post-render state updates that cause act() warnings
  const safeCurrentPage = Math.min(Math.max(1, currentPage), Math.max(1, totalPages));

  const showPagination = hasItems && totalItems > DEFAULT_PAGE_SIZE;

  // Get current page items using safeCurrentPage
  const paginatedItems = useMemo(() => {
    const startIndex = (safeCurrentPage - 1) * DEFAULT_PAGE_SIZE;
    return operatorWorklist.items.slice(startIndex, startIndex + DEFAULT_PAGE_SIZE);
  }, [operatorWorklist.items, safeCurrentPage]);

  // Page change handler - clamps before setting state
  const handlePageChange = (page: number) => {
    const clampedPage = Math.min(Math.max(1, page), Math.max(1, totalPages));
    setCurrentPage(clampedPage);
  };

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
        <>
          <ul className="worklist-items">
            {paginatedItems.map((item) => (
              <WorklistItemRow key={item.id ?? item.rank} item={item} />
            ))}
          </ul>

          {/* Pagination controls */}
          {showPagination && (
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalItems={totalItems}
              pageSize={DEFAULT_PAGE_SIZE}
              onPageChange={handlePageChange}
              label="Worklist"
            />
          )}
        </>
      ) : (
        <p className="muted tiny">No operator worklist items are available for this run.</p>
      )}
    </div>
  );
};
