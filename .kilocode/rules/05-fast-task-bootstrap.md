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

## Output rule

When implementation finishes, report:
1. Summary
2. Files changed
3. Tests updated
4. Verification run
5. Remaining risks / edge cases
