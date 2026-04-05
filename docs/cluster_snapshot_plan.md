# Cluster Snapshot Plan

## Goal

Prepare the repo to accept real cluster evidence and compare two clusters side-by-side without derailing the existing fixture-driven slice.

## Snapshot contract

Each cluster snapshot should capture the momentary state of a Kubernetes control plane plus supporting metrics:

- `metadata`: `cluster_id`, `captured_at`, `control_plane_version`, `node_count`, optional `pod_count`, `region`, and contextual labels.
- `workloads`: friendly name keys (deployments, statefulsets, etc.) mapping to structured objects such as replica counts or rollout status.
- `metrics`: key/value pairs (CPU, memory, etc.) that can drive comparison logic; values should be coercible to floats.

Fixtures can surface per-cluster snapshots via the `cluster_snapshots` field (map or list) to keep snapshot ingestion deterministic for now.

## Two-cluster comparison

Use `ClusterSnapshot` instances to represent snapshots from two clusters. The comparator should:

1. Align metadata fields and record differences in node counts, pod counts, regions, and control plane versions.
2. Compare metric sets and expose any drift between clusters, including missing keys.
3. Package comparison results in a `ClusterComparison` object so future reasoning layers can reference the diff summary.

## Next steps for real collection

1. Add adapters that turn `kubectl`, Prometheus, or other telemetry snapshots into the `cluster_snapshots` contract.
2. Install a lightweight catalog of snapshots (e.g., `snapshots/alpha.json`/`snapshots/beta.json`) so the CLI can replay realistic two-cluster comparisons.
3. Expand reasoning to treat `ClusterComparison.differences` as additional signals or findings without disrupting fixture-based tests.
4. Keep recommending low-risk, observability-first actions (logs, node inspection) while collecting snapshots for future automation.
