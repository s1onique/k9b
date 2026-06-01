# Health Assessment Remaining Seams

**ACT**: `[Open] ACT: Remap remaining health assessment seams`  
**Generated**: 2026-06-01
**Status**: RECONNAISSANCE COMPLETE

---

## 1. Current State

| Metric | Value |
|--------|-------|
| `loop.py` lines | 2,907 |
| `build_health_assessment()` lines | 366 (lines 667-1032) |
| `loop_scheduler.py` lines | 743 |
| Allowlist entry | Present for both `loop.py` and `loop_scheduler.py` |
| Checker result | 0 failures (200 warnings, non-blocking) |
| Tests | 165 passed in 6.65s |

### Extracted Module Line Counts

| Module | Lines |
|--------|-------|
| `loop_assessment_warning_events.py` | 315 |
| `loop_assessment_image_pull.py` | 93 |
| `loop_assessment_regressions.py` | 157 |
| `loop_assessment_summary.py` | 107 |
| `loop_assessment_missing_evidence.py` | 113 |
| `loop_assessment_baseline.py` | 170 |
| `loop_assessment_history_drift.py` | 176 |
| `loop_assessment_counts.py` | 167 |

### Test File Line Counts

| Test File | Lines |
|-----------|-------|
| `test_loop_assessment_counts.py` | 464 |
| `test_loop_assessment_regressions.py` | 498 |
| `test_loop_assessment_warning_events.py` | 429 |
| `test_loop_assessment_missing_evidence.py` | 474 |
| `test_loop_assessment_history_drift.py` | 396 |
| `test_loop_assessment_image_pull.py` | 224 |
| `test_loop_assessment_summary.py` | 162 |
| `test_loop_assessment_baseline.py` | 204 |

---

## 2. Current Extracted Seams

All eight sub-seams have been extracted. The caller in `loop.py` retains glue code for:

### 2.1 ImagePullBackOff Caller Glue (Lines 816-837)

```python
# ImagePullBackOff count issue (recorded here to preserve order before assess_image_pull_issues)
if pod_counts.image_pull_backoff > 0:
    workload_issue_present = True
    issues_detected = True
    references.append("ImagePullBackOff")
    _record_issue(...)
    from .loop_assessment_image_pull import assess_image_pull_issues
    returned_hypothesis, image_pull_issues_detected = assess_image_pull_issues(...)
    if returned_hypothesis is not None:
        insight_hypothesis = returned_hypothesis
    issues_detected = issues_detected or image_pull_issues_detected
```

**Preserved ordering**: ImagePullBackOff is counted before job failures and warning events per original sequence.

### 2.2 Job Failure Block (Lines 839-848)

```python
# Job failures (after ImagePullBackOff to preserve original ordering)
if job_failures > 0:
    workload_issue_present = True
    issues_detected = True
    references.append("job failures")
    _record_issue(f"{job_failures} failed job(s) observed.", ...)
```

### 2.3 Warning-Event Threshold Block (Lines 850-864)

```python
# Warning event threshold (after job failures to preserve original ordering)
warning_threshold = warning_event_threshold
warning_triggered = warning_event_count > 0 if warning_threshold <= 0 else warning_event_count >= warning_threshold
if warning_triggered:
    workload_issue_present = True
    issues_detected = True
    references.append("warning events")
    latest_warning = warning_events[0] if warning_events else None
    warning_desc = f" {latest_warning.reason} in {latest_warning.namespace}" if ... else ""
    threshold_note = f" (threshold {warning_threshold})" if warning_threshold > 0 else ""
    _record_issue(f"{warning_event_count} warning events recorded{threshold_note}{warning_desc}.", ...)
```

---

## 3. Remaining `build_health_assessment()` Block Inventory

