# Agentic Documentation Truthfulness and Usage Audit

**Epic:** [Open] Agentic Documentation Truthfulness and Usage Audit  
**Status:** In Progress  
**Date:** 2026-05-16

---

## Purpose

Review agent-facing and agent-influencing documentation for truthfulness, usefulness, discoverability, and actionability. Establish a lightweight mechanism to track which docs agents actually read/use versus ignore.

**Hypothesis:** `.kilocode/rules/memory-bank/current.md` is stale because it is not updated routinely. Other docs may reference non-existent files or contain outdated guidance.

---

## Scope

Focus on agent-facing and agent-influencing docs:

- `.kilocode/rules/**`
- `.cline/**` (if present)
- `AGENTS.md`
- `README.md`
- `CONTRIBUTING.md` (not present)
- `docs/**`
- verification/deployment docs
- operator/agent workflow docs
- scripts referenced by docs

**Do not perform:** broad unrelated refactors, new features, UI redesigns.

---

## Quality Criteria

A doc is considered **useful to agents** when it:

1. **Exists** — referenced paths resolve to actual files
2. **Is current** — describes current repo behavior, not stale state
3. **Is accurate** — commands, paths, and facts match actual implementation
4. **Is discoverable** — agents can find it via standard reading paths
5. **Is actionable** — contains guidance agents can follow without guessing
6. **Is non-misleading** — does not point agents to non-existent files or commands

---

## Classification Table

| Path | Audience | Agent Relevance | Currentness | Issues | Recommended Action |
|------|----------|-----------------|-------------|--------|-------------------|
| `AGENTS.md` | Agent/human | High | ✅ Current | None identified | keep |
| `README.md` | Human | Medium | ✅ Current | None identified | keep |
| `.kilocode/rules/00-global.md` | Agent | High | ✅ Current | None identified | keep |
| `.kilocode/rules/05-fast-task-bootstrap.md` | Agent | High | ✅ Current | None identified | keep |
| `.kilocode/rules/20-architecture-doctrine.md` | Agent | High | ✅ Current | None identified | keep |
| `.kilocode/rules/10-agent-mission.md` | Agent | High | ❌ MISSING | Referenced but does not exist | investigate/create |
| `.kilocode/rules/30-output-contracts.md` | Agent | High | ❌ MISSING | Referenced but does not exist | investigate/create |
| `.kilocode/rules/40-tool-use.md` | Agent | High | ❌ MISSING | Referenced but does not exist | investigate/create |
| `.kilocode/rules/50-kubernetes-monitoring-domain.md` | Agent | High | ❌ MISSING | Referenced but does not exist | investigate/create |
| `.kilocode/rules/memory-bank/current.md` | Agent | High | ⚠️ Partial | Contains stale references; needs update | update |
| `.kilocode/rules/memory-bank/brief.md` | Agent | Medium | ✅ Current | None identified | keep |
| `.kilocode/rules/memory-bank/progress.md` | Agent | Medium | ⚠️ Partial | References missing files (tech.md, product.md) | update |
| `.kilocode/rules/memory-bank/architecture.md` | Agent | Medium | ✅ Current | None identified | keep |
| `.kilocode/rules/memory-bank/tech.md` | Agent | Medium | ❌ MISSING | Referenced but does not exist | investigate/create |
| `.kilocode/rules/memory-bank/product.md` | Agent | Medium | ❌ MISSING | Referenced but does not exist | investigate/create |
| `docs/doctrine/constitution.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/doctrine/precedence.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/doctrine/seed_rules.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/doctrine/identity-primer.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/doctrine/beta-real-incident-validation.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/doctrine/playbooks/design_review.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/doctrine/playbooks/redesign_staging.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/doctrine/evals/eval_schema.yaml` | Agent | Medium | ✅ Current | None identified | keep |
| `docs/doctrine/evals/seed_evals.yaml` | Agent | Medium | ✅ Current | None identified | keep |
| `docs/data-model.md` | Agent/human | High | ✅ Current | None identified | keep |
| `docs/coverage.md` | Agent/human | Medium | ⚠️ Partial | References `scripts/run_coverage.sh` which does not exist | investigate |
| `docs/post-beta-backlog.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/beta-release-notes.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/beta-operator-guide.md` | Human | Low | ✅ Current | None identified | keep |
| `docs/baseline_watch_practices.md` | Human | Medium | ✅ Current | None identified | keep |
| `docs/security-policy.md` | Human | Medium | ✅ Current | None identified | keep |
| `docs/verification.md` | Human | Medium | ✅ Current | None identified | keep |
| `docs/in-cluster-deployment.md` | Human | Medium | ✅ Current | None identified | keep |
| `scripts/verify_all.sh` | Agent/human | High | ✅ Current | None identified | keep |
| `scripts/run_health_once.sh` | Agent/human | High | ✅ Current | None identified | keep |
| `scripts/start_backend.sh` | Human | Medium | ✅ Current | None identified | keep |
| `scripts/start_frontend.sh` | Human | Medium | ✅ Current | None identified | keep |
| `CONTRIBUTING.md` | Human | Low | ❌ NOT PRESENT | Does not exist; not required | N/A |

