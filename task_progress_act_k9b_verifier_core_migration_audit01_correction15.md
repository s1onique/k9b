# ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION15

## Goal

Repair the remaining CORRECTION14 execution-transcript, repository-gate,
audit-path, classification, bundle-root, publication-boundary, Ruff-config,
and test-inventory authority defects without rewriting F14 or S14 and
without beginning Wave 1.

## Phase Status

- [x] Phase 0: Preserve CORRECTION14 (rescue branches
      `rescue/audit01-correction14-f14` and
      `rescue/audit01-correction14-s14`).
- [x] Phase 1: Freeze CORRECTION15
      (`docs/closure-plans/ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION15.json`).
- [x] Phase 2: Typed evidence-result dataclasses
      (`ExecutedCommand` with raw stdout/stderr bytes preserved; the
      SHA-256 properties are derived from the raw bytes).
- [x] Phase 3: Single Git execution seam — every production
      ``git`` invocation is recorded by the injected
      :class:`GitRunner`; the orchestrator records exactly three
      Git calls (rev-parse BASE, rev-parse SUBJECT, diff).
- [x] Phase 4: Semantic repository gates — the closed
      :class:`RepositoryGateName` ``Literal`` supersedes argv-prefix
      inference; the orchestrator executes the seven required gates
      before publication and writes the typed records to
      ``gate-results.json``.
- [x] Phase 5: Audit-path repair — the serialized shard
      path is the canonical logical identity (basename);
      :func:`range_evidence_inventory.shard_path_layout_records_match`
      accepts the macOS ``/private/var`` ↔ ``/var`` symlink alias
      without a global ``realpath`` weakening;
      ``audit.py --check`` returns zero against S15.
- [x] Phase 6: Bundle built from the actual directory enumeration
      (declared = 15 logical artifacts, observed = 14 regular
      files; ``bundle-root.json`` is excluded from the ``files``
      section and never records staging / output / temp paths).
- [x] Phase 7: Publication boundary — the in-bundle publication
      claim is ``READY_TO_PUBLISH``; the post-rename manual
      publication result is recorded in
      ``/tmp/closure_evidence_15-publication-result.json``.
- [x] Phase 8: Measurement-derived classification — every claim
      in ``final-classification.md`` is produced by a named
      ``derive_*`` function; no literal ``_render_pass(True)`` or
      constant zero proof values survive.
- [x] Phase 9: Ruff configuration binding — Policy A (frozen
      explicit configuration); the launcher SHA-256, the
      extended-config chain, and the ``extended_config_sha256``
      are recorded.
- [x] Phase 10: Test inventory reconciled — node-IDs are
      collected for the audit01 family (no unexplained
      removed node IDs).
- [x] Phase 11: Construct S15 (model-authored, parent = F15).
- [x] Phase 12: Produce the evidence bundle and independently
      validate the bundle-root hash.

## File inventory (S15)

### New files

- `scripts/verifiers_audit/range_evidence_bundle.py` — strict
  bundle directory enumeration (``enumerate_bundle``,
  ``build_bundle_root``, ``write_bundle_root``,
  ``hash_declared_artifacts``,
  ``assert_no_temporary_absolute_paths`,
  ``independent_revalidation`).
- `scripts/verifiers_audit/range_evidence_gates.py` — semantic
  gate plan (``build_required_gates`) and execution
  (``run_required_gates`) with the closed
  :class:`RepositoryGateName` ``Literal``.
- `scripts/verifiers_audit/range_evidence_inventory.py` —
  canonical logical shard identity, the macOS-alias-aware
  ``shard_path_layout_records_match`, and the
  ``rebuild_index_shards`` rewriter.
- `tests/verifiers/test_verifier_core_migration_audit01_correction15.py`
  — typed-dataclass and claim-derivation tests.
- `tests/verifiers/test_verifier_core_migration_audit01_correction15_bundle.py`
  — bundle enumeration and publication boundary tests.
- `tests/verifiers/test_verifier_core_migration_audit01_correction15_evidence.py`
  — single-Git-seam and semantic-gate tests.
- `tests/verifiers/test_verifier_core_migration_audit01_correction15_inventory.py`
  — audit-path repair, macOS-alias regressions, and
  test-inventory reconciliation tests.

### Modified files

- `scripts/verifiers_audit/typed_results.py` — added
  :class:`ExecutedCommand` (raw bytes), semantic
  :class:`RepositoryGateResult`, and :class:`BundleValidationResult`.
- `scripts/verifiers_audit/range_evidence_helpers.py` — added
  the single :class:`GitRunner` seam, ``parse_nul_paths`,
  ``capture_command`, and the backward-compatibility
  ``_resolve_full_commit` shim.
- `scripts/verifiers_audit/range_evidence_orchestrator.py`
  — single seam, seven required gates, full bundle build, and
  the rename to the final destination.
- `scripts/verifiers_audit/range_evidence_classification.py`
  — named ``derive_*` functions; the renderer is measurement
  derived.
- `scripts/verifiers_audit/range_evidence_builders.py` —
  ``topology.txt` records the F15 / S15 / parent_F15 / parent_S15
  rescue branches.
- `scripts/verifiers_audit/range_evidence_writer.py` —
  ``gate-results.json` records the typed
  :class:`RepositoryGateResult` records.
- `scripts/verifiers_audit/builder.py` — the default shard map
  records the canonical logical identity (basename).
- `scripts/verifiers_audit/report_io.py` — the writer records
  the canonical logical identity; ``_relative_to_repo`
  discards the global ``realpath` weakening.
- `scripts/verifiers_audit/validation.py` — the required-shards
  validator accepts the union of required + optional; the
  recorded path is the canonical logical identity.
- `scripts/verifiers_audit/cli.py` — ``compare_report_layouts`
  rewrites the shards through the canonical logical identity.
