# Verification Profiles

> **Reference documentation.** 
> Step definitions are maintained in `scripts/verify_profiles.py`.
> Run `python scripts/verify_profiles.py --profile <fast|full>` for details.

## Profiles

### Fast Profile

**Description:** Local default profile - high-signal policy and smoke checks

**Target time:** ≤60s (ideal: ≤45s)

**Escalation command:** `./scripts/verify_all.sh --full`

### Full Profile

**Description:** Exhaustive merge-grade verification

**Target time:** ≤300s (ideal: ≤180s)

## Step Registry

### Step Categories

| Category | Description |
|----------|-------------|
| `policy` | Linting, typing, doctrine checks |
| `smoke` | Quick smoke tests |
| `full_suite` | Expensive full test suites |
| `build` | Build and packaging |
| `docs` | Documentation checks |

### All Steps

| Step ID | Lane | Category | Expensive |
|---------|------|----------|-----------|
| agent-pipeline | python | policy | No |
| artifact-immutability | python | policy | No |
| ci-gate-drift | python | policy | No |
| data-model-docs | python | docs | No |
| discovery-logging-hygiene | python | policy | No |
| docker-build-locality | python | policy | No |
| docker-workflow-hygiene | python | policy | No |
| dockerhub-base-images | python | policy | No |
| doctrine | python | policy | No |
| docs-claim-candidates | python | docs | No |
| docs-claim-candidate-coverage | python | docs | No |
| docs-claim-candidate-dispositions | python | docs | No |
| docs-claim-disposition-csv-integrity | python | docs | No |
| docs-claim-disposition-semantic-diff-self-test | python | docs | No |
| docs-claim-candidate-backlog-report-self-test | python | docs | No |
| docs-claim-traceability | python | docs | No |
| docs-claims-registry | python | docs | No |
| docs-inventory | python | docs | No |
| helm-chart | helm | policy | No |
| helm-oci-login | helm | policy | No |
| helm-workflow-hygiene | python | policy | No |
| incident-report-quality | python | policy | No |
| llm-evidence-boundaries | python | policy | No |
| llm-friendly | python | policy | No |
| llm-semantic-injection | python | policy | No |
| mypy | python | policy | No |
| mypy-tests | python | policy | No |
| next-check-sanitization | python | policy | No |
| npm-build | frontend | build | Yes |
| npm-ci | frontend | build | Yes |
| npm-test-ui | frontend | smoke | Yes |
| operator-projection-hygiene | python | policy | No |
| production-readiness-disclaimer | python | policy | No |
| pvc-rollout-policy | python | policy | No |
| ruff-lint | python | policy | No |
| shared-pvc-colocation | python | policy | No |
| structured-output | python | policy | No |
| unit-tests | python | full_suite | Yes |

## Profile Composition

### Fast Profile Steps

1. **Python Lane:**
   - doctrine
   - dockerhub-base-images
   - docker-workflow-hygiene
   - helm-workflow-hygiene
   - docker-build-locality
   - agent-pipeline
   - llm-evidence-boundaries
   - llm-semantic-injection
   - discovery-logging-hygiene
   - pvc-rollout-policy
   - shared-pvc-colocation
   - next-check-sanitization
   - operator-projection-hygiene
   - llm-friendly
   - ruff-lint
   - structured-output
   - mypy
   - mypy-tests
   - ci-gate-drift
   - docs-inventory
   - docs-claims-registry
   - incident-report-quality
   - artifact-immutability
   - production-readiness-disclaimer

2. **Helm Lane:**
   - helm-chart
   - helm-oci-login

3. **Frontend Lane:** (skipped in fast profile)

### Full Profile Steps

All steps listed above, plus:
- unit-tests (Python)
- npm-ci, npm-test-ui, npm-build (Frontend)
- docs-claim-* (heavy docs scans)
- data-model-docs
