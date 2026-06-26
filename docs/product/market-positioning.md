# k9b market positioning

The Kubernetes AI-SRE market is moving quickly. Many tools emphasize autonomous investigation, root-cause analysis, alert workflows, ChatOps, remediation suggestions, or automated remediation.

k9b should not compete by claiming to be "the AI that fixes production." Its stronger and more honest position is safer: structure the incident, collect the evidence, preserve uncertainty, and help the human operator make the next decision.

## Differentiation bullets

* k9b is not trying to be "the AI that fixes production." While much of the market is racing toward autonomous remediation, k9b's wedge is safer: collect the right evidence, structure the incident, explain uncertainty, and help the human operator make the next call.

* Purpose-built for Kubernetes incident evidence, not generic observability chat. k9b focuses on Kubernetes-native incident shape: affected workloads, events, snapshots, suggested checks, review packets, evidence artifacts, and incident timeline.

* A trust layer for AI-assisted SRE. Instead of treating the LLM response as the product, k9b treats it as one reviewable artifact among many: bounded, read-only, attached to evidence, and explicit about missing context.

* Designed for platform teams who care about auditability and safety boundaries. k9b's market position is strongest where teams need explainable diagnosis, reproducible evidence capture, and non-destructive workflows before they are ready to permit autonomous remediation.

* Built with product-quality engineering discipline, not just a demo loop. The same philosophy behind the incident model shows up in the codebase: regression tests, live-lab verification, quality gates, documentation traceability, and explicit handling of partial or failed evidence collection.

## Market stance

k9b complements observability, alerting, and AI assistant tools. It is not a metrics backend, log platform, pager, or autonomous remediation engine. Its job is to make Kubernetes incidents reviewable, evidence-backed, and safer to diagnose with AI assistance.

## Claims to avoid

Avoid claiming:

* autonomous remediation
* guaranteed root cause
* production-targeted autopilot-style automation
* replacement for observability platforms
* replacement for incident management systems
* broad multi-cloud / VM / database / SaaS incident coverage unless implemented and verified

## Claims we can make honestly

It is reasonable to claim:

* evidence-first Kubernetes incident intelligence
* structured incident records
* reviewable diagnosis artifacts
* bounded read-only AI-assisted diagnosis
* operator-controlled workflows
* explicit uncertainty and missing-evidence handling
* quality-gated engineering discipline
