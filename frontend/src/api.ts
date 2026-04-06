import type {
  ClusterDetailPayload,
  FleetPayload,
  NotificationsPayload,
  ProposalsPayload,
  RunPayload,
} from "./types";

const fetchJson = async <T>(path: string): Promise<T> => {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch ${path}: ${response.statusText}`);
  }
  return response.json();
};

export const fetchRun = (): Promise<RunPayload> => fetchJson<RunPayload>("/api/run");
export const fetchFleet = (): Promise<FleetPayload> => fetchJson<FleetPayload>("/api/fleet");
export const fetchProposals = (): Promise<ProposalsPayload> => fetchJson<ProposalsPayload>("/api/proposals");
export const fetchNotifications = (): Promise<NotificationsPayload> => fetchJson<NotificationsPayload>("/api/notifications");
export const fetchClusterDetail = (clusterLabel?: string): Promise<ClusterDetailPayload> => {
  const suffix = clusterLabel ? `?cluster_label=${encodeURIComponent(clusterLabel)}` : "";
  return fetchJson<ClusterDetailPayload>(`/api/cluster-detail${suffix}`);
};
