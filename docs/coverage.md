# Code Coverage Guide

This document describes the code coverage reporting setup for k9b.

## Overview

Code coverage reporting is implemented for both backend (Python) and frontend (TypeScript/React) to provide insight into test coverage without introducing hard pass/fail thresholds. This is the first step of the coverage epic - baseline reporting only.

## Running Coverage

### Full Coverage Report

```bash
./scripts/run_coverage.sh
```

### Backend Only

```bash
./scripts/run_coverage.sh backend
```

### Frontend Only

```bash
./scripts/run_coverage.sh frontend
```

### Alternative: Run via project test commands

Backend:
```bash
.venv/bin/python -m pytest --cov=src/k8s_diag_agent tests/
```

Frontend:
```bash
cd frontend && npm run test:ui -- --coverage
```

## Coverage Artifacts

All artifacts are written to the `coverage/` directory at the repo root:

### Backend (Python/pytest)

| Artifact | Path | Purpose |
|----------|------|---------|
| XML | `coverage/backend/coverage.xml` | Machine-readable, CI-friendly |
| JSON | `coverage/backend/coverage.json` | Machine-readable, CI-friendly |
| Lcov | `coverage/backend/coverage.info` | CI-friendly format |
| HTML | `coverage/backend/coverage_html/index.html` | Human-readable report |

### Frontend (TypeScript/vitest)

| Artifact | Path | Purpose |
|----------|------|---------|
| JSON | `coverage/frontend/coverage-final.json` | Machine-readable |
| HTML | `coverage/frontend/index.html` | Human-readable report |

## Exclusions and Justification

Exclusions are minimal and intentional. We exclude only:

### Backend Exclusions

- `tests/*` - Test infrastructure itself is not part of production code
- `src/k8s_diag_agent/__init__.py` - Package-level bootstrap/initialization, no testable business logic
- `src/k8s_diag_agent/cli.py` - CLI entrypoint that routes to handlers; business logic lives in modules

Note: `models.py` and `schemas.py` are **included** in coverage because they contain data validation logic, type conversions, and helper methods that benefit from test coverage.

### Frontend Exclusions

- `node_modules/`, `dist/`, `.vite/` - Build artifacts
- `vitest.config.ts` - Test configuration
- `src/vitest.setup.ts` - Test setup (JSDOM configuration)
- `src/main.tsx` - React entrypoint (DOM mounting only)
- `src/types.ts` - TypeScript type definitions (no runtime logic)
- `src/theme.ts` - Theme configuration (static values)
- `src/themes.css`, `src/index.css` - Styling (no JS logic)
- `**/*.{test,spec}.{ts,tsx}` - Test files themselves

Note: `src/App.tsx` is **included** in coverage because it contains substantial workflow/business logic.

### What Is Being Measured

**Backend**: All production code under `src/k8s_diag_agent/` except the exclusions listed above:
- `collect/` - Kubernetes data collection
- `correlate/` - Signal correlation
- `health/` - Health assessment logic
- `reason/` - Reasoning engine
- `recommend/` - Recommendation generation
- `render/` - Output rendering
- `ui/` - UI API and model logic
- And all other domain modules

**Frontend**: Business logic in `src/` including:
- `App.tsx` - Main component with workflow logic
- `api.ts` - API communication
- `src/components/` - Component logic

## Coverage Policy

### Current Status: Mandatory (Enforced)

Coverage reporting is now mandatory and enforced via CI thresholds:

- **Backend line coverage threshold**: 80% (`--cov-fail-under=80` in pytest)
- **Frontend line/statement coverage threshold**: 90% (Vitest threshold configuration)
- **Branch/function coverage**: Tracked but not yet enforced (informational only)
- **CI artifacts uploaded**: Coverage reports are generated and uploaded as CI artifacts
- **Blocking**: Coverage job now blocks merge on threshold violations

### Thresholds

| Component | Metric | Threshold | Status |
|-----------|--------|-----------|--------|
| Backend (Python) | Line coverage | 80% | Enforced |
| Frontend (TypeScript) | Lines | 90% | Enforced |
| Frontend (TypeScript) | Statements | 90% | Enforced |
| Backend (Python) | Branch coverage | N/A | Tracked (not enforced) |
| Frontend (TypeScript) | Branch coverage | N/A | Tracked (not enforced) |
| Frontend (TypeScript) | Function coverage | N/A | Tracked (not enforced) |

### CI Integration

Coverage runs as a separate job in `.github/workflows/verify.yml`:

- Runs on all PRs, main push, and manual dispatch
- **MANDATORY**: Job failure blocks merge on threshold violations
- Uploads coverage artifacts (XML, JSON, Lcov, HTML) to CI artifacts
- Displays coverage summary in CI logs
- Artifacts uploaded even on failure (`if: always()`)

### Manual vs CI Coverage

| Aspect | Manual | CI |
|--------|--------|-----|
| Trigger | `scripts/run_coverage.sh` | Every PR/push |
| Artifacts | `coverage/` directory | CI artifacts (7-day retention) |
| Blocking | No | No |
| Display | Terminal output | CI logs |

### Notes

- The `coverage/` directory is gitignored to avoid committing large artifacts
- Coverage artifacts are stored in CI for 7 days
- Current baseline: ~82% line coverage, ~67% branch coverage
