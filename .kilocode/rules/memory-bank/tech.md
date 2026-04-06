# Technical Context

## Purpose of this file

This file records the current technical direction of the project.

It should describe:
- technologies already chosen,
- technologies likely to be used,
- intentionally unresolved technical decisions,
- and technical constraints that should guide implementation.

It should not become a speculative wishlist.

## Current status

The repository is in an early design/bootstrap phase.

At this stage:
- the technical stack is only partially decided,
- correctness of reasoning and diagnostic structure matter more than framework choice,
- and major technical choices should remain reversible until the first useful vertical slice exists.

## Technical priorities

Current priorities are:

1. simple implementation structure
2. testability
3. fixture-driven development
4. structured diagnostic outputs
5. eval coverage
6. observability of reasoning behavior
7. low-friction iteration

## Workspace conventions

- Run every Python command through `.venv/bin/python` so the virtual environment is the canonical interpreter.
- `.venv/bin/python -m unittest discover tests` remains the active verification path unless we intentionally switch to another runner.

## Snapshot/comparison status

- Live cluster snapshot collection and comparison both exist now; CLI flows can collect a typed `ClusterSnapshot`, run the comparator, and feed `run-health-loop` without reworking the fixture path.
- The health loop now emits review artifacts, drilldowns, and typed adaptation proposals (see `docs/schemas/health-proposal-schema.md` and `docs/schemas/run-artifact-layout.md`) while still preserving the regression harness.
- There is now a `check-proposal` command that replays each proposed adjustment against a fixture before acceptance, and `assess-drilldown` validates the drilldown evidence extracted by the health run.
-- The next technical step is orchestrating multi-context runs (context configs, batch collection, and handling partial evidence) while tying the resulting evidence/proposal bundle into the existing regression harness so health-driven adaptation stays traceable.

## Health review/adaptation status

- `run-health-loop` now produces per-cluster assessments, drilldown artifacts, reviews, trigger summaries, and typed proposals under `runs/health/` so every iteration is inspectable.
- Review scoring feeds `generate_proposals_from_review`, which emits proposals for warning thresholds, baseline policies, and drilldown prioritization; `check-proposal` replays them against deterministic fixtures (`tests/fixtures/...`) before they can influence runtime policies.
- The adaptation helpers (`src/k8s_diag_agent/health/adaptation.py`) keep proposal objects typed and provide `evaluate_proposal` for quick evaluation using production-quality fixtures.
- Cohort-aware comparison gating now marks suspicious-drift peers as eligible, skipped, or unsafe, while `scripts/inspect_health_config.py` also checks watched releases against the local baseline and records the outcome in the structured logging metadata that the security policy requires.
- `scripts/run_health_once.sh` ties the inspector, `run-health-loop --once`, `health-summary`, and optional `make_health_digest.sh` digest so quick operator workflows expose the config inspection result, health run outcome, summary artifact, and digest target using the same audit trail as the longer loops.

## Technical position for v1

The first implementation slice should be:

- fixture-first
- offline / replayable
- DB-free
- framework-noncommittal
- structured-output-first
- optimized for test ergonomics and iteration speed

The first slice should not depend on:
- live Kubernetes APIs
- LangGraph
- heavy persistence
- provider-specific inference runtimes
- autonomous remediation flows

## Likely technical building blocks

The project will likely need components for:

### Fixture / input loading
Possible initial inputs include:
- structured incident fixtures
- scenario test inputs
- later, Kubernetes objects/events/metrics/logs snapshots

The initial phase should prefer structured fixture input over complex live-cluster collection.

### Domain model
The system should have stable internal domain types for concepts such as:
- `EvidenceRecord`
- `Signal`
- `Finding`
- `Hypothesis`
- `Assessment`
- `NextCheck`
- `RecommendedAction`
- `ConfidenceLevel`
- `SafetyLevel`

The domain layer should remain independent from specific model providers, orchestration frameworks, or backend schemas.

### Reasoning layer
The system will need a reasoning component that:
- consumes normalized evidence,
- produces findings and hypotheses,
- assigns confidence conservatively,
- identifies missing evidence,
- and proposes next checks or actions.

This layer may combine:
- deterministic logic,
- rules/policies,
- and optional LLM assistance.

The exact balance remains intentionally unresolved until the first slice is defined.

### Output layer
The system should produce structured outputs first.

Possible output forms:
- machine-readable assessment objects
- human-readable summaries
- explanation templates
- test/eval artifacts

Free-form chat polish is lower priority than structured correctness.

### Evaluation layer
A strong eval harness is expected to be a first-class technical component.

