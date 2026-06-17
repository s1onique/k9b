# Next-Check-to-Incident Mapping Contract

**Status**: Discovery ACT - Contract Definition  
**Date**: 2026-06-17  
**Scope**: Mapping contract only; no implementation, no population, no execution

## Executive Summary

This document defines the **next-check-to-incident mapping contract** discovered during the 2026-06-17 ACT.

**Finding**: No SAFE deterministic mapping currently exists between next-check artifacts and Incident records. The preferred outcome is to document the mapping contract with mechanically proven safe/ambiguous/unsafe classifications, plus fixtures and tests that prove the classification.

---

## 1. Artifact Inventory

### 1.1 Run-Scoped Next-Check Artifacts

These artifacts are keyed by `run_id` and exist under `runs/health/external-analysis/`:

| Artifact | Path Pattern | Producer | Scope | Identity Fields | Can Link to Incident? |
|----------|--------------|----------|-------|-----------------|----------------------|
| **next-check-plan** | `{run_id}-next-check-plan.json` | LLM planner | Run-scoped | `candidateId`, `candidateIndex`, `description`, `targetCluster` | **No** - run-scoped |
| **next-check-approval** | `{run_id}-next-check-approval-{index}.json` | Operator | Run-scoped | `candidateId`, `candidateIndex` | **No** - run-scoped |
| **next-check-promotion** | `{run_id}-next-check-promotion-{index}.json` | Operator | Run-scoped | `candidateId`, `description` | **No** - run-scoped |
| **next-check-execution** | `{run_id}-next-check-execution-{index}.json` | Manual execution | Run-scoped | `candidateId`, `candidateIndex`, `status` | **No** - run-scoped |

### 1.2 Incident Aggregate Root

| Model | Location | Identity Fields | Can Link to Next-Check? |
|-------|----------|-----------------|------------------------|
| **Incident** | `incident_lifecycle.py` | `incident_id`, `source_candidate_id`, `namespace`, `object_kind`, `object_name`, `candidate_class` | **No** - no next-check linkage |
| **IncidentSignal** | same | `run_id`, `detector_id`, `fingerprint` | **Indirect** - via run_id |

### 1.3 Key Field Comparison

| Field | In Next-Check Plan? | In Incident? |
|-------|---------------------|--------------|
| `incident_id` | No | Yes |
| `source_candidate_id` | `candidateId` (optional) | Yes |
| `run_id` | From filename only | Via signals |
| `namespace` | No | Yes |
| `object_kind` | No | Yes |
| `object_name` | In description only | Yes |
| `candidate_class` | No | Yes |
| `target_cluster` | Yes | No |

---

## 2. Mapping Contract Classification

### 2.1 SAFE Mappings

**None exist today.** All mappings require missing fields.

### 2.2 CONDITIONALLY SAFE Mappings

| Strategy | Conditions | Confidence |
|----------|------------|------------|
| `run_id + candidateId + targetCluster` | When candidateId is stable and unique per run | Medium |
| `run_id + exact entity match` | When namespace/kind/name/class match exactly | Medium |

### 2.3 AMBIGUOUS Mappings

| Strategy | Why Ambiguous |
|----------|--------------|
| Entity identity alone | Same entity may have multiple incidents across runs |
| `latest_snapshot_bundle_id` | Bundle may contain multiple candidates/incidents |
| `source_candidate_id` without run_id | Same candidate_id may appear in different runs |

### 2.4 UNSAFE Mappings (Explicitly Rejected)

| Strategy | Why Unsafe |
|----------|------------|
| Title text similarity | Not deterministic |
| LLM summary similarity | Not deterministic |
| Description fuzzy match | Free text |

---

## 3. Required Future Fields

To enable SAFE mapping, next-check artifacts need:

```json
{
  "purpose": "next-check-planning",
  "incident_id": "default-pod-my-pod-crash-loop",
  "candidates": [{
    "incident_id": "default-pod-my-pod-crash-loop",
    "namespace": "default",
    "objectKind": "Pod",
    "objectName": "my-pod",
    "candidateClass": "crash_loop"
  }]
}
```

---

## 4. Safety Constraints

- No execution
- No manual promotion
- No remediation
- No fake suggestions
- No Kubernetes mutation

---

## 5. Current Status

| Field | Status |
|-------|--------|
| `suggested_checks` in IncidentDetailPayload | **Empty by default** |
| Mapping proven safe? | **No** |

---

## 6. Future ACT Recommendation

**[Open / next] ACT: Add incident linkage fields to next-check artifacts at production time**

**Rationale**: Required fields missing from next-check plan artifacts.

---

## 7. References

- `docs/data-model/next-checks.md`
- `docs/data-model/incidents.md`
- `src/k8s_diag_agent/collect/incident_lifecycle.py`
- `src/k8s_diag_agent/collect/incident_candidates.py`