| Lines | Concern | Local State Touched | Creates Signals/Findings/Hypotheses/Next Checks | Changes `issues_detected` | Affects ID Ordering | Extraction Risk |
|-------|---------|---------------------|-----------------------------------------------|--------------------------|---------------------|-----------------|
| 688-696 | `add_signal` helper | `signals`, `generator` | Creates Signal | No | Yes (ID generator) | **HIGH** |
| 698-708 | `record_finding` helper | `issue_findings`, `generator` | Creates Finding | No | Yes (ID generator) | **HIGH** |
| 710-713 | `_record_issue` helper | Uses `add_signal` + `record_finding` | Creates Signal + Finding | No | Yes (ID generator) | **HIGH** |
| 716 | Snapshot captured signal | `signals` | Creates Signal | No | Yes | LOW |
| 717-728 | Helm error check | `issues_detected` | Creates Signal + Finding | **Yes** | Yes | MEDIUM |
| 754-767 | Control plane version check | `issues_detected` | Creates Signal + Finding | **Yes** | Yes | MEDIUM |
| 729-738 | Variable initializations | Multiple lists/dicts | No | No | No | **LOW** (pure setup) |
| 756-757 | Version missing detection | `issues_detected` | Creates Signal | **Yes** | Yes | MEDIUM |
| 816-837 | ImagePullBackOff glue | `workload_issue_present`, `issues_detected`, `references`, `insight_hypothesis` | Creates Signal, Finding, Hypothesis | **Yes** | Yes | **MEDIUM-HIGH** (ordering dependent) |
| 839-848 | Job failures block | `workload_issue_present`, `issues_detected`, `references` | Creates Signal, Finding | **Yes** | Yes | **MEDIUM-HIGH** (ordering dependent) |
| 850-864 | Warning threshold block | `workload_issue_present`, `issues_detected`, `references` | Creates Signal, Finding | **Yes** | Yes | **MEDIUM-HIGH** (ordering dependent) |
| 916-923 | Findings generation | `findings` list | Creates Finding | No | Yes | LOW (pure assembly) |
| 925-953 | Hypothesis aggregation | `hypotheses` list | Creates Hypothesis | No | Yes | LOW (pure assembly) |
| 955-985 | Next checks assembly | `next_checks` list | Creates NextCheck | No | No | **LOW** |
| 987-992 | Assessment action | `assessment_action` | Creates RecommendedAction | No | No | LOW |
| 994-1004 | Assessment assembly | `assessment` | Creates Assessment | No | Yes | LOW (pure assembly) |
| 1005-1014 | Result construction | Final return | Creates HealthAssessmentResult | No | No | **LOW** |

---

## 4. Candidate Next Seams

### Option A — ImagePullBackOff Caller Glue

**Module**: `src/k8s_diag_agent/health/loop_assessment_image_pull_flow.py`  
**Size**: ~21 lines  
**Scope**: Lines 816-837

**Content**:
- Setting `workload_issue_present` flag
- Appending `"ImagePullBackOff"` to references
- Calling `_record_issue()`
- Delegating to `assess_image_pull_issues()`
- Updating `insight_hypothesis` and `issues_detected`

**Risk**: **MEDIUM-HIGH**
- Ordering dependency: Must execute after count assessment and before job failures
- Hypothesis state mutation across multiple variables
- ID ordering depends on signal creation sequence

**Mitigation possible**: Pass all mutable state as parameters and return consolidated result.

### Option B — Job Failure + Warning-Event Threshold Tail

**Module**: `src/k8s_diag_agent/health/loop_assessment_tail_counts.py`  
**Size**: ~30 lines  
**Scope**: Lines 839-864

**Content**:
- Job failure detection and signal creation
- Warning event threshold evaluation
- Warning event signal creation with formatting

**Risk**: **MEDIUM-HIGH**
- Ordering dependency: Must execute after ImagePullBackOff and before regression
- References mutation affects downstream summary derivation

### Option C — Result Construction

**Module**: `src/k8s_diag_agent/health/loop_assessment_result.py`  
**Size**: ~19 lines  
**Scope**: Lines 1005-1014

**Content**:
- Pure object assembly: `HealthAssessmentResult(...)`
- All inputs are already computed
- No side effects

**Risk**: **LOW**
- Pure transformation with no ID ordering impact
- Inputs already contain all computed values

### Option D — Cleanup-Only ACT

**Changes**:
1. Consolidate assessment module imports from inline to top-level
2. Remove unused parameter `job_failures` from `assess_count_issues()` (passed but not used)
3. Identify other unused parameters in count helper signature

**Size**: ~15-20 lines of cleanup  
**Risk**: **LOW**

---

## 5. Recommendation

**Selected: Option D — Cleanup-Only ACT**

### Rationale

1. **Safest path**: No behavior changes, no ID ordering risk, no ordering dependencies
2. **Unblocks future extractions**: Clean signatures make the next extraction contract clearer
3. **Below 500-line threshold**: This is a small cleanup task, well within limits
4. **Prerequisite for later work**: Clean parameter signatures make Option A, B, C easier to implement later

### Why Not Other Options

- **Option A (ImagePullBackOff glue)**: Ordering dependencies are fragile without test coverage for the extracted module. The `insight_hypothesis` state mutation is complex.

- **Option B (Tail counts)**: References ordering and ID sequence dependencies make this risky without targeted tests.

- **Option C (Result construction)**: Lowest risk but least impactful. The 19-line pure assembly adds little value to extract.

### Cleanup Targets

