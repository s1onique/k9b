# Progress Context

## Purpose of this file

This file records the current project state in a concise, durable form.

It should help an agent quickly answer:
- what already exists,
- what has been decided,
- what is being worked on now,
- what should happen next,
- and what is still intentionally open.

This file is not a session diary.
It should track meaningful project progress, not chat-by-chat noise.

## Current phase

The project is in the **health-loop stabilization** phase; the CLI now runs live snapshot collection, health scoring, drilldown gathering, and review-driven adaptation proposals so that real evidence feeds training, evaluation, and guarded change gates.

Current focus:
- keeping `run-health-loop` artifacts (snapshots, assessments, reviews, proposals) documented and replayable,
- expanding drilldown collection/assessment so operators have targeted context for each regression,
- forcing eval coverage around review scoring, proposal generation, and `check-proposal` replays while preserving the fixture-driven regression harness,
- documenting the operator workflow that links `run-health-loop` → review/scoring → proposal generation → `check-proposal` before any adaptation acts on production.
- improving policy realism and the new policy preflight so suspicious-drift pairs only run when class/role/cohort metadata plus watched releases align, and structured logging records the inspection outcome for audit,
- expanding the quick-run driver (`scripts/run_health_once.sh`) so it reports the config inspection result, health run exit, summary artifact, and optional digest location while reusing existing CLI commands.
- syncing documented guidance with `docs/baseline_watch_practices.md` so platform-level baseline pruning and watched release targeting stay align with the preflight gate.

## Feedback loop status

- **Operational loop:** `run-health-loop` now drives collect -> normalize -> health assessment -> review -> adaptation proposal, emitting won approval trails (snapshots, comparisons, reviews, drilldowns, triggers, proposals) for every run.
- **Evaluation loop:** Fixture regressions, `run-feedback` artifacts, and proposal replays continue to be scored so review scoring, `assess-drilldown`, and `check-proposal` stay transparent before any acceptance.
- **Adaptation loop:** Every review proposal produced under `runs/health/proposals` is replayed against deterministic fixtures (via `check-proposal`), scored, and either accepted or rejected; no prompts, thresholds, or policies mutate outside this gated cycle.

Production snapshot tooling is now live for manual collection/comparison; the next data-driven milestone is orchestrating multiple contexts safely.

## What exists now

The repository currently has:

### Human-readable repo entrypoint
- `AGENTS.md`

### Standing Kilo rule files
- `.kilocode/rules/00-global.md`
- `.kilocode/rules/10-agent-mission.md`
- `.kilocode/rules/20-architecture-doctrine.md`
- `.kilocode/rules/30-output-contracts.md`
- `.kilocode/rules/40-tool-use.md`
- `.kilocode/rules/50-kubernetes-monitoring-domain.md`

### Memory Bank files
- `.kilocode/rules/memory-bank/brief.md`
- `.kilocode/rules/memory-bank/product.md`
- `.kilocode/rules/memory-bank/architecture.md`
- `.kilocode/rules/memory-bank/tech.md`
- `.kilocode/rules/memory-bank/progress.md`

### Doctrine files
- `docs/doctrine/constitution.md`
- `docs/doctrine/precedence.md`
- `docs/doctrine/seed_rules.md`
- `docs/doctrine/playbooks/design_review.md`
- `docs/doctrine/playbooks/redesign_staging.md`
- `docs/doctrine/evals/eval_schema.yaml`
- `docs/doctrine/evals/seed_evals.yaml`

### Source scaffolding
- `src/k8s_diag_agent/collect/cluster_snapshot.py`
- `src/k8s_diag_agent/collect/live_snapshot.py`
- `src/k8s_diag_agent/compare/two_cluster.py`
- `src/k8s_diag_agent/health/loop.py` (health run orchestration, reviews, proposal generation)
- `src/k8s_diag_agent/health/adaptation.py` (deterministic proposal helpers and `check-proposal` evaluation)
### Health/adaptation artifacts
- `docs/schemas/health-proposal-schema.md` documents the typed proposal shape that lives under `runs/health/proposals`.
- `runs/health/` contains snapshots, assessments, triggers, reviews, drilldowns, and proposals for each per-cluster iteration.
- CLI commands `run-health-loop`, `assess-drilldown`, and `check-proposal` coordinate collection, review, and proposal replay for operators.

