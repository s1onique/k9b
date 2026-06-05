# Elm-ish Controller Pattern

**Status**: Stabilized local pattern (2026-05)  
**Used by**: `manualExecution`, `approvalFlow`, `batchExecution`

---

## Purpose

The Elm-ish controller pattern provides a feature-local state machine for app orchestration seams where:

- State transitions are coupled and testable
- Async commands have explicit success/failure lifecycle
- Refresh/reconciliation must not overwrite domain results
- Logic benefits from pure update tests

**This is not a general replacement for simple React hooks or components.** It is a surgical pattern for state-machine-heavy feature seams.

---

## Canonical Examples

```
frontend/src/app/manualExecution/
├── manualExecutionModel.ts        # Model, Msg, Cmd types
├── manualExecutionUpdate.ts        # Pure update()
├── manualExecutionEffects.ts      # Effect runner
├── useManualExecutionController.ts # Thin React adapter hook
└── index.ts                       # Public exports

frontend/src/app/approvalFlow/
frontend/src/app/batchExecution/
```

Each follows the same structure.

---

## Required Shape

### 1. Model (`*Model.ts`)

Feature-local state interface. Owns all state for this feature seam.

```typescript
export interface ExampleModel {
  executingKey: string | null;
  results: Record<string, Result>;
}
export const initialModel: ExampleModel = { executingKey: null, results: {} };
```

### 2. Msg (`*Model.ts`)

Discriminated union of all messages.

```typescript
export type Msg =
  | { type: "ExecuteRequested"; key: string; request: Request }
  | { type: "ExecuteSucceeded"; key: string; result: Result }
  | { type: "ExecuteFailed"; key: string; error: ErrorResult }
  | { type: "ClearResults" };
```

### 3. Cmd (`*Model.ts`)

Discriminated union of side effects emitted by `update()`.

```typescript
export type Cmd =
  | { type: "ExecuteRequest"; key: string; request: Request }
  | { type: "NoOp" };
```

### 4. Pure update() (`*Update.ts`)

```typescript
export function update(model: ExampleModel, msg: Msg): UpdateResult {
  // Returns { model, cmd } - never async, never imports API
}
```

### 5. Effect runner (`*Effects.ts`)

```typescript
export async function runEffect(cmd: Cmd, dispatch: (msg: Msg) => void): Promise<void> {
  switch (cmd.type) {
    case "ExecuteRequest": {
      try {
        const result = await executeApi(cmd.request);
        dispatch({ type: "ExecuteSucceeded", key: cmd.key, result });
      } catch (err) {
        dispatch({ type: "ExecuteFailed", key: cmd.key, error: formatError(err) });
      }
    }
    case "NoOp": { break; }
  }
}
```

### 6. React controller hook (`use*Controller.ts`)

Thin adapter wiring `update()` and effect runner into React.

```typescript
function reducer(model: ExampleModel, msg: Msg): ExampleModel {
  return update(model, msg).model;
}

export function useExampleController(args: Args): Returns {
  const [model, dispatch] = useReducer(reducer, initialModel);

  const dispatchWithEffects = useCallback((msg: Msg) => {
    const { cmd } = update(model, msg);
    dispatch(msg);
    if (cmd.type === "ExecuteRequest") {
      runEffect(cmd, dispatchWithEffects).catch(console.error);
    }
  }, [model, /* deps */]);

  // Return state and handlers from model
  return { /* ... */ };
}
```

### 7. Public exports (`index.ts`)

```typescript
export type { ExampleModel, Msg, Cmd, UpdateResult } from "./exampleModel";
export { initialModel } from "./exampleModel";
export { update } from "./exampleUpdate";
export { runEffect } from "./exampleEffects";
export { useExampleController } from "./useExampleController";
```

---

## Core Invariant

```
Msg -> update(Model, Msg) -> { Model, Cmd }
Cmd -> effect runner -> Msg (dispatched back)
Model -> React controller -> App/UI props
```

### Data flow

1. User action or external event dispatches a `Msg`
2. `update(model, msg)` returns new `model` and `cmd`
3. React state updates with new model
4. If `cmd` is not `NoOp`, effect runner executes it
5. Effect runner dispatches result `Msg` back into step 1

---

## Rules

### update() must be pure

- No API imports
- No async operations
- No timers, DOM, or browser APIs
- Returns `{ model, cmd }` deterministically

### Effects dispatch result messages back

- Effects dispatch `*Succeeded` or `*Failed` messages on completion
- Refresh/reconciliation runs **after** domain success
- Refresh failure does **not** overwrite successful domain state

### Success keys set only on success

- `lastSucceededKey` or similar is set only when API succeeds
- No request-time success semantics

### State shape is the feature-local model

- Reducer state is exactly `ExampleModel` (not wrapped)
- No fake reducer/setter patterns

### No global runtime

- No Redux, Zustand, XState, or event bus for this pattern
- No shared abstraction until duplication is painful and proven

---

## When to Use

Use the Elm-ish controller pattern when:

- State transitions are coupled (one action affects multiple state fields)
- Async command/effect behavior with success/failure lifecycle
- Refresh/reconciliation must run after domain success but not overwrite it
- Multiple setters are currently coordinated in one callback
- Logic benefits from pure `update()` tests
- Feature has coupled request/response/error state machine

## When Not to Use

Do not use for:

- Presentational components
- Prop assembly hooks
- Simple local toggle state
- Simple forms
- Code where ceremony exceeds behavioral complexity

---

## Testing Expectations

| Test type | Target | Purpose |
|-----------|--------|---------|
| Unit | `update(model, msg)` | Verify state transitions |
| Integration | Effect runner | Verify API calls and result dispatch |
| Integration | App/component | Verify wiring for migration-sensitive changes |
| Error case | Refresh failure isolation | Verify domain success is not overwritten |

---

## Migration Checklist

1. Extract local `Model`, `Msg`, `Cmd`, `update()`, and effects to feature directory
2. Wire controller hook into `App.tsx` with same interface if possible
3. Run tests after each extraction
4. Search for legacy hook references before removal
5. Remove legacy hook only after zero active references
6. Document intentional behavior changes

---

## Anti-Patterns

| Anti-pattern | Problem |
|--------------|---------|
| Reducer-shaped callback code | Bypasses `update()` purity |
| Hidden API calls in React handlers after creating `Cmd` | Duplicates effect logic |
| `update()` returning a command that is ignored | Effect never runs |
| Command effect duplicated in controller and effect runner | Inconsistent behavior |
| Refresh running in parallel before domain success | Race condition |
| Refresh failure dispatching domain failure after success | Overwrites success |
| Creating a global framework too early | Premature abstraction |

---

## File Limits

- Each file: **under 500 lines**
- Each module: surgical, focused on one concern
- Avoid broad abstractions until pattern is proven in at least three features

---

## References

- `frontend/src/app/manualExecution/` - Full canonical example
- `frontend/src/app/approvalFlow/` - Example with refresh callback
- `frontend/src/app/batchExecution/` - Example with multi-step refresh

---

*This document describes the current stabilized pattern. Consult the epic notes for history and alternative approaches considered.*