1. **Inline imports to top-level** in `build_health_assessment()`:
   - `assess_missing_evidence` (line 741)
   - `assess_previous_run_drift` (line 781)
   - `assess_image_pull_issues` (line 826)
   - `check_regression_from_history` (line 865)
   - `match_warning_event_patterns` (line 880)
   - `derive_assessment_summary` (line 897)

2. **Unused parameter removal**:
   - `assess_count_issues()` still accepts `job_failures` and `warning_event_threshold`, but after the split design it only handles node health, pod readiness, pod scheduling, CrashLoopBackOff, and warning_event_count calculation. Remove unused parameters only after confirming they are truly unused by the helper and tests.
   - Verify both parameters are truly unused before removing either.

3. **Unused variable cleanup**:
   - `matched_event_ids` is populated but never read after pattern matching

---

## 6. Next Implementation Prompt

**Title**: `[Open] ACT: Clean up health assessment function signature and imports`

### Objective

Perform cleanup-only changes to `build_health_assessment()` that reduce maintenance burden without changing behavior.

### Constraints

- No behavior changes
- No JSON artifact shape changes
- No timestamp semantics changes
- All tests must pass unchanged
- Do not move production logic code
- Keep `loop.py` on the allowlist

### Pre-flight: Identify Cleanup Targets

```bash
# Check which assessment module imports are inline (within function)
grep -n "from .loop_assessment_" src/k8s_diag_agent/health/loop.py

# Check assess_count_issues signature and usage
grep -n "def assess_count_issues\|job_failures" src/k8s_diag_agent/health/loop_assessment_counts.py
```

### Steps

1. **Move inline imports to top-level** (guard against circular imports):
   - Move `assess_missing_evidence` import to top-level
   - Move `assess_previous_run_drift` import to top-level
   - Move `assess_image_pull_issues` import to top-level
   - Move `check_regression_from_history` import to top-level
   - Move `match_warning_event_patterns` import to top-level
   - Move `derive_assessment_summary` import to top-level
   - After moving each import, verify with ruff, mypy, and targeted pytest. If any circular import appears, leave that import local and document why in the commit message.

2. **Remove unused parameters**:
   - Remove `job_failures` parameter from `assess_count_issues()` call if confirmed unused
   - Update `loop_assessment_counts.py` signature accordingly

3. **Remove unused variables** (if any):
   - Identify `matched_event_ids` usage after extraction
   - Remove if confirmed unused

4. **Verify**:
   ```bash
   .venv/bin/python -m ruff check src/k8s_diag_agent/health/loop.py
   .venv/bin/python -m mypy src/k8s_diag_agent/health/loop.py
   .venv/bin/python -m pytest tests/unit/test_loop_assessment_*.py -q
   python scripts/check_llm_friendly_files.py --quiet
   ```

5. **Commit**: "Clean up build_health_assessment imports and unused parameters"

### Test Requirements

- All 165 existing tests must pass
- No new tests required (cleanup only)

### Verification Commands

```bash
.venv/bin/python -m ruff check src/k8s_diag_agent/health/loop.py
.venv/bin/python -m mypy src/k8s_diag_agent/health/loop.py
.venv/bin/python -m pytest tests/unit/test_loop_assessment_*.py tests/unit/test_health_loop*.py tests/unit/test_loop*.py -q
python scripts/check_llm_friendly_files.py --quiet
```

### Acceptance Criteria

- [ ] Inline imports moved to top-level (6 imports)
- [ ] Unused `job_failures` parameter removed from `assess_count_issues()` if confirmed unused
- [ ] No behavior changes in any assessment flow
- [ ] All 165 tests pass
- [ ] LLM-friendly checker reports 0 failures
- [ ] `loop.py` remains on allowlist

---

## 7. Verification Summary

| Check | Result |
|-------|--------|
| `loop.py` line count | 2,907 |
| `build_health_assessment()` line count | 366 (lines 667-1032) |
| `loop_scheduler.py` line count | 743 |
| Allowlist status | Both files present |
| Checker failures | 0 |
| Tests passed | 165/165 |

---

## 8. Files Created/Modified

- `docs/reports/health-assessment-remaining-seams.md` — this report

---

## 9. Post-Extraction Cleanup Candidates

After the cleanup ACT, the next recommended extraction candidates in order of safety:

1. **Option C — Result Construction** (19 lines, pure assembly, lowest risk)
2. **Option A — ImagePullBackOff caller glue** (requires test coverage for extracted module)
3. **Option B — Job failure + warning threshold tail** (requires test coverage and reference ordering)

---

*Report generated by reconnaissance ACT on 2026-06-01*
