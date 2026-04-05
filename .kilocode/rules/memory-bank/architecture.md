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

## Module responsibilities

### `collect`
Responsible for obtaining raw inputs.

Examples:
- Kubernetes objects
- events
- metrics
- logs
- rollout/config metadata
- fixture inputs
- scenario test inputs

This layer should focus on acquisition, not diagnosis.

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

No extraction should happen before need is demonstrated.

### 5. Prefer incremental evolution
Architectural changes should support staged migration, rollback, and side-by-side validation where practical.

## Initial implementation bias

The first working version should likely be:

- fixture-driven,
- test-heavy,
- focused on structured assessments,
- and light on live-cluster integration complexity.

Start with a vertical slice that can:
1. ingest a structured scenario,
2. normalize evidence,
3. produce findings and hypotheses,
4. assign confidence,
5. recommend next checks/actions,
6. and validate behavior with tests/evals.

## Initial non-goals for architecture

Avoid in the first phase:
- multi-service decomposition,
- autonomous remediation pipelines,
- direct production mutation workflows by default,
- heavy persistence architecture before proven need,
- provider-specific architecture lock-in,
- complex UI-driven architecture decisions.

## Known architectural unknowns

These areas are intentionally unresolved early on:
- exact LLM orchestration framework
- prompt/rule storage layout
- long-term persistence needs
- live-cluster vs offline/fixture-first balance
- API/UI shape
- multi-cluster support
- real-time vs batch/event-driven execution model

These should be decided incrementally as evidence accumulates.

## Current default data flow

Preferred conceptual flow:

1. input collected
2. evidence normalized
3. signals correlated
4. findings and hypotheses produced
5. next checks/actions recommended
6. output rendered
7. behavior validated through tests/evals

## Architectural risks to watch

Watch for:
- domain logic leaking into collection adapters
- rendering concerns leaking into reasoning logic
- provider-specific schemas leaking into internal interfaces
- hidden coupling between prompts/policies and code
- overgrowth of untested heuristics
- recommendation logic becoming opaque or non-debuggable
- premature infrastructure complexity

## Change policy for this file

Update this file when:
- the intended module boundaries change,
- a major architectural decision is made,
- a new stable subsystem is introduced,
- a major non-goal changes,
- or a previously unresolved unknown becomes decided.

Do not update this file for small local implementation details.
This file should describe durable architectural direction, not session noise.
