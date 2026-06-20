# Documentation Truthfulness Doctrine

## Purpose

This doctrine establishes the foundation for mechanical documentation truthfulness in the k9b repository. It provides a classification system and verification framework that ensures documentation accurately represents system behavior, security posture, and operational constraints.

## Why Documentation Must Be Classified

Unclassified documentation creates several risks:

1. **Stale information** — Without status tracking, readers cannot distinguish current docs from outdated ones
2. **Claim inflation** — Behavioral or security claims without evidence backing erode trust
3. **Maintenance debt** — Unknown stale docs accumulate and become increasingly difficult to update
4. **Traceability gaps** — Without classification, it's unclear which docs require claim verification

Classification enables:
- Automated discovery of stale content
- Clear ownership and maintenance responsibilities  
- Systematic claim tracing
- Evidence-backed documentation standards

## Document Classification (doc_class)

Every document must have a `doc_class` value from the allowed enum:

| Class | Definition | Examples |
|-------|------------|----------|
| `canonical` | Root project docs that define truth | README.md, docs/data-model.md |
| `reference` | Technical reference documentation | API docs, schema definitions |
| `runbook` | Operational procedures | Deployment guides, debugging walkthroughs |
| `architecture` | Design and structural documentation | Seam maps, system architecture docs |
| `design_proposal` | Proposed but not yet implemented designs | Security design documents |
| `historical` | Docs preserved for historical context | Release notes, old runbooks |
| `superseded` | Replaced by another document | Old architecture docs |
| `generated` | Auto-generated from code/tools | Coverage reports, API schemas |
| `epic_wal` | Epic-level work tracking | Epic breakdowns, WAL documents |
| `external_import` | External documentation brought in | Third-party integration docs |
| `doctrine` | Engineering doctrine documents | Seed rules, governance docs |

## Truth Status (truth_status)

Every document must have a `truth_status` that reflects its current validity:

| Status | Meaning | Required Actions |
|--------|---------|-----------------|
| `current` | Document accurately reflects current behavior | Maintain as needed |
| `historical` | Document preserved for historical reference | Mark clearly, do not update for new behavior |
| `superseded` | Replaced by another document | Add `replacement_doc` or clear `notes` |
| `generated` | Auto-generated, not manually authored | Auto-update in CI |
| `planned` | Document describes future intended state | Track in backlog, not yet implemented |
| `stale` | Document may no longer reflect reality | Review and update or reclassify |
| `unknown` | Truth status has not been determined | Investigate and classify |

### Status Transition Rules

```
unknown → current (verified)
unknown → stale (evidence of age)
unknown → historical (superseded by new docs)

stale → current (updated)
stale → historical (preserved for reference)
stale → superseded (replaced)

planned → current (implemented)
planned → superseded (not implemented)
```

## Claim Tracing Requirements

Some documents contain claims about behavior, security, or operational characteristics that must be verifiable. These are marked with `claim_trace_required=true`.

### When Claim Tracing Is Required

Claim tracing is required when a document asserts:

- **Behavioral claims** — "The system does X when Y occurs"
- **Security properties** — "Data is encrypted at rest", "access requires authentication"
- **Performance characteristics** — "Collection completes within N seconds"
- **Operational constraints** — "The agent never mutates live clusters without approval"

### Evidence Sources for Claim Tracing

Valid evidence sources include:

1. **Tests** — Unit tests, integration tests, property-based tests
2. **Verifiers** — Deterministic verification scripts (`scripts/verify_*.py`)
3. **CI gates** — Automated quality gates in `.github/workflows/`
4. **Manual lab evidence** — Documented test results from controlled environments
5. **Source code** — Direct code references (only for simple, unambiguous claims)

### The Evidence-Backed Claim Rule

> **Current behavior, security, or operator claims must eventually trace to tests/verifiers/CI/manual-lab evidence.**

This does not mean every sentence needs a citation. It means:
- Key behavioral assertions must be verifiable
- Security claims must have test coverage or explicit security review
- Operator-facing claims must match implemented behavior

## Next Planned Layers

This doctrine establishes the foundation. The following layers are planned:

