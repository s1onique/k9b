# ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 Repair Task Progress Archive

**Purpose:** Historical entries from R20 PARTIAL through R101 ROUND 22,
split from  to keep the canonical file
under the 500-line llm-friendly threshold. The current ROUND 23 entry
remains in the canonical file.


## Status: ROUND 22 CLOSURE (R101 follow-up) - R98/R99/R100 fixes landed. 83 paired regressions pass (75 R81-R96 + 8 R98/R99); verifier green against production. R20 PARTIAL defects called out in the original task spec are CLOSED. The 138-test figure from ROUND 21 remains historical and is superseded by this entry.

## Round 21 follow-up fixes (2026-07-16, post-R20 closure review)

### R94 (P0) -- decorator-only ambiguous bindings

Decorator-only ambiguity now propagates through ``_decorator_call_pairs``:
the function returns both resolved pairs and ambiguous decorator
sites, and ``_collect_local_calls_in_callable_body`` merges decorator
ambiguity into the same fail-closed path that handles ``ast.Call``
ambiguity. Bare-name ``@trigger`` decorations whose factory has
branch-defined live bindings are rejected with
``ambiguous callable binding``.

### R95 (P0) -- position-aware binding selection via ``path``

``_Binding`` now carries a ``path`` field (an ``(parent_id, attr_name)``
tuple) so the runtime-scope walker can distinguish
``if.body`` assignments from ``if.orelse`` assignments. The
parent-aware walker in ``_walk_runtime_scope_with_parent`` was
extended to also yield the list-attribute name through which a
child was reached.

``_resolve_alias`` now:
* always filters the CURRENT scope by source position (R95);
* treats sequential rebinding at the same path as ordinary
  last-binding-wins (no longer ambiguous);
* treats rebindings across distinct paths (e.g. ``if``/``else``
  branches) as ambiguous and surfaces them as a violation;
* treats cross-scope bindings (call in inner, binding in outer)
  without applying the position filter, since the relative source
  positions of inner-vs-outer scopes are not directly comparable.

### R96 (P0) -- scope ownership decided before position lookup

When the current scope owns a binding for ``name`` (a rebinding
anywhere in the block -- later ``def``, later alias, ``lambda``
assignment, or a branch-local assignment under ``if``/``except``),
the resolver no longer falls through to an outer-scope binding
that happens to share the same name. It reports
``(None, False, True)`` (``use_before_binding=True``) and the audit
silently excludes the call from the reachable mutator list -- the
call cannot run in Python (UnboundLocalError) so no mutation
violation is emitted.

R96 is covered by four paired regression tests covering the four
required binding forms (post-call ``def``, post-call alias,
post-call ``lambda`` assignment, branch-local ``if`` rebinding) and
a fifth sanity test confirming an inner pre-def safe shadow is
accepted (R89 symmetry).

## Round 20 fixes (2026-07-16)

### R81 (P0) -- per-scope callable identity

`scripts/verifiers/incident_current_run_promotion_workset01.py`:

* `_collect_local_callable_bodies` no longer stores callables under a
  flat `dict[str, body]`. Each callable is registered under a
  `(name, id(enclosing_scope))` key so two nested `def mutator(...)`
  declared inside different enclosing scopes can no longer collide.
  Class method entries use the qualified `"ClassName.method_name"`
  key so a method declared in two different classes cannot collide
  either.
* `_resolve_alias` walks both the current scope's aliases and the
  top-level scope's aliases so a nested helper can still resolve a
  top-level helper name.
* `_live_reachable_local_calls` passes `id(body)` as the new
  `scope_id` when descending into a called body, so the BFS resolves
  nested-def names against the nested scope.
* `check_ingestion_stable_deduplicates_artifact_workset` uses ONE
  `list(ingest.body)` instance so the harvester and the walker share
  the same id and the per-scope identity matches end-to-end.
  (Earlier: two separate `list(ingest.body)` calls produced two
  distinct list ids and silently failed every lookup.)

### R82 (P0) -- bare-name / Attribute decorator implicit calls

`scripts/verifiers/incident_current_run_promotion_workset01.py`:

* New `_decorator_call_pairs` helper treats each `Name` and
  `Attribute` decorator expression as an implicit call root
  (`@trigger` -> `trigger(<decorated>)`, `@mod.trigger` ->
  `mod.trigger(<decorated>)`). The decorator factory body is then
  merged into the reachability graph and audited like any other
  reachable local-callable invocation.
