# Design Review Playbook

This playbook defines the default procedure for reviewing a proposed design, architecture change, redesign, or implementation structure in this repository.

It should be used when reviewing:
- system architecture proposals,
- module boundaries,
- reasoning pipeline changes,
- major refactors,
- integration choices,
- persistence/interface changes,
- or any change that may affect evolvability, observability, correctness, or safety.

This playbook sits below:
- `constitution.md`
- `precedence.md`
- `seed_rules.md`

And above:
- implementation details
- local coding choices
- one-off task decisions

## Purpose

The purpose of design review is not to find a perfect end-state design.

The purpose is to determine whether the proposed design:
- solves the current problem,
- tells the truth about current unknowns,
- preserves safe future evolution,
- remains observable and testable,
- and avoids unjustified irreversible commitments.

## Required review mindset

A good review in this repo should be:

- evidence-first,
- explicit about uncertainty,
- skeptical of one-way doors,
- attentive to observability,
- attentive to coupling,
- and biased toward safe evolution.

Do not review only for elegance.

Do not assume more complexity is more advanced.

Do not assume the current proposal is correct just because it is detailed.

## Standard review procedure

### Step 1 — Restate the problem being solved
State clearly:
- what problem exists now,
- who experiences it,
- what evidence shows it matters,
- and why this review is happening now.

If the actual problem is unclear, stop and say so.

### Step 2 — Identify known facts and unknowns
Separate:
- established facts,
- assumptions,
- open questions,
- and production details that are still missing.

If the recommendation depends heavily on unknowns, that must shape the review outcome.

### Step 3 — Classify constraints
List:
- hard constraints
- soft constraints
- preferences
- non-goals

Examples:
- safety requirements
- operational limits
- team capability
- latency/resource constraints
- backward compatibility needs
- rollout constraints
- compliance restrictions

Do not treat preferences as hard constraints.

### Step 4 — Identify the proposed change in structural terms
Describe what is actually changing.

Examples:
- new module boundary
- new subsystem
- storage introduction
- provider abstraction
- interface change
- service split
- policy/prompt asset move
- reasoning pipeline change

A review should assess the real structural move, not just the implementation details.

### Step 5 — Identify one-way doors
Explicitly ask:
- what is expensive to reverse?
- what is hard to migrate away from later?
- what changes contracts, state, or ownership boundaries?
- what would be painful to roll back?

If the proposal creates a one-way door, that must be called out clearly.

### Step 6 — Check for unjustified complexity
Ask:
- does this complexity solve a real current problem?
- is it compensating for a hypothetical future?
- could a simpler modular structure solve the same need now?
- is decomposition being proposed before evidence justifies it?

Default bias:
- modular monolith before multi-service decomposition
- explicit seams before distributed boundaries
- incremental migration before speculative end-state design

### Step 7 — Check coupling and boundary quality
Review whether the proposal:
- couples concerns that change at different rates,
- leaks provider/vendor details into domain logic,
- mixes collection, reasoning, rendering, or evaluation concerns,
- or creates boundaries based only on current convenience.

Prefer boundaries that:
- reflect domain concepts,
- reduce change coupling,
- remain testable,
- and preserve future extraction paths.

### Step 8 — Check observability and debuggability
Ask:
- what evidence will exist after this change?
- what can still be inspected?
- can operators see inputs, findings, hypotheses, confidence, and actions?
- are important failures easier or harder to diagnose?
- does this reduce metrics, logs, traces, or auditability?

If observability weakens, treat that as a serious review concern.

### Step 9 — Check testability and evalability
Ask:
- can the important behavior be tested?
- can the reasoning path be evaluated?
- can false certainty be caught?
- can regression cases be preserved?
- is the system becoming more or less verifiable?

Important changes should improve or preserve testability.

### Step 10 — Check migration and rollout shape
Ask:
- can this be introduced incrementally?
- can old and new paths coexist temporarily?
- is side-by-side validation possible?
- is there a rollback or fallback path?
- what is the blast radius if this fails?

If rollout must be all-at-once, that must be justified.

### Step 11 — Check operator usefulness
Ask:
- does this make the product more useful to platform engineers and operators?
- does it improve evidence handling?
- does it improve clarity of uncertainty?
- does it help produce safer next actions?
- or is it mostly internal complexity with unclear user value?

A design that is impressive but not more useful is not automatically good.

### Step 12 — Compare credible alternatives
For any meaningful design review, consider at least:
- the proposed option,
- a simpler option,
- and a deferred/staged option if relevant.

Do not review a proposal as if no alternatives exist.

### Step 13 — Make a recommendation
End with one of:
- proceed
- proceed with changes
- defer pending evidence
- reject for now

A recommendation must include:
- why,
- key tradeoffs,
- what is being protected,
- what remains unknown,
- and what would change the recommendation.

## Required review output shape

Unless the task explicitly asks otherwise, a design review should include:

### Goal
What problem is being reviewed?

### Facts
What is known?

### Assumptions / unknowns
What is not yet known?

### Proposed structural change
What is changing?

### Main risks
What are the most important concerns?

### Simpler alternative
What simpler path was considered?

### Recommendation
What is the preferred outcome?

### Why
Why is that the preferred outcome?

### Tradeoffs
What is gained and what is sacrificed?

### Evolution / migration impact
What future moves are preserved or blocked?

### Observability / testability impact
What visibility or verification changes?

### Rollback / fallback
How can this be reversed or contained?

### Next validation step
What evidence should be collected next?

## Design review anti-patterns

Do not:
- confuse detail with correctness,
- reward complexity for sounding mature,
- assume microservices are progress,
- ignore missing production evidence,
- ignore rollback shape,
- ignore observability loss,
- treat present org structure as permanent architecture truth,
- or hide tradeoffs in vague prose.

## Design review heuristics for this repo

In this repository, strong designs usually have these properties:

- modular monolith by default
- domain-first boundaries
- explicit distinction between evidence, findings, hypotheses, and actions
- visible reasoning path
- structured outputs
- low-friction eval coverage
- reversible decisions where practical
- incremental rollout path

Weak designs often show these smells:

- provider leakage into domain types
- hidden coupling between reasoning and rendering
- no path for regression testing
- storage or interface commitments without demonstrated need
- distributed complexity before a working vertical slice
- recommendation logic that cannot explain itself

## Escalate instead of overcommitting when

Escalate if:
- the problem statement is weak,
- the proposal depends on missing production facts,
- a one-way door is present without strong evidence,
- the main tradeoff is unresolved,
- or multiple viable paths remain and the choice is strategically important.

A good escalation should say:
1. what is unresolved,
2. why it matters,
3. which smaller or safer next step is still possible.

## Change policy

Update this playbook when:
- design reviews repeatedly miss the same class of issue,
- a recurring ambiguity needs a formal review step,
- or the repository’s review philosophy changes materially.

Do not update this file for one-off disputes or local implementation preferences.
