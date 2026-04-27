/**
 * ReviewEnrichmentPanel component and related advisory utilities.
 *
 * Provides:
 * - ReviewEnrichmentPanel: Main panel displaying provider-assisted advisory content
 * - AdvisoryExecutiveSummary: Compact scan-friendly overview metrics strip
 * - AdvisoryClusterCard: Compact triage card for each cluster
 * - buildClusterViewModels: Helper to build cluster view-models from review enrichment data
 * - reviewEnrichmentStatusMessage: Helper for status message generation
 */

import {
  ReviewEnrichment,
  ReviewEnrichmentStatus,
  RunPayload,
} from "../types";
import {
  artifactUrl,
  formatTimestamp,
  statusClass,
} from "../utils";
import {
  AdvisoryTopConcernsSection,
  AdvisoryEvidenceGapsSection,
  AdvisoryNextChecksSection,
  AdvisoryFocusNotesSection,
  AdvisoryAlertEvidenceSection,
} from "./AdvisorySections";

// ============================================================================
// Helper functions
// ============================================================================

const reviewEnrichmentStatusMessage = (status?: ReviewEnrichmentStatus) => {
  if (!status) {
    return "Provider-assisted review enrichment is not configured for this run.";
  }
  const reason = status.reason;
  switch (status.status) {
    case "policy-disabled":
      return reason || "Review enrichment is disabled in the current configuration.";
    case "provider-missing":
      return reason || "No provider is configured for review enrichment.";
    case "adapter-unavailable":
      return reason || "The configured adapter is not registered for review enrichment.";
    case "awaiting-next-run":
      return (
        reason || "Review enrichment is enabled now, but the latest recorded run predates this setting."
      );
    case "not-attempted":
      return (
        reason || "Review enrichment was enabled for this run, but no artifact was recorded."
      );
    case "unknown":
      return reason || "Review enrichment status cannot be determined for this run.";
    default:
      return (
        reason || "Review enrichment will run once the deterministic review artifact is available."
      );
  }
};

// ============================================================================
// Props type
// ============================================================================

export type ReviewEnrichmentPanelProps = {
  reviewEnrichment: RunPayload["reviewEnrichment"];
  reviewEnrichmentStatus: RunPayload["reviewEnrichmentStatus"];
  nextCheckPlan: RunPayload["nextCheckPlan"];
  onNavigateToQueue?: () => void;
  onFocusQueueReview?: () => void;
};

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Executive summary strip - compact scan-friendly overview metrics
 */
const AdvisoryExecutiveSummary = ({
  reviewEnrichment,
  reviewEnrichmentStatus,
}: {
  reviewEnrichment: ReviewEnrichment;
  reviewEnrichmentStatus?: ReviewEnrichmentStatus;
}) => {
  const clusterCount = reviewEnrichment.triageOrder.length;
  const concernCount = reviewEnrichment.topConcerns.length;
  const gapCount = reviewEnrichment.evidenceGaps.length;
  const nextCheckCount = reviewEnrichment.nextChecks.length;
  const hasFocusNotes = reviewEnrichment.focusNotes.length > 0;

  // Collect notable tags from concerns
  const concernTags = reviewEnrichment.topConcerns.slice(0, 2);

  // Get provider info - prefer direct enrichment provider, fall back to status
  const providerLabel = reviewEnrichment.provider ?? reviewEnrichmentStatus?.provider ?? reviewEnrichmentStatus?.runProvider;

  if (clusterCount === 0) {
    return null;
  }

  return (
    <div className="advisory-summary-strip">
      {/* Provider display - required for test compatibility */}
      <div className="advisory-summary-provider">
        <span className="muted small">
          {providerLabel ? `Provider ${providerLabel}` : "Provider unspecified"}
        </span>
      </div>
      <div className="provider-metrics">
        <div className="provider-metric provider-metric--clusters">
          <span className="provider-metric__value">{clusterCount}</span>
          <span className="provider-metric__label">Cluster{clusterCount !== 1 ? "s" : ""}</span>
        </div>
        <div className="provider-metric provider-metric--concerns">
          <span className="provider-metric__value">{concernCount}</span>
          <span className="provider-metric__label">Concern{concernCount !== 1 ? "s" : ""}</span>
        </div>
        <div className="provider-metric provider-metric--checks">
          <span className="provider-metric__value">{nextCheckCount}</span>
          <span className="provider-metric__label">Check{nextCheckCount !== 1 ? "s" : ""}</span>
        </div>
        {gapCount > 0 && (
          <div className="provider-metric provider-metric--gaps">
            <span className="provider-metric__value">{gapCount}</span>
            <span className="provider-metric__label">Gap{gapCount !== 1 ? "s" : ""}</span>
          </div>
        )}
      </div>
      {concernTags.length > 0 && (
        <div className="advisory-chip-row">
          {concernTags.map((tag) => (
            <span key={tag} className="advisory-chip advisory-chip--concern">{tag}</span>
          ))}
        </div>
      )}
      {hasFocusNotes && (
        <div className="advisory-chip-row">
          <span className="advisory-chip advisory-chip--focus">Focus note</span>
        </div>
      )}
    </div>
  );
};

