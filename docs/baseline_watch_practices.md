# Baseline & Watched Release Practices

This document keeps platform-level parity guidance in one place so operators can manage baseline policies and watched releases without drifting into ad hoc app-level detail.

## Platform-level baseline parity

- Treat the baseline as the authoritative description of what the platform expects to support: control-plane versions, shared CRDs, and curated release families that matter across workloads.
- Every watched release key declared in `runs/health-config*.json` should exist in the baseline policy so the preflight can verify compatibility before any health run executes.
- Prefer grouping release keys by platform concern (e.g., ingress controller, service mesh, cluster agent) rather than mirroring every application release version you track elsewhere.
- When platform policy changes (control-plane upgrade, CRD refresh, shared Helm chart bump), update the baseline and confirm the preflight still passes before the loop runs again.

## Pruning baseline releases

1. When a platform release retires, remove its entry from the baseline after ensuring no target still watches it.
2. If a baseline release needs to persist for traceability, add a short note inside the baseline policy describing why it stays (e.g., historical audit, compatibility window).
3. Run `scripts/inspect_health_config.py runs/health-config.local.json` after pruning to confirm no watched release is left orphaned; the preflight now prints missing baseline policies and guidance when the alignment is off.

## Targeting watched releases safely

- Keep watched releases focused on the platform-level artifacts that influence health assessments (shared operators, ingress, authentication charts, etc.). Avoid mirroring every application Helm release unless it directly influences the platform health you care about.
- If a watched release absolutely needs to stay, add or update the matching baseline entry rather than patching the health config alone. The inspector now flags any mismatch and prints explicit guidance about the required metadata or baseline entry.
- Use the inspector output to spot suspicious-drift pairs that fail compatibility (class/role/cohort misalignment) so you can adjust metadata before the run proceeds.
- Remember that `scripts/run_health_once.sh` already chains the config inspection, single health loop, and summary (plus optional digest), so the quick path mirrors the scheduled loop’s gating and artifact layout.
