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

**Status**: Planned (ACT 3)

A matrix mapping:
- Documents → Claims
- Claims → Evidence
- Evidence → Verification status
- Produces coverage reports

### 5. Claim Coverage Reports

Automated reports showing:
- Documents with untraced claims
- Evidence coverage by owner area
- Stale claims requiring review

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

- **Verification:** `scripts/verify_docs_inventory.py`, `scripts/verify_docs_claims_registry.py`
- **Self-tests:** Inline fixtures covering all validation rules
- **CI:** Both verifiers run as part of standard gate
- **Maintenance:** Inventory and registry updated when docs are added, moved, or reclassified

## History

- **2026-06-19** — Initial doctrine: classification system, truth status, claim tracing foundation
- **2026-06-19** — ACT 2: Added claims registry (`docs/claims/docs_claims_registry.csv`) and verifier (`scripts/verify_docs_claims_registry.py`)
