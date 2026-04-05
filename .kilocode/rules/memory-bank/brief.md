# Project Brief

## Project
LLM-based Kubernetes monitoring and diagnostics agent.

## Purpose
Build an agent that helps platform engineers and operators understand abnormal Kubernetes states by separating raw signals from findings, findings from hypotheses, and hypotheses from recommended next checks or actions.

## Primary goals
- Detect and summarize abnormal cluster and workload conditions.
- Correlate evidence across Kubernetes objects, events, metrics, logs, and recent change history.
- Produce grounded hypotheses instead of confident guesses.
- Recommend the next most useful diagnostic step.
- Suggest safe actions when appropriate.
- Stay evolvable as models, integrations, and requirements change.

## Initial scope
Start with a simple, modular system that can:
- ingest structured incident/health input,
- normalize evidence,
- produce a structured assessment,
- express uncertainty,
- and recommend next checks.

Initial development should prioritize fixture-based and test-driven workflows over live-cluster automation.

## Initial non-goals
Not in the first phase:
- autonomous remediation,
- direct mutation of production clusters by default,
- complex multi-service architecture,
- provider-specific lock-in,
- fancy UI before diagnostic correctness,
- unsupported root-cause certainty.

## Default design stance
- Prefer modular monolith over premature microservices.
- Prefer explicit seams over implicit coupling.
- Prefer evidence-first reasoning over heuristic certainty.
- Prefer staged evolution over speculative end-state design.
- Prefer observability and rollback over architectural elegance.

## Primary users
- platform engineers
- SREs
- Kubernetes operators

## Success signals
The project is improving when it becomes better at:
- diagnostic accuracy,
- evidence handling,
- operator usefulness,
- explicit uncertainty,
- rollback-safe guidance,
- observability,
- and eval coverage.

## Governing repo guidance
Primary human-readable entrypoint: `AGENTS.md`

Standing repo rules:
- `.kilocode/rules/00-global.md`
- `.kilocode/rules/10-agent-mission.md`
- `.kilocode/rules/20-architecture-doctrine.md`
- `.kilocode/rules/30-output-contracts.md`
- `.kilocode/rules/40-tool-use.md`
- `.kilocode/rules/50-kubernetes-monitoring-domain.md`

Deeper doctrine:
- `docs/doctrine/`
