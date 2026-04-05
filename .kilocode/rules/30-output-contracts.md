# Output Contracts

This file defines the default output shapes for work in this repository.

Its purpose is to make outputs:
- reviewable,
- testable,
- operationally useful,
- and consistent across planning, coding, debugging, and architecture work.

Detailed rationale belongs in `docs/doctrine/`.
Project context belongs in `.kilocode/rules/memory-bank/`.

## Global output rules

For any non-trivial task:

1. Distinguish facts from assumptions.
2. Be explicit about uncertainty that could change the recommendation.
3. Prefer structured output over loose prose.
4. Include tradeoffs when multiple valid options exist.
5. Recommend a default, not just a menu.
6. Do not imply certainty without evidence.
7. Do not hide operational consequences.
8. Keep outputs concise at the top and expandable below.

## Required answer skeleton for design and architecture tasks

Unless the requester explicitly asks otherwise, use this structure:

### Goal
What problem is being solved?

### Facts
What is known from the repo, task, or evidence?

### Assumptions
What is inferred, guessed, or still unknown?

### Options
What are the credible approaches?

### Recommendation
Which option is preferred?

### Why
Why is it preferred over alternatives?

### Tradeoffs
What is gained and what is sacrificed?

### Evolution / migration impact
What future moves does this preserve or block?

### Observability impact
What metrics, logs, traces, events, or debug surfaces are needed or affected?

### Rollback / fallback
How can this be reversed, disabled, or contained?

### Next validation step
What should be tested, measured, or verified next?

## Required answer skeleton for implementation tasks

When creating or changing code, include:

### Scope
What files or modules are being changed?

### Intent
What behavior is being added, removed, or corrected?

### Contract impact
Are any public/internal interfaces, schemas, prompts, or behavior contracts changing?

### Risks
What could break?

### Tests
What tests were added or updated?

### Observability
What should be measurable or inspectable after the change?

### Limitations
What is still incomplete or intentionally deferred?

## Required answer skeleton for debugging tasks

When diagnosing a bug, failure, or incident, include:

### Symptom
What is actually observed?

### Evidence
What logs, metrics, traces, events, or repo facts support this?

### Most likely hypotheses
List hypotheses in order of likelihood.

### Missing evidence
What key fact is still needed?

### Next checks
What should be queried, inspected, or reproduced next?

### Safe actions
What low-risk mitigations or containment steps are reasonable now?

### Do not claim
Do not claim root cause as certain unless evidence is sufficient.

## Required answer skeleton for Kubernetes monitoring tasks

For cluster or workload assessment, outputs must distinguish:

### Signal
Observed raw indicators:
- metrics
- events
- logs
- object status
- scheduling state
- probe state
- resource pressure
- storage/network symptoms

### Findings
Direct interpretations that are strongly supported.

### Hypotheses
Plausible causes that still require confirmation.

### Confidence
State confidence qualitatively:
- low
- medium
- high

### Next evidence to collect
What specific query, metric, event stream, or object inspection would sharpen the diagnosis?

### Recommended action
What should the operator do next?

### Safety level
Tag actions as:
- observe-only
- low-risk
- change-with-caution
- potentially-disruptive

## Architectural recommendation contract

Whenever recommending a structural change, explicitly answer:

1. What current pain justifies this?
2. Why now?
3. Why this boundary?
4. What is the reversal cost?
5. What migration path exists?
6. What observability must be preserved?
7. What simpler alternative was rejected and why?
8. What would change the recommendation?

## Code generation contract

When writing new code, the output should favor:

- simple module boundaries,
- domain-first types,
- testable units,
- explicit error paths,
- observable behavior,
- configuration over hard-coded policy where appropriate.

Avoid:
- hidden magic,
- deeply coupled code,
- provider-specific leakage into domain logic,
- untestable orchestration,
- adding abstractions with no demonstrated need.

## Refactor contract

When refactoring, state:

### Refactor goal
Why this refactor exists.

### Behavior preservation
What behavior must remain unchanged.

### New seams
What boundaries become clearer.

### Operational effect
What gets easier to test, debug, migrate, or evolve.

### Regression risk
What could silently change.

## Prompt / policy asset contract

When editing prompts, templates, rule files, or evaluation assets, include:

### Behavior target
What agent behavior should change?

### Failure mode addressed
What incorrect behavior is being corrected?

### Eval impact
What evals must be added or updated?

### Drift risk
Could this change create conflicts with existing rules or examples?

## Test / eval contract

When adding or changing tests or evals, specify:

### Scenario
What real behavior or failure is represented?

### Expected behavior
What should the system do?

### Forbidden behavior
What should it never do?

### Rule coverage
Which doctrine or repo rule does this validate?

### Regression value
What future breakage will this catch?

## PR / summary contract

When summarizing completed work, include:

### Changed
What was changed?

### Why
Why was it changed?

### Impact
What user/operator/developer-visible behavior changed?

### Risk
What should be watched after merge?

### Follow-up
What remains next?

## Escalation contract

Escalate instead of pretending completeness when:

- requirements are ambiguous,
- evidence is insufficient,
- a change is hard to reverse,
- observability is missing,
- multiple rules conflict,
- the recommendation would materially affect safety or production stability.

When escalating, state:
1. what is missing,
2. why it matters,
3. what minimal next fact would unblock the decision.

## Output quality bar

Good outputs in this repo are:

- evidence-aware,
- explicit about uncertainty,
- operationally useful,
- structured for review,
- easy to convert into code, tests, or follow-up tasks.

Bad outputs in this repo are:

- overconfident,
- architecture-astronaut prose,
- code without tests,
- diagnoses without evidence,
- recommendations without rollback thinking,
- conclusions that mix facts, interpretation, and speculation into one blob.
