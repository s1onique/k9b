# Incident Report Schema Specification

## Epic: Canonical Incident Report Contract

**Purpose:** Define the first-class incident report contract for k9b beta so operators can understand an active situation quickly without stitching together multiple detailed panels.

**Status:** Implemented (see `src/k8s_diag_agent/ui/api_incident_report.py`, `tests/unit/test_api_incident_report.py`, `tests/fixtures/incident_report_fixtures.py`)

---

## 1. IncidentReportView Schema Definition

The canonical incident report contract is defined as `IncidentReportPayload` (Python TypedDict) and `IncidentReportPayload` (TypeScript) in the respective type definition files.

### Schema Structure

```python
# src/k8s_diag_agent/ui/api_payloads.py

class IncidentReportPayload(TypedDict, total=False):
    """Canonical incident report projection for a selected health run.

    Derived from existing artifacts. Not a new immutable source of truth.

    Canonical structured claims live in facts, derived, inferences,
    recommendations, and unknowns. recommendedActions is legacy display
    compatibility only.
    """

    title: str
    status: str  # "healthy" | "degraded"
    affectedScope: str | None  # comma-separated degraded cluster labels
    impact: str | None
    evidenceSummary: str | None
    facts: list[IncidentReportFactPayload]       # observed claims
    derived: list[IncidentReportDerivedPayload]  # derived claims
    inferences: list[IncidentReportInferencePayload]  # hypothesis claims
    recommendations: list[IncidentReportRecommendationPayload]
    unknowns: list[IncidentReportUnknownPayload]
    staleEvidenceWarnings: list[str]
    confidence: str | None
    freshness: FreshnessPayload | None
    recommendedActions: list[str]  # Legacy display compatibility only
    sourceArtifactRefs: list[ArtifactLink]
```

### Claim Type Taxonomy

Every claim in the incident report is classified into one of five types:

| Claim Type | Description | Invariant |
|------------|-------------|-----------|
| `observed` | Direct telemetry signal (metric, event count, status) | Must have sourceArtifactRefs |
| `derived` | Deterministic conclusion from evidence fields | Tracks which fields produced the claim |
| `hypothesis` | Plausible cause requiring confirmation | Must have non-empty basis |
| `recommendation` | Operator action suggestion with safety level | Separated from findings |
| `unknown` | Explicitly acknowledged missing evidence | Must NOT be omitted or invented |

### Payload Type Definitions

```python
class ClaimType = Literal["observed", "derived", "hypothesis", "recommendation", "unknown"]

class IncidentReportFactPayload(TypedDict, total=False):
    """observed: Direct telemetry signal with evidence/provenance"""
    claimType: ClaimType  # Literal["observed"]
    statement: str
    sourceArtifactRefs: list[ArtifactLink]
    confidence: str

class IncidentReportDerivedPayload(TypedDict, total=False):
    """derived: Deterministic conclusion from evidence fields"""
    claimType: ClaimType  # Literal["derived"]
    statement: str
    sourceFields: list[str]  # Deterministic fields that produced this claim
    sourceArtifactRefs: list[ArtifactLink]
    confidence: str

class IncidentReportInferencePayload(TypedDict, total=False):
    """hypothesis: Plausible cause requiring confirmation"""
    claimType: ClaimType  # Literal["hypothesis"]
    statement: str
    basis: list[str]
    confidence: str
    sourceArtifactRefs: list[ArtifactLink]

class IncidentReportRecommendationPayload(TypedDict, total=False):
    """recommendation: Operator action suggestion with safety level"""
    claimType: ClaimType  # Literal["recommendation"]
    statement: str
    safetyLevel: str
    sourceArtifactRefs: list[ArtifactLink]

class IncidentReportUnknownPayload(TypedDict, total=False):
    """unknown: Explicitly acknowledged missing evidence"""
    claimType: ClaimType  # Literal["unknown"]
    statement: str
    whyMissing: str | None
    sourceArtifactRefs: list[ArtifactLink]
```

---

## 2. Field-to-Artifact Mapping

Each field in `IncidentReportPayload` maps to existing source artifacts:

