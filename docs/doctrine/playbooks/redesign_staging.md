# Redesign Staging Playbook

This playbook defines the default procedure for evolving a simpler system into a more capable system in this repository.

It should be used when:
- a modular monolith is under pressure,
- a subsystem may need extraction,
- a new data path or interface is being introduced,
- a reasoning pipeline is being reworked,
- a persistence layer is being added,
- a provider/runtime dependency may be changing,
- or any architectural change risks blocking future evolution.

This playbook sits below:
- `constitution.md`
- `precedence.md`
- `seed_rules.md`

And above:
- local implementation details
- one-off migration choices
- task-specific coding work

## Purpose

The purpose of redesign staging is not to jump directly to an imagined final architecture.

The purpose is to:
- solve the current pressure,
- preserve future options,
- reduce irreversible risk,
- keep the system observable,
- and learn safely from each stage.

## Core rule

Do not redesign for theoretical elegance alone.

Redesign only when:
- there is a real current pressure,
- the pressure is evidenced,
- and the proposed stage improves the situation without blocking likely future moves.

## Standard staging procedure

### Step 1 — Name the current pressure precisely
State:
- what is failing or straining now,
- where it appears,
- who feels it,
- and what evidence shows it is real.

Examples:
- reasoning logic is too coupled to rendering
- fixture-based evals are hard to maintain
- provider-specific code is leaking into domain logic
- collection adapters are entangled with assessment logic
- rollout of new behavior cannot be validated safely
- current structure blocks useful testing or observability

If the pressure cannot be stated clearly, do not force a redesign.

### Step 2 — Separate current pain from imagined future pain
Distinguish:
- current evidenced problems,
- near-term likely next problems,
- speculative long-term possibilities.

Do not let speculative future scale or complexity dominate the redesign unless the cost of later adaptation would be clearly unacceptable.

### Step 3 — Identify what must remain stable
List the things that should remain stable across the redesign.

Examples:
- user-facing behavior contract
- assessment output schema
- internal domain concepts
- eval semantics
- operator expectations
- rollout safety guarantees
- observability surfaces

A redesign should preserve stability where stability is valuable.

### Step 4 — Identify what may safely change
List the things that may change without violating core expectations.

Examples:
- internal module layout
- provider integration details
- prompt/policy asset organization
- implementation language boundaries
- adapter structure
- orchestration internals

This prevents accidental overprotection of local implementation detail.

### Step 5 — Define the smallest viable next form
Describe the smallest structural change that materially relieves the current pressure.

Prefer:
- extracting a seam before extracting a service,
- introducing a stable interface before a full subsystem split,
- adding comparative validation before replacing the old path,
- improving observability before adding complexity.

Do not jump directly to the grand redesign if an intermediate stage can teach more safely.

### Step 6 — Preserve or create explicit seams
Before moving components apart, create or clarify boundaries.

Common seams in this repo include:
- collection vs normalization
- normalization vs reasoning
- reasoning vs recommendation
- recommendation vs rendering
- domain contracts vs provider/runtime adapters
- eval harness vs runtime behavior

A seam is useful only if it improves testability, observability, or future change safety.

### Step 7 — Add observability before structural change
Before significant redesign, ensure the current and future paths can be compared.

Where practical, make visible:
- inputs
- normalized evidence
- findings
- hypotheses
- confidence
- next checks/actions
- failure modes
- timing/latency where relevant

If old and new paths cannot be compared, redesign risk rises sharply.

### Step 8 — Preserve side-by-side validation where practical
Prefer redesign stages that allow:
- old and new behavior to coexist,
- fixture-based comparison,
- shadow evaluation,
- dual execution on the same scenario,
- or explicit rollback.

If the redesign requires a hard cutover, that must be justified.

### Step 9 — Keep migration paths explicit
For any meaningful redesign, state:
- what changes first,
- what remains temporarily duplicated,
- what compatibility window exists,
- when old paths may be removed,
- and what conditions must be met before removal.

