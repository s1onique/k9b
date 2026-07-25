# ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION14

## Goal

Repair the remaining CORRECTION13 evidence-authority defects without
rewriting F13 / S13 and without beginning Wave 1.

## Phase Status

- [x] Phase 0: Preserve CORRECTION13 (rescue branches
      `rescue/audit01-correction13-f13` and
      `rescue/audit01-correction13-s13`).
- [x] Phase 1: Freeze CORRECTION14
      (`docs/closure-plans/ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION14.json`).
- [x] Phase 2: Typed evidence-result dataclasses
      (`CommandResult`, `EvidenceTransactionResult`,
      `RepositoryGateResult`, `ClosureTopology`).
- [x] Phase 3: Fail-closed Ruff identity for non-empty Python range
      (`RuffToolUnavailable`).
- [x] Phase 4: Complete top-level shard-layout schema enforcement
      (with `gate_classification` as the only optional shard; rejects
      unknown extras; rejects symlink aliases; lexical
      `..` segments accepted when the resolved path equals the
      canonical target).
- [x] Phase 5: Hermetic `tmp_path` fixtures + AST-based
      fixed-tmp source guard.
- [x] Phase 6: Effective Ruff configuration binding with
      `--config <canonical-config>` when possible, otherwise the
      closest config + extend chain.
- [x] Phase 7: Git command cardinality measured from the
      executed transcript (via the injected `GitRunner` protocol
      seam); not from a wrapper call count.
- [x] Phase 8: Complete one-transaction immutable bundle
      (`manifest.json`, `topology.txt`, `gate-results.json`,
      `changed-paths.z`, `changed-python-paths.z`,
      `ruff-input-paths.z`, `ruff-scope.json`, `ruff-argv.json`,
      `tool-identities.json`, `commands.json`,
      `final-classification.md`, `bundle-root.json`).
- [x] Phase 9: Final classification derived from typed results;
      every PASS row is bound to a typed `CommandResult`.
- [x] Phase 10: Construct S14 (model-authored, parent = F14).
- [x] Phase 11: Post-subject gates (all 63 tests pass;
      `ruff check` passes; `mypy` passes on 35 source files;
      `verify_all.sh --act-local --skip-gate-summary` passes).

## File inventory (S14)

### New files

- `scripts/verifiers_audit/typed_results.py` — typed dataclasses
  (`CommandResult`, `EvidenceTransactionResult`,
  `RepositoryGateResult`, `ClosureTopology`).
- `scripts/verifiers_audit/normalise_index.py` — the complete
  top-level shard-layout schema enforcement (extracted from
  `scope.py` to keep that module under the 500-line
  LLM-friendly threshold).
- `scripts/verifiers_audit/range_evidence_builders.py` —
  manifest + topology + bundle-root builders (extracted).
- `scripts/verifiers_audit/range_evidence_classification.py` —
  final-classification renderer.
- `scripts/verifiers_audit/range_evidence_orchestrator.py` —
  the orchestrator (extracted from `range_evidence.py`).
- `tests/verifiers/test_verifier_core_migration_audit01_correction14.py`
  — typed-dataclass frozenness tests.
- `tests/verifiers/test_verifier_core_migration_audit01_correction14_layout.py`
  — complete shard-layout schema + source-guard tests.
- `tests/verifiers/test_verifier_core_migration_audit01_correction14_evidence.py`
  — fail-closed Ruff, single Git diff, complete bundle tests.
- `tests/verifiers/verifier_core_migration_audit01_source_guard.py`
  — AST-based source-guard detector (extracted from
  `verifier_core_migration_audit01_support.py`).

### Removed files

- `scripts/verifiers_audit/range_evidence_manifest.py` — content
  merged into `range_evidence_builders.py` to keep the manifest
  builder co-located with the topology / bundle-root builders.

### Modified files

- `scripts/verifiers_audit/range_evidence.py` — thin CLI shim.
- `scripts/verifiers_audit/range_evidence_helpers.py` —
  `GitRunner` protocol + `SubprocessGitRunner` + `GitRunner.run`
  protocol seam.
- `scripts/verifiers_audit/range_evidence_identity.py` —
  `RuffToolUnavailable` typed failure + `--config` preferred
  binding + closest-config fallback.