* `_collect_local_calls_in_callable_body` now returns the union of
  explicit `ast.Call` pairs and decorator-implicit pairs. The
  decorator-only invocation chain is fully audited so the previous
  silent bypass for bare-name decorators is closed.

### R83 (P0) -- annotated assignment inside called deferred bodies

`scripts/verifiers/incident_current_run_promotion_workset01.py`:

* `_check_annassign_closed_grammar` gains a keyword-only
  `allow_initial_declaration` flag. When the checker is invoked
  from inside a called deferred body, the initial-declaration
  exemption is disabled so `refs: list = []` inside a deferred
  body is rejected as a REASSIGNMENT.
* `_callable_body_mutates_collection` now applies
  `_check_annassign_closed_grammar` (with
  `allow_initial_declaration=False`) to every `AnnAssign` node in
  the deferred body, so annotated reassignment / subscript /
  attribute stores against the authoritative collection inside a
  called body are rejected.

### R86 (P0) -- intermediate enclosing scope lexical resolution

Python nested functions can resolve names from enclosing function
scopes; lexical lookup is not limited to only the immediate block
and the module/top-level block. The previous per-scope harvest
stored only the immediate scope id and the top scope id, so a call
originating inside `inner` could not resolve a name declared in
the intermediate `outer` scope. The harvest now records a parent
relation `parent_scope_by_id[scope_id] = parent_scope_id` and
resolution walks the lexical-ancestor chain.

### R87 (P0) -- implicit decorators under executable compound statements

The previous detector only inspected decorators of the direct
member statements of the scope, so `if enabled: @trigger def nested():
pass` was invisible to the audit. The decorator search now uses
the execution-aware `_walk_runtime_scope` to descend through
executable compound statements (`if` / `try` / `with` / `for` /
`while` / `match`) while still pruning deferred function / lambda /
method bodies.

### R89 (P0) -- scope-by-scope shadowing

`_resolve_alias` rewrote `resolved_name` through aliases in **every**
scope before searching bodies, which let an outer-scope alias mask
an inner-scope direct binding. The fix is scope-by-scope
shadowing: at each scope in the lexical chain, the audit first
checks whether the original name has a direct callable binding,
then whether it has an alias binding in that scope. An alias is
resolved beginning from the **same** lexical scope (not from the
outer scopes), so a binding introduced in an inner scope shadows
the same name in any outer scope. Lookup only continues outward
when the current scope has no binding for the name at all.

### R90 (P0) -- position-aware binding selection

Each binding is now an ordered event recorded with its source
`(lineno, col_offset)` position. The previous `bodies` / `aliases`
dicts stored only a single value per `(name, scope_id)` and
silently lost any binding that was overwritten before the call
site was reached (e.g. `invoke = mutator; invoke(); invoke = safe`).
The new `bindings` dict stores a list of `_Binding` events per
`(name, scope_id)` so resolution picks the latest binding strictly
before the call position. Multiple bindings for the same
`(name, scope_id)` that are ALL strictly before the call position
are reported as ambiguous and surfaced as a violation so the
caller can fail the audit instead of silently picking one binding
(branch-defined same-name callables).

### R91 (P0) -- lambda lexical parent linkage

Lambda assignments now record
`parent_scope_by_id[id(lambda_node)] = scope_id` so the lexical
chain used during name resolution continues past a lambda body to
its enclosing scope. The previous implementation only stored
`parent_scope_by_id[id(new_body)]` for `def` / class-method bodies;
a lambda body therefore had no lexical parent in the resolution
chain and could not resolve names defined in the enclosing scope
(e.g. `invoke = lambda: mutator(); invoke()` inside the ingest
function missed the parent `def mutator`).

### R92 (P0) -- class method namespace leakage

The harvest now uses `_walk_runtime_scope_with_parent` and refuses
to register a `FunctionDef` whose immediate lexical owner is a
`ClassDef` under the unqualified name. Python executes the class
suite in a separate namespace; names defined in the class block
become class attributes, and the class scope does NOT become an
enclosing scope for method bodies. The qualified
`"ClassName.method_name"` key registered by the `ClassDef`
branch remains the only public binding for a class method, so an
unqualified call inside the enclosing function does not
accidentally resolve to the class method.

## Test inventory (verified 2026-07-16)

