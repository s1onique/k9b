# Unit Test Feedback Loop Guidelines

This repo has specific testing friction points that generic guidance ignores:

1. **Many similarly shaped UI panels** - Queue, cluster detail, fleet overview, proposals all use the same structural patterns. Assertions on panel position break when layout changes, even when behavior is correct.

2. **Wording-sensitive workflow semantics** - "Safe candidate", "Approval needed", "Approval required before execution" are workflow signals. Copy changes that rephrase these break tests, even though behavior may be unchanged.

3. **Repeated run-specific payload builders** - `panel-selection-binding.test.tsx` has ~160 lines of inline `createRun123Payload`/`createRun122Payload` that obscure test intent and make LLM repair harder.

4. **LLM-assisted repair loops** - Tests must fail with messages that help LLMs diagnose the issue without needing full context.

These rules exist to address the above friction, not as generic testing advice.

---

## Naming Conventions

### Python
- File: `test_<module_name>.py`
- Class: `<ModuleName>Tests` or `<ModuleName>Test`
- Method: `test_verb_object_condition`

```python
class HealthUITests(unittest.TestCase):
    def test_run_payload_contains_artifacts(self) -> None: ...
    def test_latest_run_discovery_prefers_newer_timestamp(self) -> None: ...
```

### Frontend (TypeScript/Vitest)
- File: `<component>.test.tsx`
- Group by behavior with `describe`
- Name tests after behavior, not implementation

```typescript
describe("Queue workstream filter", () => {
  it("filters queue items by incident workstream", async () => { ... });
});
```

---

## Assertion Types: Semantic Contract vs Copy-Sensitive vs Incidental

### Semantic Contract Assertions
Stable, behavior-focused. Prefer these:

```typescript
screen.getByRole("heading", { name: /Work list/i });
screen.getByLabelText(/Queue status/i);
queueScoped.getAllByRole("article").length === 4;
panel.getByRole("button", { name: /Approve candidate/i });
```

### Copy-Sensitive Assertions
Fragile to UI text changes. Use sparingly, with intent comment:

```typescript
// Copy-sensitive: breaks if wording changes
expect(screen.getByText(/Why not actionable now:/i));
expect(screen.getByText(/Command preview/i));
```

Centralize fragile UI strings in `fixtures.ts` as named constants:

```typescript
// In fixtures.ts
export const UI_STRINGS = {
  QUEUE: {
    APPROVAL_RATIONALE: /Approval required before execution/i,
    SOURCE_REASON: /Source reason:/i,
  },
} as const;

// In test
expect(queueScoped.getByText(UI_STRINGS.QUEUE.APPROVAL_RATIONALE));
```

### Incidental DOM/Layout Assertions
Avoid asserting on DOM order, panel position, or CSS class names:

```typescript
// Bad: relies on DOM structure
expect(panels[2].textContent).toContain("content");

// Bad: relies on exact panel ordering
const panels = screen.getAllByRole("region");
expect(panels[1]).toBeVisible();

// Good: scopes by semantic role
const heading = await screen.findByRole("heading", { name: /Next check plan/i });
const planSection = heading.closest("section");
expect(within(planSection).getByText(/Collect kubelet logs/i)).toBeInTheDocument();
```

**Exception:** When ordering IS the feature (e.g., "orders proposals by confidence"), positional assertions are legitimate.

---

## Scoping Patterns

Use `within()` to scope queries to a specific panel:

```typescript
// Good: scoped to queue panel
const queueScoped = within(queuePanel);
expect(queueScoped.getByText(/Collect kubelet logs/i)).toBeInTheDocument();

// Bad: global query, may match elsewhere
expect(screen.getByText(/Collect kubelet logs/i)).toBeInTheDocument();
```

Reusable scoping helper pattern (already in use in `app.test.tsx`):

```typescript
// In fixtures.ts
export const getQueuePanel = async () => {
  const eyebrow = await screen.findByText(/Next-check queue/i);
  const queuePanel = eyebrow.closest(".next-check-queue-panel");
  if (!queuePanel) throw new Error("Queue panel is not rendered");
  return within(queuePanel);
};
```

---

## Test Data Builders

### Frontend: Centralize in `fixtures.ts`

Inline builders that exceed ~20 lines should be extracted:

```typescript
// Good: extracted builder
export const makeRunWithOverrides = (overrides: Partial<RunPayload> = {}): RunPayload => {
  const base = JSON.parse(JSON.stringify(sampleRun)) as RunPayload;
  return { ...base, ...overrides };
};
```

**Rule:** Do not create inline payload builders in test files. Add to `fixtures.ts`.

**Exception:** Test-specific run variants (e.g., `createRun123Payload` with specific enrichment config) may stay in the test file if they are not reused across files.

### Python: Use Helper Functions for Dict Fixtures

Flat dict literals over ~50 lines become hard to read and maintain:

```python
# Good: builder function
def _sample_deterministic_next_checks() -> dict[str, object]:
    return {
        "clusterCount": 1,
        "clusters": [{ "label": "cluster-a", ... }]
    }
```

Shared fixtures go in `tests/fixtures/`. The `ui_index_sample.py` pattern is already correct.

---

## Mock Helpers: Extract Duplicates

Four test files currently have identical `createStorageMock`:

```typescript
// app.test.tsx, panel-selection-binding.test.tsx,
// queue-workstream-filter.test.tsx, execution-history-filter.test.tsx
// all have this same implementation:

const createStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
};
```

Extract to `fixtures.ts`:

```typescript
// In fixtures.ts
export const createStorageMock = () => { ... };
export const createFetchMock = (payloads: Record<string, unknown>) => { ... };
```

---

## Failure Message Quality

Include context that helps diagnose failures:

```python
self.assertIn("Assessment JSON", labels,
    "Run payload should include assessment artifact link for UI display")
```

```typescript
// Good: explains what is being verified
expect(queueScoped.queryByText(/Approval required/i)).toBeNull();
// Verifies rationale is omitted when priorityRationale field is absent
```

---

## Verification Reporting Rules

When reporting test verification:

1. **Include exact command run** - not "tests pass" but `.venv/bin/python -m pytest tests/unit/test_ui_api.py -v`
2. **Report pass/fail counts** - "30 passed" not "all tests pass"
3. **For red baseline**: show first failure verbatim, classify as:
   - introduced by recent change
   - pre-existing (broken before this work)
   - environment-specific (fails in this environment but not in CI)
4. **Do not encode local environment failures as repo policy**

---

## What NOT to Do

1. Do not assert on DOM order or panel position unless ordering is the feature under test.
2. Do not assert on full component snapshots unless the component is intentionally static.
3. Do not test implementation details (internal state, private methods).
4. Do not create assertions that pass trivially.
5. Do not ignore test performance - avoid `waitFor` in tight loops.

---

## Scope Boundaries

This guide covers Python `unittest` and TypeScript/Vitest + React Testing Library patterns.

It does NOT cover:
- Integration/e2e testing strategy
- Framework migration (e.g., pytest migration)
- CI pipeline changes
- Snapshot test frameworks