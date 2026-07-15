# ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 Progress Report

Round-10 Item 2: deterministic, provenance-aware collapse of repeated
same-run signal references before constructing the strict immutable
workset.

Parent: `ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01`.

Status: **complete** in scope of Item 2 (after reviewer audit). The
reviewer identified three findings that have been closed in-place
(runtime provenance bypass, the clamp-vs-raise on the collapse metric,
and the production-path telemetry proof) and the report has been
re-written to reflect the corrected evidence. No commits or pushes
performed.

## 1. Before

* The typed `CurrentRunPromotionWorkset` correctly admitted both
  `SignalInserted` and `SignalIdentityMatched` observations, but the
  factory produced one `CurrentRunSignalRef` per promotable
  persistence outcome, deduplicated only at the strict
  `__post_init__` step.
* When the same alert appeared twice in one snapshot, persistence
  produced `SignalInserted(X)` for the first observation and
  `SignalIdentityMatched(X)` for the second. Both refs were passed
  to the factory, the factory sorted and passed both into the
  strict aggregate, and `__post_init__` raised
  `ValueError("... duplicate signal_id ...")` before collapse
  metrics could be computed.
* The intended collapse metric
  `current_batch_identity_collapse_count` was therefore
  unobservable on the failure path; the dispatcher never received
  the request, and the run still emitted `event="complete"`.
* `promotable_signal_ids` was the only available raw-count proxy
  (a legacy projection). It did not differentiate the same-id
  collapse from the historical-duplicate scenario.

## 2. Reviewer findings closed in this revision

Three reviewer findings were closed against the prior commit's
implementation:

### Finding 1 - D7 runtime provenance bypass (closed)

`CurrentRunSignalProvenance` is a `:class:`StrEnum``. Plain strings
value-equal valid enum members, so the prior check
``ref.provenance not in PROMOTABLE_PROVENANCE`` allowed
``provenance="inserted"`` to pass.

The factory and the strict aggregate now both apply an explicit
``isinstance(ref.provenance, CurrentRunSignalProvenance)`` check
via the helper `_is_promotable_provenance`. Two parametrized tests
now cover both raw-string bypass paths:

```python
@pytest.mark.parametrize("raw_provenance", ["inserted", "identity_matched"])
def test_raw_string_provenance_rejected_by_factory(self, raw_provenance: str): ...
@pytest.mark.parametrize("raw_provenance", ["inserted", "identity_matched"])
def test_raw_string_provenance_rejected_by_direct_aggregate(self, raw_provenance: str): ...
```

### Finding 2 - the metric should fail loudly, not clamp (closed)

The prior code computed:

```python
current_batch_identity_collapse_count = max(
    0,
    raw_promotable_reference_count - unique_workset_signal_count,
)
```

Clamping hid a future contract regression. The production site now
raises :class:`CurrentRunWorksetCardinalityError` whenever
``unique_workset_signal_count > raw_promotable_reference_count``,
and the subtraction is performed unguarded when the invariant
holds. The new exception class lives in
``src/k8s_diag_agent/collect/current_run_promotion_workset.py``
with public ``raw_reference_count`` /
``unique_workset_signal_count`` attributes.

### Finding 3 - the same-alert-twice production path was not exercised (closed)

The prior integration tests:
1. fed **one alert** through `_ingest_alert_signals` (no collapse)
2. ran two manually constructed `CurrentRunSignalRef` values
3. ran two `AlertSignal` values through `persist_alert_signals`
   followed by manual reference construction.

That did not satisfy the spec's
"`_ingest_alert_signals` -> ... -> dispatch exactly 1 ID"
end-to-end requirement.

The new file
`tests/integration/test_act_k9b_hulk_current_run_workset_stable_collapse01_production_regression.py`
includes a **continuous production-path proof** (Option B from
the reviewer). It patches
`adapt_snapshot_to_alert_signals` to return two
`AlertSignal` objects sharing canonical identity (the same shape
the production orchestrator would hand to persistence when the
within-batch dedupe is bypassed by a future change), then runs the
real `_ingest_alert_signals` -> `persist_alert_signals` ->
`build_current_run_workset` -> scoped dispatcher pipeline and
asserts:

* dispatcher's `signal_ids` keyword has exactly one entry;
  that entry equals the canonical identity;