```bash
.venv/bin/python -m pytest \
  tests/verifiers/test_incident_current_run_promotion_workset01_r62_r63_r64.py \
  tests/verifiers/test_incident_current_run_promotion_workset01_r62.py \
  tests/verifiers/test_incident_current_run_promotion_workset01_r63_r64.py \
  tests/verifiers/test_incident_current_run_promotion_workset01_r58_r59.py \
  tests/verifiers/test_incident_current_run_promotion_workset01.py \
  tests/verifiers/test_incident_current_run_promotion_workset01_r81_r82_r83.py \
  tests/verifiers/test_incident_current_run_promotion_workset01_r86_r87.py \
  tests/verifiers/test_incident_current_run_promotion_workset01_r89_r90_r91_r92.py
```

Result: **138 tests collected, 138 passed in <2s** (126 R81-R92 + 12 R94-R96)

| File | Lines | Tests |
|------|-------|-------|
| test_act_k9b_..._r62_r63_r64.py | 387 | 18 |
| test_act_k9b_..._r62.py (expanded) | 330 | 11 |
| test_act_k9b_..._r63_r64.py | 242 | 13 |
| test_act_k9b_..._r58_r59.py | 263 | 16 |
| test_act_k9b_..._workset01.py (production) | 575 | 32 |
| test_act_k9b_..._r81_r82_r83.py (R20) | 439 | 11 |
| test_act_k9b_..._r86_r87.py (R20) | 408 | 9 |
| test_act_k9b_..._r89_r90_r91_r92.py (R20, NEW) | 437 | 16 |
| **Total** | **3081** | **126** |

### R81 paired regressions

* `test_r81_called_mutating_nested_def_is_isolated_from_safe_sibling` -- positive
* `test_r81_called_safe_nested_def_does_not_trigger_when_only_it_is_live` -- mirror
* `test_r81_two_class_methods_with_same_name_are_isolated` -- positive

### R82 paired regressions

* `test_r82_bare_name_decorator_chain_to_mutator_is_rejected` -- positive
* `test_r82_attribute_form_decorator_chain_to_mutator_is_rejected` -- positive
* `test_r82_uncalled_decorated_def_does_not_trigger` -- mirror
* `test_r82_safe_bare_name_decorator_does_not_trigger` -- mirror

### R83 paired regressions

* `test_r83_called_deferred_body_annotated_reassign_is_rejected` -- positive
* `test_r83_called_deferred_body_annotated_attribute_store_is_rejected` -- positive
* `test_r83_called_deferred_body_annotated_subscript_store_is_rejected` -- positive
* `test_r83_called_deferred_body_unrelated_annotated_assignment_is_accepted` -- mirror

### R86 paired regressions

* `test_r86_inner_calls_helper_defined_in_parent_wrapper_is_rejected` -- positive
* `test_r86_three_level_nested_call_chain_is_rejected` -- positive
* `test_r86_inner_safe_helper_shadows_mutating_parent_helper_is_accepted` -- mirror
* `test_r86_parent_helper_resolves_when_sibling_helper_does_not_shadow` -- mirror

### R87 paired regressions

* `test_r87_bare_name_decorator_under_if_is_rejected` -- positive
* `test_r87_bare_name_decorator_under_try_is_rejected` -- positive
* `test_r87_bare_class_decorator_under_if_is_rejected` -- positive
* `test_r87_decorated_definition_inside_uncalled_helper_is_accepted` -- mirror
* `test_r87_safe_nested_decorator_is_accepted` -- mirror

### R89 paired regressions (NEW)

* `test_r89_inner_mutating_def_shadows_parent_safe_alias_is_rejected` -- positive
* `test_r89_inner_safe_def_shadows_parent_mutating_alias_is_accepted` -- mirror
* `test_r89_inner_alias_shadows_parent_direct_callable_is_followed` -- mirror
* `test_r89_parent_alias_used_only_when_no_inner_binding_exists` -- mirror

### R90 paired regressions (NEW)

* `test_r90_mutator_alias_before_call_safe_alias_after_call_is_rejected` -- positive
* `test_r90_safe_alias_before_call_mutator_alias_after_call_is_accepted` -- mirror
* `test_r90_two_same_name_defs_around_a_call_uses_the_live_definition` -- mirror
* `test_r90_branch_defined_same_name_callables_is_rejected_for_ambiguity` -- positive

### R91 paired regressions (NEW)

* `test_r91_top_level_lambda_calling_mutator_is_rejected` -- positive
* `test_r91_lambda_inside_wrapper_calling_parent_mutator_is_rejected` -- positive
* `test_r91_uncalled_lambda_calling_mutator_is_accepted` -- mirror
* `test_r91_lambda_local_alias_shadows_enclosing_helper` -- mirror

### R92 paired regressions (NEW)