| IncidentReport Field | Source Artifact | Mapping Logic |
|----------------------|------------------|---------------|
| `title` | Computed | "Degraded health detected in N cluster(s)" when `fleet_status.degraded_clusters` non-empty; "No degraded clusters detected" otherwise |
| `status` | `fleet_status` | "degraded" if any clusters in `degraded_clusters`; "healthy" otherwise |
| `affectedScope` | `fleet_status.degraded_clusters` | Comma-separated list of cluster labels |
| `facts[].statement` | `drilldowns/latest_findings` | Trigger reasons, warning events, non-running pods counts |
| `facts[].sourceArtifactRefs` | `drilldowns/*` artifact_path | Points to drilldown artifact |
| `derived[].statement` | `assessments/latest_assessment.health_rating` | "Cluster {name} health rating is {rating}." |
| `derived[].sourceFields` | `assessments/latest_assessment` | ["health_rating"] |
| `derived[].sourceArtifactRefs` | `assessments/*` artifact_path | Points to assessment artifact |
| `inferences[].statement` | `assessments/latest_assessment.hypotheses` | Hypothesis descriptions (sanitized) |
| `inferences[].basis` | `assessments/latest_assessment.hypotheses.probable_layer` | Layer name as basis |
| `inferences[].statement` (provider) | `run.review_enrichment.summary` | Provider-assisted summary (when present) |
| `inferences[].basis` (provider) | ["review-enrichment"] | Fixed basis for provider content |
| `recommendations[].statement` | `assessments/latest_assessment.recommended_action.description` | Action description (sanitized) |
| `recommendations[].safetyLevel` | `assessments/latest_assessment.recommended_action.safety_level` | Safety level from assessment |
| `unknowns[].statement` | `assessments/latest_assessment.missing_evidence` | "Missing evidence: {item}" |
| `unknowns[].whyMissing` | Computed | "Not collected in this run" |
| `staleEvidenceWarnings` | `freshness.status` | "Run freshness is {status}; some evidence may be stale." when status in ("delayed", "stale") |
| `freshness` | `freshness` (API parameter) | Passed directly from API caller |
| `sourceArtifactRefs` | Multiple | Deduplicated refs from assessment, drilldown, review_enrichment artifacts |
| `recommendedActions` | `assessments/latest_assessment.recommended_action.description` | Legacy string list for backward compatibility |

---

## 3. Truthfulness Rules for Synthesis

The builders enforce the following truthfulness rules:

### Rule 1: Facts are deterministic/evidence-backed only

**What qualifies as fact:**
- Assessment health rating → goes to `derived[]`, not `facts[]`
- Drilldown trigger reasons, warning event counts, non-running pod counts → `facts[]`
- These are directly observable telemetry signals

**What does NOT qualify as fact:**
- Provider-assisted review enrichment summaries → `inferences[]` only
- Hypothesis descriptions → `inferences[]` only
- Missing evidence → `unknowns[]` only

### Rule 2: Inferences are explicitly labeled as inferences

**Provider-assisted content:**
- `review_enrichment.summary` appears in `inferences[]` with `basis: ["review-enrichment"]`
- Never appears in `facts[]` regardless of content

**Assessment hypotheses:**
- Appear in `inferences[]` with `basis: [hypothesis.probable_layer]`
- Have explicit confidence level from assessment

### Rule 3: Unknowns/missing evidence are explicit

**Missing evidence handling:**
- Any `missing_evidence` item from assessment becomes `IncidentReportUnknownPayload`
- Each unknown includes `whyMissing` explanation ("Not collected in this run")
- Unknowns are never omitted or converted to confident statements

### Rule 4: Stale evidence is flagged when supported

**Freshness-based warnings:**
- When `freshness.status` is "delayed" or "stale", `staleEvidenceWarnings` is populated
- Warning text: "Run freshness is {status}; some evidence may be stale."
- When freshness is "fresh", no warnings are generated

### Rule 5: Provider-assisted content is never classified as deterministic fact

**Critical invariant:** Review enrichment is always `inferences[]`, never `facts[]`

**Enforced by tests:**
- `test_provider_content_is_inference_not_fact`
- `test_enrichment_in_inferences_only_not_facts`
- `GoldenFixtureStaleProviderEnrichedDegradedTests`

### Rule 6: Source artifact refs are preserved where available

**Provenance rules:**
- Each claim includes `sourceArtifactRefs` pointing to originating artifact
- Paths are real (from artifact_path fields), never "unknown"
- Deduplication prevents duplicate paths in top-level `sourceArtifactRefs`

### Rule 7: Internal context markers are sanitized

**Security sanitization:**
- Cluster labels with internal markers ("in-cluster", "in_cluster") are handled
- Operator-facing text is sanitized via `sanitize_operator_text()`
- Derived statements avoid "Cluster in-cluster" or "Cluster the cluster" phrasing

---

## 4. Example Payloads

### Example 1: Clearly Degraded Incident

**Scenario:** Single cluster with CrashLoopBackOff, 5 warning events, 2 non-running pods, missing events evidence, no provider enrichment.

