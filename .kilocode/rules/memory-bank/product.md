# Product Context

## Product name
LLM-based Kubernetes monitoring and diagnostics agent.

## Product goal
Help platform engineers and operators understand abnormal Kubernetes states faster and more safely by turning raw technical signals into structured, evidence-aware diagnostic guidance.

## Core user problem
Kubernetes failures are often noisy, cross-layered, and ambiguous.

Operators commonly face:
- many symptoms at once,
- incomplete or delayed telemetry,
- uncertainty about whether the issue is app, platform, network, storage, rollout, or capacity related,
- pressure to act before root cause is clear,
- and fragmented evidence across dashboards, logs, events, and object state.

The product should reduce time spent moving from “something is wrong” to “here is the most likely explanation, here is what we know, here is what we still need to verify, and here is the safest next step.”

## Primary users
- platform engineers
- SREs
- Kubernetes operators
- senior developers operating services in Kubernetes

## User jobs to be done
Users want the agent to:
- summarize cluster/workload health clearly,
- identify the strongest signals,
- distinguish findings from hypotheses,
- explain likely causes with honest confidence,
- recommend the next best diagnostic check,
- suggest low-risk actions before disruptive ones,
- and make debugging paths easier to follow.

## Product promise
The product should behave like a careful Kubernetes diagnostician:
- evidence-first,
- conservative with causality,
- explicit about uncertainty,
- useful about next steps,
- and safe in recommendations.

## Initial product scope
In the first phase, the product should focus on:
- structured incident/health inputs,
- evidence normalization,
- correlation across common Kubernetes layers,
- structured assessments,
- next-check recommendations,
- and evaluation against realistic diagnostic scenarios.

Initial emphasis is on correctness, clarity, and testability.

## Initial non-goals
The first phase should not optimize for:
- autonomous remediation,
- direct production mutation by default,
- chat polish over diagnostic quality,
- broad multi-cluster fleet orchestration,
- highly customized vendor-specific integrations,
- or unsupported root-cause certainty.

## Product principles
1. Evidence before conclusion.
2. Hypotheses must be falsifiable.
3. Missing telemetry is itself a finding.
4. The next useful check is often more valuable than a confident-sounding verdict.
5. Low-risk guidance is preferred when evidence is incomplete.
6. Product usefulness matters more than LLM cleverness.
7. Structured outputs are preferred over opaque prose.
8. Diagnostic correctness outranks UI sophistication.

## Expected outputs
The product should usually produce:
- observed signals
- findings
- hypotheses
- confidence
- next evidence to collect
- recommended action
- safety level

Where relevant, also include:
- probable layer of origin
- likely blast radius
- recent-change relevance
- what would falsify the leading hypothesis

## Primary evidence domains
The product is expected to reason about:
- Kubernetes object state
- events
- metrics
- logs
- rollout/config change context
- node conditions
- scheduling/resource pressure
- networking symptoms
- storage symptoms
- autoscaling signals
- observability gaps

## Product quality bar
A good product output should be:
- grounded in available evidence,
- easy for an operator to review,
- explicit about what is unknown,
- useful for deciding the next action,
- and robust against overclaiming.

A bad product output is:
- overconfident,
- vague,
- unfalsifiable,
- operationally unsafe,
- or unable to separate observation from interpretation.

## Success criteria
The product is succeeding when it improves:
- diagnostic accuracy,
- operator trust,
- clarity of uncertainty,
- speed to the next useful check,
- safety of recommended actions,
- test/eval pass rate,
- and maintainability of the reasoning pipeline.

## Current product strategy
Start simple.

Prefer:
- fixture-based scenarios before heavy live integrations,
- modular monolith before service decomposition,
- clear internal domain types before backend-specific plumbing,
- and eval-driven refinement before broad feature expansion.

## Relationship to repo guidance
This file describes product intent and user value.

For behavioral and implementation guidance, also consult:
- `AGENTS.md`
- `.kilocode/rules/00-global.md`
- `.kilocode/rules/10-agent-mission.md`
- `.kilocode/rules/20-architecture-doctrine.md`
- `.kilocode/rules/30-output-contracts.md`
- `.kilocode/rules/40-tool-use.md`
- `.kilocode/rules/50-kubernetes-monitoring-domain.md`
