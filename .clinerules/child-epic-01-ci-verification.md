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
- [ ] Check repository status
- [ ] Inspect scripts/verify_all.sh
- [ ] Run local verification to reproduce failure
- [ ] Identify first concrete blocker
- [ ] Fix syntax/runtime issues
- [ ] Verify fix
- [ ] Run full gate again
- [ ] Document results and remaining issues