```json
{
  "title": "Degraded health detected in 1 cluster(s)",
  "status": "degraded",
  "affectedScope": "cluster-degraded",
  "facts": [
    {
      "claimType": "observed",
      "statement": "Trigger reasons: non_running_pods, warning_event_threshold",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/cluster-degraded.json"}],
      "confidence": "high"
    },
    {
      "claimType": "observed",
      "statement": "Warning events observed: 5",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/cluster-degraded.json"}],
      "confidence": "high"
    },
    {
      "claimType": "observed",
      "statement": "Non-running pods observed: 2",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/cluster-degraded.json"}],
      "confidence": "high"
    }
  ],
  "derived": [
    {
      "claimType": "derived",
      "statement": "Cluster cluster-degraded health rating is degraded.",
      "sourceFields": ["health_rating"],
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-degraded.json"}],
      "confidence": "high"
    }
  ],
  "inferences": [
    {
      "claimType": "hypothesis",
      "statement": "Application misconfiguration causes repeated crashes",
      "basis": ["workload"],
      "confidence": "medium",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-degraded.json"}]
    }
  ],
  "recommendations": [
    {
      "claimType": "recommendation",
      "statement": "Investigate pod events and logs for my-pod",
      "safetyLevel": "low-risk",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-degraded.json"}]
    }
  ],
  "unknowns": [
    {
      "claimType": "unknown",
      "statement": "Missing evidence: events",
      "whyMissing": "Not collected in this run",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-degraded.json"}]
    }
  ],
  "staleEvidenceWarnings": [],
  "confidence": "medium",
  "freshness": {"ageSeconds": 120, "expectedIntervalSeconds": 300, "status": "fresh"},
  "recommendedActions": ["Investigate pod events and logs for my-pod"],
  "sourceArtifactRefs": [
    {"label": "Assessment", "path": "assessments/cluster-degraded.json"},
    {"label": "Drilldown", "path": "drilldowns/cluster-degraded.json"},
    {"label": "Snapshot", "path": "snapshots/cluster-degraded.json"}
  ]
}
```

### Example 2: Ambiguous Incident with Unknowns

**Scenario:** Cluster with degraded health but high missing evidence count, multiple hypotheses, no clear trigger pattern, moderate confidence.

```json
{
  "title": "Degraded health detected in 1 cluster(s)",
  "status": "degraded",
  "affectedScope": "cluster-ambiguous",
  "facts": [
    {
      "claimType": "observed",
      "statement": "Trigger reasons: warning_event_threshold",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/cluster-ambiguous.json"}],
      "confidence": "high"
    },
    {
      "claimType": "observed",
      "statement": "Warning events observed: 12",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/cluster-ambiguous.json"}],
      "confidence": "high"
    }
  ],
  "derived": [
    {
      "claimType": "derived",
      "statement": "Cluster cluster-ambiguous health rating is degraded.",
      "sourceFields": ["health_rating"],
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-ambiguous.json"}],
      "confidence": "medium"
    }
  ],
  "inferences": [
    {
      "claimType": "hypothesis",
      "statement": "Network connectivity issues between pods and API server",
      "basis": ["network"],
      "confidence": "low",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-ambiguous.json"}]
    },
    {
      "claimType": "hypothesis",
      "statement": "Resource pressure causing throttling",
      "basis": ["infrastructure"],
      "confidence": "medium",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-ambiguous.json"}]
    },
    {
      "claimType": "hypothesis",
      "statement": "High ingress latency detected; consider scaling the gateway.",
      "basis": ["review-enrichment"],
      "confidence": "medium",
      "sourceArtifactRefs": [{"label": "Review Enrichment", "path": "external-analysis/run-amb-review-enrichment.json"}]
    }
  ],
  "recommendations": [
    {
      "claimType": "recommendation",
      "statement": "Collect network diagnostic evidence",
      "safetyLevel": "low-risk",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-ambiguous.json"}]
    }
  ],
  "unknowns": [
    {
      "claimType": "unknown",
      "statement": "Missing evidence: pod metrics",
      "whyMissing": "Metrics collector not responding",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-ambiguous.json"}]
    },
    {
      "claimType": "unknown",
      "statement": "Missing evidence: node conditions",
      "whyMissing": "Node metrics unavailable",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-ambiguous.json"}]
    },
    {
      "claimType": "unknown",
      "statement": "Missing evidence: CNI logs",
      "whyMissing": "Not collected in this run",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-ambiguous.json"}]
    }
  ],
  "staleEvidenceWarnings": [],
  "confidence": "low",
  "freshness": {"ageSeconds": 450, "expectedIntervalSeconds": 300, "status": "delayed"},
  "recommendedActions": ["Collect network diagnostic evidence"],
  "sourceArtifactRefs": [
    {"label": "Assessment", "path": "assessments/cluster-ambiguous.json"},
    {"label": "Drilldown", "path": "drilldowns/cluster-ambiguous.json"},
    {"label": "Review Enrichment", "path": "external-analysis/run-amb-review-enrichment.json"}
  ]
}
```