/**
 * Cluster overview card - compact triage card for each cluster
 */
const AdvisoryClusterCard = ({
  clusterName,
  rank,
  topConcerns,
  focusNotes,
}: {
  clusterName: string;
  rank: number;
  topConcerns: string[];
  focusNotes: string[];
}) => {
  const primaryConcern = topConcerns[0];
  const focusNote = focusNotes[0];

  return (
    <article className="advisory-cluster-card">
      <header className="advisory-cluster-card-header">
        <span className="advisory-cluster-rank">#{rank}</span>
        <strong className="advisory-cluster-name">{clusterName}</strong>
      </header>
      {primaryConcern && (
        <p className="advisory-cluster-concern">{primaryConcern}</p>
      )}
      {focusNote && (
        <p className="advisory-cluster-focus">
          <span className="advisory-focus-hint">Focus: </span>
          {focusNote}
        </p>
      )}
    </article>
  );
};

/**
 * Build cluster view-model from review enrichment data.
 * Concerns that explicitly mention the cluster name are attached to that cluster.
 * For the first cluster (index 0), if no cluster-specific concerns exist,
 * attach the top concerns as generic (typically the top problems affecting triage order).
 * Focus notes are matched if they contain the cluster name.
 */
const buildClusterViewModels = (reviewEnrichment: ReviewEnrichment) => {
  return reviewEnrichment.triageOrder.map((clusterName, index) => {
    const clusterLower = clusterName.toLowerCase();

    // Concerns that explicitly reference this cluster by name
    const clusterSpecificConcerns = reviewEnrichment.topConcerns.filter(
      (concern) => concern.toLowerCase().includes(clusterLower)
    );

    // If no cluster-specific concerns, attach the first concern as generic
    // (typically the top problem affecting triage order)
    const clusterConcerns = clusterSpecificConcerns.length > 0
      ? clusterSpecificConcerns.slice(0, 2)
      : (index === 0 ? reviewEnrichment.topConcerns.slice(0, 2) : []);

    // Focus notes that mention this cluster
    const clusterFocusNotes = reviewEnrichment.focusNotes.filter(
      (note) => note.toLowerCase().includes(clusterLower)
    );

    return {
      clusterName,
      rank: index + 1,
      topConcerns: clusterConcerns,
      focusNotes: clusterFocusNotes,
    };
  });
};

// ============================================================================
// Main component
// ============================================================================

