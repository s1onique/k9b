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

## Three-Tier Architecture

The golden-case diagnosis system has evolved through three distinct implementations:

### 1. Offline Fixture Harness (`scripts/run_diagnosis_offline.py`)

The original standalone harness that:
- Loads golden-case evidence from bundle
- Produces deterministic diagnosis output
- Validates against expected.json
- Preserved for focused unit tests

### 2. Deterministic Adapter Scaffold

The intermediate adapter that:
- Validates prerequisites (privacy, provenance, sanitizer)
- Loads golden-case bundle
- Uses `GoldenCaseEvidenceProvider` for evidence
- Uses `DeterministicDiagnosisProvider` for diagnosis
- Validates evidence requirements
- Enforces safety constraints
- Outputs diagnosis.json + summary.md

**Note**: This scaffold verifies the seam but does NOT wire into production modules.

### 3. One-Pass Production-Loop Runner (`scripts/run_golden_case_via_one_pass_diagnosis_loop.py`)

The production adapter that exercises **real production modules**:

```
One-Pass Production-Loop Runner
├── Validates prerequisites (privacy, provenance, sanitizer)  [fail-closed on missing]
├── Loads golden-case bundle
├── GoldenCaseEvidenceProvider         - Serves evidence from bundle
├── build_golden_case_case_file()     - Converts bundle to production case-file shape
├── GoldenCaseDeterministicLLMProvider - Injects deterministic LLM seam
├── incident_diagnosis_loop_orchestrator.run_one_read_only_diagnosis_loop_pass()
│   └── Uses injected fake_handlers (NOT live commands)
├── Enforces fake-handler execution    [fail-closed if checks_run=0 or unknown check_id]
└── Enforces safety constraints        [fail-closed on mutation/forbidden conclusions]
```

**Key Enforcements**:

| Check | Behavior |
|-------|----------|
| Missing privacy/provenance scripts | Exit code 3 (fail-closed) |
| `checks_run <= 0` | Raises `FakeHandlerExecutionError` |
| Empty `handler_invocations` | Raises `FakeHandlerExecutionError` |
| Unknown check ID | Raises `FakeHandlerExecutionError` |
| Missing `golden_case_handler=true` | Raises `FakeHandlerExecutionError` |
| Missing `no_kubernetes_call=true` | Raises `FakeHandlerExecutionError` |

### Adapter Comparison

| Adapter | Production Modules | Fake Handlers | Enforcement | Use Case |
|---------|-------------------|---------------|-------------|----------|
| `run_diagnosis_offline.py` | ❌ | ❌ | Safety only | Focused unit tests |
| Deterministic scaffold | ❌ | ❌ | Safety only | Seam verification |
| `run_golden_case_via_one_pass_diagnosis_loop.py` | ✅ | ✅ | Full | ACT-local proof path |

### Key Design Points

1. **Offline Only**: Runner does not call kubectl, helm, docker, registry, or GitHub APIs
2. **Read-Only**: Cannot propose mutation/remediation actions
3. **Evidence-Backed**: Uses sanitized golden-case evidence only
4. **Safety-First**: Fails if privacy/provenance/sanitizer verifiers fail
5. **Fake-Handler Enforcement**: Enforces actual fake-handler execution, not just presence
6. **Production Seam**: Exercises real k9b modules with injected fake handlers

### ACT-Local Verification

ACT-local verification runs the **one-pass production-loop runner** by default:

```python
# scripts/act_local_checks.py - run_golden_case_check()
production_cmd = [
    str(REPO_ROOT / ".venv" / "bin" / "python"),
    str(REPO_ROOT / "scripts" / "run_golden_case_via_one_pass_diagnosis_loop.py"),
    "--case-dir", str(case_dir),
    "--output-dir", str(output_dir),
]
```

The runner proves:
- ✅ Production orchestrator path is exercised
- ✅ Fake handlers are passed to orchestrator
- ✅ Handler invocations are recorded with proper flags
- ✅ Unknown check IDs fail closed
- ✅ Zero checks fails closed
- ✅ Missing verifiers fail closed

## References

- Live lab workflow: `.github/workflows/k9b-cnpg-incident-lab-live.yml`
- Sanitizer: `scripts/sanitize_live_lab_artifacts.py`
- Case builder: `scripts/build_diagnosis_golden_case.py`
- Offline runner: `scripts/run_diagnosis_offline.py`
- Verifier: `scripts/verify_diagnosis_golden_case.py`
