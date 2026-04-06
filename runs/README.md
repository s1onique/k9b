# Health run artifacts

Tracked JSON files under `runs/` provide placeholders and examples for configuring the health loop. Keep the tracked files read-only in source control and copy them locally before applying fleet policy.

## Config files

- `health-config.local.example.json` is the repository-provided example. Copy it to `health-config.local.json` (which is ignored by git) and fill in your real kube contexts, peer mappings, and other runtime values.
- `health-config.local.json` is the file the runner actually reads. Point its `baseline_policy_path` at `health-baseline.local.json` if you need a fleet-specific baseline.

## Baseline policy

- `health-baseline.example.json` is a checked-in placeholder needed for tests and examples. Do not modify it directly.
- Create `health-baseline.local.json` (ignored by git) next to the config and describe your true control-plane, release, CRD, and peer role policy there. The loader prefers `health-baseline.local.json`, then falls back to `health-baseline.json` for backwards compatibility, and finally to the example file if nothing else exists.

This separation keeps placeholder values isolated while letting the live runner pick up real fleet policy from your local overrides.

## Cluster metadata and comparisons

- Each target entry in `health-config.local.json` can include optional `cluster_class` and `cluster_role` fields to describe its intent within the fleet. These values are surfaced in health summaries and drive policy-aware pairing.
- Peer mappings now accept an `intent` field (`suspicious-drift`, `expected-drift`, or `irrelevant-drift`). The loop only triggers comparisons when the declared intent is compatible with the clustered metadata and the policy permits it.
- Health runs record their comparison decisions next to the other artifacts as `<run-id>-comparison-decisions.json`. The summary view reads that file to explain which pairs were eligible, which ones actually executed, and why they fired (or did not).