It should eventually support:
- fixture-based scenarios
- regression cases
- false-certainty checks
- evidence-handling checks
- recommendation-safety checks
- output-shape validation

## Technical decision gates for v1

The following decisions should be made before or during initial scaffolding:

1. choose primary language/runtime
2. choose canonical assessment schema
3. choose canonical fixture schema
4. choose v1 public surface: CLI, library API, or both
5. choose deterministic-only vs LLM-assisted v1 reasoning
6. choose whether provider adapter seam is implemented now or stubbed

These are the main gates blocking implementation planning.

## Technical direction by concern

### Language/runtime
Not yet fixed.

Choose based on:
- speed of building the first vertical slice
- test ergonomics
- data/model integration ergonomics
- maintainability
- team/operator comfort

Do not overcommit early unless a clear implementation path requires it.

### LLM provider / inference path
Not yet fixed.

Design should avoid hard dependency on:
- one model vendor
- one prompt format
- one orchestration framework
- or one hosted/runtime assumption

Model integration should stay behind explicit seams.

### Prompt / policy storage
Likely needed as separate assets rather than buried inside application logic.

Possible categories:
- prompts
- policy rules
- explanation templates
- examples
- eval fixtures

Exact layout remains open, but volatile reasoning assets should be easy to inspect, test, and revise.

### Persistence
Explicitly deferred for v1.

Do not add heavy persistence architecture until a concrete need appears.

Possible future needs:
- storing assessments
- storing evaluation results
- storing evidence snapshots
- audit history

Until then, prefer simple file-based or fixture-driven flows.

### Interfaces
Not yet fixed.

Potential future surfaces:
- CLI
- library API
- service API
- UI

The first useful implementation does not need all of them.

### Live integrations
Explicitly deferred for the first implementation slice.

The first useful version should work well with:
- static fixtures
- structured sample incidents
- deterministic tests

Live-cluster integrations can come later once internal domain contracts and evals are stable.

## Deferred technologies

These are explicitly deferred unless a current pressure justifies them:

- LangGraph
- HolmesGPT / k8sgpt style orchestration/tool ecosystems
- Postgres / JSON persistence
- live Kubernetes API integrations
- provider-specific inference runtime commitments
- heavy service/API infrastructure

## Must-not-couple-yet constraints

Do not tightly couple:

- orchestration framework ↔ domain contracts
- persistence ↔ reasoning core
- rendering ↔ reasoning
- provider/runtime APIs ↔ domain types
- fixture schema ↔ normalized evidence schema

These boundaries should remain loose until the first vertical slice is working and tested.

## Technical constraints

The implementation should preserve:

### Reversibility
Avoid choices that make it hard to:
- switch model providers,
- replace orchestration logic,
- change prompt/policy layout,
- add persistence later only if needed,
- or split modules later if justified.

### Observability
Technical choices should make it possible to inspect:
- input evidence
- normalization results
- intermediate findings
- hypothesis generation
- confidence assignment
- final recommendations

### Testability
Technical choices should support:
- deterministic tests where possible
- fixture replay
- eval-based regression checks
- narrow unit tests around transformation and reasoning steps

### Low coupling
Avoid tight coupling between:
- collection and reasoning
- reasoning and rendering
- policy assets and core code
- provider APIs and domain types
- persistence concerns and the first slice

## Initial implementation bias

The first vertical slice should likely be able to:

1. load a structured incident fixture
2. normalize it into internal evidence
3. produce findings and hypotheses
4. assign confidence
5. recommend next checks/actions
6. emit structured output
7. validate behavior with tests/evals

That matters more right now than choosing the “perfect” framework stack.

## First implementation acceptance criteria

The first implementation slice should be considered successful if it can:

- load at least one replayable fixture
- transform that fixture into normalized evidence
- produce a structured assessment object
- clearly distinguish signal, finding, hypothesis, confidence, next evidence, recommended action, and safety level
- run without live-cluster dependency
- run without database dependency
- validate behavior with tests and at least one regression/eval case

## Known unresolved technical questions

These are intentionally open:

- primary implementation language
- exact project/package layout
- canonical assessment schema
- canonical fixture schema
- deterministic-only vs hybrid reasoning path
- LLM orchestration framework, if any
- model provider/runtime strategy
- whether CLI, library API, or both come first
- long-term prompt/policy asset layout
- multi-cluster support strategy

These should be resolved incrementally as the first working slices appear.

## What should update this file

Update this file when:
- a major technical choice becomes real,
- a previously open decision is intentionally closed,
- a new technical constraint appears,
- or a major subsystem becomes part of the stable direction.

Do not update this file for minor implementation details or day-to-day coding notes.
