/**
 * vmalert.ts — TypeScript type definitions for VictoriaMetrics vmalert integration.
 *
 * Mirrors the backend VmalertSourceView and VmalertSourcesView from
 * src/k8s_diag_agent/ui/model_vmalert.py and VmalertRuleState*View from
 * src/k8s_diag_agent/ui/model_vmalert_rule_state.py
 *
 * Backend fields (vmalertSourcesView):
 * - sources: VmalertSourceView[]
 * - total_count: int
 * - source_count: int (same as total_count for backward compatibility)
 * - discovered_count: int
 * - discovered_but_unverified_count: int
 * - auto_tracked_count: int
 * - manual_count: int
 * - discovery_timestamp: str | None
 * - cluster_context: str | None
 *
 * Backend fields (VmalertRuleStatePayload):
 * - source_count: int
 * - fetched_source_count: int
 * - failed_source_count: int
 * - alert_count: int
 * - firing_alert_count: int
 * - pending_alert_count: int
 * - critical_firing_count: int
 * - rule_group_count: int
 * - fetch_error_count: int
 * - captured_at: str
 * - alerts: VmalertRuleStateAlertPayload[]
 * - rule_groups: VmalertRuleStateRuleGroupPayload[]
 * - fetch_errors: VmalertRuleStateFetchErrorPayload[]
 *
 * Frontend usage: compact display in RunSummaryPanel, similar to alertmanagerCompact.
 * Full source table is out of scope for this slice.
 */

/** A single vmalert source entry from discovery */
export type VmalertSource = {
  source_id: string;
  /** Stable key for cross-run deduplication */
  matching_key: string;
  /** Canonical identity from discovery layer */
  canonical_identity: string;
  endpoint: string;
  namespace: string | null;
  name: string | null;
  origin: string;
  state: string;
  discovered_at: string | null;
  verified_at: string | null;
  last_check: string | null;
  last_error: string | null;
  verified_version: string | null;
  confidence_hints: string[];
  /** All origins that contributed to this source (for deduplication display) */
  merged_provenances: string[];
  /** Human-readable provenance for UI tooltip */
  display_provenance: string;
  /** Computed UI fields */
  is_manual: boolean;
  is_tracking: boolean;
  can_disable: boolean;
  can_promote: boolean;
  display_origin: string;
  display_state: string;
  provenance_summary: string;
  /** Operator-facing cluster label for per-cluster UI filtering */
  cluster_label: string | null;
  /** Manual source mode: "operator-configured" | "operator-promoted" | null */
  manual_source_mode: string | null;
  /** Deterministic identity for historical/debug tracking */
  canonicalEntityId: string | null;
  cluster_uid: string | null;
  object_uid: string | null;
};

/** Full vmalert source inventory */
export type VmalertSources = {
  sources: VmalertSource[];
  total_count: number;
  source_count: number;
  discovered_count: number;
  discovered_but_unverified_count: number;
  auto_tracked_count: number;
  manual_count: number;
  discovery_timestamp: string | null;
  cluster_context: string | null;
};

/** A single vmalert alert in rule state */
export type VmalertRuleStateAlert = {
  alertname: string;
  state: string;
  severity: string | null;
  cluster_label: string | null;
  namespace: string | null;
  workload: string | null;
  pod: string | null;
  instance: string | null;
  summary: string | null;
  description: string | null;
  active_at: string | null;
  starts_at: string | null;
  source_endpoint: string | null;
  group_name: string | null;
  rule_name: string | null;
};

/** A vmalert rule group in rule state */
export type VmalertRuleStateRuleGroup = {
  name: string;
  file: string | null;
  interval: string | null;
  rule_count: number;
  firing_alert_count: number;
  error_count: number;
};

/** A vmalert fetch error in rule state */
export type VmalertRuleStateFetchError = {
  source_endpoint: string;
  source_id: string | null;
  status: string;
  error: string;
};

/** Full vmalert rule state for a run */
export type VmalertRuleState = {
  source_count: number;
  fetched_source_count: number;
  failed_source_count: number;
  alert_count: number;
  firing_alert_count: number;
  pending_alert_count: number;
  critical_firing_count: number;
  rule_group_count: number;
  fetch_error_count: number;
  captured_at: string;
  alerts: VmalertRuleStateAlert[];
  rule_groups: VmalertRuleStateRuleGroup[];
  fetch_errors: VmalertRuleStateFetchError[];
};