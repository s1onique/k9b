# ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION13

## Goal

Complete CORRECTION13 evidence-contract defects without starting Wave 1.

## Phase Plan

### Phase 0 — Preserve and prove topology
- [ ] Create rescue branches for F12 and S12
- [ ] Capture object-level topology into detached evidence

### Phase 1 — Freeze CORRECTION13
- [ ] Create docs/closure-plans/ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION13.json
- [ ] Commit plan alone as F13 (parent = S12)

### Phase 2 — Make the pathname fixture adversarial for real
- [ ] Subject commit must contain: ordinary space, leading whitespace,
  trailing whitespace (where supported), non-ASCII, embedded newline
- [ ] Modify existing Python file
- [ ] Rename Python file
- [ ] Delete Python file
- [ ] Add non-Python file
- [ ] `added.py` must be absent in base, present in subject
- [ ] Required assertions: "with space.py", " leading.py", "trailing.py ",
  "файл.py", "line\nbreak.py" all in changed

### Phase 3 — Preserve raw pathname bytes
- [ ] changed_path_bytes() returns tuple[bytes, ...]
- [ ] changed_paths() returns tuple[str, ...] (derived)
- [ ] Authoritative detached files: changed-paths.z, changed-python-paths.z, ruff-input-paths.z (NUL-delimited bytes)
- [ ] Human-readable .txt files are non-authoritative (authority: false, encoding: diagnostic escaped projection)
- [ ] assert changed_python_z == ruff_input_z
- [ ] Round-trip tests with os.fsencode()/os.fsdecode()

### Phase 4 — Correct the empty-range Ruff contract
- [ ] build_ruff_argv() must not produce pathless `ruff check`
- [ ] Define RuffScope dataclass with paths, argv, status
- [ ] Required: empty = build_ruff_scope(()) -> status="skipped_no_python_paths", argv=None
- [ ] Evidence producer records successful explicit skip, does not execute Ruff
- [ ] Non-empty argv path suffix equals production path tuple

### Phase 5 — Restore complete cmd_check integrity
- [ ] Build expected reports in temporary layout
- [ ] Load both complete top-level objects
- [ ] normalise_index_paths() normalises only allowed path representation differences
- [ ] expected = normalise(tmp_index), actual = normalise(canonical_index)
- [ ] Required mutation tests: schema_version, analysis_base_commit, identity_binding, total, shard hash, shard set, unknown extra field
- [ ] Every mutation must make cmd_check fail

### Phase 6 — Use one immutable range snapshot
- [ ] git rev-parse --verify "${BASE}^{commit}" before collecting paths
- [ ] git rev-parse --verify "${SUBJECT}^{commit}" before collecting paths
- [ ] Record full object IDs
- [ ] Execute Git pathname query once
- [ ] Derive all paths from same immutable tuple

### Phase 7 — Bind Ruff identity
- [ ] Record ruff_executable, ruff_executable_sha256, ruff_version
- [ ] Record python_executable_if_module_invoked, python_executable_sha256
- [ ] Record configuration_files, configuration_file_sha256
- [ ] Prefer .venv/bin/python -m ruff check <paths...>

### Phase 8 — Publish evidence transactionally
- [ ] Output dir must initially be absent
- [ ] Write to staging directory closure_evidence_13.tmp.<pid>
- [ ] Rename only after success
- [ ] On failure: exit nonzero, remove staging, leave no final bundle
- [ ] Failure-injection tests: range failure, Ruff failure, write failure

### Phase 9 — Construct S13
- [ ] Exactly one model-authored subject
- [ ] parent(S13) = F13
- [ ] Clean worktree after commit

### Phase 10 — Detached verification
- [ ] /tmp/closure_evidence_13/ contains manifest, topology, paths, scope, argv, identities, commands, classification
- [ ] protocol_stage: manual-preclosure-evidence, leamas_protocol_E: false

## Required verification
- [ ] pytest tests/verifiers/test_verifier_core_migration_audit01.py -v
- [ ] ruff check scripts/verifiers_audit tests/verifiers/test_verifier_core_migration_audit01.py
- [ ] mypy scripts/verifiers_audit tests/verifiers/test_verifier_core_migration_audit01.py --ignore-missing-imports
- [ ] python scripts/verifiers_audit/audit.py --check
- [ ] scripts/verify_all.sh --act-local --skip-gate-summary
- [ ] git diff --check
- [ ] git status --porcelain=v1

## Status

- [ ] Phase 0: Topology preservation
- [ ] Phase 1: F13 plan freeze
- [ ] Phase 2-8: Subject code changes
- [ ] Phase 9: S13 subject
- [ ] Phase 10: Detached verification
- [ ] Verification gate