### Example 3: Stale-Evidence Incident

**Scenario:** Degraded cluster with stale run freshness (scheduler missed runs), provider-assisted review enrichment present, multiple issues detected.

```json
{
  "title": "Degraded health detected in 1 cluster(s)",
  "status": "degraded",
  "affectedScope": "cluster-stale",
  "facts": [
    {
      "claimType": "observed",
      "statement": "Trigger reasons: non_running_pods, warning_event_threshold",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/cluster-stale.json"}],
      "confidence": "high"
    },
    {
      "claimType": "observed",
      "statement": "Warning events observed: 8",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/cluster-stale.json"}],
      "confidence": "high"
    },
    {
      "claimType": "observed",
      "statement": "Non-running pods observed: 3",
      "sourceArtifactRefs": [{"label": "Drilldown", "path": "drilldowns/cluster-stale.json"}],
      "confidence": "high"
    }
  ],
  "derived": [
    {
      "claimType": "derived",
      "statement": "Cluster cluster-stale health rating is degraded.",
      "sourceFields": ["health_rating"],
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-stale.json"}],
      "confidence": "high"
    }
  ],
  "inferences": [
    {
      "claimType": "hypothesis",
      "statement": "Storage subsystem showing degraded performance",
      "basis": ["storage"],
      "confidence": "medium",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-stale.json"}]
    },
    {
      "claimType": "hypothesis",
      "statement": "High ingress latency detected; consider scaling the gateway.",
      "basis": ["review-enrichment"],
      "confidence": "medium",
      "sourceArtifactRefs": [{"label": "Review Enrichment", "path": "external-analysis/run-stale-review-enrichment-llamacpp.json"}]
    }
  ],
  "recommendations": [
    {
      "claimType": "recommendation",
      "statement": "Investigate storage subsystem health",
      "safetyLevel": "low-risk",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-stale.json"}]
    }
  ],
  "unknowns": [
    {
      "claimType": "unknown",
      "statement": "Missing evidence: storage metrics",
      "whyMissing": "Not collected in this run",
      "sourceArtifactRefs": [{"label": "Assessment", "path": "assessments/cluster-stale.json"}]
    }
  ],
  "staleEvidenceWarnings": [
    "Run freshness is stale; some evidence may be stale."
  ],
  "confidence": "medium",
  "freshness": {"ageSeconds": 3600, "expectedIntervalSeconds": 300, "status": "stale"},
  "recommendedActions": ["Investigate storage subsystem health"],
  "sourceArtifactRefs": [
    {"label": "Assessment", "path": "assessments/cluster-stale.json"},
    {"label": "Drilldown", "path": "drilldowns/cluster-stale.json"},
    {"label": "Review Enrichment", "path": "external-analysis/run-stale-review-enrichment-llamacpp.json"}
  ]
}
```

---

## 5. Backend/API Insertion Point

**Location:** `src/k8s_diag_agent/ui/api_incident_report.py`

**Entry points:**
- `_build_incident_report_payload(context, freshness)` - builds incident report projection
- `_build_operator_worklist_payload(context)` - builds operator worklist projection

**Composition root:** `src/k8s_diag_agent/ui/api.py::build_run_payload()`

```python
# src/k8s_diag_agent/ui/api.py (simplified)

def build_run_payload(context: UIIndexContext) -> RunPayload:
    # ... other composition ...
    
    # Thread incident report projection
    incident_report = _build_incident_report_payload(context, _build_freshness_payload(context))
    
    # Thread operator worklist projection  
    operator_worklist = _build_operator_worklist_payload(context)
    
    return {
        # ... other fields ...
        "incidentReport": incident_report,
        "operatorWorklist": operator_worklist,
    }
```

**Design rationale:**
- No new persistence layer introduced
- Projections are derived on-demand from existing artifacts
- UI index (`runs/health/ui-index.json`) is the source of truth
- Builders are stateless and deterministic
- `build_run_payload` threads both projections into the run payload

---

## 6. Regression Tests for the Contract

### Test Coverage

**Location:** `tests/unit/test_api_incident_report.py`