### 3. Claims Registry

**Status**: Implemented (ACT 2)

A structured registry that tracks claims from documentation:

**Registry file**: `docs/claims/docs_claims_registry.csv`

**Registry columns**:
| Field | Description |
|-------|-------------|
| `claim_id` | Stable ID (DOC-CLAIM-0001 format, zero-padded 4 digits) |
| `doc_path` | Source document path |
| `anchor` | Section/anchor identifier within the doc |
| `claim_text` | The specific claim being registered |
| `claim_type` | Classification: behavior, security, operator, data_model, api_contract, ui_contract, ci_gate, architecture, performance, historical, planned |
| `claim_status` | Current status: current, planned, historical, stale, unsupported, superseded |
| `owner_area` | Team/area responsible for maintaining this claim |
| `evidence_required` | Boolean: does this claim need evidence tracing |
| `evidence_status` | Status: pending, linked, not_required, manual_only, unsupported |
| `evidence_ref` | Reference to evidence (test, verifier, etc.) |
| `freshness_policy` | How often to verify: on_change, per_release, manual_review, historical_only, not_applicable |
| `notes` | Additional context |

**What counts as a claim**:
- Behavioral assertions ("The system does X when Y occurs")
- Security properties ("Data is encrypted at rest")
- Operator constraints ("The agent never mutates live clusters")
- API/data-model contracts
- CI gate requirements
- Performance characteristics

**What does NOT need to be registered**:
- Introductory or motivational prose
- General descriptions without specific assertions
- Historical context that is explicitly labeled as such
- Low-value descriptive text

**Claim ID stability**:
- IDs are zero-padded to 4 digits (DOC-CLAIM-0001, DOC-CLAIM-0002, etc.)
- IDs are sorted ascending in the registry
- IDs are never reused or renumbered

**Claim status semantics**:
| Status | Meaning | Evidence expectations |
|--------|---------|----------------------|
| `current` | Claim accurately reflects current behavior | Must have supported evidence_status |
| `planned` | Future intended behavior | Evidence should be pending/manual_only/not_required |
| `historical` | Past behavior preserved for reference | Use historical_only or not_applicable freshness |
| `stale` | May no longer reflect reality | Needs review/update |
| `unsupported` | Evidence is no longer valid | Cannot back current claims |
| `superseded` | Replaced by another claim | Should reference replacement |

**Evidence status semantics**:
| Status | Meaning |
|--------|---------|
| `pending` | Evidence tracing not yet completed |
| `linked` | Evidence reference provided (evidence_ref required) |
| `not_required` | Claim does not need evidence tracing |
| `manual_only` | Manual verification only (evidence_ref required) |
| `unsupported` | Evidence was valid but is no longer available |

**Freshness policy semantics**:
| Policy | When to verify |
|--------|----------------|
| `on_change` | When the source document changes |
| `per_release` | Verify before each release |
| `manual_review` | Periodic human review |
| `historical_only` | Historical claim, no current verification |
| `not_applicable` | Claim does not require verification |

**Next planned layer (ACT 3)**: The full traceability matrix that maps:
- Claims → Evidence (test/verifier/manual)
- Evidence → Verification status
- Generates coverage reports

### 4. Traceability Matrix

**Status**: Implemented (ACT 3)

A matrix mapping:
- Documents → Claims
- Claims → Evidence
- Evidence → Verification status
- Produces coverage reports

**Matrix file**: `docs/claims/docs_claim_traceability_matrix.csv`

**Matrix columns**:
| Field | Description |
|-------|-------------|
| `trace_id` | Stable ID (DOC-TRACE-0001 format, zero-padded 4 digits) |
| `claim_id` | Reference to claim in docs_claims_registry.csv |
| `evidence_kind` | Type: unit_test, integration_test, frontend_test, verifier, ci_gate, source_anchor, manual_lab, historical_record, none |
| `evidence_ref` | Reference identifier for the evidence |
| `evidence_path` | Path to evidence on disk (for test/verifier/source_anchor/historical_record) |
| `evidence_symbol` | Symbol name if applicable (test function, class, etc.) |
| `gate_name` | CI/local gate name (required for ci_gate evidence_kind) |
| `coverage_strength` | Strength: direct, indirect, partial, manual, historical, none |
| `verification_status` | Status: verified, pending, manual_only, historical_only, unsupported |
| `last_verified` | ISO date of last verification |
| `notes` | Additional context |

