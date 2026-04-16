# Test Cleanup Inventory

Prioritized targets for the "Harden unit tests for scalable feedback loops" epic. Ranking is by feedback-loop leverage, not purity.

---

## P0: Duplicate Mock Helpers

**What hurts today:** Four test files have identical `createStorageMock` and `createFetchMock` implementations. Any change to mock behavior requires editing all four files. LLM repair must identify and update all copies.

**Why it matters:** This is the clearest feedback-loop win. Low risk, low effort, high reuse.

**Why now:** Directly blocks efficient test evolution as the suite grows.

**Why not broader:** Focus on extracting just these two helpers first. Do not expand to other utilities yet.

**Files:**
- `frontend/src/__tests__/fixtures.ts` (add exports)
- `frontend/src/__tests__/app.test.tsx` (update import)
- `frontend/src/__tests__/panel-selection-binding.test.tsx` (update import)
- `frontend/src/__tests__/queue-workstream-filter.test.tsx` (update import)
- `frontend/src/__tests__/execution-history-filter.test.tsx` (update import)

---

## P1: Inline Run Payload Builders in `panel-selection-binding.test.tsx`

**What hurts today:** This file is ~1060 lines. ~160 lines are inline `createRun123Payload` and `createRun122Payload` builders that obscure test intent. Navigation and LLM repair are harder than necessary.

**Why it matters:** Large file with concentrated duplication. Refactoring yields immediate maintainability improvement.

**Why now:** This is the highest-leverage frontend cleanup target.

**Why not broader:** Focus on parameterizing these two builders. Do not attempt to refactor the entire file at once.

**Files:**
- `frontend/src/__tests__/fixtures.ts` (add parameterized builders)
- `frontend/src/__tests__/panel-selection-binding.test.tsx` (replace inline builders)

---

## P2: Fragile Text Assertions in `app.test.tsx`

**What hurts today:** Assertions like `screen.getByText(/Why not actionable now:/i)` and `screen.getByText(/Command preview/i)` will break if UI copy changes, even when behavior is correct.

**Why it matters:** As the suite grows, copy changes become riskier. Centralizing fragile strings makes updates tractable.

**Why now:** Defensive hygiene before the test count grows further.

**Why not broader:** Do not centralize ALL text assertions. Only the workflow-critical ones that signal state (approval needed, empty state messages, etc.).

**Files:**
- `frontend/src/__tests__/fixtures.ts` (add `UI_STRINGS` constants)
- `frontend/src/__tests__/app.test.tsx` (use constants for fragile assertions)

---

## P3: DOM Order Assertions in Filter Tests

**What hurts today:** Tests like "recent-runs review download link" use `document.querySelectorAll(".runs-filter-button")[1]` which depends on button order. Filter label changes break these tests.

**Why it matters:** Filter functionality is correct, but the assertion method is fragile to layout changes.

**Why now:** Low urgency but will become a problem as UI evolves.

**Why not broader:** Do not fix all DOM-order assertions. Focus on filter tests which are high-traffic.

**Files:**
- `frontend/src/__tests__/app.test.tsx` (scoped to filter-related assertions)

---

## P4: Queue Scoping Helper Extraction

**What hurts today:** `getQueuePanel` pattern appears multiple times in `app.test.tsx` with slight variations.

**Why it matters:** Standardizes queue panel access, reduces boilerplate.

**Why now:** Low effort, consistent with existing patterns.

**Why not broader:** Only extract the queue panel helper. Do not generalize to all panel scoping yet.

**Files:**
- `frontend/src/__tests__/fixtures.ts` (add `getQueuePanel` helper)
- `frontend/src/__tests__/app.test.tsx` (use helper)

---

## Not This Sprint

The following are identified but excluded from this epic:

1. **Python dict fixture consolidation** - Pattern is already established in `tests/fixtures/ui_index_sample.py`. Low urgency.

2. **Mixed scoping pattern cleanup** - Some tests use `screen`, others use `within()`. Currently functional, low risk.

3. **Frontend snapshot test framework** - Would require additional setup. Out of scope for this epic.

4. **Integration test coverage gaps** - Integration/e2e excluded per epic scope.

5. **pytest migration** - Framework migration excluded per epic scope.

6. **CI pipeline changes** - CI redesign excluded per epic scope.

---

## Summary: Priority vs Effort

| Priority | Target | Leverage | Effort | Risk |
|----------|--------|----------|--------|------|
| P0 | Duplicate mock helpers | High | Low | Very Low |
| P1 | Inline builders in panel-selection-binding | High | Medium | Low |
| P2 | Fragile text assertions | Medium | Medium | Low |
| P3 | DOM order assertions in filters | Medium | Medium | Low |
| P4 | Queue scoping helper | Low | Low | Very Low |