* `alert-signals-written` carries `signals_written=1`,
  `signals_duplicates=1`, `signals_failed=0`;
* `alert-signals-promoted` (or `-via-backend`) carries
  `persisted_signal_count=2`, `unique_artifact_signal_count=1`,
  `current_batch_identity_collapse_count=1`,
  `requested_signal_count=1`,
  `promotion_scope="explicit_current_run_signal_ids"`;
* the new telemetry collapse metric equals
  `persisted_signal_count - unique_artifact_signal_count`.
* no `ValueError` from the workset factory propagates out
  (failure short-circuits the test if it does).

The persistence-level pair test
(`test_persistence_outcome_pair_yields_one_workset_member`) is kept
as a non-regression anchor for the
`SignalInserted` + `SignalIdentityMatched` outcome pair shape.

The workset-layer mirror
(`test_same_alert_twice_workset_contract`) is kept as the
canonical non-regression assertion that does not depend on the
adapter stub.

## 3. After - Implementation

### Normalization location

The collapse belongs in the validated factory
(`CurrentRunPromotionWorkset.build` /
`build_current_run_workset`). Direct aggregate construction via
`CurrentRunPromotionWorkset(...)` remains strict and still
rejects duplicate memberships, so only callers that explicitly
opt into the same-id collapse go through the factory.

### Explicit provenance precedence

A single production precedence table
(`_PROVENANCE_PRECEDENCE` in
`src/k8s_diag_agent/collect/current_run_promotion_workset.py`):

```text
CurrentRunSignalProvenance.INSERTED        : 0  (stronger)
CurrentRunSignalProvenance.IDENTITY_MATCHED : 1  (weaker)
```

`_stronger_reference(a, b)` returns the lower-rank entry. The
helper is the single source of truth so the semantic winner stays
explicit and testable, never hidden behind incidental enum
ordering.

### Deterministic ordering

After collapse, references are sorted by
`(provenance_rank, signal_id)` via the `_deterministic_order`
helper. The dispatcher receives the same backend request for any
input permutation that yields the same logical workset.

### Validation order

The factory now performs strict validation BEFORE any collapse work
so a duplicate valid reference cannot be used to conceal an invalid
one:

1. `_validate_raw_reference(run_id, ref)` -- empty `signal_id`,
   mismatched `run_id`, or non-promotable provenance short-circuits
   the factory. The provenance check uses
   `_is_promotable_provenance` which performs the explicit
   ``isinstance`` guard.
2. `_collapse_same_signal_references(references)` -- groups by
   `signal_id` and resolves precedence collisions.
3. `_deterministic_order(collapsed)` -- sorts by
   `(provenance_rank, signal_id)`.
4. Final `cls(run_id, signals=ordered, source_identity=...)` --
   triggers `__post_init__`, which still verifies the aggregate
   invariant (run_id match, empty signal_id rejection, runtime
   provenance guard, and duplicate `signal_id` rejection).

### Metric derivation

`current_batch_identity_collapse_count` is derived from the
actual factory input length minus the unique workset membership
count via the focused production helper
`_calculate_identity_collapse_count` in
`src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py`:

```python
def _calculate_identity_collapse_count(
    *,
    raw_reference_count: int,
    unique_workset_signal_count: int,
) -> int:
    if unique_workset_signal_count > raw_reference_count:
        raise CurrentRunWorksetCardinalityError(
            raw=raw_reference_count,
            unique=unique_workset_signal_count,
        )
    return raw_reference_count - unique_workset_signal_count
```

The legacy `promotable_signal_ids` projection is no longer the
source of the raw count. The relationship
`raw_reference_count >= unique_workset_signal_count` holds
structurally; a violation is now a `CurrentRunWorksetCardinalityError`
rather than a silently-clamped zero.

### Dispatcher request authority

The backend request continues to come exclusively from the
normalized workset:

```python
current_run_signal_ids = tuple(current_run_workset.signal_ids)
```

The dispatcher is fed from the workset's deterministic tuple. No
parallel identity list is reintroduced. The backend's strict
rejection of duplicate `signalIds` is unchanged.

## 4. Required semantic rules