| Test Class | Coverage |
|------------|----------|
| `IncidentReportPayloadTests` | Basic payload construction, status derivation, source refs |
| `OperatorWorklistPayloadTests` | Worklist items, command metadata, counts |
| `TruthfulnessContractTests` | Cross-cutting truthfulness (provider content never in facts) |
| `ClaimTaxonomyTests` | Claim type invariants, root-cause language guards |
| `GoldenFixtureHealthyNoIncidentTests` | Healthy run honest empty state |
| `GoldenFixtureDegradedSingleClusterTests` | Degraded run with all sections populated |
| `GoldenFixtureStaleProviderEnrichedDegradedTests` | Stale freshness + provider enrichment invariants |
| `GoldenFixtureDeterministicOnlyNoCommandTests` | Deterministic checks with null command |
| `GoldenFixtureQueueWithCommandTests` | Queue items with executable command |
| `ContentQualityTests` | Quality rules (causal language, basis, whyMissing) |
| `ContentQualityNegativeTests` | Quality helper rejects bad input |
| `ContentQualityReportStructureTests` | Report structure completeness |
| `ClusterLabelSanitizationRegressionTests` | Internal marker sanitization |

### Hard Invariants Enforced by Tests

1. **Provider-assisted content never in facts** - `TruthfulnessContractTests::test_facts_never_include_review_enrichment`
2. **Unknowns/missing evidence must be explicit** - `ClaimTaxonomyTests::test_unknown_claims_have_why_missing`
3. **Stale evidence must create stale warnings** - `IncidentReportPayloadTests::test_stale_evidence_warning_when_freshness_stale`
4. **No fake artifact paths** - `GoldenFixtureDegradedSingleClusterTests::test_degraded_report_source_refs_no_unknown`
5. **Null command for deterministic items** - `GoldenFixtureDeterministicOnlyNoCommandTests::test_worklist_command_is_null`
6. **Queue items expose all required metadata** - `GoldenFixtureQueueWithCommandTests::test_queue_item_has_all_required_metadata`

### Quality Gates (Deterministic, not LLM)

**Location:** `tests/fixtures/incident_report_quality.py`

| Rule | Description | Protected Against |
|------|-------------|-------------------|
| `observed_no_causal_language` | observed claims do not contain causal/root-cause language | Overconfident causal claims |
| `derived_no_causal_language` | derived claims do not contain unsupported causal/root-cause language | Causal language in deterministic conclusions |
| `hypotheses_have_basis` | hypothesis claims must have non-empty basis | Speculative claims without evidence |
| `unknowns_have_why_missing` | unknown claims must have whyMissing explanation | Missing evidence not properly explained |
| `recommendations_separated` | recommendations are separated from findings | Actions mixed with observations |
| `section_headings_concise` | section headings are concise (under 50 characters) | Verbose headings |
| `claim_statements_short` | claim statements are reasonably short (under 200 characters) | Verbose content |
| `no_filler_phrases` | no generic filler phrases in claim statements | Operator-hostile prose |
| `report_has_full_degraded_shape` | report has all sections: facts, derived, inferences, unknowns, recommendations | Incomplete reports |

---

## 7. Non-Goals (Preserved Constraints)

- **No new persistence layer** - projections are derived on-demand
- **No new immutable artifact type** - no `IncidentReportArtifact` created
- **No new execution engine** - existing health loop is unchanged
- **No LLM judge added** - deterministic gates are the first defense
- **No breaking schema changes** - additive payload fields only

---

## 8. Extension Seams

1. **Adding a new claim type:** Extend `ClaimType` Literal, add new TypedDict payload class, update `_build_incident_report_payload` to populate it
2. **Adding a new quality rule:** Add rule function to `incident_report_quality.py`, include in `check_incident_report_quality()`, add test
3. **Enriching the incident report:** Update `_build_incident_report_payload` in `api_incident_report.py`; derived projections don't require artifact migration

---

## 9. Files Changed

| File | Purpose |
|------|---------|
| `src/k8s_diag_agent/ui/api_payloads.py` | TypedDict definitions for all claim types and payloads |
| `src/k8s_diag_agent/ui/api_incident_report.py` | Builder logic for incident report and operator worklist |
| `src/k8s_diag_agent/ui/api.py` | Composition root that threads projections into run payload |
| `tests/fixtures/incident_report_fixtures.py` | Golden fixture builders for regression testing |
| `tests/fixtures/incident_report_quality.py` | Deterministic quality rule helpers |
| `tests/unit/test_api_incident_report.py` | Comprehensive test coverage |
| `frontend/src/types.ts` | TypeScript type definitions |
| `docs/data-model.md` | Updated with incident report section |
| `docs/schemas/incident-report-schema.md` | This specification |