# Health run artifacts

Tracked JSON files under `runs/` provide placeholders and examples for configuring the health loop. Keep the tracked files read-only in source control and copy them locally before applying fleet policy.

## Config files

- `health-config.local.example.json` is the repository-provided example. Copy it to `health-config.local.json` (which is ignored by git) and fill in your real kube contexts, peer mappings, and other runtime values.
- `health-config.local.json` is the file the runner actually reads. Point its `baseline_policy_path` at `health-baseline.local.json` if you need a fleet-specific baseline.

## Baseline policy

- `health-baseline.example.json` is a checked-in placeholder needed for tests and examples. Do not modify it directly.
- Create `health-baseline.local.json` (ignored by git) next to the config and describe your true control-plane, release, CRD, and peer role policy there. The loader prefers `health-baseline.local.json`, then falls back to `health-baseline.json` for backwards compatibility, and finally to the example file if nothing else exists.

This separation keeps placeholder values isolated while letting the live runner pick up real fleet policy from your local overrides.

For guidance on pruning baseline release entries and aligning watched Helm releases with the platform-level policy, see `docs/baseline_watch_practices.md`.

## Cluster metadata and comparisons

- Each target entry in `health-config.local.json` must now declare `cluster_class`, `cluster_role`, and `baseline_cohort` (or legacy `platform_generation`) so the loop can reason about intent, responsibilities, and cohort compatibility. Run `scripts/inspect_health_config.py runs/health-config.local.json` to preview the metadata matrix, see which peer mappings are eligible, skipped, or unsafe, and confirm every suspicious-drift comparison stays within the same class/cohort before executing the loop.
- Peer mappings now accept an `intent` field (`suspicious-drift`, `expected-drift`, or `irrelevant-drift`). The loop only triggers comparisons when the declared intent is compatible with the clustered metadata and the policy permits it.
- Use `scripts/run_health_once.sh` to chain the config inspection, a single `run-health-loop` invocation, `health-summary`, and an optional `make_health_digest.sh` digest in one go. The wrapper reuses the configured `output_dir`, annotates statuses, and keeps the operator workflow on the fast path.
- Health runs record their comparison decisions next to the other artifacts as `<run-id>-comparison-decisions.json`. The summary view reads that file to explain which pairs were eligible, which ones actually executed, and why they fired (or did not).
