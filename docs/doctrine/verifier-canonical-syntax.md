# Verifier Canonical Syntax Doctrine

This doctrine is canonical for every static verifier that
consumes `scripts.verifiers.verifier_core`. It defines the
exact "canonical shape" the canonical R20 verifier recognises
for the current-run alert-signal ingestion chain in
`src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py::_ingest_alert_signals`.

The doctrine is intentionally narrow: it specifies a small,
verifiable grammar rather than a full Python semantics. It is
the reference for what the canonical R20 verifier accepts.

The doctrine is **structural**, not **policy**: it describes
the AST shape that the verifier-core primitives can recognise.
Verdict (allow / reject / hypothesis) is the policy layer that
sits on top of these structural facts.

## Production source of truth

The canonical chain lives in:

```
src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py
```

The function is `_ingest_alert_signals`. The verifier file
`scripts/verifiers/incident_current_run_promotion_workset01.py`
is the policy consumer that recognises the canonical shape and
emits the production violation records; it is NOT the location
of the production function.

The contract test in
`tests/verifiers/test_canonical_doctrine_matches_production.py`
parses the real production file and proves the documented
major statement sequence is exactly the shape the doctrine
specifies.

## Accepted grammar (positive case)

The canonical chain lives entirely inside one function body
(`_ingest_alert_signals`). The accepted grammar is the
following sequence of statements at the top level of that
body, in source order. Each step is a **structural fact** the
verifier-core primitives recognise; none of these steps
represent a policy decision.

1. **State 0 -- authoritative accumulator declaration.**

   ```python
   workset_refs: list[CurrentRunSignalRef] = []
   ```

   Accepted shape: an `ast.AnnAssign` whose target is a
   `list[T]` typed `Name`, OR an `ast.Assign` whose target is
   a bare `Name`. The value must be an EMPTY list literal.

2. **State 1 -- canonical loop.**

   ```python
   for outcome in persist_result.promotable_outcomes:
   ```

   Accepted shape: an `ast.For` whose `iter` is a direct
   `Attribute` load on a direct `Name` load
   (`persist_result.promotable_outcomes`).

3. **State 2 -- canonical `if`/`elif`/`else: continue` dispatch
   inside the loop.**

   ```python
   if isinstance(outcome, _OutcomeSignalInserted):
       provenance = CurrentRunSignalProvenance.INSERTED
       signal_id = outcome.signal_id
   elif isinstance(outcome, _OutcomeIdentityMatched):
       provenance = CurrentRunSignalProvenance.IDENTITY_MATCHED
       signal_id = outcome.signal_id
   else:
       continue
   ```

   Accepted shape (per arm):

   * `if isinstance(<name>, <type>):` -- single direct-Name
     subject, single direct-Name type, no `and`/`or` chaining.
   * The body is a sequence of direct assignments
     (`provenance = ...`, `signal_id = ...`).
   * `elif isinstance(<name>, <type>):` -- same shape, repeated.
   * The chain MUST terminate with `else: continue`; the
     production grammar requires the fallback `continue` to be
     present so non-matching outcomes skip the append without
     raising.

4. **State 3 -- authoritative append to the same accumulator.**

   ```python
   workset_refs.append(
       CurrentRunSignalRef(
           run_id=run_id,
           signal_id=str(signal_id),
           provenance=provenance,
       )
   )
   ```

   Accepted shape: an `ast.Expr` statement whose value is a
   direct `Method(Name("workset_refs"), "append", ...)` call
   whose argument is a direct constructor call
   `CurrentRunSignalRef(...)`.

5. **State 4 -- unique workset factory.**

   ```python
   current_run_workset: CurrentRunPromotionWorkset = build_current_run_workset(
       run_id=run_id,
       source_identity=source_instance,
       references=tuple(workset_refs),
   )
   ```

   Accepted shape: an `ast.AnnAssign` whose target is a
   `CurrentRunPromotionWorkset` typed `Name`, whose value is a
   direct `Name("build_current_run_workset")` call with the
   following keyword arguments (in any order):

   * `run_id=<direct Name load>`,
   * `source_identity=<direct Name load>`,
   * `references=Name("workset_refs")` -- the `workset_refs`
     accumulator from State 0 wrapped in a `tuple(...)` call.
     The grammar REQUIRES `references=tuple(workset_refs)`,
     NOT the bare `workset_refs` list. A bare-list reference
     is rejected because the factory contract requires an
     immutable sequence.

6. **State 5 -- unique signal-ID projection.**

   ```python
   current_run_signal_ids: tuple[str, ...] = tuple(
       current_run_workset.signal_ids
   )
   ```

   Accepted shape: an `ast.AnnAssign` whose target is a
   `tuple[str, ...]` typed `Name` and whose value is the
   `tuple(...)` projection from
   `current_run_workset.signal_ids` (i.e. the value MUST be a
   direct `Attribute` load on `current_run_workset` wrapped in
   `tuple(...)`).

