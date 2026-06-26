# k9b

k9b is an evidence-first Kubernetes incident intelligence layer for teams that want AI-assisted diagnosis without giving up operator control.

It turns Kubernetes operational noise into structured incidents with signals, evidence links, snapshots, review packets, timelines, and bounded read-only diagnosis artifacts.

## What k9b does

* Promotes relevant Kubernetes signals into incident-centered records.
* Captures evidence artifacts and snapshots for reviewable diagnosis.
* Surfaces incident details through an API and UI.
* Supports bounded, read-only AI-assisted diagnosis workflows.
* Preserves uncertainty, limitations, and missing evidence instead of pretending every incident has a complete answer.

## Why it is different

* Evidence-first, not guess-first.
* Incident-centered, not just alert-centered.
* Read-only AI assistance by design.
* Built for operator trust, auditability, and review.
* Quality gates, live-lab checks, and documentation traceability are part of the engineering model.

## Current boundaries

k9b does not currently claim autonomous remediation, universal root-cause certainty, or replacement of observability platforms. It is focused on Kubernetes incident evidence, review, and safe diagnosis support.

## Documentation

* [Product pitch](docs/product/pitch.md)
* [Market positioning](docs/product/market-positioning.md)
* [Architecture](ARCHITECTURE.md)
* [Incident model](docs/data-model/incidents.md)
* [Development and verification](docs/verification.md)
* [Deployment / Helm](docs/in-cluster-deployment.md)

## Verification

Use the repository quality gate before merging changes.

```bash
./scripts/verify_all.sh
```

## Status

- **Active development** — APIs, UI, and workflows are still evolving.
- **Deterministic assessment and review paths** are stable and tested.
- **LLM-assisted branches** are opt-in, auditable, and do not block deterministic flows.
- **Production readiness** — Do not claim production readiness without explicit evidence in the repository.

## License

License: not specified in this repository yet.