**Evidence kind semantics**:
| Kind | Description |
|------|-------------|
| `unit_test` | Python unit test |
| `integration_test` | Integration test |
| `frontend_test` | Frontend/test UI test |
| `verifier` | Deterministic verification script |
| `ci_gate` | CI gate step |
| `source_anchor` | Source code reference |
| `manual_lab` | Manual lab evidence |
| `historical_record` | Historical documentation/report |
| `none` | No evidence (placeholder) |

**Coverage strength semantics**:
| Strength | Meaning |
|----------|---------|
| `direct` | Evidence directly proves the claim |
| `indirect` | Evidence supports the claim but doesn't directly prove it |
| `partial` | Evidence covers part of the claim |
| `manual` | Manual verification required |
| `historical` | Historical evidence (cannot prove current behavior) |
| `none` | No coverage |

**Verification status semantics**:
| Status | Meaning |
|--------|---------|
| `verified` | Evidence has been verified by automated test/verifier |
| `pending` | Evidence tracing not yet completed |
| `manual_only` | Manual verification only (requires meaningful notes) |
| `historical_only` | Historical evidence only (cannot prove current behavior) |
| `unsupported` | Evidence was valid but is no longer available (requires meaningful notes) |

**Trace ID stability**:
- IDs are zero-padded to 4 digits (DOC-TRACE-0001, DOC-TRACE-0002, etc.)
- IDs are sorted ascending in the matrix
- IDs are never reused or renumbered
- Format: `DOC-TRACE-{4-digit-number}`

**Linked claims**:
Claims with `evidence_status=linked` in the registry must:
1. Reference at least one valid `trace_id` in `evidence_ref`
2. Have at least one trace row with `verification_status` in: `verified`, `manual_only`, or `historical_only`
3. NOT be current claims linked only to `historical_only` evidence (historical evidence cannot prove current behavior)

**Pending evidence**:
Claims may remain pending when:
- Evidence is being developed
- Claim is stale and needs review
- Manual verification is required

**Historical evidence rules**:
- Historical claims may use `historical_record` evidence_kind with `historical` coverage_strength
- Historical evidence is labeled with `verification_status=historical_only`
- Current claims MUST NOT be linked only to historical evidence
- Historical evidence proves past behavior only, not current behavior

**Verifier**: `scripts/verify_docs_claim_traceability.py`
- Validates matrix structure and schema
- Validates cross-file linkage to claims registry
- Validates evidence references and paths
- Validates semantic combinations
- Produces coverage reports

### 5. Claim Coverage Reports

Automated reports showing:
- Documents with untraced claims
- Evidence coverage by owner area
- Stale claims requiring review

### 6. Claim Candidate Scanner (ACT 4)

**Status**: Implemented

A deterministic claim-candidate scanner that reviews the full documentation corpus and makes under-registration mechanically visible.

**Scanner file**: `scripts/scan_docs_claim_candidates.py`

**Coverage verifier**: `scripts/verify_docs_claim_candidate_coverage.py`

**Generated output**: `docs/claims/generated_claim_candidates.csv`

**What the scanner does**:
1. Scans markdown docs using regex patterns for 8 claim types:
   - `normative` — MUST/SHOULD/SHALL statements
   - `security` — authentication, RBAC, mutation, injection
   - `api_contract` — endpoints, routes, request/response
   - `config` — environment variables, flags, defaults
   - `data_model` — lifecycle, states, schemas
   - `source_of_truth` — immutable artifacts, durable records
   - `ci_gate` — verify scripts, CI thresholds, coverage
   - `performance` — timeouts, intervals, thresholds

2. Generates deterministic candidate IDs using SHA1 hash of doc_path|line_number|text|claim_type (line_number ensures uniqueness per row)

3. Assigns severity based on claim type (high/medium/low)

4. Sets initial registration status based on doc classification

