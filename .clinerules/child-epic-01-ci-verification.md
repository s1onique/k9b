# Child Epic: CI and Verification Hardening

**Parent Epic**: Beta hardening and release readiness  
**Goal**: Make the repository verification path dependable enough to support beta release readiness.

## Scope
1. Inspect verification entrypoints:
   - scripts/verify_all.sh
   - scripts/coverage_all.sh if invoked
   - GitLab CI verify jobs
   - helper scripts

2. Run local verification to reproduce failures

3. Fix concrete syntax/runtime issues in verification scripts

4. Preserve transitional vs strict behavior

5. Improve failure output only where useful

6. Remove flaky verification behavior if encountered

7. Re-run targeted checks after fixes

## Non-goals
- No new product features
- No reopening closed beta contract epics
- No UI redesign
- No broad unrelated refactors
- No quality gate lowering
- No deletion of checks unless obsolete

## Exit Criteria
- Beta verification path is reproducibly green
- Remaining failures explicitly outside this epic
- Fail fast but emit actionable diagnostics
- Local and CI verification aligned
- No beta product guarantees weakened

## Task Progress
- [x] Check repository status
- [x] Inspect scripts/verify_all.sh
- [x] Run local verification to reproduce failure
- [x] Identify first concrete blocker (coverage policy ambiguity)
- [x] Fix syntax/runtime issues (added CI coverage job, documented policy)
- [x] Verify fix (gate passes: ruff OK, unit-tests OK, mypy OK)
- [x] Run full gate again
- [x] Document results and remaining issues

## Coverage Hardening Results (2026-05-13)

### Policy Decision: Report-Only (Non-Blocking)

Coverage reporting is now integrated into CI as a separate non-blocking job:

**Changes made:**
- `.github/workflows/verify.yml`: Added `coverage` job that runs `scripts/run_coverage.sh` and uploads artifacts
- `docs/coverage.md`: Added "Coverage Policy" section documenting the report-only status
- `docs/post-beta-backlog.md`: Updated "Coverage gate in CI" status from "Deferred" to "Report-only"

**Current baseline metrics:**
- Line coverage: ~82% (13,700/16,745 lines)
- Branch coverage: ~67% (3,657/5,452 branches)

**Verification gate status:**
- ruff-lint: PASS (All checks passed!)
- unit-tests: PASS (OK, skipped=20)
- mypy: PASS (Success: no issues found in 375 source files)

**CI changes:**
- New job `coverage` runs independently from `verify` gate
- Does NOT block merge on low coverage
- Artifacts uploaded with 7-day retention
- Coverage summary displayed in CI logs

**Remaining:**
- Threshold enforcement deferred (fail_under=0 in pyproject.toml)
- Next check: add thresholds after baseline coverage stabilizes
