# UI model boundaries

## Purpose

Document UI/API read-model boundaries and modularization ownership.

## Core principle

**UI/API payloads are derived read models.**

The backend never stores another copy of data already present in the artifact tree. All UI/API responses are derived from `runs/health/` artifacts.

## Ownership structure

### Model layer

| Module | Owner symbols | Rationale |
|--------|--------------|-----------|
| `model.py` | Composition/root builder (`RunView`, `UIIndexContext`, `load_ui_index`, `build_ui_context`) | Public surface |
| `model_cluster.py` | `ClusterView`, `_build_cluster_view` | Domain-focused extraction |
| `model_assessment.py` | `AssessmentView`, assessment-related views | Domain-focused extraction |
| `model_review_enrichment.py` | `ReviewEnrichmentView` | Domain-focused extraction |
| `model_diagnostic_pack.py` | `DiagnosticPackView` | Domain-focused extraction |
| `model_next_check_plan.py` | `NextCheckPlanView`, `NextCheckCandidateView` | Domain-focused extraction |
| `model_next_check_queue.py` | `NextCheckQueueItemView` | Domain-focused extraction |
| `model_llm_stats.py` | `LLMStatsView` | Domain-focused extraction |
| `model_fleet.py` | `FleetStatusSummary` | Domain-focused extraction |
| `model_alertmanager.py` | `AlertmanagerCompactView`, `AlertmanagerSourcesView` | Domain-focused extraction |

### API layer

| Module | Owner symbols | Rationale |
|--------|--------------|-----------|
| `api.py` | Public builders (`build_run_payload`, `build_fleet_payload`, `build_runs_list`) | Public compatibility/composition surface |
| `api_payloads.py` | All TypedDict payload classes | Contract module; JSON key names frozen |
| `api_alertmanager.py` | Alertmanager serializers | Domain-focused extraction |
| `api_cluster_detail.py` | Cluster detail serializers | Domain-focused extraction |
| `api_llm.py` | LLM stats serializers | Domain-focused extraction |
| `api_incident_report.py` | `_build_incident_report_payload`, `_build_operator_worklist_payload` | Domain-focused extraction |
| `api_review_enrichment.py` | Review enrichment serializers | Domain-focused extraction |

## Read model rules

1. **TypedDict payloads live in `api_payloads.py`**: JSON key names, optional vs required fields, and field types are frozen.

2. **Serializers live in focused `api_*.py` modules**: Serializer functions belong in domain-specific modules.

3. **`api.py` remains the public compatibility/composition surface**: Existing imports continue to work.

4. **Legacy imports from `ui.api` are intentionally preserved**: Re-exports are stable contracts.

5. **Public builders remain in `api.py`**: Functions like `build_run_payload` compose multiple serializers and stay as public entry points.

## Incident views

Incident list/detail views should become incident-centered.

The Incident aggregate owns case lifecycle truth. UI views are derived projections.

## Next-check views

Global next-check page, if retained, is a **derived work queue** over incidents and compatibility next-check artifacts.

Do not introduce a hidden persistence layer in UI docs.

## Derived projections

| Projection | Source | Computed on |
|-----------|--------|-------------|
| `ui-index.json` | All `runs/health/` artifacts | Every run completion |
| `llmStats` | External analysis artifacts | Every run completion |
| `historicalLlmStats` | Retained external analysis artifacts | On request |
| `llmActivity` | Retained external analysis artifacts | On request |
| `provider_execution` | Run config + artifacts | Every run completion |

## Compatibility re-exports

Re-exports in `model.py` and `api.py` are stable contracts. Do not remove or rename re-exported symbols without a deprecation period.

Breaking changes to re-exported symbols must include migration guidance.
