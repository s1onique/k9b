# Architecture Doctrine

This file defines the always-on architectural doctrine for this repository.

It is intentionally compact.
Detailed rationale, playbooks, and evals belong under `docs/doctrine/`.
Project-specific context belongs under `.kilocode/rules/memory-bank/`.

## Mission

Build a Kubernetes monitoring and diagnostics agent that:
- produces grounded assessments from evidence,
- helps operators move from symptoms to likely causes,
- recommends safe next actions,
- remains evolvable as requirements, models, and integrations change.

## Architectural bias

Default to a **modular monolith** with explicit seams.

Do not decompose into multiple services unless there is clear evidence that decomposition improves:
- operational isolation,
- ownership scaling,
- deployability,
- reliability,
- or data/control-plane separation.

Premature decomposition is forbidden by default.

## Core architectural principles

### 1. Preserve evolvability
Prefer designs that keep future extraction, replacement, migration, and scaling possible.

If two options satisfy current requirements similarly, prefer the one with:
- lower reversal cost,
- smaller blast radius,
- better observability,
- simpler migration path.

### 2. Optimize for the next safe step
Do not design for an imagined final architecture.

Design for:
- the current problem,
- the next likely scale/complexity step,
- and the ability to learn from production safely.

### 3. Prefer explicit seams over premature services
Keep boundaries clear even inside a single process.

The system should be separable into modules such as:
- ingestion
- evidence normalization
- correlation
- reasoning
- recommendation
- output formatting
- evaluation

These are **logical boundaries first**, not necessarily deployment boundaries.

### 4. Evidence before conclusion
The system must distinguish:
- observed signal,
- derived symptom,
- hypothesis,
- confidence,
- recommended next check,
- recommended action.

Never collapse these into one opaque conclusion.

### 5. Observability is part of correctness
A design is incomplete if it cannot be inspected, tested, or debugged.

Every meaningful architectural change should preserve or improve:
- metrics
- logs
- traces
- decision visibility
- failure visibility
- input/output auditability

### 6. Stage risky change
If architecture, data flow, or reasoning behavior changes materially:
- prefer staged rollout,
- preserve rollback paths,
- avoid one-way migrations unless explicitly justified.

### 7. Keep rates of change decoupled
Do not tightly couple concerns that evolve at different speeds.

Examples:
- Kubernetes collection logic vs reasoning logic
- provider/model integration vs domain logic
- prompt/policy assets vs code
- UI formatting vs diagnostic core
- storage schema vs inference pipeline

### 8. Externalize volatile intelligence
Keep volatile behavior outside core code where practical.

Examples:
- prompts
- policy rules
- evaluation scenarios
- examples
- mappings
- thresholds
- explanation templates

But do not externalize behavior so aggressively that the system becomes untestable or incoherent.

### 9. Domain-first contracts
Internal interfaces should reflect monitoring/diagnostics concepts rather than vendor-specific API shapes.

Prefer contracts like:
- `EvidenceRecord`
- `Finding`
- `Hypothesis`
- `Assessment`
- `RecommendedNextStep`
- `ActionSafetyLevel`

Avoid leaking raw provider, model, or transport details across the system.

### 10. Human review is part of system fitness
Recommendations should help a platform engineer validate and act.

Prefer outputs that:
- show evidence,
- show uncertainty,
- explain why,
- say what would change the conclusion,
- and suggest the next useful query or check.

## Default module shape

Unless a stronger reason exists, organize the system roughly as:

1. `collect/`
   - Kubernetes objects, events, metrics, logs, external inputs

2. `normalize/`
   - Convert raw inputs into stable internal evidence structures

3. `correlate/`
   - Relate signals across workload, node, control plane, storage, network, ingress, autoscaling

4. `reason/`
   - Produce findings, hypotheses, confidence, and missing-information requests

5. `recommend/`
   - Suggest next checks, mitigations, or rollback-safe actions

6. `render/`
   - Human-facing and machine-facing structured outputs

7. `evals/`
   - Scenario fixtures, behavioral tests, regression tests

This is a conceptual layout, not a hard filesystem mandate.

## Architectural prohibitions

Do not:
- adopt microservices by default,
- hard-code provider-specific behavior into domain logic,
- treat one metric or one event as proof of root cause,
- remove observability during refactors,
- introduce irreversible storage or contract changes without migration notes,
- mix evidence collection, reasoning, and rendering so tightly that they cannot be tested independently,
- optimize for elegance at the expense of operability.

## Required design checks

Before accepting any significant architectural change, check:

1. What problem exists now?
2. What evidence proves this structure is needed?
3. What is the reversal cost?
4. What future move does this preserve?
5. What future move does this block?
6. What new coupling does this introduce?
7. How will this be observed in production?
8. How will it be tested?
9. What is the rollback or fallback path?
10. What condition would invalidate this design choice?

## Decision rule

When in doubt, prefer the architecture that is:
- simpler,
- more observable,
- easier to test,
- easier to reverse,
- and easier to evolve.

## Escalate when

Escalate instead of making a strong architectural recommendation when:
- requirements are under-specified,
- success criteria are unclear,
- the proposal creates a one-way door,
- the proposal reduces visibility,
- the proposal tightly couples unrelated concerns,
- or the recommendation depends on unknown production facts.

## Relationship to other repo guidance

Use this file together with:
- `AGENTS.md`
- `.kilocode/rules/10-agent-mission.md`
- `.kilocode/rules/30-output-contracts.md`
- `.kilocode/rules/40-tool-use.md`
- `.kilocode/rules/50-kubernetes-monitoring-domain.md`
- `.kilocode/rules/memory-bank/*.md`
- `docs/doctrine/*`