```text
INSERTED(X) + IDENTITY_MATCHED(X)     -> one INSERTED(X)
IDENTITY_MATCHED(X) + INSERTED(X)     -> one INSERTED(X)
INSERTED(X) + INSERTED(X)             -> one INSERTED(X)
IDENTITY_MATCHED(X) + IDENTITY_MATCHED(X)
                                       -> one IDENTITY_MATCHED(X)
```

Different `signal_id`s never collapse together; mismatch run ids,
empty signal ids, raw-string provenance, and unsupported
provenance values fail closed.

## 5. Tests

### New / updated unit tests

In `tests/unit/test_current_run_promotion_workset.py`:

| Test id | Subject |
|---|---|
| `TestStableCollapseSemantics::test_inserted_and_matched_same_id_collapse_to_inserted` | 8.1 INSERTED + IDENTITY_MATCHED -> one INSERTED |
| `TestStableCollapseSemantics::test_inserted_then_matched_equals_matched_then_inserted` | 8.2 input-order equivalence |
| `TestStableCollapseSemantics::test_three_matched_references_collapse_to_one` | 8.3 repeated matched collapse |
| `TestStableCollapseSemantics::test_two_inserted_references_collapse_to_one` | 8.4 repeated inserted collapse |
| `TestStableCollapseSemantics::test_different_signal_ids_do_not_collapse` | 8.5 different IDs do not collapse |
| `TestStableCollapseSemantics::test_direct_aggregate_with_duplicates_remains_rejected` | 8.6 direct aggregate still rejects |
| `TestStableCollapseSemantics::test_run_id_mismatch_in_factory_is_rejected` | 8.7 run mismatch fail-closed |
| `TestStableCollapseSemantics::test_unsupported_provenance_cannot_be_concealed_by_duplicate` | 8.8 invalid provenance fail-closed |
| `TestStableCollapseSemantics::test_empty_signal_id_cannot_be_concealed_by_duplicate` | 8.8 empty signal id fail-closed |
| `TestStableCollapseSemantics::test_raw_string_provenance_rejected_by_factory[inserted/identity_matched]` | D7 hardening: factory rejects value-equal strings |
| `TestStableCollapseSemantics::test_raw_string_provenance_rejected_by_direct_aggregate[inserted/identity_matched]` | D7 hardening: aggregate rejects value-equal strings |
| `TestStableCollapseSemantics::test_empty_signal_id_rejected_by_strict_aggregate` | D7 / D9 hardening: empty signal id rejected in aggregate |
| `TestStableCollapseSemantics::test_permutations_produce_identical_worksets` | 8.9 120-element permutation stability |
| `TestStableCollapseSemantics::test_empty_input_builds_empty_workset` | 8.10 empty input |
| `TestStableCollapseSemantics::test_single_unique_reference_builds_one_membership` | 8.10 single ref |
| `TestStableCollapseSemantics::test_multiple_unique_references_build_deterministic_membership` | 8.10 mixed provenance ranking |
| `TestStableCollapseSemantics::test_thirty_three_unique_identity_matched_references_remain_thirty_three` | non-regression for 33 historical ids |

In `tests/unit/test_loop_alertmanager_identity_collapse.py` (new file):

| Test id | Subject |
|---|---|
| `TestCalculateIdentityCollapseCount::test_valid_cases_return_raw_minus_unique[7 cases]` | Helper arithmetic correctness; uses the actual production helper |
| `TestCalculateIdentityCollapseCount::test_cardinality_violation_raises_at_metric_site` | D9 regression: real helper raises on cardinality violation |
| `TestCalculateIdentityCollapseCount::test_zero_raw_with_zero_unique_does_not_raise` | Boundary: empty batch doesn't raise |
| `TestCalculateIdentityCollapseCount::test_raw_equals_unique_does_not_raise` | Boundary: equality is not strict-greater |

### New / updated integration tests

`tests/integration/test_act_k9b_hulk_current_run_workset_stable_collapse01_production_regression.py`:

| Test id | Path exercised |
|---|---|
| `TestSameIdentityCollapseProductionPath::test_persist_alert_signals_yields_inserted_and_matched_for_same_id` | Continuous production-path proof: real `_ingest_alert_signals`, real `persist_alert_signals`, real `build_current_run_workset`, real scoped dispatch; patched adapter exposes two same-identity signals (Option B) |
| `TestSameIdentityCollapseProductionPath::test_same_alert_twice_workset_contract` | Workset-layer non-regression anchor (does not depend on adapter stub) |
| `TestSameIdentityCollapseProductionPath::test_persistence_outcome_pair_yields_one_workset_member` | Real `persist_alert_signals` producing `SignalInserted` + `SignalIdentityMatched` outcome pair |

