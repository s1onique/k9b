# Fixture Schema

| Field | Description |
| --- | --- |
| `id` | Unique scenario identifier. |
| `timestamp` | RFC3339 time for when the snapshot was captured. |
| `namespace` | Kubernetes namespace under observation. |
| `workload` | Object with `kind` and `name` identifying the workload. |
| `signals.pods` | List of pod status entries with name, status (e.g., `CrashLoopBackOff`), and restart count. |
| `signals.events` | Kubernetes events captured during the incident. |
| `signals.metrics` | Optional metrics snapshots (name/value/labels). |
| `signals.logs` | Optional log entries, each with source, message, and timestamp. |
| `observability_gaps` | Explicit descriptions of missing telemetry. |
| `rollout_history` | Last deployment metadata plus pending rollout flag. |
| `seed_eval_id` | Links the fixture to an eval case in `docs/doctrine/evals/seed_evals.yaml`. |
| `cluster_snapshots` | Optional map or list of per-cluster snapshot entries (metadata, workloads, metrics) to surface real cluster evidence and support two-cluster comparison. See `docs/cluster_snapshot_plan.md` for the expected contract. |

The JSON schema lives in `src/k8s_diag_agent/schemas.py` (exported as `FIXTURE_SCHEMA`). Clients should validate fixtures via `FixtureValidator.validate`.
