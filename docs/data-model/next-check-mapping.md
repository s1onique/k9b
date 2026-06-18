# Next-Check-to-Incident Mapping Contract

**Status**: ACT Complete - Linkage Fields Added  
**Date**: 2026-06-18  
**Scope**: Schema change complete; suggested_checks population deferred to future ACT

## Executive Summary

This document defines the **next-check-to-incident mapping contract** and documents the 2026-06-18 ACT that added deterministic linkage fields to newly produced next-check artifacts.

**Finding**: Next-check plan artifacts now include incident linkage fields when production context provides them. Old artifacts without linkage fields remain compatible.

---

## 1. Artifact Inventory

### 1.1 Run-Scoped Next-Check Artifacts (Updated)

These artifacts are keyed by `run_id` and exist under `runs/health/external-analysis/`:

| Artifact | Path Pattern | Producer | Scope | Identity Fields | Can Link to Incident? |
|----------|--------------|----------|-------|-----------------|----------------------|
| **next-check-plan** | `{run_id}-next-check-plan.json` | LLM planner | Run-scoped | `candidateId`, `candidateIndex`, `description`, `targetCluster`, **linkage fields** | **Yes (with linkage context)** |
| **next-check-approval** | `{run_id}-next-check-approval-{index}.json` | Operator | Run-scoped | `candidateId`, `candidateIndex` | **May be enriched when read** |
| **next-check-promotion** | `{run_id}-next-check-promotion-{index}.json` | Operator | Run-scoped | `candidateId`, `description` | **May be enriched when read** |
| **next-check-execution** | `{run_id}-next-check-execution-{index}.json` | Manual execution | Run-scoped | `candidateId`, `candidateIndex`, `status` | **May be enriched when read** |

### 1.2 Incident Aggregate Root

| Model | Location | Identity Fields | Can Link to Next-Check? |
|-------|----------|-----------------|------------------------|
| **Incident** | `incident_lifecycle.py` | `incident_id`, `source_candidate_id`, `namespace`, `object_kind`, `object_name`, `candidate_class` | **Yes - via linkage fields** |
| **IncidentSignal** | same | `run_id`, `detector_id`, `fingerprint` | **Indirect** - via run_id |

### 1.3 Linkage Fields Schema (NEW)

New next-check plan artifacts include:

**Plan-level fields:**
```json
{
  "linkage_schema_version": 1,
  "run_id": "run-123",
  "linkage_status": "linked | partial | unlinked",
  "linkage_reason": "Human-readable explanation"
}
```

**Per-candidate fields:**
```json
{
  "incident_id": "default-pod-my-pod-crash-loop",
  "source_candidate_id": "cand-001",
  "namespace": "default",
  "objectKind": "Pod",
  "objectName": "my-pod",
  "candidateClass": "crash_loop",
  "linkage_status": "linked | partial | unlinked",
  "linkage_reason": "Human-readable explanation"
}
```

---

## 2. Linkage Status Classification

### 2.1 Linked

**Definition**: Candidate has `incident_id` and enough structured context to identify the incident.

**Conditions**:
- `incident_id` field is present AND
- `incident_id` matches an existing Incident record

**Classification**: **SAFE** - Direct deterministic mapping.

### 2.2 Partial

**Definition**: Candidate lacks `incident_id` but has enough structured fields for fallback mapping.

**Conditions** (one of):
- `run_id` + `source_candidate_id` are present (unique match against Incident signals)
- Complete entity identity (all 4 fields): `namespace` + `objectKind` + `objectName` + `candidateClass`

**Classification**: **CONDITIONALLY SAFE** - Depends on uniqueness guarantees.

### 2.3 Unlinked

**Definition**: Candidate lacks enough structured fields for deterministic mapping.

**Conditions**:
- No `incident_id`
- No `run_id` + `source_candidate_id`
- Incomplete or missing entity identity

**Classification**: **UNSAFE** - Cannot determine incident mapping.

---

## 3. Mapping Contract Classification (Updated)

### 3.1 SAFE Mappings