The integration test uses **monkeypatch** (not manual module
assignments) to patch both ``adapt_snapshot_to_alert_signals`` and
the ``K9B_INCIDENT_PROMOTION_MODE`` / ``K9B_STORE_BACKEND`` env
vars. pytest restores them automatically after the test.

### Adjacent tests re-run

All adjacent tests stay green:

| Command | Result |
|---|---|
| `pytest tests/unit/test_current_run_promotion_workset.py` | 33/33 PASS |
| `pytest tests/unit/test_loop_alertmanager_identity_collapse.py` | 10/10 PASS |
| `pytest tests/integration/test_act_k9b_hulk_current_run_workset_stable_collapse01_production_regression.py` | 3/3 PASS |
| `pytest tests/integration/test_act_k9b_hulk_current_run_promotion_seam01_production_regression.py` | 11/11 PASS |
| `pytest tests/integration/test_act_k9b_incident_current_run_promotion_workset01_scheduler.py` | 3/3 PASS |
| `pytest tests/integration/test_act_k9b_incident_current_run_promotion_workset01_e2e.py` | 3/3 PASS |
| `pytest tests/unit/test_incident_alert_signal_snapshot_adapter.py` | passing |
| `pytest tests/unit/test_current_run_promotion_seam01_verifier.py` | 6/6 PASS |
| `ruff check <all files I touched>` | All checks passed |
| `mypy src/k8s_diag_agent/collect/current_run_promotion_workset.py src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py` | no issues found in 2 source files |
| `python scripts/verify_current_run_promotion_seam01.py` | exit 0; "OK: ... no violations" |
| `git diff --check` | no whitespace conflicts |

## 6. Invariant table (D1-D12) - corrected

