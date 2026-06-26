# k9b product pitch

k9b is an evidence-first Kubernetes incident intelligence layer for teams that want AI-assisted diagnosis without giving up operator control.

## Pitch bullets

* k9b turns Kubernetes noise into incident-centered context. Instead of scattering clues across pods, events, deployments, logs, and manual notes, it promotes relevant signals into a structured incident with identity, severity, status, evidence links, and timeline.

* It is evidence-first, not guess-first. k9b captures snapshots, artifacts, symptoms, failing workloads, warning events, and review packets so every diagnosis can be traced back to concrete cluster evidence.

* It supports safe, read-only AI-assisted diagnosis. The diagnosis loop is designed around bounded budgets, read-only checks, explicit allowed actions, and reviewable outputs, helping operators reason faster without handing remediation control to an LLM.

* It preserves operator trust by being honest about uncertainty. Review packets include limitations, missing evidence questions, confidence signals, and failure states instead of pretending every incident has a complete answer.

* It bridges backend incident intelligence with a usable UI. Operators can inspect incidents, signals, evidence, snapshots, review packets, and diagnosis state from the product interface instead of stitching together CLI output manually.

* Its quality gates are part of the product philosophy. k9b treats verifiers, live-lab workflows, regression tests, documentation traceability, and LLM-friendly file boundaries as first-class engineering constraints, not afterthoughts.

## Positioning line

k9b is the evidence-first Kubernetes incident intelligence layer for teams that want AI-assisted diagnosis without giving up operator control.
