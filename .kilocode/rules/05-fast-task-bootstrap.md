# 05-fast-task-bootstrap.md

Purpose: minimal mandatory bootstrap for routine implementation tasks.

Use this file for:
- small feature work
- bug fixes
- UI/API/model changes
- test additions
- verification-focused follow-ups

Do not use this file alone for:
- architecture redesign
- doctrine changes
- memory-bank updates
- large refactors
- roadmap / backlog restructuring

## Hard invariants

- Run Python via `.venv/bin/python` only.
- Prefer the smallest coherent change.
- Preserve artifact-first behavior.
- Keep deterministic core separate from optional provider-assisted branches.
- No autonomous live-cluster mutation.
- Verification is part of implementation.

## Completion contract

Work is not complete unless `scripts/verify_all.sh` exits successfully and prints the canonical verification marker.

If the gate cannot be completed:
1. say which step failed first,
2. quote the blocking error,
3. state the smallest required fix,
4. do not present the task as done.

## Implementation posture

- Read nearby code before changing it.
- Reuse existing repo patterns unless there is a clear reason not to.
- Do not invent parallel abstractions when an existing seam already exists.
- Preserve contracts unless the task explicitly changes them.
- Prefer read-only UI/API projections over new persistence.
- Prefer fixture/test updates that follow the exact changed path.

## File-reading rule

For routine implementation tasks:
1. read `AGENTS.md`
2. read this file
3. read only directly relevant code/tests/docs for the task
4. read `docs/data-model.md` only if artifact/UI/API/persistence contracts are involved
5. do not read `README.md`, doctrine playbooks, or all memory-bank files unless the task specifically needs them

## Task-type bootstrap table

Based on the task type, load additional doctrine before implementing:

### Security-path work (static serving, artifact serving, file downloads, path validation)

If task touches:
- static file serving
- artifact serving
- file downloads
- path validation
- user-controlled path segments

Then also read:
- `docs/doctrine/path-security-doctrine.md`
- `src/k8s_diag_agent/security/path_validation.py`
- `tests/test_security_path_validation.py`

Required checks:
- Run targeted path traversal tests
- Add regression test for new path boundary
- Close report must include trust-boundary statement

### Bug fix

If task is a bug fix, also read:
- `docs/doctrine/bug-fossils.md` (if exists; apply manifest checks and mention missing planned doctrine in close report)

Required checks:
- Regression test for the bug class exists
- Root cause documented in test or comment

### UI/reporting work

If task touches:
- UI claims
- Report generation
- Operator conclusions

Then also read:
- `docs/doctrine/operator-path-truth.md` (if exists; apply manifest checks and mention missing planned doctrine in close report)
- `docs/doctrine/executable-claims.md` (if exists; apply manifest checks and mention missing planned doctrine in close report)

Required checks:
- Claims backed by artifacts
- Uncertainty is explicit

### File creation or large file work

If task creates new files or modifies large files, also read:
- `docs/doctrine/llm-friendly-files.md`

Required checks:
- New files < 300 lines (warning threshold)
- New files < 500 lines (failure threshold)
- Splitting plan if over threshold

## Output rule

When implementation finishes, report:
1. Summary
2. Files changed
3. Doctrines read (from bootstrap table above)
4. Tests updated
5. Verification run
6. Remaining risks / edge cases
7. **Impact Scan Ledger:** For non-trivial edits, include:
   - `Updated: docs/reports/impact-scan-ledger.md`
   - or `Skipped: <short rationale>` if the edit was trivial (docs-only, pure formatting, generated artifact, lockfile-only with no runtime behavior change)

