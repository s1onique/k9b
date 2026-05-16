# Agent Run Review Template

Use this template to record significant agent (Cline/Kilo) runs for later analysis. This helps track which docs agents actually read/use versus ignore.

---

## Quick Start

```markdown
# Agent Run: YYYY-MM-DD-<short-id>

**Date:** YYYY-MM-DD
**Agent:** cline / kilo / other
**Task:** <one-line summary>

## Docs Read
- <doc path 1>
- <doc path 2>

## Docs Referenced in Final Answer/Patch
- <doc path 1>
- <doc path 2>

## Issues
- <issue 1>
- <issue 2>

## Outcome
[PASS / PARTIAL / FAIL]

## Notes
<observations, insights, suggestions for doc improvement>
```

---

## Full Template

```markdown
# Agent Run Review

## Run Metadata

| Field | Value |
|-------|-------|
| **Run ID** | YYYY-MM-DD-<short-id> |
| **Date** | YYYY-MM-DD |
| **Agent/Tool** | cline / kilo / other |
| **Task Summary** | <brief description of the task> |

---

## Documentation Usage

### Docs Read
List all documentation files read during this run.

- `AGENTS.md`
- `.kilocode/rules/00-global.md`
- `.kilocode/rules/05-fast-task-bootstrap.md`
- `.kilocode/rules/20-architecture-doctrine.md`
- `.kilocode/rules/memory-bank/current.md`
- `docs/data-model.md`
- <other>

### Docs Referenced in Final Answer/Patch
List docs that were actually referenced in the final answer, code changes, or recommendations.

- <doc path 1>
- <doc path 2>

### Docs That Appeared Stale or Misleading
Mark docs that contained outdated, incorrect, or confusing information.

| Doc Path | Issue |
|----------|-------|
| | |

### Docs That Would Have Helped But Were Missing
Mark docs that should exist but don't, or topics that lacked documentation.

| Topic | Missing Doc Path (if known) |
|-------|---------------------------|
| | |

---

## Commands Used

List commands run during this session.

```
<command 1>
<command 2>
```

---

## Verification

**Verification Command:** `<command>`

**Result:** [PASS / FAIL / SKIPPED / N/A]

---

## Outcome

| Aspect | Status |
|--------|--------|
| **Task Completion** | [COMPLETE / PARTIAL / INCOMPLETE] |
| **Verification Gate** | [PASSED / FAILED / SKIPPED] |
| **Documentation Quality** | [GOOD / NEEDS IMPROVEMENT / POOR] |

---

## Notes

### What Worked Well
-

### What Could Be Improved
-

### Suggestions for Documentation
-

### Patterns Observed
- Agent read: X docs
- Agent referenced: Y docs
- Gap: X - Y docs read but not used
- Missing docs that would have helped: Z

---

## JSON Record (Machine-Readable)

For future tooling and analysis, use this JSON shape:

```json
{
  "run_id": "YYYY-MM-DD-<short-id>",
  "date": "YYYY-MM-DD",
  "agent": "cline",
  "task_summary": "",
  "docs_read": [],
  "docs_referenced": [],
  "stale_or_misleading_docs": [],
  "missing_docs_that_would_have_helped": [],
  "commands_used": [],
  "verification_result": "",
  "outcome": "",
  "notes": ""
}
```

---

## Example Entry

```markdown
# Agent Run: 2026-05-16-001

**Date:** 2026-05-16
**Agent:** cline
**Task:** Fix ruff lint error in health loop

## Docs Read
- `AGENTS.md`
- `.kilocode/rules/00-global.md`
- `.kilocode/rules/05-fast-task-bootstrap.md`
- `src/k8s_diag_agent/health/loop.py`

## Docs Referenced in Final Answer/Patch
- `.kilocode/rules/05-fast-task-bootstrap.md`

## Docs That Appeared Stale or Misleading
- None identified

## Docs That Would Have Helped But Were Missing
- None identified

## Commands Used
```
.venv/bin/python -m ruff check src/k8s_diag_agent/health/loop.py
```

## Verification
**Verification Command:** `scripts/verify_all.sh --python-only`

**Result:** PASS

## Outcome
| Aspect | Status |
|--------|--------|
| **Task Completion** | COMPLETE |
| **Verification Gate** | PASSED |
| **Documentation Quality** | GOOD |

## Notes

### What Worked Well
- Bootstrap files provided clear guidance
- Fast task path was appropriate for the task

### What Could Be Improved
- None

### Suggestions for Documentation
- None

### Patterns Observed
- Agent read: 4 docs
- Agent referenced: 1 doc
- Gap: 3 docs read but not used (expected for focused bug fix)
```

---

## Usage Guidelines

1. **When to record:** Record significant runs where an agent made changes or recommendations.
2. **When to skip:** Skip trivial commands (git status, ls) unless they reveal doc issues.
3. **What to capture:** Focus on documentation quality, not the task itself.
4. **How to analyze:** Periodically review entries to identify patterns in doc usage.

## Storage

Store completed reviews in `runs/agent-reviews/` with the filename pattern:
`YYYY-MM-DD-<short-id>.md`

Example: `runs/agent-reviews/2026-05-16-001.md`