**Severity by type**:
| Type | Severity |
|------|----------|
| security | high |
| source_of_truth | high |
| ci_gate | medium |
| normative | medium |
| api_contract | medium |
| data_model | medium |
| config | low |
| performance | low |

**Registration status**:
| Status | When assigned |
|--------|---------------|
| `unregistered` | Current docs with candidate claims |
| `ignored_historical` | Historical docs |
| `ignored_stale` | Stale/unknown docs |
| `ignored_by_policy` | Generated docs |

**Coverage gate policy** (ADVISORY ROLLOUT):
- Scanner/verifier integrity problems → **FAIL** (invalid CSV, invalid enum values)
- HIGH severity + unregistered + current + trace_required=true → **WARN** (advisory only)
- HIGH severity + unregistered + current + trace_required=false → **WARN** (advisory only)
- Stale/historical candidates → reported as INFO, no gate impact
- Duplicate candidate IDs → NOT EXPECTED (IDs are unique per row via line_number in hash)

The advisory policy makes under-registration visible without blocking the gate. Once the claims registry is expanded and candidates are registered, this can be converted to hard enforcement.

**Gate wiring** (verify mode - does not mutate):
```
docs-claim-candidates  → scan_docs_claim_candidates.py
docs-claim-coverage    → verify_docs_claim_candidate_coverage.py
```

**Manual regeneration** (when needed):
```bash
python scripts/scan_docs_claim_candidates.py --update  # regenerate CSV
```

**Self-tests**:
- Scanner: 10 test cases covering type detection, severity, ID generation
- Coverage verifier: 8 test cases covering all gate policies

**Using the scanner**:
```bash
# Scan docs and generate candidates CSV
python scripts/scan_docs_claim_candidates.py --update

# Run coverage verification
python scripts/verify_docs_claim_candidate_coverage.py

# Run self-tests
python scripts/scan_docs_claim_candidates.py --self-test
python scripts/verify_docs_claim_candidate_coverage.py --self-test
```

**Integration with registry**:
- Scanner output is the input for expanding the claims registry
- Each registered claim should have a corresponding entry in `docs_claims_registry.csv`
- Unregistered candidates flagged by coverage verifier should be reviewed for registry addition

### 7. Candidate-to-Registry Curation Policy (ACT 2.5)

**Status**: Implemented

Claims in `docs_claims_registry.csv` that were curated from generated candidates must link back to their source candidates.

**Registry fields for candidate linkage**:

| Field | Description |
|-------|-------------|
| `candidate_ids` | Semicolon-separated `DOC-CAND-xxx` IDs from `generated_claim_candidates.csv` |
| `registered_claim_id` | Back-link in candidates CSV to the registry claim |

**Curated claims must have**:
1. `candidate_ids` field populated with at least one matching `DOC-CAND-xxx` ID
2. Candidate IDs validated against `generated_claim_candidates.csv` for existence
3. `generated_claim_candidates.csv` updated with `registered_claim_id` back-link

**Curator workflow**:
1. Run scanner: `python scripts/scan_docs_claim_candidates.py --update`
2. Review high-severity candidates in `generated_claim_candidates.csv`
3. Curate selected candidates into `docs_claims_registry.csv`
4. Populate `candidate_ids` field with matching `DOC-CAND-xxx` IDs
5. Update `generated_claim_candidates.csv` with `registered_claim_id` mappings
6. Regenerate traceability matrix rows for new claims

**Validation**:
- `verify_docs_claims_registry.py` validates `candidate_ids` format (DOC-CAND-12-char-hex)
- `verify_docs_claim_candidate_coverage.py` reports unregistered high-severity candidates
- Linked candidates are recognized as "registered" status

**Preserving original claims**:
- Original claims DOC-CLAIM-0001 to DOC-CLAIM-0018 are preserved
- Their traceability rows (DOC-TRACE-0001 to DOC-TRACE-0018) are preserved with verified evidence
- New claims start at DOC-CLAIM-0019

## Inventory Maintenance

The docs inventory (`docs/docs_inventory.csv`) is the source of truth for document classification. It is verified by `scripts/verify_docs_inventory.py` as part of the standard gate.