---

## Status/Action Taxonomy

| Status | Meaning |
|--------|---------|
| **keep** | Doc exists, is current, accurate, and useful |
| **update** | Doc exists but needs factual corrections |
| **merge** | Doc duplicates others; consolidate |
| **archive** | Historical info that should not guide current behavior |
| **delete** | Clearly obsolete and safe to remove |
| **investigate** | Doc is missing or correctness is unclear; needs research |
| **make discoverable** | Doc exists but is not in standard reading paths |

---

## Initial Findings

### Critical: Missing Files Referenced in Agent Guidance

Several files are referenced in `AGENTS.md` and other agent-facing docs but **do not exist**:

1. **`.kilocode/rules/10-agent-mission.md`** — Referenced in:
   - `AGENTS.md` (Full planning path, line 71)
   - `00-global.md` (Read order, line 13)
   - `brief.md` (Governing repo guidance)
   - `progress.md` (Standing Kilo rule files)

2. **`.kilocode/rules/30-output-contracts.md`** — Referenced in:
   - `AGENTS.md` (Fast path, line 44; Full path, line 73)
   - `00-global.md` (Read order, line 15)
   - `20-architecture-doctrine.md` (Relationship section)
   - `brief.md` (Governing repo guidance)

3. **`.kilocode/rules/40-tool-use.md`** — Referenced in:
   - `AGENTS.md` (Fast path, line 45; Full path, line 74)
   - `00-global.md` (Read order, line 16)
   - `20-architecture-doctrine.md` (Relationship section)

4. **`.kilocode/rules/50-kubernetes-monitoring-domain.md`** — Referenced in:
   - `AGENTS.md` (Full path, line 75)
   - `00-global.md` (Read order, line 17)
   - `20-architecture-doctrine.md` (Relationship section)

5. **`.kilocode/rules/memory-bank/tech.md`** — Referenced in:
   - `progress.md` (Memory Bank files section)

6. **`.kilocode/rules/memory-bank/product.md`** — Referenced in:
   - `progress.md` (Memory Bank files section)

7. **`scripts/run_coverage.sh`** — Referenced in:
   - `docs/coverage.md` (Usage instructions)

### Impact

These missing files create a **discoverability gap**: agents following the documented reading paths will encounter references to non-existent files, potentially causing confusion or failed operations.

### `.kilocode/rules/memory-bank/current.md` Assessment

**Currentness:** ⚠️ Partial

| Aspect | Status | Notes |
|--------|--------|-------|
| Describes current repo facts | ⚠️ Partial | Generally accurate but some stale references |
| Points to current commands | ✅ Yes | `scripts/verify_all.sh` exists and is current |
| References valid paths | ⚠️ Partial | References missing files (see above) |
| Describes current verification | ✅ Yes | Verification behavior matches `verify_all.sh` |
| Contains stale historical narrative | ⚠️ Partial | "Current backlog themes" may be outdated |
| Duplicates other docs | ⚠️ Partial | Some overlap with `progress.md` |
| Risks misleading coding agents | ⚠️ Medium | Missing file references could mislead agents |

