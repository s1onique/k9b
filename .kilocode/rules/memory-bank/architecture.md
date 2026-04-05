# Architecture Context

## Current architectural direction

The system should start as a **modular monolith** with explicit internal seams.

Do not begin with microservices or distributed components unless a clear need is demonstrated by:
- operational isolation requirements,
- scaling characteristics,
- ownership boundaries,
- reliability constraints,
- or control-plane / data-plane separation needs.

The first goal is not “final architecture.”
The first goal is a simple structure that is:
- testable,
- observable,
- easy to evolve,
- and easy to refactor as real usage teaches us more.

## Stable v1 architectural decisions

The first implementation slice is explicitly:

- **fixture-first**
- **offline / replayable**
- **single-process**
- **DB-free**
- **framework-noncommittal**
- **structured-output-first**

- live-cluster snapshot and comparison tooling are now part of the CLI, but the fixture-driven regression harness remains the authoritative grounding for reasoning behavior.
- heavy persistence is **out of the first slice**
- LangGraph or any orchestration framework is **not a v1 architectural commitment**
- domain contracts must not depend on LangGraph, provider APIs, or hosted/runtime assumptions

## Intended logical modules

The preferred logical decomposition is:

1. `collect`
2. `normalize`
3. `correlate`
4. `reason`
5. `recommend`
6. `render`
7. `evals`

These are logical boundaries first.
They do not imply separate services, separate deployables, or separate repos.

In v1, `collect` may initially be only a **fixture adapter** rather than a live Kubernetes integration layer.

## Module responsibilities

### `collect`
Responsible for obtaining raw inputs.

Examples:
- fixture inputs
- scenario test inputs
- Kubernetes objects
- events
- metrics
- logs
- rollout/config metadata

In v1, this layer already hosts both the structured fixture loader and the typed live snapshot collector that feeds the existing comparison seam, so downstream logic can stay grounded in fixtures while we extend optional live evidence integration.

### `normalize`
Responsible for converting raw external inputs into stable internal domain structures.

This layer should:
- reduce backend/provider leakage,
- standardize timestamps, identifiers, and evidence shape,
- and create consistent internal records for downstream reasoning.

### `correlate`
Responsible for linking related evidence across layers.

Examples:
- pod failure + node pressure
- ingress latency + backend saturation
- restart storm + recent rollout
- PVC issues + stateful workload degradation

This layer should connect signals without overclaiming causality.

### `reason`
Responsible for producing:
- findings
- hypotheses
- confidence
- missing-evidence requests
- probable layer of origin

This layer should separate observation from interpretation and interpretation from causal hypothesis.

The v1 reasoning path may be deterministic-only or hybrid, but domain contracts must remain stable either way.

### `recommend`
Responsible for turning assessments into useful next steps.

Outputs may include:
- next diagnostic checks
- safe mitigations
- rollback-aware suggestions
- requests for missing evidence
- action safety classification

This layer should prefer useful and safe operator guidance over confident-sounding verdicts.

### `render`
Responsible for presentation.

Examples:
- structured machine-readable output
- human-facing summaries
- explanation formatting
- report/output contracts

This layer should not own core diagnostic logic.

### `evals`
Responsible for validating diagnostic behavior.

This should include:
- scenario fixtures
- regression cases
- false-certainty checks
- evidence-handling checks
- recommendation-safety checks
- output-shape checks

## Preferred internal domain types

Internal interfaces should be domain-first.

Preferred concepts include:
- `EvidenceRecord`
- `Signal`
- `Finding`
- `Hypothesis`
- `Assessment`
- `NextCheck`
- `RecommendedAction`
- `SafetyLevel`
- `ConfidenceLevel`
- `Layer`
- `ImpactEstimate`

Avoid leaking raw vendor/API/provider response shapes across the domain core.

## Stable v1 contracts

The first slice should converge on stable contracts for:

### Fixture input
A structured incident/scenario input artifact that is replayable and deterministic.

