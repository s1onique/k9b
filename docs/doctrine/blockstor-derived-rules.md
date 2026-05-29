# Blockstor-Derived Factory Rules

## Purpose

These rules capture reusable engineering discipline observed during the blockstor review. They are not blockstor-specific; they are Factory review doctrine.

## Rules

### 1. Clean-room claims require executable evidence

A project may claim clean-room rebuildability only when the repository contains enough commands, scripts, manifests, fixtures, or release instructions for a competent outsider or agent to reproduce the important path.

Documentation-only claims are useful, but they are partial credit.

**Factory review question:**

> Can this repo be rebuilt, tested, or released from a fresh checkout using repo-owned instructions and commands?

**Evidence examples:**
- Makefile targets
- scripts/
- CI jobs
- release checklist
- container build instructions
- generated artifact verification

**Failure examples:**
- "Run the usual process"
- tribal knowledge
- release notes without commands
- undocumented local machine assumptions

### 2. Cold resume is a product requirement

A project should be resumable after context loss.

**Factory review question:**

> Can a new maintainer or agent understand the current state, next step, known risks, and verification path from repository artifacts alone?

**Expected artifacts may include:**
- README entry point
- docs/evaluation/
- docs/epics/
- WAL / decision logs
- known risks
- open follow-ups
- verification commands

### 3. Release certification must be evidence-backed

A release is not certified merely because it has a tag, changelog, or deployment.

**Factory review question:**

> Does the repo preserve evidence for what was verified before release?

A good release certificate states:
- version / commit / artifact identity
- verification commands
- test result summary
- known unverified areas
- accepted risks
- rollback or recovery notes where relevant

### 4. Prefer boring, inspectable artifacts

Factory should reward projects that are easy to inspect.

**Positive signals:**
- small files
- clear naming
- simple scripts
- explicit checklists
- low hidden magic
- readable CI
- reviewable docs

**Negative signals:**
- oversized source files
- giant generated-looking hand-written docs
- opaque pipelines
- clever abstractions without operational payoff
- "framework smell" before project need exists

### 5. Truth beats theater

Factory reviews must prefer honest partial capability over inflated claims.

**Acceptable:**
- "not implemented"
- "manual only"
- "verified locally but not in CI"
- "known risk"
- "partial support"

**Bad:**
- ambiguous green badges
- success claims without commands
- "production-ready" without operational evidence
- hidden TODOs behind polished prose

### 6. Doctrine should connect to checks

A doctrine should eventually affect at least one of:
- review checklist
- scoring rubric
- prompt template
- CI/local gate
- generated review report
- release checklist

Factory should distinguish:
- documented doctrine
- review-enforced doctrine
- mechanically checked doctrine

## Templates

- [Release Certification template](../templates/release-certification.md)
- [Cold Resume template](../templates/cold-resume.md)