**Verdict:** The file is mostly accurate but references missing files and may contain stale backlog themes. Safe to update with corrections identified in this audit.

---

## Next-Step Checklist

### Immediate (Safe Updates)

- [ ] Update `.kilocode/rules/memory-bank/current.md` to remove references to missing files
- [ ] Update `progress.md` to remove references to missing `tech.md` and `product.md`
- [ ] Document the missing files as `investigate` items

### Deferred (Require Investigation)

- [ ] Investigate whether `.kilocode/rules/10-agent-mission.md` should be created
- [ ] Investigate whether `.kilocode/rules/30-output-contracts.md` should be created
- [ ] Investigate whether `.kilocode/rules/40-tool-use.md` should be created
- [ ] Investigate whether `.kilocode/rules/50-kubernetes-monitoring-domain.md` should be created
- [ ] Investigate whether `.kilocode/rules/memory-bank/tech.md` should be created
- [ ] Investigate whether `.kilocode/rules/memory-bank/product.md` should be created
- [ ] Investigate whether `scripts/run_coverage.sh` should exist or if `docs/coverage.md` should be updated

### Maintenance Workflow (To Be Added)

- [ ] Define when to update `.kilocode/rules/memory-bank/current.md`
- [ ] Define what belongs in current memory vs historical docs
- [ ] Define how to review docs after major workflow/CI/deployment changes
- [ ] Define how to sample Cline runs and feed findings back into docs

### Tracking

- [ ] Create `docs/agent-run-review-template.md` for lightweight Cline run tracking
- [ ] Establish periodic audit schedule (e.g., quarterly or after major releases)

---

## Maintenance Checklist

### When to Update `.kilocode/rules/memory-bank/current.md`

Update when:
- A major milestone is completed (e.g., beta release, new feature)
- Verification commands or paths change
- New scripts are added or removed
- Architecture direction changes materially
- Product priorities shift significantly

Do NOT update for:
- Small code edits
- Temporary experiments
- Routine day-to-day changes

### What Belongs in Current Memory vs Historical Docs

**Current Memory (`current.md`):**
- Current verification commands and paths
- Current verification gate behavior
- Current product state and priorities
- Current architectural posture
- Stable implementation invariants

**Historical Docs:**
- Completed milestones and decisions → `progress.md`
- Architectural rationale → `architecture.md`
- Product overview → `brief.md`
- Technical details → dedicated `tech.md` (if created)

### How to Review Docs After Major Changes

1. After CI/deployment changes: verify all referenced scripts exist
2. After workflow changes: update reading paths in `AGENTS.md`
3. After architecture changes: update `current.md` and `architecture.md`
4. After adding new docs: ensure they are discoverable via standard reading paths

### How to Sample Cline Runs

1. Use `docs/agent-run-review-template.md` to record each significant run
2. Track which docs were read vs ignored
3. Identify patterns in doc usage
4. Feed findings back into doc improvements

### How to Run the Drift Checker

A documentation drift checker is available to detect broken references:

```bash
.venv/bin/python scripts/check_doc_references.py
```

**What it checks:**
- Backtick-quoted paths in agent-facing docs
- Paths must start with a known prefix (docs/, scripts/, src/, .kilocode/, etc.)
- Flags/commands are excluded (e.g., `verify_all.sh --python-only`)

**What it skips:**
- Short filenames (e.g., `progress.md`) — valid in context
- Code/function names (e.g., `EvidenceRecord`, `run-health-loop`)
- Audit table entries (intentionally-missing files documented there)
- Code blocks

**Scope:** Currently covers 11 key agent-facing docs. Can be extended to scan additional files.

---

## Verification

```bash
# Verify Python lane (proxy for docs-focused verification)
scripts/verify_all.sh --python-only
```

**Result:** VERIFICATION GATE: PASSED (2026-05-16, 8:02)

---

## Files Added/Modified

| File | Action |
|------|--------|
| `docs/agent-docs-audit.md` | Created |
| `docs/agent-run-review-template.md` | Created |
| `.kilocode/rules/memory-bank/current.md` | Updated (removes stale references, fixed coverage claim) |
| `.kilocode/rules/memory-bank/progress.md` | Updated (removed missing file refs) |