### Inventory Fields

| Field | Description |
|-------|-------------|
| `doc_path` | Relative path from repo root |
| `doc_class` | Classification from allowed enum |
| `truth_status` | Current validity status |
| `owner_area` | Team/area responsible for maintenance |
| `generated_by` | Tool/script that generates (for generated docs) |
| `replacement_doc` | Document that supersedes this (for superseded docs) |
| `claim_trace_required` | Whether this doc has verifiable claims |
| `notes` | Additional context |

## Gate Behavior

The docs inventory verification runs as part of the standard gate:

```
python scripts/verify_docs_inventory.py
```

**Hard-gated:** The verifier runs as a blocking step in the standard gate. Since the initial inventory is complete and verified, this is a hard gate from the start.

**Advisory path (if needed):** If the inventory needs stabilization during future updates, the script can be made advisory by wrapping it with `|| true`. The PATH to hard-gating is only needed if the verifier were initially advisory.

## Non-Goals

This doctrine does not require:
- Updating every stale document immediately
- Building the full claims registry in this ACT
- Building the full traceability matrix in this ACT
- Inventing requirements for every sentence in every doc
- Moving large numbers of docs without clear justification

## Relationship to Other Doctrines

This doctrine complements:

- **Seed Rules** — General operational requirements
- **LLM-Friendly Files** — File size and structure constraints  
- **Path Security Doctrine** — Security claim verification patterns
- **Constitution** — Foundational governance

## Enforcement

- **Verification:** `scripts/verify_docs_inventory.py`, `scripts/verify_docs_claims_registry.py`, `scripts/verify_docs_claim_traceability.py`
- **Self-tests:** Inline fixtures covering all validation rules
- **CI:** All three verifiers run as part of standard gate
- **Maintenance:** Inventory, registry, and traceability matrix updated when docs are added, moved, or reclassified

> **Note**: Section 8 (Candidate Disposition Ledger) has been moved to [documentation-truthfulness-dispositions.md](documentation-truthfulness-dispositions.md) to maintain LLM-friendly file size limits.

## Semantic Disposition Diffs

When CSV-safe tooling reserializes claim disposition shards, reviewers must rely on semantic CSV diff output rather than line-count churn. Use:

```bash
python scripts/diff_docs_claim_dispositions.py --base-ref HEAD~1 --target-ref HEAD
```

The report must be included in close reports for tranche ACTs when shard diffs are broad.

The tool compares parsed disposition rows by `candidate_id` across git refs, reports changed fields, validates stable row sets and disposition counts, and emits optional deterministic JSON. Self-tests verify the tool's correctness against known fixtures.

## Candidate Backlog Reporting

After completing long-tail review tranches (ACT 5.0, ACT 5.2, etc.), use the deterministic backlog reporter to plan future tranches:

```bash
# Summary with top 100 recommended candidates
python scripts/run_backlog_report.py --top 100

# Export to JSON for structured analysis
python scripts/run_backlog_report.py --json /tmp/backlog.json

# Export to TSV for future tranche selection
python scripts/run_backlog_report.py --tsv /tmp/tranche-candidates.tsv

# Include already-reviewed candidates in output
python scripts/run_backlog_report.py --include-reviewed

# Filter by disposition or doc path
python scripts/run_backlog_report.py --disposition ignored_by_policy
python scripts/run_backlog_report.py --doc docs/security/
```

The report ranks remaining unreviewed candidates by risk score, which considers:
- Generic ignored notes (+20)
- High-value doc paths (+10)
- Normative candidate text (+8)
- No ACT review marker (+4)
- ACT 5.0/5.2 review (deprioritized: -20)

Self-tests ensure scoring determinism:

```bash
python scripts/run_backlog_report.py --self-test
```

The self-test is wired into the standard gate via `docs-claim-candidate-backlog-report-self-test`.

### Stop/continue planning

The `--planning` flag enables deterministic stop/continue assessment:

```bash
# Human-readable planning output
python scripts/run_backlog_report.py --planning --top 100

# JSON/TSV with planning block
python scripts/run_backlog_report.py --planning --json /tmp/backlog-planning.json --tsv /tmp/backlog-planning.tsv --top 100
```