| Id | Statement | Evidence (corrected after reviewer audit) |
|---|---|---|
| D1 | The workset factory accepts repeated same-run references. | `TestStableCollapseSemantics::test_inserted_and_matched_same_id_collapse_to_inserted`, `test_three_matched_references_collapse_to_one`, `test_two_inserted_references_collapse_to_one`, `test_different_signal_ids_do_not_collapse`. |
| D2 | The final workset contains each signal id at most once. | `_collapse_same_signal_references` plus `__post_init__`; covered by 8.1-8.5. |
| D3 | INSERTED dominates IDENTITY_MATCHED for the same signal id. | `_PROVENANCE_PRECEDENCE` table + `_stronger_reference`; covered by `test_inserted_and_matched_same_id_collapse_to_inserted` (asserts `workset.signals[0].provenance == INSERTED`). |
| D4 | Collapse is independent of input order. | `_deterministic_order` + `_collapse_same_signal_references`; covered by `test_inserted_then_matched_equals_matched_then_inserted` and `test_permutations_produce_identical_worksets` (120 permutations of a 5-element fixture). |
| D5 | Different signal ids never collapse together. | `_collapse_same_signal_references` keys on `signal_id`; covered by `test_different_signal_ids_do_not_collapse`, `test_multiple_unique_references_build_deterministic_membership`. |
| D6 | Run mismatches are rejected before or during normalization. | `_validate_raw_reference` runs before any collapse work; covered by `test_run_id_mismatch_in_factory_is_rejected`, `test_run_id_mismatch_rejected` (direct aggregate). |
| D7 | Unsupported provenance cannot be hidden by a valid duplicate; raw string provenance masquerading as ``CurrentRunSignalProvenance`` is rejected by both the factory and the strict aggregate. | After reviewer finding: `_is_promotable_provenance` performs an explicit ``isinstance`` check (closed the StrEnum bypass). Covered by `test_unsupported_provenance_cannot_be_concealed_by_duplicate`, `test_empty_signal_id_cannot_be_concealed_by_duplicate`, `test_raw_string_provenance_rejected_by_factory[inserted/identity_matched]`, and `test_raw_string_provenance_rejected_by_direct_aggregate[inserted/identity_matched]`. **D7 is now closed.** |
| D8 | Direct aggregate construction with duplicate membership remains invalid. | `__post_init__` rejection logic preserved; covered by `test_direct_aggregate_with_duplicates_remains_rejected`. |
| D9 | Collapse metrics equal raw references minus unique members and the cardinality invariant is enforced (not clamped). | After reviewer finding: the production metric computation raises :class:`CurrentRunWorksetCardinalityError` on a violation. The mathematical relationship `collapse_count = raw - unique` is asserted in the integration test's `assert promoted_event["current_batch_identity_collapse_count"] == raw_persisted - unique_artifacts`. The helper itself is exercised directly via `tests/unit/test_loop_alertmanager_identity_collapse.py::test_cardinality_violation_raises_at_metric_site` so a regression that decoupled the metric from the raise would actually fail the test. **D9 is now closed.** |
| D10 | Backend signal ids come exactly from the normalized workset. | `current_run_signal_ids: tuple[str, ...] = tuple(current_run_workset.signal_ids)`; the spy assertion `assert sent_ids[0] == canonical_identity` and `assert len(sent_ids) == len(set(sent_ids))` in `test_persist_alert_signals_yields_inserted_and_matched_for_same_id` proves the dispatcher received exactly one entry from the workset (and that one entry equals the canonical identity). |
| **D11 (truthful wording)** | **One ingestion execution receiving two same-identity adapted signals dispatches one signal ID in the continuous production chain.** | After reviewer finding: the new `test_persist_alert_signals_yields_inserted_and_matched_for_same_id` runs the real `_ingest_alert_signals` -> `persist_alert_signals` -> `build_current_run_workset` -> scoped dispatcher pipeline in one execution, asserting `signals_written=1`, `signals_duplicates=1`, `current_batch_identity_collapse_count=1`, `requested_signal_count=1`, and `promoted_event["signals_written"]==1` / `signals_duplicates==1` / `current_batch_identity_collapse_count==1` / `requested_signal_count==1` on the real production events. **D11 is now closed via Option B.** The test intentionally does NOT use a snapshot containing the same alert twice because the within-batch dedupe in `adapt_snapshot_to_alert_signals` would prevent two same-identity signals from reaching persistence; Option B replaces the adapter with a deterministic two-same-identity stub. |
| D12 | Thirty-three distinct identity-matched references remain 33 members. | Covered by `test_thirty_three_unique_identity_matched_references_remain_thirty_three` and `test_33_identity_matched_signals_admitted`. |

## 7. Verification outcomes

### SEAM01 verifier

```bash
.venv/bin/python scripts/verify_current_run_promotion_seam01.py
OK: current-run promotion seam verifier found no violations
Exit code: 0
```

### Inherited `incident_current_run_promotion_workset01` verifier

```bash
.venv/bin/python scripts/verifiers/incident_current_run_promotion_workset01.py
ingestion: ingestion does not reference persisted.artifact_identity
ingestion: ingestion does not stable-deduplicate via dict.fromkeys(...)
Exit code: 1
```

The inherited verifier still fails on the same obsolete
sentinels referenced in the task brief (`persisted.artifact_identity`,
`dict.fromkeys(...)`). Per task instructions, this verifier is not
updated in this ACT. These failures predate this ACT.

### `scripts/verify_all.sh --act-local`

Result: every check I touched passes. The inherited
`incident_current_run_promotion_workset01` verifier still fails
on the same obsolete sentinels as before; the ruff / mypy /
llm-friendly checks flag pre-existing issues in files I did not
modify (e.g. `tests/unit/test_seam01_final_summary_consistency.py`
unused import). No NEW failures introduced by this ACT.

The gate is reported as **FAIL** with respect to the inherited
verifier, exactly as the original ACT brief instructs.

### mypy on changed files

`tests/unit/test_current_run_promotion_workset.py` shows two
`unused-ignore` warnings at lines 113 and 131. These predate this
ACT (the `# type: ignore[arg-type]` markers are on preexisting
tests `test_conflicts_do_not_enter_workset` and
`test_persistence_failures_do_not_enter_workset`).

## 8. Worktree

Item 2 contributed 5 paths under this ACT:

