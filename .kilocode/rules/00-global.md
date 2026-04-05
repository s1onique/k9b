# Global Rules

This repository builds an LLM-based Kubernetes monitoring and diagnostics agent.

This file is the top-level entrypoint for repo guidance.
It should stay short, stable, and always applicable.

## Read order

Before doing substantial work, consult in this order:

1. `AGENTS.md`
2. `.kilocode/rules/10-agent-mission.md`
3. `.kilocode/rules/20-architecture-doctrine.md`
4. `.kilocode/rules/30-output-contracts.md`
5. `.kilocode/rules/40-tool-use.md`
6. `.kilocode/rules/50-kubernetes-monitoring-domain.md`
7. relevant files under `.kilocode/rules/memory-bank/`
8. relevant files under `docs/doctrine/`

Do not assume the current task is context-free.

## Default posture

The default posture in this repo is:

- evidence-first
- explicit about uncertainty
- modular and evolvable
- operationally practical
- conservative with causality
- structured in output
- small in changes
- testable in implementation

## Universal requirements

Always:

- distinguish facts from assumptions,
- preserve observability,
- prefer reversible changes when practical,
- recommend the smallest coherent next step,
- verify meaningful changes,
- and state risks and tradeoffs clearly.

## Never

Never:

- invent facts,
- blur signal and hypothesis,
- assume one symptom proves root cause,
- introduce major complexity without justification,
- remove visibility silently,
- or make irreversible changes casually.

## Architectural bias

Prefer:

- modular monolith over premature decomposition,
- explicit seams over implicit coupling,
- domain-first contracts over provider leakage,
- staged evolution over speculative end-state design.

## Output bias

For non-trivial tasks, prefer outputs that include:

- goal
- facts
- assumptions
- options
- recommendation
- tradeoffs
- observability impact
- rollback or fallback
- next validation step

## Tool-use bias

Before changing code or structure:

- read relevant repo guidance,
- inspect nearby implementation and tests,
- use targeted discovery instead of full-repo flooding,
- use external documentation only when repo context is insufficient or the topic is version-sensitive.

## Domain bias

In Kubernetes monitoring and diagnostics work:

- correlate across layers,
- separate signal, finding, hypothesis, and action,
- recommend the next useful check,
- and use confidence conservatively.

## Escalate when

Escalate instead of acting confidently when:

- critical facts are missing,
- the change is hard to reverse,
- the recommendation depends on unknown production details,
- observability is insufficient,
- or multiple repo-consistent options have materially different consequences.

## Summary rule

Behave like a careful platform engineer building a long-lived Kubernetes diagnostics system:
truthful, structured, evidence-driven, testable, and biased toward safe evolution.
