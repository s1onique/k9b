/**
 * DeterministicNextChecksPanel
 * 
 * Extracts the deterministic-next-checks section from App.tsx.
 * Displays evidence-based diagnostic checks organized by workstream
 * (incident, evidence, drift) with promotion and filtering capabilities.
 */

import type {
  DeterministicNextCheckCluster,
  DeterministicNextCheckSummary,
  DeterministicNextChecks,
  PromotionStatus,
} from "../types";

// File-scope constants for deterministic next checks
const DETERMINISTIC_WORKSTREAM_LABELS: Record<string, string> = {
  incident: "Firefight now",
  evidence: "Evidence gathering",
  drift: "Drift / toil follow-up",
};
const DETERMINISTIC_WORKSTREAM_DESCRIPTIONS: Record<string, string> = {
  incident: "Focus on the current degraded symptom",
  evidence: "Collect supporting telemetry and context",
  drift: "Log drift, parity, and toil follow-up",
};
const INCIDENT_PREVIEW_LIMIT = 3;

export interface DeterministicNextChecksPanelProps {
  deterministicChecks?: DeterministicNextChecks | null;
  deterministicSummary: string;
  hookPromotionStatus: Record<string, PromotionStatus>;
  incidentExpandedClusters: Record<string, boolean>;
  onPromoteCheck: (
    clusterLabel: string,
    context: string | null,
    topProblem: string | null,
    check: DeterministicNextCheckSummary,
    index: number
  ) => void;
  onToggleIncidentExpansion: (label: string) => void;
  onFocusClusterForNextChecks: (clusterLabel?: string | null) => void;
  onSetQueueStatusFilter: (status: string) => void;
  onSetQueueClusterFilter: (cluster: string) => void;
  onScrollToSection: (id: string) => void;
  artifactUrl: (path: string) => string;
  hasDegradedClusters: boolean;
}

interface DeterministicCluster extends DeterministicNextCheckCluster {
  context: string;
}

const sortDeterministicSummaries = (
  summaries: DeterministicNextCheckSummary[] = []
): DeterministicNextCheckSummary[] =>
  [...summaries].sort((first, second) => (second.priorityScore ?? 0) - (first.priorityScore ?? 0));

const buildPromotionKey = (clusterLabel: string, description: string, index: number) =>
  `${clusterLabel}::${description}::${index}`;

