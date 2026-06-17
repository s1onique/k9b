# Incident report quality

## Purpose

Preserve incident report/operator worklist quality contracts and fixture taxonomy.

**Distinction:** These are derived read models, not source-of-truth domain roots. Incident is the aggregate root; report/worklist are projections.

## Claim taxonomy

Every claim in the incident report is classified into one of five types:

| Claim Type | Description | Invariant |
|------------|-------------|-----------|
| `observed` | Direct telemetry signal (metric, event count, status) | Must have sourceArtifactRefs |
| `derived` | Deterministic conclusion from evidence fields | Tracks which fields produced the claim |
| `hypothesis` | Plausible cause requiring confirmation | Must have non-empty basis |
| `recommendation` | Operator action suggestion with safety level | Separated from findings |
| `unknown` | Explicitly acknowledged missing evidence | Must NOT be omitted or invented |

## Quality gates

| Gate | Enforced by | What it protects |
|------|------------|------------------|
| observed claims have evidence/provenance | Backend tests | Facts are backed by source artifacts |
| hypothesis claims have non-empty basis | Backend tests | Inferences are explicitly labeled |
| recommendations separated from findings | Backend tests | Actions not mixed with observations |
| unknowns have whyMissing explanation | Backend tests | Missing evidence surfaced, not invented |
| root-cause language only in hypothesis | Backend tests | No ungrounded causal claims in observed |

## Hard invariants

1. **observed claims never contain root-cause language** ("caused by", "root cause", "because of")
2. **hypothesis claims must have non-empty basis** to use root-cause language
3. **missing evidence must surface as unknown, not be omitted or invented**
4. **recommendations are separated from findings** to prevent mixing observation and prescription
5. **No LLM judge added** — deterministic gates are the first defense

## Content quality rules

| Rule | Description | Protected Against |
|------|-------------|-------------------|
| `observed_no_causal_language` | observed claims do not contain causal/root-cause language | Overconfident causal claims in facts |
| `derived_no_causal_language` | derived claims do not contain unsupported causal/root-cause language | Causal language leaking into deterministic conclusions |
| `hypotheses_have_basis` | hypothesis claims must have non-empty basis | Speculative claims without evidence |
| `unknowns_have_why_missing` | unknown claims must have whyMissing explanation | Missing evidence not properly explained |
| `recommendations_separated` | recommendations are separated from findings | Actions mixed with findings |
| `section_headings_concise` | section headings are concise (under 50 characters) | Verbose headings |
| `claim_statements_short` | claim statements are reasonably short (under 200 characters) | Verbose content |
| `no_filler_phrases` | no generic filler phrases in claim statements | Operator-hostile prose |
| `report_has_full_degraded_shape` | report has all sections: facts, derived, inferences, unknowns, recommendations | Incomplete reports |

## Forbidden patterns

### Causal/root-cause language

- "root cause"
- "caused by"
- "because of"
- "is the cause"
- "the cause of"
- "directly caused"
- "responsible for"

### Filler phrases

- "the system has identified"
- "potentially relevant diagnostic indicators"
- "it is recommended that"
- "various issues"
- "multiple issues detected"
- "several problems found"
- "numerous concerns"

## Fixture harness

The `tests/fixtures/incident_report_fixtures.py` module provides deterministic golden fixtures for regression testing.

### Available fixtures

| Builder | Scenario | Key invariant tested |
|---------|----------|---------------------|
| `_fixture_healthy_no_incident()` | No degraded clusters, no enrichment | Honest empty state; no invented concern |
| `_fixture_degraded_single_cluster()` | Degraded + drilldown + missing evidence | Facts, unknowns, actions, real refs |
| `_fixture_stale_provider_enriched_degraded()` | Stale freshness + review enrichment | Stale warning + enrichment in inferences only |
| `_fixture_deterministic_only_no_command()` | Deterministic checks only | `command` stays null |
| `_fixture_queue_with_command()` | Queue item with command | All metadata fields present |

### Test files

- `tests/fixtures/incident_report_quality.py` — deterministic quality helper module
- `tests/unit/test_api_incident_report.py` — backend projection tests
- `frontend/src/__tests__/incident-report-operator-worklist.test.tsx` — frontend rendering tests

## Derived vs source-of-truth boundary

- The incident report and worklist are **derived projections**, not source-of-truth artifacts.
- All facts, inferences, unknowns, and worklist items trace back to existing durable artifacts (`assessments`, `drilldowns`, `reviews`, `external-analysis`, `next-check-plan`).
- The UI/API must not write these projections back to the artifact tree.

## Non-goals

- No LLM judge added
- No production sanitizer behavior
- No full DOM snapshots
- No breaking schema changes (additive payload fields only)
