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

## Likely technical building blocks

The project will likely need components for:

### Kubernetes-facing data input
Possible inputs include:
- Kubernetes object snapshots
- events
- metrics
- logs
- rollout/config metadata
- manually prepared incident fixtures

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

The domain layer should remain independent from specific model providers or backend schemas.

### Reasoning layer
The system will likely need a reasoning component that:
- consumes normalized evidence,
- produces findings and hypotheses,
- assigns confidence conservatively,
- identifies missing evidence,
- and proposes next checks or actions.

This layer may combine:
- deterministic logic,
- rules/policies,
- and LLM assistance.

The exact balance is intentionally undecided early on.

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
Not yet justified as a major subsystem.

Do not add heavy persistence architecture until a concrete need appears.

Possible future needs:
- storing assessments
- storing evaluation results
- storing evidence snapshots
- audit history

Until then, prefer simple file-based or test-fixture-driven flows.

### Interfaces
Not yet fixed.

Potential future surfaces:
- CLI
- library API
- service API
- UI

The first useful implementation does not need all of them.

### Live integrations
Should be introduced incrementally.

The first useful version should work well with:
- static fixtures
- structured sample incidents
- deterministic tests

Live-cluster integrations can come later once internal domain contracts and evals are stable.

## Technical constraints

The implementation should preserve:

### Reversibility
Avoid choices that make it hard to:
- switch model providers,
- replace orchestration logic,
- change prompt/policy layout,
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

## Known unresolved technical questions

These are intentionally open:

- primary implementation language
- exact project/package layout
- LLM orchestration framework, if any
- model provider/runtime strategy
- persistence needs
- live-cluster collection strategy
- whether API/CLI/UI comes first
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