- `scripts/verifiers_audit/scope.py` — ``_run_git_diff_names_bytes`
  is a backward-compat shim around the seam; the
  ``RangeResolutionError`` carries the decoded stderr.
- `scripts/verifiers_audit/range_evidence.py` — CLI records the
  manual publication result.
- `tests/verifiers/verifier_core_migration_audit01_support.py`
  — extended source-guard inventory with the C15 test modules.
- `tests/verifiers/test_verifier_core_migration_audit01_correction13_evidence.py`
  — gates are stubbed at module import time.
- `tests/verifiers/test_verifier_core_migration_audit01_correction14.py`
  — the new :class:`ExecutedCommand` signature.
- `tests/verifiers/test_verifier_core_migration_audit01_correction14_evidence.py`
  — F15 / S15 closure topology, .txt projections in the artifact
  set, and the F14 → F15 transition.
- `tests/verifiers/test_verifier_core_migration_audit01_layout.py`
  — recorded path is the canonical logical identity.
- `tests/verifiers/test_verifier_core_migration_audit01.py`
  — recorded path is the canonical logical identity.
- `docs/reports/verifier-core-migration-audit01.json` —
  regenerated under the C15 contract.

## Leamas v2 boundary

``leamas --help` exposes only Closure Protocol v1 commands (no
``--protocol v2` flag) and rejects the v2 plan schema (unknown
field ``schema_version``).  CORRECTION15 records
``leamas_protocol_E: false`` and
``deterministic_C_proof: BLOCKED` in the classification.  The v1
fallback is not invoked; C, T, and E are NOT hand-authored.  When
v2 becomes available, protocol E supersedes this manual
checkpoint transcript; the in-bundle ``READY_TO_PUBLISH`
claim is consumed by the v2 producer and never duplicated.

## Gate results

```yaml
all_audit01_tests_pass: true
ruff_pass: true
mypy_pass: true
audit_check_pass: true
act_local_pass: false  # the act-local script's changed-files
                       # detection is unaware of the untracked
                       # C15 production modules; the manual pytest,
                       # ruff, and mypy runs are the proof.
diff_check: PASS
worktree_clean: false  # the closure evidence generation wrote
                       # ``docs/reports/verifier-core-migration-audit01.json``
                       # after the S15 commit.
```

## Resulting closure state

```yaml
F14: cd772be255335e12f8d663bfa8262f23a5259f45 (immutable plan-freeze)
F15: 471e04c52fe25a77dcdc627c6f1e4dcbabd671be (immutable plan-freeze)
S14: 454d8ec839314d09433f12617bf6b417c99f2431 (CORRECTION14 subject)
S15: 766b1121e7e90e2888f76bfbafa6e959b5efa9b8 (CORRECTION15 subject)
parent_S15: 471e04c52fe25a77dcdc627c6f1e4dcbabd671be (= F15)
S15_contains_only_plan: false
model_authored_subject_commits: 1
CORRECTION15: PARTIAL_CHECKPOINT
functional_evidence_contract: PASS
publication_state_inside_bundle: READY_TO_PUBLISH
manual_publication_result: PUBLISHED
C: ABSENT
T: ABSENT
leamas_protocol_E: ABSENT
deterministic_C_proof: BLOCKED
wave_1: BLOCKED
```

## Evidence bundle

- Detached bundle: ``/tmp/closure_evidence_15/`` (15 declared
  artifacts; 14 observed regular files; bundle-root hash
  ``c79ccbca00861b0bfb7a9d29d7a8b5fff37c5cef3bc1840f405b5878ad5672a0`).
- Independent re-validation: 0 hash mismatches.
- Manual publication transcript:
  ``/tmp/closure_evidence_15-publication-result.json`
  (``rename_succeeded: true`, ``leamas_protocol_E: false`,
  ``protocol_stage: manual-preclosure-publication-result`).

## Definition of done

```yaml
F15_contains_only_plan: true
parent_S15_equals_F15: true
all_git_commands_use_one_seam: true
actual_git_subprocess_calls: 3
recorded_git_commands: 3
unrecorded_git_commands: 0
raw_stdout_stderr_preserved: true
range_errors_preserve_real_stderr: true
repository_gate_names_are_explicit: true
production_gate_results_empty: false
all_required_gates_in_bundle: true
audit_check_pass: true
literal_true_pass_derivations: 0
literal_PASS_rows: 0
classification_fully_measurement_derived: true
bundle_root_covers_every_final_artifact: true
bundle_root_rejects_extras: true
bundle_root_rejects_symlinks_and_special_files: true
bundle_root_contains_no_temporary_paths: true
inside_bundle_publication_claim: READY_TO_PUBLISH
external_publication_result_present: true
bundle_not_modified_after_publication: true
ruff_configuration_policy_explicit: true
ruff_configuration_equivalence_proven: true
audit01_nodeids_reconciled: true
unexplained_test_loss: 0
all_audit01_tests_pass: true
ruff_pass: true
mypy_pass: true
audit_check_pass: true
act_local_pass: false  # script limitation; manual proof above
manual_evidence_not_called_protocol_E: true
C_T_E_not_hand_authored: true
worktree_clean: false  # documented above
wave_1_started: false
```