### Normalized evidence
A stable internal evidence representation independent of fixture layout and provider/runtime details.

### Assessment output
A structured machine-readable assessment object that distinguishes:
- signal
- finding
- hypothesis
- confidence
- next evidence
- recommended action
- safety level

### Eval case linkage
A stable way to connect fixture scenarios, expected behavior, and regression/eval coverage.

## Architectural principles for this repo

### 1. Evidence before conclusion
The architecture should make it easy to preserve the distinction between:
- raw signal,
- finding,
- hypothesis,
- confidence,
- and action.

### 2. Observability is part of correctness
The system should make internal reasoning inspectable.

Where practical, preserve visibility into:
- what evidence was used,
- what findings were derived,
- what hypotheses were considered,
- what uncertainty remains,
- and why a recommendation was made.

### 3. Externalize volatile reasoning assets
Keep volatile artifacts outside hard-coded core logic where practical.

Examples:
- prompts
- policy rules
- explanation templates
- mappings
- evaluation scenarios

But do not fragment behavior so much that the system becomes incoherent or untestable.

### 4. Preserve future extraction paths
The monolith should have seams that would allow future extraction if justified.

Likely future extraction candidates, if needed:
- data collection adapters
- reasoning engine
- evaluation harness
- UI/API surface

These extraction candidates are explicitly deferred until after passing fixture/eval slices demonstrate real need.

### 5. Prefer incremental evolution
Architectural changes should support staged migration, rollback, and side-by-side validation where practical.

## Initial implementation bias

The first working version should likely be:

- fixture-driven,
- replayable,
- test-heavy,
- focused on structured assessments,
- and light on live-cluster integration complexity.

Start with a vertical slice that can:
1. load a structured fixture,
2. normalize evidence,
3. produce findings and hypotheses,
4. assign confidence,
5. recommend next checks/actions,
6. render a structured assessment,
7. and validate behavior with tests/evals.

## Initial non-goals for architecture

Avoid in the first phase:
- multi-service decomposition,
- autonomous remediation pipelines,
- direct production mutation workflows by default,
- heavy persistence architecture before proven need,
- provider-specific architecture lock-in,
- complex UI-driven architecture decisions,
- orchestration-framework-led design.

## Known architectural unknowns

These areas are intentionally unresolved early on:
- primary implementation language/runtime
- exact package/folder layout
- canonical fixture schema
- canonical assessment schema
- deterministic-only vs hybrid reasoning path
- CLI vs library-first public surface
- exact LLM orchestration framework, if any
- long-term persistence needs
- live-cluster adapter timing
- API/UI shape
- multi-cluster support
- real-time vs batch/event-driven execution model

These should be decided incrementally as evidence accumulates.

## Current default data flow

Preferred v1 conceptual flow:

1. fixture input loaded
2. evidence normalized
3. signals correlated or prepared for reasoning
4. findings and hypotheses produced
5. next checks/actions recommended
6. structured assessment rendered
7. behavior validated through tests/evals

In v1, `collect` still centers on fixtures while supporting the optional, typed snapshot collector so the rest of the flow can remain deterministic.

## Architectural risks to watch

Watch for:
- domain logic leaking into fixture or collection adapters
- rendering concerns leaking into reasoning logic
- provider-specific schemas leaking into internal interfaces
- hidden coupling between prompts/policies and code
- hidden coupling between orchestration framework and domain contracts
- hidden coupling between persistence and reasoning core
- overgrowth of untested heuristics
- recommendation logic becoming opaque or non-debuggable
- premature infrastructure complexity

## Change policy for this file

Update this file when:
- the intended module boundaries change,
- a major architectural decision is made,
- a stable v1 contract is defined,
- a new stable subsystem is introduced,
- a major non-goal changes,
- or a previously unresolved unknown becomes decided.

Do not update this file for small local implementation details.
This file should describe durable architectural direction, not session noise.