| Strategy | Conditions | Confidence |
|----------|------------|------------|
| **Direct incident_id match** | `incident_id` in candidate matches `incident_id` in Incident | **SAFE** |

### 3.2 CONDITIONALLY SAFE Mappings

| Strategy | Conditions | Confidence |
|----------|------------|------------|
| `run_id + source_candidate_id` | Unique match on run_id signals + source_candidate_id | **Conditionally Safe** |
| Complete entity identity | All 4 fields match uniquely | **Conditionally Safe** |

### 3.3 AMBIGUOUS Mappings

| Strategy | Why Ambiguous |
|----------|--------------|
| Entity identity alone | Same entity may have multiple incidents across runs |
| `latest_snapshot_bundle_id` | Bundle may contain multiple candidates/incidents |
| `source_candidate_id` without run_id | Same candidate_id may appear in different runs |

### 3.4 UNSAFE Mappings (Explicitly Rejected)

| Strategy | Why Unsafe |
|----------|----------|
| Title text similarity | Not deterministic |
| LLM summary similarity | Not deterministic |
| Description fuzzy match | Free text |
| Partial entity identity | Missing fields for unique identification |

---

## 4. Old Artifact Compatibility

**Key Invariant**: Old next-check plan artifacts without linkage fields remain compatible.

- Artifacts without `linkage_schema_version` are treated as legacy
- Reader code must handle missing linkage fields gracefully
- `linkage_status: "unlinked"` is the implied default for old artifacts
- No migration or rewriting of old artifacts is required

---

## 5. Production Context Requirements

### 5.1 When Linkage Fields Are Available

Linkage fields are available when:

1. **IncidentCandidate exists for the run**: The candidate's entity identity (namespace, kind, name, class) can be used to derive `incident_id`.

2. **Run has associated Incident records**: The `run_id` from the artifact filename can be matched against Incident signals.

### 5.2 When Linkage Fields Are NOT Available

Linkage fields are unavailable when:

- No incident context is threaded into the planner input
- The run has no associated Incident records
- Only run-scoped candidates are available (no entity identity)

### 5.3 Threading Incident Context

The `IncidentLinkageContext` dataclass in `next_check_incident_linkage.py` provides:

- `from_incident_candidate()`: Create context from an IncidentCandidate
- `from_selection_context()`: Create partial context from review selection
- `determine_linkage_status()`: Classify linkage quality

The context is threaded through:
1. `plan_next_checks()` → accepts `linkage_context` parameter
2. `run_next_check_planning()` → accepts `linkage_context` parameter  
3. `HealthLoopRunner._run_next_check_planning()` → accepts `linkage_context` parameter

---

## 6. Safety Constraints

- **No execution** - Linkage fields are provenance only
- **No manual promotion** - Artifacts are read-only
- **No remediation** - No Kubernetes mutation
- **No fake suggestions** - Fields are deterministically derived
- **No LLM-generated linkage** - Provider output cannot forge incident_id
- **No Kubernetes mutation** - No cluster changes

---

## 7. Current Status

| Field | Status |
|-------|--------|
| `suggested_checks` in IncidentDetailPayload | **Fully implemented - runtime population from artifact loading** |
| Linkage fields in new plan artifacts | **Implemented** |
| Old artifact compatibility | **Preserved** |
| Extraction helper | **Implemented** (incident_suggested_checks.py) |
| Artifact loading helper | **Implemented** (incident_next_check_artifacts.py) |
| Handler wiring | **Implemented** (api_incident_reads.py + server_incident_reads.py) |

### 7.1 ACT Complete: Handler Wiring for Runtime Population (2026-06-18)

**Implemented** in this ACT:

1. **Artifact loading helper**: `src/k8s_diag_agent/collect/incident_next_check_artifacts.py`
   - `incident_signal_run_ids()`: Extracts run_id values from incident signals
   - `next_check_plan_path_for_run()`: Constructs expected artifact path
   - `load_next_check_plan_payload()`: Loads and validates a single plan artifact
   - `load_next_check_plan_payloads_for_incident()`: Loads all plan payloads for an incident

