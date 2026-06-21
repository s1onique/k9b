/**
 * EvidenceArtifactsSection Component
 *
 * Read-only UI for displaying evidence artifact metadata from IncidentDetailPayload.
 * Renders bounded metadata for evidence artifacts linked to an incident.
 *
 * Hard constraints enforced:
 * - NO remediation actions
 * - NO Kubernetes mutation
 * - NO LLM calls
 * - NO external tool invocation
 * - NO persistence
 * - NO write actions
 * - NO raw artifact contents
 * - NO logs, stdout/stderr, stack traces
 * - NO prompts, secrets, tokens, kubeconfig
 */

import type { EvidenceArtifact } from "../api";

export interface EvidenceArtifactsSectionProps {
  evidenceArtifacts: EvidenceArtifact[];
}

/**
 * Formats a timestamp for display in UTC.
 */
const formatTimestamp = (timestamp: string | null): string => {
  if (!timestamp) return "—";
  try {
    const date = new Date(timestamp);
    // Use explicit UTC formatting to match incident timestamp convention
    return date.toISOString().replace("T", " ").replace("Z", " UTC");
  } catch {
    return timestamp;
  }
};

/**
 * Returns a human-readable label for artifact kind.
 */
const getArtifactKindLabel = (kind: string | null): string => {
  if (!kind) return "Unknown";
  switch (kind) {
    case "snapshot_bundle":
      return "Snapshot bundle";
    case "review_packet":
      return "Review packet";
    case "evidence_artifact":
      return "Evidence artifact";
    case "debug_artifact":
      return "Debug artifact";
    default:
      return "Unknown artifact";
  }
};

/**
 * Returns CSS class for artifact kind badge.
 */
const getArtifactKindClass = (kind: string | null): string => {
  if (!kind) return "artifact-kind-unknown";
  switch (kind) {
    case "snapshot_bundle":
      return "artifact-kind-snapshot";
    case "review_packet":
      return "artifact-kind-review";
    case "evidence_artifact":
      return "artifact-kind-evidence";
    case "debug_artifact":
      return "artifact-kind-debug";
    default:
      return "artifact-kind-unknown";
  }
};

/**
 * Renders a single evidence artifact item.
 */
const EvidenceArtifactItem: React.FC<{ artifact: EvidenceArtifact; index: number }> = ({
  artifact,
  index,
}) => {
  const kindClass = getArtifactKindClass(artifact.artifact_kind);
  const kindLabel = getArtifactKindLabel(artifact.artifact_kind);

  return (
    <li key={`${artifact.artifact_id}-${index}`} className="evidence-artifact-item">
      <div className="evidence-artifact-header">
        <span className={`artifact-kind-badge ${kindClass}`}>{kindLabel}</span>
        {artifact.evidence_role && (
          <span className="evidence-role-badge">{artifact.evidence_role}</span>
        )}
      </div>

      <div className="evidence-artifact-id">
        <span className="muted small">Artifact ID:</span>
        <code className="artifact-id">{artifact.artifact_id}</code>
      </div>

      <div className="evidence-artifact-meta muted small">
        {artifact.attached_at && (
          <div className="meta-row">
            <span className="muted">Attached:</span>
            <span>{formatTimestamp(artifact.attached_at)}</span>
          </div>
        )}
        {artifact.safe_reference && (
          <div className="meta-row">
            <span className="muted">Reference:</span>
            <code className="safe-reference">{artifact.safe_reference}</code>
          </div>
        )}
      </div>

      {/* Safety notice */}
      <div className="evidence-artifact-safety muted small">
        <span className="safety-notice">
          Read-only · No remediation · Raw content not available
        </span>
      </div>
    </li>
  );
};

/**
 * Read-only evidence artifacts section.
 * Displays bounded metadata for evidence artifacts linked to an incident.
 *
 * Availability state:
 * - Currently, EvidenceLink has no availability field, so all artifacts are shown
 *   as available with unavailable_reason=null.
 * - Unavailable artifact state is deferred until EvidenceLink model supports it.
 *
 * Safe reference contract:
 * - safe_reference equals artifact_id, which is guaranteed to be a bounded opaque ID.
 * - artifact_id is the approved safe reference convention; it cannot be a file path,
 *   URL, object path, or raw artifact locator.
 *
 * Empty state: "No evidence artifacts attached."
 *
 * Displays:
 * - artifact_id
 * - artifact_kind (human-readable label)
 * - evidence_role
 * - attached_at
 * - safe_reference
 * - Safety wording (read-only, no remediation, raw content not available)
 *
 * Does NOT display:
 * - raw artifact contents
 * - logs, stdout, stderr
 * - stack traces
 * - prompts
 * - secrets, tokens, kubeconfig
 * - Action/remediation controls
 */
export const EvidenceArtifactsSection: React.FC<EvidenceArtifactsSectionProps> = ({
  evidenceArtifacts,
}) => {
  if (evidenceArtifacts.length === 0) {
    return (
      <div className="incident-detail-section">
        <h4>Evidence artifacts</h4>
        <p className="muted small">No evidence artifacts attached.</p>
      </div>
    );
  }

  return (
    <div className="incident-detail-section">
      <h4>Evidence artifacts</h4>
      <p className="muted small">
        Read-only view · No remediation available · Raw content not exposed
      </p>
      <ul className="evidence-artifacts-list">
        {evidenceArtifacts.map((artifact, index) => (
          <EvidenceArtifactItem key={`${artifact.artifact_id}-${index}`} artifact={artifact} index={index} />
        ))}
      </ul>
    </div>
  );
};

export default EvidenceArtifactsSection;
