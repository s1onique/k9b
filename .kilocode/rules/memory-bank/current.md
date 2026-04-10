# current.md

Purpose: compact task-facing project state for routine work.

## Mission

k9b is a Kubernetes diagnostics and monitoring agent that is:
- evidence-first
- artifact-first
- conservative with causality
- testable
- safe to evolve

## Current architecture posture

- File-backed artifacts under `runs/health` are the source of truth.
- UI/API are read-only projections derived from artifacts.
- Deterministic assessment/review/proposal paths are the core behavior.
- Provider-assisted branches are optional and auditable through external-analysis artifacts.
- No live cluster mutation is performed automatically.

## Stable implementation invariants

- Python commands must use `.venv/bin/python`.
- Prefer the smallest coherent change.
- Preserve artifact-first behavior.
- Keep deterministic and provider-assisted paths separate.
- Verification is mandatory before claiming completion.
- `scripts/verify_all.sh` is the canonical acceptance gate.

## Current product state

- Health loop, assessments, drilldowns, reviews, proposals, and UI projections are in place.
- Optional provider-assisted paths exist for review enrichment, auto drilldown, next-check planning/execution flows, and diagnostic-pack review.
- Diagnostic-pack review is now surfaced through backend/model/API/frontend.
- Frontend work is currently in a polish and coverage phase, not major redesign.

## Current backlog themes

Prefer the next smallest coherent slice in this order:
1. close concrete operator visibility gaps
2. strengthen test coverage for existing UI/panel states
3. expose existing artifact links cleanly
4. avoid reopening completed backend/provider work unless a real bug is found

## When to read deeper memory-bank files

Read individual memory-bank files only if the task changes:
- architecture direction
- roadmap priorities
- project status tracking
- major technical constraints