export function DeterministicNextChecksPanel({
  deterministicChecks,
  deterministicSummary,
  hookPromotionStatus,
  incidentExpandedClusters,
  onPromoteCheck,
  onToggleIncidentExpansion,
  onFocusClusterForNextChecks,
  onSetQueueStatusFilter,
  onSetQueueClusterFilter,
  onScrollToSection,
  artifactUrl,
  hasDegradedClusters,
}: DeterministicNextChecksPanelProps) {
  const deterministicClusters: DeterministicCluster[] = deterministicChecks?.clusters ?? [];
  const hasDeterministicNextChecks = deterministicClusters.length > 0;

  return (
    <section className="panel deterministic-next-checks-panel" id="deterministic-next-checks">
      <div className="section-head">
        <div>
          <p className="eyebrow">Deterministic evidence</p>
          <h2>Deterministic next checks</h2>
          <p className="muted tiny">{deterministicSummary}</p>
        </div>
        <span className="muted tiny">
          {deterministicChecks?.clusterCount ?? 0} degraded cluster
          {(deterministicChecks?.clusterCount ?? 0) === 1 ? "" : "s"}
        </span>
      </div>
      {hasDeterministicNextChecks ? (
        <div className="deterministic-cluster-grid">
          {deterministicClusters.map((cluster) => {
            const sortedChecks = sortDeterministicSummaries(
              cluster.deterministicNextCheckSummaries
            );
            const incidentChecks = sortedChecks.filter((check) => check.workstream === "incident");
            const evidenceChecks = sortedChecks.filter((check) => check.workstream === "evidence");
            const driftChecks = sortedChecks.filter((check) => check.workstream === "drift");
            const isIncidentExpanded = Boolean(incidentExpandedClusters[cluster.label]);
            const incidentPreview = isIncidentExpanded
              ? incidentChecks
              : incidentChecks.slice(0, INCIDENT_PREVIEW_LIMIT);
            const incidentHasMore = incidentChecks.length > INCIDENT_PREVIEW_LIMIT;
            const renderCheckItem = (
              check: DeterministicNextCheckSummary,
              index: number
            ) => {
              const promotionKey = buildPromotionKey(cluster.label, check.description, index);
              const promotionEntry = hookPromotionStatus[promotionKey];
              const isPromoting = promotionEntry?.status === "pending";
              const isPromoted = promotionEntry?.status === "success";
              return (
                <li key={`${cluster.label}-${check.workstream}-${index}`}>
                  <div className="deterministic-check-head">
                    <div>
                      <strong>{check.description}</strong>
                      <div className="deterministic-check-badges">
                        <span
                          className={`deterministic-workstream-pill deterministic-workstream-pill-${check.workstream}`}
                        >
                          {DETERMINISTIC_WORKSTREAM_LABELS[check.workstream]}
                        </span>
                        <span
                          className={`deterministic-urgency-pill deterministic-urgency-pill-${check.urgency}`}
                        >
                          {check.urgency}
                        </span>
                        {check.isPrimaryTriage ? (
                          <span className="deterministic-primary-pill">Primary triage</span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <div className="deterministic-check-meta">
                    <span>Method: {check.method || "—"}</span>
                    <span>Owner: {check.owner}</span>
                  </div>
                  <p className="muted tiny">{check.whyNow}</p>
                  {check.evidenceNeeded.length ? (
                    <p className="muted tiny">
                      Evidence: {check.evidenceNeeded.join(", ")}
                    </p>
                  ) : null}
                  <div className="deterministic-check-actions">
                    {isPromoted ? (
                      <span className="muted tiny">Promoted to queue</span>
                    ) : (
                      <button
                        type="button"
                        className="button tertiary tiny"
                        onClick={() =>
                          onPromoteCheck(
                            cluster.label,
                            cluster.context || null,
                            cluster.topProblem ?? null,
                            check,
                            index
                          )
                        }
                        disabled={isPromoting}
                      >
                        {isPromoting ? "Promoting…" : "Add to work list"}
                      </button>
                    )}
                    {promotionEntry?.message ? (
                      <p className="muted tiny deterministic-promotion-message">
                        {promotionEntry.message}
                      </p>
                    ) : null}
                    {isPromoted ? (
                      <button
                        type="button"
                        className="deterministic-promotion-view-queue-link"
                        onClick={() => {
                          onSetQueueStatusFilter("approval-needed");
                          onSetQueueClusterFilter(cluster.label);
                          onScrollToSection("next-check-queue");
                        }}
                      >
                        View in work list →
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            };
            const buildCheckCountLabel = (count: number) =>
              `${count} check${count === 1 ? "" : "s"}`;
            return (
              <article className="deterministic-cluster-card" key={cluster.label}>
                <div className="deterministic-cluster-head">
                  <div>
                    <p className="eyebrow">Cluster detail</p>
                    <h3>{cluster.label}</h3>
                    <p className="muted tiny">
                      {cluster.topProblem ?? "Trigger reasons pending"}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="run-summary-next-checks-button"
                    onClick={() => onFocusClusterForNextChecks(cluster.label)}
                  >
                    Review cluster detail
                  </button>
                </div>
                <div className="deterministic-cluster-stats">
                  <span>
                    {cluster.deterministicNextCheckCount} deterministic check
                    {cluster.deterministicNextCheckCount === 1 ? "" : "s"}
                  </span>
                  <span>
                    Drilldown: {cluster.drilldownAvailable ? "available" : "missing"}
                  </span>
                </div>
                <div className="deterministic-group-list">
                  <section className="deterministic-group">
                    <div className="deterministic-group-head">
                      <div>
                        <p className="eyebrow">{DETERMINISTIC_WORKSTREAM_LABELS.incident}</p>
                        <p className="muted tiny">
                          {DETERMINISTIC_WORKSTREAM_DESCRIPTIONS.incident}
                        </p>
                      </div>
                      <span className="muted tiny">
                        {buildCheckCountLabel(incidentChecks.length)}
                      </span>
                    </div>
                    {incidentChecks.length ? (
                      <>
                        <ul className="deterministic-check-list">
                          {incidentPreview.map(renderCheckItem)}
                        </ul>
                        {incidentHasMore ? (
                          <button
                            type="button"
                            className="text-button deterministic-show-more"
                            onClick={() => onToggleIncidentExpansion(cluster.label)}
                          >
                            {isIncidentExpanded
                              ? "Show fewer incident checks"
                              : `Show all ${incidentChecks.length} incident checks`}
                          </button>
                        ) : null}
                      </>
                    ) : (
                      <p className="muted tiny deterministic-empty-bucket">No firefight checks for this cluster.</p>
                    )}
                  </section>
                  <section className="deterministic-group">
                    <div className="deterministic-group-head">
                      <div>
                        <p className="eyebrow">{DETERMINISTIC_WORKSTREAM_LABELS.evidence}</p>
                        <p className="muted tiny">
                          {DETERMINISTIC_WORKSTREAM_DESCRIPTIONS.evidence}
                        </p>
                      </div>
                      <span className="muted tiny">
                        {buildCheckCountLabel(evidenceChecks.length)}
                      </span>
                    </div>
                    {evidenceChecks.length ? (
                      <ul className="deterministic-check-list">
                        {evidenceChecks.map(renderCheckItem)}
                      </ul>
                    ) : (
                      <p className="muted tiny deterministic-empty-bucket">No evidence gathering checks for this cluster.</p>
                    )}
                  </section>
                  <details
                    className="deterministic-group deterministic-group--drift"
                    open={!hasDegradedClusters}
                  >
                    <summary className="deterministic-group-head">
                      <div>
                        <p className="eyebrow">{DETERMINISTIC_WORKSTREAM_LABELS.drift}</p>
                        <p className="muted tiny">
                          {DETERMINISTIC_WORKSTREAM_DESCRIPTIONS.drift}
                        </p>
                      </div>
                      <span className="muted tiny">
                        {buildCheckCountLabel(driftChecks.length)}
                      </span>
                    </summary>
                    {driftChecks.length ? (
                      <ul className="deterministic-check-list">
                        {driftChecks.map(renderCheckItem)}
                      </ul>
                    ) : (
                      <p className="muted tiny deterministic-empty-bucket">No drift/toil checks for this cluster.</p>
                    )}
                  </details>
                </div>
                <div className="deterministic-cluster-attachments">
                  {cluster.assessmentArtifactPath ? (
                    <a
                      className="link tiny"
                      href={artifactUrl(cluster.assessmentArtifactPath)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      View assessment artifact
                    </a>
                  ) : null}
                  {cluster.drilldownArtifactPath ? (
                    <a
                      className="link tiny"
                      href={artifactUrl(cluster.drilldownArtifactPath)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      View drilldown artifact
                    </a>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="deterministic-empty-state">
          <p className="muted small">No evidence-based checks are available for this run.</p>
          <p className="muted tiny">Review the cluster detail for evidence-based checks to promote.</p>
        </div>
      )}
    </section>
  );
}