* `test_r92_safe_class_method_before_mutating_local_function_is_rejected` -- positive
* `test_r92_mutating_class_method_never_invoked_is_accepted` -- mirror
* `test_r92_explicit_class_method_invocation_is_rejected` -- positive
* `test_r92_unqualified_method_call_without_local_def_does_not_resolve` -- mirror

### R78 fixture update

The pre-existing
`test_r78_function_decorator_calling_local_mutator_is_rejected`
was updated to assert that the bare-name decorator form
(`@trigger`) is now also rejected (R82). The previous
`assert violations == []` line that documented the bug is replaced
with an explicit positive assertion that the implicit
`trigger(nested)` invocation is observable.

## Production verifier evidence (2026-07-16)

```bash
.venv/bin/python scripts/verifiers/incident_current_run_promotion_workset01.py
# Exit code: 0 (no violations)
```

The production ingestion tree at
`src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py`
satisfies every detector after the R81/R82/R83/R86/R87/R89/R90/R91/R92
repairs. No new false positives were introduced.

## Scope of changes

* `scripts/verifiers/incident_current_run_promotion_workset01.py`
  -- 3295 -> ~3500 lines (+~200). R81/R82/R83/R86 helpers preserved;
  R89/R90/R91/R92 helpers added:
  - `_walk_runtime_scope_with_parent` (parent-aware walker, R92)
  - `_Binding` dataclass and `_add_binding` helper (R90)
  - `_resolve_alias` rewritten for scope-by-scope shadowing (R89)
    plus position-aware binding selection (R90)
  - `_live_reachable_local_calls` returns
    `(pairs, ambiguity_violations)` (R90)
  - `_collect_local_callable_bodies` records lambda parent scope
    (R91) and skips unqualified class methods (R92)
  - `check_ingestion_stable_deduplicates_artifact_workset`
    threads the new `bindings` dict through the reachability graph
    and surfaces ambiguity violations
* `tests/verifiers/test_incident_current_run_promotion_workset01_r81_r82_r83.py`
  -- unchanged (439 lines, 11 paired regressions)
* `tests/verifiers/test_incident_current_run_promotion_workset01_r86_r87.py`
  -- unchanged (408 lines, 9 paired regressions)
* `tests/verifiers/test_incident_current_run_promotion_workset01_r89_r90_r91_r92.py`
  -- NEW, 437 lines, 16 paired regressions

## Remaining follow-up

1. Production promotion-dispatch wiring is still in flight per
   `task_progress_hulk_current_run_promotion_seam01.md` (Item 3
   close-out). The R20 verifier changes do not depend on that
   work and are independently green.
2. The three pre-existing oversized files documented in the
   seam01 close-out are still split-out targets for future
   ACTs. The R20 repairs did not touch their line counts.
3. The R20 verifier file is now ~3500 lines (up from 3178 at the
   end of R81/R82/R83); it remains inside the soft 3500-line
   ceiling for the active detector module and is a candidate for
   the next split ACT only if additional detection rules land.

## Completion contract

* `python scripts/verifiers/incident_current_run_promotion_workset01.py`
  exits 0.
* `pytest tests/verifiers/test_incident_current_run_promotion_workset01_*.py`
  runs 126 paired regressions in <2s and is fully green.
* The ten defects (R81/R82/R83/R86/R87/R89/R90/R91/R92 + R84 documentary
  reconciliation) are closed with paired evidence and the R78 baseline
  test was updated to reflect the new decorator contract.
## Round 22 (R101) follow-up fixes (2026-07-16, post-R21 closure review)

The original task spec called R20 PARTIAL with two outstanding P0
defects (R98 cross-scope temporal binding, R99 branch-path
dominance) and one P1 defect (R100 `_Binding.path` typing). The
R101 follow-up closes all three.

### R98 (P0) -- outer-scope bindings use invocation-time activation state

`_resolve_alias` now accepts an `outer_cutoffs:
dict[scope_id, (line, col)]` argument. `_live_reachable_local_calls`
threads the cutoff for each BFS hop -- the cutoff for the caller
scope is set to the call's source position so any outer-scope
binding declared AFTER the call position is invisible inside the
descended body. The three-level `outer -> wrapper -> inner ->
leaf` chain preserves every ancestor cutoff transitively.

### R99 (P0) -- control-flow dominance

