# Local Verification Profiles

## Motivation

The previous monolithic verification gate (~180-220s) was too slow for the inner development loop. LLMs routinely skip slow gates, run wrong subsets, or misreport partial verification as "gate green."

This creates a verification culture problem: the gate becomes a ritual, not a feedback loop.

## Solution

Introduce explicit verification profiles with honest scope boundaries:

| Profile | Target Time | Purpose | Evidence Level |
|---------|-------------|---------|----------------|
| `--fast` | ≤45s ideal, ≤60s ceiling | Catch common mistakes quickly | Local development only |
| `--full` | ~180-220s | Exhaustive merge-grade verification | CI/release-grade |

## Profile Semantics

### Fast Profile (`--fast`)

The **local default**. Runs high-signal policy and smoke checks:

**Included:**
- Core linting: `ruff-lint`, `mypy`, `mypy-tests`
- Policy/doctrine checks (see step list)
- File size checks for LLM-friendliness
- Helm quick checks
- Basic docs inventory and claims registry

**Explicitly Excluded:**
- `unit-tests` (full Python test suite)
- `npm-ci`, `npm-test-ui`, `npm-build` (full frontend suite)
- Heavy docs scans (`docs-claim-*`)
- Data model docs verification

**Output Footer:**
```
VERIFICATION PROFILE: fast
Steps run: 21
Elapsed: 38.4s

Skipped (fast profile excludes expensive suites):
  - unit-tests (Python full test suite)
  - npm-ci, npm-test-ui, npm-build (Frontend full suite)
  - docs-claim-* (Heavy docs scans)

For merge-grade verification:
  ./scripts/verify_all.sh --full
```

### Full Profile (`--full`)

The **exhaustive merge-grade gate**. Runs all steps including:
- Full Python unit test suite
- Full frontend build and test suite
- All docs truthfulness scans
- All generated artifact checks

**Output Footer:**
```
VERIFICATION PROFILE: full
Steps run: 35
Elapsed: 198.3s

Full profile: All verification steps executed.
```

## Evidence Policy

**Only `--full` may be called "full gate green."**

Close reports must distinguish:
- `fast profile green` — local development evidence only
- `full gate green` — merge-grade evidence

Example correct close report:
```text
./scripts/verify_all.sh --fast PASS
./scripts/verify_all.sh --full PASS
Full gate green
```

Example incorrect close report:
```text
Gate green  # Ambiguous - which profile?
```

## Changed-File Recommendation

For targeted verification, use:

```bash
python scripts/recommend_verification.py
```

This analyzes changed files and recommends specific checks:

```text
Changed files (3):
  - src/k8s_diag_agent/ui/api_incident_reads.py
  - tests/unit/test_api_incident_reads.py
  - frontend/src/api.ts

Recommended local checks:
  ruff-lint:
    Command: python -m ruff check src tests
    Reason: Changed: src/k8s_diag_agent/ui/api_incident_reads.py
  
  npm-test-ui:
    Command: cd frontend && npm run test:ui
    Reason: Changed: frontend/src/api.ts

Escalation commands:
  Local fast check: ./scripts/verify_all.sh --fast
  Merge-grade verification: ./scripts/verify_all.sh --full
```

## Profile Contract

A verifier ensures profiles maintain their semantics:

```bash
python scripts/verify_profile_contract.py
```

Contract rules:
1. Fast profile must not include expensive steps
2. Fast profile must include core linting and typing
3. Full profile must include all non-excluded steps
4. All steps covered by at least one profile
5. Non-full profiles have escalation commands
6. All step IDs are unique

## Usage Guidelines

### For LLM-Assisted Coding

1. **Start with fast profile**: `./scripts/verify_all.sh --fast`
2. **If fast passes**, run full before claiming green
3. **For targeted work**, use changed-file recommendation first
4. **Never claim "gate green"** without profile name

### For CI/CD

CI workflows must use `--full` (or their own exhaustive gate). The fast profile is explicitly **not merge-grade evidence**.

### For Manual Development

1. Fast profile is the recommended default
2. Run full profile before opening PR
3. Use `--json` for machine parsing: `./scripts/verify_all.sh --fast --json`

## File Structure

```
scripts/
  verify_all.sh           # Canonical gate entrypoint
  verify_profiles.py      # Profile definitions
  recommend_verification.py # Changed-file advisor
  verify_profile_contract.py # Profile contract validator

tests/unit/
  test_verify_profile_contract.py # Profile contract tests

docs/
  doctrine/
    local-verification-profiles.md  # This file
  gate-timings.md                   # Timing benchmarks
  generated/
    verification_profiles.md         # Profile docs reference
```

## Acceptance Criteria

- [x] `./scripts/verify_all.sh --fast` exists and is the recommended local default
- [x] `./scripts/verify_all.sh --full` preserves current exhaustive behavior
- [x] Fast profile target is documented as ≤60s, preferred ≤45s
- [x] Each profile prints profile name, elapsed time, checks run/skipped, escalation command
- [x] A verifier prevents ambiguous success wording
- [x] Profile contract self-tests prove fast excludes expensive suites
- [x] Changed-file recommendation command exists
- [x] CI remains merge-grade (does not silently downgrade to fast)
