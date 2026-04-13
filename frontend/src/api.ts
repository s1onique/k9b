import type {
  ClusterDetailPayload,
  DeterministicNextCheckPromotionRequest,
  DeterministicNextCheckPromotionResponse,
  FleetPayload,
  NextCheckApprovalRequest,
  NextCheckApprovalResponse,
  NextCheckExecutionRequest,
  NextCheckExecutionResponse,
  NotificationsPayload,
  ProposalsPayload,
  RunPayload,
  UsefulnessFeedbackRequest,
  UsefulnessFeedbackResponse,
} from "./types";

type NextCheckExecutionError = Error & { blockingReason?: string | null };

const fetchJson = async <T>(path: string): Promise<T> => {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch ${path}: ${response.statusText}`);
  }
  return response.json();
};

export const fetchRun = (runId?: string): Promise<RunPayload> => {
  const suffix = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return fetchJson<RunPayload>(`/api/run${suffix}`);
};
export const fetchFleet = (): Promise<FleetPayload> => fetchJson<FleetPayload>("/api/fleet");
export const fetchProposals = (): Promise<ProposalsPayload> => fetchJson<ProposalsPayload>("/api/proposals");

export type NotificationsQuery = {
  kind?: string;
  cluster_label?: string;
  search?: string;
  limit?: number;
  page?: number;
};

export type NotificationsResponse = NotificationsPayload;

export const fetchNotifications = (
  query?: NotificationsQuery
): Promise<NotificationsResponse> => {
  const params = new URLSearchParams();
  if (query?.kind) {
    params.append("kind", query.kind);
  }
  if (query?.cluster_label) {
    params.append("cluster_label", query.cluster_label);
  }
  if (query?.search) {
    params.append("search", query.search);
  }
  if (query?.limit) {
    params.append("limit", String(query.limit));
  }
  if (query?.page) {
    params.append("page", String(query.page));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<NotificationsResponse>(`/api/notifications${suffix}`);
};
export const fetchClusterDetail = (clusterLabel?: string): Promise<ClusterDetailPayload> => {
  const suffix = clusterLabel ? `?cluster_label=${encodeURIComponent(clusterLabel)}` : "";
  return fetchJson<ClusterDetailPayload>(`/api/cluster-detail${suffix}`);
};

export const executeNextCheckCandidate = async (
  request: NextCheckExecutionRequest
): Promise<NextCheckExecutionResponse> => {
  const response = await fetch("/api/next-check-execution", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });
  if (!response.ok) {
    let message = response.statusText;
    let blockingReason: string | null | undefined;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object") {
        if ("error" in payload) {
          message = String((payload as Record<string, unknown>).error);
        }
        if ("blockingReason" in payload) {
          blockingReason = (payload as Record<string, unknown>).blockingReason as string | null;
        }
      }
    } catch {
      // ignore
    }
    const error = new Error(
      message || "Failed to execute next-check candidate"
    ) as NextCheckExecutionError;
    error.blockingReason = blockingReason ?? null;
    throw error;
  }
  const data = await response.json();
  return data as NextCheckExecutionResponse;
};

export const approveNextCheckCandidate = async (
  request: NextCheckApprovalRequest
): Promise<NextCheckApprovalResponse> => {
  const response = await fetch("/api/next-check-approval", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to approve next-check candidate");
  }
  const data = await response.json();
  return data as NextCheckApprovalResponse;
};

export const promoteDeterministicNextCheck = async (
  request: DeterministicNextCheckPromotionRequest
): Promise<DeterministicNextCheckPromotionResponse> => {
  const response = await fetch("/api/deterministic-next-check/promote", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to promote deterministic next check");
  }
  return (await response.json()) as DeterministicNextCheckPromotionResponse;
};

export const submitUsefulnessFeedback = async (
  request: UsefulnessFeedbackRequest
): Promise<UsefulnessFeedbackResponse> => {
  const response = await fetch("/api/next-check-execution-usefulness", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const payload = await response.json();
      if (payload && typeof payload === "object" && "error" in payload) {
        message = String((payload as Record<string, unknown>).error);
      }
    } catch {
      // ignore
    }
    throw new Error(message || "Failed to submit usefulness feedback");
  }
  return (await response.json()) as UsefulnessFeedbackResponse;
};

export type RunsListPayload = import("./types").RunsListPayload;

export const fetchRunsList = (): Promise<RunsListPayload> => fetchJson<RunsListPayload>("/api/runs");
