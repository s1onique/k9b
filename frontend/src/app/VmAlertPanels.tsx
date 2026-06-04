/**
 * VmAlertPanels Component
 *
 * VictoriaMetrics vmalert discovery and alert state panels.
 * Extracted from App.tsx to reduce component size.
 */

import { VmalertDiscoveryPanel } from "../components/VmalertDiscoveryPanel";
import { VmalertAlertStatePanel } from "../components/VmalertAlertStatePanel";

export interface VmAlertPanelsProps {
  vmalertSources?: unknown;
  vmalertRuleState?: unknown;
}

export function VmAlertPanels({ vmalertSources, vmalertRuleState }: VmAlertPanelsProps) {
  return (
    <>
      {/* VictoriaMetrics vmalert discovery - compact display only, no actions */}
      <VmalertDiscoveryPanel vmalertSources={vmalertSources} />
      {/* VictoriaMetrics vmalert alert state - compact display of alert counts and firing alerts */}
      <VmalertAlertStatePanel vmalertRuleState={vmalertRuleState} />
    </>
  );
}