# Review packets

## Purpose

Document diagnostic pack/review packet semantics and new incident review packet state.

## Diagnostic pack source-of-truth

The diagnostic pack system uses a layered artifact strategy:

| Artifact | Path | Scope | Mutability | Authority |
|----------|------|-------|------------|-----------|
| Pack ZIP | `diagnostic-packs/diagnostic-pack-{run_id}-{timestamp}.zip` | Run | Immutable (written once) | **Immutable source of truth** |
| Run-scoped contents | `diagnostic-packs/{run_id}/` | Run | Immutable (written once) | Immutable source of truth |
| **Latest mirror** | `diagnostic-packs/latest/` | Global | **Mutable** (overwritten in place) | **NOT authoritative**; convenience alias only |

## Review bundle

### review_bundle.json

The `review_bundle.json` sits beside the digest and captures the complete current-run state in one canonical JSON file.

It preserves:
- Fleet summary
- Deterministic artifacts (assessments, drilldowns, triggers, comparisons)
- External-analysis artifacts
- Proposals
- Review metadata
- Enrichment/provider execution summaries
- Deterministic next checks
- `diagnostic_pack_review` payload

Every artifact entry includes its pack-relative `path` plus fresh `content`, and `artifact_manifest.included_paths` mirrors the manifest.

The review bundle is deterministic, normalized, schema versioned (`diagnostic-pack-review-bundle/v1`), and only surfaces current-run artifacts without mutating or removing raw artifacts.

### review_input_14b.json

Because `review_bundle.json` can still be large for local reviewers, every pack adds a derived `review_input_14b.json`.

That compact artifact (`schema_version: diagnostic-pack-review-input-14b/v1`) is computed deterministically from the same current-run state and keeps only:
- High-level fleet summary
- Trimmed review summary
- Per-cluster top findings/hypotheses/next checks
- Comparison drifts
- External-analysis summaries
- Proposal excerpts
- Artifact-path pointers

Each `cluster_summaries` entry exposes a normalized `cluster_label`, health rating, concise drilldown summary, and artifact references.

## Latest mirror is mutable and non-authoritative

**The `diagnostic-packs/latest/` directory is a mutable derived convenience alias, NOT an immutable artifact.**

- It is overwritten in place when new diagnostic packs are generated or refreshed.
- Immutable truth lives in the actual diagnostic pack ZIP file and run-scoped pack contents.
- API/UI consumers must NOT treat `latest/` paths as immutable references.

When the diagnostic pack payload includes `reviewBundlePath` or `reviewInput14bPath`, consumers should check the `isMirror` field to determine mutability.

## ReviewPacketState

`ReviewPacketState` replaces the old pattern of `review_packet_available: bool` + `review_packet_id: str | None`.

Source: `src/k8s_diag_agent/collect/incident_review_packet_state.py`

### Status values

| Status | Description |
|--------|-------------|
| `NOT_GENERATED` | No review packet has been generated |
| `GENERATING` | Review packet generation in progress |
| `AVAILABLE` | Review packet is ready |
| `FAILED` | Review packet generation failed |

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | ReviewPacketStatus | Current status |
| `id` | str \| None | Artifact ID (required for GENERATING/AVAILABLE) |
| `generated_at` | datetime \| None | When packet was generated |
| `error_message` | str \| None | Error message if failed |

### Invariant

**`GENERATING` and `AVAILABLE` require non-empty `id`.**

The old pattern could produce `review_packet_available=True` + `review_packet_id=None` (drift). This model makes state explicit and prevents drift.

## Review packet is not the central root object

The review packet is a **generated artifact/state attached to Incident**.

Incident remains the case file even when review packet generation fails or is unavailable.

## Schema versions

| Schema | Version | Purpose |
|--------|---------|---------|
| Review bundle | `diagnostic-pack-review-bundle/v1` | Complete current-run state |
| Review input 14B | `diagnostic-pack-review-input-14b/v1` | Compact reviewer-friendly slice |