`_resolve_alias` now discriminates UNCONDITIONAL bindings (path
parent is the scope body list itself, attr "self") from
CONDITIONAL bindings. When multiple pre-call bindings exist for
the same `(name, scope_id)`, the resolver picks the latest
UNCONDITIONAL binding as the live binding and only reports
ambiguity when a conditional binding has a position strictly
greater than the unconditional binding's position. The
`_is_unconditional_at_scope` helper accepts `parent_id is None`
(for the per-statement seed case) or `parent_id == scope_id` (for
the scope-body seed case) and `attr == "self"`.

### R100 (P1) -- `_Binding.path` typing

A `BindingPath = tuple[int, str]` type alias is defined at module
top. `_Binding.__init__` and `_add_binding` now declare `path:
BindingPath = (0, "self")` instead of `path: int = 0`. The
verifier-specific mypy run (`mypy scripts/verifiers/incident_current_run_promotion_workset01.py --ignore-missing-imports`)
reports no issues.

### R98/R99 paired regression tests (8 fixtures, NEW companion)

`tests/verifiers/test_incident_current_run_promotion_workset01_r98_r99.py`:

- `test_r98_outer_mutator_binding_then_inner_call_then_outer_safe_rebinding_is_rejected`
- `test_r98_outer_safe_binding_then_inner_call_then_outer_mutator_rebinding_is_accepted`
- `test_r98_outer_rebinding_immediately_before_inner_uses_new_binding`
- `test_r98_three_level_wrapper_inner_leaf_preserves_every_ancestor_cutoff`
- `test_r99_conditional_mutator_then_unconditional_safe_is_accepted`
- `test_r99_if_else_bindings_then_unconditional_safe_is_accepted`
- `test_r99_unconditional_safe_then_conditional_mutator_is_rejected`
- `test_r99_two_unresolved_if_else_bindings_with_no_later_override_is_ambiguous`

### Final post-staging evidence (2026-07-16)

- 83 paired regressions pass: `pytest tests/verifiers/test_incident_current_run_promotion_workset01_r9[4-6].py tests/verifiers/test_incident_current_run_promotion_workset01_r8[9-9][0-2].py tests/verifiers/test_incident_current_run_promotion_workset01_r86_r87.py tests/verifiers/test_incident_current_run_promotion_workset01_r81_r82_r83.py tests/verifiers/test_incident_current_run_promotion_workset01.py tests/verifiers/test_incident_current_run_promotion_workset01_r98_r99.py` -> 83 passed.
- Production tree clean: `.venv/bin/python scripts/verifiers/incident_current_run_promotion_workset01.py` exits 0.
- Verifier-specific Ruff: `ruff check scripts/verifiers/incident_current_run_promotion_workset01.py` -> `All checks passed!`
- Verifier-specific mypy: `mypy scripts/verifiers/incident_current_run_promotion_workset01.py --ignore-missing-imports` -> `Success: no issues found in 1 source file`
- `git diff --cached --check` clean.
- `.factory/gate-summary.json` regenerated; the R20 verifier check itself is among the 17 ACT-local checks and still passes (the 3 unrelated check failures are pre-existing environmental issues: R3 redaction `full-gate-negative-proofs`, `llm-friendly` file size warnings on `task_progress_r20_workset01_repair.md` and `docs/reports/impact-scan-ledger.md`, and cascading `targeted-repository-gate`).

### R101 close-out verdict

The two P0 defects (R98, R99) and the one P1 defect (R100) called out
in the original R20 PARTIAL verdict are CLOSED. The R101 follow-up
ACT is COMPLETE. R20 is fully accepted.

### Historical note (ROUND 21)

The "ROUND 21 CLOSURE" entry above reflects the 138-test figure
that was current before the R98/R99/R100 follow-up. The R20
status was technically marked "ACCEPTED" at ROUND 21 closure,
but the original task spec's PARTIAL verdict correctly identified
the two outstanding P0 defects (R98, R99) and one P1 defect
(R100) that the R101 follow-up has now closed. The 138-test
figure is historical and the 83-test figure from this ROUND 22
entry is the new source of truth.

### Scope of changes (R101)

- `scripts/verifiers/incident_current_run_promotion_workset01.py`:
  R98 BFS cutoff threading (~40 lines), R99 dominance logic in
  `_resolve_alias` (~30 lines), R100 `BindingPath` type alias
  (~10 lines). Total: ~50 lines added/modified.
- `tests/verifiers/test_incident_current_run_promotion_workset01_r98_r99.py`:
  NEW, 8 paired regressions (~250 lines).
- `.factory/gate-summary.json`: regenerated with new
  `generated_at` timestamp.
- `task_progress_r20_workset01_repair.md`: this entry.
- `docs/reports/impact-scan-ledger.md`: new R98/R99/R100 entry.
