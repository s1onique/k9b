# current.md

Purpose: compact task-facing project state for routine work.

**Last Updated:** 2026-06-29

**See also:** `docs/agent-docs-audit.md` for documentation drift tracking.

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
- Coverage is gate-managed; verify active thresholds in `docs/coverage.md` and CI config.

## Current product state (as of 2026-05-13)

- Health loop, assessments, drilldowns, reviews, proposals, and UI projections are in place.
- Optional provider-assisted paths exist for review enrichment, auto drilldown, next-check planning/execution flows, and diagnostic-pack review.
- Diagnostic-pack review is now surfaced through backend/model/API/frontend.
- Frontend work is in polish and coverage phase.
- GitHub Actions CI verification added (`.github/workflows/verify.yml`).
- Coverage reporting integrated as non-blocking CI job.

## Live lab architecture (2026-06-29)

CNPG and OTel demo labs share common k9b platform gates via `scripts/lab_common/`:

- `provider_status.py`: Canonical parser for `/api/health/details` provider status
- `provider_preflight.py`: P0b provider preflight gate implementation
- `constants.py`: Shared failure class constants

Both labs import from `scripts.lab_common` instead of implementing their own
health/provider parsing logic. See `scripts/k9b_provider_preflight.py` for
backward-compatible wrapper.

## Current backlog themes

From post-beta backlog, prefer the next smallest coherent slice:
1. expand deterministic next-check fixture coverage
2. strengthen test coverage for existing UI/panel states
3. expose existing artifact links cleanly
4. avoid reopening completed backend/provider work unless a real bug is found
5. review beta operator feedback and scope first post-beta increment

## Verification commands

| Command | Purpose |
|---------|---------|
| `scripts/verify_all.sh` | Full canonical acceptance gate |
| `scripts/verify_all.sh --python-only` | Python lane only (ruff, unittest, mypy) |
| `scripts/verify_all.sh --frontend-only` | Frontend lane only (npm ci, test, build) |
| `scripts/verify_all.sh --helm-only` | Helm chart verification only |

## When to update this file

Update when:
- A major milestone is completed
- Verification commands or paths change
- New scripts are added or removed
- Architecture direction changes materially
- Product priorities shift significantly

Do NOT update for:
- Small code edits
- Temporary experiments
- Routine day-to-day changes

## When to read deeper memory-bank files

Read individual memory-bank files only if the task changes:
- architecture direction → see `architecture.md`
- roadmap priorities → see `progress.md`
- project status tracking → see `progress.md`
- major technical constraints → see `architecture.md`
- product overview → see `brief.md`
