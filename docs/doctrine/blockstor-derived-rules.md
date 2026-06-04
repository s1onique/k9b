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

---

## 7. Impact Scan Before Broad Edits

### Rejection trigger: `broad_edit_without_impact_scan`

When reviewing non-trivial or cross-module edits, enforce an impact map.

**Reviewer check:** If the edit affects shared symbols, interfaces, cross-module state, test coverage, public contracts, or architectural seams, the proposal must include a structured impact map:

```text
- target symbol / file
- definitions
- direct references
- likely tests
- intended edit surface
- reason if broader exploration is needed
```

**Allowed without impact map:** Trivial edits where the reason is obvious — typo fixes, comment-only cleanup, one-line local fixes, mechanical formatting already scoped by tooling, emergency hotfix with explicit follow-up.

**Reject or block when:** The edit is non-trivial, no impact map is provided, and no equivalent rationale explains why a scan was unnecessary.

**Bootstrap helper:** `scripts/impact_scan.sh <target>` may be used to generate a starting point, but manual correction is required. The output is **derived evidence, not source of truth**.

**Prohibited:** Do not add databases, file watchers, MCP integration, committed code graphs, or third-party analysis tools to satisfy this rule.

### Doctrine linkage

- **Manifest trigger:** `broad_edit_without_impact_scan` (already registered)
- **Agent guidance:** `.kilocode/rules/40-tool-use.md` → Impact Scan Doctrine
- **Script:** `scripts/impact_scan.sh`
- **Policy:** Impact scans are derived evidence, not source of truth