| Path | Status | Notes |
|---|---|---|
| `src/k8s_diag_agent/collect/current_run_promotion_workset.py` | previously untracked, content edited | added `_PROVENANCE_PRECEDENCE`, `_stronger_reference`, `_validate_raw_reference`, `_collapse_same_signal_references`, `_deterministic_order`, `CurrentRunWorksetError`, `CurrentRunWorksetCardinalityError`, `_is_promotable_provenance`; rewrote `build` to use the new normalization helpers; updated `__post_init__` with the runtime isinstance provenance guard and empty signal_id rejection |
| `src/k8s_diag_agent/health/loop_alertmanager_snapshot_signals.py` | modified (tracked) | `_calculate_identity_collapse_count` helper; ingestion loop now calls the helper rather than `max(0, ...)`; raises `CurrentRunWorksetCardinalityError` on violation |
| `tests/unit/test_current_run_promotion_workset.py` | previously untracked, content edited | added `TestStableCollapseSemantics` covering items 8.1-8.10 plus the 33-distinct historical non-regression, plus the reviewer-requested D7 / D9 hardening tests |
| `tests/integration/test_act_k9b_hulk_current_run_workset_stable_collapse01_production_regression.py` | new (untracked) | continuous production-path proof (Option B), workset-layer mirror, and persistence-pair non-regression |

Additional new file:

| Path | Status | Notes |
|---|---|---|
| `tests/unit/test_loop_alertmanager_identity_collapse.py` | new (untracked) | direct unit tests for `_calculate_identity_collapse_count` so a regression that decoupled the metric from the raise would actually fail the test |

The **combined ACT worktree contains 22 changed paths:
3 modified tracked and 19 untracked. All are unstaged.

Files NOT modified by this ACT (carry-over from prior rounds):

* `src/k8s_diag_agent/health/loop_runner_execute.py` (R7)
* `src/k8s_diag_agent/incident_alert_signal_snapshot_adapter.py`

Per task instructions, **no commits or pushes were made.**

### `git diff --check`

Exit code 0; no whitespace conflicts.

## 9. Remaining work (Round-10 Items 3-9) - NOT addressed by this ACT

This ACT closes only Round-10 Item 2 in the requested scope. The
remaining Round-10 items remain:

* **Item 3** - dispatcher-outcome wiring
* **Item 4** - diagnosis-selection orchestration
* **Item 5** - `StoreScanPolicy` public-entry migration
* **Item 6** - semantic-verifier replacement
* **Item 7** - closing the deeper 33-duplicate continuous-chain
  regression
* **Item 8** - `PromotionDispatchError` rename
* **Item 9** - final ACT-wide closure report and gate refresh

This ACT introduces no behavior changes that overlap those items.

## 10. Stop conditions check

* Persistence can produce two different immutable identities with
  the same `signal_id` - NOT observed.
* Provenance precedence is already defined differently elsewhere -
  NOT observed.
* Collapsing references would discard source identity or
  schema-version information - NOT observed.
* Backend request ordering has an incompatible canonical contract
  - NOT observed.
* Telemetry fields cannot represent raw and unique counts truthfully
  - NOT observed.

No stop condition fires. The closure criteria specified in §16 of
the task brief are satisfied:

* repeated same-run references no longer cause workset construction
  failure - YES
* the final workset remains unique and immutable - YES
* inserted provenance deterministically wins over matched
  provenance - YES
* input permutations produce identical worksets - YES
* invalid run / provenance references still fail closed - YES
* the dispatcher receives exactly one copy of every signal id -
  YES (asserted at the production dispatch site)
* collapse telemetry is mathematically consistent - YES
  (asserted in the integration test)
* one ingestion execution receiving two same-identity adapted signals dispatches one signal ID - YES (Option B
  continuous proof)
* the 33-distinct-identity path remains unchanged - YES
* focused tests, Ruff, mypy and `git diff --check` pass on changed
  files - YES
* inherited verifier failures are reported truthfully - YES
* no commits or pushes were made - YES

## 11. Reviewer-finding ledger

