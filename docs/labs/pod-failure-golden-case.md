# Pod-Failure Golden Diagnosis Case

## Overview

This document describes the first deterministic golden case for the read-only automatic diagnosis loop.

**Case ID**: `pod-failure-readiness-001`  
**Scenario**: Pod with intentionally failing readiness probe  
**Expected Root Cause**: `readiness_probe_failure`

## What This Case Proves

The pod-failure golden case proves that k9b can diagnose a known readiness-probe failure from sanitized lab evidence:

1. **Pod State**: `cnpg-lab-failing-app` is Running but NotReady
2. **Container State**: Container is running (not crashed), but Ready=False
3. **Symptom**: Readiness probe consistently fails (exit code 1)
4. **Evidence**: Events show "Unhealthy" warnings with "Readiness probe failed"

The diagnosis must:
- Correctly identify `readiness_probe_failure` as the category
- Mention readiness probe / NotReady semantics in root cause
- NOT claim image pull, PVC, scheduling, registry, or CNPG operator as primary cause
- NOT propose remediation/mutation (apply, delete, patch, etc.)

## Promotion Status

**Current State**: This is a **representative fixture** case. The case is currently a scaffold for early verification before real promotion.

**Promotion Pending**: Real promotion requires:
1. A successful K3s CNPG Incident Lab Live workflow run
2. Downloaded sanitized artifacts from that run
3. Real GitHub provenance data (run ID, attempt, SHA, artifact name, digest)

**Promotion Method**: When ready, run `promote_diagnosis_golden_case_from_artifact.py` to:
- Regenerate case bundle from actual sanitized artifacts
- Update manifest with real provenance fields
- Change `source_kind` from `representative_fixture` to `live_sanitized_artifact`

**Key Point**: Only sanitized artifacts are used for promotion; raw `lab-artifacts/live/` artifacts are never committed.

## Case Bundle Structure

```
fixtures/diagnosis-golden-cases/pod-failure-readiness/
├── manifest.json              # Case metadata
├── expected.json              # Expected diagnosis output
├── sanitizer-findings.json    # Sanitizer verification results
├── incident/
│   ├── pods.txt               # Pod snapshot during incident
│   ├── events.txt             # Events during incident
│   ├── injected-change.yaml   # Fixture manifest
│   ├── symptom-watch.json     # Symptom progression snapshots
│   ├── cnpg-clusters.json     # CNPG cluster state (required)
│   └── k9b-incident-detail.json
├── baseline/
│   └── pods.txt               # Pod snapshot before incident
└── recovery-or-final/
    ├── pods.txt               # Pod snapshot at end
    └── events.txt             # Events at end
```

## Expected Root Cause

**Category**: `readiness_probe_failure`

**Root Cause Description**: Pod `cnpg-lab-failing-app` is Running but NotReady. The readiness probe consistently fails (exit code 1), preventing the pod from being marked as Ready.

## Intentional Out of Scope

This case does NOT prove:
- General auto-diagnosis system completeness
- Diagnosis of other failure modes (image pull, PVC, scheduling, etc.)
- Remediation or mutation capabilities
- Live cluster interaction (diagnosis runs offline from fixtures)

## Forbidden Conclusions

The diagnosis MUST NOT cite these as primary causes:
- ImagePullBackOff or ErrImagePull
- PVC mount or storage issues
- CNPG operator issues
- Scheduling failures
- Registry authentication failures

The diagnosis MUST NOT propose:
- kubectl apply, kubectl delete, kubectl edit, kubectl patch
- helm upgrade, helm install
- Any cluster mutation

## Running the Diagnosis

```bash
# Run diagnosis on golden case
python scripts/run_diagnosis_offline.py \
    --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness \
    --output-dir /tmp/diagnosis-output

# Verify diagnosis output
python scripts/verify_diagnosis_golden_case.py \
    --expected fixtures/diagnosis-golden-cases/pod-failure-readiness/expected.json \
    --diagnosis /tmp/diagnosis-output/diagnosis.json
```

## Deterministic Adapter Scaffold

**Status**: This is a **deterministic adapter scaffold**, not the production diagnosis loop itself. It verifies the seam by exercising:
- Evidence loading from golden-case bundles
- Deterministic diagnosis matching expected output schema
- Safety enforcement (no forbidden conclusions, no mutation proposals)
- Privacy and provenance verification via actual verifier scripts

The adapter does NOT wire into:
- Incident case-file builder
- One-pass diagnosis orchestrator
- Read-only check runner with fake handlers
- LLM diagnosis path

### Adapter Comparison

| Adapter | Status | Description |
|---------|--------|-------------|
| `run_diagnosis_offline.py` | ✅ Implemented | Standalone fixture harness (preserved for focused tests) |
| `run_golden_case_diagnosis_via_production_loop.py` | ✅ Implemented | **Deterministic scaffold** - exercises seam, not production loop |

### Current Architecture

```
Deterministic Adapter Scaffold (run_golden_case_diagnosis_via_production_loop.py)
├── Validates prerequisites (privacy, provenance, sanitizer)
├── Loads golden-case bundle
├── GoldenCaseEvidenceProvider        - Serves evidence from bundle
├── build_deterministic_diagnosis()   - Uses DeterministicDiagnosisProvider
├── Validates evidence requirements
├── Enforces safety constraints
└── outputs diagnosis.json + summary.md

Golden Case Provider Layer (src/k8s_diag_agent/collect/golden_case_providers.py)
├── GoldenCaseEvidenceProvider         - Reads evidence from bundle
├── create_golden_case_fake_handlers() - Future: wire into read-only check runner
└── DeterministicDiagnosisProvider     - Produces safe, bounded diagnosis
```

### Production Adapter Interface

The production adapter implements the same interface as the fixture harness:

```python
# Production adapter must implement:
def run_diagnosis(case_dir: Path, output_dir: Path) -> dict:
    """
    Run diagnosis on golden case evidence.
    
    Returns dict with same schema as diagnosis.json:
    - category: str
    - root_cause: str  
    - confidence: str
    - description: str
    - evidence_refs: list[str]
    - read_only: bool
    - forbidden_actions_observed: list[str]
    - mutation_proposals_observed: list[str]
    - diagnosis_engine: str
    - next_checks: list[dict]
    """
```

### Key Design Points

1. **Offline Only**: Adapter does not call kubectl, helm, docker, registry, or GitHub APIs
2. **Read-Only**: Adapter cannot propose mutation/remediation actions
3. **Evidence-Backed**: Uses sanitized golden-case evidence only
4. **Safety-First**: Fails if privacy/provenance/sanitizer verifiers fail
5. **Production Seam**: Exercises real k9b modules, not a parallel regex-only path

### ACT-Local Verification

ACT-local verification runs the **production adapter** by default:

```python
# scripts/act_local_checks.py - run_golden_case_check()
production_cmd = [
    str(REPO_ROOT / ".venv" / "bin" / "python"),
    str(production_adapter_path),  # run_golden_case_diagnosis_via_production_loop.py
    "--case-dir", str(case_dir),
    "--output-dir", str(output_dir),
]
```

The standalone fixture harness (`run_diagnosis_offline.py`) is preserved for focused unit tests but is no longer the primary proof path.

## References

- Live lab workflow: `.github/workflows/k9b-cnpg-incident-lab-live.yml`
- Sanitizer: `scripts/sanitize_live_lab_artifacts.py`
- Case builder: `scripts/build_diagnosis_golden_case.py`
- Offline runner: `scripts/run_diagnosis_offline.py`
- Verifier: `scripts/verify_diagnosis_golden_case.py`