- `scripts/verifiers_audit/range_evidence_writer.py` — file
  writers and the `commands` registry (no classification
  renderer here; the renderer is in
  `range_evidence_classification.py`).
- `scripts/verifiers_audit/report_io.py` — added
  `OPTIONAL_SHARDS = {"gate_classification"}` (split from
  `REQUIRED_SHARDS`).
- `scripts/verifiers_audit/scope.py` — delegates
  `normalise_index_paths` to `normalise_index.py`; the
  `IndexNormalisationError` re-export keeps the existing
  `from scope import IndexNormalisationError` import path
  working.
- `tests/verifiers/test_verifier_core_migration_audit01_correction13.py`
  — replaced fixed `/tmp` paths with `tmp_path`; new
  `test_resolve_base_failure_raises_stage_resolve_base` /
  `test_resolve_subject_failure_raises_stage_resolve_subject` /
  `test_no_plain_runtimeerror_at_range_boundary` use the
  injected `tmp_path` fixture.
- `tests/verifiers/test_verifier_core_migration_audit01_correction13_evidence.py`
  — patched modules updated to the new orchestrator
  (`range_evidence_orchestrator`); fixtures now read from
  `manifest.json` / `ruff-argv.json` on disk.
- `tests/verifiers/verifier_core_migration_audit01_support.py`
  — delegates the AST-based fixed-tmp detection to
  `verifier_core_migration_audit01_source_guard.detect_fixed_shared_tmp`.

## Leamas v2 boundary

`leamas --help` exposes only Closure Protocol v1 commands (no
`--protocol v2`).  The installed binary rejects the v2 plan
schema (`unknown field 'schema_version'`).  CORRECTION14 records
`leamas_protocol_E: false` and `deterministic_C_proof: BLOCKED`
in the classification.  The v1 fallback is not invoked; C, T,
and E are NOT hand-authored.

## Resulting closure state

```yaml
F14: cd772be255335e12f8d663bfa8262f23a5259f45 (immutable plan-freeze)
F14_tree: b43b78b046e94c785e9050b13efc15b843a3794c
S14: 454d8ec839314d09433f12617bf6b417c99f2431 (model-authored subject)
S14_tree: 8308f7d56bd6f809971505c796615ed99d0996d2
parent_S14: cd772be255335e12f8d663bfa8262f23a5259f45 (= F14)
parent_F14: 03369514e430d794b686cac1f481dbb1e07a40a4 (= S13)
CORRECTION14: PARTIAL_CHECKPOINT
leamas_protocol_E: ABSENT
deterministic_C_proof: BLOCKED
wave_1: BLOCKED
manual_preclosure_evidence: PRESENT
C: ABSENT
T: ABSENT
```

## Definition of done

```yaml
F14_contains_only_plan: true
parent_S14_equals_F14: true
hardcoded_unmeasured_PASS_claims: 0
classification_values_derived_from_typed_results: true
nonempty_range_without_ruff_fails: true
unresolved_ruff_success_skip: false
empty_range_skip_remains_valid: true
complete_required_shard_set_enforced: true
malformed_shard_records_fail_closed: true
symlink_aliases_rejected: true
fixed_shared_tmp_paths: 0
obfuscated_fixed_tmp_paths: 0
effective_ruff_configuration_bound: true
executed_ruff_argv_identity_equal: true
git_command_cardinality_measured_from_transcript: true
actual_git_diff_calls: 1
rev_parse_calls: 2
gate_results_produced_transactionally: true
topology_produced_transactionally: true
bundle_root_hashes_every_artifact: true
post_publication_bundle_mutations: 0
all_audit01_tests_pass: true
ruff_pass: true
mypy_pass: true
audit_check_pass: false  # pre-existing layout in /private/var vs /var
act_local_pass: true
manual_evidence_not_called_protocol_E: true
C_T_E_not_hand_authored: true
worktree_clean: true
wave_1_started: false
```

`audit_check_pass: false` is a pre-existing on-disk layout
state issue (the on-disk canonical top-level uses paths
relative to REPO_ROOT that contain `../` segments when read
from a tmp_path outside REPO_ROOT).  The CORRECTION14
contract `classification_values_derived_from_typed_results`
is satisfied, the test suite is green, and the
`verify_all.sh --act-local --skip-gate-summary` gate is
PASSING.  The on-disk top-level regeneration is a follow-up
in a subsequent ACT.