| Finding | Status | Evidence |
|---|---|---|
| Raw string `"inserted"` / `"identity_matched"` provenance masquerades through `StrEnum` value-equality | Closed | `_is_promotable_provenance` is run by both the factory and `__post_init__`; parametrized `test_raw_string_provenance_rejected_by_factory` and `test_raw_string_provenance_rejected_by_direct_aggregate` cover both raw-string paths |
| `max(0, raw - unique)` silently clamps a contract violation | Closed | Replaced with `if unique > raw: raise CurrentRunWorksetCardinalityError(...)`; `tests/unit/test_loop_alertmanager_identity_collapse.py::test_cardinality_violation_raises_at_metric_site` invokes the **actual production helper** (``_calculate_identity_collapse_count``) and the integration assertion `collapse_count == raw_persisted - unique_artifacts` enforces the new contract |
| Same-alert-twice production path was exercised only via disconnected tests | Closed (Option B) | The new `test_persist_alert_signals_yields_inserted_and_matched_for_same_id` runs the real `_ingest_alert_signals` -> `persist_alert_signals` -> `build_current_run_workset` -> scoped dispatcher pipeline in one execution, asserting the real production events and the dispatcher spy |
| (Reviewer finding on the D9 metric-site test being a false positive) | Closed | The original `test_cardinality_violation_raises_at_metric_site` in `tests/unit/test_current_run_promotion_workset.py` was removed because it manually raised the exception class without exercising the production arithmetic. The new replacement lives in `tests/unit/test_loop_alertmanager_identity_collapse.py` and invokes the real `_calculate_identity_collapse_count` helper, so any future regression (e.g. restoration of `max(0, ...)` or try/except swallow) is caught here |
| D11 report wording | Closed | Report uses the truthful Option-B wording: "*One ingestion execution receiving two same-identity adapted signals dispatches one signal ID*" instead of the misleading "*One snapshot containing the same alert twice*". The within-batch dedupe in `adapt_snapshot_to_alert_signals` makes the literal "same alert twice" scenario unreachable at the adapter level. |
| Integration test hermeticity | Closed | The integration test now uses `pytest.MonkeyPatch.setattr` and `monkeypatch.setenv` (with `K9B_INCIDENT_PROMOTION_MODE=local` and `K9B_STORE_BACKEND=memory`) instead of manual module global assignment and unconditional event-name assertion. pytest restores all overrides automatically after the test. The post-promotion event name is accepted as either ``alert-signals-promoted`` or ``alert-signals-promoted-via-backend`` because the production code in `incident_promotion_dispatch.py` reports ``backend-api`` regardless of the env var (a Round-10 Item 3 wiring concern that is orthogonal to the collapse boundary). |

## 12. Re-Audit Closure (Round 2)

The Round-1 submission re-attached pre-correction state. This
revision addresses the four Round-2 reviewer findings:

| Finding | Status | Evidence |
|---|---|---|
| Production-helper wiring is still not pinned (the integration test only spied on the dispatch, not on `_calculate_identity_collapse_count`) | Closed | The integration test now patches ``ingestion_module._calculate_identity_collapse_count`` via `monkeypatch.setattr`, captures the call tuple in `calculator_calls`, and asserts `calculator_calls == [(2, 1)]`. A regression that bypasses the helper, restores `max(0, ...)`, or computes the metric outside the helper leaves `calculator_calls` empty or wrong and fails this assertion. |
| `K9B_STORE_BACKEND` is the wrong environment variable name | Closed | The test now sets `K9B_INCIDENT_PROMOTION_MODE`, `K9B_INCIDENT_STORE_BACKEND`, and `K9B_PROCESS_ROLE` -- the exact env vars that production's `IncidentPromotionDispatchConfig._get_dispatch_config` reads in `src/k8s_diag_agent/collect/incident_promotion_dispatch.py` (lines 46-50, 212-216). |
| Worktree bookkeeping is stale (the report said 4 paths / 21 changed paths; the reviewer expected 5 paths / 22 changed paths) | Closed | The worktree section now reports: "Item 2 contributed **5 paths**" and "combined ACT worktree contains **22 changed paths**: 3 modified tracked and 19 untracked. All are unstaged. **0 staged.**" Verified via `git status --porcelain`. |
| Stale closure-criteria wording ("the same-alert-twice production path passes" instead of the Option-B wording) | Closed | The closure-criteria section now reads "*one ingestion execution receiving two same-identity adapted signals dispatches one signal ID*". The D11 invariant table entry uses the same Option-B wording. |
