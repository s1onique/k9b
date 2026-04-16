# Epic: Harden Unit Tests for Scalable Feedback Loops

**Goal:** Faster, more trustworthy human and LLM repair loops as the test suite grows.

**Out of scope:** Integration/e2e, framework migration, CI redesign, broad snapshot changes.

---

## Task 1: Extract `createStorageMock` and `createFetchMock` to `fixtures.ts`

**Goal:** Remove duplicate mock implementations from 4 test files.

**Files:**
- `frontend/src/__tests__/fixtures.ts` - add `export const createStorageMock` and `export const createFetchMock`
- `frontend/src/__tests__/app.test.tsx` - replace local definition with import
- `frontend/src/__tests__/panel-selection-binding.test.tsx` - replace local definition with import
- `frontend/src/__tests__/queue-workstream-filter.test.tsx` - replace local definition with import
- `frontend/src/__tests__/execution-history-filter.test.tsx` - replace local definition with import

**Expected change shape:**
- `fixtures.ts` gains ~40 lines (two helper functions)
- Each test file removes ~15 lines and gains one import line

**Verification:**
```bash
cd /Users/chistyakov/Projects/SPbNIX/k9b/frontend && bun test 2>&1 | tail -5
```

**Non-goal:** Do not refactor `createRunAwareFetchMock` in this task.

---

## Task 2: Extract `getQueuePanel` helper to `fixtures.ts`

**Goal:** Standardize queue panel scoping, reduce boilerplate.

**Files:**
- `frontend/src/__tests__/fixtures.ts` - add `getQueuePanel` helper
- `frontend/src/__tests__/app.test.tsx` - replace inline `getQueuePanel` (lines 50-57) with import

**Expected change shape:**
- `fixtures.ts` gains ~10 lines
- `app.test.tsx` removes ~10 lines, gains import

**Verification:**
Same as Task 1.

---

## Task 3: Parameterize `createRun123Payload` and `createRun122Payload`

**Goal:** Replace ~160 lines of inline builders in `panel-selection-binding.test.tsx` with parameterized factory functions.

**Files:**
- `frontend/src/__tests__/fixtures.ts` - add `makeRunWithStatus(runId, status, provider)` and `makeRunWithExecutionCounts(eligible, attempted, succeeded, failed, skipped)`
- `frontend/src/__tests__/panel-selection-binding.test.tsx` - replace inline builders (lines 71-235) with factory calls

**Expected change shape:**
- `fixtures.ts` gains ~60 lines (two parameterized builders)
- `panel-selection-binding.test.tsx` reduces by ~160 lines, each test becomes 2-3 lines of factory call

**Verification:**
```bash
cd /Users/chistyakov/Projects/SPbNIX/k9b/frontend && bun test 2>&1 | tail -5
```

**Non-goal:** Do not change test assertions. Only refactor builders.

---

## Task 4: Add `UI_STRINGS` constants to `fixtures.ts`

**Goal:** Centralize workflow-critical text strings that are fragile to copy changes.

**Files:**
- `frontend/src/__tests__/fixtures.ts` - add `UI_STRINGS` constant object
- `frontend/src/__tests__/app.test.tsx` - replace fragile text assertions with constants

**Expected change shape:**
- `fixtures.ts` gains ~20 lines (string constants)
- `app.test.tsx` updates ~10 assertions to use constants

**Verification:**
Same as Task 1.

**Non-goal:** Do not centralize ALL text assertions. Only workflow-critical ones (approval signals, empty states, etc.).

---

## Task 5: Add scoped queue panel helper to style guide

**Goal:** Document the preferred panel scoping pattern in the style guide.

**Files:**
- `docs/testing/unit-test-feedback-loop-guidelines.md` - ensure "Scoping Patterns" section clearly shows `getQueuePanel` example

**Verification:**
Style guide content review. No code change.

---

## Epic Completion Rubric

**Done enough when:**
- P0 and P1 are complete (duplicate mocks extracted, inline builders parameterized)
- P2 is complete or nearly complete (fragile text constants added)
- P3 and P4 are optional bonus (scope creep guard)
- `scripts/verify_all.sh` passes, or failures are classified as pre-existing/environment-specific

**Intentionally deferred:**
- Python dict fixture consolidation (pattern established, low urgency)
- Mixed scoping pattern cleanup (currently functional, low risk)
- Frontend snapshot test framework (requires additional setup)
- Any integration test changes (out of scope)

**Hard stop:** Do not refactor tests that are not in the P0-P2 inventory. This epic ends when P0-P2 are done and verification passes.

---

## Execution Order

1. Task 1 (P0: duplicate mocks) - safest, highest reuse
2. Task 2 (P4: queue helper) - low effort, consistent with existing patterns
3. Task 3 (P1: inline builders) - highest impact, most lines reduced
4. Task 4 (P2: text constants) - defensive, reduces future copy-change risk
5. Task 5 (P3: style guide) - documentation, no code change

Tasks 1 and 2 can run in either order. Task 5 is last.