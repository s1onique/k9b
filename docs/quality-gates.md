# Quality Gates

**Purpose:** Document the automated quality gates that enforce repository standards in CI and locally.

## Overview

k9b uses multiple automated quality gates to maintain code quality, consistency, and LLM-friendliness. These gates run in CI on every pull request and can be run locally via `scripts/verify_all.sh`.

## Active Quality Gates

| Gate | Tool | Threshold | CI Job | Purpose |
|------|------|-----------|--------|---------|
| Python lint | ruff | 0 errors | `lint` | Code style, imports, best practices |
| Type checking | mypy | 0 errors | `lint` | Type safety |
| File size | `check_llm_friendly_files.py` | < 500 lines | `lint` | LLM-reasoning friendly modules |
| Duplicate code | jscpd | < 4.0% | `lint` | Prevent copy/paste drift |
| Unit tests | pytest | 0 failures | `python-unit-tests` | Core behavior coverage |
| Frontend tests | vitest | 0 failures | `frontend` | UI component coverage |
| Helm validation | `verify_helm_chart.sh` | pass | `helm-chart` | Chart correctness |

## Duplicate Code Gate

**Tool:** [jscpd](https://github.com/kucherenko/jscpd) (language-agnostic duplicate detection)

### Purpose

The duplicate-code gate prevents unintentional copy/paste drift that can occur after module extraction. A split is not complete if it merely moves duplicated logic into smaller files.

### Configuration

- **Config file:** `.jscpd.json`
- **Threshold:** 4.0% (initial baseline, set above measured 3.78% to allow for measurement variance)
- **Min duplicate block:** 8 lines or 80 tokens
- **Mode:** mild (report duplicates without blocking on minor noise)

### Baseline Policy

The initial threshold was set based on measured repository state (2026-07-01):

| Metric | Value |
|--------|-------|
| **Total Duplication** | 3.78% lines, 4.56% tokens |
| **Python Duplication** | 3.15% lines, 3.78% tokens |
| **TypeScript/TSX Duplication** | 1.31% / 7.41% |
| **Files Analyzed** | 2,155 |
| **Clones Found** | 664 |

**Initial threshold:** 4.0% (set above measured 3.78% to allow for measurement variance)

**Ratchet policy:** Lower threshold by 0.2-0.5% after each significant duplicate-removal cleanup. Target: < 3.5% within 3 cleanup cycles.

### Acceptable Duplication

Some duplication is intentionally acceptable:

- **Tiny repeated assertions** — inline test assertions that would be harder to read if extracted
- **Table-driven test cases** — explicit repetition that documents behavior variations clearly
- **Helm/YAML boilerplate** — where abstraction would reduce readability or Helm templating would add complexity
- **Compatibility façade re-exports** — intentional API compatibility layers
- **Generated or lock files** — excluded from detection entirely

### Unacceptable Duplication

Large duplicate blocks that should trigger extraction:

- **Repeated backend HTTP/curl parsing logic**
- **Repeated incident API JSON-shape normalization**
- **Repeated diagnosis-loop artifact parsing**
- **Repeated frontend fetch/error handling**
- **Repeated test fixture construction that should be a helper**
- **Repeated CI/YAML logic that should be a reusable job/template/helper**

### Running Locally

```bash
make check-duplicates
```

### CI Behavior

- Runs in the `lint` job (parallel with ruff, mypy, and doctrine checks)
- Report uploaded to `artifacts/jscpd` regardless of pass/fail
- Gate fails if duplication percentage exceeds threshold

## File Size Gate

**Tool:** `scripts/check_llm_friendly_files.py`

### Thresholds

| Level | Lines | Behavior |
|-------|-------|----------|
| Warning | > 300 | Non-blocking, logged |
| Failure | > 500 | Gate fails, file must be split |

### Doctrine

The file-size gate prevents modules from becoming too large to reason about. The duplicate-code gate prevents extracted modules from becoming copy/paste islands. A split is not complete if it merely moves duplicated logic into smaller files.

See [docs/doctrine/llm-friendly-files.md](doctrine/llm-friendly-files.md) for full doctrine.

### Running Locally

```bash
python scripts/check_llm_friendly_files.py
python scripts/check_llm_friendly_files.py --quiet  # Failures only
python scripts/check_llm_friendly_files.py --changed-only  # Fast path
```

## Verification Commands

### Local (Full Gate)

```bash
./scripts/verify_all.sh
```

### Local (Fast Path)

```bash
./scripts/verify_all.sh --fast
```

### Local (ACT-Local)

For bounded verification on changed files only:

```bash
./scripts/verify_all.sh --act-local
```

### Individual Gates

```bash
make check-duplicates  # Duplicate code
ruff check src tests   # Python lint
mypy src              # Type checking
pytest tests/         # Unit tests (slow)
```

## Related Documents

- [docs/doctrine/llm-friendly-files.md](doctrine/llm-friendly-files.md) — File size doctrine
- [docs/doctrine/documentation-truthfulness.md](doctrine/documentation-truthfulness.md) — Documentation standards
- [docs/doctrine/shell-containment.md](doctrine/shell-containment.md) — Shell script safety
