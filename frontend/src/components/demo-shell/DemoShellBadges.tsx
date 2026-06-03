/**
 * Demo Shell Badge Components
 *
 * Evidence source, severity, and safety mode badge components.
 */

import type { EvidenceSource, SafetyMode, SeverityLevel } from "./DemoShellTypes";
import { EVIDENCE_SOURCE_LABELS, SAFETY_MODE_LABELS, SEVERITY_CONFIG } from "./DemoShellData";

/** Evidence Source Badge */
export const EvidenceSourceBadge = ({ source }: { source: EvidenceSource }) => (
  <span className={`demo-badge demo-badge--${source}`}>
    {EVIDENCE_SOURCE_LABELS[source]}
  </span>
);

/** Severity Badge */
export const SeverityBadge = ({ severity }: { severity: SeverityLevel }) => (
  <span className={`demo-badge ${SEVERITY_CONFIG[severity].colorClass}`}>
    {SEVERITY_CONFIG[severity].label}
  </span>
);

/** Safety Mode Label */
export const SafetyModeLabel = ({ mode }: { mode: SafetyMode }) => (
  <span className={`demo-badge demo-badge--safety-${mode.replace("-", "")}`}>
    {SAFETY_MODE_LABELS[mode]}
  </span>
);