2. **Handler update**: `src/k8s_diag_agent/collect/api_incident_reads.py`
   - `handle_get_incident()` now accepts optional `external_analysis_dir` parameter
   - When provided, loads plan artifacts and passes payloads to serializer
   - When None, returns empty suggested_checks (backward compatible)

3. **Server route update**: `src/k8s_diag_agent/ui/server_incident_reads.py`
   - `handle_incident_detail_route()` computes `external_analysis_dir` from `handler._health_root`
   - Passes directory to `handle_get_incident()` for artifact loading

4. **Serializer update**: `src/k8s_diag_agent/ui/api_incident_reads.py`
   - `build_incident_detail_payload()` accepts `next_check_plan_payloads` (iterable)
   - Preserves backward compatibility with legacy `next_check_plan_payload` parameter
   - Flattens suggestions from multiple plan payloads

5. **SAFE filter** (enforced at serializer level):
   - `candidate.linkage_status == "linked"`
   - `candidate.incident_id == incident.incident_id`
   - Candidate must have incident_id present

6. **Filters that IGNORE candidates**:
   - Partial linkage (entity fields only, no incident_id)
   - Unlinked linkage status
   - Non-matching incident_id
   - Old artifacts without linkage fields
   - Provider/text-only candidates
   - Text similarity

7. **No unsafe behavior implemented**:
   - No execution
   - No manual promotion
   - No remediation
   - No Kubernetes mutation
   - No LLM calls
   - No text similarity matching
   - No partial mapping population

8. **Mapping to IncidentSuggestedCheckPayload**:
   - `check_id`: candidate["candidateId"] or source_candidate_id fallback
   - `title`: candidate["title"] or description first line or "Suggested check"
   - `rationale`: candidate["rationale"] or description or linkage_reason or default
   - `source`: "next-check-plan"
   - `risk_level`: candidate["riskLevel"] or risk_level or null
   - `status`: "suggested"
   - `artifact_id`: from plan artifact (optional)
   - `run_id`: from plan-level run_id (optional)

### 7.2 Artifact Read Path (Production Ready)

The handler now handles artifact discovery automatically:

1. Extract run_ids from incident signals (structured, deterministic)
2. For each run_id, look for `{run_id}-next-check-plan.json` in `external-analysis/` directory
3. Load and validate JSON payloads
4. Pass payloads to serializer for SAFE linkage extraction
5. Merge suggestions from multiple artifacts in deterministic run_id order

**Read path**:
```
Incident.signals[].run_id
  → external_analysis_dir / {run_id}-next-check-plan.json
  → load_next_check_plan_payload()
  → build_incident_detail_payload(incident, next_check_plan_payloads=payloads)
  → suggested_checks populated from linked candidates
```

### 7.3 Tests Added

- `tests/unit/test_incident_next_check_artifacts.py`: artifact loading tests
- `tests/unit/test_api_incident_reads_detail_serializers.py`: handler composition tests
- Existing extraction tests preserved: `test_incident_suggested_checks.py`
- Existing serializer tests preserved: `test_api_incident_reads_suggested_checks_serializers.py`

---

## 8. Future ACT Recommendation

### Immediate Next ACT (Recommended)

**[Open / next] ACT: Wire incident detail handler to load next-check plan artifacts**

**Rationale**: Handler needs artifact read path integration to populate suggested_checks from signal run_ids.

### Alternative Next ACT (If full read seam unavailable)

**[Open / next] ACT: Add read-only external-analysis artifact index for incident details**

**Rationale**: Required if production needs automatic artifact discovery without manual path construction.

---

## 9. References

- `docs/data-model/next-checks.md`
- `docs/data-model/incidents.md`
- `src/k8s_diag_agent/collect/incident_lifecycle.py`
- `src/k8s_diag_agent/collect/incident_candidates.py`
- `src/k8s_diag_agent/external_analysis/next_check_incident_linkage.py`
- `src/k8s_diag_agent/external_analysis/next_check_planner.py`
- `src/k8s_diag_agent/health/loop_runner_next_check_planning.py`
- `src/k8s_diag_agent/ui/incident_suggested_check_mapping.py`