const ReviewEnrichmentPanel = ({
  reviewEnrichment,
  reviewEnrichmentStatus,
  nextCheckPlan,
  onNavigateToQueue,
  onFocusQueueReview,
}: ReviewEnrichmentPanelProps) => {
  const status =
    reviewEnrichment?.status || reviewEnrichmentStatus?.status || "pending";
  const artifactLink = reviewEnrichment?.artifactPath
    ? artifactUrl(reviewEnrichment.artifactPath)
    : null;
  // Check if this enrichment led to planning - match by artifact path
  const enrichmentArtifactPath = reviewEnrichment?.artifactPath;
  const linkedPlan = nextCheckPlan?.enrichmentArtifactPath === enrichmentArtifactPath
    ? nextCheckPlan
    : null;
  const planCandidates = linkedPlan?.candidates ?? [];
  const planCandidateCount = linkedPlan?.candidateCount ?? planCandidates.length;
  const topPlanCandidates = planCandidates.slice(0, 3);
  const hasLinkedPlan = Boolean(linkedPlan) && planCandidateCount > 0;

  // Build cluster view models for cards
  const clusterViewModels = reviewEnrichment ? buildClusterViewModels(reviewEnrichment) : [];

  const runConfigDescription = () => {
    if (!reviewEnrichmentStatus) {
      return null;
    }
    if (reviewEnrichmentStatus.runEnabled === null) {
      return "Run metadata unavailable";
    }
    if (!reviewEnrichmentStatus.runEnabled) {
      return "Run configuration disabled review enrichment";
    }
    const runProvider = reviewEnrichmentStatus.runProvider
      ? ` (${reviewEnrichmentStatus.runProvider})`
      : "";
    return `Run configuration enabled${runProvider}`;
  };

  const providerLabel =
    reviewEnrichmentStatus?.provider ?? reviewEnrichmentStatus?.runProvider;
  const providerDisplay = providerLabel ? `Provider ${providerLabel}` : "Provider unspecified";

  return (
    <section className="panel review-enrichment" id="review-enrichment">
      {/* Header row with title, metadata, timestamp, and status badge - aligned to section-head pattern */}
      <div className="section-head">
        <div>
          <p className="eyebrow">Review enrichment</p>
          <h2>Provider-assisted advisory</h2>
        </div>
        <div className="status-badges">
          <span className={`status-pill ${statusClass(status)}`}>{status}</span>
          {reviewEnrichment?.timestamp && (
            <span className="muted small">{formatTimestamp(reviewEnrichment.timestamp)}</span>
          )}
        </div>
      </div>

      {reviewEnrichment ? (
        <div className="review-enrichment-body">
          {/* Executive summary strip - compact scan-friendly overview */}
          <AdvisoryExecutiveSummary
            reviewEnrichment={reviewEnrichment}
            reviewEnrichmentStatus={reviewEnrichmentStatus}
          />

          {/* Cluster overview cards */}
          {clusterViewModels.length > 0 && (
            <div className="advisory-cluster-grid">
              {clusterViewModels.map((vm) => (
                <AdvisoryClusterCard
                  key={vm.clusterName}
                  clusterName={vm.clusterName}
                  rank={vm.rank}
                  topConcerns={vm.topConcerns}
                  focusNotes={vm.focusNotes}
                />
              ))}
            </div>
          )}

          {/* Enrichment summary from provider - demoted to small muted text below cards */}
          {reviewEnrichment.summary && (
            <details className="advisory-summary-collapsible">
              <summary className="muted small">View provider summary</summary>
              <p className="review-enrichment-summary muted">{reviewEnrichment.summary}</p>
            </details>
          )}

          {/* Lower advisory sections - compressed, structured, operator-friendly */}
          <div className="advisory-lower-sections">
            <div className="advisory-lower-row advisory-lower-row--top">
              <AdvisoryTopConcernsSection concerns={reviewEnrichment.topConcerns} />
              <AdvisoryEvidenceGapsSection gaps={reviewEnrichment.evidenceGaps} />
            </div>
            <AdvisoryNextChecksSection checks={reviewEnrichment.nextChecks} />
            <AdvisoryFocusNotesSection notes={reviewEnrichment.focusNotes} />
            {reviewEnrichment.alertmanagerEvidenceReferences?.length ? (
              <AdvisoryAlertEvidenceSection
                references={reviewEnrichment.alertmanagerEvidenceReferences}
              />
            ) : null}
          </div>

          {reviewEnrichment.errorSummary ? (
            <p className="small muted">Error: {reviewEnrichment.errorSummary}</p>
          ) : null}
          {reviewEnrichment.skipReason ? (
            <p className="small muted">Skipped because {reviewEnrichment.skipReason}</p>
          ) : null}
          {artifactLink ? (
            <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
              View enrichment artifact
            </a>
          ) : null}
          {hasLinkedPlan && (
            <div className="review-enrichment-planning-summary">
              <p className="eyebrow">Planning outcomes</p>
              <p className="small">
                {planCandidateCount} candidate{planCandidateCount === 1 ? "" : "s"} generated from this enrichment
              </p>
              <ul className="review-enrichment-plan-preview">
                {topPlanCandidates.map((candidate, idx) => (
                  <li key={idx}>
                    <span className="tiny">{candidate.description}</span>
                  </li>
                ))}
              </ul>
              {planCandidateCount > 3 && (
                <p className="muted tiny">…and {planCandidateCount - 3} more</p>
              )}
              <button
                type="button"
                className="link"
                onClick={() => {
                  if (onFocusQueueReview) {
                    onFocusQueueReview();
                  }
                  if (onNavigateToQueue) {
                    onNavigateToQueue();
                  }
                }}
              >
                View full queue
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="review-enrichment-body">
          <p className="small">
            {reviewEnrichmentStatusMessage(reviewEnrichmentStatus)}
          </p>
          <p className="small muted">
            {providerDisplay}
            {runConfigDescription() ? ` · ${runConfigDescription()}` : ""}
          </p>
        </div>
      )}
    </section>
  );
};

export { ReviewEnrichmentPanel };
export type { ReviewEnrichmentPanelProps };