Do not rely on “we’ll clean it up later” as the only migration strategy.

### Step 10 — Protect domain contracts from provider leakage
As the system evolves, keep stable domain concepts separate from:
- model provider APIs
- transport details
- prompt formatting conventions
- backend-specific schemas

Redesign should usually reduce provider leakage, not increase it.

### Step 11 — Check coupling introduced by the redesign
Ask:
- what new dependencies are introduced?
- what now changes together that did not before?
- does this create a new hidden center of gravity?
- are we trading one type of complexity for a worse one?

Prefer redesigns that reduce or clarify coupling rather than merely moving it around.

### Step 12 — Re-evaluate whether decomposition is truly needed
Before introducing multi-service or distributed boundaries, ask:
- is modular separation inside one deployable still enough?
- is the pressure operational, organizational, or conceptual?
- do we actually need distributed isolation, or just clearer seams?
- will the added complexity pay for itself now?

The default answer in this repo should still be:
- modular monolith first,
- distributed boundaries only when justified.

### Step 13 — Define rollback and containment
State:
- how to revert the redesign stage,
- how to disable the new path,
- what data/contracts require care,
- and how to contain failure if the new stage behaves badly.

If rollback is not possible, that must be treated as a one-way door.

### Step 14 — Define validation criteria
A redesign stage is not complete until success criteria are stated.

Examples:
- easier isolated testing
- clearer reasoning visibility
- lower provider leakage
- simpler module boundaries
- improved eval pass rate
- safer rollout
- reduced change coupling
- better operator-facing consistency

Validation should be observable, not rhetorical.

### Step 15 — Stop after the smallest successful stage
After a successful stage, reassess before continuing.

Do not assume the full redesign plan still makes sense after the first structural improvement.

## Required output shape

Unless explicitly asked otherwise, a redesign staging recommendation should include:

### Current pressure
What real problem exists now?

### Stable elements
What must stay stable?

### Changeable elements
What may safely change?

### Smallest viable next stage
What is the next structural move?

### Why this stage
Why now, and why this instead of a larger jump?

### New seam or boundary
What boundary is being created or clarified?

### Observability / comparison plan
How will old and new behavior be compared?

### Migration / compatibility window
How can the transition happen safely?

### Rollback / containment
How can this be reversed or limited?

### Validation criteria
What evidence will show the stage worked?

### Next likely stage
What may come after this, if the evidence justifies it?

## Redesign anti-patterns

Do not:
- redesign because the final architecture “should” look more advanced,
- split services before proving modular seams,
- replace multiple concerns at once without isolation,
- remove the old path before validating the new one,
- weaken observability during migration,
- lock in providers or schemas casually,
- treat temporary boundaries as permanent truth,
- or confuse movement with progress.

## Repo-specific redesign heuristics

In this repository, redesign is often justified when it improves one or more of:
- evidence normalization clarity
- reasoning isolation
- recommendation safety
- structured output consistency
- eval coverage
- provider independence
- observability of internal reasoning
- ability to test behavior without live cluster dependencies

In this repository, redesign is often unjustified when it is mainly about:
- abstract elegance
- hypothetical future scale
- framework fashion
- distributed architecture prestige
- avoiding local cleanup work
- or replacing simple seams with heavier infrastructure

## Escalate instead of forcing a redesign when

Escalate when:
- the pressure is vague,
- the next stage is not smaller than the final target,
- the redesign introduces multiple one-way doors at once,
- comparison or rollback is missing,
- or the proposal depends on future conditions that remain speculative.

A good escalation should state:
1. what is insufficiently understood,
2. what safer intermediate step exists,
3. and what evidence would justify the larger redesign later.

## Change policy

Update this playbook when:
- repeated redesign efforts fail for the same reason,
- a recurring migration issue needs a formal step,
- or the repository’s philosophy of staged evolution changes materially.

Do not update this file for one-off local refactors or temporary implementation disputes.