### Documentation artifacts
- `docs/cluster_snapshot_plan.md`
- `docs/schemas/fixture-schema.md`
- `docs/security-policy.md`

## Key decisions already made

### Product direction
The repo is building an LLM-based Kubernetes monitoring and diagnostics agent.

### User focus
Primary users are:
- platform engineers
- SREs
- Kubernetes operators

### Behavioral stance
The agent should:
- be evidence-first,
- distinguish facts from assumptions,
- separate signal, finding, hypothesis, confidence, and action,
- avoid unsupported certainty,
- recommend the next useful diagnostic step,
- and prefer low-risk guidance when evidence is incomplete.

### Architectural stance
The system should start as a **modular monolith** with explicit internal seams.

Preferred logical boundaries are:
- collect
- normalize
- correlate
- reason
- recommend
- render
- evals

### Development stance
The first useful implementation should be:
- simple,
- fixture-first,
- replayable,
- test-heavy,
- structured in output,
- and easy to evolve.

## Resolved since older design chat

The following are now treated as resolved for v1:

- no DB in v1
- no LangGraph commitment in v1
- live-cluster integration in v1
- no autonomous remediation in v1
- no framework-led architecture in v1
- structured assessment object first
- fixture-first vertical slice first

## What is intentionally not done yet

The following are intentionally deferred:

- choosing the final implementation language/runtime
- choosing the final LLM provider/runtime path
- LangGraph or similar orchestration commitments
- database/persistence subsystem
- autonomous remediation
- multi-service decomposition
- UI-first product work
- periodic loop/watch orchestration beyond the new batch collector

## Current blockers

Implementation planning is currently blocked on:

- chosen language/runtime
- chosen v1 public surface: CLI, library API, or both
- defined v1 assessment schema
- defined v1 fixture input schema (including cluster snapshot metadata)
- selected first end-to-end scenario
- decision on deterministic-only vs LLM-assisted v1 reasoning
- multi-cluster orchestration (batch collection, watch loop, per-context config)
- surfacing partial/missing evidence to reasoning layers

## Immediate next milestones

### 1. Stabilize the cluster snapshot contract
Document `cluster_snapshots` inputs, metadata expectations, and ensure validators/tests handle missing or partial snapshot data.

### 2. Automate multi-context runs
Add configs + batch commands so multiple contexts can be collected consistently and snapshot collection issues are recorded.

### 3. Keep the fixture-driven slice working
Preserve the existing CLI/fixture regression path while wiring in the new evidence sources behind the current harness.

### 4. Expand regression coverage for snapshots
Add tests or evals that exercise snapshot ingestion, comparison logic, and partial-evidence handling when collecting real clusters.

## Near-term success criteria

The next stage is successful if the repo can do all of the following:

- provide stable repo guidance to Kilo
- preserve durable project memory
- define the governing doctrine clearly
- support a first vertical slice implementation
- define stable fixture and assessment contracts
- and test at least one realistic diagnostic scenario end to end

## Risks to watch now

Current early-stage risks:

- too much duplication between `AGENTS.md`, repo rules, Memory Bank, and doctrine files
- over-design before the first working vertical slice
- choosing framework/tooling too early
- writing long policy prose without turning important rules into evals
- allowing domain logic to become entangled with provider/runtime assumptions
- reintroducing DB, orchestration, or live-integration complexity before the first slice is proven

## Update rules for this file

Update this file when:
- a major milestone is completed,
- a new stable repo structure is added,
- a major decision is made,
- implementation begins,
- or priorities change.

Do not update this file for:
- small code edits,
- temporary experiments,
- conversational notes,
- or routine day-to-day chatter.

## Current summary

The repo has a firm guidance layer, the scaffolding is live, and the work now centers on per-cluster health monitoring: collecting new snapshots, drilling down on anomalies, writing health reviews, producing adaptation proposals, and keeping the inspector/quick-run gating honest so the policy memory stays accurate.

The next important move is to:
1. keep the health artifact layout (snapshots, assessments, reviews, proposals, triggers) consistent and well documented,
2. expand regression coverage around review scoring, proposal generation, and proposal replay,
3. keep the fixture-driven regression slice healthy while the new health signals land,
4. tighten the operator workflow from `run-health-loop` through review -> proposal -> `check-proposal` so each adaptation is grounded in evidence,
5. and lock the new baseline/watch guidance into the documented memory via `docs/baseline_watch_practices.md` so operators can prune policy drift deliberately.