7. **State 6 -- direct dispatcher declaration.**

   ```python
   dispatch_result: IncidentPromotionResult | Exception | None = None
   ```

   Accepted shape: an `ast.AnnAssign` whose target is the
   union-typed dispatcher result. The RHS MUST be the constant
   `None`.

8. **State 7 -- direct dispatcher call with
   `signal_ids=current_run_signal_ids`.**

   The dispatcher call MUST be a direct
   `Name("promote_alert_signals_scoped_for_accumulator")`
   call with at least these keyword arguments:

   * `signal_ids=Name("current_run_signal_ids")` -- the
     projection from State 5 is the canonical argument;
     passing any other name is rejected because the backend
     must read from the canonical workset projection, not the
     raw list.
   * `runs_dir=<direct Name load>`,
   * `health_run_id=<direct Name load>`,
   * `source_identity=<direct Name load>`,
   * `accumulator=None`,
   * `cluster_context=<direct Name load>`.

   The dispatcher call lives inside a `try:` block whose
   `except Exception` arm captures the typed exception into
   `dispatch_result`. This means the actual dispatcher call
   is nested under a `try` statement at the body level; the
   verifier recognises this structural fact and does not
   conflate the `try` with the append-side forbidden
   compound-under placement (which would place an
   authoritative append inside the try).

   `dispatch_result = batch.promotion_result` follows the
   dispatcher call directly, in source order, after the call
   resolves without exception.

## State ordering

The canonical body MUST begin with the accumulator
declaration (State 0). The loop (State 1) MUST follow in
source order. The canonical-arm `if`/`elif`/`else: continue`
dispatch (State 2) MUST be the only statements inside the
loop. The authoritative append (State 3) MUST be the final
statement inside the loop. The unique workset factory (State
4), signal-ID projection (State 5), and direct dispatcher
declaration (State 6) MUST follow in source order AFTER the
loop. The dispatcher call (State 7) MUST follow the dispatcher
declaration in source order.

The verifier does NOT require any particular arm count beyond
the first; arms may be added or removed as long as each
surviving arm satisfies the canonical-arm grammar AND the
chain terminates with `else: continue`.

## Permitted `if`/`elif` layout

Per arm:

* `if isinstance(<name>, <type>)` -- single direct-Name
  subject, single direct-Name type, no `and`/`or` chaining.
* `elif isinstance(<name>, <type>)` -- same shape, repeated.
* Body: a sequence of direct assignments; each RHS must be
  a direct-Name or direct-Attribute load of the canonical
  provenance / signal-id mapping.
* The chain MUST terminate with `else: continue`. The
  fallback `continue` is mandatory in the production grammar
  so non-matching outcomes skip the append without raising.
  The grammar and the production tests both REQUIRE this
  trailer; an `else: pass` or absent `else` is rejected.

Forbidden inside any arm:

* Nested `if` arms.
* `try`/`except*` around any arm.
* `with` around any arm.
* `for`/`while` around any arm.
* Star expansion in any assignment or append.
* `getattr(...)` anywhere in the body.
* `partial(...)` (per Option A) anywhere in the body.

## Direct-name requirements

The verifier recognises ONLY direct `Name` loads and direct
`Attribute` loads. The following are NOT direct and are
rejected by the verifier-core primitives:

* `obj.attr.method()` -- the call is on an attribute, not a
  direct `Name`.
* `getattr(obj, "name")` -- dynamic lookup, recognised by
  `detect_dynamic_getattr` as a structural fact.
* `globals()["name"]` -- indirect load.
* `partial(g, x)` -- recognised by `detect_partial_application`
  (Option A: bare name only).
* `lambda: g` -- a Lambda at body level, recognised by
  `detect_lambdas`.
* `functools.partial(g, x)` -- NOT detected by the current
  bare-name detector; if the doctrine later chooses to reject
  attribute-access shapes, a SEPARATE detector must be added
  (this is the Option B extension).

## Forbidden nested compound placements

The canonical chain forbids every nested compound statement
inside the body of `_ingest_alert_signals` that would wrap an
authoritative append or the dispatcher call. The full
forbidden list:

| Compound | Where forbidden |
|----------|----------------|
| `for` / `async for` (non-canonical) | wrapping the append or dispatcher |
| `while` | wrapping the append or dispatcher |
| `with` / `async with` | wrapping the append |
| `try` / `try*` | wrapping the append (NOT the dispatcher: see below) |
| nested `if` (inside arm) | inside any arm body |
| `def` / `async def` at body level | any |
| `lambda` at body level | any |