The planning section groups remaining candidates into priority bands:

| Band | Score range | Description |
|------|-------------|-------------|
| P0 | >= 42 | Highest priority: generic ignored + high-value doc + normative + no marker |
| P1 | 34-41 | High priority: generic ignored + high-value or generic + normative |
| P2 | 24-33 | Medium priority: generic ignored or weak covered with lower-risk context |
| P3 | 1-23 | Low priority: low-confidence remaining backlog |
| P4 | <= 0 | Deprioritized: reviewed, stale, historical, or low-risk |

Recommendation rules:

| Action | Condition |
|--------|-----------|
| `continue_large_tranche` | P0+P1 >= 100 |
| `continue_small_targeted_tranche` | P0+P1 >= 25 and < 100, OR P0+P1 < 25 with nonzero weak-covered or stale/high-value entries |
| `pause_manual_tranches` | P0+P1 < 25 AND weak_covered_count == 0 AND stale_or_historical_high_value_count == 0 |
| `blocked_or_inconclusive` | Unable to determine recommendation |

TSV output includes `priority_band` column for future tranche selection.

### Review class calibration

The backlog reporter classifies candidates as one of the following review classes:

| Class | Description |
|-------|-------------|
| `claim_candidate` | Strong normative signal (MUST, required, invariant, etc.), no structural/non-normative markers |
| `structural_fragment` | Table cells, headings, schema fields, metadata annotations |
| `non_normative_prose` | Descriptive prose, design notes, examples, non-normative requirement phrasing |
| `covered_or_registered` | Already covered by existing claim or registered |
| `stale_or_historical` | Stale or historical disposition or doc |
| `reviewed_low_value` | Has ACT review marker and remains ignored_by_policy |
| `unknown` | Cannot determine classification |

Scoring is calibrated by review class:

| Class | Score Adjustment |
|-------|-----------------|
| `claim_candidate` | +20 |
| `structural_fragment` | -30 |
| `non_normative_prose` | -25 |
| `reviewed_low_value` | -40 |
| `stale_or_historical` | -30 |
| `covered_or_registered` | -20 |

Planning output reports a `planning_caveat` indicating the composition of high-priority work:

| Caveat | Meaning |
|--------|---------|
| `claim-candidate-heavy` | P0+P1 dominated by claim_candidate rows |
| `cleanup-heavy` | P0+P1 dominated by structural/non-normative rows |
| `mixed` | Both types present in significant numbers |
| `low-backlog` | Very few high-priority entries |
| `inconclusive` | Cannot determine |

A `cleanup-heavy` recommendation means the next tranche should be treated as reason/note burn-down, not new claim discovery.

TSV output includes `review_class` and `review_class_reasons` columns for future tranche selection.

### Calibrated claim-discovery stop decision

ACT 5.8 added first-class `--review-class` and `--priority-band` filters to the backlog reporter. The calibrated reporter can now directly produce targeted worklists.

#### Live calibrated filter results

| Filter | Total | P0+P1 | Recommendation |
|--------|-------|-------|----------------|
| `--review-class claim_candidate` | 373 | 369 | `continue_large_tranche` |
| `--review-class structural_fragment` | 99 | 0 | `pause_manual_tranches` |
| `--review-class non_normative_prose` | 852 | 0 | `pause_manual_tranches` |
| `--review-class stale_or_historical` | 2227 | 0 | `continue_small_targeted_tranche` (for stale/high-value) |

#### Decision

**Claim discovery remains open.** The calibrated `claim_candidate` filter returned 373 candidates with 369 in P0+P1. Future claim-discovery tranches must use:

```bash
python scripts/run_backlog_report.py --review-class claim_candidate --planning --top 100
```

**Cleanup work is separate.** Remaining backlog is primarily non-normative prose (852), stale/historical (2227), and structural fragments (99). These are maintenance/cleanup classes:

```bash
# Structural fragment burn-down (low priority, P4)
python scripts/run_backlog_report.py --review-class structural_fragment --top 100

# Non-normative prose burn-down (low priority, P3+P4)
python scripts/run_backlog_report.py --review-class non_normative_prose --top 100

# Stale/historical maintenance (1336 in high-value docs)
python scripts/run_backlog_report.py --review-class stale_or_historical --planning --top 100
```

**Stop rule:** If the calibrated `claim_candidate` filter ever returns zero candidates, manual claim-discovery tranches are paused until new candidates are generated.

## History

- **2026-06-20** — ACT 5.11: Tightened `claim_candidate` classification by splitting claim signals into high-confidence and broad categories. Broad normative words ("must", "required", "never", "only") no longer promote generic low-value prose by themselves. A candidate now requires claim-shaped context (system subjects, action terms) and must not match exclusion markers (meta-documentation, policy/process, design/future, schema/table, example, CI/gate docs). Post-repair calibrated report: claim_candidate total reduced from 318 to ~82 P0 candidates. Next recommended ACT: review remaining claim candidates or pause for backlog consolidation.
- **2026-06-20** — ACT 5.10: **BLOCKED** - Discrepancy found between ACT 5.9 context and live state. ACT 5.9 context claimed "calibrated P0/P1 claim-candidate backlog is now empty" with "4 P2 candidates remaining." Live reporter shows 318 claim_candidate candidates (314 P0/P1 + 4 P2). Root cause: (1) The bugfix commit f9d2f5d changed classification order (claim_candidate now checked BEFORE non_normative_prose), (2) STRONG_NORMATIVE_SIGNALS includes common words ("must", "required", "never", "only", etc.), (3) Many low-value prose fragments with these words are now classified as claim_candidate, (4) ACT 5.9 reviewed only 100 of 373+ candidates, leaving residual backlog unreviewed. ACT 5.10 is blocked pending classification fix and full calibrated backlog validation. See: `python scripts/run_backlog_report.py --review-class claim_candidate --planning --top 50` for live state.
- **2026-06-20** — ACT 5.8: Added `--review-class` and `--priority-band` filters to the backlog reporter with validation and deterministic JSON filters block. Formal stop/continue decision recorded: claim discovery remains open (373 claim_candidates, 369 in P0+P1). Cleanup classes (structural_fragment, non_normative_prose, stale_or_historical) are separate work.
- **2026-06-20** — ACT 5.7: Calibrated claim candidate backlog scoring with review classes (claim_candidate, structural_fragment, non_normative_prose, etc.) and planning caveats (cleanup-heavy, claim-candidate-heavy, mixed). Structural/non-normative false positives now receive score penalties, preventing them from silently dominating P0 as claim-worthy work.
- **2026-06-20** — ACT 5.3: Added claim candidate backlog reporter (`scripts/report_docs_claim_candidate_backlog/` package) with risk scoring, self-tests, wired into verify_all.sh gate
- **2026-06-20** — ACT 5.3b: Split backlog reporter into LLM-friendly modules (loader, model, report, selftest, __main__, __init__)
- **2026-06-20** — ACT 5.1: Added semantic disposition diff reporter (`scripts/diff_docs_claim_dispositions.py`) with self-tests, wired into verify_all.sh gate
- **2026-06-19** — Initial doctrine: classification system, truth status, claim tracing foundation
- **2026-06-19** — ACT 2: Added claims registry (`docs/claims/docs_claims_registry.csv`) and verifier (`scripts/verify_docs_claims_registry.py`)
- **2026-06-19** — ACT 3: Added traceability matrix (`docs/claims/docs_claim_traceability_matrix.csv`), verifier (`scripts/verify_docs_claim_traceability.py`), and evidence linkage for claims
- **2026-06-19** — ACT 4: Added claim candidate scanner (`scripts/scan_docs_claim_candidates.py`) and coverage verifier (`scripts/verify_docs_claim_candidate_coverage.py`), wired into verify_all.sh gate
- **2026-06-19** — ACT 2.8: Added candidate disposition ledger (`docs/claims/docs_claim_dispositions-shard-*.csv`), verifier (`scripts/verify_docs_claim_candidate_dispositions.py`), and generator (`scripts/generate_disposition_ledger.py`), wired into local and CI gates
