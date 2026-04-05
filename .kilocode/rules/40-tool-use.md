# Tool Use Rules

This file defines how the agent should use tools in this repository.

Its purpose is to make tool use:
- evidence-driven,
- efficient,
- safe,
- incremental,
- and aligned with repository doctrine.

Use this together with:
- `AGENTS.md`
- `.kilocode/rules/20-architecture-doctrine.md`
- `.kilocode/rules/30-output-contracts.md`
- `.kilocode/rules/50-kubernetes-monitoring-domain.md`
- `.kilocode/rules/memory-bank/*.md`
- `docs/doctrine/*`

## Default operating posture

Before making changes:
1. understand the task,
2. inspect relevant repo context,
3. check project memory,
4. prefer existing patterns,
5. then change the smallest useful thing.

Do not treat the repo as blank just because the current file is blank.

## Read-before-write rule

Before creating or editing implementation code, first inspect:

1. `AGENTS.md`
2. relevant files under `.kilocode/rules/`
3. relevant files under `.kilocode/rules/memory-bank/`
4. nearby source files
5. existing tests
6. configuration, fixtures, and docs if they affect behavior

Do not write code before understanding existing structure and constraints.

## Discovery rules

Use discovery tools before assuming structure.

Preferred order:
1. `glob` to find likely files
2. `grep` to find symbols, patterns, or config keys
3. `read` to inspect selected files in detail
4. `bash` only when command output is needed
5. web lookup only when repository context is insufficient or the question is version-sensitive

## Memory Bank rule

Treat `.kilocode/rules/memory-bank/` as durable project context.

Before major design, refactor, or feature work:
- read the project brief,
- read architecture/product/progress memory if present,
- align work with those files unless the task explicitly changes direction.

If the implementation materially changes architecture, priorities, or project status, update the relevant Memory Bank files.

## Minimal-context rule

Do not reread the whole repo by default.

Prefer:
- targeted discovery,
- reading only relevant files,
- referencing specific modules,
- using project memory instead of repeated full scans.

This repository should favor deliberate context loading over broad context flooding.

## Existing-patterns-first rule

Before introducing a new pattern, abstraction, dependency, or layout:
- check whether the repo already has a local pattern,
- prefer extending an existing pattern if it is adequate,
- justify any new abstraction or dependency.

Do not create parallel patterns without a reason.

## Write rules

When editing files:
- prefer the smallest coherent change,
- keep related changes grouped,
- avoid speculative cleanup mixed with functional work,
- do not rewrite large files unless the task requires it,
- preserve comments, docs, and formatting unless they are part of the change.

When creating files:
- follow existing naming/layout conventions,
- place files where a future human would expect them,
- avoid placeholder files with no immediate purpose.

## Bash / command execution rules

Use `bash` when command output is necessary to:
- run tests,
- inspect repository state,
- inspect generated files,
- verify formatting/lint/typecheck,
- inspect local fixtures or example outputs,
- gather information unavailable from static file reads.

Do not use shell commands:
- as a substitute for reading obvious files,
- for noisy repo-wide output unless needed,
- or for destructive operations without clear justification.

Prefer commands that:
- are reproducible,
- are scoped,
- and directly support the current task.

## Test-first verification rule

After changing behavior, run the smallest relevant verification step.

Preferred order:
1. focused unit tests
2. targeted eval/fixture tests
3. typecheck/lint for touched areas
4. broader test suites only when justified

Do not claim completion without some verification unless the repo truly has no verification path, and then say so explicitly.

## Web lookup rule

Use web tools when:
- Kubernetes behavior may be version-sensitive,
- a third-party API/library/tool behavior is unclear,
- syntax or semantics may have changed,
- current documentation matters,
- or the repo does not contain enough trustworthy information.

Do not use web lookup for facts already established in the repo unless cross-checking is necessary.

When using external information:
- prefer official documentation,
- prefer primary sources,
- do not let external examples override repo doctrine without explanation.

## Kubernetes/domain-specific tool rules

When working on monitoring or diagnostics behavior:
- never invent cluster state from code alone,
- use fixtures, tests, schemas, or explicit inputs,
- treat sample incidents as evidence artifacts, not truth templates,
- preserve distinction between signal, finding, hypothesis, confidence, and action.

When adding a new diagnostic capability, also consider:
- what evidence source it depends on,
- how that evidence is normalized,
- how confidence is assigned,
- and how it will be tested with fixtures.

## Prompt/policy/eval asset rules

When editing prompts, rule files, examples, or evals:
- state what behavior is intended to change,
- check for conflicts with existing doctrine,
- add or update eval coverage when behavior meaningfully changes,
- avoid vague policy prose that cannot be tested.

Prefer changing:
- examples,
- schemas,
- evals,
- and narrowly scoped rules

before adding broad overlapping instructions.

## Refactor rules

Before refactoring:
- identify the exact pain,
- identify what behavior must remain stable,
- read nearby tests,
- preserve observability and error surfaces,
- avoid hidden architectural shifts.

After refactoring:
- verify behavior,
- summarize new seams or simplifications,
- note any migration implications.

## Ask-vs-act rule

Act without asking when:
- the task is clear,
- the change is local,
- the intent is obvious from repo doctrine and context.

Escalate or ask when:
- a choice is materially irreversible,
- multiple repo-consistent paths exist with different tradeoffs,
- the task changes architecture or public contracts,
- production assumptions are required but absent,
- or safety/risk posture is unclear.

## Safety and destructiveness rule

Do not perform destructive or hard-to-reverse actions unless the task explicitly requires them and the impact is understood.

Examples:
- mass file rewrites
- deleting tests or evals
- changing schemas or public interfaces
- removing observability hooks
- broad dependency replacement
- irreversible migration scripts

If such a change is required, explicitly state:
- what is changing,
- why it is necessary,
- what could break,
- how to validate it,
- and how to recover.

## Completion rule

Do not stop at “code written.”

A task is closer to complete when:
- relevant files are updated,
- tests/evals are updated or the gap is explained,
- output shape matches repo contracts,
- observability/debuggability impact is considered,
- and next risks are stated.

## Preferred workflow summary

For most non-trivial tasks:
1. read repo guidance
2. read memory-bank context
3. discover relevant files
4. inspect current implementation/tests
5. propose or choose the smallest coherent change
6. implement
7. verify
8. summarize impact, risk, and follow-up

## Anti-patterns

Do not:
- invent architecture from thin air,
- code before reading repo guidance,
- reread the whole repo when targeted discovery is enough,
- add abstractions with no demonstrated need,
- claim diagnosis without evidence,
- change behavior without updating tests/evals when needed,
- use web examples as if they were repo requirements,
- hide uncertainty behind confident prose.

## Summary rule

Use tools like a careful engineer:
- read before writing,
- verify before concluding,
- prefer targeted context over context flooding,
- prefer evidence over assumption,
- and keep changes small, testable, and reversible.