The canonical chain DOES place the dispatcher call under a
`try:` block. This is the only place where `try` is
permitted: it scopes the **exception capture** path, not the
append. The verifier recognises this structural fact and does
not conflate it with the append-side forbidden compound-under
placement.

The `detect_nested_compound_under` primitive recognises every
forbidden placement without descending into the arm body. The
single canonical top-level `for` loop is NOT a nested
compound.

## Verifier-core primitives (structural facts)

The following primitives back the doctrine. They are
**structural facts** about the production AST -- they do not
encode a policy verdict. Each primitive has at least one
non-test consumer inside the verifier-core package itself.

* `statement_value(stmt)` -- bounded extractor for the
  immediate expression owned by a statement (Expr, Assign,
  AnnAssign, Return). Returns `None` for compound statement
  shapes.
* `single_direct_name_call(stmts, call_name)` -- first direct
  Name call in source order at the top level of the supplied
  statement sequence. Does NOT descend into `If.body`,
  `Try.body`, `for`/`while`/`with` body, `Match` cases,
  nested function definitions, lambdas, or any other compound
  statement.
* `detect_partial_application(body)` -- first location of a
  direct `partial(...)` call, regardless of binding (Option
  A: purely syntactic).
* `detect_dynamic_getattr(body)` -- first location of a direct
  `getattr(...)` call across the four recognised statement
  shapes (Expr, Assign, AnnAssign, Return).
* `detect_star_expansion(call)` -- first location of `*args`
  or `**kwargs` inside the supplied call.
* `detect_nested_compound_under(parent, target_lineno)` --
  first recognised compound (Try/For/While/With/If/Match)
  whose body contains a statement at or after
  `target_lineno`.
* `is_callable_collection_literal(node)` -- true when `node`
  is a non-empty literal list/tuple/dict of Names. Empty
  `refs: list[T] = []` is the canonical accumulator
  initializer and must NOT be reported.
* `top_level_function(tree, name)` -- first-match top-level
  lookup returning `None` when absent.
* `parse_function_body(func)` / `function_body_statements(func)`
  -- the doctrine-mandated body accessor.
* `parse_strict(source)`, `parse_path(path)`, `read_source(path)` --
  AST parsing and source-reading helpers.
* `VerInfrastructureError`, `SourceLocation`, `location_of(node)` --
  the broken-verifier signal, the deterministic (line,
  column) record, and the AST-to-location helper.

The core does NOT provide:

* call-graph primitives,
* alias-flow resolution,
* closure or fixed-point analysis,
* value-tracking,
* a `Diagnostic` record or `format_violation` helper (the
  production R20 verifier has its own detector output
  vocabulary and does not consume the verifier-core
  `Diagnostic` dataclass),
* a subcode vocabulary (the production R20 verifier does
  not emit any of the 23 historical `SUB_*` constants; they
  have been removed from the public API in CORRECTION05),
* a `SOURCE_LINE_DIRECTNESS_BOUND` /
  `enforce_directness_bound` budget (the canonical grammar is
  bounded by grammar, not by line count).

## Reference

* Production shape: `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py::_ingest_alert_signals`.
* Policy consumer: `scripts/verifiers/incident_current_run_promotion_workset01.py`.
* Contract tests: `tests/verifiers/test_verifier_core.py`.
* Production self-tests: `tests/verifiers/test_incident_current_run_promotion_workset01.py`.
* Paired-regression companions:
  `tests/verifiers/test_incident_current_run_promotion_workset01_r98_r99.py`,
  `tests/verifiers/test_incident_current_run_promotion_workset01_r102_r103_r104.py`.
* Doctrine-to-production contract test:
  `tests/verifiers/test_canonical_doctrine_matches_production.py`.
* Reconciliation markdown:
  `docs/reports/r20-verifier-test-reconciliation.md`.

## Adding new shapes or primitives

If a new canonical-syntax shape needs to be recognised:

1. Add the primitive to the appropriate focused module
   (`detectors.py`, `directness.py`, `lookups.py`).
2. Add focused positive and negative contract tests to
   `test_verifier_core.py` AND a paired-regression fixture to
   the production self-test companion.
3. Document the new shape in this doctrine.

If a primitive becomes redundant (e.g. a detector with no
remaining reachable shape), remove it from the package and
add a deletion note to this doctrine. Do NOT silently delete
primitives -- they may still behave as policy hooks for
downstream consumers.

A new `SUB_*` subcode, `Diagnostic` record, or
`SUBCODE_REACHABILITY` matrix MUST NOT be reintroduced in this
ACT or any subsequent ACT: the production R20 verifier does
not emit those codes, and reintroducing them would resurrect
the speculative public surface that CORRECTION05 removed.