---

## Recommended Next Board Item

**[Open] Investigate and resolve missing agent guidance files**

Determine whether the missing files should be created, consolidated, or their references removed from agent-facing docs.

---

## Missing Reference Decisions

| Missing Path | Referenced By | Decision | Rationale | Follow-up |
|--------------|---------------|-----------|-----------|-----------|
| `.kilocode/rules/10-agent-mission.md` | AGENTS.md, 00-global.md, brief.md, progress.md | remove reference | Content distributed across AGENTS.md and 20-architecture-doctrine.md | ✅ RESOLVED: removed from all active reading paths |
| `.kilocode/rules/30-output-contracts.md` | AGENTS.md, 00-global.md, 20-architecture-doctrine.md, brief.md | remove reference | No clear gap this file would fill; existing docs cover the intent | ✅ RESOLVED: removed from all active reading paths |
| `.kilocode/rules/40-tool-use.md` | AGENTS.md, 00-global.md, 20-architecture-doctrine.md | remove reference | Tool use guidance is in 00-global.md and 05-fast-task-bootstrap.md | ✅ RESOLVED: removed from all active reading paths |
| `.kilocode/rules/50-kubernetes-monitoring-domain.md` | AGENTS.md, 00-global.md, 20-architecture-doctrine.md | remove reference | Domain guidance is embedded in existing docs | ✅ RESOLVED: removed from all active reading paths |
| `.kilocode/rules/memory-bank/tech.md` | progress.md | remove reference | Already noted as missing; tech detail scattered across source | ✅ RESOLVED: removed from progress.md |
| `.kilocode/rules/memory-bank/product.md` | progress.md | remove reference | Already noted as missing; product info in brief.md | ✅ RESOLVED: removed from progress.md |
| `scripts/run_coverage.sh` | docs/coverage.md | update reference | Make run_coverage.sh canonical; direct commands as component-level | ✅ RESOLVED: run_coverage.sh is primary; direct commands are component-level examples |

---

## High-Relevance Docs Deep Dive (2026-05-16)

### Coverage Documentation Audit

| Doc | Verdict | Issue | Action Taken | Follow-up |
|-----|---------|-------|-------------|-----------|
| `docs/coverage.md` | ✅ Corrected | Direct pytest/vitest commands presented as "Full Coverage Report" without noting `run_coverage.sh` as canonical | Made `run_coverage.sh` primary; direct commands are "Component-Level Commands" | None |

### Verification Documentation Audit

| Doc | Verdict | Issue | Action Taken | Follow-up |
|-----|---------|-------|-------------|-----------|
| `docs/verification.md` | ✅ Current | None identified | N/A | None |

### Agent Guidance Audit

| Doc | Verdict | Issue | Action Taken | Follow-up |
|-----|---------|-------|-------------|-----------|
| `AGENTS.md` | ✅ Current | Stale reading paths | ✅ Cleaned in previous slice | None |
| `.kilocode/rules/00-global.md` | ✅ Current | Stale reading paths | ✅ Cleaned in previous slice | None |
| `.kilocode/rules/05-fast-task-bootstrap.md` | ✅ Current | None identified | N/A | None |
| `.kilocode/rules/20-architecture-doctrine.md` | ✅ Current | Stale relationship section | ✅ Cleaned in previous slice | None |
| `.kilocode/rules/memory-bank/current.md` | ✅ Current | Stale references | ✅ Cleaned in previous slice | None |
| `.kilocode/rules/memory-bank/brief.md` | ✅ Current | Stale standing rules | ✅ Cleaned in previous slice | None |
| `.kilocode/rules/memory-bank/progress.md` | ✅ Current | Stale references | ✅ Cleaned in previous slice | None |
| `docs/data-model.md` | ✅ Current | None identified | N/A | None |
| `README.md` | ✅ Current | None identified | N/A | None |

### Summary

| Category | Count |
|----------|-------|
| Useful/Current | 15 |
| Corrected | 8 |
| Stale/Investigate | 0 |
| Duplicate/Merge | 0 |
| Not agent-facing | 5 |
| **Total audited** | **28** |
